"""Custom subclass navigation and body-of-method override editing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from ..codegen.custom_classes import (
    class_catalog,
    class_path_for_node,
    compatible_custom_classes,
    framework_class_catalog,
)
from ..i18n import tr
from ..refresh import RefreshContext
from ..presentation.labels import node_title, typed_title
from ..application.editing import CustomClassSession
from ..model.problem import CustomClassNode, MethodOverrideNode, Node, ProblemDefinition
from .codeeditor import CodeEditor
from .collection_controls import ActionButton, AddButton, CollectionHeader

if TYPE_CHECKING:
    from .definition_actions import DefinitionActions


class CustomClassOverview(QWidget):
    """Manage reusable classes from their root model-tree collection."""
    nodeSelected = Signal(object)

    def __init__(self, actions: DefinitionActions, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.actions = actions
        layout = QVBoxLayout(self)
        header = CollectionHeader(tr('ui.widgets.model_tree.container.custom_classes'), actions.add_custom_class)
        self.remove_button = ActionButton(tr('ui.common.delete'), self._remove)
        header.actions.addWidget(self.remove_button)
        layout.addWidget(header)
        hint = QLabel(tr('ui.widgets.custom_classes.overview_hint'), self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.items = QListWidget(self)
        self.items.currentItemChanged.connect(self._selection_changed)
        self.items.itemActivated.connect(self._activate)
        layout.addWidget(self.items)
        self.remove_button.setEnabled(False)

    def set_problem(self, problem: ProblemDefinition) -> None:
        selected = self.items.currentRow()
        self.items.clear()
        for custom in problem.custom_classes:
            item = QListWidgetItem(node_title(problem, custom))
            item.setData(Qt.ItemDataRole.UserRole, custom)
            item.setToolTip(custom.base_class)
            self.items.addItem(item)
        self.items.setCurrentRow(min(selected, self.items.count() - 1))

    def refresh_ui(self, context: RefreshContext) -> None:
        self.set_problem(context.problem)

    def _selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self.remove_button.setEnabled(current is not None)

    def _activate(self, item: QListWidgetItem) -> None:
        self.nodeSelected.emit(item.data(Qt.ItemDataRole.UserRole))

    def _remove(self) -> None:
        item = self.items.currentItem()
        if item is not None:
            self.actions.remove_custom_class(item.data(Qt.ItemDataRole.UserRole))


class CustomClassEditor(QWidget):
    changed = Signal(object)
    nodeSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._custom = None
        self._problem = None
        self._methods = {}
        self.current_method: MethodOverrideNode | None = None
        self._loading = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._rename)
        self.base = QLabel()
        self.base.setWordWrap(True)
        form.addRow(tr('ui.widgets.custom_classes.class_name'), self.name)
        form.addRow(tr('ui.widgets.custom_classes.inherits_from'), self.base)
        layout.addLayout(form)
        hint = QLabel(tr('ui.widgets.custom_classes.edit_the_body_signatures_follow_the_framework_base_super_calls_framework'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.signature = QLabel()
        self.signature.setWordWrap(True)
        self.signature.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.signature, 1)
        self.add_button = AddButton(self.add_override)
        self.add_button.setToolTip(tr('ui.widgets.custom_classes.override_method'))
        row.addWidget(self.add_button)
        self.remove_button = ActionButton(
            tr('ui.common.delete'), self._remove_override, danger=True,
            tooltip=tr('ui.widgets.custom_classes.remove_override'),
        )
        row.addWidget(self.remove_button)
        layout.addLayout(row)
        self.code = CodeEditor(tr('ui.widgets.custom_classes.method_body'))
        self.code.edit.textChanged.connect(self._save_body)
        layout.addWidget(self.code, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#e57373;")
        layout.addWidget(self.error)

    def edit_node(self, node, problem):
        custom = node if isinstance(node, CustomClassNode) else next(
            (custom for custom in problem.custom_classes if node in custom.children), None)
        if custom is None:
            return
        previous = self.current_method if custom is self._custom else None
        self._custom = custom
        self._problem = problem
        self.session = CustomClassSession(problem)
        self._loading = True
        self.name.setText(custom.name)
        self.base.setText(custom.base_class)
        self.error.clear()
        try:
            spec = framework_class_catalog(problem).get(custom.base_class)
            self._methods = spec.methods if spec else {}
            if spec is not None:
                self.base.setText(spec.path)
            if spec is None:
                self.error.setText(tr('ui.widgets.custom_classes.base_class_missing_recreate_the_subclass'))
        except Exception as exc:
            self._methods = {}
            self.error.setText(str(exc))
        self.add_button.setEnabled(bool(self._methods))
        focus = node if isinstance(node, MethodOverrideNode) else previous
        self.current_method = focus if focus in custom.children else next(iter(custom.children), None)
        self._loading = False
        self._show_method()

    def refresh_ui(self, context: RefreshContext) -> None:
        node = self.current_method or self._custom
        if node is not None:
            self.edit_node(node, context.problem)

    def _show_method(self, *_):
        if self._loading:
            return
        override = self.current_method
        spec = self._methods.get(override.name) if override else None
        self.signature.setText(spec.header if spec else "")
        self.signature.setToolTip(spec.documentation if spec else "")
        self.code.setEnabled(override is not None)
        self.remove_button.setEnabled(override is not None)
        self._loading = True
        self.code.set_body(override.body if override else "")
        self.code.set_completion_context(override.name if override else "", self._problem)
        self._loading = False
        self._validate_body()

    def add_override(self):
        taken = {method.name for method in self._custom.children}
        methods = [method for name, method in sorted(self._methods.items()) if name not in taken]
        if not methods:
            return
        choices = [f"{method.name}{method.signature}" for method in methods]
        text, ok = QInputDialog.getItem(self, tr('ui.widgets.custom_classes.override_method_411bc8b9'),
                                       tr('ui.widgets.custom_classes.choose_a_method_to_override'), choices, 0, False)
        if not ok:
            return
        spec = methods[choices.index(text)]
        override = self.session.add_override(self._custom, spec)
        self.current_method = override
        self._show_method()
        self.changed.emit(self._custom)
        self.nodeSelected.emit(override)

    def _remove_override(self):
        override = self.current_method
        if override:
            self.session.remove(override)
            self.current_method = next(iter(self._custom.children), None)
            self.error.clear()
            self._show_method()
            self.changed.emit(self._custom)
            self.nodeSelected.emit(self._custom)

    def _save_body(self):
        if self._loading:
            return
        override = self.current_method
        if override:
            override.body = self.code.body()
            self._validate_body()
            self.changed.emit(self._custom)

    def _validate_body(self):
        override = self.current_method
        spec = self._methods.get(override.name) if override else None
        if spec is None:
            return
        try:
            self.session.validate_body(override, spec)
        except SyntaxError as exc:
            self.error.setText(tr(
                'ui.widgets.custom_classes.syntax_error_body_line_value_value',
                value_0=max(1, (exc.lineno or 2) - 1),
                value_1=exc.msg,
            ))
        else:
            self.error.clear()

    def _rename(self):
        if self._custom is None:
            return
        value = self.name.text().strip()
        try:
            changed = self.session.rename(self._custom, value)
        except ValueError as exc:
            self.error.setText(str(exc))
            self.name.setText(self._custom.name)
            return
        if changed:
            self.changed.emit(self._custom)


class ModelClassSelector(QWidget):
    """Explicit custom-class choice shared by all model editor pages."""

    changed = Signal()

    def __init__(self, parent=None, title=""):
        super().__init__(parent)
        self._title = title
        self._problem = None
        self._path = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._save)
        layout.addWidget(self.label)
        layout.addWidget(self.combo, 1)
        self.apply_language()
        self.hide()

    def apply_language(self):
        self.label.setText((self._title + " " if self._title else "") + tr('ui.widgets.custom_classes.use_class'))
        self.combo.setToolTip(tr('ui.widgets.custom_classes.choose_a_compatible_module_level_custom_class_or_the_framework_default'))

    def edit_node(self, node, problem):
        self._problem = problem
        self._path = class_path_for_node(node)
        self.combo.blockSignals(True)
        self.combo.clear()
        try:
            targets = class_catalog(problem) if self._path else {}
            target = targets.get(self._path)
            if target is not None:
                self.combo.addItem(typed_title(tr("ui.naming.default"), target.base_expression.rsplit(".", 1)[-1]), "")
                for custom in compatible_custom_classes(problem, target):
                    self.combo.addItem(typed_title(custom.name, custom.base_class.rsplit(".", 1)[-1]), custom.name)
                selected = problem.class_bindings.get(self._path, "")
                if selected and self.combo.findData(selected) < 0:
                    self.combo.addItem(typed_title(tr("ui.naming.unavailable"), selected), selected)
                self.combo.setCurrentIndex(max(0, self.combo.findData(selected)))
                self.show()
            else:
                self.hide()
        except Exception as exc:
            self.combo.addItem(str(exc), "")
            self.show()
        finally:
            self.combo.blockSignals(False)

    def refresh_ui(self, context: RefreshContext) -> None:
        self.edit_node(context.selected, context.problem)

    def _save(self, *_):
        if self._problem is None or not self._path:
            return
        value = self.combo.currentData()
        if value:
            self._problem.class_bindings[self._path] = value
        else:
            self._problem.class_bindings.pop(self._path, None)
        self.changed.emit()
