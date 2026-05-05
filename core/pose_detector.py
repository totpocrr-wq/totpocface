"""Определение позы человека (скелет) через MediaPipe."""
from __future__ import annotations

import cv2
import mediapipe as mp
import numpy as np

from config import POSE_MIN_DETECTION_CONFIDENCE, POSE_MIN_TRACKING_CONFIDENCE


class PoseDetector:
    """Обёртка над MediaPipe Pose. Рисует скелет поверх кадра."""

    def __init__(self):
        self._mp_pose = mp.solutions.pose
        self._mp_draw = mp.solutions.drawing_utils
        self._mp_styles = mp.solutions.drawing_styles
        self._pose = self._mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=POSE_MIN_TRACKING_CONFIDENCE,
        )

        # Кастомные стили — ярче и чище, чем дефолтные
        self._landmark_style = self._mp_draw.DrawingSpec(
            color=(0, 255, 200), thickness=2, circle_radius=3
        )
        self._connection_style = self._mp_draw.DrawingSpec(
            color=(255, 100, 0), thickness=2
        )

    def process(self, frame_bgr: np.ndarray, draw: bool = True) -> tuple[np.ndarray, bool]:
        """Обрабатывает кадр. Возвращает (кадр_с_отрисовкой, человек_найден)."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._pose.process(rgb)
        rgb.flags.writeable = True

        person_found = results.pose_landmarks is not None

        if draw and person_found:
            self._mp_draw.draw_landmarks(
                frame_bgr,
                results.pose_landmarks,
                self._mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=self._landmark_style,
                connection_drawing_spec=self._connection_style,
            )

        return frame_bgr, person_found

    def close(self):
        self._pose.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
