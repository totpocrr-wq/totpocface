"""Поиск и работа с веб-камерами."""
from __future__ import annotations

import cv2
from dataclasses import dataclass


@dataclass
class CameraInfo:
    index: int
    name: str
    width: int
    height: int

    def __str__(self) -> str:
        return f"{self.name} ({self.width}x{self.height})"


def list_cameras(max_index: int = 5) -> list[CameraInfo]:
    """Сканируем индексы 0..max_index-1, возвращаем доступные камеры.

    На Windows используем CAP_DSHOW — иначе долгие тайм-ауты.
    """
    cameras: list[CameraInfo] = []
    backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY

    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, backend)
        if not cap.isOpened():
            cap.release()
            continue

        ok, _ = cap.read()
        if not ok:
            cap.release()
            continue

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        cameras.append(
            CameraInfo(index=idx, name=f"Camera {idx}", width=width, height=height)
        )
        cap.release()

    return cameras


class Camera:
    """Тонкая обёртка над cv2.VideoCapture с безопасным закрытием."""

    def __init__(self, index: int):
        backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(index, backend)
        if not self._cap.isOpened():
            raise RuntimeError(f"Не удалось открыть камеру с индексом {index}")

        # Запрашиваем 1280x720 — большинство встроенных камер тянет
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0

    def read(self):
        """Возвращает (ok, frame) — frame в BGR."""
        return self._cap.read()

    def release(self):
        if self._cap is not None and self._cap.isOpened():
            self._cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()
