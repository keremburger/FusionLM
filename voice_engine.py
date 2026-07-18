"""
voice_engine.py — FusionLM için TTS (EdgeTTS / Kokoro / ElevenLabs) ve
STT (Whisper, ambient-noise kalibrasyonlu) motorları.

chat_window.py bu modülden şunları bekler:
    - SmartTTS(cfg).speak(text, on_start=callable, on_done=callable) / .stop()
    - WhisperMicWorker(whisper_model, language, wake_word) -> QThread
        sinyaller: finished(str), error(str), level(float)
"""
import asyncio
import os
import tempfile
import time

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, QObject

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

# Sohbet diline göre otomatik EdgeTTS ses eşlemesi
EDGE_TTS_VOICE_MAP = {
    "English": "en-US-GuyNeural", "Turkish": "tr-TR-AhmetNeural",
    "Spanish": "es-ES-AlvaroNeural", "French": "fr-FR-HenriNeural",
    "German": "de-DE-ConradNeural", "Italian": "it-IT-DiegoNeural",
    "Portuguese": "pt-BR-AntonioNeural", "Russian": "ru-RU-DmitryNeural",
    "Chinese": "zh-CN-YunxiNeural", "Japanese": "ja-JP-KeitaNeural",
    "Korean": "ko-KR-InJoonNeural", "Arabic": "ar-SA-HamedNeural",
    "Hindi": "hi-IN-MadhurNeural", "Dutch": "nl-NL-MaartenNeural",
    "Swedish": "sv-SE-MattiasNeural", "Norwegian": "nb-NO-FinnNeural",
    "Polish": "pl-PL-MarekNeural", "Ukrainian": "uk-UA-OstapNeural",
    "Vietnamese": "vi-VN-NamMinhNeural", "Greek": "el-GR-NestorasNeural",
}


class _TTSWorker(QThread):
    started_speaking = pyqtSignal()
    finished_speaking = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, cfg, text):
        super().__init__()
        self.cfg = cfg
        self.text = text
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _voice(self):
        if self.cfg.get("tts_auto_voice", True):
            lang = self.cfg.get("language", "English")
            return EDGE_TTS_VOICE_MAP.get(lang, "en-US-GuyNeural")
        return self.cfg.get("tts_voice", "en-US-GuyNeural")

    def run(self):
        try:
            engine = self.cfg.get("tts_engine", "edgetts")
            if engine == "elevenlabs":
                path = self._synth_elevenlabs()
            elif engine == "kokoro":
                path = self._synth_kokoro()
            else:
                path = self._synth_edgetts()

            if self._stop_flag or not path:
                return

            self.started_speaking.emit()
            self._play_file(path)
            try:
                os.remove(path)
            except OSError:
                pass
            self.finished_speaking.emit()
        except Exception as e:
            self.failed.emit(str(e))

    # ---- sentezleme backend'leri: her biri geçici bir ses dosyası yolu döner ----

    def _synth_edgetts(self):
        import edge_tts
        voice = self._voice()
        speed = self.cfg.get("tts_speed", 1.0)
        rate_str = f"{int((speed - 1) * 100):+d}%"

        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        async def _gen():
            communicate = edge_tts.Communicate(self.text, voice, rate=rate_str)
            await communicate.save(path)

        asyncio.run(_gen())
        return path

    def _synth_elevenlabs(self):
        import requests
        api_key = self.cfg.get("elevenlabs_api_key", "")
        if not api_key:
            raise RuntimeError("ElevenLabs API key is not set (Settings → Voice).")
        voice_id = self.cfg.get("tts_voice") or "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        payload = {"text": self.text, "model_id": "eleven_multilingual_v2"}
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()

        fd, path = tempfile.mkstemp(suffix=".mp3")
        with os.fdopen(fd, "wb") as f:
            f.write(resp.content)
        return path

    def _synth_kokoro(self):
        # Kokoro Türkçe desteklemiyor (bkz. README/FAQ)
        from kokoro import KPipeline
        import soundfile as sf

        pipeline = KPipeline(lang_code="a")
        chunks = [audio for _, _, audio in
                  pipeline(self.text, voice=self.cfg.get("tts_voice", "af_heart"))]
        if not chunks:
            raise RuntimeError("Kokoro produced no audio.")
        full_audio = np.concatenate(chunks)

        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        sf.write(path, full_audio, 24000)
        return path

    def _play_file(self, path):
        """miniaudio ile decode edip sounddevice üzerinden çalar (mp3/wav)."""
        try:
            import miniaudio
            import sounddevice as sd

            decoded = miniaudio.decode_file(path)
            audio = np.frombuffer(decoded.samples, dtype=np.int16)
            audio = audio.reshape(-1, decoded.nchannels)
            sd.play(audio, decoded.sample_rate)
            while True:
                stream = sd.get_stream()
                if not stream or not stream.active:
                    break
                if self._stop_flag:
                    sd.stop()
                    break
                time.sleep(0.05)
        except Exception as e:
            print(f"[TTS] Playback failed: {e}")


class SmartTTS(QObject):
    """cfg'ye ('tts_engine') göre EdgeTTS / Kokoro / ElevenLabs'ı yöneten sarmalayıcı."""

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._worker: _TTSWorker | None = None

    def speak(self, text, on_start=None, on_done=None):
        self.stop()
        self._worker = _TTSWorker(self.cfg, text)
        if on_start:
            self._worker.started_speaking.connect(on_start)
        if on_done:
            self._worker.finished_speaking.connect(on_done)
            self._worker.failed.connect(lambda _e: on_done())
        self._worker.failed.connect(lambda e: print(f"[TTS] {e}"))
        self._worker.start()

    def stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(500)
        self._worker = None


# ---------------------------------------------------------------------------
# STT — Whisper, ambient-noise kalibrasyonlu mikrofon dinleyici
# ---------------------------------------------------------------------------

class WhisperMicWorker(QThread):
    """
    Mikrofonu ~400ms sessizlik ile kalibre eder, sonra konuşma başlayana ve
    tekrar sessizliğe dönene (ya da max_record_secs dolana) kadar kaydeder,
    stt.py içindeki WhisperSTT ile transkribe eder.
    """

    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    level = pyqtSignal(float)

    def __init__(self, whisper_model="base", language="auto", wake_word=None,
                 mic_device=None, samplerate=16000, max_record_secs=20):
        super().__init__()
        self.whisper_model = whisper_model
        self.language = language
        self.wake_word = wake_word
        self.mic_device = mic_device  # cihaz adı (str) ya da None -> sistem varsayılanı
        self.samplerate = samplerate
        self.max_record_secs = max_record_secs
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _resolve_device(self, sd):
        """cfg'de kayıtlı mikrofon adını sounddevice cihaz index'ine çevirir.
        Bulunamazsa (cihaz çıkarıldı/isim değişti vb.) sessizce sistem
        varsayılanına döner."""
        if not self.mic_device:
            return None
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0 and dev["name"] == self.mic_device:
                    return idx
        except Exception:
            pass
        return None

    def _record_until_silence(self, sd, threshold, device):
        block_dur = 0.1
        block_size = int(self.samplerate * block_dur)
        chunks = []
        speaking = False
        silence_blocks = 0
        max_blocks = int(self.max_record_secs / block_dur)

        with sd.InputStream(samplerate=self.samplerate, channels=1, dtype="float32",
                             device=device) as stream:
            for _ in range(max_blocks):
                if self._stop_flag:
                    break
                block, _ = stream.read(block_size)
                block = block[:, 0]
                level = float(np.abs(block).mean())
                self.level.emit(min(level * 20, 1.0))

                if level > threshold:
                    speaking = True
                    silence_blocks = 0
                    chunks.append(block)
                elif speaking:
                    silence_blocks += 1
                    chunks.append(block)
                    if silence_blocks > 8:  # ~0.8s sessizlik -> turu bitir
                        break

        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks)

    def run(self):
        try:
            import sounddevice as sd
        except ImportError:
            self.error.emit("sounddevice not installed. Run: pip install sounddevice")
            return

        try:
            from stt import WhisperSTT
        except Exception as e:
            self.error.emit(f"Whisper could not be loaded: {e}")
            return

        try:
            stt_engine = WhisperSTT(self.whisper_model, self.language)
        except Exception as e:
            self.error.emit(str(e))
            return

        device = self._resolve_device(sd)

        # Ortam gürültüsüne göre eşik kalibrasyonu (~400ms)
        try:
            calib = sd.rec(int(0.4 * self.samplerate), samplerate=self.samplerate,
                            channels=1, dtype="float32", device=device)
            sd.wait()
            ambient = float(np.abs(calib).mean())
            threshold = max(ambient * 3.0, 0.01)
        except Exception:
            threshold = 0.02

        audio = self._record_until_silence(sd, threshold, device)
        if self._stop_flag:
            return
        if audio.size == 0:
            self.finished.emit("")
            return

        try:
            text = stt_engine.transcribe(audio)
        except Exception as e:
            self.error.emit(str(e))
            return

        self.finished.emit(text or "")
