"""Определение позы человека (скелет) через MediaPipe.

Добавлено сглаживание (EMA) — landmarks усредняются с предыдущим кадром,
чтобы убрать дрожание на статичных изображениях и при медленных движениях.
"""
from __future__ import annotations

import cv2
import mediapipe as mp
import numpy as np

from config import POSE_MIN_DETECTION_CONFIDENCE, POSE_MIN_TRACKING_CONFIDENCE


class PoseDetector:
    """Обёртка над MediaPipe Pose с экспоненциальным сглаживанием."""

    # Коэффициент сглаживания (0 = только новый кадр, 1 = только предыдущий)
    # 0.7 = 70% веса предыдущему кадру → плавное движение
    SMOOTHING_ALPHA = 0.7

    def __init__(self):
        self._mp_pose = mp.solutions.pose
        self._mp_draw = mp.solutions.drawing_utils
        self._pose = self._mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            smooth_landmarks=True,  # включаем встроенное сглаживание
            min_detection_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=POSE_MIN_TRACKING_CONFIDENCE,
        )

        self._landmark_style = self._mp_draw.DrawingSpec(
            color=(0, 255, 200), thickness=2, circle_radius=3
        )
        self._connection_style = self._mp_draw.DrawingSpec(
            color=(255, 100, 0), thickness=2
        )

        # Состояние сглаживания
        self._prev_landmarks: np.ndarray | None = None
        self._frames_since_lost = 0

    def _smooth_landmarks(self, current: np.ndarray) -> np.ndarray:
        """Экспоненциальное сглаживание (EMA) координат landmarks."""
        if self._prev_landmarks is None or self._prev_landmarks.shape != current.shape:
            self._prev_landmarks = current
            return current

        # Если человек пропадал на >3 кадра, не сглаживаем — резкий старт
        if self._frames_since_lost > 3:
            self._prev_landmarks = current
            return current

        smoothed = (
            self.SMOOTHING_ALPHA * self._prev_landmarks
            + (1 - self.SMOOTHING_ALPHA) * current
        )
        self._prev_landmarks = smoothed
        return smoothed

    def process(self, frame_bgr: np.ndarray, draw: bool = True) -> tuple[np.ndarray, bool]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._pose.process(rgb)
        rgb.flags.writeable = True

        person_found = results.pose_landmarks is not None

        if not person_found:
            self._frames_since_lost += 1
            return frame_bgr, False

        self._frames_since_lost = 0

        if draw:
            # Применяем сглаживание прямо к landmark-объекту
            current = np.array(
                [(lm.x, lm.y, lm.z, lm.visibility) for lm in results.pose_landmarks.landmark],
                dtype=np.float32,
            )
            smoothed = self._smooth_landmarks(current)
            for i, lm in enumerate(results.pose_landmarks.landmark):
                lm.x = float(smoothed[i, 0])
                lm.y = float(smoothed[i, 1])
                lm.z = float(smoothed[i, 2])
                lm.visibility = float(smoothed[i, 3])

            self._mp_draw.draw_landmarks(
                frame_bgr,
                results.pose_landmarks,
                self._mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=self._landmark_style,
                connection_drawing_spec=self._connection_style,
            )

        return frame_bgr, True

    def reset(self):
        """Сбросить сглаживание (например, при смене камеры)."""
        self._prev_landmarks = None
        self._frames_since_lost = 0

    def close(self):
        self._pose.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
