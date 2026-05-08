# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для FaceSwap Studio.

История:
  v1: упало на onnx.reference (Access Violation)
  v2: упало на onnxruntime.quantization.operators
  v3: успешная сборка, но в рантайме отсутствовал matplotlib
  v4 (этот файл): добавлен matplotlib обратно и принудительный сбор scipy/sklearn
"""
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    collect_dynamic_libs,
)

block_cipher = None

# ---------- Данные ----------
mediapipe_data = collect_data_files("mediapipe")
insightface_data = collect_data_files("insightface")
onnxruntime_data = collect_data_files(
    "onnxruntime",
    excludes=["**/quantization/**", "**/transformers/**", "**/tools/**"],
)

# ---------- Утилита ----------
def safe_submodules(pkg, exclude_prefixes=()):
    mods = collect_submodules(pkg)
    bad = tuple(pkg + "." + p for p in exclude_prefixes)
    return [m for m in mods if not any(m.startswith(b) for b in bad)]


# ---------- Hidden imports ----------
hidden = []

# MediaPipe
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

# scipy — собираем всё, чтобы не было "module not found" в рантайме
hidden += collect_submodules("scipy")

# sklearn — insightface через albumentations требует его
hidden += collect_submodules(
    "sklearn",
    filter=lambda name: not name.startswith("sklearn.datasets")
                        and not name.startswith("sklearn.experimental"),
)

# albumentations — без pytorch-расширений
hidden += collect_submodules(
    "albumentations",
    filter=lambda name: not name.startswith("albumentations.pytorch"),
)

# onnxruntime — только runtime
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

# pyvirtualcam — для трансляции в виртуальную камеру.
# Может быть не установлен — это не критично, обернём в try.
try:
    hidden += collect_submodules("pyvirtualcam")
except Exception:
    pass


# ---------- Бинарники ----------
# scipy и numpy включают .pyd файлы, которые иначе не подхватываются
binaries = []
binaries += collect_dynamic_libs("scipy")
binaries += collect_dynamic_libs("numpy")
binaries += collect_dynamic_libs("sklearn")


# ---------- Чёрный список ----------
excludes = [
    # onnx — режем рекурсивные/тестовые
    "onnx.reference",
    "onnx.backend",
    "onnx.backend.test",
    "onnx.tools",
    "onnx.examples",
    "onnx.test",

    # onnxruntime — quantization крашит сборку
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

    # JAX — балласт
    "jax", "jaxlib", "flatbuffers",
    "jax._src", "jaxlib.mlir",

    # Тяжёлое из sklearn/skimage
    "sklearn.datasets",
    "sklearn.experimental",
    "skimage.data",

    # GUI и dev-тулзы (matplotlib НЕ исключаем — нужен mediapipe!)
    "matplotlib.tests",
    "tkinter", "PyQt5", "PySide2", "PySide6",
    "IPython", "jupyter", "notebook",
    "pytest", "_pytest",

    # mediapipe тестовое
    "mediapipe.examples",
    "mediapipe.tasks.python.test",
    "mediapipe.tasks.cc.metadata.tests",
    "insightface.commands",

    # albumentations.pytorch не используется
    "albumentations.pytorch",

    # sympy — символьная математика, не нужна
    "sympy",
]


# ---------- Сборка ----------
a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
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
