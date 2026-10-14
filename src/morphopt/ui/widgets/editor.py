"""Schema-driven property editor (center pane of the workbench).

``fields_for_node`` decides which parameter fields / code slots belong to each
tree-node kind (surface / interface / material / geometry / solver / ...);
``PropertyEditor`` renders those fields into editable widgets and keeps them in
sync with the node's typed fields. Geometry symmetry constraints belong to the
geometry updater editor.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..model.problem import Node
from .codeeditor import CodeEditor
from ..application.fields import fields_for_node
from ..application.editing import set_node_field, rename_node
from .param_form import ParamForm


class PropertyEditor(QWidget):
    """Renders the field list of one node into editable widgets."""

    changed = Signal(object)  # Node that changed

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self._compact = compact
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel("—")
        self._title.setStyleSheet("font-size:14px; font-weight:600; color:#e0e0e0;")
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
        self._form.setContentsMargins(8, 4, 8, 4)
        self._form.setVerticalSpacing(6)
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll, 0 if compact else 1)

        self._node: Node | None = None
        self._schema = None
        self._parameter_form: ParamForm | None = None
        self._completion_problem = None
        self._controls: dict[str, QWidget] = {}
        self._code_controls: dict[str, CodeEditor] = {}
        self._dof_groups: dict[str, list[QCheckBox]] = {}

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
        if fields is None:
            fields, code_slots, extra_choices = fields_for_node(node, completion_problem)
        code_slots, extra_choices = code_slots or {}, extra_choices or {}
        helper_names = [item.name for item in completion_problem.helper_variables] if completion_problem else []
        schema = tuple((field["key"], field["type"]) for field in fields), tuple(code_slots)
        if node is self._node and schema == self._schema and self._parameter_form is not None:
            self._title.setText(title if title is not None else (node.name or node.kind))
            self._parameter_form.helper_names = set(helper_names)
            self._parameter_form.refresh_choices(extra_choices)
            return
        self._schema = schema
        self._node = node
        self._controls.clear()
        self._code_controls.clear()
        self._dof_groups.clear()
        # clear form (remove all rows)
        while self._form.rowCount():
            self._form.removeRow(0)

        self._title.setText(title if title is not None else (node.name or node.kind))
        if node.kind in {"interface", "part_interface", "material", "instance"}:
            name_edit = QLineEdit(node.name or "")
            name_edit.setToolTip(
                (tr('ui.widgets.editor.load_name_the_step_matrix_jacobian_needed_hold_object_references_and_fol') if node.kind == "interface" else (tr('ui.widgets.editor.registration_name_in_geometryparams_geometry_updaters_are_retargeted') if node.kind == "part_interface" else tr('ui.widgets.editor.unique_assembly_name_of_this_part_instance')))
            )
            if node.kind == "material":
                name_edit.setToolTip(
                    tr('ui.widgets.editor.registration_name_in_materialsparams_material_updaters_are_retargeted')
                )
            name_edit.editingFinished.connect(
                lambda e=name_edit: self._rename_node(e.text())
            )
            self._form.addRow(
                (
                    tr('ui.widgets.editor.load_name')
                    if node.kind == "interface"
                    else tr('ui.widgets.editor.geometry_interface_name')
                    if node.kind == "part_interface"
                    else tr('ui.widgets.editor.material_interface_name')
                    if node.kind == "material"
                    else tr('ui.widgets.editor.instance_name')
                ),
                name_edit,
            )
        if subtitle:
            lbl = QLabel(subtitle)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#7f8c8d; font-size:11px;")
            self._form.addRow(lbl)

        if actions:
            action_row = QWidget()
            if len(actions) > 2:
                action_layout = QGridLayout(action_row)
                action_layout.setContentsMargins(0, 2, 0, 2)
                action_layout.setHorizontalSpacing(6)
                action_layout.setVerticalSpacing(6)
                for column in range(2):
                    action_layout.setColumnStretch(column, 1)
            else:
                action_layout = QHBoxLayout(action_row)
                action_layout.setContentsMargins(0, 2, 0, 2)
                action_layout.setSpacing(6)
            for index, (label, callback, danger) in enumerate(actions):
                button = QPushButton(label)
                button.setMinimumHeight(32)
                button.setStyleSheet(
                    "QPushButton { background:#9d3434; color:white; padding:5px 9px; "
                    "border:1px solid #b45151; border-radius:4px; } "
                    "QPushButton:hover { background:#b84646; }"
                    if danger
                    else "QPushButton { background:#27374c; color:#edf3fa; "
                    "padding:5px 9px; border:1px solid #40536b; border-radius:4px; } "
                    "QPushButton:hover { background:#354b65; }"
                )
                button.clicked.connect(
                    lambda _checked=False, action=callback: action()
                )
                if len(actions) > 2:
                    action_layout.addWidget(button, index // 2, index % 2)
                else:
                    action_layout.addWidget(button)
            if len(actions) <= 2:
                action_layout.addStretch(1)
            self._form.addRow(action_row)

        form = ParamForm(None, fields, extra_choices, helper_names=helper_names,
                         read=node.get_field,
                         write=lambda key, value: set_node_field(node, key, value, self._completion_problem))
        form.changed.connect(lambda _key: self.changed.emit(node))
        self._parameter_form = form
        self._controls = form.controls
        self._dof_groups = form.dof_groups
        self._form.addRow(form)
        for key, caption in code_slots.items():
            self._add_code_slot(key, caption)
        if self._compact:
            self._body.adjustSize()
            self._scroll.setMinimumHeight(
                self._body.layout().sizeHint().height() + 8
            )

    def _rename_node(self, text: str) -> None:
        if self._node is not None and rename_node(self._node, text, self._completion_problem):
            self._title.setText(self._node.name)
            self.changed.emit(self._node)

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
