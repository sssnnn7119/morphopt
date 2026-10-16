"""Parameter picker for inserting composable ObjectiveFunction code snippets."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox,
    QVBoxLayout,
)

from ..i18n import tr
from ..application.fields import SnippetInputs
from ..model.problem import ProblemDefinition
from ..presentation.labels import reference_choice_title
from ..schemes.snippets import CodeSnippet, SnippetParameter
from .values import combo_value


class TemplateInsertDialog(QDialog):
    """Collect model-backed parameters before inserting one code template."""

    def __init__(self, snippet: CodeSnippet, problem: ProblemDefinition,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr('ui.widgets.template_insert_dialog.insert_code_snippet'))
        self.inputs = SnippetInputs(problem)
        self._snippet = snippet
        self._fields: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr(snippet.name_key)))
        if snippet.key.startswith("jacobian_"):
            hint = QLabel(tr('ui.widgets.template_insert_dialog.before_using_this_template_make_sure_the_concentrated_force_and_moment_a'))
            hint.setWordWrap(True)
            hint.setProperty("textRole", "warning")
            layout.addWidget(hint)
        form = QFormLayout()

        for parameter in snippet.parameters:
            combo = self._parameter_combo(parameter)
            self._fields[parameter.key] = combo
            form.addRow(tr(parameter.label_key), combo)
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
        for parameter in self._snippet.parameters:
            if parameter.source in self.inputs.editable and combo_value(self._fields[parameter.key]) == "":
                self._show_validation_error(tr(
                    "ui.widgets.template_insert_dialog.select_parameter",
                    name=tr(parameter.label_key),
                ))
                return
        if (self._snippet.key.startswith("jacobian_")
                and not self._validate_jacobian_reference_point()):
            return
        self.accept()

    def _validate_jacobian_reference_point(self) -> bool:
        issue = self.inputs.jacobian_issue(self.parameter_values())
        return self._show_validation_error(tr(issue)) if issue else True

    def _show_validation_error(self, message: str) -> bool:
        QMessageBox.warning(self, tr('ui.widgets.template_insert_dialog.inconsistent_parameters'), message)
        return False

    def parameter_values(self) -> dict[str, object]:
        """Return the values currently selected (or typed) by the user."""
        return {key: combo_value(combo) for key, combo in self._fields.items()}

    def _parameter_combo(self, parameter: SnippetParameter) -> QComboBox:
        options = self._options(parameter.source)
        combo = QComboBox()
        is_customizable = parameter.source in self.inputs.editable
        combo.setEditable(is_customizable)
        if is_customizable:
            combo.addItem("", "")
        for label, value in options:
            combo.addItem(label, value)

        default = parameter.default
        if is_customizable:
            combo.setCurrentIndex(0)
        elif combo.count():
            index = combo.findData(default)
            combo.setCurrentIndex(index if index >= 0 else 0)
        else:
            combo.addItem(str(default), default)
        return combo

    def _options(self, source: str) -> list[tuple[str, object]]:
        captions = {
            "load_steps": lambda value: tr('ui.widgets.template_insert_dialog.load_step_value', value_0=value),
            "axis": lambda value: tr('ui.widgets.template_insert_dialog.x_value', value_0=value),
            "translation_axis": lambda value: tr(
                'ui.widgets.template_insert_dialog.translation_x_value',
                value_0=value,
            ),
            "rotation_axis": lambda value: tr(
                'ui.widgets.template_insert_dialog.rotation_value_value',
                value_0=("Rx", "Ry", "Rz")[value-3],
                value_1=value,
            ),
            "six_component": lambda value: f"{tr(f'ui.snippet.component.{value}')} ({value})",
        }
        references = {
            "instances": "instance_name",
            "reference_points": "rp_name",
            "force_loads": "force_load_name",
            "moment_loads": "moment_load_name",
        }
        caption = captions.get(source) or (
            lambda value: reference_choice_title(self.inputs.problem, references.get(source, ""), value) or str(value)
        )
        return [(caption(value), value) for value in self.inputs.values(source)]
