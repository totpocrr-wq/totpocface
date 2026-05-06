"""FaceSwap Studio — точка входа.

ВАЖНО: при сборке с PyInstaller --windowed (console=False) sys.stdout и
sys.stderr равны None. Многие библиотеки (tqdm, pip, insightface и др.)
пытаются в них писать и падают с
    AttributeError: 'NoneType' object has no attribute 'write'

Чтобы это починить, в самом начале (ДО импорта PyQt6 и любых ML-библиотек)
подменяем None-потоки на безопасную заглушку.
"""
from __future__ import annotations

import sys
import os


# ===== Фикс stdout/stderr для PyInstaller --windowed =====
class _NullStream:
    """Заглушка для sys.stdout/stderr, когда их нет (windowed mode).

    Имитирует все методы файлоподобного объекта, которые могут вызвать
    библиотеки. Все операции — пустые.
    """
    encoding = "utf-8"
    errors = None

    def write(self, *args, **kwargs):
        return 0

    def flush(self, *args, **kwargs):
        pass

    def isatty(self, *args, **kwargs):
        return False

    def fileno(self, *args, **kwargs):
        raise OSError("no fileno in windowed mode")

    def close(self, *args, **kwargs):
        pass

    def writable(self, *args, **kwargs):
        return True

    def readable(self, *args, **kwargs):
        return False

    def seekable(self, *args, **kwargs):
        return False

    def __iter__(self):
        return iter([])


if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()

# Дополнительно отключаем прогресс-бары tqdm, чтобы они не мешали
os.environ.setdefault("TQDM_DISABLE", "1")


# ===== Дальше — обычный запуск =====
import multiprocessing
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt

from config import APP_NAME, APP_VERSION, DATA_DIR
from ui.main_window import MainWindow


def _setup_crash_log():
    """Логируем непойманные исключения в %LOCALAPPDATA%/FaceSwapStudio/crash.log,
    чтобы можно было диагностировать проблемы у пользователей.
    """
    crash_log = DATA_DIR / "crash.log"

    def excepthook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write("\n=== CRASH ===\n")
                f.write(text)
                f.write("\n")
        except Exception:
            pass
        # Покажем пользователю
        try:
            QMessageBox.critical(
                None,
                "Ошибка",
                f"Произошла непредвиденная ошибка:\n\n{exc_value}\n\n"
                f"Подробности записаны в:\n{crash_log}",
            )
        except Exception:
            pass

    sys.excepthook = excepthook


def main():
    multiprocessing.freeze_support()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")

    _setup_crash_log()

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
