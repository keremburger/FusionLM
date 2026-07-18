from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QPushButton, QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer
from markdown import markdown
from themes import THEMES

class Bubble(QFrame):
    def __init__(self, text, is_user, cfg, model_name=""):
        super().__init__()
        self.setObjectName("userBubble" if is_user else "botBubble")
        self.cfg = cfg
        self.is_user = is_user
        self.raw_text = text
        self.model_name = model_name
        self.setMouseTracking(True)
        self.init_ui()

    def init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(4)

        if self.model_name:
            header_row = QHBoxLayout()
            header = QLabel(f"<b>{self.model_name}</b>")
            header.setStyleSheet("font-size: 9px; background: transparent;")
            header_row.addWidget(header)
            header_row.addStretch()
            lay.addLayout(header_row)

        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setOpenExternalLinks(True)
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = QFont(self.cfg.get("font_family", "Segoe UI"), self.cfg.get("font_size", 10))
        self.lbl.setFont(font)
        self.lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.update_text()
        lay.addWidget(self.lbl)

        self.copy_btn = QPushButton("📋", self)
        self.copy_btn.setFixedSize(22, 22)
        self.copy_btn.setToolTip("Copy")
        self.copy_btn.setStyleSheet("background: rgba(0,0,0,60); border: none; border-radius: 4px;")
        self.copy_btn.clicked.connect(self.copy_text)
        self.copy_btn.hide()

        self.apply_style()
        self.setMaximumWidth(700)

    def copy_text(self):
        QApplication.clipboard().setText(self.raw_text)
        self.copy_btn.setText("✅")
        QTimer.singleShot(1000, lambda: self.copy_btn.setText("📋"))

    def enterEvent(self, event):
        self.copy_btn.move(self.width() - 30, 6)
        self.copy_btn.raise_()
        self.copy_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.copy_btn.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        self.copy_btn.move(self.width() - 30, 6)
        super().resizeEvent(event)

    def update_text(self):
        try:
            html = markdown(self.raw_text, extensions=['fenced_code', 'tables'])
            self.lbl.setText(html)
            self.lbl.setTextFormat(Qt.TextFormat.RichText)
        except Exception:
            self.lbl.setText(self.raw_text)

    def apply_style(self):
        r = self.cfg.get("bubble_radius", 14)
        theme = THEMES.get(self.cfg.get("theme", "Dark"), THEMES["Dark"])
        if self.is_user:
            bg = theme["user_bubble_bg"]
            text_color = theme["user_text"]
        else:
            bg = theme["bot_bubble_bg"]
            text_color = theme["bot_text"]
        self.setStyleSheet(f"""
            #{self.objectName()} {{
                background-color: {bg};
                border-radius: {r}px;
                padding: 4px;
                margin-left: {40 if self.is_user else 8}px;
                margin-right: {8 if self.is_user else 40}px;
            }}
            #{self.objectName()} QLabel {{
                color: {text_color};
                background: transparent;
            }}
        """)


class TypingBubble(Bubble):
    """Cümle sonunda 'Thinking' balonu için nokta nokta animasyonlu gösterge."""
    def __init__(self, base_text, cfg):
        self.base_text = base_text
        self._dots = 0
        super().__init__(base_text, False, cfg)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(450)

    def _tick(self):
        self._dots = (self._dots + 1) % 4
        self.raw_text = self.base_text + "." * self._dots
        self.update_text()

    def stop(self):
        self.timer.stop()