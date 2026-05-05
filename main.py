"""FaceSwap Studio — точка входа."""
from __future__ import annotations

import sys
import multiprocessing

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from config import APP_NAME, APP_VERSION
from ui.main_window import MainWindow


def main():
    # Для PyInstaller на Windows
    multiprocessing.freeze_support()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
