"""Покадровая обработка целевого видео: face swap + водяной знак."""
from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Callable

from config import (
    OUTPUT_DIR,
    RECORD_CODEC,
    RECORD_EXT,
    WATERMARK_TEXT,
    WATERMARK_FONT_SCALE,
    WATERMARK_THICKNESS,
)
from core.face_swapper import FaceSwapper


def add_watermark(frame: np.ndarray, text: str = WATERMARK_TEXT) -> np.ndarray:
    """Полупрозрачный водяной знак в правом нижнем углу. Обязателен по EU AI Act."""
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(
        text, font, WATERMARK_FONT_SCALE, WATERMARK_THICKNESS
    )
    pad = 12
    x = w - tw - pad
    y = h - pad

    # Полупрозрачный чёрный фон
    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (x - 8, y - th - 8),
        (x + tw + 8, y + baseline + 4),
        (0, 0, 0),
        -1,
    )
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

    # Текст
    cv2.putText(
        frame, text, (x, y), font,
        WATERMARK_FONT_SCALE, (255, 255, 255),
        WATERMARK_THICKNESS, cv2.LINE_AA,
    )
    return frame


def process_video(
    target_video_path: str | Path,
    swapper: FaceSwapper,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_flag: Callable[[], bool] | None = None,
) -> Path:
    """Прогоняет целевое видео через swapper, кадр за кадром.

    Возвращает путь к итоговому файлу.
    """
    cap = cv2.VideoCapture(str(target_video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Не удалось открыть видео {target_video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"swapped_{ts}{RECORD_EXT}"
    fourcc = cv2.VideoWriter_fourcc(*RECORD_CODEC)
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Не удалось создать выходной VideoWriter")

    frame_idx = 0
    try:
        while True:
            if cancel_flag and cancel_flag():
                break

            ok, frame = cap.read()
            if not ok:
                break

            try:
                swapped = swapper.swap_frame(frame)
            except Exception as e:
                # На сложных кадрах InsightFace иногда падает — оставляем оригинал
                print(f"[processor] swap failed on frame {frame_idx}: {e}")
                swapped = frame

            swapped = add_watermark(swapped)
            writer.write(swapped)

            frame_idx += 1
            if progress_cb and total_frames:
                progress_cb(frame_idx, total_frames)
    finally:
        cap.release()
        writer.release()

    return out_path
