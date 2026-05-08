"""Запись кадров в видеофайл."""
from __future__ import annotations

import cv2
import numpy as np
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR, RECORD_CODEC, RECORD_EXT, RECORD_FPS
from core.cv_io import videowriter_safe


class VideoRecorder:
    """Пишет кадры в .mp4. Размер кадра фиксируется при первом write()."""

    def __init__(self, fps: int = RECORD_FPS, output_dir: Path = OUTPUT_DIR):
        self.fps = fps
        self.output_dir = output_dir
        self._writer: cv2.VideoWriter | None = None
        self._path: Path | None = None
        self._frame_size: tuple[int, int] | None = None

    def start(self, prefix: str = "record") -> Path:
        """Создаёт writer. Реальная инициализация — на первом кадре."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = self.output_dir / f"{prefix}_{ts}{RECORD_EXT}"
        self._frame_size = None
        self._writer = None
        return self._path

    def write(self, frame_bgr: np.ndarray):
        if self._path is None:
            raise RuntimeError("Сначала вызови start()")

        if self._writer is None:
            h, w = frame_bgr.shape[:2]
            self._frame_size = (w, h)
            fourcc = cv2.VideoWriter_fourcc(*RECORD_CODEC)
            self._writer = videowriter_safe(
                self._path, fourcc, self.fps, self._frame_size
            )
            if not self._writer.isOpened():
                raise RuntimeError(f"Не удалось открыть VideoWriter для {self._path}")

        # Если размер кадра внезапно изменился — ресайзим
        h, w = frame_bgr.shape[:2]
        if (w, h) != self._frame_size:
            frame_bgr = cv2.resize(frame_bgr, self._frame_size)

        self._writer.write(frame_bgr)

    def stop(self) -> Path | None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        path = self._path
        self._path = None
        self._frame_size = None
        return path

    @property
    def is_active(self) -> bool:
        return self._path is not None
