"""Live face swap — замена лица в реал-тайм с веб-камеры.

Опционально транслирует результат в виртуальную камеру (pyvirtualcam),
чтобы Zoom / Discord / OBS / Chrome видели подменённое лицо как
обычную веб-камеру.

Производительность:
  - GTX 1060 + CUDA: ~20 FPS при 640×480
  - GTX 1060 + CUDA: ~12 FPS при 1280×720
  - CPU: ~3-5 FPS (рваное, не для использования)

Оптимизации:
  - Детекция лица не на каждом кадре (см. FACE_DETECT_EVERY_N_FRAMES)
  - Кэш landmarks между детекциями
  - Если pyvirtualcam недоступен — просто не транслируем, остальное работает
"""
from __future__ import annotations

import time
import traceback
from typing import Callable

import cv2
import numpy as np

from config import FACE_DETECT_EVERY_N_FRAMES_LIVE
from core.camera import Camera
from core.face_swapper import FaceSwapper


# pyvirtualcam импортируем лениво — он может быть не установлен,
# либо драйвер OBS Virtual Camera не зарегистрирован в системе.
def _try_import_pyvirtualcam():
    try:
        import pyvirtualcam
        return pyvirtualcam
    except ImportError:
        return None


class LiveSwapEngine:
    """Однопроходный движок live-замены лица.

    Не QThread — мы вызываем его методы из CameraWorker, чтобы не
    плодить лишние треды. Если позже захочется отдельный поток,
    обернуть несложно.
    """

    def __init__(
        self,
        swapper: FaceSwapper,
        detect_every: int = FACE_DETECT_EVERY_N_FRAMES_LIVE,
    ):
        self.swapper = swapper
        self.detect_every = detect_every
        self._frame_idx = 0

        # FPS-измеритель: считаем средний FPS за последние 30 кадров
        self._fps_window: list[float] = []
        self._last_frame_time: float | None = None

        # Виртуальная камера
        self._vcam = None
        self._vcam_module = None
        self._vcam_size: tuple[int, int] | None = None
        self._vcam_error: str | None = None

    # ---------- Виртуальная камера ----------
    def start_virtual_camera(self, width: int, height: int, fps: int = 30) -> tuple[bool, str]:
        """Пытается открыть виртуальную камеру.

        Возвращает (успех, сообщение). Если уже открыта — закрывает старую.
        """
        self.stop_virtual_camera()

        pvc = _try_import_pyvirtualcam()
        if pvc is None:
            return False, (
                "pyvirtualcam не установлен. Это бывает если запущено "
                "не из сборки приложения, а из исходников без зависимостей."
            )

        self._vcam_module = pvc
        try:
            # Пробуем backend OBS — он самый надёжный на Windows
            self._vcam = pvc.Camera(
                width=width, height=height, fps=fps,
                fmt=pvc.PixelFormat.BGR,  # OpenCV отдаёт BGR
            )
            self._vcam_size = (width, height)
            return True, f"Виртуальная камера запущена: {self._vcam.device}"
        except RuntimeError as e:
            self._vcam = None
            self._vcam_size = None
            self._vcam_error = str(e)
            return False, (
                "Не удалось открыть виртуальную камеру. Скорее всего "
                "не установлена OBS Virtual Camera. Установи OBS Studio "
                "(obsproject.com) и запусти его хотя бы раз — после этого "
                "драйвер появится в системе. Подробности: " + str(e)
            )

    def stop_virtual_camera(self):
        if self._vcam is not None:
            try:
                self._vcam.close()
            except Exception:
                pass
        self._vcam = None
        self._vcam_size = None

    @property
    def is_streaming(self) -> bool:
        return self._vcam is not None

    # ---------- Обработка кадра ----------
    def process_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Главный шаг: применяет face swap к кадру и (если включено) шлёт в vcam.

        Возвращает обработанный кадр для UI-предпросмотра.
        """
        # 1) Замена лица с кэшем детекций
        try:
            swapped = self.swapper.swap_frame_cached(
                frame_bgr, self._frame_idx, self.detect_every
            )
        except Exception:
            # На любом сбое в swap-цепочке оставляем оригинал, чтобы не зависнуть
            swapped = frame_bgr

        # 2) Если включена виртуальная камера — транслируем
        if self._vcam is not None:
            try:
                # Если размер кадра внезапно изменился — ресайз под vcam
                if self._vcam_size and (
                    swapped.shape[1] != self._vcam_size[0]
                    or swapped.shape[0] != self._vcam_size[1]
                ):
                    swapped_for_cam = cv2.resize(swapped, self._vcam_size)
                else:
                    swapped_for_cam = swapped
                self._vcam.send(swapped_for_cam)
                # send_until_next_frame внутри сам контролит частоту
                # vcam синхронизируется со своим fps, поэтому sleep тут не нужен
            except Exception as e:
                # Не падаем при сбое vcam — просто отключаем её
                self._vcam_error = str(e)
                self.stop_virtual_camera()

        # 3) FPS статистика
        now = time.time()
        if self._last_frame_time is not None:
            dt = now - self._last_frame_time
            if dt > 0:
                self._fps_window.append(1.0 / dt)
                if len(self._fps_window) > 30:
                    self._fps_window.pop(0)
        self._last_frame_time = now

        self._frame_idx += 1
        return swapped

    @property
    def fps(self) -> float:
        if not self._fps_window:
            return 0.0
        return sum(self._fps_window) / len(self._fps_window)

    def reset(self):
        """Сбросить кэш и счётчики (например, при переключении донора)."""
        self.swapper.reset_cache()
        self._frame_idx = 0
        self._fps_window.clear()
        self._last_frame_time = None

    def close(self):
        self.stop_virtual_camera()
