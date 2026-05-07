"""Глобальные константы приложения.

Важно: пользовательские данные (модели, записи, результаты) хранятся в
%LOCALAPPDATA%/FaceSwapStudio/, а не рядом с .exe. Так нужно потому, что
после установки в Program Files обычное приложение НЕ имеет прав на запись
в свою папку — это политика Windows для защищённых директорий.
"""
from pathlib import Path
import os
import sys


APP_NAME = "FaceSwap Studio"
APP_VERSION = "0.1.0"
APP_FOLDER_NAME = "FaceSwapStudio"


def _user_data_dir() -> Path:
    """Возвращает папку для пользовательских данных приложения.

    Windows: C:/Users/<Name>/AppData/Local/FaceSwapStudio/
    macOS:   ~/Library/Application Support/FaceSwapStudio/
    Linux:   ~/.local/share/FaceSwapStudio/
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_FOLDER_NAME
        return Path.home() / "AppData" / "Local" / APP_FOLDER_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_FOLDER_NAME
    # Linux / прочее
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_FOLDER_NAME
    return Path.home() / ".local" / "share" / APP_FOLDER_NAME


# Базовый путь приложения (где .exe или main.py)
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent

# Папка для пользовательских данных — туда мы можем писать
DATA_DIR = _user_data_dir()
MODELS_DIR = DATA_DIR / "models"
OUTPUT_DIR = DATA_DIR / "output"
ASSETS_DIR = APP_DIR / "assets"  # ассеты — read-only, лежат рядом с .exe

# Создаём только то, во что будем писать
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Параметры записи ----------
RECORD_FPS = 30
RECORD_CODEC = "mp4v"
RECORD_EXT = ".mp4"

# ---------- Параметры превью ----------
PREVIEW_WIDTH = 960
PREVIEW_HEIGHT = 540

# ---------- Pose detection ----------
POSE_MIN_DETECTION_CONFIDENCE = 0.5
POSE_MIN_TRACKING_CONFIDENCE = 0.5

# ---------- Face swap ----------
FACE_SWAP_MODEL_NAME = "inswapper_128.onnx"
FACE_DETECTOR_PACK = "buffalo_l"

# ---------- Watermark (обязателен по EU AI Act) ----------
WATERMARK_TEXT = "AI GENERATED"
WATERMARK_FONT_SCALE = 0.7
WATERMARK_THICKNESS = 2
