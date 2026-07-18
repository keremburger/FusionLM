"""
voice_overlay.py — "Jarvis" tarzı, mikrofon seviyesine/duruma tepki veren
animasyonlu ses göstergesi (VoiceOrb).

chat_window.py bu widget'tan şunları bekler:
    orb = VoiceOrb(cfg)
    orb.set_state("idle" | "listening" | "speaking")
    orb.set_level(float 0..1)      # QThread'den de bağlanabilir (pyqtSlot)
    orb.cfg = yeni_cfg             # settings sonrası tema güncellemesi için
"""
import math

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QPainter, QColor, QPen, QRadialGradient

from themes import THEMES


class VoiceOrb(QWidget):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setFixedSize(40, 40)
        self._state = "idle"  # idle | listening | speaking
        self._level = 0.0
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    # ---------- public API ----------

    def set_state(self, state: str):
        self._state = state
        if state == "idle":
            self._level = 0.0
        self.update()

    @pyqtSlot(float)
    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, level))

    # ---------- animasyon ----------

    def _tick(self):
        self._phase += 0.15
        if self._state != "idle":
            self.update()

    def _accent_color(self) -> QColor:
        theme = THEMES.get(self.cfg.get("theme", "Dark"), THEMES["Dark"])
        return QColor(theme.get("accent", "#89b4fa"))

    # ---------- çizim ----------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        base_r = min(w, h) / 2 - 4
        color = self._accent_color()

        if self._state == "idle":
            radius = base_r * 0.55
            alpha = 130
        elif self._state == "listening":
            pulse = 0.5 + 0.5 * self._level
            radius = base_r * (0.55 + 0.35 * pulse)
            alpha = 230
        else:  # speaking
            pulse = 0.5 + 0.5 * abs(math.sin(self._phase))
            radius = base_r * (0.55 + 0.3 * pulse)
            alpha = 230

        gradient = QRadialGradient(cx, cy, max(radius, 1))
        inner = QColor(color)
        inner.setAlpha(alpha)
        outer = QColor(color)
        outer.setAlpha(15)
        gradient.setColorAt(0.0, inner)
        gradient.setColorAt(1.0, outer)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

        pen = QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(cx - base_r), int(cy - base_r), int(base_r * 2), int(base_r * 2))
