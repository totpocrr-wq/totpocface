"""Замена лица через InsightFace (inswapper_128).

Важный момент про пути: InsightFace ожидает модели по пути
    {root}/models/{name}/*.onnx
То есть если root = MODELS_DIR, то buffalo_l должен лежать в
    MODELS_DIR/models/buffalo_l/*.onnx

Если папки нет — InsightFace пытается её скачать через свой встроенный
механизм. У этого механизма зеркала часто отвалены, и в windowed-сборке
PyInstaller ещё и tqdm падает. Поэтому мы:
  1) Проверяем папку buffalo_l/ заранее
  2) Если её нет — даём пользователю понятное сообщение об ошибке
  3) НЕ полагаемся на storage.ensure_available
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import cv2
import numpy as np

import insightface
from insightface.app import FaceAnalysis

from config import MODELS_DIR, FACE_DETECTOR_PACK
from core.model_downloader import ensure_inswapper


# Файлы, которые должны лежать внутри buffalo_l/
BUFFALO_L_FILES = [
    "1k3d68.onnx",
    "2d106det.onnx",
    "det_10g.onnx",
    "genderage.onnx",
    "w600k_r50.onnx",
]


def _ensure_buffalo_l_extracted():
    """Гарантирует, что buffalo_l/ распакован в нужном месте.

    InsightFace ищет модели по пути MODELS_DIR/models/{name}/.
    Если у нас лежит buffalo_l.zip — распакуем его.
    Если уже распакован — ничего не делаем.
    Если нет ни zip, ни папки — кидаем ясное исключение.
    """
    target_root = MODELS_DIR / "models" / FACE_DETECTOR_PACK

    # Проверяем, всё ли уже на месте
    if target_root.is_dir():
        existing = {p.name for p in target_root.iterdir()}
        if all(f in existing for f in BUFFALO_L_FILES):
            return target_root  # всё ок

    # Ищем zip-архив в нескольких местах
    zip_candidates = [
        MODELS_DIR / "models" / f"{FACE_DETECTOR_PACK}.zip",
        MODELS_DIR / f"{FACE_DETECTOR_PACK}.zip",
    ]

    zip_path = None
    for cand in zip_candidates:
        if cand.exists() and cand.stat().st_size > 1024 * 1024:  # хотя бы 1 МБ
            zip_path = cand
            break

    if zip_path is None:
        # Нет ни папки, ни zip — это ошибка пользователя/окружения
        raise FileNotFoundError(
            f"Не найдена модель {FACE_DETECTOR_PACK}. "
            f"Скачай buffalo_l.zip и положи в {MODELS_DIR / 'models'}, "
            f"либо распакуй прямо в {target_root}."
        )

    # Распаковываем
    target_root.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Архив может содержать всё на верхнем уровне, либо в подпапке buffalo_l/
        names = zf.namelist()
        has_top_folder = any(n.startswith(f"{FACE_DETECTOR_PACK}/") for n in names)

        if has_top_folder:
            # Распакуем как есть, в models/
            zf.extractall(target_root.parent)
        else:
            # Файлы лежат на верхнем уровне zip — распакуем в buffalo_l/
            target_root.mkdir(exist_ok=True)
            zf.extractall(target_root)

    # Удалим zip, чтобы InsightFace не вздумал его перезагружать
    try:
        zip_path.unlink()
    except Exception:
        pass

    return target_root


class FaceSwapper:
    """Высокоуровневый класс для замены лица.

    Использует:
      - FaceAnalysis (buffalo_l) для детекции лиц
      - inswapper_128.onnx для самой подмены
    """

    def __init__(self, providers: list[str] | None = None):
        # Auto-detect CUDA
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

        # Подготавливаем структуру папок (распаковка zip если нужно)
        _ensure_buffalo_l_extracted()

        # Скачиваем inswapper_128.onnx если ещё нет
        # (этот вызов не падает, потому что мы используем requests без tqdm)
        model_path = ensure_inswapper()

        # Детектор + анализатор лиц.
        # root указывает на корень, внутри которого ожидается models/buffalo_l/
        self._analyser = FaceAnalysis(
            name=FACE_DETECTOR_PACK,
            root=str(MODELS_DIR),
            providers=providers,
            allowed_modules=["detection", "recognition", "genderage", "landmark_3d_68", "landmark_2d_106"],
        )
        self._analyser.prepare(ctx_id=0, det_size=(640, 640))

        # Модель замены
        self._swapper = insightface.model_zoo.get_model(
            str(model_path), providers=providers
        )

        self._source_face = None

    def set_source_from_image(self, image_path: str | Path) -> bool:
        """Загружает фото-источник и извлекает оттуда крупнейшее лицо."""
        img = cv2.imread(str(image_path))
        if img is None:
            return False
        faces = self._analyser.get(img)
        if not faces:
            return False
        faces.sort(
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
            reverse=True,
        )
        self._source_face = faces[0]
        return True

    def set_source_from_video(self, video_path: str | Path) -> bool:
        """Извлекает лицо из лучшего кадра видео-источника."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False

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
        """Заменяет все лица в кадре на исходное."""
        if self._source_face is None:
            return frame_bgr

        faces = self._analyser.get(frame_bgr)
        if not faces:
            return frame_bgr

        result = frame_bgr.copy()
        for face in faces:
            result = self._swapper.get(result, face, self._source_face, paste_back=True)
        return result
