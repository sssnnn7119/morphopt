"""Controller-level problem settings."""
from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..theme import theme_manager
from ..application.devices import detect_devices
from ..i18n import tr
from ..model.problem import ProblemDefinition
from ..refresh import RefreshContext
from .file_dialogs import choose_directory


class ControllerSettingsEditor(QWidget):
    """Edit settings stored on the problem controller."""

    labelChanged = Signal(str)
    resultFolderChanged = Signal(str)
    deviceChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._problem: ProblemDefinition | None = None
        self._device_block = False

        layout = QVBoxLayout(self)
        self.group = QGroupBox(self)
        form = QFormLayout(self.group)
        layout.addWidget(self.group)
        layout.addStretch(1)

        self.name_label = QLabel()
        self.name = QLineEdit(self.group)
        self.name.setFixedWidth(theme_manager.palette.layout.workbench.output_name_width)
        self.name.editingFinished.connect(
            lambda: self.labelChanged.emit(self.name.text().strip())
        )
        form.addRow(self.name_label, self.name)

        self.path_label = QLabel()
        self.path = QLineEdit(self.group)
        self.path.setMinimumWidth(theme_manager.palette.layout.workbench.path_minimum_width)
        self.path.editingFinished.connect(
            lambda: self.resultFolderChanged.emit(self.path.text().strip())
        )
        path_row = QWidget(self.group)
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        path_layout.addWidget(self.path, 1)
        self.browse_button = QPushButton("…", path_row)
        self.browse_button.setFixedWidth(
            theme_manager.palette.layout.workbench.directory_button_width
        )
        self.browse_button.clicked.connect(self._browse_path)
        path_layout.addWidget(self.browse_button)
        form.addRow(self.path_label, path_row)

        self.device_label = QLabel()
        self.device = QComboBox(self.group)
        self.device.setEditable(True)
        self.device.setFixedWidth(
            theme_manager.palette.layout.workbench.device_selector_width
        )
        self.device.addItem("cpu")
        self.device.addItems(
            [device for device in detect_devices() if device != "cpu"]
        )
        self.device.currentTextChanged.connect(self._emit_device)
        form.addRow(self.device_label, self.device)

        self.apply_language()

    def apply_language(self) -> None:
        self.group.setTitle(tr("ui.widgets.model_tree.container.problem"))
        self.name_label.setText(tr("ui.workbench.optimization_name"))
        self.path_label.setText(tr("ui.workbench.output_folder"))
        self.device_label.setText(tr("ui.workbench.device"))
        self.name.setToolTip(
            tr("ui.workbench.problem_name_opt_label_used_when_exporting_running")
        )
        self.path.setToolTip(
            tr("ui.workbench.result_output_directory_controller_path_result_folder")
        )
        self.device.setToolTip(
            tr(
                "ui.workbench.global_compute_device_cpu_cuda_0_used_by_start_optimization_and_the_upda"
            )
        )
        self.browse_button.setToolTip(tr("ui.workbench.select_output_folder"))

    def edit_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        if not self.name.hasFocus() and self.name.text() != problem.label:
            self.name.setText(problem.label)
        if not self.path.hasFocus() and self.path.text() != problem.result_folder:
            self.path.setText(problem.result_folder)

        self._device_block = True
        try:
            device = problem.device or "cpu"
            if self.device.findText(device) < 0:
                self.device.addItem(device)
            self.device.setCurrentText(device)
        finally:
            self._device_block = False

    def refresh_ui(self, context: RefreshContext) -> None:
        self.edit_problem(context.problem)

    def set_name(self, value: str) -> None:
        self.name.setText(value)

    def _emit_device(self, text: str) -> None:
        if not self._device_block:
            self.deviceChanged.emit(text)

    def _browse_path(self) -> None:
        start = self.path.text() or os.getcwd()
        folder = choose_directory(
            self, tr("ui.workbench.select_output_folder"), start
        )
        if folder:
            self.path.setText(folder)
            self.resultFolderChanged.emit(folder)
