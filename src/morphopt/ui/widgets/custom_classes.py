"""Custom subclass navigation and body-of-method override editing."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..codegen.custom_classes import (
    class_catalog, class_path_for_node, compatible_custom_classes,
    framework_class_catalog, validate_custom_name,
)
from ..i18n import T
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
        self.title.setText(T("自定义类（进阶）", "Custom classes (advanced)"))
        self.add_button.setToolTip(T("添加自定义类", "Add custom class"))
        self.rebuild()

    def set_problem(self, problem):
        self._problem = problem
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
            catalog = framework_class_catalog(self._problem)
        except Exception as exc:
            QMessageBox.warning(self, T("无法读取父类", "Cannot read base classes"), str(exc))
            return
        available = sorted(catalog)
        if not available:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(T("添加自定义类", "Add custom class"))
        layout = QFormLayout(dialog)
        name = QLineEdit("CustomClass")
        base = QComboBox()
        base.addItems(available)
        base.setMinimumWidth(400)
        layout.addRow(T("类名", "Class name"), name)
        layout.addRow(T("继承自", "Inherits from"), base)
        hint = QLabel(T("自定义类定义在脚本顶层。创建后，在模型节点的“使用类”中选择它。",
                        "Custom classes are module-level definitions. Select one using a model node's class selector."))
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(buttons)
        buttons.rejected.connect(dialog.reject)

        def accept():
            value = name.text().strip()
            try:
                validate_custom_name(value, catalog)
                if any(node.name == value for node in self._problem.custom_classes):
                    raise ValueError(T("类名已存在。", "Class name already exists."))
            except ValueError as exc:
                QMessageBox.warning(dialog, T("类名无效", "Invalid class name"), str(exc))
                return
            dialog.accept()

        buttons.accepted.connect(accept)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        custom = CustomClassNode(name=name.text().strip(), params={"base_class": base.currentText()})
        self._problem.custom_classes.append(custom)
        self.rebuild(select=custom)
        self.treeChanged.emit()
        self.nodeSelected.emit(custom)

    def _menu(self, position):
        item = self.tree.itemAt(position)
        menu = QMenu(self)
        menu.addAction(T("添加自定义类", "Add custom class"), self.add_class)
        if item:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(node, CustomClassNode):
                menu.addAction(T("重写方法…", "Override method…"),
                               lambda: self.overrideRequested.emit(node))
            menu.addAction(T("删除", "Delete"), lambda: self._remove(node))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _remove(self, node):
        selected = None
        if isinstance(node, CustomClassNode):
            self._problem.custom_classes.remove(node)
            self._problem.class_bindings = {path: name for path, name in self._problem.class_bindings.items()
                                            if name != node.name}
            for item in self._problem.root.iter_nodes():
                if item.custom_class == node.name:
                    item.custom_class = ""
            if self._problem.updater:
                for config in self._problem.updater.geometry + self._problem.updater.materials:
                    for key in ("objective_functions", "constraints"):
                        for item in config.get(key, []):
                            if item.get("custom_class") == node.name:
                                item.pop("custom_class", None)
        else:
            for custom in self._problem.custom_classes:
                if node in custom.children:
                    custom.remove_child(node)
                    selected = custom
                    break
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
        form.addRow(T("类名", "Class name"), self.name)
        form.addRow(T("继承自", "Inherits from"), self.base)
        layout.addLayout(form)
        hint = QLabel(T("只编辑方法体；签名沿用框架父类，super() 调用框架方法。重写声明方法会替代相应 UI 生成的方法。",
                        "Edit the body; signatures follow the framework base. super() calls framework methods. Overridden declaration hooks replace generated methods."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.signature = QLabel()
        self.signature.setWordWrap(True)
        self.signature.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.signature, 1)
        self.add_button = QPushButton(T("重写方法…", "Override method…"))
        self.add_button.setStyleSheet("padding:3px 10px;")
        self.add_button.clicked.connect(self.add_override)
        row.addWidget(self.add_button)
        self.remove_button = QPushButton(T("删除重写", "Remove override"))
        self.remove_button.setStyleSheet("padding:3px 10px;")
        self.remove_button.clicked.connect(self._remove_override)
        row.addWidget(self.remove_button)
        layout.addLayout(row)
        self.code = CodeEditor(T("方法体", "Method body"))
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
                self.error.setText(T("父类已不存在，请重新创建自定义类。", "Base class missing; recreate the subclass."))
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
        text, ok = QInputDialog.getItem(self, T("重写方法", "Override method"),
                                       T("选择要重写的方法：", "Choose a method to override:"), choices, 0, False)
        if not ok:
            return
        spec = methods[choices.index(text)]
        override = MethodOverrideNode(name=spec.name, params={"body": spec.body})
        self._custom.add_child(override)
        self.current_method = override
        self._show_method()
        self.changed.emit(self._custom)
        self.nodeSelected.emit(override)

    def _remove_override(self):
        override = self.current_method
        if override:
            self._custom.remove_child(override)
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
        source = spec.header + "\n" + "\n".join(
            "    " + line for line in (override.body if override.body.strip() else "pass").splitlines())
        try:
            compile(source, "<method body>", "exec")
        except SyntaxError as exc:
            self.error.setText(T(f"语法错误（方法体第 {max(1, (exc.lineno or 2) - 1)} 行）：{exc.msg}",
                                 f"Syntax error (body line {max(1, (exc.lineno or 2) - 1)}): {exc.msg}"))
        else:
            self.error.clear()

    def _rename(self):
        if self._custom is None:
            return
        value = self.name.text().strip()
        try:
            catalog = framework_class_catalog(self._problem)
            validate_custom_name(value, catalog)
            if any(
                other is not self._custom and other.name == value
                for other in self._problem.custom_classes
            ):
                raise ValueError(T("类名已存在。", "Class name already exists."))
        except ValueError as exc:
            self.error.setText(str(exc))
            self.name.setText(self._custom.name)
            return
        if value != self._custom.name:
            old_name = self._custom.name
            self._custom.name = value
            self._problem.class_bindings = {path: value if name == old_name else name
                                            for path, name in self._problem.class_bindings.items()}
            for item in self._problem.root.iter_nodes():
                if item.custom_class == old_name:
                    item.custom_class = value
            if self._problem.updater:
                for config in self._problem.updater.geometry + self._problem.updater.materials:
                    for key in ("objective_functions", "constraints"):
                        for item in config.get(key, []):
                            if item.get("custom_class") == old_name:
                                item["custom_class"] = value
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
        self.label.setText((self._title + " " if self._title else "") + T("使用类", "Use class"))
        self.combo.setToolTip(T("选择兼容的顶层自定义类；默认使用框架类。",
                               "Choose a compatible module-level custom class, or the framework default."))

    def edit_node(self, node, problem):
        self._problem = problem
        self._path = class_path_for_node(node)
        self.combo.blockSignals(True)
        self.combo.clear()
        try:
            targets = class_catalog(problem) if self._path else {}
            target = targets.get(self._path)
            if target is not None:
                self.combo.addItem(T("默认：", "Default: ") + target.base_expression, "")
                for custom in compatible_custom_classes(problem, target):
                    self.combo.addItem(custom.name, custom.name)
                selected = problem.class_bindings.get(self._path, "")
                if selected and self.combo.findData(selected) < 0:
                    self.combo.addItem(T("不可用：", "Unavailable: ") + selected, selected)
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
