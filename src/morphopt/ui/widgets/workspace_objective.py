"""Structured workspace objective settings over existing load parameters."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...constants import CONSTANT
from ..application.load_cases import WORKSPACE_AXES, workspace_case_status
from ..i18n import tr
from ..model.problem import ProblemDefinition


class WorkspaceObjectiveEditor(QWidget):
    changed = Signal()

    def __init__(
        self, term: dict, problem: ProblemDefinition, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.term, self.problem = term, problem
        self._rows = []
        layout = QVBoxLayout(self)
        form = QFormLayout()
        mode = QComboBox()
        for kind in WORKSPACE_AXES:
            mode.addItem(tr("ui.quickstart.goal." + kind), kind)
        mode.setCurrentIndex(max(0, mode.findData(term.get("kind"))))
        mode.currentIndexChanged.connect(lambda: self._set("kind", mode.currentData()))
        form.addRow(tr("ui.workspace_objective.kind"), mode)
        reference = QComboBox()
        reference.addItem(tr("ui.widgets.objective_editor.select_reference_point"), "")
        for name in problem.reference_point_names():
            reference.addItem(name, name)
        reference.setCurrentIndex(
            max(0, reference.findData(term.get("reference_point_name")))
        )
        reference.currentIndexChanged.connect(
            lambda: self._set("reference_point_name", reference.currentData())
        )
        form.addRow(tr("ui.widgets.objective_editor.reference_point"), reference)
        order = QSpinBox()
        order.setRange(
            CONSTANT.UI.QUICKSTART.LIMITS.WORKSPACE_GAUSS_ORDER_MIN,
            CONSTANT.UI.QUICKSTART.LIMITS.WORKSPACE_GAUSS_ORDER_MAX,
        )
        order.setValue(int(term.get("gauss_order", 2)))
        order.valueChanged.connect(lambda value: self._set("gauss_order", value))
        form.addRow(tr("ui.workspace_objective.gauss_order"), order)
        normalization = QDoubleSpinBox()
        normalization.setDecimals(8)
        normalization.setRange(1e-8, 1e12)
        normalization.setValue(float(term.get("normalization", 1.0)))
        normalization.valueChanged.connect(
            lambda value: self._set("normalization", value)
        )
        form.addRow(tr("ui.workspace_objective.normalization"), normalization)
        layout.addLayout(form)
        hint = QLabel(tr("ui.workspace_objective.inputs_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        selected = term.get("inputs", [])
        entries = [(entry["parameters"], entry["upper"], True) for entry in selected]
        occupied = {
            tuple(parameter) for entry in selected for parameter in entry["parameters"]
        }
        for load in problem.amplitude_components():
            for index in range(load.num_values):
                if (load.name, index) not in occupied:
                    entries.append(([[load.name, index]], 1.0, False))
        for parameters, upper, checked in entries:
            row = QHBoxLayout()
            check = QCheckBox(
                " + ".join(f"{name}[{index}]" for name, index in parameters)
            )
            check.setChecked(checked)
            limit = QLineEdit(str(upper))
            row.addWidget(check, 1)
            row.addWidget(QLabel(tr("ui.workspace_objective.upper")))
            row.addWidget(limit)
            layout.addLayout(row)
            self._rows.append((parameters, check, limit))
            check.toggled.connect(self._save_inputs)
            limit.editingFinished.connect(self._save_inputs)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh_status()

    def refresh_status(self) -> None:
        self.status.setText(workspace_case_status(self.term, self.problem))

    def _set(self, key: str, value: object) -> None:
        if self.term.get(key) == value:
            self.refresh_status()
            return
        self.term[key] = value
        self.changed.emit()
        self.refresh_status()

    def _save_inputs(self) -> None:
        try:
            inputs = [
                {"parameters": parameters, "upper": float(limit.text())}
                for parameters, check, limit in self._rows
                if check.isChecked()
            ]
        except ValueError:
            self.status.setText(tr("ui.workspace_objective.invalid_upper"))
            return
        self._set("inputs", inputs)
