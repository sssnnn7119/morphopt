"""Parameter picker for inserting composable ObjectiveFunction code snippets."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout,
)

from ..i18n import T
from ..model.problem import ProblemDefinition
from ..schemes.snippets import CodeSnippet, SnippetParameter


class TemplateInsertDialog(QDialog):
    """Collect model-backed parameters before inserting one code template."""

    def __init__(self, snippet: CodeSnippet, problem: ProblemDefinition,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(T("插入代码片段", "Insert code snippet"))
        self._problem = problem
        self._fields: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(T(snippet.name_zh, snippet.name_en)))
        form = QFormLayout()

        for parameter in snippet.parameters:
            combo = self._parameter_combo(parameter)
            self._fields[parameter.key] = combo
            form.addRow(T(parameter.label, parameter.label_en), combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def parameter_values(self) -> dict[str, Any]:
        """Return the values currently selected (or typed) by the user."""
        values: dict[str, Any] = {}
        for key, combo in self._fields.items():
            value = combo.currentData()
            values[key] = combo.currentText() if value is None else value
        return values

    def _parameter_combo(self, parameter: SnippetParameter) -> QComboBox:
        options = self._options(parameter.source)
        combo = QComboBox()
        is_customizable = self._is_customizable(parameter.source)
        combo.setEditable(is_customizable)
        for label, value in options:
            combo.addItem(label, value)

        default = parameter.default
        index = combo.findData(default)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif is_customizable:
            combo.setEditText(str(default))
        elif combo.count() == 0:
            combo.addItem(str(default), default)
        return combo

    def _options(self, source: str) -> list[tuple[str, Any]]:
        if source == "load_steps":
            count = self._problem.steps.num_steps if self._problem.steps else 1
            return [(T(f"工况 {index}", f"Load step {index}"), index)
                    for index in range(count)]
        if source == "instances":
            return [(name, name) for name in self._problem.instance_names()]
        if source == "reference_points":
            return [(name, name) for name in self._problem.reference_point_names()]
        if source == "elements":
            return [(name, name) for name in self._problem.element_names()]
        if source == "axis":
            return [(label, index) for index, label in enumerate((
                "X (0)", "Y (1)", "Z (2)",
            ))]
        if source == "six_component":
            return [(label, index) for index, label in enumerate((
                "Fx / Ux (0)", "Fy / Uy (1)", "Fz / Uz (2)",
                "Mx / Rx (3)", "My / Ry (4)", "Mz / Rz (5)",
            ))]
        raise ValueError(f"Unknown template parameter source: {source!r}")

    @staticmethod
    def _is_customizable(source: str) -> bool:
        """Allow custom FEA names not representable in a *.morph definition."""
        return source in {"instances", "reference_points", "elements"}
