"""Custom subclass navigation and body-of-method override editing."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..codegen.custom_classes import (
    class_catalog,
    class_path_for_node,
    compatible_custom_classes,
    framework_class_catalog,
)
from ..i18n import tr
from ..application.editing import CustomClassSession
from ..model.problem import CustomClassNode, MethodOverrideNode
from .codeeditor import CodeEditor


class CustomClassTree(QWidget):
    nodeSelected = Signal(object)
    treeChanged = Signal()
    overrideRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._problem = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.title = QLabel()
        row.addWidget(self.title, 1)
        self.add_button = QPushButton("+")
        self.add_button.setFixedWidth(28)
        self.add_button.setStyleSheet("padding:5px 0px;")
        self.add_button.clicked.connect(self.add_class)
        row.addWidget(self.add_button)
        layout.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._select)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        layout.addWidget(self.tree)
        self.apply_language()

    def apply_language(self):
        self.title.setText(tr('ui.widgets.custom_classes.custom_classes_advanced'))
        self.add_button.setToolTip(tr('ui.widgets.custom_classes.add_custom_class'))
        self.rebuild()

    def set_problem(self, problem):
        self._problem = problem
        self.session = CustomClassSession(problem)
        self.rebuild()

    def rebuild(self, select=None):
        if select is None and self.tree.currentItem() is not None:
            select = self.tree.currentItem().data(0, Qt.ItemDataRole.UserRole)
        self.tree.blockSignals(True)
        self.tree.clear()
        if self._problem:
            for custom in self._problem.custom_classes:
                item = QTreeWidgetItem([f"{custom.name} [{custom.base_class}]"])
                item.setToolTip(0, custom.base_class)
                item.setData(0, Qt.ItemDataRole.UserRole, custom)
                self.tree.addTopLevelItem(item)
                if select is custom:
                    self.tree.setCurrentItem(item)
                for method in custom.children:
                    child = QTreeWidgetItem([f"{method.name}()"])
                    child.setData(0, Qt.ItemDataRole.UserRole, method)
                    item.addChild(child)
                    if select is method:
                        self.tree.setCurrentItem(child)
                item.setExpanded(True)
        self.tree.blockSignals(False)

    def _select(self, current, previous):
        if current:
            self.nodeSelected.emit(current.data(0, Qt.ItemDataRole.UserRole))

    def add_class(self):
        if self._problem is None:
            return
        try:
            catalog = self.session.catalog()
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.widgets.custom_classes.cannot_read_base_classes'), str(exc))
            return
        available = sorted(catalog)
        if not available:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('ui.widgets.custom_classes.add_custom_class'))
        layout = QFormLayout(dialog)
        name = QLineEdit("CustomClass")
        base = QComboBox()
        base.addItems(available)
        base.setMinimumWidth(400)
        layout.addRow(tr('ui.widgets.custom_classes.class_name'), name)
        layout.addRow(tr('ui.widgets.custom_classes.inherits_from'), base)
        hint = QLabel(tr('ui.widgets.custom_classes.custom_classes_are_module_level_definitions_select_one_using_a_model_nod'))
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(buttons)
        buttons.rejected.connect(dialog.reject)

        def accept():
            value = name.text().strip()
            try:
                self.session.validate_name(value)
            except ValueError as exc:
                QMessageBox.warning(dialog, tr('ui.widgets.custom_classes.invalid_class_name'), str(exc))
                return
            dialog.accept()

        buttons.accepted.connect(accept)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        custom = self.session.add_class(name.text().strip(), base.currentText())
        self.rebuild(select=custom)
        self.treeChanged.emit()
        self.nodeSelected.emit(custom)

    def _menu(self, position):
        item = self.tree.itemAt(position)
        menu = QMenu(self)
        menu.addAction(tr('ui.widgets.custom_classes.add_custom_class'), self.add_class)
        if item:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(node, CustomClassNode):
                menu.addAction(tr('ui.widgets.custom_classes.override_method'),
                               lambda: self.overrideRequested.emit(node))
            menu.addAction(tr('ui.widgets.custom_classes.delete'), lambda: self._remove(node))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _remove(self, node):
        selected = self.session.remove(node)
        self.rebuild(select=selected)
        self.treeChanged.emit()
        self.nodeSelected.emit(selected)


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
        self.add_button = QPushButton(tr('ui.widgets.custom_classes.override_method'))
        self.add_button.setStyleSheet("padding:3px 10px;")
        self.add_button.clicked.connect(self.add_override)
        row.addWidget(self.add_button)
        self.remove_button = QPushButton(tr('ui.widgets.custom_classes.remove_override'))
        self.remove_button.setStyleSheet("padding:3px 10px;")
        self.remove_button.clicked.connect(self._remove_override)
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
                self.combo.addItem(tr('ui.widgets.custom_classes.default') + target.base_expression, "")
                for custom in compatible_custom_classes(problem, target):
                    self.combo.addItem(custom.name, custom.name)
                selected = problem.class_bindings.get(self._path, "")
                if selected and self.combo.findData(selected) < 0:
                    self.combo.addItem(tr('ui.widgets.custom_classes.unavailable') + selected, selected)
                self.combo.setCurrentIndex(max(0, self.combo.findData(selected)))
                self.show()
            else:
                self.hide()
        except Exception as exc:
            self.combo.addItem(str(exc), "")
            self.show()
        finally:
            self.combo.blockSignals(False)

    def _save(self, *_):
        if self._problem is None or not self._path:
            return
        value = self.combo.currentData()
        if value:
            self._problem.class_bindings[self._path] = value
        else:
            self._problem.class_bindings.pop(self._path, None)
        self.changed.emit()
