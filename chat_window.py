import os, sys, base64, tempfile, threading, re, subprocess, sqlite3
from io import BytesIO
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QTimer, QIODevice, QBuffer, QByteArray
from PyQt6.QtGui import QAction, QImage, QPixmap, QShortcut, QKeySequence
from config import load_cfg, save_cfg
from database import (load_conversations, load_messages, save_message,
                      new_conversation, delete_conversation, DB_PATH)
from themes import THEMES
from translations import LANGS, LANG_CODES, tr
from workers import ModelWorker, WebSearchThread
from bubble import Bubble, TypingBubble
from camera_dialog import CameraDialog
from settings_dialog import SettingsDialog
from actions import ACTIONS_SYSTEM_PROMPT, is_action_json, run_action
from voice_engine import WhisperMicWorker, SmartTTS
from voice_overlay import VoiceOrb
import ollama
import psutil
import requests
from bs4 import BeautifulSoup
from markdown import markdown
import warnings
warnings.filterwarnings("ignore")

class Chatter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FusionLM – Local Multi-Model AI")
        self.resize(1150, 780)
        self.db_path = DB_PATH
        self.cfg = load_cfg()
        self.cid = None
        self.model = ""
        self.mode = "Normal"
        self.worker = None
        self.reply = ""
        self.mic_worker = None
        self.recording = False
        self.tts_speaking = False
        self.compare_reply = ""
        self.compare_worker = None
        self.attachments = []
        self.smart_tts = None
        self.pending_action = False
        self.voice_chat_active = False
        self.setup_ui()
        self.stop_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.stop_shortcut.activated.connect(self.interrupt_voice)
        self.retranslate_ui()
        self.refresh_convs()
        convs = load_conversations()
        if convs:
            self.load_conv(convs[0][0])
        else:
            self.new_chat()
        self.input.setFocus()
        if self.cfg.get("tts_enabled", False):
            self.init_tts()
        self.setWindowOpacity(self.cfg.get("opacity", 100) / 100.0)
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.update_stats)
        self.monitor_timer.start(2000)
        self.update_stats()

    # ---------- TTS (EdgeTTS / Kokoro / ElevenLabs — voice_engine.py) ----------
    def init_tts(self):
        try:
            self.smart_tts = SmartTTS(self.cfg)
            self.tts_speaking = False
        except Exception as e:
            self.smart_tts = None
            print(f"[TTS] init failed: {e}")

    def _strip_for_speech(self, text):
        # Markdown işaretlerini ve kod bloklarını konuşmadan önce temizle
        text = re.sub(r"```.*?```", " kod bloğu ", text, flags=re.S)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = re.sub(r"[*_#>~]", "", text)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
        return text.strip()

    def speak(self, text, on_done=None):
        if not self.cfg.get("tts_enabled", False):
            if on_done:
                on_done()
            return
        clean = self._strip_for_speech(text)
        if not clean:
            if on_done:
                on_done()
            return
        if not self.smart_tts:
            self.init_tts()
        if not self.smart_tts:
            if on_done:
                on_done()
            return

        def _on_start():
            self.tts_speaking = True
            try:
                self.tts_btn.setStyleSheet("background-color:#a6e22e; color:#121212;")
                self.voice_orb.set_state("speaking")
            except RuntimeError:
                pass

        def _on_done():
            self.tts_speaking = False
            try:
                self.tts_btn.setStyleSheet("")
                self.voice_orb.set_state("idle")
            except RuntimeError:
                pass
            if on_done:
                on_done()

        self.smart_tts.speak(clean, on_start=_on_start, on_done=_on_done)

    def stop_speaking(self):
        self.tts_speaking = False
        if self.smart_tts:
            try:
                self.smart_tts.stop()
            except Exception:
                pass
        try:
            self.tts_btn.setStyleSheet("")
            self.voice_orb.set_state("idle")
        except RuntimeError:
            pass

    # ---------- MİKROFON (Whisper — voice_engine.py) ----------
    def interrupt_voice(self):
        """Esc: konuşan TTS'i ve/veya dinleyen mikrofonu anında durdurur."""
        self.stop_speaking()
        self.stop_mic()

    def stop_mic(self):
        if self.recording and self.mic_worker:
            self.mic_worker.stop()
            self.mic_worker.wait(1000)
            self.recording = False
            self.mic_btn.setStyleSheet("")
            self.voice_orb.set_state("idle")

    def toggle_mic(self):
        if self.recording:
            self.stop_mic()
            return
        if self.tts_speaking:
            self.stop_speaking()  # konuşma sırasında mikrofona basınca anında kes
        self._start_listening(on_done=self.send)

    def _start_listening(self, on_done):
        """Bir kez dinler, metne çevirir, on_done(text) çağırır."""
        self.recording = True
        self.mic_btn.setStyleSheet("background-color:#ff5555; color:white;")
        wake = self.cfg.get("wake_word", "") if self.cfg.get("wake_enabled", False) else None
        self.mic_worker = WhisperMicWorker(
            whisper_model=self.cfg.get("whisper_model", "base"),
            language=self.cfg.get("stt_language", "auto"),
            wake_word=wake,
            mic_device=self.cfg.get("mic_device", ""),
        )
        self.mic_worker.finished.connect(lambda text: self._on_mic_done(text, on_done))
        self.mic_worker.error.connect(self.on_mic_error)
        self.mic_worker.level.connect(self.voice_orb.set_level)
        self.voice_orb.set_state("listening")
        self.mic_worker.start()

    def _on_mic_done(self, text, on_done):
        self.recording = False
        self.mic_btn.setStyleSheet("")
        self.voice_orb.set_state("idle")
        on_done(text)

    def on_mic_error(self, err):
        self.recording = False
        self.mic_btn.setStyleSheet("")
        self.voice_orb.set_state("idle")
        if self.voice_chat_active:
            # sesli sohbet modunda sessiz hatalarda tekrar dinlemeye devam et
            QTimer.singleShot(300, self._voice_chat_listen)
            return
        QMessageBox.critical(self, "Mic Error", err)

    # ---------- SESLİ SOHBET MODU ----------
    def toggle_voice_chat(self, checked):
        self.voice_chat_active = checked
        self.voice_chat_btn.setStyleSheet(
            "background-color:#ff5555; color:white;" if checked else ""
        )
        if checked:
            if not self.cfg.get("tts_enabled", False):
                self.cfg["tts_enabled"] = True
                save_cfg(self.cfg)
                self.tts_btn.setChecked(True)
                if not self.smart_tts:
                    self.init_tts()
            self._voice_chat_listen()
        else:
            self.stop_mic()

    def _voice_chat_listen(self):
        if not self.voice_chat_active:
            return
        if self.recording or (self.worker and self.worker.isRunning()):
            QTimer.singleShot(300, self._voice_chat_listen)
            return
        self._start_listening(on_done=self._voice_chat_on_text)

    def _voice_chat_on_text(self, text):
        if not text.strip():
            QTimer.singleShot(300, self._voice_chat_listen)
            return
        self.send(text)

    # ---------- ARAYÜZ ----------
    def setup_ui(self):
        c = QWidget()
        self.setCentralWidget(c)
        ml = QHBoxLayout(c)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        left = QWidget()
        left.setFixedWidth(260)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 12, 12)
        self.conv_lbl = QLabel("Fusions")
        ll.addWidget(self.conv_lbl)
        self.conv_search = QLineEdit()
        self.conv_search.setPlaceholderText("🔍 Search fusions...")
        self.conv_search.textChanged.connect(self.filter_convs)
        ll.addWidget(self.conv_search)
        self.conv_lst = QListWidget()
        self.conv_lst.itemClicked.connect(self.load_sel_conv)
        self.conv_lst.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conv_lst.customContextMenuRequested.connect(self.show_ctx_menu)
        ll.addWidget(self.conv_lst)
        btn_row = QHBoxLayout()
        self.new_btn = QPushButton("+ New Fusion")
        self.new_btn.clicked.connect(self.new_chat)
        btn_row.addWidget(self.new_btn)
        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self.export_conv)
        btn_row.addWidget(self.export_btn)
        self.mini_btn = QPushButton("⊞")
        self.mini_btn.clicked.connect(self.toggle_mini)
        btn_row.addWidget(self.mini_btn)
        ll.addLayout(btn_row)
        self.left_panel = left

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(12, 8, 12, 8)
        self.model_lbl = QLabel("Model:")
        top.addWidget(self.model_lbl)
        self.model_cmb = QComboBox()
        self.model_cmb.setEditable(True)
        self.model_cmb.setMinimumWidth(150)
        self.model_cmb.lineEdit().setPlaceholderText("model name")
        self.model_cmb.currentTextChanged.connect(self.set_model)
        top.addWidget(self.model_cmb)
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.clicked.connect(self.refresh_models)
        top.addWidget(self.refresh_btn)
        self.mode_lbl = QLabel("Mode:")
        top.addWidget(self.mode_lbl)
        self.mode_cmb = QComboBox()
        self.mode_cmb.addItems(["Lite", "Normal", "Pro", "Coding", "Deep Research"])
        self.mode_cmb.currentTextChanged.connect(self.set_mode)
        top.addWidget(self.mode_cmb)
        self.lang_lbl = QLabel("Lang:")
        top.addWidget(self.lang_lbl)
        self.lang_cmb = QComboBox()
        self.lang_cmb.addItems(LANGS)
        cur = self.cfg.get("language", "English")
        if cur in LANGS:
            self.lang_cmb.setCurrentText(cur)
        self.lang_cmb.currentTextChanged.connect(self.set_lang)
        top.addWidget(self.lang_cmb)
        self.tts_btn = QPushButton("🔊")
        self.tts_btn.setCheckable(True)
        self.tts_btn.setChecked(self.cfg.get("tts_enabled", False))
        self.tts_btn.clicked.connect(self.toggle_tts)
        self.tts_btn.setToolTip("Enable/disable text-to-speech")
        top.addWidget(self.tts_btn)
        self.tts_stop_btn = QPushButton("⏹")
        self.tts_stop_btn.setFixedWidth(32)
        self.tts_stop_btn.setToolTip("Stop speaking")
        self.tts_stop_btn.clicked.connect(self.stop_speaking)
        top.addWidget(self.tts_stop_btn)
        self.web_btn = QPushButton("🌐")
        self.web_btn.setCheckable(True)
        self.web_btn.setChecked(self.cfg.get("web_search", False))
        self.web_btn.clicked.connect(self.toggle_web)
        top.addWidget(self.web_btn)
        self.compare_btn = QPushButton("⇆")
        self.compare_btn.setCheckable(True)
        self.compare_btn.setChecked(self.cfg.get("compare_enabled", False))
        self.compare_btn.clicked.connect(self.toggle_compare)
        top.addWidget(self.compare_btn)
        top.addStretch()
        self.voice_chat_btn = QPushButton("🗣️ Voice Chat")
        self.voice_chat_btn.setCheckable(True)
        self.voice_chat_btn.setToolTip("Continuous voice conversation: listen → reply → speak → listen again")
        self.voice_chat_btn.clicked.connect(self.toggle_voice_chat)
        top.addWidget(self.voice_chat_btn)
        self.sett_btn = QPushButton("⚙")
        self.sett_btn.clicked.connect(self.open_settings)
        top.addWidget(self.sett_btn)
        rl.addLayout(top)

        self.compare_row = QHBoxLayout()
        self.compare_lbl = QLabel("2nd Model:")
        self.compare_row.addWidget(self.compare_lbl)
        self.compare_cmb = QComboBox()
        self.compare_cmb.setEditable(True)
        self.compare_cmb.setMinimumWidth(150)
        self.compare_row.addWidget(self.compare_cmb)
        self.compare_row.addStretch()
        self.compare_widget = QWidget()
        self.compare_widget.setLayout(self.compare_row)
        self.compare_widget.setVisible(self.cfg.get("compare_enabled", False))
        rl.addWidget(self.compare_widget)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_lay = QVBoxLayout(self.scroll_content)
        self.scroll_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_lay.setSpacing(12)
        self.scroll_content.setLayout(self.scroll_lay)
        self.scroll.setWidget(self.scroll_content)
        rl.addWidget(self.scroll)

        self.attachment_bar = QWidget()
        self.attachment_layout = QHBoxLayout(self.attachment_bar)
        self.attachment_layout.setContentsMargins(8, 4, 8, 4)
        self.attachment_layout.setSpacing(8)
        self.attachment_bar.setVisible(False)
        rl.addWidget(self.attachment_bar)

        inp_lay = QHBoxLayout()
        inp_lay.setContentsMargins(12, 8, 12, 12)
        self.att_btn = QPushButton("📎")
        self.att_btn.setFixedWidth(40)
        self.att_btn.clicked.connect(self.attach)
        inp_lay.addWidget(self.att_btn)
        self.screenshot_btn = QPushButton("📷")
        self.screenshot_btn.setFixedWidth(40)
        self.screenshot_btn.clicked.connect(self.take_screenshot)
        inp_lay.addWidget(self.screenshot_btn)
        self.camera_btn = QPushButton("📹")
        self.camera_btn.setFixedWidth(40)
        self.camera_btn.clicked.connect(self.take_camera)
        inp_lay.addWidget(self.camera_btn)
        self.voice_orb = VoiceOrb(self.cfg)
        self.voice_orb.setToolTip("Voice activity")
        inp_lay.addWidget(self.voice_orb)
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedWidth(40)
        self.mic_btn.clicked.connect(self.toggle_mic)
        inp_lay.addWidget(self.mic_btn)
        self.input = QTextEdit()
        self.input.setPlaceholderText("Type your message...")
        self.input.setMaximumHeight(80)
        self.input.installEventFilter(self)
        inp_lay.addWidget(self.input)
        self.send_btn = QPushButton("Fuse")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.clicked.connect(self.send)
        inp_lay.addWidget(self.send_btn)
        rl.addLayout(inp_lay)

        sys_layout = QHBoxLayout()
        self.cpu_label = QLabel("CPU: --%")
        self.ram_label = QLabel("RAM: --%")
        self.gpu_label = QLabel("GPU: --")
        self.stats_label = QLabel("Fusions: 0 | Tokens: 0")
        sys_layout.addWidget(self.cpu_label)
        sys_layout.addWidget(self.ram_label)
        sys_layout.addWidget(self.gpu_label)
        sys_layout.addStretch()
        sys_layout.addWidget(self.stats_label)
        rl.addLayout(sys_layout)

        spl = QSplitter(Qt.Orientation.Horizontal)
        spl.addWidget(left)
        spl.addWidget(right)
        spl.setSizes([260, 890])
        ml.addWidget(spl)

        self.refresh_models()
        self.apply_theme()

    # ---------- TEMEL METOTLAR ----------
    def toggle_mini(self): self.left_panel.setVisible(not self.left_panel.isVisible())
    def filter_convs(self, text):
        text = text.strip().lower()
        for i in range(self.conv_lst.count()):
            item = self.conv_lst.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())
    def toggle_web(self, checked): self.cfg["web_search"] = checked; save_cfg(self.cfg)
    def toggle_compare(self, checked):
        self.cfg["compare_enabled"] = checked; self.compare_widget.setVisible(checked)
        if checked: self.refresh_compare_models()
        save_cfg(self.cfg)
    def toggle_tts(self, checked):
        self.cfg["tts_enabled"] = checked; save_cfg(self.cfg)
        if checked and not self.smart_tts: self.init_tts()
    def set_model(self, m): self.model = m
    def set_mode(self, m): self.mode = m
    def set_lang(self, l):
        self.cfg["language"] = l
        if self.cfg.get("sync_ui_lang", True): self.cfg["ui_language"] = l; self.retranslate_ui()
        save_cfg(self.cfg)

    def new_chat(self):
        if not self.model: QMessageBox.warning(self, "No model", "Select or type a model name."); return
        self.cid = new_conversation(self.model); self.clear_chat(); self.refresh_convs(); self.input.clear()
    def load_sel_conv(self, item): self.load_conv(item.data(Qt.ItemDataRole.UserRole))
    def load_conv(self, cid):
        self.cid = cid; self.clear_chat()
        for role, content, _ in load_messages(cid): self.add_bubble(content, role == "user")
        self.refresh_convs()
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))
    def clear_chat(self):
        while self.scroll_lay.count():
            w = self.scroll_lay.takeAt(0).widget()
            if w: w.deleteLater()
    def add_bubble(self, text, is_user, model_name=""):
        bub = Bubble(text, is_user, self.cfg, model_name=model_name)
        self.scroll_lay.addWidget(bub)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
    def refresh_convs(self):
        self.conv_lst.clear()
        for c in load_conversations():
            it = QListWidgetItem(f"{c[1]} ({c[2]})"); it.setData(Qt.ItemDataRole.UserRole, c[0]); self.conv_lst.addItem(it)
        if hasattr(self, "conv_search"):
            self.filter_convs(self.conv_search.text())
    def delete_conv(self, cid):
        if self.cid == cid: self.cid = None; self.clear_chat()
        delete_conversation(cid); self.refresh_convs()
        convs = load_conversations()
        if convs: self.load_conv(convs[0][0])
        else: self.new_chat()
    def export_conv(self, cid=None):
        if cid is None: cid = self.cid
        if not cid: return
        msgs = load_messages(cid)
        fp, _ = QFileDialog.getSaveFileName(self, "Export Fusion", "", "Text (*.txt)")
        if not fp: return
        with open(fp, "w", encoding="utf-8") as f:
            for role, content, _ in msgs: f.write(f"{role}: {content}\n\n")
        QMessageBox.information(self, "Export", "Fusion exported.")
    def show_ctx_menu(self, pos):
        item = self.conv_lst.itemAt(pos)
        if not item: return
        cid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self); lang = self.cfg.get("ui_language", "English")
        del_act = QAction(tr("Delete", lang), self); del_act.triggered.connect(lambda: self.delete_conv(cid)); menu.addAction(del_act)
        exp_act = QAction(tr("Export", lang), self); exp_act.triggered.connect(lambda: self.export_conv(cid)); menu.addAction(exp_act)
        menu.exec(self.conv_lst.mapToGlobal(pos))

    # ---------- TEMA & DİL ----------
    def retranslate_ui(self):
        lang = self.cfg.get("ui_language", "English")
        self.conv_lbl.setText(tr("Conversations", lang)); self.new_btn.setText(tr("New Chat", lang))
        self.export_btn.setText(tr("Export", lang)); self.model_lbl.setText(tr("Model:", lang))
        self.mode_lbl.setText(tr("Mode:", lang)); self.lang_lbl.setText(tr("Lang:", lang))
        self.send_btn.setText(tr("Send", lang)); self.input.setPlaceholderText(tr("Type your message...", lang))
        self.sett_btn.setText("⚙ " + tr("Settings", lang)); self.refresh_btn.setToolTip(tr("Refresh", lang))

    def apply_theme(self):
        theme = THEMES.get(self.cfg.get("theme", "Dark"), THEMES["Dark"])
        font = self.cfg.get("font_family", "Segoe UI")
        css = f"""
            QMainWindow{{background-color:{theme["main_bg"]};}}
            QWidget{{color:{theme["text"]};font-family:'{font}';}}
            QTextEdit,QListWidget,QComboBox,QSpinBox,QSlider,QLineEdit{{
                background-color:{theme["widget_bg"]};border:1px solid {theme["border"]};border-radius:8px;padding:6px;
            }}
            QPushButton{{
                background-color:{theme["widget_bg"]};border:1px solid {theme["border"]};border-radius:8px;padding:6px 14px;color:{theme["text"]};
            }}
            QPushButton:hover{{background-color:{theme["button_hover"]};color:{theme["main_bg"]};}}
            QPushButton:checked{{background-color:{theme["accent"]};color:{theme["main_bg"]};}}
            QPushButton#sendBtn{{background-color:{theme["send_btn_bg"]};color:{theme["send_btn_text"]};font-weight:bold;}}
            QScrollArea{{border:none;background-color:{theme["scroll_bg"]};}}
            QLabel{{color:{theme["text"]};}}
            #scrollContent{{background-color:{theme["scroll_bg"]};}}
        """
        custom_css = self.cfg.get("custom_css", "")
        if custom_css: css += custom_css
        QApplication.instance().setStyleSheet(css)
        self.refresh_chat_bubbles()

    def refresh_chat_bubbles(self):
        for i in range(self.scroll_lay.count()):
            w = self.scroll_lay.itemAt(i).widget()
            if isinstance(w, Bubble): w.cfg = self.cfg; w.apply_style(); w.update_text()

    def refresh_models(self):
        try:
            models = ollama.list()
            if isinstance(models, dict) and 'models' in models: names = [m['name'] for m in models['models']]
            else: raise Exception("invalid")
        except:
            try:
                out = subprocess.check_output("ollama list", shell=True, text=True)
                lines = out.strip().split('\n')[1:]; names = [line.split()[0] for line in lines if line.strip()]
            except: names = []
        self.model_cmb.clear()
        if names: self.model_cmb.addItems(names); self.model = self.model_cmb.currentText()
        else: self.model_cmb.addItem(""); QMessageBox.warning(self, "Warning", "Could not fetch models.")

    def refresh_compare_models(self):
        self.compare_cmb.clear()
        for i in range(self.model_cmb.count()): self.compare_cmb.addItem(self.model_cmb.itemText(i))
        if self.compare_cmb.count() > 0: self.compare_cmb.setCurrentIndex(0)

    def eventFilter(self, obj, event):
        if obj == self.input and event.type() == event.Type.KeyPress and \
           event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.send(); return True
        return super().eventFilter(obj, event)

    # ---------- MESAJ GÖNDERME ----------
    def set_busy(self, busy):
        self.send_btn.setEnabled(not busy)
        self.send_btn.setText("..." if busy else tr("Send", self.cfg.get("ui_language", "English")))

    def send(self, txt=None):
        if self.worker and self.worker.isRunning():
            return  # önceki yanıt hala üretiliyor, çakışmayı önle
        if not self.model: QMessageBox.warning(self, "No model", "Select a model."); return
        if not txt: txt = self.input.toPlainText().strip()
        if not txt and not self.attachments: return
        if not self.cid: self.new_chat()

        url_pattern = re.compile(r'^https?://\S+$')
        if url_pattern.match(txt) and not self.attachments:
            self.input.clear()
            self.handle_url(txt); return

        image_list = []
        file_texts = []
        for att in self.attachments:
            if att["type"] == "image" and att["base64"]:
                image_list.append(att["base64"])
            elif att["type"] == "file":
                fp = att.get("file_path", "")
                try:
                    if os.path.getsize(fp) < 200_000:  # ~200KB metin sınırı
                        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                            file_texts.append(f"--- {os.path.basename(fp)} ---\n{f.read()}")
                    else:
                        QMessageBox.warning(self, "File too large", f"{os.path.basename(fp)} is too large to include and was skipped.")
                except Exception:
                    QMessageBox.warning(self, "Unsupported file", f"{os.path.basename(fp)} could not be read as text and was skipped.")

        final_user_text = txt
        if file_texts:
            final_user_text += "\n\n" + "\n\n".join(file_texts)

        if image_list and self.is_multimodal(self.model):
            self.add_bubble(final_user_text, True)
            save_message(self.cid, "user", final_user_text)
            self.input.clear(); self.clear_attachments()
            self.run_model([{"role":"user", "content":final_user_text, "images":image_list}])
        else:
            if image_list:
                QMessageBox.warning(self, "Multimodal required", "Current model does not support images. Images omitted.")
            self._send_message(final_user_text); self.clear_attachments()

    def _send_message(self, txt, web_context=None):
        if not self.cid: self.new_chat()
        lang = self.cfg.get("language", "English")
        prefix = lang_instr(lang) if lang != "English" else ""
        self.add_bubble(txt, True); save_message(self.cid, "user", txt); self.input.clear()

        mode_prompt = self.cfg.get("custom_prompts", {}).get(self.mode, "")
        persona_prompt = self.cfg.get("custom_persona", "")
        user_profile = self.cfg.get("user_profile", "")
        sys_prompt = mode_prompt
        if lang != "English":
            sys_prompt = lang_instr(lang) + "\n" + sys_prompt
        if self.cfg.get("actions_enabled", True):
            sys_prompt += "\n\n" + ACTIONS_SYSTEM_PROMPT
            if self.cfg.get("web_search", False):
                sys_prompt += (
                    "\n\nThe user has web search turned on. If the question needs current "
                    "or real-time information (today's news, live scores, weather, prices, "
                    "recent events, anything that could be outdated in your training data), "
                    "you MUST respond with the web_search action (mode=\"news\" for news-type "
                    "requests) or get_weather action, using a short well-formed search query "
                    "in the user's own language — never reply that you have no internet access "
                    "or cannot find results without first trying the action."
                )
        if persona_prompt: sys_prompt += "\n" + persona_prompt
        if user_profile: sys_prompt += "\nFacts about the user: " + user_profile
        if web_context: sys_prompt += "\n\n### WEB SEARCH RESULTS (use these to answer accurately):\n" + web_context

        history = load_messages(self.cid); msgs = []
        for role, content, _ in history:
            if role == "user" and lang != "English": content = lang_instr(lang) + " " + content
            msgs.append({"role": role, "content": content})
        msgs.insert(0, {"role": "system", "content": sys_prompt})

        stats = self.cfg.get("stats", {"messages":0,"tokens":0})
        stats["messages"] = stats.get("messages",0) + 1; self.cfg["stats"] = stats; save_cfg(self.cfg)

        self.run_model(msgs)
        if self.cfg.get("compare_enabled", False) and self.compare_cmb.currentText():
            compare_model = self.compare_cmb.currentText(); self.compare_reply = ""
            think_compare = TypingBubble(f"Fusing ({compare_model})", self.cfg)
            self.scroll_lay.addWidget(think_compare)
            opts = self.get_model_opts()
            self.compare_worker = ModelWorker(compare_model, msgs, **opts)
            self.compare_worker.chunk.connect(lambda c, b=think_compare: self.update_compare(c, b))
            self.compare_worker.done.connect(lambda b=think_compare, m=compare_model: self.finish_compare(b, m))
            self.compare_worker.start()

    def run_model(self, msgs):
        self.reply = ""
        self.set_busy(True)
        think = TypingBubble(tr("Thinking...", self.cfg.get("ui_language", "English")), self.cfg)
        self.scroll_lay.addWidget(think)
        opts = self.get_model_opts()
        self.worker = ModelWorker(self.model, msgs, **opts)
        self.worker.chunk.connect(lambda c, b=think: self.update_think(c, b))
        self.worker.done.connect(lambda b=think: self.finish(b))
        self.worker.err.connect(lambda e, b=think: self.err(e, b))
        self.worker.start()

    def update_think(self, c, bub):
        try:
            if hasattr(bub, "stop"): bub.stop()
            self.reply += c; bub.raw_text = self.reply; bub.update_text()
        except RuntimeError: pass
    def finish(self, bub):
        self.set_busy(False)
        try:
            if hasattr(bub, "stop"): bub.stop()
            final = self.reply
            self.reply = ""

            # ---- Aksiyon JSON'u mu? (actions.py) ----
            if not self.pending_action and self.cfg.get("actions_enabled", True) and is_action_json(final):
                bub.raw_text = "⚙️ Running action..."
                bub.update_text()
                result = run_action(final)
                self.pending_action = True

                history = load_messages(self.cid)
                msgs = [{"role": r, "content": c} for r, c, _ in history]
                sys_prompt = self.cfg.get("custom_prompts", {}).get(self.mode, "")
                msgs.insert(0, {"role": "system", "content": sys_prompt})
                msgs.append({"role": "assistant", "content": final})
                msgs.append({"role": "user",
                             "content": f"[ACTION_RESULT] {result}\nBriefly tell the user the result in "
                                        f"natural language, in their language. If this is an error, just "
                                        f"relay the message you were given plainly and suggest checking "
                                        f"their internet connection — do NOT invent extra technical causes "
                                        f"or details you were not given."})
                try:
                    self.scroll_lay.removeWidget(bub); bub.deleteLater()
                except RuntimeError:
                    pass
                self.run_model(msgs)
                return

            self.pending_action = False
            bub.raw_text = final; bub.update_text()
            save_message(self.cid, "assistant", final)
            stripped = final.strip()
            title = (stripped[:30] + "...") if len(stripped) > 30 else (stripped or "New Fusion")
            conn = sqlite3.connect(self.db_path); c = conn.cursor()
            c.execute("UPDATE conversations SET title=?,model=? WHERE id=?", (title, self.model, self.cid))
            conn.commit(); conn.close(); self.refresh_convs()
            stats = self.cfg.get("stats", {}); stats["tokens"] = stats.get("tokens",0) + len(final.split())
            self.cfg["stats"] = stats; save_cfg(self.cfg)

            on_done = self._voice_chat_listen if self.voice_chat_active else None
            if self.cfg.get("tts_enabled", False):
                self.speak(final, on_done=on_done)
            elif on_done:
                on_done()
        except RuntimeError: pass
    def err(self, e, bub):
        self.set_busy(False)
        self.pending_action = False
        try:
            if hasattr(bub, "stop"): bub.stop()
            bub.raw_text = f"Error: {e}"; bub.update_text()
        except RuntimeError: pass
        if self.voice_chat_active:
            QTimer.singleShot(300, self._voice_chat_listen)
            return
        QMessageBox.critical(self, "Model Error", e)
    def update_compare(self, c, bub):
        try:
            if hasattr(bub, "stop"): bub.stop()
            self.compare_reply += c; bub.raw_text = self.compare_reply; bub.update_text()
        except RuntimeError: pass
    def finish_compare(self, bub, model_name):
        try:
            if hasattr(bub, "stop"): bub.stop()
            bub.raw_text = self.compare_reply; bub.update_text()
        except RuntimeError: pass
        self.compare_reply = ""

    def get_model_opts(self):
        opts = {"temperature": self.cfg["temperature"], "max_tokens": self.cfg["max_tokens"],
                "top_p": self.cfg["top_p"], "repeat_penalty": self.cfg["repeat_penalty"],
                "num_ctx": self.cfg.get("context_length", 4096), "top_k": self.cfg.get("top_k", 40),
                "seed": self.cfg.get("seed", -1)}
        stop = self.cfg.get("stop", "")
        if stop: opts["stop"] = [s.strip() for s in stop.split(",") if s.strip()]
        if self.mode == "Lite": opts["max_tokens"] = min(opts["max_tokens"], 300); opts["temperature"] = max(opts["temperature"], 0.8)
        elif self.mode == "Pro": opts["max_tokens"] = max(opts["max_tokens"], 1500); opts["temperature"] = min(opts["temperature"], 0.4)
        elif self.mode == "Coding": opts["max_tokens"] = max(opts["max_tokens"], 2000); opts["temperature"] = min(opts["temperature"], 0.2)
        elif self.mode == "Deep Research": opts["max_tokens"] = max(opts["max_tokens"], 4000); opts["temperature"] = min(opts["temperature"], 0.3)
        elif self.mode == "Code Hub": opts["max_tokens"] = max(opts["max_tokens"], 3000); opts["temperature"] = min(opts["temperature"], 0.1)
        return opts

    # ---------- WEB & ARAMA ----------
    def handle_url(self, url):
        try:
            resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)[:3000]
            if not text.strip(): raise Exception("Empty page")
            self._send_message(f"Summarize: {url}", web_context=text)
        except Exception as e:
            QMessageBox.critical(self, "URL Error", f"Could not fetch URL. Check the link and try again.\n{str(e)[:200]}")

    def perform_web_search(self, query):
        self.search_thread = WebSearchThread(query)
        self.search_thread.result.connect(lambda snippets: self._send_message(query, web_context="\n".join(snippets)))
        self.search_thread.error.connect(lambda e: QMessageBox.critical(self, "Search Error", e))
        self.search_thread.start()

    def internet_available(self):
        try: requests.get("https://www.google.com", timeout=3); return True
        except: return False

    # ---------- EKLENTİ ----------
    def attach(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select files", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All (*.*)")
        if not files: return
        for fp in files:
            self.add_attachment(fp)
        self.update_attachment_bar()

    def add_attachment(self, fp):
        ext = os.path.splitext(fp)[1].lower()
        att = {"type": "file", "file_path": fp, "base64": None, "content": None, "thumbnail": None}
        if ext in ['.png','.jpg','.jpeg','.bmp','.gif','.webp']:
            att["type"] = "image"
            with open(fp, "rb") as f: att["base64"] = base64.b64encode(f.read()).decode()
            import cv2, numpy as np
            img = cv2.imread(fp)
            if img is not None:
                h, w = img.shape[:2]; scale = min(80/w, 60/h)
                new_w, new_h = int(w*scale), int(h*scale)
                thumb = cv2.resize(img, (new_w, new_h))
                thumb_rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
                qimg = QImage(thumb_rgb.data, new_w, new_h, new_w*3, QImage.Format.Format_RGB888)
                att["thumbnail"] = QPixmap.fromImage(qimg)
        else:
            att["thumbnail"] = QPixmap(80, 60); att["thumbnail"].fill(Qt.GlobalColor.darkGray)
        self.attachments.append(att)

    def remove_attachment(self, index):
        if 0 <= index < len(self.attachments):
            del self.attachments[index]; self.update_attachment_bar()

    def update_attachment_bar(self):
        while self.attachment_layout.count():
            item = self.attachment_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not self.attachments:
            self.attachment_bar.setVisible(False); return
        self.attachment_bar.setVisible(True)
        for i, att in enumerate(self.attachments):
            container = QWidget(); container.setFixedSize(90, 90)
            lay = QVBoxLayout(container); lay.setContentsMargins(2,2,2,2); lay.setSpacing(2)
            thumb_label = QLabel()
            if att.get("thumbnail"):
                thumb_label.setPixmap(att["thumbnail"].scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else: thumb_label.setText("?")
            thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(thumb_label)
            name_label = QLabel(os.path.basename(att.get("file_path", "attachment"))[:15])
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter); name_label.setStyleSheet("font-size:8px;"); lay.addWidget(name_label)
            remove_btn = QPushButton("✕"); remove_btn.setFixedSize(20,20)
            remove_btn.setStyleSheet("background:transparent; color:white; border:none; font-weight:bold;")
            remove_btn.clicked.connect(lambda checked, idx=i: self.remove_attachment(idx))
            top_row = QHBoxLayout(); top_row.addStretch(); top_row.addWidget(remove_btn)
            lay.insertLayout(0, top_row); container.setLayout(lay)
            self.attachment_layout.addWidget(container)
        self.attachment_layout.addStretch()

    def clear_attachments(self):
        self.attachments.clear(); self.update_attachment_bar()

    # ---------- EKRAN GÖRÜNTÜSÜ & KAMERA ----------
    def take_screenshot(self):
        self.stop_mic(); self.hide(); QTimer.singleShot(500, self._capture_screen)

    def _capture_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            pixmap = screen.grabWindow(0); img = pixmap.toImage()
            buffer = QByteArray(); pbuffer = QBuffer(buffer)
            pbuffer.open(QIODevice.OpenModeFlag.WriteOnly); img.save(pbuffer, "PNG")
            img_b64 = bytes(buffer.toBase64()).decode(); self.show()
            self.attachments.append({"type":"image", "file_path":"screenshot.png", "base64":img_b64, "content":None, "thumbnail":None})
            self.update_attachment_bar()
        else: self.show()

    def take_camera(self):
        self.stop_mic()
        lang = self.cfg.get("ui_language", "English")
        dlg = CameraDialog(lang, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_image is not None:
            import cv2, numpy as np
            from PIL import Image
            frame = dlg.captured_image; frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb); buf = BytesIO(); img.save(buf, format='PNG')
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            self.attachments.append({"type":"image", "file_path":"camera.jpg", "base64":img_b64, "content":None, "thumbnail":None})
            self.update_attachment_bar()

    def send_img(self, text, img_b64):
        instruction = "You are an image analysis assistant. Describe ONLY what you actually see."
        msg = f"{instruction}\n\n{text}"
        self.add_bubble(f"[Image]\n{text}", True); save_message(self.cid, "user", f"[Image]\n{text}")
        self.run_model([{"role":"user", "content":msg, "images":[img_b64]}])

    # ---------- SİSTEM İZLEME ----------
    def update_stats(self):
        try:
            cpu = psutil.cpu_percent(); ram = psutil.virtual_memory().percent
            self.cpu_label.setText(f"CPU: {cpu}%"); self.ram_label.setText(f"RAM: {ram}%")
            gpu_text = "GPU: N/A"
            try:
                import pynvml; pynvml.nvmlInit(); h = pynvml.nvmlDeviceGetHandleByIndex(0)
                gpu_text = f"GPU: {pynvml.nvmlDeviceGetUtilizationRates(h).gpu}%"; pynvml.nvmlShutdown()
            except: pass
            self.gpu_label.setText(gpu_text)
        except: pass
        stats = self.cfg.get("stats", {}); msgs = stats.get("messages",0); tokens = stats.get("tokens",0)
        self.stats_label.setText(f"Fusions: {msgs} | Tokens: {tokens}")

    # ---------- AYARLAR ----------
    def open_settings(self):
        lang = self.cfg.get("ui_language", "English")
        dlg = SettingsDialog(self.cfg, lang, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_cfg = dlg.get_config()
            # SettingsDialog ses/aksiyon anahtarlarını yönetmiyor — mevcut
            # değerleri koru, yeni cfg'de yoksa eskisinden al.
            for k, v in self.cfg.items():
                new_cfg.setdefault(k, v)
            self.cfg = new_cfg
            self.voice_orb.cfg = self.cfg
            save_cfg(self.cfg); self.apply_theme(); self.retranslate_ui()
            self.setWindowOpacity(self.cfg.get("opacity", 100) / 100.0); self.refresh_models()
            self.tts_btn.setChecked(self.cfg.get("tts_enabled", False))
            if self.cfg.get("tts_enabled", False) and not self.smart_tts: self.init_tts()
            elif not self.cfg.get("tts_enabled", False): self.smart_tts = None
            QMessageBox.information(self, "Settings", "Settings saved.")

    def is_multimodal(self, model):
        if not hasattr(self, "_multimodal_cache"):
            self._multimodal_cache = {}
        if model in self._multimodal_cache:
            return self._multimodal_cache[model]
        try:
            info = ollama.show(model); families = info.get('details',{}).get('families',[])
            result = 'clip' in families or 'vision' in families
        except Exception:
            result = False
        self._multimodal_cache[model] = result
        return result

    def closeEvent(self, ev):
        self.voice_chat_active = False
        self.stop_mic()
        self.stop_speaking()
        if self.worker and self.worker.isRunning(): self.worker.terminate()
        if self.compare_worker and self.compare_worker.isRunning(): self.compare_worker.terminate()
        ev.accept()

def lang_instr(lang):
    return f"[IMPORTANT: You must reply exclusively in {lang}. Do not use any other language.]"