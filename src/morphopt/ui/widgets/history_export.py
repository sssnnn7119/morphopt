"""History export forms with one shared subprocess and dialog lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...postprocess import BoundarySurfaceInfo
from ..i18n import tr
from ..presentation.labels import component_selection_title
from ..processes import start_worker
from .file_dialogs import choose_save_directory, choose_save_file, confirm_overwrite


class _HistoryExportDialog(QDialog):
    """Own request staging, busy state, completion, failure, and cancellation."""

    def __init__(self, prefix: str, title: str, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr(title))
        self._prefix = prefix
        self._active = False
        self._cancelled = False
        self._directory: TemporaryDirectory | None = None
        self._request: dict[str, Any] = {}
        self._process = QProcess(self)
        self._process.finished.connect(self._completed)
        self._process.errorOccurred.connect(self._failed)
        layout = QVBoxLayout(self)
        hint = QLabel(tr(prefix + ".hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.controls = QWidget()
        self.content = QVBoxLayout(self.controls)
        self.content.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.controls, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr("ui.files.cancel"))
        cancel.clicked.connect(self.reject)
        self.export = QPushButton(tr(prefix + ".export"))
        self.export.setProperty("actionRole", "primary")
        self.export.clicked.connect(self._export)
        buttons.addWidget(cancel)
        buttons.addWidget(self.export)
        layout.addLayout(buttons)

    def _export(self) -> None:
        raise NotImplementedError

    def _completion_message(self, response: dict[str, Any]) -> str:
        raise NotImplementedError

    def _start_export(self, request: dict[str, Any]) -> None:
        self._directory = TemporaryDirectory(prefix="morphopt-history-export-")
        path = Path(self._directory.name) / "request.json"
        path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        self._request = request
        self._active, self._cancelled = True, False
        self._set_busy(True)
        start_worker(self._process, path)

    def _set_busy(self, busy: bool) -> None:
        self.controls.setEnabled(not busy)
        self.export.setEnabled(not busy)
        self.progress.setVisible(busy)

    def _completed(self, code: int, status: QProcess.ExitStatus) -> None:
        if not self._active:
            return
        output = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        error, message = "", ""
        if not self._cancelled:
            if code != 0 or status != QProcess.ExitStatus.NormalExit:
                error = output or tr(self._prefix + ".failed")
            else:
                try:
                    response = json.loads(
                        (Path(self._directory.name) / "response.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    message = self._completion_message(response)
                except (OSError, ValueError, KeyError) as exc:
                    error = str(exc)
        self._finish(error, message)

    def _failed(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish(self._process.errorString())

    def _finish(self, error: str = "", message: str = "") -> None:
        if not self._active:
            return
        self._active = False
        self._directory.cleanup()
        self._directory = None
        self._set_busy(False)
        if self._cancelled:
            return
        if error:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle(self.windowTitle())
            dialog.setText(tr(self._prefix + ".failed"))
            dialog.setDetailedText(error)
            dialog.exec()
        else:
            QMessageBox.information(self, self.windowTitle(), message)
            self.accept()

    def reject(self) -> None:
        if self._active:
            self._cancelled = True
            self._process.kill()
            self._process.waitForFinished(1000)
            if self._request["action"] == "export_gif":
                output = Path(self._request["destination"])
                output.with_name(f".{output.stem}.partial.gif").unlink(missing_ok=True)
        super().reject()


class SurfaceExportDialog(_HistoryExportDialog):
    def __init__(
        self,
        folder: str,
        max_iteration: int,
        iteration: int,
        surfaces: tuple[BoundarySurfaceInfo, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("ui.surface_export", "ui.surface_export.title", parent)
        self.resize(720, 450)
        self._folder, self._surfaces = folder, surfaces
        form = QFormLayout()
        self.iteration = QSpinBox()
        self.iteration.setRange(1, max_iteration)
        self.iteration.setValue(iteration)
        form.addRow(tr("ui.surface_export.iteration"), self.iteration)
        self.content.addLayout(form)
        self.table = QTableWidget(len(surfaces), 4)
        self.table.setHorizontalHeaderLabels(
            [
                tr("ui.surface_export.part"),
                tr("ui.surface_export.surface"),
                tr("ui.surface_export.type"),
                tr("ui.surface_export.format"),
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self._formats: list[QComboBox] = []
        for row, surface in enumerate(surfaces):
            part = QTableWidgetItem(surface.part)
            part.setFlags(part.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            part.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, part)
            self.table.setItem(row, 1, QTableWidgetItem(f"surface_{surface.index}"))
            self.table.setItem(row, 2, QTableWidgetItem(surface.surface_type))
            formats = QComboBox()
            for format in surface.formats:
                formats.addItem(
                    "STEP (.stp)" if format == "stp" else "STL (.stl)", format
                )
            self._formats.append(formats)
            self.table.setCellWidget(row, 3, formats)
        self.content.addWidget(self.table)
        self.export.setEnabled(bool(surfaces))

    def _export(self) -> None:
        selections = [
            {
                "part": surface.part,
                "index": surface.index,
                "format": self._formats[row].currentData(),
            }
            for row, surface in enumerate(self._surfaces)
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        if not selections:
            QMessageBox.warning(
                self, self.windowTitle(), tr("ui.surface_export.invalid_selection")
            )
            return
        destination = choose_save_directory(
            self,
            self.windowTitle(),
            self._folder,
            f"iteration_{self.iteration.value()}_surfaces",
        )
        if not destination:
            return
        exists = Path(destination).exists()
        if exists and not confirm_overwrite(
            self, Path(destination), message_key="ui.surface_export.overwrite"
        ):
            return
        self._start_export(
            {
                "action": "export_surfaces",
                "folder": self._folder,
                "iteration": self.iteration.value(),
                "destination": destination,
                "selections": selections,
                "overwrite": exists,
            }
        )

    def _completion_message(self, response: dict[str, Any]) -> str:
        return tr(
            "ui.surface_export.completed",
            count=len(self._request["selections"]),
            iteration=self._request["iteration"],
            path=self._request["destination"],
        )


class HistoryGifExportDialog(_HistoryExportDialog):
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
        super().__init__(
            "ui.history_gif",
            "ui.history_gif.design_title"
            if mode == "design"
            else "ui.history_gif.deformation_title",
            parent,
        )
        self.resize(520, 280)
        self._folder, self._mode = folder, mode
        self._camera, self._window_size, self._style = camera, window_size, style
        form = QFormLayout()
        self.target = QComboBox()
        if mode == "design":
            for category, component in components:
                self.target.addItem(
                    component_selection_title(category, component),
                    {
                        "category": category,
                        "name": component.name,
                    },
                )
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
        self.content.addLayout(form)
        self.export.setEnabled(self.target.count() > 0)

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
        selection = choose_save_file(
            self,
            self.windowTitle(),
            self._folder,
            "design_history" if self._mode == "design" else "deformation_history",
            {"gif": tr("ui.history_gif.file_filter")},
        )
        if selection is not None:
            self._start_export(
                {
                    "action": "export_gif",
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
                }
            )

    def _completion_message(self, response: dict[str, Any]) -> str:
        return tr(
            "ui.history_gif.completed",
            count=response["frames"],
            path=self._request["destination"],
        )
