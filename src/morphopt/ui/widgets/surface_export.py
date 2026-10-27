"""Select an archived iteration and export its individual boundary surfaces."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QProgressBar, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..application.surface_export import BoundarySurfaceExport
from ..i18n import tr
from ..worker_environment import configure_worker_process
from .file_dialogs import choose_save_directory, confirm_overwrite


class SurfaceExportDialog(QDialog):
    def __init__(
        self,
        folder: str,
        max_iteration: int,
        iteration: int,
        surfaces: tuple[BoundarySurfaceExport, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("ui.surface_export.title"))
        self.resize(720, 450)
        self._folder = folder
        self._surfaces = surfaces
        self._active = False
        self._cancelled = False
        self._directory: TemporaryDirectory | None = None
        self._destination = ""
        self._surface_count = 0
        self._process = QProcess(self)
        configure_worker_process(self._process)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.finished.connect(self._completed)
        self._process.errorOccurred.connect(self._failed)
        layout = QVBoxLayout(self)
        hint = QLabel(tr("ui.surface_export.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.iteration = QSpinBox()
        self.iteration.setRange(1, max_iteration)
        self.iteration.setValue(iteration)
        form.addRow(tr("ui.surface_export.iteration"), self.iteration)
        layout.addLayout(form)
        self.table = QTableWidget(len(surfaces), 4)
        self.table.setHorizontalHeaderLabels([
            tr("ui.surface_export.part"), tr("ui.surface_export.surface"),
            tr("ui.surface_export.type"), tr("ui.surface_export.format"),
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
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
                formats.addItem("STEP (.stp)" if format == "stp" else "STL (.stl)", format)
            self._formats.append(formats)
            self.table.setCellWidget(row, 3, formats)
        layout.addWidget(self.table, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr("ui.files.cancel"))
        cancel.clicked.connect(self.reject)
        self.export = QPushButton(tr("ui.surface_export.export"))
        self.export.setProperty("actionRole", "primary")
        self.export.clicked.connect(self._export)
        buttons.addWidget(cancel)
        buttons.addWidget(self.export)
        layout.addLayout(buttons)

    def _export(self) -> None:
        selections = [
            {"part": surface.part, "index": surface.index, "format": self._formats[row].currentData()}
            for row, surface in enumerate(self._surfaces)
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        if not selections:
            QMessageBox.warning(self, self.windowTitle(), tr("ui.surface_export.invalid_selection"))
            return
        destination = choose_save_directory(
            self, self.windowTitle(), self._folder, f"iteration_{self.iteration.value()}_surfaces",
        )
        if not destination:
            return
        exists = Path(destination).exists()
        if exists and not confirm_overwrite(self, Path(destination), message_key="ui.surface_export.overwrite"):
            return
        self._directory = TemporaryDirectory(prefix="morphopt-surface-export-")
        request = Path(self._directory.name) / "request.json"
        request.write_text(json.dumps({
            "folder": self._folder, "iteration": self.iteration.value(),
            "destination": destination, "selections": selections, "overwrite": exists,
        }, ensure_ascii=False), encoding="utf-8")
        self._destination, self._surface_count = destination, len(selections)
        self._active = True
        self._cancelled = False
        self._set_busy(True)
        self._process.start(sys.executable, ["-u", "-m", "morphopt.ui.surface_export_worker", str(request)])

    def _set_busy(self, busy: bool) -> None:
        self.iteration.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self.export.setEnabled(not busy)
        self.progress.setVisible(busy)

    def _completed(self, code: int, status: QProcess.ExitStatus) -> None:
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        error = (output or tr("ui.surface_export.failed")) if code != 0 or status != QProcess.ExitStatus.NormalExit else ""
        self._finish(error)

    def _failed(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish(self._process.errorString())

    def _finish(self, error: str) -> None:
        if not self._active:
            return
        self._active = False
        self._directory.cleanup()
        self._directory = None
        self._set_busy(False)
        if self._cancelled:
            return
        if error:
            message = QMessageBox(self)
            message.setIcon(QMessageBox.Icon.Warning)
            message.setWindowTitle(self.windowTitle())
            message.setText(tr("ui.surface_export.failed"))
            message.setDetailedText(error)
            message.exec()
        else:
            QMessageBox.information(self, self.windowTitle(), tr(
                "ui.surface_export.completed", count=self._surface_count,
                iteration=self.iteration.value(), path=self._destination,
            ))
            self.accept()

    def reject(self) -> None:
        if self._active:
            self._cancelled = True
            self._process.kill()
            self._process.waitForFinished(1000)
        super().reject()
