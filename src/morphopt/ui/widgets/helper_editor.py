"""Editors for module-level helper code and individual helper definitions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QMenu, QVBoxLayout, QWidget

from ..theme import theme_manager
from ..application.editing import HelperCodeSession
from ..i18n import tr
from ..model.problem import HelperFunctionNode, HelperVariableNode, Node, ProblemDefinition
from ..refresh import RefreshContext
from .codeeditor import CodeEditor
from .collection_controls import CollectionHeader

if TYPE_CHECKING:
    from .definition_actions import DefinitionActions


class HelperCodeEditor(QWidget):
    """Edit free code, or one helper embedded in its collection's card."""
    changed = Signal(object)
    activated = Signal(object)

    def __init__(self, actions: DefinitionActions, parent: QWidget | None = None, *, embedded: bool = False):
        super().__init__(parent)
        self.actions = actions
        self.embedded = embedded
        self.session: HelperCodeSession | None = None
        self._loading = False
        layout = QVBoxLayout(self)
        self._add_menu = QMenu(self)
        self._variable_action = self._add_menu.addAction(
            "", lambda: actions.add_helper("helper_variable")
        )
        self._function_action = self._add_menu.addAction(
            "", lambda: actions.add_helper("helper_function")
        )
        self.header = CollectionHeader("", menu=self._add_menu)
        layout.addWidget(self.header)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.name, self.value, self.parameters = QLineEdit(), QLineEdit(), QLineEdit()
        self.name_label, self.value_label, self.parameters_label, self.code_label = QLabel(), QLabel(), QLabel(), QLabel()
        for label, edit in ((self.name_label, self.name), (self.value_label, self.value), (self.parameters_label, self.parameters)):
            layout.addWidget(label)
            layout.addWidget(edit)
            edit.editingFinished.connect(self._save)
        layout.addWidget(self.code_label)
        self.code = CodeEditor("Python")
        self.code.edit.textChanged.connect(self._save)
        layout.addWidget(self.code, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setProperty("textRole", "error")
        layout.addWidget(self.error)
        if embedded:
            layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
            self.header.hide()
            self.hint.hide()
            self.code.setMinimumHeight(theme_manager.palette.layout.helper_code_minimum_height)
        for edit in (self.name, self.value, self.parameters, self.code.edit):
            edit.installEventFilter(self)
        self.apply_language()

    def apply_language(self) -> None:
        self.hint.setText(tr('ui.workbench.use_the_free_code_block_for_module_code_variables_have_a_name_and_python'))
        self._variable_action.setText(tr('ui.workbench.add_helper_variable'))
        self._function_action.setText(tr('ui.workbench.add_helper_function'))
        self.header.add_button.setText(tr('ui.common.add'))
        for label, key in ((self.name_label, 'name'), (self.value_label, 'value_python_expression'), (self.parameters_label, 'parameters')):
            label.setText(tr(f'ui.workbench.{key}'))
        self.name.setPlaceholderText(tr('ui.workbench.name'))
        self.value.setPlaceholderText(tr('ui.workbench.value_python_expression'))
        self.parameters.setPlaceholderText(tr('ui.workbench.parameters_e_g_x_scale_1'))

    def edit_node(self, node: Node | None, problem: ProblemDefinition) -> None:
        binding_changed = (
            self.session is None
            or self.session.node is not node
            or self.session.problem is not problem
        )
        self.session = HelperCodeSession(problem, node)
        kind = node.kind if node is not None else "helper_code"
        editable = kind in {"helper_variable", "helper_function"}
        self.header.add_button.setVisible(kind == "helper_code")
        self.header.title.setText(tr('ui.widgets.model_tree.container.helper_code_block' if kind == "helper_code_block" else 'ui.widgets.model_tree.container.helper_code'))
        for label, widget, visible in (
            (self.name_label, self.name, editable),
            (self.value_label, self.value, kind == "helper_variable"),
            (self.parameters_label, self.parameters, kind == "helper_function"),
            (self.code_label, self.code, kind in {"helper_code_block", "helper_function"}),
        ):
            label.setVisible(visible)
            widget.setVisible(visible)
        self.error.setVisible(kind in {"helper_code_block", "helper_variable", "helper_function"})
        self.code_label.setText(tr('ui.workbench.free_code' if kind == "helper_code_block" else 'ui.workbench.function_body'))
        self._loading = True
        try:
            for edit, text in (
                (self.name, node.name if editable else ""),
                (self.value, node.value if isinstance(node, HelperVariableNode) else ""),
                (self.parameters, node.parameters if isinstance(node, HelperFunctionNode) else ""),
            ):
                if (binding_changed or not edit.hasFocus()) and edit.text() != text:
                    with QSignalBlocker(edit):
                        edit.setText(text)
            if binding_changed or not self.code.edit.hasFocus():
                self.code.set_body(problem.helper_code if kind == "helper_code_block" else node.body if isinstance(node, HelperFunctionNode) else "")
        finally:
            self._loading = False
        self._validate()

    def refresh_ui(self, context: RefreshContext) -> None:
        if self.session is not None:
            self.edit_node(self.session.node, context.problem)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FocusIn and self.session is not None and self.session.node is not None:
            self.activated.emit(self.session.node)
        return super().eventFilter(watched, event)

    def _save(self) -> None:
        if self._loading or self.session is None:
            return
        self.session.save(self.name.text(), self.value.text(), self.parameters.text(), self.code.body())
        self._validate()
        self.changed.emit(self.session.node)

    def _validate(self) -> None:
        if self.session is None:
            return
        try:
            self.session.validate()
        except (SyntaxError, ValueError) as exc:
            self.error.setText(tr('ui.workbench.invalid_helper_definition_value', value_0=exc))
        else:
            self.error.clear()
