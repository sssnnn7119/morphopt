"""Schema-driven property editor (center pane of the workbench).

``fields_for_node`` decides which parameter fields / code slots belong to each
tree-node kind (surface / component / material / geometry / solver / ...);
``PropertyEditor`` renders those fields into editable widgets and keeps them in
sync with the node's typed fields. Geometry symmetry constraints belong to the
geometry updater editor.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..application.editing import rename_node, set_node_field
from ..application.fields import fields_for_node
from ..i18n import tr
from ..model.problem import Node
from ..presentation.labels import display_choice, node_title, reference_choice_title
from ..refresh import RefreshContext
from ..theme import theme_manager
from .codeeditor import CodeEditor
from .collection_controls import ActionButton
from .param_form import ParamForm


class PropertyEditor(QWidget):
    """Renders the field list of one node into editable widgets."""

    changed = Signal(object)  # Node that changed
    activated = Signal(object)  # Node whose controls received keyboard focus

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self._compact = compact
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        # Visibility is set before insertion into the layout. Give the label
        # its owner now so it can never appear as a temporary top-level window.
        self._title = QLabel("—", self)
        self._title.setProperty("textRole", "sectionHeading")
        self._title.setVisible(not compact)
        if not compact:
            outer.addWidget(self._title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        if compact:
            self._scroll.setFrameShape(QFrame.Shape.NoFrame)
            self._scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self._scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        self._body = QWidget()
        self._form = QFormLayout(self._body)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setContentsMargins(
            *deepcopy(theme_manager.palette.layout.widgets.form_contents_margins)
        )
        self._form.setVerticalSpacing(
            theme_manager.palette.layout.widgets.standard_form_spacing
        )
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll, 0 if compact else 1)

        self._node: Node | None = None
        self._schema = None
        self._parameter_form: ParamForm | None = None
        self._completion_problem = None
        self._controls: dict[str, QWidget] = {}
        self._code_controls: dict[str, CodeEditor] = {}
        self._dof_groups: dict[str, list[QCheckBox]] = {}
        self._name_edit: QLineEdit | None = None

    # ------------------------------------------------------------- content
    def edit_node(
        self,
        node: Node,
        fields=None,
        code_slots=None,
        extra_choices=None,
        subtitle: str = "",
        title: str | None = None,
        completion_problem=None,
        actions: list[tuple[str, Callable[[], None], bool]] | None = None,
    ) -> None:
        self._completion_problem = completion_problem
        title = title if title is not None else node_title(completion_problem, node)
        if fields is None:
            fields, code_slots, extra_choices = fields_for_node(
                node, completion_problem
            )
        code_slots, extra_choices = code_slots or {}, extra_choices or {}
        helper_names = (
            [item.name for item in completion_problem.helper_variables]
            if completion_problem
            else []
        )
        schema = tuple((field.key, field.type) for field in fields), tuple(code_slots)
        if (
            node is self._node
            and schema == self._schema
            and self._parameter_form is not None
        ):
            self._title.setText(title)
            self._parameter_form.helper_names = set(helper_names)
            self._parameter_form.refresh_choices(extra_choices)
            self._parameter_form.refresh_values()
            if self._name_edit is not None and not self._name_edit.hasFocus():
                if self._name_edit.text() != node.name:
                    self._name_edit.setText(node.name)
            return
        self._schema = schema
        self._node = node
        self._controls.clear()
        self._code_controls.clear()
        self._dof_groups.clear()
        self._name_edit = None
        # clear form (remove all rows)
        while self._form.rowCount():
            self._form.removeRow(0)

        self._title.setText(title)
        if node.kind in {"fea_component", "part", "material", "instance"}:
            name_edit = QLineEdit(node.name or "")
            self._name_edit = name_edit
            name_edit.setToolTip(
                tr("ui.widgets.editor.component_name")
                if node.kind == "fea_component"
                else (
                    tr(
                        "ui.widgets.editor.registration_name_in_geometryparams_geometry_updaters_are_retargeted"
                    )
                    if node.kind == "part"
                    else tr(
                        "ui.widgets.editor.unique_assembly_name_of_this_part_instance"
                    )
                )
            )
            if node.kind == "material":
                name_edit.setToolTip(
                    tr(
                        "ui.widgets.editor.registration_name_in_materialsparams_material_updaters_are_retargeted"
                    )
                )
            name_edit.editingFinished.connect(
                lambda e=name_edit: self._rename_node(e.text())
            )
            self._form.addRow(
                (
                    tr("ui.widgets.editor.component_name")
                    if node.kind == "fea_component"
                    else tr("ui.widgets.editor.part_name")
                    if node.kind == "part"
                    else tr("ui.widgets.editor.material_name")
                    if node.kind == "material"
                    else tr("ui.widgets.editor.instance_name")
                ),
                name_edit,
            )
        if subtitle:
            lbl = QLabel(subtitle)
            lbl.setWordWrap(True)
            lbl.setProperty("textRole", "muted")
            self._form.addRow(lbl)

        if actions:
            action_row = QWidget()
            action_grid_columns = (
                theme_manager.palette.layout.widgets.action_grid_columns
            )
            if len(actions) > action_grid_columns:
                action_layout = QGridLayout(action_row)
                action_layout.setContentsMargins(
                    0,
                    theme_manager.palette.layout.widgets.action_row_vertical_margin,
                    0,
                    theme_manager.palette.layout.widgets.action_row_vertical_margin,
                )
                action_layout.setHorizontalSpacing(
                    theme_manager.palette.layout.widgets.action_grid_spacing
                )
                action_layout.setVerticalSpacing(
                    theme_manager.palette.layout.widgets.action_grid_spacing
                )
                for column in range(
                    theme_manager.palette.layout.widgets.action_grid_columns
                ):
                    action_layout.setColumnStretch(column, 1)
            else:
                action_layout = QHBoxLayout(action_row)
                action_layout.setContentsMargins(
                    0,
                    theme_manager.palette.layout.widgets.action_row_vertical_margin,
                    0,
                    theme_manager.palette.layout.widgets.action_row_vertical_margin,
                )
                action_layout.setSpacing(
                    theme_manager.palette.layout.widgets.action_grid_spacing
                )
            for index, (label, callback, danger) in enumerate(actions):
                button = ActionButton(label, callback, danger=danger)
                if (
                    len(actions)
                    > theme_manager.palette.layout.widgets.action_grid_columns
                ):
                    columns = theme_manager.palette.layout.widgets.action_grid_columns
                    action_layout.addWidget(button, index // columns, index % columns)
                else:
                    action_layout.addWidget(button)
            if len(actions) <= theme_manager.palette.layout.widgets.action_grid_columns:
                action_layout.addStretch(1)
            self._form.addRow(action_row)

        form = ParamForm(
            None,
            fields,
            extra_choices,
            helper_names=helper_names,
            read=node.get_field,
            write=lambda key, value: set_node_field(
                node, key, value, self._completion_problem
            ),
            choice_label=self._choice_label,
        )
        form.changed.connect(lambda _key: self.changed.emit(node))
        self._parameter_form = form
        self._controls = form.controls
        self._dof_groups = form.dof_groups
        self._form.addRow(form)
        for key, caption in code_slots.items():
            self._add_code_slot(key, caption)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)
        if self._compact:
            self._body.adjustSize()
            self._scroll.setMinimumHeight(self._body.layout().sizeHint().height() + 8)

    def refresh_ui(self, context: RefreshContext) -> None:
        if self._node is not None:
            self.edit_node(self._node, completion_problem=context.problem)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn and self._node is not None:
            self.activated.emit(self._node)
        return super().eventFilter(watched, event)

    def refresh_choices(self) -> None:
        if self._node is not None and self._parameter_form is not None:
            _, _, choices = fields_for_node(self._node, self._completion_problem)
            self._parameter_form.refresh_choices(choices)

    def _rename_node(self, text: str) -> None:
        if self._node is None:
            return
        renamed = rename_node(self._node, text, self._completion_problem)
        if self._name_edit is not None:
            # Rejected or whitespace-only edits must not leave the form
            # displaying a name that differs from the referenced object.
            self._name_edit.setText(self._node.name)
        if renamed:
            self._title.setText(node_title(self._completion_problem, self._node))
            self.changed.emit(self._node)

    def _choice_label(self, key: str, value: object) -> str:
        return reference_choice_title(
            self._completion_problem, key, value
        ) or display_choice(key, value)

    def _add_code_slot(self, key: str, caption: str) -> None:
        node = self._node
        editor = CodeEditor(
            caption,
            completion_context=key,
            completion_problem=self._completion_problem,
        )
        editor.set_body(str(node.get_field(key, "") or ""))
        editor.edit.textChanged.connect(lambda: self._sync_code(key, editor))
        self._code_controls[key] = editor
        self._form.addRow(editor)

    # -------------------------------------------------------------- helpers

    def _sync_code(self, key: str, editor: CodeEditor) -> None:
        if self._node is None:
            return
        self._node.set_field(key, editor.body())
        self.changed.emit(self._node)
