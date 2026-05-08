"""Глобальные константы приложения."""
from pathlib import Path
import os
import sys


APP_NAME = "FaceSwap Studio"
APP_VERSION = "0.2.0"
APP_FOLDER_NAME = "FaceSwapStudio"


def _user_data_dir() -> Path:
    """Папка для пользовательских данных (туда у нас всегда есть права)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_FOLDER_NAME
        return Path.home() / "AppData" / "Local" / APP_FOLDER_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_FOLDER_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_FOLDER_NAME
    return Path.home() / ".local" / "share" / APP_FOLDER_NAME


if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent

DATA_DIR = _user_data_dir()
MODELS_DIR = DATA_DIR / "models"
OUTPUT_DIR = DATA_DIR / "output"
ASSETS_DIR = APP_DIR / "assets"

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

# ---------- Производительность рендеринга ----------
# Раз в сколько кадров заново детектить лицо. Между детекциями
# используем интерполяцию (трекинг). 1 = каждый кадр (медленно, точно),
# 2 = каждый второй (быстрее в 1.5×), 3 = каждый третий (быстрее в 2×).
FACE_DETECT_EVERY_N_FRAMES = 2

# Параллелизм покадровой обработки. На CPU стоит ставить max(1, cpu//2),
# чтобы не упереться в память. На CUDA — 1 (GPU и так загружен).
RENDER_WORKERS_CPU = max(1, (os.cpu_count() or 4) // 2)
RENDER_WORKERS_GPU = 1

# ---------- Watermark (обязателен по EU AI Act) ----------
WATERMARK_TEXT = "AI GENERATED"
WATERMARK_FONT_SCALE = 0.7
WATERMARK_THICKNESS = 2

# ---------- Поддерживаемые форматы ----------
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
