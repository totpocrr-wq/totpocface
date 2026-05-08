"""Безопасные обёртки над OpenCV для работы с путями.

Зачем это нужно:
    OpenCV на Windows внутри использует ANSI-кодировку для имён файлов
    (это легаси из C++ кода). Если в пути есть кириллица, японские
    иероглифы или вообще любые символы вне Latin-1 — функции вроде
    cv2.imread() / cv2.imwrite() / cv2.VideoCapture() / cv2.VideoWriter()
    тихо падают и возвращают None или not opened().

    Вот типичный путь, который ломает OpenCV:
        C:\\Users\\Даниил\\AppData\\Local\\FaceSwapStudio\\1.jpg
                  ^^^^^^

Решение:
    Читаем файл через numpy/Path, потом отдаём байты в OpenCV.
    Запись — наоборот: сначала кодируем в память, потом пишем как байты.

    Для VideoCapture/VideoWriter (видео) трюк такой: используем CAP_FFMPEG
    бэкенд и конвертируем путь в short-name (DOS 8.3) — это работает
    с любыми символами на Windows.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imread_safe(path: str | Path) -> np.ndarray | None:
    """cv2.imread, который не падает на кириллических путях.

    Возвращает BGR ndarray или None, если файл не удалось прочитать.
    """
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def imwrite_safe(path: str | Path, img: np.ndarray, ext: str | None = None) -> bool:
    """cv2.imwrite, который работает с кириллическими путями.

    ext — расширение для кодировки (например, ".jpg", ".png").
    Если не указан — берётся из path.
    """
    p = Path(path)
    if ext is None:
        ext = p.suffix or ".png"
    try:
        ok, encoded = cv2.imencode(ext, img)
        if not ok:
            return False
        encoded.tofile(str(p))
        return True
    except Exception:
        return False


def videocapture_safe(path: str | Path) -> cv2.VideoCapture:
    """cv2.VideoCapture, который пытается работать с кириллическими путями.

    На Windows: пробуем сначала short-path (DOS 8.3), потом обычный путь.
    На других ОС: обычный путь.

    Возвращает VideoCapture (может быть not opened — проверяй isOpened()).
    """
    path_str = str(path)

    # На Windows пробуем сконвертировать в short path (8.3 DOS),
    # тогда там не будет кириллицы.
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
            GetShortPathNameW.argtypes = [
                wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ]
            GetShortPathNameW.restype = wintypes.DWORD

            buf = ctypes.create_unicode_buffer(260)
            need = GetShortPathNameW(path_str, buf, 260)
            if 0 < need < 260:
                short = buf.value
                # Иногда short-path возвращает то же самое, если short-name
                # отключён в ФС — тогда смысла пробовать нет.
                if short and short != path_str:
                    cap = cv2.VideoCapture(short, cv2.CAP_FFMPEG)
                    if cap.isOpened():
                        return cap
                    cap.release()
        except Exception:
            pass

    # Fallback — обычный путь
    return cv2.VideoCapture(path_str)


def videowriter_safe(
    path: str | Path,
    fourcc: int,
    fps: float,
    frame_size: tuple[int, int],
) -> cv2.VideoWriter:
    """cv2.VideoWriter с обходом проблемы кириллических путей.

    На Windows: создаём пустой файл (через Path), берём short-path,
    отдаём его в VideoWriter.
    """
    path_str = str(path)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            # Создаём пустой файл, чтобы short-path смог его найти
            if not p.exists():
                p.touch()

            GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
            GetShortPathNameW.argtypes = [
                wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ]
            GetShortPathNameW.restype = wintypes.DWORD

            buf = ctypes.create_unicode_buffer(260)
            need = GetShortPathNameW(path_str, buf, 260)
            if 0 < need < 260:
                short = buf.value
                if short and short != path_str:
                    writer = cv2.VideoWriter(short, fourcc, fps, frame_size)
                    if writer.isOpened():
                        return writer
                    writer.release()
        except Exception:
            pass

    return cv2.VideoWriter(path_str, fourcc, fps, frame_size)
