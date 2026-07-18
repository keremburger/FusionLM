import sys
from PyQt6.QtWidgets import QApplication
from chat_window import Chatter

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Chatter()
    w.show()
    sys.exit(app.exec())