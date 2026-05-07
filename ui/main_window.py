"""Главное окно — пошаговый flow."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import Qt, pyqtSlot, QSize
from PyQt6.QtGui import QImage, QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFileDialog, QMessageBox, QProgressBar, QFrame, QStatusBar,
    QStackedWidget, QSizePolicy, QApplication,
)

from config import APP_NAME, APP_VERSION, OUTPUT_DIR
from core.camera import list_cameras, CameraInfo
from core.recorder import VideoRecorder
from ui.styles import QSS, COLORS
from ui.workers import (
    CameraWorker, ModelInitWorker, SourceLoadWorker, ProcessVideoWorker,
)


# ---------- вспомогательные виджеты ----------

class Card(QFrame):
    def __init__(self, title: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(12)
        if title:
            t = QLabel(title)
            t.setObjectName("cardTitle")
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
        # Фиксированная высота — чтобы карточка не «прыгала», когда меняется текст
        self.setFixedHeight(110)
        self.setWordWrap(True)
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._on_dropped = on_file_dropped

    def set_filename(self, name: str):
        """Показывает имя файла, обрезая если слишком длинное."""
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


# ---------- главное окно ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — v{APP_VERSION}")
        self.setMinimumSize(1180, 760)
        self.setStyleSheet(QSS)

        # Состояние
        self.cameras: list[CameraInfo] = []
        self.camera_worker: CameraWorker | None = None
        self.recorder = VideoRecorder()
        self.last_recording: Path | None = None

        self.swapper = None  # FaceSwapper, инициализируется в фоне
        self.model_worker: ModelInitWorker | None = None
        self.source_worker: SourceLoadWorker | None = None
        self.process_worker: ProcessVideoWorker | None = None

        self._build_ui()
        self._refresh_cameras()
        self._init_models_async()

    # ---------- UI ----------

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        main = QVBoxLayout(root)
        main.setContentsMargins(28, 24, 28, 16)
        main.setSpacing(20)

        # Header
        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Запись • замена лица • экспорт")
        subtitle.setObjectName("subtitle")
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header.addLayout(header_text)
        header.addStretch()

        self.model_status = QLabel("Инициализация моделей…")
        self.model_status.setObjectName("status_warn")
        header.addWidget(self.model_status)

        main.addLayout(header)

        # Контент: слева превью, справа контролы
        content = QHBoxLayout()
        content.setSpacing(20)

        # --- Левая колонка ---
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

        # Бейдж записи
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

        # --- Правая колонка ---
        right = QVBoxLayout()
        right.setSpacing(16)
        right.setContentsMargins(0, 0, 0, 0)

        # Шаг 1: камера
        cam_card = Card("01  Камера — лицо А (исходное)")
        cam_row = QHBoxLayout()
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(180)
        cam_row.addWidget(self.camera_combo, stretch=1)
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self._refresh_cameras)
        cam_row.addWidget(self.refresh_btn)
        cam_card.add_layout(cam_row)

        self.start_cam_btn = QPushButton("Запустить камеру")
        self.start_cam_btn.setObjectName("primary")
        self.start_cam_btn.clicked.connect(self._toggle_camera)
        cam_card.add(self.start_cam_btn)
        right.addWidget(cam_card)

        # Шаг 2: запись
        rec_card = Card("02  Запись видео с лицом А")
        self.record_btn = QPushButton("● Начать запись")
        self.record_btn.setObjectName("primary")
        self.record_btn.setEnabled(False)
        self.record_btn.clicked.connect(self._toggle_recording)
        rec_card.add(self.record_btn)
        self.record_status = QLabel("Запусти камеру, чтобы начать запись")
        self.record_status.setObjectName("subtitle")
        self.record_status.setWordWrap(True)
        self.record_status.setMinimumHeight(20)
        rec_card.add(self.record_status)
        right.addWidget(rec_card)

        # Шаг 3: лицо-донор Б
        src_card = Card("03  Лицо-донор Б (на которое заменяем)")
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

        # Шаг 4: обработка
        proc_card = Card("04  Замена А → Б")
        self.process_btn = QPushButton("Заменить лицо в записи")
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

        content.addLayout(right, stretch=1)
        main.addLayout(content)

        # Footer
        footer = QLabel(
            "Все экспортируемые видео содержат маркировку «AI GENERATED» "
            "согласно требованиям EU AI Act."
        )
        footer.setObjectName("subtitle")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(footer)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Готово")

    # ---------- инициализация моделей ----------

    def _init_models_async(self):
        self.model_worker = ModelInitWorker()
        self.model_worker.status.connect(
            lambda s: self.model_status.setText(s)
        )
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
        self._update_process_button()

    @pyqtSlot(str)
    def _on_models_error(self, msg: str):
        self.model_status.setText("Ошибка модели")
        self.model_status.setObjectName("status_err")
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)
        QMessageBox.critical(self, "Не удалось инициализировать модели", msg)

    # ---------- камеры ----------

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

    # ---------- запись ----------

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
        self.record_btn.setText("■ Остановить запись")
        self.rec_indicator.setVisible(True)
        self.record_status.setText(f"Идёт запись → {path.name}")

    def _stop_recording(self):
        if self.camera_worker:
            self.camera_worker.attach_recorder(None)
        path = self.recorder.stop()
        self.last_recording = path
        self.record_btn.setText("● Начать запись")
        self.rec_indicator.setVisible(False)
        if path:
            self.record_status.setText(f"Сохранено: {path.name}")
        self._update_process_button()

    # ---------- источник ----------

    def _browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбери фото или видео с лицом",
            "",
            "Медиа (*.jpg *.jpeg *.png *.bmp *.webp *.mp4 *.mov *.avi *.mkv)",
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
            lambda ok: self._on_source_loaded(ok, path)
        )
        self.source_worker.error.connect(
            lambda m: QMessageBox.critical(self, "Ошибка загрузки лица Б", m)
        )
        self.source_worker.start()

    @pyqtSlot(object, Path)
    def _on_source_loaded(self, result, path: Path):
        # result — это FaceLoadError из core.face_swapper
        from core.face_swapper import FaceLoadError

        if result == FaceLoadError.OK:
            self.source_status.setText(f"✓ Лицо Б извлечено из {path.name}")
            self.source_status.setStyleSheet(f"color: {COLORS['ok']};")
        else:
            # У FaceLoadError значение — это сразу человекочитаемое сообщение
            msg = result.value if hasattr(result, "value") else "Лицо Б не найдено."
            self.source_status.setText(msg)
            self.source_status.setWordWrap(True)
            self.source_status.setStyleSheet(f"color: {COLORS['danger']};")
        self._update_process_button()

    # ---------- обработка ----------

    def _update_process_button(self):
        ready = (
            self.swapper is not None
            and self.swapper.has_source
            and self.last_recording is not None
            and self.last_recording.exists()
        )
        self.process_btn.setEnabled(ready)

    def _start_processing(self):
        if not (self.swapper and self.last_recording):
            return
        self.process_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        self.process_worker = ProcessVideoWorker(self.swapper, self.last_recording)
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
            self,
            "Готово",
            f"Видео сохранено:\n{out_path}",
        )

    @pyqtSlot(str)
    def _on_process_error(self, msg: str):
        self.progress.setVisible(False)
        self.process_btn.setEnabled(True)
        QMessageBox.critical(self, "Ошибка обработки", msg)

    # ---------- утилиты ----------

    def _open_output_dir(self):
        path = OUTPUT_DIR
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # ---------- закрытие ----------

    def closeEvent(self, event):
        if self.camera_worker:
            self.camera_worker.stop()
        if self.recorder.is_active:
            self.recorder.stop()
        event.accept()
