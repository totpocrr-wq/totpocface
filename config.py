"""Глобальные константы приложения."""
from pathlib import Path
import sys

# Базовый путь работает и для разработки, и для собранного .exe
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

MODELS_DIR = BASE_DIR / "models"
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"

MODELS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Параметры записи
RECORD_FPS = 30
RECORD_CODEC = "mp4v"
RECORD_EXT = ".mp4"

# Параметры превью
PREVIEW_WIDTH = 960
PREVIEW_HEIGHT = 540

# Pose detection
POSE_MIN_DETECTION_CONFIDENCE = 0.5
POSE_MIN_TRACKING_CONFIDENCE = 0.5

# Face swap
FACE_SWAP_MODEL_NAME = "inswapper_128.onnx"
FACE_DETECTOR_PACK = "buffalo_l"

# Watermark (обязателен по EU AI Act)
WATERMARK_TEXT = "AI GENERATED"
WATERMARK_FONT_SCALE = 0.7
WATERMARK_THICKNESS = 2

APP_NAME = "FaceSwap Studio"
APP_VERSION = "0.1.0"
