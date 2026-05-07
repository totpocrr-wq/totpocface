"""FaceSwap Studio — точка входа.

ВАЖНО про windowed-сборку PyInstaller (--noconsole):
    sys.stdout и sys.stderr равны None.
    Многие библиотеки (tqdm, pip, insightface, urllib3 и др.) пытаются
    в них писать и падают с
        AttributeError: 'NoneType' object has no attribute 'write'

    Чинится это в самом начале — ДО импорта PyQt6 и любых ML-библиотек —
    подменой None-потоков на безопасную заглушку. Дополнительно патчим
    tqdm, чтобы он вообще ничего не выводил и не падал.
"""
from __future__ import annotations

import sys
import os


# ============================================================
#  Шаг 1. Безопасные потоки stdout/stderr
# ============================================================
class _NullStream:
    """Заглушка для sys.stdout/stderr в windowed-режиме."""
    encoding = "utf-8"
    errors = None

    def write(self, *args, **kwargs): return 0
    def flush(self, *args, **kwargs): pass
    def isatty(self, *args, **kwargs): return False
    def close(self, *args, **kwargs): pass
    def writable(self, *args, **kwargs): return True
    def readable(self, *args, **kwargs): return False
    def seekable(self, *args, **kwargs): return False
    def fileno(self, *args, **kwargs):
        raise OSError("no fileno in windowed mode")
    def __iter__(self): return iter([])


# Подменяем ДО любых импортов
if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()

# Заодно sys.__stdout__ и __stderr__ — некоторые библиотеки используют их
if sys.__stdout__ is None:
    sys.__stdout__ = sys.stdout
if sys.__stderr__ is None:
    sys.__stderr__ = sys.stderr


# ============================================================
#  Шаг 2. Глушим tqdm полностью
# ============================================================
# Переменные окружения, на которые tqdm реагирует
os.environ["TQDM_DISABLE"] = "1"
os.environ["TQDM_MININTERVAL"] = "9999"

# Глобальный патч tqdm: оборачиваем его в no-op, который не пытается писать
# никуда. Делаем ДО импорта insightface — тогда insightface при `from tqdm
# import tqdm` получит уже наш патченный tqdm.
try:
    import tqdm as _tqdm_module

    class _SilentTqdm:
        """No-op замена tqdm.tqdm. Не выводит прогресс, не падает."""
        def __init__(self, iterable=None, *args, **kwargs):
            self.iterable = iterable
            self.n = 0
            self.total = kwargs.get("total", 0)

        def __iter__(self):
            if self.iterable is None:
                return iter([])
            for item in self.iterable:
                self.n += 1
                yield item

        def __enter__(self): return self
        def __exit__(self, *args, **kwargs): pass
        def update(self, *args, **kwargs): pass
        def close(self, *args, **kwargs): pass
        def set_description(self, *args, **kwargs): pass
        def set_postfix(self, *args, **kwargs): pass
        def refresh(self, *args, **kwargs): pass
        def write(self, *args, **kwargs): pass

    _tqdm_module.tqdm = _SilentTqdm
    # Некоторые библиотеки делают `from tqdm.auto import tqdm`
    try:
        import tqdm.auto as _tqdm_auto
        _tqdm_auto.tqdm = _SilentTqdm
    except Exception:
        pass
except ImportError:
    pass  # tqdm может вообще не быть в системе


# ============================================================
#  Шаг 3. Обычный запуск приложения
# ============================================================
import multiprocessing
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt

from config import APP_NAME, APP_VERSION, DATA_DIR
from ui.main_window import MainWindow


def _setup_crash_log():
    """Все непойманные исключения → %LOCALAPPDATA%/FaceSwapStudio/crash.log"""
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
        try:
            QMessageBox.critical(
                None, "Ошибка",
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
