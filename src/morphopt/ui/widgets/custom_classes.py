"""New-class methods and framework-method overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QGroupBox, QInputDialog, QLabel, QLineEdit, QMenu, QScrollArea,
    QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from ..theme import theme_manager
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
from ..model.problem import (
    CustomClassNode, CustomFunctionNode, MethodOverrideNode, Node, ProblemDefinition,
)
from .codeeditor import CodeEditor
from .collection_controls import ActionButton, CollectionHeader, ItemActions

if TYPE_CHECKING:
    from .definition_actions import DefinitionActions


class CustomClassOverview(QWidget):
    """Manage reusable classes from their root model-tree collection."""
    nodeSelected = Signal(object)

    def __init__(self, actions: DefinitionActions, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.actions = actions
        layout = QVBoxLayout(self)
        self.add_menu = QMenu(self)
        header = CollectionHeader(
            tr('ui.widgets.model_tree.container.custom_classes'), menu=self.add_menu
        )
        self.title_label = header.title
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
        self._mode: str | None = None

    def set_problem(self, problem: ProblemDefinition, node=None) -> None:
        if node is not None:
            self._mode = {
                "new_classes_group": "new",
                "override_classes_group": "override",
            }.get(node.kind)
        title_key = {
            "new": "ui.widgets.model_tree.container.new_classes_group",
            "override": "ui.widgets.model_tree.container.override_classes_group",
        }.get(self._mode, "ui.widgets.model_tree.container.custom_classes")
        self.title_label.setText(tr(title_key))
        self.add_menu.clear()
        choices = (
            [("new", "ui.widgets.custom_classes.add_new_class")]
            if self._mode == "new"
            else [("override", "ui.widgets.custom_classes.add_override_class")]
            if self._mode == "override"
            else [
                ("new", "ui.widgets.custom_classes.add_new_class"),
                ("override", "ui.widgets.custom_classes.add_override_class"),
            ]
        )
        for class_type, label_key in choices:
            action = self.add_menu.addAction(tr(label_key))
            action.triggered.connect(
                lambda _checked=False, class_type=class_type:
                    self.actions.add_custom_class(class_type)
            )
        selected = self.items.currentRow()
        self.items.clear()
        for custom in problem.custom_classes:
            if self._mode == "new" and custom.class_type != "new":
                continue
            if self._mode == "override" and custom.class_type != "override":
                continue
            item = QListWidgetItem(node_title(problem, custom))
            item.setData(Qt.ItemDataRole.UserRole, custom)
            item.setToolTip(custom.base_class or "object")
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
        self.current_method: MethodOverrideNode | CustomFunctionNode | None = None
        self._loading = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._rename)
        self.base_label = QLabel(tr('ui.widgets.custom_classes.inherits_from'))
        self.base = QLabel()
        self.base.setWordWrap(True)
        class_card = QGroupBox(tr('ui.widgets.custom_classes.class_definition'))
        form.addRow(tr('ui.widgets.custom_classes.class_name'), self.name)
        form.addRow(self.base_label, self.base)
        class_layout = QVBoxLayout(class_card)
        class_layout.addLayout(form)
        layout.addWidget(class_card)
        self.hint = QLabel()
        hint = self.hint
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.method_header = CollectionHeader(
            tr('ui.widgets.custom_classes.methods'), self._add_member
        )
        self.add_button = self.method_header.add_button
        layout.addWidget(self.method_header)

        self.method_scroll = QScrollArea(self)
        self.method_scroll.setWidgetResizable(True)
        self.method_container = QWidget(self.method_scroll)
        self.method_list = QVBoxLayout(self.method_container)
        self.method_list.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.method_list.setSpacing(theme_manager.palette.layout.widgets.collection_spacing)
        self.method_list.addStretch(1)
        self.method_scroll.setWidget(self.method_container)
        layout.addWidget(self.method_scroll, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setProperty("textRole", "error")
        layout.addWidget(self.error)

    def edit_node(self, node, problem):
        custom = node if isinstance(node, CustomClassNode) else next(
            (custom for custom in problem.custom_classes if node in custom.members), None)
        if custom is None:
            return
        previous = self.current_method if custom is self._custom else None
        self._custom = custom
        self._problem = problem
        self.session = CustomClassSession(problem)
        self._loading = True
        self.name.setText(custom.name)
        self.base.setText(custom.base_class or "object")
        self.error.clear()
        if custom.class_type == "override":
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
            self.base_label.show()
            self.base.show()
            self.hint.setText(tr('ui.widgets.custom_classes.override_class_hint'))
            self.method_header.title.setText(tr('ui.widgets.custom_classes.method_overrides'))
            self.add_button.setText(tr('ui.widgets.custom_classes.override_method'))
            self.add_button.setEnabled(bool(self._methods))
        else:
            self._methods = {}
            self.base_label.hide()
            self.base.hide()
            self.hint.setText(tr('ui.widgets.custom_classes.new_class_hint'))
            self.method_header.title.setText(tr('ui.widgets.custom_classes.methods'))
            self.add_button.setText(tr('ui.common.add'))
            self.add_button.setEnabled(True)
        focus = node if isinstance(node, (MethodOverrideNode, CustomFunctionNode)) else previous
        self.current_method = focus if focus in custom.members else next(iter(custom.members), None)
        self._loading = False
        self._render_methods()

    def refresh_ui(self, context: RefreshContext) -> None:
        focus = QApplication.focusWidget()
        if focus is not None and self.isAncestorOf(focus):
            return
        node = self.current_method or self._custom
        if node is not None:
            self.edit_node(node, context.problem)

    def _render_methods(self):
        while self.method_list.count() > 1:
            item = self.method_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if self._custom is None:
            return
        members = list(self._custom.members)
        self._member_cards = {}
        for index, member in enumerate(members):
            spec = self._methods.get(member.name) if isinstance(member, MethodOverrideNode) else None
            title = spec.header if spec is not None else f"{member.name}({getattr(member, 'parameters', '')})"
            card = QGroupBox(title, self.method_container)
            card.setToolTip(spec.documentation if spec is not None else "")
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(ItemActions(
                index,
                len(members),
                lambda member=member: self._remove_member(member),
                lambda delta, member=member: self._move_member(member, delta),
                remove_tooltip=tr('ui.widgets.custom_classes.remove_method'),
            ))
            if isinstance(member, CustomFunctionNode):
                signature = QFormLayout()
                method_name = QLineEdit(member.name, card)
                parameters = QLineEdit(member.parameters, card)
                method_name.editingFinished.connect(
                    lambda member=member, field=method_name:
                        self._save_function_signature(member, field, None)
                )
                parameters.editingFinished.connect(
                    lambda member=member, field=parameters:
                        self._save_function_signature(member, None, field)
                )
                signature.addRow(tr('ui.widgets.custom_classes.function_name'), method_name)
                signature.addRow(tr('ui.widgets.custom_classes.parameters'), parameters)
                card_layout.addLayout(signature)
            code = CodeEditor(tr('ui.widgets.custom_classes.method_body'))
            code.set_body(member.body)
            code.set_completion_context(member.name, self._problem)
            code.edit.textChanged.connect(
                lambda member=member, code=code: self._save_member_body(member, code)
            )
            card_layout.addWidget(code, 1)
            self.method_list.insertWidget(index, card)
            self._member_cards[member] = card
        if self.current_method in self._member_cards:
            self.method_scroll.ensureWidgetVisible(self._member_cards[self.current_method])

    def _add_member(self):
        if self._custom is None:
            return
        if self._custom.class_type == "override":
            self.add_override()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('ui.widgets.custom_classes.add_function'))
        layout = QFormLayout(dialog)
        taken = {member.name for member in self._custom.members}
        index = 1
        while f"method_{index}" in taken:
            index += 1
        name = QLineEdit(f"method_{index}", dialog)
        parameters = QLineEdit("self", dialog)
        layout.addRow(tr('ui.widgets.custom_classes.function_name'), name)
        layout.addRow(tr('ui.widgets.custom_classes.parameters'), parameters)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        layout.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        temporary = CustomFunctionNode(
            name=name.text().strip(),
            params={"parameters": parameters.text().strip(), "body": "pass"},
        )
        try:
            if any(member.name == temporary.name for member in self._custom.members):
                raise ValueError(tr('ui.widgets.custom_classes.duplicate_function_name'))
            self.session.validate_function(temporary)
        except (SyntaxError, ValueError) as exc:
            self.error.setText(str(exc))
            return
        self.current_method = self.session.add_function(
            self._custom, temporary.name, temporary.parameters
        )
        self._render_methods()
        self.changed.emit(self._custom)
        self.nodeSelected.emit(self.current_method)

    def add_member(self):
        """Add one method using the editor's class-specific method policy."""
        self._add_member()

    def add_override(self):
        taken = {method.name for method in self._custom.members}
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
        self._render_methods()
        self.changed.emit(self._custom)
        self.nodeSelected.emit(override)

    def _remove_member(self, member):
        if self._custom is None:
            return
        self.session.remove(member)
        self.current_method = next(iter(self._custom.members), None)
        self.error.clear()
        self._render_methods()
        self.changed.emit(self._custom)
        self.nodeSelected.emit(self.current_method or self._custom)

    def _move_member(self, member, delta):
        if self._custom and self.session.move_member(self._custom, member, delta):
            self.current_method = member
            self._render_methods()
            self.changed.emit(self._custom)
            self.nodeSelected.emit(member)

    def _save_member_body(self, member, code):
        if self._loading:
            return
        member.body = code.body()
        try:
            if isinstance(member, MethodOverrideNode):
                spec = self._methods[member.name]
                self.session.validate_body(member, spec)
            else:
                self.session.validate_function(member)
        except SyntaxError as exc:
            self.error.setText(tr(
                'ui.widgets.custom_classes.syntax_error_body_line_value_value',
                value_0=max(1, (exc.lineno or 2) - 1),
                value_1=exc.msg,
            ))
        except ValueError as exc:
            self.error.setText(str(exc))
        else:
            self.error.clear()
        self.changed.emit(self._custom)

    def _save_function_signature(self, member, name_field, parameters_field):
        previous_name = member.name
        previous_parameters = member.parameters
        if name_field is not None:
            member.name = name_field.text().strip()
        if parameters_field is not None:
            member.parameters = parameters_field.text().strip()
        try:
            if any(other is not member and other.name == member.name for other in self._custom.members):
                raise ValueError(tr('ui.widgets.custom_classes.duplicate_function_name'))
            self.session.validate_function(member)
        except (SyntaxError, ValueError) as exc:
            member.name = previous_name
            member.parameters = previous_parameters
            if name_field is not None:
                name_field.setText(previous_name)
            if parameters_field is not None:
                parameters_field.setText(previous_parameters)
            self.error.setText(str(exc))
            return
        self.error.clear()
        self._render_methods()
        self.changed.emit(self._custom)

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
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
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
