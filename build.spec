# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для FaceSwap Studio.

Что важно знать про этот файл:
  * collect_submodules('onnxruntime') рекурсивно тащит onnx.reference,
    который при анализе крашит PyInstaller (Access Violation).
    Решение — явно исключить onnx.reference и весь onnxruntime.transformers.
  * insightface тянет albumentations -> pydantic -> jax/jaxlib (~500 МБ
    балласта), которые нам не нужны. Исключаем.
  * Куча *_test модулей mediapipe и onnxruntime тоже не нужна в проде.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ---------- Данные (assets, .tflite модели mediapipe и т.д.) ----------
mediapipe_data = collect_data_files("mediapipe")
insightface_data = collect_data_files("insightface")
onnxruntime_data = collect_data_files("onnxruntime")

# ---------- Hidden imports ----------
# Берём submodules адресно — без onnx.reference и transformers
def safe_submodules(pkg, exclude_prefixes=()):
    """Возвращает submodules пакета, отфильтровав опасные/тяжёлые."""
    mods = collect_submodules(pkg)
    return [
        m for m in mods
        if not any(m.startswith(pkg + "." + p) or m == pkg + "." + p.rstrip(".")
                   for p in exclude_prefixes)
    ]

hidden = []

# MediaPipe — без тестов и desktop-примеров
hidden += safe_submodules(
    "mediapipe",
    exclude_prefixes=(
        "examples", "tasks.python.test", "tasks.cc.metadata.tests",
        "python.calculator_graph_test", "python.image_frame_test",
        "python.image_test", "python.packet_test",
        "python.solution_base_test", "python.timestamp_test",
    ),
)

# InsightFace — без 3D-frontend и команд CLI
hidden += safe_submodules(
    "insightface",
    exclude_prefixes=("commands", "thirdparty.face3d.mesh_numpy"),
)

# onnxruntime — БЕЗ transformers (тащит jax, sympy и т.п.) и tools
hidden += safe_submodules(
    "onnxruntime",
    exclude_prefixes=(
        "transformers", "tools", "training",
        "quantization.matmul_4bits_quantizer",
        "quantization.matmul_bnb4_quantizer",
    ),
)

hidden += [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "cv2",
]

# ---------- Чёрный список ----------
# Это ключевая часть: onnx.reference крашит сборку, остальное — балласт
excludes = [
    # Главный виновник прошлого падения
    "onnx.reference",
    "onnx.backend.test",

    # onnxruntime лишнее
    "onnxruntime.transformers",
    "onnxruntime.tools",
    "onnxruntime.training",
    "onnxruntime.quantization.matmul_4bits_quantizer",
    "onnxruntime.quantization.matmul_bnb4_quantizer",

    # JAX и спутники — пришли как косвенная зависимость, ~500 МБ
    "jax", "jaxlib", "flatbuffers",

    # sklearn / skimage / scipy пришли через insightface, нам нужны лишь куски
    # Полностью отрезать sklearn нельзя (insightface использует),
    # но можно убрать тяжёлое
    "sklearn.datasets",
    "sklearn.experimental",
    "skimage.data",

    # Всякие GUI и прочее
    "matplotlib", "matplotlib.tests",
    "tkinter", "PyQt5", "PySide2", "PySide6",
    "IPython", "jupyter", "notebook",
    "pytest", "_pytest", "unittest",

    # mediapipe и insightface тестовые модули
    "mediapipe.examples",
    "mediapipe.tasks.python.test",
    "mediapipe.tasks.cc.metadata.tests",
    "insightface.commands",

    # JAX/MLIR
    "jax._src", "jaxlib.mlir",

    # Albumentations — крупная и не используется явно
    # (если insightface всё-таки требует, удалить из excludes)
    "albumentations.pytorch",
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
    upx=False,            # UPX часто триггерит антивирусы
    console=False,        # без консольного окна
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
