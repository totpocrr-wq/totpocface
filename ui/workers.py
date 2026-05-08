"""Фоновые потоки: камера, обработка, инициализация моделей."""
from __future__ import annotations

import time
import traceback
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    CAMERA_WIDTH, CAMERA_HEIGHT,
    CAMERA_WIDTH_LIVE, CAMERA_HEIGHT_LIVE,
)
from core.camera import Camera
from core.pose_detector import PoseDetector
from core.face_swapper import FaceSwapper
from core.live_swapper import LiveSwapEngine
from core.video_processor import process_video
from core.recorder import VideoRecorder


class CameraWorker(QThread):
    """Читает кадры, прогоняет через PoseDetector и (опц.) Live face swap.

    Поддерживает 2 режима:
      - Обычный: 1280×720, с MediaPipe Pose (скелет), 30 FPS UI
      - Live: 640×480, БЕЗ MediaPipe Pose, БЕЗ отрисовки скелета, 15 FPS UI

    Переключение между режимами требует перезапуска треда — изменение
    разрешения камеры на лету не работает на большинстве устройств.
    """

    frame_ready = pyqtSignal(np.ndarray)        # BGR кадр для отображения
    person_status = pyqtSignal(bool)             # найден ли человек
    fps_update = pyqtSignal(float)               # средний FPS обработки
    error = pyqtSignal(str)

    def __init__(
        self,
        camera_index: int,
        live_mode: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self._show_skeleton = not live_mode  # в live скелет всегда выключен
        self._live_mode = live_mode
        self._recorder: VideoRecorder | None = None
        self._live_engine: LiveSwapEngine | None = None
        self._live_enabled = False

    def set_show_skeleton(self, show: bool):
        # В live-режиме скелет принципиально не показывается
        if self._live_mode:
            self._show_skeleton = False
        else:
            self._show_skeleton = show

    def attach_recorder(self, recorder: VideoRecorder | None):
        self._recorder = recorder

    def attach_live_engine(self, engine: LiveSwapEngine | None):
        """Подключить движок live face swap. None → выключить."""
        self._live_engine = engine

    def set_live_enabled(self, enabled: bool):
        """Включает/выключает live face swap без отсоединения engine."""
        self._live_enabled = enabled
        if self._live_engine and not enabled:
            self._live_engine.reset()

    def stop(self):
        self._running = False
        self.wait(2000)

    def run(self):
        self._running = True

        # Параметры режима
        if self._live_mode:
            cam_w, cam_h = CAMERA_WIDTH_LIVE, CAMERA_HEIGHT_LIVE
            ui_fps = 15  # реже обновляем UI чтобы не тратить CPU
            use_pose = False  # не запускаем MediaPipe вообще
        else:
            cam_w, cam_h = CAMERA_WIDTH, CAMERA_HEIGHT
            ui_fps = 30
            use_pose = True

        ui_interval = 1.0 / ui_fps

        try:
            cam = Camera(self.camera_index, width=cam_w, height=cam_h)
            pose = PoseDetector() if use_pose else None

            try:
                last_emit = 0.0
                last_fps_emit = 0.0
                while self._running:
                    ok, frame = cam.read()
                    if not ok:
                        time.sleep(0.01)
                        continue

                    # Зеркалим — привычнее как в зеркале
                    frame = cv2.flip(frame, 1)

                    # Live face swap (если включён)
                    if self._live_enabled and self._live_engine is not None:
                        frame = self._live_engine.process_frame(frame)

                    # Pose detection ТОЛЬКО в обычном режиме
                    if pose is not None and self._show_skeleton:
                        display, found = pose.process(frame.copy(), draw=True)
                    elif pose is not None:
                        # Скелет выключен пользователем, но мы в обычном режиме —
                        # всё равно проверяем наличие человека (это полезный индикатор)
                        _, found = pose.process(frame.copy(), draw=False)
                        display = frame
                    else:
                        # Live mode: вообще не проверяем человека через MediaPipe
                        display = frame
                        # «Найден» считаем равным факту что был face swap
                        found = bool(
                            self._live_engine
                            and self._live_engine.swapper._last_faces
                        )

                    # Запись (без скелета — чистый кадр)
                    if self._recorder is not None and self._recorder.is_active:
                        self._recorder.write(frame)

                    # UI throttle
                    now = time.time()
                    if now - last_emit >= ui_interval:
                        self.frame_ready.emit(display)
                        self.person_status.emit(found)
                        last_emit = now

                    # FPS обновляем раз в секунду
                    if self._live_engine and now - last_fps_emit >= 1.0:
                        self.fps_update.emit(self._live_engine.fps)
                        last_fps_emit = now
            finally:
                cam.release()
                if pose is not None:
                    pose.close()
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
