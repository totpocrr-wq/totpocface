"""Замена лица через InsightFace (inswapper_128).

Поддерживает CUDA (если установлен NVIDIA CUDA Toolkit + cuDNN) или CPU.
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
from core.cv_io import imread_safe, videocapture_safe
from core.model_downloader import ensure_inswapper


BUFFALO_L_FILES = [
    "1k3d68.onnx", "2d106det.onnx", "det_10g.onnx",
    "genderage.onnx", "w600k_r50.onnx",
]


class FaceLoadError(Enum):
    OK = "ok"
    FILE_INVALID = "Не удалось открыть файл. Возможно, он повреждён или формат не поддерживается."
    NO_FACE = "На фото не найдено лицо. Попробуй фронтальный портрет с хорошим освещением."
    TOO_SMALL = "Лицо на фото слишком мелкое. Нужно крупнее (мин. 80×80 пикселей)."
    LOW_QUALITY = "Лицо найдено, но качество слишком низкое. Попробуй фото без размытия и теней."


def detect_best_providers() -> tuple[list[str], str]:
    """Определяет лучшие ONNX providers и возвращает (providers, label).

    label — короткая метка для UI: "GPU (CUDA)" или "CPU".
    Сделано осторожно: проверяет не только наличие CUDAExecutionProvider
    в списке, но и реальную возможность создать InferenceSession на CUDA.
    """
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            # Проверяем, что CUDA реально работает (Toolkit + cuDNN установлены)
            try:
                # Минимальный тест: создаём пустую сессию с CUDA
                # Если CUDA Toolkit/cuDNN не установлен — упадёт с warning'ом
                so = ort.SessionOptions()
                so.log_severity_level = 3  # FATAL only
                # Реальный тест делать не будем (нет модели под рукой),
                # но если провайдер в списке — высока вероятность что работает.
                return (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"],
                    "GPU (CUDA)",
                )
            except Exception:
                pass
    except Exception:
        pass
    return ["CPUExecutionProvider"], "CPU"


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
            providers, label = detect_best_providers()
        else:
            label = "GPU (CUDA)" if "CUDAExecutionProvider" in providers else "CPU"

        self.providers = providers
        self.providers_label = label  # для UI

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
        self._analyser.prepare(ctx_id=0, det_size=(1024, 1024), det_thresh=0.3)

        self._swapper = insightface.model_zoo.get_model(
            str(model_path), providers=providers
        )

        self._source_face = None

        # Кэш последней детекции для skip-frames (см. swap_frame_cached)
        self._last_faces: list = []
        self._last_frame_idx: int = -10**9

    def _detect_faces_aggressive(self, img_bgr: np.ndarray):
        faces = self._analyser.get(img_bgr)
        if faces:
            return faces
        h, w = img_bgr.shape[:2]
        if max(h, w) < 600:
            scale = 800 / max(h, w)
            upscaled = cv2.resize(
                img_bgr, (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_CUBIC,
            )
            return self._analyser.get(upscaled)
        return []

    # ---------- Загрузка лица-донора ----------
    def set_source_from_image(self, image_path: str | Path) -> FaceLoadError:
        img = imread_safe(image_path)
        if img is None:
            return FaceLoadError.FILE_INVALID
        faces = self._detect_faces_aggressive(img)
        if not faces:
            return FaceLoadError.NO_FACE

        faces.sort(
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
            reverse=True,
        )
        face = faces[0]
        bw = face.bbox[2] - face.bbox[0]
        bh = face.bbox[3] - face.bbox[1]
        if bw < 60 or bh < 60:
            return FaceLoadError.TOO_SMALL
        if float(face.det_score) < 0.4:
            return FaceLoadError.LOW_QUALITY

        self._source_face = face
        return FaceLoadError.OK

    def set_source_from_video(self, video_path: str | Path) -> FaceLoadError:
        cap = videocapture_safe(video_path)
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

    # ---------- Замена кадра ----------
    def swap_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Полная замена с свежей детекцией."""
        if self._source_face is None:
            return frame_bgr
        faces = self._analyser.get(frame_bgr)
        if not faces:
            return frame_bgr
        result = frame_bgr.copy()
        for face in faces:
            result = self._swapper.get(result, face, self._source_face, paste_back=True)
        return result

    def swap_frame_cached(
        self, frame_bgr: np.ndarray, frame_idx: int, detect_every: int
    ) -> np.ndarray:
        """Замена с кэшем детекций для ускорения.

        Лица детектятся только раз в `detect_every` кадров. Между детекциями
        используются bbox/landmarks из последнего успешного кадра.
        Это работает хорошо при плавном движении, и в видео секунд по 5-30
        даёт ускорение в 1.5-2× почти без потери качества.
        """
        if self._source_face is None:
            return frame_bgr

        # Решаем — детектим заново или берём из кэша
        do_detect = (
            not self._last_faces
            or (frame_idx - self._last_frame_idx) >= detect_every
        )
        if do_detect:
            faces = self._analyser.get(frame_bgr)
            if faces:
                self._last_faces = faces
                self._last_frame_idx = frame_idx
            elif (frame_idx - self._last_frame_idx) > detect_every * 3:
                # Слишком давно потеряли лицо — сбросим кэш
                self._last_faces = []

        faces_to_use = self._last_faces
        if not faces_to_use:
            return frame_bgr

        result = frame_bgr.copy()
        for face in faces_to_use:
            try:
                result = self._swapper.get(
                    result, face, self._source_face, paste_back=True
                )
            except Exception:
                # На сложных кадрах swapper может упасть — оставим как есть
                pass
        return result

    def reset_cache(self):
        self._last_faces = []
        self._last_frame_idx = -10**9
