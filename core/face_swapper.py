"""Замена лица через InsightFace (inswapper_128)."""
from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path

import insightface
from insightface.app import FaceAnalysis

from config import MODELS_DIR, FACE_DETECTOR_PACK
from core.model_downloader import ensure_inswapper


class FaceSwapper:
    """Высокоуровневый класс для замены лица.

    Использует:
      - FaceAnalysis (buffalo_l) для детекции лиц
      - inswapper_128.onnx для самой подмены
    """

    def __init__(self, providers: list[str] | None = None):
        # На GTX без CUDA-сборки onnxruntime — используем CPU.
        # Если у юзера onnxruntime-gpu установлен, попробуем CUDA.
        if providers is None:
            try:
                import onnxruntime as ort
                available = ort.get_available_providers()
                if "CUDAExecutionProvider" in available:
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                else:
                    providers = ["CPUExecutionProvider"]
            except Exception:
                providers = ["CPUExecutionProvider"]

        self.providers = providers

        # Детектор + анализатор лиц
        self._analyser = FaceAnalysis(
            name=FACE_DETECTOR_PACK,
            root=str(MODELS_DIR),
            providers=providers,
        )
        self._analyser.prepare(ctx_id=0, det_size=(640, 640))

        # Сама модель замены
        model_path = ensure_inswapper()
        self._swapper = insightface.model_zoo.get_model(
            str(model_path), providers=providers
        )

        self._source_face = None  # face object из исходного фото

    def set_source_from_image(self, image_path: str | Path) -> bool:
        """Загружает фото-источник и извлекает оттуда первое (крупнейшее) лицо."""
        img = cv2.imread(str(image_path))
        if img is None:
            return False
        faces = self._analyser.get(img)
        if not faces:
            return False
        # Берём самое крупное лицо
        faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
        self._source_face = faces[0]
        return True

    def set_source_from_video(self, video_path: str | Path) -> bool:
        """Извлекает лицо из лучшего кадра видео-источника."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False

        best_face = None
        best_score = 0.0

        # Сэмплируем до 30 кадров равномерно
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 30
        step = max(1, total // 30)
        idx = 0

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                faces = self._analyser.get(frame)
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
            return False
        self._source_face = best_face
        return True

    @property
    def has_source(self) -> bool:
        return self._source_face is not None

    def swap_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Заменяет все лица в кадре на исходное. Если лиц нет — возвращает оригинал."""
        if self._source_face is None:
            return frame_bgr

        faces = self._analyser.get(frame_bgr)
        if not faces:
            return frame_bgr

        result = frame_bgr.copy()
        for face in faces:
            result = self._swapper.get(result, face, self._source_face, paste_back=True)
        return result
