"""Фоновые потоки: камера, обработка, инициализация моделей."""
from __future__ import annotations

import time
import traceback
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from core.camera import Camera
from core.pose_detector import PoseDetector
from core.face_swapper import FaceSwapper
from core.video_processor import process_video
from core.recorder import VideoRecorder


class CameraWorker(QThread):
    """Читает кадры, прогоняет через PoseDetector, отдаёт в UI."""

    frame_ready = pyqtSignal(np.ndarray)        # BGR кадр для отображения
    person_status = pyqtSignal(bool)             # найден ли человек
    error = pyqtSignal(str)

    def __init__(self, camera_index: int, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self._show_skeleton = True
        self._recorder: VideoRecorder | None = None

    def set_show_skeleton(self, show: bool):
        self._show_skeleton = show

    def attach_recorder(self, recorder: VideoRecorder | None):
        """Привязать рекордер — кадры будут писаться, пока он активен."""
        self._recorder = recorder

    def stop(self):
        self._running = False
        self.wait(2000)

    def run(self):
        self._running = True
        try:
            with Camera(self.camera_index) as cam, PoseDetector() as pose:
                last_emit = 0.0
                while self._running:
                    ok, frame = cam.read()
                    if not ok:
                        time.sleep(0.01)
                        continue

                    # Зеркалим — привычнее как в зеркале
                    frame = cv2.flip(frame, 1)

                    # Pose detection
                    drawn, found = pose.process(frame.copy(), draw=self._show_skeleton)

                    # Запись (без скелета — чистый кадр)
                    if self._recorder is not None and self._recorder.is_active:
                        self._recorder.write(frame)

                    # Throttle до ~30 FPS на UI, чтобы не душить event loop
                    now = time.time()
                    if now - last_emit >= 1 / 30:
                        self.frame_ready.emit(drawn)
                        self.person_status.emit(found)
                        last_emit = now
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")


class ModelInitWorker(QThread):
    """Инициализирует FaceSwapper в фоне (скачивание + загрузка ONNX)."""

    progress = pyqtSignal(int, int)  # downloaded, total
    status = pyqtSignal(str)
    finished_ok = pyqtSignal(object)  # FaceSwapper
    error = pyqtSignal(str)

    def run(self):
        try:
            self.status.emit("Готовим ML-модели…")
            # Прогресс скачивания пробросим внутрь FaceSwapper -> ensure_inswapper
            # Для простоты — патчим прогресс через сигнал
            from core import model_downloader

            original = model_downloader.download_file
            signal = self.progress

            def wrapped(url, dest, progress_cb=None):
                def cb(d, t):
                    signal.emit(d, t)
                return original(url, dest, cb)

            model_downloader.download_file = wrapped
            try:
                swapper = FaceSwapper()
            finally:
                model_downloader.download_file = original

            self.status.emit("Модели готовы")
            self.finished_ok.emit(swapper)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")


class SourceLoadWorker(QThread):
    """Загрузка исходного лица из фото или видео."""

    finished_ok = pyqtSignal(object)  # FaceLoadError enum
    error = pyqtSignal(str)

    def __init__(self, swapper: FaceSwapper, source_path: Path, parent=None):
        super().__init__(parent)
        self.swapper = swapper
        self.source_path = source_path

    def run(self):
        try:
            ext = self.source_path.suffix.lower()
            if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
                result = self.swapper.set_source_from_video(self.source_path)
            else:
                result = self.swapper.set_source_from_image(self.source_path)
            self.finished_ok.emit(result)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")


class ProcessVideoWorker(QThread):
    """Прогон записанного видео через face swap."""

    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(object)  # Path
    error = pyqtSignal(str)

    def __init__(
        self,
        swapper: FaceSwapper,
        target_video: Path,
        overlays: list | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.swapper = swapper
        self.target_video = target_video
        self.overlays = overlays or []
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            out = process_video(
                self.target_video,
                self.swapper,
                overlays=self.overlays,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                cancel_flag=lambda: self._cancel,
            )
            self.finished_ok.emit(out)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")
