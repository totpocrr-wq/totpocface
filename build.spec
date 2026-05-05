# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для FaceSwap Studio.

Сборка:
    pyinstaller build.spec

Получаем dist/FaceSwapStudio/ — папку с .exe и DLL.
Папку потом упаковывает Inno Setup в установщик.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os

block_cipher = None

# MediaPipe и InsightFace требуют упаковки своих ассетов / весов
mediapipe_data = collect_data_files("mediapipe")
insightface_data = collect_data_files("insightface")
onnxruntime_data = collect_data_files("onnxruntime")

hidden = []
hidden += collect_submodules("mediapipe")
hidden += collect_submodules("insightface")
hidden += collect_submodules("onnxruntime")
hidden += [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=mediapipe_data + insightface_data + onnxruntime_data,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "scipy.spatial.cKDTree", "tkinter",
        "PyQt5", "PySide2", "PySide6",
    ],
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
    icon="assets/app.ico" if os.path.exists("assets/app.ico") else None,
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
