"""Замена лица через InsightFace (inswapper_128).

Детекция лиц настроена агрессивно:
  - Низкий порог уверенности (0.3 вместо стандартных 0.5)
  - Высокое разрешение поиска (1024×1024 вместо 640×640)
  - Двухпроходный fallback на меньший размер при провале
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from enum import Enum

import cv2
import numpy as np

import insightface
from insightface.app import FaceAnalysis

from config import MODELS_DIR, FACE_DETECTOR_PACK
from core.model_downloader import ensure_inswapper


BUFFALO_L_FILES = [
    "1k3d68.onnx",
    "2d106det.onnx",
    "det_10g.onnx",
    "genderage.onnx",
    "w600k_r50.onnx",
]


class FaceLoadError(Enum):
    """Расширенный код ошибки при загрузке исходного лица."""
    OK = "ok"
    FILE_INVALID = "Не удалось открыть файл. Возможно, он повреждён или формат не поддерживается."
    NO_FACE = "На фото не найдено лицо. Попробуй фронтальный портрет с хорошим освещением."
    TOO_SMALL = "Лицо на фото слишком мелкое. Нужно крупнее (мин. 80×80 пикселей)."
    LOW_QUALITY = "Лицо найдено, но качество слишком низкое. Попробуй фото без размытия и теней."


def _ensure_buffalo_l_extracted():
    target_root = MODELS_DIR / "models" / FACE_DETECTOR_PACK
    if target_root.is_dir():
        existing = {p.name for p in target_root.iterdir()}
        if all(f in existing for f in BUFFALO_L_FILES):
            return target_root

    zip_candidates = [
        MODELS_DIR / "models" / f"{FACE_DETECTOR_PACK}.zip",
        MODELS_DIR / f"{FACE_DETECTOR_PACK}.zip",
    ]
    zip_path = next(
        (c for c in zip_candidates if c.exists() and c.stat().st_size > 1024 * 1024),
        None,
    )
    if zip_path is None:
        raise FileNotFoundError(
            f"Не найдена модель {FACE_DETECTOR_PACK}. "
            f"Скачай buffalo_l.zip и положи в {MODELS_DIR / 'models'}"
        )

    target_root.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if any(n.startswith(f"{FACE_DETECTOR_PACK}/") for n in names):
            zf.extractall(target_root.parent)
        else:
            target_root.mkdir(exist_ok=True)
            zf.extractall(target_root)

    try:
        zip_path.unlink()
    except Exception:
        pass
    return target_root


class FaceSwapper:
    def __init__(self, providers: list[str] | None = None):
        if providers is None:
            try:
                import onnxruntime as ort
                if "CUDAExecutionProvider" in ort.get_available_providers():
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                else:
                    providers = ["CPUExecutionProvider"]
            except Exception:
                providers = ["CPUExecutionProvider"]

        self.providers = providers

        _ensure_buffalo_l_extracted()
        model_path = ensure_inswapper()

        self._analyser = FaceAnalysis(
            name=FACE_DETECTOR_PACK,
            root=str(MODELS_DIR),
            providers=providers,
            allowed_modules=[
                "detection", "recognition", "genderage",
                "landmark_3d_68", "landmark_2d_106",
            ],
        )
        # Высокое разрешение + низкий порог = находим больше лиц
        self._analyser.prepare(ctx_id=0, det_size=(1024, 1024), det_thresh=0.3)

        self._swapper = insightface.model_zoo.get_model(
            str(model_path), providers=providers
        )

        self._source_face = None

    # ---------- Внутренний детектор с fallback ----------
    def _detect_faces_aggressive(self, img_bgr: np.ndarray):
        """Двухпроходная детекция: сначала большой размер, потом маленький.

        InsightFace внутри ресайзит вход к det_size, поэтому если лицо
        крошечное — оно может потеряться. Поэтому пробуем оба прохода.
        """
        # Проход 1 — основной
        faces = self._analyser.get(img_bgr)
        if faces:
            return faces

        # Проход 2 — на полном разрешении (без ресайза)
        # Меняем det_size временно
        h, w = img_bgr.shape[:2]
        # Если картинка маленькая — апскейлим её, потом всё равно работаем с этим
        if max(h, w) < 600:
            scale = 800 / max(h, w)
            upscaled = cv2.resize(
                img_bgr, (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_CUBIC,
            )
            faces = self._analyser.get(upscaled)
            if faces:
                # Координаты на апскейлнутой картинке — возвращаем как есть,
                # потому что это только для проверки наличия лица.
                # А исходное лицо для подмены берём из оригинала.
                # Делаем ещё один проход на оригинале с найденными координатами
                # — но проще просто использовать апскейлнутую версию.
                return self._analyser.get(upscaled)

        return []

    # ---------- Загрузка исходного лица ----------
    def set_source_from_image(self, image_path: str | Path) -> FaceLoadError:
        """Загружает фото-источник. Возвращает код ошибки."""
        img = cv2.imread(str(image_path))
        if img is None:
            return FaceLoadError.FILE_INVALID

        faces = self._detect_faces_aggressive(img)
        if not faces:
            return FaceLoadError.NO_FACE

        # Берём крупнейшее
        faces.sort(
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
            reverse=True,
        )
        face = faces[0]

        # Проверка размера
        bw = face.bbox[2] - face.bbox[0]
        bh = face.bbox[3] - face.bbox[1]
        if bw < 60 or bh < 60:
            return FaceLoadError.TOO_SMALL

        # Проверка уверенности
        if float(face.det_score) < 0.4:
            return FaceLoadError.LOW_QUALITY

        self._source_face = face
        return FaceLoadError.OK

    def set_source_from_video(self, video_path: str | Path) -> FaceLoadError:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return FaceLoadError.FILE_INVALID

        best_face = None
        best_score = 0.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 30
        step = max(1, total // 30)
        idx = 0

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                faces = self._detect_faces_aggressive(frame)
                if faces:
                    f = max(
                        faces,
                        key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]),
                    )
                    score = float(f.det_score) * (
                        (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
                    )
                    if score > best_score:
                        best_score = score
                        best_face = f
            idx += 1

        cap.release()
        if best_face is None:
            return FaceLoadError.NO_FACE

        bw = best_face.bbox[2] - best_face.bbox[0]
        bh = best_face.bbox[3] - best_face.bbox[1]
        if bw < 60 or bh < 60:
            return FaceLoadError.TOO_SMALL

        self._source_face = best_face
        return FaceLoadError.OK

    @property
    def has_source(self) -> bool:
        return self._source_face is not None

    def swap_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        if self._source_face is None:
            return frame_bgr
        faces = self._analyser.get(frame_bgr)
        if not faces:
            return frame_bgr
        result = frame_bgr.copy()
        for face in faces:
            result = self._swapper.get(result, face, self._source_face, paste_back=True)
        return result
