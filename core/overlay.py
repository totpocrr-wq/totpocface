"""Наложение PNG-аксессуаров на лицо с автотрекингом.

Подход — простой, но рабочий:
  - Используем landmarks от InsightFace (уже есть в pipeline)
  - Для каждого аксессуара выбираем якорную точку (нос, левое ухо, ...)
  - PNG масштабируется относительно ширины лица
  - Альфа-канал PNG используется для прозрачности

Это НЕ AI-генерация, а простое геометрическое наложение. Зато:
  - Работает за миллисекунды
  - Не требует видеокарты
  - Предсказуемый результат
  - Понятный UX: «загрузил PNG → выбрал точку → готово»

Если позже добавим IP-Adapter / Stable Diffusion — сможем сосуществовать.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
import numpy as np

from core.cv_io import imread_safe


class AnchorPoint(Enum):
    """Куда крепить аксессуар. Имена — что видит пользователь."""
    LEFT_EAR = "Левое ухо"
    RIGHT_EAR = "Правое ухо"
    BOTH_EARS = "Оба уха"
    NOSE_TIP = "Кончик носа"
    NOSE_BRIDGE = "Переносица"
    FOREHEAD = "Лоб"
    LEFT_CHEEK = "Левая щека"
    RIGHT_CHEEK = "Правая щека"
    CHIN = "Подбородок"
    UPPER_LIP = "Над губой"


# InsightFace 2d106-landmark индексы (из buffalo_l/2d106det)
# https://github.com/deepinsight/insightface/wiki/Sample-and-usage#106-landmarks
_LANDMARK_106 = {
    "nose_tip": 80,
    "nose_bridge": 51,
    "left_eye_outer": 35,
    "right_eye_outer": 89,
    "left_ear": 0,    # leftmost contour point
    "right_ear": 32,  # rightmost contour point
    "forehead": 51,   # на 2d106 нет лба, берём переносицу + смещение вверх
    "chin": 16,
    "left_cheek": 6,
    "right_cheek": 26,
    "upper_lip": 86,
}


def _landmark_xy(face, key: str) -> tuple[int, int]:
    """Достаём (x,y) landmark по ключу, fallback на bbox если нет landmarks."""
    try:
        kps = face.landmark_2d_106
    except AttributeError:
        kps = None
    if kps is not None and key in _LANDMARK_106:
        idx = _LANDMARK_106[key]
        return int(kps[idx][0]), int(kps[idx][1])
    # Fallback — центр bbox
    bx1, by1, bx2, by2 = face.bbox
    return int((bx1 + bx2) / 2), int((by1 + by2) / 2)


@dataclass
class Overlay:
    """Один аксессуар."""
    image_bgra: np.ndarray   # PNG с альфа-каналом, BGRA
    anchor: AnchorPoint
    # Размер относительно ширины лица (1.0 = во всю ширину лица)
    scale: float = 0.3
    # Смещение от точки крепления, тоже в долях ширины лица
    offset_x: float = 0.0
    offset_y: float = 0.0
    enabled: bool = True

    @classmethod
    def from_path(cls, path: str | Path, anchor: AnchorPoint, scale: float = 0.3):
        img = imread_safe(path)
        if img is None:
            raise ValueError(f"Не удалось прочитать {path}")
        # imread_safe возвращает BGR; для PNG с альфой нужен BGRA.
        # Перечитываем напрямую через imdecode с UNCHANGED.
        data = np.fromfile(str(path), dtype=np.uint8)
        bgra = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        if bgra is None:
            raise ValueError(f"Не удалось декодировать {path}")
        if bgra.ndim == 2:  # grayscale
            bgra = cv2.cvtColor(bgra, cv2.COLOR_GRAY2BGRA)
        elif bgra.shape[2] == 3:  # без альфы — сделаем непрозрачным
            alpha = np.full(bgra.shape[:2], 255, dtype=np.uint8)
            bgra = np.dstack([bgra, alpha])
        return cls(image_bgra=bgra, anchor=anchor, scale=scale)


def _anchor_to_keys(anchor: AnchorPoint) -> list[str]:
    """Возвращает список ключей landmark для данной точки крепления."""
    return {
        AnchorPoint.LEFT_EAR: ["left_ear"],
        AnchorPoint.RIGHT_EAR: ["right_ear"],
        AnchorPoint.BOTH_EARS: ["left_ear", "right_ear"],
        AnchorPoint.NOSE_TIP: ["nose_tip"],
        AnchorPoint.NOSE_BRIDGE: ["nose_bridge"],
        AnchorPoint.FOREHEAD: ["forehead"],
        AnchorPoint.LEFT_CHEEK: ["left_cheek"],
        AnchorPoint.RIGHT_CHEEK: ["right_cheek"],
        AnchorPoint.CHIN: ["chin"],
        AnchorPoint.UPPER_LIP: ["upper_lip"],
    }[anchor]


def _alpha_blend(dst_bgr: np.ndarray, src_bgra: np.ndarray, x: int, y: int):
    """Смешиваем src_bgra поверх dst_bgr с центром в (x, y)."""
    sh, sw = src_bgra.shape[:2]
    dh, dw = dst_bgr.shape[:2]

    x0 = x - sw // 2
    y0 = y - sh // 2
    x1 = x0 + sw
    y1 = y0 + sh

    # Обрезаем по границам
    src_x0 = max(0, -x0); src_y0 = max(0, -y0)
    src_x1 = sw - max(0, x1 - dw); src_y1 = sh - max(0, y1 - dh)
    if src_x0 >= src_x1 or src_y0 >= src_y1:
        return  # вне кадра

    dx0 = max(0, x0); dy0 = max(0, y0)
    dx1 = min(dw, x1); dy1 = min(dh, y1)

    src = src_bgra[src_y0:src_y1, src_x0:src_x1]
    alpha = src[:, :, 3:4].astype(np.float32) / 255.0
    fg = src[:, :, :3].astype(np.float32)
    bg = dst_bgr[dy0:dy1, dx0:dx1].astype(np.float32)
    blended = fg * alpha + bg * (1 - alpha)
    dst_bgr[dy0:dy1, dx0:dx1] = blended.astype(np.uint8)


def apply_overlays(
    frame_bgr: np.ndarray,
    face,
    overlays: list[Overlay],
) -> np.ndarray:
    """Накладывает все включённые overlays на кадр в позициях согласно face."""
    if not overlays or face is None:
        return frame_bgr

    # Ширина лица для масштабирования
    bx1, by1, bx2, by2 = face.bbox
    face_w = max(20, int(bx2 - bx1))

    for ov in overlays:
        if not ov.enabled:
            continue
        keys = _anchor_to_keys(ov.anchor)
        for key in keys:
            cx, cy = _landmark_xy(face, key)
            target_w = max(8, int(face_w * ov.scale))
            sh, sw = ov.image_bgra.shape[:2]
            target_h = max(8, int(sh * target_w / sw))
            resized = cv2.resize(
                ov.image_bgra, (target_w, target_h),
                interpolation=cv2.INTER_AREA,
            )
            ox = int(face_w * ov.offset_x)
            oy = int(face_w * ov.offset_y)
            _alpha_blend(frame_bgr, resized, cx + ox, cy + oy)

    return frame_bgr
