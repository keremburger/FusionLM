"""
settings_dialog.py — FusionLM ayarlar penceresi.

chat_window.py bu modülden şunu bekler:
    dlg = SettingsDialog(self.cfg, lang, self)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        new_cfg = dlg.get_config()

README'deki sekme tablosuna göre: Generation / Appearance / Prompts / Voice / Persona / User
"""
from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
    QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox, QCheckBox, QTextEdit,
    QDialogButtonBox, QSlider, QLabel, QPushButton, QFileDialog
)
from PyQt6.QtCore import Qt

from themes import THEMES
from translations import LANGS, tr

# Ayar dialogunda seçilebilecek TTS dilleri (voice_engine.EDGE_TTS_VOICE_MAP ile uyumlu)
TTS_LANGUAGES = [
    "English", "Turkish", "Spanish", "French", "German", "Italian", "Portuguese",
    "Russian", "Chinese", "Japanese", "Korean", "Arabic", "Hindi", "Dutch",
    "Swedish", "Norwegian", "Polish", "Ukrainian", "Vietnamese", "Greek",
]

MODES = ["Lite", "Normal", "Pro", "Coding", "Deep Research", "Code Hub"]


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, lang: str, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)  # kopya üzerinde çalış, iptal edilirse orijinali bozma
        self.lang = lang
        self.setWindowTitle(tr("Settings", lang))
        self.resize(560, 560)

        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)

        self.tabs.addTab(self._build_generation_tab(), "⚙ " + tr("Generation", lang))
        self.tabs.addTab(self._build_appearance_tab(), "🎨 " + tr("Appearance", lang))
        self.tabs.addTab(self._build_prompts_tab(), "📝 " + tr("Prompts", lang))
        self.tabs.addTab(self._build_voice_tab(), "🎤 Voice")
        self.tabs.addTab(self._build_persona_tab(), "🧑 " + tr("Persona", lang))
        self.tabs.addTab(self._build_user_tab(), "👤 " + tr("User", lang))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    # GENERATION
    # ------------------------------------------------------------------
    def _build_generation_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.05)
        self.temperature.setValue(float(self.cfg.get("temperature", 0.7)))
        form.addRow("Temperature", self.temperature)

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(1, 32000)
        self.max_tokens.setValue(int(self.cfg.get("max_tokens", 800)))
        form.addRow("Max tokens", self.max_tokens)

        self.top_p = QDoubleSpinBox()
        self.top_p.setRange(0.0, 1.0)
        self.top_p.setSingleStep(0.05)
        self.top_p.setValue(float(self.cfg.get("top_p", 0.9)))
        form.addRow("Top-p", self.top_p)

        self.top_k = QSpinBox()
        self.top_k.setRange(0, 500)
        self.top_k.setValue(int(self.cfg.get("top_k", 40)))
        form.addRow("Top-k", self.top_k)

        self.repeat_penalty = QDoubleSpinBox()
        self.repeat_penalty.setRange(0.0, 3.0)
        self.repeat_penalty.setSingleStep(0.05)
        self.repeat_penalty.setValue(float(self.cfg.get("repeat_penalty", 1.1)))
        form.addRow("Repeat penalty", self.repeat_penalty)

        self.context_length = QSpinBox()
        self.context_length.setRange(256, 131072)
        self.context_length.setSingleStep(256)
        self.context_length.setValue(int(self.cfg.get("context_length", 4096)))
        form.addRow("Context length", self.context_length)

        self.seed = QSpinBox()
        self.seed.setRange(-1, 2_147_483_647)
        self.seed.setValue(int(self.cfg.get("seed", -1)))
        form.addRow("Seed (-1 = random)", self.seed)

        self.stop = QLineEdit(self.cfg.get("stop", ""))
        self.stop.setPlaceholderText("comma,separated,stop,sequences")
        form.addRow("Stop sequences", self.stop)

        return w

    # ------------------------------------------------------------------
    # APPEARANCE
    # ------------------------------------------------------------------
    def _build_appearance_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setCurrentText(self.cfg.get("theme", "Dark"))
        form.addRow(tr("Appearance", self.lang) + " – Theme", self.theme_combo)

        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.addItems(LANGS)
        if self.cfg.get("ui_language", "English") in LANGS:
            self.ui_lang_combo.setCurrentText(self.cfg.get("ui_language", "English"))
        form.addRow("UI language", self.ui_lang_combo)

        self.chat_lang_combo = QComboBox()
        self.chat_lang_combo.addItems(TTS_LANGUAGES)
        current_lang = self.cfg.get("language", "English")
        if current_lang not in TTS_LANGUAGES:
            self.chat_lang_combo.addItem(current_lang)
        self.chat_lang_combo.setCurrentText(current_lang)
        form.addRow("AI reply language", self.chat_lang_combo)

        self.sync_ui_lang = QCheckBox("Keep UI language in sync with AI language")
        self.sync_ui_lang.setChecked(bool(self.cfg.get("sync_ui_lang", True)))
        form.addRow(self.sync_ui_lang)

        self.font_family = QLineEdit(self.cfg.get("font_family", "Segoe UI"))
        form.addRow("Font family", self.font_family)

        self.font_size = QSpinBox()
        self.font_size.setRange(6, 32)
        self.font_size.setValue(int(self.cfg.get("font_size", 10)))
        form.addRow("Font size", self.font_size)

        self.bubble_radius = QSpinBox()
        self.bubble_radius.setRange(0, 40)
        self.bubble_radius.setValue(int(self.cfg.get("bubble_radius", 14)))
        form.addRow("Bubble radius", self.bubble_radius)

        self.shadow_blur = QSpinBox()
        self.shadow_blur.setRange(0, 60)
        self.shadow_blur.setValue(int(self.cfg.get("shadow_blur", 8)))
        form.addRow("Shadow blur", self.shadow_blur)

        self.shadow_offset = QSpinBox()
        self.shadow_offset.setRange(0, 20)
        self.shadow_offset.setValue(int(self.cfg.get("shadow_offset", 2)))
        form.addRow("Shadow offset", self.shadow_offset)

        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(int(self.cfg.get("opacity", 100)))
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        form.addRow("Window opacity", opacity_row)

        self.custom_css = QTextEdit(self.cfg.get("custom_css", ""))
        self.custom_css.setPlaceholderText("QPushButton { border-radius: 20px; }")
        self.custom_css.setFixedHeight(90)
        form.addRow("Custom CSS", self.custom_css)

        return w

    # ------------------------------------------------------------------
    # PROMPTS
    # ------------------------------------------------------------------
    def _build_prompts_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODES)
        layout.addWidget(self.mode_combo)

        self.prompt_edit = QTextEdit()
        layout.addWidget(self.prompt_edit)

        self._prompts = dict(self.cfg.get("custom_prompts", {}))

        def _load_prompt(mode):
            self.prompt_edit.setPlainText(self._prompts.get(mode, ""))

        def _store_current():
            mode = self.mode_combo.currentText()
            self._prompts[mode] = self.prompt_edit.toPlainText()

        self.mode_combo.currentTextChanged.connect(
            lambda new_mode: (_store_current(), _load_prompt(new_mode))
        )
        self._store_current_prompt = _store_current
        _load_prompt(self.mode_combo.currentText())

        return w

    # ------------------------------------------------------------------
    # VOICE
    # ------------------------------------------------------------------
    def _build_voice_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        self.tts_engine = QComboBox()
        self.tts_engine.addItems(["edgetts", "kokoro", "elevenlabs"])
        self.tts_engine.setCurrentText(self.cfg.get("tts_engine", "edgetts"))
        form.addRow("TTS engine", self.tts_engine)

        self.tts_auto_voice = QCheckBox("Match voice to chat language automatically")
        self.tts_auto_voice.setChecked(bool(self.cfg.get("tts_auto_voice", True)))
        form.addRow(self.tts_auto_voice)

        self.tts_voice = QLineEdit(self.cfg.get("tts_voice", "en-US-GuyNeural"))
        self.tts_voice.setPlaceholderText("e.g. tr-TR-AhmetNeural (manual override)")
        form.addRow("Manual voice ID", self.tts_voice)

        self.tts_speed = QDoubleSpinBox()
        self.tts_speed.setRange(0.5, 2.0)
        self.tts_speed.setSingleStep(0.1)
        self.tts_speed.setValue(float(self.cfg.get("tts_speed", 1.0)))
        form.addRow("TTS speed", self.tts_speed)

        self.elevenlabs_key = QLineEdit(self.cfg.get("elevenlabs_api_key", ""))
        self.elevenlabs_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("ElevenLabs API key", self.elevenlabs_key)

        self.whisper_model = QComboBox()
        self.whisper_model.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.whisper_model.setCurrentText(self.cfg.get("whisper_model", "base"))
        form.addRow("Whisper model size", self.whisper_model)

        mic_row = QHBoxLayout()
        self.mic_device = QComboBox()
        self._mic_device_map = {}  # combobox index -> sounddevice index (None = system default)
        self._populate_mic_devices()
        mic_refresh_btn = QPushButton("🔄")
        mic_refresh_btn.setFixedWidth(30)
        mic_refresh_btn.setToolTip("Refresh microphone list")
        mic_refresh_btn.clicked.connect(self._populate_mic_devices)
        mic_row.addWidget(self.mic_device)
        mic_row.addWidget(mic_refresh_btn)
        form.addRow("Microphone", mic_row)

        self.stt_language = QLineEdit(self.cfg.get("stt_language", "auto"))
        self.stt_language.setPlaceholderText("auto, en, tr, ...")
        form.addRow("STT language", self.stt_language)

        self.wake_enabled = QCheckBox('Enable "Hey Fusion" wake word')
        self.wake_enabled.setChecked(bool(self.cfg.get("wake_enabled", False)))
        form.addRow(self.wake_enabled)

        self.wake_word = QLineEdit(self.cfg.get("wake_word", "Hey Fusion"))
        form.addRow("Wake word", self.wake_word)

        self.actions_enabled = QCheckBox("Enable actions")
        self.actions_enabled.setChecked(bool(self.cfg.get("actions_enabled", True)))
        form.addRow(self.actions_enabled)

        self.web_search = QCheckBox("Enable web search")
        self.web_search.setChecked(bool(self.cfg.get("web_search", False)))
        form.addRow(self.web_search)

        return w

    def _populate_mic_devices(self):
        """Sistemdeki giriş (mikrofon) cihazlarını sounddevice ile listeler.
        Kayıtlı cfg['mic_device'] (isim) varsa onu seçili getirir; yoksa
        'System Default' seçili kalır."""
        self.mic_device.clear()
        self._mic_device_map = {0: None}
        self.mic_device.addItem("System Default")

        saved_name = self.cfg.get("mic_device", "")
        select_index = 0
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    combo_index = self.mic_device.count()
                    self.mic_device.addItem(dev["name"])
                    self._mic_device_map[combo_index] = idx
                    if saved_name and dev["name"] == saved_name:
                        select_index = combo_index
        except Exception as e:
            self.mic_device.addItem(f"(sounddevice not available: {e})")

        self.mic_device.setCurrentIndex(select_index)

    # ------------------------------------------------------------------
    # PERSONA
    # ------------------------------------------------------------------
    def _build_persona_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel(
            "Custom persona text appended to every system prompt (e.g. tone, "
            "role, restrictions)."
        ))
        self.custom_persona = QTextEdit(self.cfg.get("custom_persona", ""))
        layout.addWidget(self.custom_persona)
        return w

    # ------------------------------------------------------------------
    # USER
    # ------------------------------------------------------------------
    def _build_user_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel(
            "Facts about you the model should keep in mind across conversations "
            "(name, job, preferences, ongoing projects, etc.)."
        ))
        self.user_profile = QTextEdit(self.cfg.get("user_profile", ""))
        layout.addWidget(self.user_profile)
        return w

    # ------------------------------------------------------------------
    # SONUÇ
    # ------------------------------------------------------------------
    def get_config(self) -> dict:
        """Dialogdaki tüm alanları okuyup güncellenmiş cfg dict'i döner."""
        self._store_current_prompt()

        cfg = dict(self.cfg)
        cfg.update({
            "temperature": self.temperature.value(),
            "max_tokens": self.max_tokens.value(),
            "top_p": self.top_p.value(),
            "top_k": self.top_k.value(),
            "repeat_penalty": self.repeat_penalty.value(),
            "context_length": self.context_length.value(),
            "seed": self.seed.value(),
            "stop": self.stop.text(),

            "theme": self.theme_combo.currentText(),
            "ui_language": self.ui_lang_combo.currentText(),
            "language": self.chat_lang_combo.currentText(),
            "sync_ui_lang": self.sync_ui_lang.isChecked(),
            "font_family": self.font_family.text(),
            "font_size": self.font_size.value(),
            "bubble_radius": self.bubble_radius.value(),
            "shadow_blur": self.shadow_blur.value(),
            "shadow_offset": self.shadow_offset.value(),
            "opacity": self.opacity_slider.value(),
            "custom_css": self.custom_css.toPlainText(),

            "custom_prompts": self._prompts,

            "tts_engine": self.tts_engine.currentText(),
            "tts_auto_voice": self.tts_auto_voice.isChecked(),
            "tts_voice": self.tts_voice.text(),
            "tts_speed": self.tts_speed.value(),
            "elevenlabs_api_key": self.elevenlabs_key.text(),
            "whisper_model": self.whisper_model.currentText(),
            "mic_device": self.mic_device.currentText() if self.mic_device.currentIndex() > 0 else "",
            "stt_language": self.stt_language.text(),
            "wake_enabled": self.wake_enabled.isChecked(),
            "wake_word": self.wake_word.text(),
            "actions_enabled": self.actions_enabled.isChecked(),
            "web_search": self.web_search.isChecked(),

            "custom_persona": self.custom_persona.toPlainText(),
            "user_profile": self.user_profile.toPlainText(),
        })
        return cfg
