# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для FaceSwap Studio.

История падений:
  v1: упало на onnx.reference (Access Violation)
  v2: упало на onnxruntime.quantization.operators
  v3 (этот файл): отрезаем onnxruntime.quantization целиком +
                  большинство модулей onnx, кроме core, нужного runtime.

Подход — собираем submodules выборочно, без рекурсии в quantization/tools/transformers.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ---------- Данные ----------
mediapipe_data = collect_data_files("mediapipe")
insightface_data = collect_data_files("insightface")
# Берём только бинарные части onnxruntime, без quantization-данных
onnxruntime_data = collect_data_files(
    "onnxruntime",
    excludes=["**/quantization/**", "**/transformers/**", "**/tools/**"],
)

# ---------- Утилита ----------
def safe_submodules(pkg, exclude_prefixes=()):
    """submodules без указанных префиксов (например, 'tools.', 'quantization.')."""
    mods = collect_submodules(pkg)
    bad = tuple(pkg + "." + p for p in exclude_prefixes)
    return [m for m in mods if not any(m.startswith(b) for b in bad)]


# ---------- Hidden imports ----------
hidden = []

# MediaPipe — без тестов и десктоп-примеров
hidden += safe_submodules(
    "mediapipe",
    exclude_prefixes=(
        "examples", "tasks.python.test", "tasks.cc.metadata.tests",
        "python.calculator_graph_test", "python.image_frame_test",
        "python.image_test", "python.packet_test",
        "python.solution_base_test", "python.timestamp_test",
    ),
)

# InsightFace
hidden += safe_submodules(
    "insightface",
    exclude_prefixes=("commands", "thirdparty.face3d.mesh_numpy"),
)

# onnxruntime — только то, что нужно для inference: capi, core, datasets
# ВАЖНО: НЕ собираем submodules для quantization/transformers/tools/training/backend
hidden += [
    "onnxruntime",
    "onnxruntime.capi",
    "onnxruntime.capi._pybind_state",
    "onnxruntime.capi.onnxruntime_pybind11_state",
    "onnxruntime.capi.onnxruntime_inference_collection",
]

# PyQt6
hidden += [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
]

# OpenCV
hidden += ["cv2"]


# ---------- Чёрный список ----------
excludes = [
    # ===== onnx — режем всё, кроме базового =====
    "onnx.reference",         # крашил v1
    "onnx.backend",
    "onnx.backend.test",
    "onnx.tools",
    "onnx.examples",
    "onnx.test",

    # ===== onnxruntime — quantization крашил v2 =====
    "onnxruntime.quantization",
    "onnxruntime.quantization.operators",
    "onnxruntime.quantization.fusions",
    "onnxruntime.quantization.matmul_4bits_quantizer",
    "onnxruntime.quantization.matmul_bnb4_quantizer",
    "onnxruntime.transformers",
    "onnxruntime.tools",
    "onnxruntime.training",
    "onnxruntime.backend",
    "onnxruntime.datasets",

    # ===== JAX — пришёл через onnxruntime.transformers =====
    "jax", "jaxlib", "flatbuffers",
    "jax._src", "jaxlib.mlir",

    # ===== Тяжёлые библиотеки, которые потянул insightface =====
    # sklearn нельзя отрезать целиком — insightface её использует
    "sklearn.datasets",
    "sklearn.experimental",
    "skimage.data",

    # ===== GUI и dev-инструменты =====
    "matplotlib", "matplotlib.tests",
    "tkinter", "PyQt5", "PySide2", "PySide6",
    "IPython", "jupyter", "notebook",
    "pytest", "_pytest",

    # ===== mediapipe тестовое =====
    "mediapipe.examples",
    "mediapipe.tasks.python.test",
    "mediapipe.tasks.cc.metadata.tests",
    "insightface.commands",

    # ===== albumentations.pytorch не используется без torch =====
    "albumentations.pytorch",

    # ===== ml_dtypes — экзотические типы данных, нам не нужны =====
    # (если что-то сломается, вернуть)
    # "ml_dtypes",

    # ===== sympy — символьная математика =====
    "sympy",
]

# ---------- Сборка ----------
a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=mediapipe_data + insightface_data + onnxruntime_data,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FaceSwapStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FaceSwapStudio",
)
