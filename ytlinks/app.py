"""Sovelluksen käynnistys."""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 puuttuu. Asenna riippuvuudet: pip install -r requirements.txt",
              file=sys.stderr)
        return 1
    from .gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("YouTube-linkkien kerääjä")
    window = MainWindow()
    window.show()
    return app.exec()
