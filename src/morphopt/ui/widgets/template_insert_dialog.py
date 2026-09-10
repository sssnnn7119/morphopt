"""Parameter picker for inserting composable ObjectiveFunction code snippets."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox,
    QVBoxLayout,
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
        self._snippet = snippet
        self._fields: dict[str, QComboBox] = {}
        self._field_sources: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(T(snippet.name_zh, snippet.name_en)))
        if snippet.key.startswith("jacobian_"):
            hint = QLabel(T(
                "使用前请确认：集中力和集中力矩施加在同一个末端参考点，"
                "参考点下拉框用于定位该参考点在 GC 中的自由度，"
                "并且对应载荷已在目标函数面板中手动勾选 Jacobian。",
                "Before using this template, make sure the concentrated force "
                "and moment act at the same end reference point. The selected "
                "reference point locates its GC rows; manually check both "
                "loads for Jacobian computation in the objective panel."))
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#d6a85f;")
            layout.addWidget(hint)
        form = QFormLayout()

        for parameter in snippet.parameters:
            combo = self._parameter_combo(parameter)
            self._fields[parameter.key] = combo
            self._field_sources[parameter.key] = parameter.source
            form.addRow(T(parameter.label, parameter.label_en), combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        """Validate load/reference-point consistency before insertion."""
        if (self._snippet.key.startswith("jacobian_")
                and not self._validate_jacobian_reference_point()):
            return
        self.accept()

    def _validate_jacobian_reference_point(self) -> bool:
        values = self.parameter_values()
        reference_name = str(values.get("reference_point_name", "")).strip()
        force_name = str(values.get("force_load_name", "")).strip()
        moment_name = str(values.get("moment_load_name", "")).strip()

        interfaces = self._problem.interfaces()
        reference_exists = any(
            interface.interface_type == "ReferencePoint"
            and interface.name == reference_name
            for interface in interfaces
        )
        force = next(
            (interface for interface in interfaces
             if interface.interface_type == "ConcentratedForce"
             and interface.name == force_name),
            None,
        )
        moment = next(
            (interface for interface in interfaces
             if interface.interface_type == "ConcentratedMoment"
             and interface.name == moment_name),
            None,
        )

        if not reference_exists or force is None or moment is None:
            return self._show_validation_error(T(
                "雅可比模板必须选择当前模型中已定义的参考点、集中力和集中力矩。",
                "The Jacobian template requires a reference point, force, and "
                "moment that are defined in the current model."))

        if (force.rp_name != reference_name
                or moment.rp_name != reference_name
                or force.rp_name != moment.rp_name):
            return self._show_validation_error(T(
                "集中力、集中力矩和所选参考点必须完全一致，当前选择不能插入。",
                "The concentrated force, concentrated moment, and selected "
                "reference point must match exactly; this template cannot be "
                "inserted."))
        return True

    def _show_validation_error(self, message: str) -> bool:
        QMessageBox.warning(self, T("参数不一致", "Inconsistent parameters"), message)
        return False

    def parameter_values(self) -> dict[str, Any]:
        """Return the values currently selected (or typed) by the user."""
        values: dict[str, Any] = {}
        for key, combo in self._fields.items():
            # Editable model-name combos may retain the previous item's data
            # role after the user types a new name; always trust their text.
            source = self._field_sources[key]
            value = combo.currentData()
            values[key] = (combo.currentText()
                           if value is None or self._is_customizable(source)
                           else value)
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
        if source == "force_loads":
            return [
                (interface.name, interface.name)
                for interface in self._problem.interfaces()
                if interface.interface_type == "ConcentratedForce" and interface.name
            ]
        if source == "moment_loads":
            return [
                (interface.name, interface.name)
                for interface in self._problem.interfaces()
                if interface.interface_type == "ConcentratedMoment" and interface.name
            ]
        if source == "axis":
            return [
                (T(f"X（{index}）", f"X ({index})"), index)
                for index in range(3)
            ]
        if source == "translation_axis":
            return [
                (T(f"平移 X（{index}）", f"Translation X ({index})"), index)
                for index in range(3)
            ]
        if source == "rotation_axis":
            return [
                (T(f"旋转 {label}（{index}）",
                   f"Rotation {label} ({index})"), index)
                for index, label in enumerate(("Rx", "Ry", "Rz"), start=3)
            ]
        if source == "six_component":
            labels = (
                ("力/位移 X", "Fx / Ux"), ("力/位移 Y", "Fy / Uy"),
                ("力/位移 Z", "Fz / Uz"), ("力矩/转角 X", "Mx / Rx"),
                ("力矩/转角 Y", "My / Ry"), ("力矩/转角 Z", "Mz / Rz"),
            )
            return [(T(f"{zh}（{index}）", f"{en} ({index})"), index)
                    for index, (zh, en) in enumerate(labels)]
        raise ValueError(f"Unknown template parameter source: {source!r}")

    @staticmethod
    def _is_customizable(source: str) -> bool:
        """Allow custom FEA names not representable in a *.morph definition."""
        return source in {
            "instances", "reference_points", "elements",
            "force_loads", "moment_loads",
        }
