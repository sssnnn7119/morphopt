"""Controls for exporting saved design and deformation histories as GIFs."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..presentation.labels import typed_title
from ..worker_environment import configure_worker_process
from .file_dialogs import choose_save_file


class HistoryGifExportDialog(QDialog):
    def __init__(
        self,
        folder: str,
        max_iteration: int,
        mode: str,
        cases: tuple[str, ...],
        components: tuple[tuple[str, object], ...],
        camera: dict[str, Any],
        window_size: tuple[int, int],
        style: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self.setWindowTitle(tr(
            "ui.history_gif.design_title"
            if mode == "design"
            else "ui.history_gif.deformation_title"
        ))
        self.resize(520, 280)
        self._folder = folder
        self._camera = camera
        self._window_size = window_size
        self._style = style
        self._active = False
        self._cancelled = False
        self._directory: TemporaryDirectory | None = None
        self._destination = ""
        self._process = QProcess(self)
        configure_worker_process(self._process)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.finished.connect(self._completed)
        self._process.errorOccurred.connect(self._failed)

        layout = QVBoxLayout(self)
        hint = QLabel(tr("ui.history_gif.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.target = QComboBox()
        if mode == "design":
            for category, component in components:
                category_key = {
                    "Part": "ui.widgets.model_tree.container.geometry",
                    "FEA": "ui.widgets.model_tree.container.loads_group",
                    "Material": "ui.widgets.model_tree.container.materials",
                }[category]
                label = tr(
                    "ui.observation.component_title",
                    category=tr(category_key),
                    title=typed_title(component.name, type(component).__name__),
                )
                self.target.addItem(label, {
                    "category": category,
                    "name": component.name,
                })
        else:
            for case in cases:
                self.target.addItem(case, {"case": case})
        form.addRow(tr("ui.history_gif.target"), self.target)
        self.first_iteration = QSpinBox()
        self.first_iteration.setRange(1, max(1, max_iteration))
        self.first_iteration.setValue(1)
        form.addRow(tr("ui.history_gif.first_iteration"), self.first_iteration)
        self.last_iteration = QSpinBox()
        self.last_iteration.setRange(1, max(1, max_iteration))
        self.last_iteration.setValue(max(1, max_iteration))
        form.addRow(tr("ui.history_gif.last_iteration"), self.last_iteration)
        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(8)
        form.addRow(tr("ui.history_gif.fps"), self.fps)
        layout.addLayout(form)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr("ui.files.cancel"))
        cancel.clicked.connect(self.reject)
        self.export = QPushButton(tr("ui.history_gif.export"))
        self.export.setProperty("actionRole", "primary")
        self.export.clicked.connect(self._export)
        self.export.setEnabled(self.target.count() > 0)
        buttons.addWidget(cancel)
        buttons.addWidget(self.export)
        layout.addLayout(buttons)

    def _export(self) -> None:
        if self.first_iteration.value() > self.last_iteration.value():
            QMessageBox.warning(
                self, self.windowTitle(), tr("ui.history_gif.invalid_range")
            )
            return
        target = self.target.currentData()
        if not target:
            QMessageBox.warning(
                self, self.windowTitle(), tr("ui.history_gif.target_unavailable")
            )
            return
        default_name = (
            "design_history" if self._mode == "design" else "deformation_history"
        )
        selection = choose_save_file(
            self,
            self.windowTitle(),
            self._folder,
            default_name,
            {"gif": tr("ui.history_gif.file_filter")},
        )
        if selection is None:
            return

        self._directory = TemporaryDirectory(prefix="morphopt-history-gif-")
        request = Path(self._directory.name) / "request.json"
        request.write_text(json.dumps({
            "folder": self._folder,
            "destination": str(selection.path),
            "mode": self._mode,
            "target": target,
            "first_iteration": self.first_iteration.value(),
            "last_iteration": self.last_iteration.value(),
            "fps": self.fps.value(),
            "camera": self._camera,
            "window_size": self._window_size,
            "style": self._style,
        }, ensure_ascii=False), encoding="utf-8")
        self._destination = str(selection.path)
        self._active = True
        self._cancelled = False
        self._set_busy(True)
        self._process.start(
            sys.executable,
            ["-u", "-m", "morphopt.ui.history_gif_worker", str(request)],
        )

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.target,
            self.first_iteration,
            self.last_iteration,
            self.fps,
        ):
            widget.setEnabled(not busy)
        self.export.setEnabled(not busy)
        self.progress.setVisible(busy)

    def _completed(self, code: int, status: QProcess.ExitStatus) -> None:
        output = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        if code != 0 or status != QProcess.ExitStatus.NormalExit:
            self._finish(output or tr("ui.history_gif.failed"))
            return
        try:
            count_line = next(
                line for line in reversed(output.splitlines())
                if line.startswith("Exported ")
            )
            frame_count = int(count_line.split()[1])
        except (StopIteration, IndexError, ValueError):
            self._finish(output or tr("ui.history_gif.failed"))
            return
        self._finish(None, frame_count)

    def _failed(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish(self._process.errorString())

    def _finish(self, error: str | None, frame_count: int = 0) -> None:
        if not self._active:
            return
        self._active = False
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
        self._set_busy(False)
        if self._cancelled:
            return
        if error is not None:
            message = QMessageBox(self)
            message.setIcon(QMessageBox.Icon.Warning)
            message.setWindowTitle(self.windowTitle())
            message.setText(tr("ui.history_gif.failed"))
            message.setDetailedText(error)
            message.exec()
            return
        QMessageBox.information(
            self,
            self.windowTitle(),
            tr(
                "ui.history_gif.completed",
                count=frame_count,
                path=self._destination,
            ),
        )
        self.accept()

    def reject(self) -> None:
        if self._active:
            self._cancelled = True
            self._process.kill()
            self._process.waitForFinished(1000)
            output = Path(self._destination)
            output.with_name(f".{output.stem}.partial.gif").unlink(missing_ok=True)
        super().reject()

