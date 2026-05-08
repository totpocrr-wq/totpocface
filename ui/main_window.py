"""Главное окно — пошаговый flow с поддержкой записи или загрузки видео."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFileDialog, QMessageBox, QProgressBar, QFrame, QStatusBar,
    QSizePolicy, QApplication, QScrollArea, QGroupBox, QListWidget,
    QListWidgetItem, QDoubleSpinBox, QSlider,
)

from config import APP_NAME, APP_VERSION, OUTPUT_DIR, VIDEO_EXTS, IMAGE_EXTS
from core.camera import list_cameras, CameraInfo
from core.recorder import VideoRecorder
from core.overlay import Overlay, AnchorPoint
from ui.styles import QSS, COLORS
from ui.workers import (
    CameraWorker, ModelInitWorker, SourceLoadWorker, ProcessVideoWorker,
)


# =====================================================================
#  Вспомогательные виджеты
# =====================================================================

class Card(QFrame):
    def __init__(self, title: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setObjectName("cardTitle")
            t.setWordWrap(True)
            layout.addWidget(t)
        self._inner = layout

    def add(self, *widgets):
        for w in widgets:
            if isinstance(w, int):
                self._inner.addSpacing(w)
            else:
                self._inner.addWidget(w)

    def add_layout(self, layout):
        self._inner.addLayout(layout)


class DropZone(QLabel):
    """Область drag-and-drop для фото/видео-источника."""

    DEFAULT_TEXT = "Перетащи сюда фото или видео\nс лицом-донором (Б)"

    def __init__(self, on_file_dropped, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self.DEFAULT_TEXT)
        self.setFixedHeight(110)
        self.setWordWrap(True)
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._on_dropped = on_file_dropped

    def set_filename(self, name: str):
        if len(name) > 40:
            name = name[:18] + "…" + name[-18:]
        self.setText(f"📄 {name}")

    def reset_text(self):
        self.setText(self.DEFAULT_TEXT)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            self.setProperty("active", True)
            self.style().unpolish(self); self.style().polish(self)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.setProperty("active", False)
        self.style().unpolish(self); self.style().polish(self)

    def dropEvent(self, e: QDropEvent):
        self.setProperty("active", False)
        self.style().unpolish(self); self.style().polish(self)
        urls = e.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.exists():
            self._on_dropped(path)


# =====================================================================
#  Главное окно
# =====================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — v{APP_VERSION}")
        self.setMinimumSize(1280, 820)
        self.setStyleSheet(QSS)

        # --- Состояние ---
        self.cameras: list[CameraInfo] = []
        self.camera_worker: CameraWorker | None = None
        self.recorder = VideoRecorder()

        # «Лицо A» — может быть либо запись с камеры, либо загруженное видео
        self.source_a_video: Path | None = None

        self.swapper = None
        self.model_worker: ModelInitWorker | None = None
        self.source_worker: SourceLoadWorker | None = None
        self.process_worker: ProcessVideoWorker | None = None

        # Список накладываемых аксессуаров
        self.overlays: list[Overlay] = []

        self._build_ui()
        self._refresh_cameras()
        self._init_models_async()

    # -----------------------------------------------------------------
    #  Построение UI
    # -----------------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        main = QVBoxLayout(root)
        main.setContentsMargins(28, 24, 28, 16)
        main.setSpacing(20)

        # ---- Header ----
        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Запись • замена лица • аксессуары")
        subtitle.setObjectName("subtitle")
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header.addLayout(header_text)
        header.addStretch()

        self.device_label = QLabel("")
        self.device_label.setObjectName("subtitle")
        header.addWidget(self.device_label)
        header.addSpacing(16)

        self.model_status = QLabel("Инициализация моделей…")
        self.model_status.setObjectName("status_warn")
        header.addWidget(self.model_status)
        main.addLayout(header)

        # ---- Контент: левая колонка (превью), правая (контролы со скроллом) ----
        content = QHBoxLayout()
        content.setSpacing(20)

        # === Левая колонка ===
        left = QVBoxLayout()
        left.setSpacing(16)

        self.preview_label = QLabel("Камера не запущена")
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(720, 405)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        left.addWidget(self.preview_label, stretch=1)

        self.rec_indicator = QLabel("● REC")
        self.rec_indicator.setObjectName("recIndicator")
        self.rec_indicator.setVisible(False)

        person_row = QHBoxLayout()
        self.person_status_label = QLabel("Человек: не определён")
        self.person_status_label.setObjectName("subtitle")
        person_row.addWidget(self.person_status_label)
        person_row.addStretch()
        person_row.addWidget(self.rec_indicator)
        left.addLayout(person_row)

        content.addLayout(left, stretch=2)

        # === Правая колонка — со скроллом, чтобы помещались все карточки ===
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setMinimumWidth(420)
        right_scroll.setMaximumWidth(460)

        right_inner = QWidget()
        right = QVBoxLayout(right_inner)
        right.setSpacing(16)
        right.setContentsMargins(0, 0, 4, 0)

        # ---- 01 Камера ----
        cam_card = Card("01 · Камера (лицо А)")
        cam_row = QHBoxLayout()
        cam_row.setSpacing(8)
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(180)
        self.camera_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        cam_row.addWidget(self.camera_combo, stretch=1)
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedWidth(40)
        self.refresh_btn.setToolTip("Обновить список камер")
        self.refresh_btn.clicked.connect(self._refresh_cameras)
        cam_row.addWidget(self.refresh_btn)
        cam_card.add_layout(cam_row)

        self.start_cam_btn = QPushButton("Запустить камеру")
        self.start_cam_btn.setObjectName("primary")
        self.start_cam_btn.clicked.connect(self._toggle_camera)
        cam_card.add(self.start_cam_btn)
        right.addWidget(cam_card)

        # ---- 02 Видео А: запись или загрузка ----
        rec_card = Card("02 · Видео А (исходное)")
        ab_row = QHBoxLayout()
        ab_row.setSpacing(8)
        self.record_btn = QPushButton("● Записать")
        self.record_btn.setObjectName("primary")
        self.record_btn.setEnabled(False)
        self.record_btn.clicked.connect(self._toggle_recording)
        ab_row.addWidget(self.record_btn, stretch=1)
        self.load_video_btn = QPushButton("Загрузить…")
        self.load_video_btn.clicked.connect(self._browse_video_a)
        ab_row.addWidget(self.load_video_btn, stretch=1)
        rec_card.add_layout(ab_row)

        self.record_status = QLabel("Запусти камеру для записи или загрузи готовое видео")
        self.record_status.setObjectName("subtitle")
        self.record_status.setWordWrap(True)
        self.record_status.setMinimumHeight(36)
        self.record_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        rec_card.add(self.record_status)
        right.addWidget(rec_card)

        # ---- 03 Лицо-донор Б ----
        src_card = Card("03 · Лицо-донор Б")
        self.dropzone = DropZone(self._on_source_dropped)
        src_card.add(self.dropzone)

        browse_btn = QPushButton("Выбрать файл…")
        browse_btn.clicked.connect(self._browse_source)
        src_card.add(browse_btn)

        self.source_status = QLabel("Лицо-донор Б не выбран")
        self.source_status.setObjectName("subtitle")
        self.source_status.setWordWrap(True)
        self.source_status.setMinimumHeight(36)
        self.source_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        src_card.add(self.source_status)
        right.addWidget(src_card)

        # ---- 03b Аксессуары ----
        acc_card = Card("03b · Аксессуары (необязательно)")
        acc_hint = QLabel(
            "Можно наложить PNG поверх лица: серьги, пирсинг, очки и т.п. "
            "Лучше всего PNG с прозрачным фоном."
        )
        acc_hint.setObjectName("subtitle")
        acc_hint.setWordWrap(True)
        acc_card.add(acc_hint)

        self.overlay_list = QListWidget()
        self.overlay_list.setMinimumHeight(80)
        self.overlay_list.setMaximumHeight(140)
        acc_card.add(self.overlay_list)

        acc_btns = QHBoxLayout()
        acc_btns.setSpacing(8)
        add_overlay_btn = QPushButton("+ Добавить…")
        add_overlay_btn.clicked.connect(self._add_overlay)
        acc_btns.addWidget(add_overlay_btn, stretch=1)
        rm_overlay_btn = QPushButton("Удалить")
        rm_overlay_btn.clicked.connect(self._remove_overlay)
        acc_btns.addWidget(rm_overlay_btn, stretch=1)
        acc_card.add_layout(acc_btns)
        right.addWidget(acc_card)

        # ---- 04 Замена ----
        proc_card = Card("04 · Замена А → Б")
        self.process_btn = QPushButton("Обработать видео")
        self.process_btn.setObjectName("primary")
        self.process_btn.setEnabled(False)
        self.process_btn.clicked.connect(self._start_processing)
        proc_card.add(self.process_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        proc_card.add(self.progress)

        self.open_output_btn = QPushButton("Открыть папку с результатами")
        self.open_output_btn.clicked.connect(self._open_output_dir)
        proc_card.add(self.open_output_btn)
        right.addWidget(proc_card)

        right.addStretch()
        right_scroll.setWidget(right_inner)
        content.addWidget(right_scroll, stretch=1)

        main.addLayout(content)

        # ---- Footer ----
        footer = QLabel(
            "Все экспорты содержат метку «AI GENERATED» (EU AI Act, ст. 50)."
        )
        footer.setObjectName("subtitle")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setWordWrap(True)
        main.addWidget(footer)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Готово")

    # -----------------------------------------------------------------
    #  Инициализация моделей
    # -----------------------------------------------------------------
    def _init_models_async(self):
        self.model_worker = ModelInitWorker()
        self.model_worker.status.connect(lambda s: self.model_status.setText(s))
        self.model_worker.progress.connect(self._on_model_progress)
        self.model_worker.finished_ok.connect(self._on_models_ready)
        self.model_worker.error.connect(self._on_models_error)
        self.model_worker.start()

    @pyqtSlot(int, int)
    def _on_model_progress(self, downloaded: int, total: int):
        if total > 0:
            mb = downloaded / (1024 * 1024)
            tot = total / (1024 * 1024)
            self.model_status.setText(f"Скачивание модели… {mb:.0f}/{tot:.0f} МБ")

    @pyqtSlot(object)
    def _on_models_ready(self, swapper):
        self.swapper = swapper
        self.model_status.setText("Модели готовы")
        self.model_status.setObjectName("status_ok")
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)

        # Покажем устройство (CUDA / CPU)
        label = getattr(swapper, "providers_label", "CPU")
        self.device_label.setText(f"⚙ {label}")
        if "CUDA" in label:
            self.device_label.setStyleSheet(f"color: {COLORS['ok']};")
        else:
            self.device_label.setStyleSheet(f"color: {COLORS['text_muted']};")

        self._update_process_button()

    @pyqtSlot(str)
    def _on_models_error(self, msg: str):
        self.model_status.setText("Ошибка модели")
        self.model_status.setObjectName("status_err")
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)
        QMessageBox.critical(self, "Не удалось инициализировать модели", msg)

    # -----------------------------------------------------------------
    #  Камеры
    # -----------------------------------------------------------------
    def _refresh_cameras(self):
        self.camera_combo.clear()
        self.statusBar().showMessage("Поиск камер…")
        QApplication.processEvents()
        self.cameras = list_cameras()
        if not self.cameras:
            self.camera_combo.addItem("Камеры не найдены")
            self.start_cam_btn.setEnabled(False)
            self.statusBar().showMessage("Камеры не найдены")
            return
        for c in self.cameras:
            self.camera_combo.addItem(str(c), userData=c.index)
        self.start_cam_btn.setEnabled(True)
        self.statusBar().showMessage(f"Найдено камер: {len(self.cameras)}")

    def _toggle_camera(self):
        if self.camera_worker and self.camera_worker.isRunning():
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self):
        idx = self.camera_combo.currentData()
        if idx is None:
            return
        self.camera_worker = CameraWorker(idx)
        self.camera_worker.frame_ready.connect(self._on_frame)
        self.camera_worker.person_status.connect(self._on_person_status)
        self.camera_worker.error.connect(
            lambda m: QMessageBox.critical(self, "Ошибка камеры", m)
        )
        self.camera_worker.start()
        self.start_cam_btn.setText("Остановить камеру")
        self.record_btn.setEnabled(True)
        self.record_status.setText("Готов к записи")

    def _stop_camera(self):
        if self.recorder.is_active:
            self._stop_recording()
        if self.camera_worker:
            self.camera_worker.stop()
            self.camera_worker = None
        self.start_cam_btn.setText("Запустить камеру")
        self.record_btn.setEnabled(False)
        self.preview_label.setText("Камера остановлена")
        self.preview_label.setPixmap(QPixmap())

    @pyqtSlot(np.ndarray)
    def _on_frame(self, frame_bgr: np.ndarray):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img)
        scaled = pix.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    @pyqtSlot(bool)
    def _on_person_status(self, found: bool):
        if found:
            self.person_status_label.setText("● Человек определён")
            self.person_status_label.setStyleSheet(f"color: {COLORS['ok']};")
        else:
            self.person_status_label.setText("○ Человек не виден")
            self.person_status_label.setStyleSheet(f"color: {COLORS['text_muted']};")

    # -----------------------------------------------------------------
    #  Запись и загрузка видео А
    # -----------------------------------------------------------------
    def _toggle_recording(self):
        if self.recorder.is_active:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not self.camera_worker:
            return
        path = self.recorder.start("record")
        self.camera_worker.attach_recorder(self.recorder)
        self.record_btn.setText("■ Остановить")
        self.rec_indicator.setVisible(True)
        self.record_status.setText(f"Идёт запись → {path.name}")

    def _stop_recording(self):
        if self.camera_worker:
            self.camera_worker.attach_recorder(None)
        path = self.recorder.stop()
        self.source_a_video = path
        self.record_btn.setText("● Записать")
        self.rec_indicator.setVisible(False)
        if path:
            self.record_status.setText(f"✓ Запись: {path.name}")
            self.record_status.setStyleSheet(f"color: {COLORS['ok']};")
        self._update_process_button()

    def _browse_video_a(self):
        exts = " ".join(f"*{e}" for e in VIDEO_EXTS)
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери видео с лицом А", "",
            f"Видео ({exts})",
        )
        if not path:
            return
        p = Path(path)
        self.source_a_video = p
        self.record_status.setText(f"✓ Загружено: {p.name}")
        self.record_status.setStyleSheet(f"color: {COLORS['ok']};")
        self._update_process_button()

    # -----------------------------------------------------------------
    #  Лицо-донор Б
    # -----------------------------------------------------------------
    def _browse_source(self):
        all_exts = " ".join(f"*{e}" for e in (IMAGE_EXTS | VIDEO_EXTS))
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери фото или видео с лицом Б", "",
            f"Медиа ({all_exts})",
        )
        if path:
            self._on_source_dropped(Path(path))

    def _on_source_dropped(self, path: Path):
        if not self.swapper:
            QMessageBox.warning(
                self, "Модели ещё грузятся",
                "Подожди завершения инициализации моделей.",
            )
            return
        self.source_status.setText(f"Ищу лицо Б в {path.name}…")
        self.source_status.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.dropzone.set_filename(path.name)

        self.source_worker = SourceLoadWorker(self.swapper, path)
        self.source_worker.finished_ok.connect(
            lambda res: self._on_source_loaded(res, path)
        )
        self.source_worker.error.connect(
            lambda m: QMessageBox.critical(self, "Ошибка загрузки лица Б", m)
        )
        self.source_worker.start()

    @pyqtSlot(object, Path)
    def _on_source_loaded(self, result, path: Path):
        from core.face_swapper import FaceLoadError
        if result == FaceLoadError.OK:
            self.source_status.setText(f"✓ Лицо Б извлечено из {path.name}")
            self.source_status.setStyleSheet(f"color: {COLORS['ok']};")
        else:
            msg = result.value if hasattr(result, "value") else "Лицо Б не найдено."
            self.source_status.setText(msg)
            self.source_status.setStyleSheet(f"color: {COLORS['danger']};")
        self._update_process_button()

    # -----------------------------------------------------------------
    #  Аксессуары (overlays)
    # -----------------------------------------------------------------
    def _add_overlay(self):
        # 1) Выбор PNG
        exts = " ".join(f"*{e}" for e in IMAGE_EXTS)
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери PNG с аксессуаром", "", f"Изображения ({exts})",
        )
        if not path:
            return

        # 2) Выбор точки крепления
        from PyQt6.QtWidgets import QInputDialog
        names = [a.value for a in AnchorPoint]
        chosen, ok = QInputDialog.getItem(
            self, "Куда крепим аксессуар?",
            "Выбери место на лице:",
            names, 0, False,
        )
        if not ok:
            return
        anchor = next(a for a in AnchorPoint if a.value == chosen)

        # 3) Размер
        scale, ok = QInputDialog.getDouble(
            self, "Размер аксессуара",
            "Доля ширины лица (0.05 — крошка, 1.0 — во всё лицо):",
            0.3, 0.05, 1.5, 2,
        )
        if not ok:
            return

        # 4) Создаём overlay
        try:
            ov = Overlay.from_path(path, anchor, scale=scale)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки аксессуара", str(e))
            return
        self.overlays.append(ov)

        item = QListWidgetItem(f"{Path(path).name} → {anchor.value} (×{scale:.2f})")
        item.setData(Qt.ItemDataRole.UserRole, len(self.overlays) - 1)
        self.overlay_list.addItem(item)

    def _remove_overlay(self):
        row = self.overlay_list.currentRow()
        if row < 0:
            return
        # Удаляем по индексу из списка
        if 0 <= row < len(self.overlays):
            self.overlays.pop(row)
        self.overlay_list.takeItem(row)

    # -----------------------------------------------------------------
    #  Обработка
    # -----------------------------------------------------------------
    def _update_process_button(self):
        ready = (
            self.swapper is not None
            and self.swapper.has_source
            and self.source_a_video is not None
            and Path(self.source_a_video).exists()
        )
        self.process_btn.setEnabled(ready)

    def _start_processing(self):
        if not (self.swapper and self.source_a_video):
            return
        self.process_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        self.process_worker = ProcessVideoWorker(
            self.swapper, self.source_a_video, overlays=self.overlays,
        )
        self.process_worker.progress.connect(self._on_process_progress)
        self.process_worker.finished_ok.connect(self._on_process_done)
        self.process_worker.error.connect(self._on_process_error)
        self.process_worker.start()

    @pyqtSlot(int, int)
    def _on_process_progress(self, current: int, total: int):
        if total > 0:
            pct = int(current * 100 / total)
            self.progress.setValue(pct)
            self.progress.setFormat(f"{current} / {total} кадров — {pct}%")

    @pyqtSlot(object)
    def _on_process_done(self, out_path: Path):
        self.progress.setValue(100)
        self.progress.setFormat("Готово")
        self.process_btn.setEnabled(True)
        QMessageBox.information(
            self, "Готово", f"Видео сохранено:\n{out_path}",
        )

    @pyqtSlot(str)
    def _on_process_error(self, msg: str):
        self.progress.setVisible(False)
        self.process_btn.setEnabled(True)
        QMessageBox.critical(self, "Ошибка обработки", msg)

    # -----------------------------------------------------------------
    #  Утилиты
    # -----------------------------------------------------------------
    def _open_output_dir(self):
        path = OUTPUT_DIR
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def closeEvent(self, event):
        if self.camera_worker:
            self.camera_worker.stop()
        if self.recorder.is_active:
            self.recorder.stop()
        event.accept()
