"""Editable Objective-Function panel.

Shown when the ``objective`` node is selected in the workbench.  The two
hand-written methods ``objective_function(self)`` / ``get_metrics(self)`` of the
generated ``ObjectiveFunction`` are edited here (body only, the ``def`` line is
added by the code generator).  ``jacobian_needed`` is the list of parameterised
load names whose Jacobians are requested.  The whole problem is (re)generated read-only in
the workbench's "代码 (只读)" tab; editing the canonical ``*.morph`` and re-
exporting the ``.py`` is the recommended workflow.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QComboBox, QPushButton,
    QHBoxLayout, QToolButton, QMenu, QWidgetAction, QCheckBox,
)

from ..model.problem import ObjectiveNode, ProblemDefinition
from ..schemes.base import get_template
from .codeeditor import CodeEditor
from .template_insert_dialog import TemplateInsertDialog
from ..i18n import tr


class JacobianLoadSelector(QToolButton):
    """Compact multi-select menu for the loads whose Jacobians are needed.

    A Jacobian is only meaningful for an interface with an amplitude entry in
    the load-step matrix.  The editor supplies precisely that list, keeping
    this widget presentation-only and avoiding a second schema lookup here.
    """

    selectionChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load_names: list[str] = []
        self._checks: dict[str, QCheckBox] = {}
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._update_summary()

    def set_loads(self, load_names: list[str], selected_names: list[str]) -> None:
        """Replace the available loads and mark the persisted selection."""
        self._load_names = list(dict.fromkeys(name for name in load_names if name))
        selected = set(selected_names)
        self._menu.clear()
        self._checks.clear()

        for name in self._load_names:
            check = QCheckBox(name, self._menu)
            check.setChecked(name in selected)
            check.toggled.connect(self._selection_changed)
            action = QWidgetAction(self._menu)
            action.setDefaultWidget(check)
            self._menu.addAction(action)
            self._checks[name] = check

        self.setEnabled(bool(self._load_names))
        self._update_summary()

    def selected_names(self) -> list[str]:
        """Return selected loads in their stable load-step-matrix order."""
        return [name for name in self._load_names if self._checks[name].isChecked()]

    def _selection_changed(self) -> None:
        self._update_summary()
        self.selectionChanged.emit()

    def _update_summary(self) -> None:
        selected = self.selected_names()
        if not self._load_names:
            self.setText(tr('ui.widgets.objective_editor.no_parameterized_loads'))
            self.setToolTip(tr('ui.widgets.objective_editor.add_a_load_with_an_amplitude_first'))
            return
        if not selected:
            self.setText(tr('ui.widgets.objective_editor.none_selected'))
            self.setToolTip(tr('ui.widgets.objective_editor.select_loads_requiring_jacobians'))
            return
        self.setText(tr(
            'ui.widgets.objective_editor.value_value_selected',
            value_0=len(selected),
            value_1=len(self._load_names),
        ))
        self.setToolTip(", ".join(selected))


class ObjectiveEditor(QWidget):
    changed = Signal(object)   # objective Node

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        head = QLabel(tr('ui.widgets.objective_editor.objective_function_edit_in_ide_recommended'))
        head.setStyleSheet("font-weight:600; color:#e0e0e0;")
        lay.addWidget(head)

        form = QFormLayout()
        # composable FEA code-snippet chooser
        tbar = QHBoxLayout()
        self.tpl_combo = QComboBox()
        self.btn_apply = QPushButton(tr('ui.widgets.objective_editor.insert_snippet'))
        self.btn_apply.clicked.connect(self._insert_template)
        tbar.addWidget(self.tpl_combo, 1)
        tbar.addWidget(self.btn_apply)
        form.addRow(tr('ui.widgets.objective_editor.template'), tbar)

        self.jacobian_loads = JacobianLoadSelector()
        self.jacobian_loads.selectionChanged.connect(self._save_jacobian)
        form.addRow(tr('ui.widgets.objective_editor.jacobian_needed'), self.jacobian_loads)
        self.jacobian_hint = QLabel(tr('ui.widgets.objective_editor.stiffness_templates_do_not_select_loads_automatically_add_a_concentrated'))
        self.jacobian_hint.setWordWrap(True)
        self.jacobian_hint.setStyleSheet("color:#9aa4b2;")
        form.addRow("", self.jacobian_hint)

        lay.addLayout(form)

        self.obj_editor = CodeEditor(tr('ui.widgets.objective_editor.objective_function_body_define_the_objective_function'),
            completion_context="_objective_function")
        self.obj_editor.focusReceived.connect(
            lambda: self._set_active_editor(self.obj_editor))
        self.obj_editor.edit.textChanged.connect(lambda: self._save_slot("_objective_function", self.obj_editor))
        lay.addWidget(self.obj_editor, 1)

        self.met_editor = CodeEditor(tr('ui.widgets.objective_editor.get_metrics_body_return_a_list_displayed_in_the_morphopt_ui_metrics_bar'),
            completion_context="_get_metrics")
        self.met_editor.focusReceived.connect(
            lambda: self._set_active_editor(self.met_editor))
        self.met_editor.edit.textChanged.connect(lambda: self._save_slot("_get_metrics", self.met_editor))
        lay.addWidget(self.met_editor, 1)

        self._obj: ObjectiveNode | None = None
        self._problem: ProblemDefinition | None = None
        self._active_editor: CodeEditor | None = None
        self._loading = False

    # ------------------------------------------------------------------ api
    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self._obj = problem.objective
        self.obj_editor.set_completion_context("_objective_function", problem)
        self.met_editor.set_completion_context("_get_metrics", problem)
        self._loading = True
        try:
            # composable FEA snippet list
            self.tpl_combo.clear()
            for snippet in get_template(problem.scheme).objective_code_snippets():
                self.tpl_combo.addItem(tr(snippet.name_key), snippet)
            self.tpl_combo.setCurrentIndex(0 if self.tpl_combo.count() else -1)
            if self._obj is not None:
                self.jacobian_loads.set_loads(
                    [interface.name for interface in problem.amplitude_interfaces()],
                    [interface.name for interface in self._obj.jacobian_needed],
                )
                self.obj_editor.set_body(str(self._obj.get_field("_objective_function", "")))
                self.met_editor.set_body(str(self._obj.get_field("_get_metrics", "")))
            else:
                self.jacobian_loads.set_loads([], [])
                self.obj_editor.set_body("")
                self.met_editor.set_body("")
        finally:
            self._loading = False

    # ------------------------------------------------------------- handlers

    def _set_active_editor(self, editor: CodeEditor) -> None:
        """Remember the slot containing the cursor before opening a dialog."""
        self._active_editor = editor

    def _save_jacobian(self) -> None:
        if self._loading:
            return
        nd = self._obj
        if nd is None:
            return
        if self._problem is not None:
            self._problem.set_jacobian_interfaces(
                self.jacobian_loads.selected_names()
            )
        self.changed.emit(nd)

    def _save_slot(self, key: str, editor: CodeEditor) -> None:
        if not self._loading and self._obj is not None:
            self._obj.set_field(key, editor.body())
            self.changed.emit(self._obj)

    def _insert_template(self) -> None:
        """Prompt for parameters, then insert one template at the chosen slot."""
        idx = self.tpl_combo.currentIndex()
        if idx < 0 or self._problem is None:
            return
        snippet = self.tpl_combo.itemData(idx)
        if snippet is None:
            return
        dialog = TemplateInsertDialog(snippet, self._problem, self)
        if not dialog.exec():
            return
        values = dialog.parameter_values()
        source = snippet.render(values)
        editor = self._active_editor or self.obj_editor
        editor.insert_snippet(source, at_cursor=self._active_editor is not None)
