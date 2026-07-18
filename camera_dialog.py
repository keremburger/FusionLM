from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QHBoxLayout, QPushButton, QDialogButtonBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from translations import tr

class CameraDialog(QDialog):
    def __init__(self, lang, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(tr("Webcam Capture", lang))
        self.resize(640, 520)
        self.captured_image = None

        layout = QVBoxLayout(self)

        self.camera_combo = QComboBox()
        self.detect_cameras()
        layout.addWidget(QLabel(tr("Select Camera:", lang)))
        layout.addWidget(self.camera_combo)

        self.video_label = QLabel(tr("Camera preview", lang))
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; border: 2px solid #555;")
        layout.addWidget(self.video_label)

        btn_layout = QHBoxLayout()
        self.capture_btn = QPushButton("📸 " + tr("Capture", lang))
        self.capture_btn.clicked.connect(self.capture)
        btn_layout.addWidget(self.capture_btn)
        self.retry_btn = QPushButton("🔄 " + tr("Retry", lang))
        self.retry_btn.clicked.connect(self.restart_camera)
        btn_layout.addWidget(self.retry_btn)
        layout.addLayout(btn_layout)

        self.button_box = QDialogButtonBox()
        self.ok_btn = self.button_box.addButton(QDialogButtonBox.StandardButton.Ok)
        self.cancel_btn = self.button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.ok_btn.setText(tr("Send", lang))
        self.cancel_btn.setText(tr("Delete", lang))
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.start_camera()

    def detect_cameras(self):
        self.camera_combo.clear()
        try:
            import cv2
            misses = 0
            for i in range(5):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    self.camera_combo.addItem(f"Camera {i}")
                    cap.release()
                    misses = 0
                else:
                    cap.release()
                    misses += 1
                    if misses >= 2:  # art arda 2 boş index -> daha fazla arama yapma
                        break
            if self.camera_combo.count() == 0:
                self.camera_combo.addItem("Default Camera")
        except Exception:
            self.camera_combo.addItem("Default Camera")

    def start_camera(self):
        try:
            import cv2
            idx = self.camera_combo.currentIndex()
            self.cap = cv2.VideoCapture(idx)
            if self.cap.isOpened():
                self.timer.start(30)
        except:
            pass

    def restart_camera(self):
        self.timer.stop()
        if self.cap:
            self.cap.release()
        self.captured_image = None
        self.start_camera()

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                import cv2
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                qimg = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(qimg).scaled(self.video_label.size(), Qt.AspectRatioMode.KeepAspectRatio)
                self.video_label.setPixmap(pixmap)

    def capture(self):
        self.timer.stop()
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.captured_image = frame.copy()
                import cv2
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                qimg = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(qimg).scaled(self.video_label.size(), Qt.AspectRatioMode.KeepAspectRatio)
                self.video_label.setPixmap(pixmap)
                if self.cap:
                    self.cap.release()
                    self.cap = None

    def closeEvent(self, event):
        self.timer.stop()
        if self.cap:
            self.cap.release()
        event.accept()