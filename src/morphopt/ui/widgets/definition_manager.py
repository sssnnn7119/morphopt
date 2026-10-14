"""List-oriented editors for geometry, load, and material interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..model.problem import (
    CADOperationNode,
    InstanceNode,
    InterfaceNode,
    MaterialNode,
    Node,
    PartInterfaceNode,
    ProblemDefinition,
    SurfaceNode,
)
from ..model.schemas import (
    CAD_OPERATION_TYPES,
    INTERFACE_TYPES,
    MATERIAL_TYPES,
    PART_INTERFACE_TYPES,
    SURFACE_TYPES,
)
from .editor import PropertyEditor
from ..application.fields import fields_for_node
from ..application.part_sets import PartSetCatalog
from ..application.editor_routing import managed_nodes
from ..presentation.labels import (
    cad_operation_title_text,
    instance_title_text,
    part_interface_title_text,
    surface_title_text,
)

if TYPE_CHECKING:
    from .definition_actions import DefinitionActions


class DefinitionManagerEditor(QWidget):
    """Edit collection members as cards within their owning definition page."""

    changed = Signal(object)

    def __init__(self, mode: str, actions: DefinitionActions, parent: QWidget | None = None, *, sets: PartSetCatalog | None = None):
        super().__init__(parent)
        self.mode = mode
        self.actions = actions
        self.sets = sets
        self._problem: ProblemDefinition | None = None
        self._structure: tuple[Any, ...] | None = None
        self._focus: Node | None = None
        self._focus_widgets: dict[Node, QWidget] = {}
        self._item_groups: dict[Node, QGroupBox] = {}
        self._child_groups: dict[Node, QGroupBox] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self._heading = QLabel()
        self._heading.setStyleSheet("font-size:14px; font-weight:600; color:#e0e0e0;")
        head.addWidget(self._heading)
        head.addStretch(1)
        self._add_button = QToolButton()
        self._add_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._add_button.setText(tr('ui.widgets.definition_manager.add'))
        self._add_button.setStyleSheet(
            "QToolButton { background:#27374c; color:#edf3fa; padding:6px 12px; "
            "border:1px solid #40536b; border-radius:4px; } "
            "QToolButton:hover { background:#354b65; }"
        )
        self._add_menu = QMenu(self._add_button)
        self._add_button.setMenu(self._add_menu)
        head.addWidget(self._add_button)
        outer.addLayout(head)

        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color:#9aa4b2; font-size:11px;")
        outer.addWidget(self._hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        body = QWidget()
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        self._scroll.setWidget(body)
        outer.addWidget(self._scroll, 1)

    def edit_node(
        self,
        manager: Node | None,
        problem: ProblemDefinition,
        focus: Node | None = None,
    ) -> None:
        self._problem = problem
        self._focus = focus if focus is not manager else None
        self._heading.setText(
            {
                "geometry": tr('ui.widgets.definition_manager.geometry_interfaces'),
                "loads": tr('ui.widgets.definition_manager.load_interfaces'),
                "materials": tr('ui.widgets.definition_manager.material_interfaces'),
            }[self.mode]
        )
        self._hint.setText(
            {
                "geometry": tr('ui.widgets.definition_manager.select_a_part_in_the_model_tree_to_edit_it_edit_instance_placement_bound'),
                "loads": tr('ui.widgets.definition_manager.select_one_load_boundary_condition_reference_point_or_contact_in_the_mod'),
                "materials": tr('ui.widgets.definition_manager.select_a_material_interface_in_the_model_tree_to_edit_its_properties_and'),
            }[self.mode]
        )
        self._refresh_add_menu()
        structure = self._structure_signature()
        if structure != self._structure:
            self._structure = structure
            self._rebuild_cards()
        self._update_titles()
        self._focus_selection()

    def invalidate(self) -> None:
        """Refresh node forms the next time this manager page is selected."""
        self._structure = None

    def _all_items(self) -> list[Node]:
        if self._problem is None:
            return []
        if self.mode == "geometry":
            return list(self._problem.part_interfaces())
        if self.mode == "loads":
            return list(self._problem.interfaces())
        return list(self._problem.material_nodes())

    def _structure_signature(self) -> tuple[Any, ...]:
        items = managed_nodes(self._problem, self.mode, self._focus)
        if self.mode == "geometry":
            return (
                id(self._focus),
                tuple(
                    (id(item), tuple(id(child) for child in item.children))
                    for item in items
                ),
            )
        return id(self._focus), tuple(id(item) for item in items)

    def _refresh_add_menu(self) -> None:
        self._add_menu.clear()
        if self._problem is None:
            return
        from ..schemes.base import get_template

        template = get_template(self._problem.scheme)
        if self.mode == "geometry":
            for interface_type in template.available_geometry_types():
                spec = PART_INTERFACE_TYPES.get(interface_type, {})
                action = self._add_menu.addAction(
                    tr(spec.get("label_key", interface_type))
                )
                action.triggered.connect(
                    lambda _checked=False, kind=interface_type:
                    self.actions.add_part_interface(kind)
                )
            candidates = {
                kind: (
                    "morphopt.BoundaryPartInterface"
                    if spec.get("surfaces")
                    else f"morphopt.{kind}"
                )
                for kind, spec in PART_INTERFACE_TYPES.items()
                if kind in template.available_geometry_types()
            }
            candidates["BasePartInterface"] = "morphopt.BasePartInterface"
            self.actions.custom_add_menu(
                self._add_menu, candidates, self.actions.add_part_interface
            )
        elif self.mode == "loads":
            for interface_type, spec in INTERFACE_TYPES.items():
                action = self._add_menu.addAction(
                    tr(spec.get("label_key", interface_type))
                )
                action.triggered.connect(
                    lambda _checked=False, kind=interface_type:
                    self.actions.add_interface(kind)
                )
            self.actions.custom_add_menu(
                self._add_menu,
                {
                    kind: f"morphopt.FEAParams.{kind}Interface"
                    for kind in INTERFACE_TYPES
                },
                self.actions.add_interface,
            )
        else:
            for material_type, spec in MATERIAL_TYPES.items():
                action = self._add_menu.addAction(
                    tr(spec.get("label_key", material_type))
                )
                action.triggered.connect(
                    lambda _checked=False, kind=material_type:
                    self.actions.add_material(kind)
                )
            self.actions.custom_add_menu(
                self._add_menu,
                {kind: f"morphopt.{kind}" for kind in MATERIAL_TYPES},
                self.actions.add_material,
            )

    def _rebuild_cards(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._focus_widgets.clear()
        self._item_groups.clear()
        self._child_groups.clear()
        items = managed_nodes(self._problem, self.mode, self._focus)
        all_items = self._all_items()
        for node in items:
            index = all_items.index(node)
            if self.mode == "geometry":
                card = self._part_card(node, index, len(all_items))
            else:
                card = self._simple_card(node, index, len(all_items))
            self._layout.addWidget(card)
        if not items:
            message = (
                tr('ui.widgets.definition_manager.select_a_part_load_or_material_in_the_model_tree_to_edit_it')
                if all_items
                else tr('ui.widgets.definition_manager.no_items_have_been_added')
            )
            self._layout.addWidget(
                QLabel(message)
            )
        self._layout.addStretch(1)

    def _part_card(self, node: Node, index: int, count: int) -> QGroupBox:
        assert isinstance(node, PartInterfaceNode)
        group = QGroupBox(part_interface_title_text(node))
        self._item_groups[node] = group
        self._focus_widgets[node] = group
        col = QVBoxLayout(group)
        self._add_order_controls(
            col,
            node,
            index,
            count,
            lambda item=node: self.actions.remove_part_interface(item),
            lambda item=node, delta=-1: self.actions.move_part_interface(item, delta),
            tr('ui.widgets.definition_manager.delete_geometry_interface'),
        )
        if node.interface_type == "TorchFEAPartInterface":
            from .torchfea_model_editor import TorchFEAModelEditor

            col.addWidget(
                self._node_editor(
                    node, exclude_fields={"model_directory", "model_filename"}
                )
            )
            model_editor = TorchFEAModelEditor(group, embedded=True)
            model_editor.edit_node(node, self._problem)
            model_editor.changed.connect(self.changed.emit)
            col.addWidget(model_editor)
        else:
            col.addWidget(self._node_editor(node))

        col.addWidget(
            self._child_collection(
                tr('ui.widgets.definition_manager.instances'),
                node.instances(),
                add=lambda owner=node: self.actions.add_instance(owner),
                remove=lambda child: self.actions.remove_instance(child),
                move=lambda child, delta: self.actions.move_instance(child, delta),
                title_fn=instance_title_text,
                edit_all=True,
            )
        )
        if node.has_surfaces:
            col.addWidget(
                self._child_collection(
                    tr('ui.widgets.definition_manager.boundary_surfaces'),
                    node.surfaces(),
                    add_menu=self._surface_add_menu(node),
                    remove=lambda child: self.actions.remove_surface(child),
                    move=lambda child, delta: self.actions.move_surface(child, delta),
                    title_fn=lambda child: surface_title_text(
                        child, node.surfaces().index(child)
                    ),
                    edit_all=True,
                )
            )
        if node.interface_type == "CADPartInterface":
            self._add_cad_collection(col, node)
        return group

    def _simple_card(self, node: Node, index: int, count: int) -> QGroupBox:
        group = QGroupBox(self._item_title(node))
        self._item_groups[node] = group
        self._focus_widgets[node] = group
        col = QVBoxLayout(group)
        if isinstance(node, InterfaceNode):
            remove = lambda item=node: self.actions.remove_interface(item)
            move = lambda item=node, delta=-1: self.actions.move_interface(item, delta)
            delete_title = tr('ui.widgets.definition_manager.delete_load_interface')
        else:
            remove = lambda item=node: self.actions.remove_material(item)
            move = lambda item=node, delta=-1: self.actions.move_material(item, delta)
            delete_title = tr('ui.widgets.definition_manager.delete_material')
        self._add_order_controls(col, node, index, count, remove, move, delete_title)
        col.addWidget(self._node_editor(node))
        return group

    def _child_collection(
        self,
        title: str,
        children: list[Node],
        *,
        add=None,
        remove,
        move,
        title_fn,
        add_menu: QMenu | None = None,
        edit_all: bool = False,
    ) -> QGroupBox:
        group = QGroupBox(title)
        col = QVBoxLayout(group)
        if add is not None or add_menu is not None:
            add_button = QPushButton(tr('ui.widgets.definition_manager.add'))
            add_button.setMaximumWidth(112)
            if add_menu is not None:
                add_button.setMenu(add_menu)
            else:
                add_button.clicked.connect(
                    lambda _checked=False, callback=add: callback()
                )
            col.addWidget(add_button, 0, Qt.AlignmentFlag.AlignLeft)
        for index, child in enumerate(children):
            card = QGroupBox(title_fn(child))
            self._child_groups[child] = card
            self._focus_widgets[child] = card
            item_col = QVBoxLayout(card)
            self._add_order_controls(
                item_col,
                child,
                index,
                len(children),
                lambda item=child: remove(item),
                (
                    lambda item=child, delta=-1: move(item, delta)
                    if move is not None
                    else None
                ),
                tr('ui.widgets.definition_manager.delete'),
                allow_move=move is not None,
            )
            if edit_all or child is self._focus:
                item_col.addWidget(self._node_editor(child))
            col.addWidget(card)
        return group

    def _surface_add_menu(self, owner: PartInterfaceNode) -> QMenu:
        menu = QMenu(self)
        for surface_type, spec in SURFACE_TYPES.items():
            action = menu.addAction(
                tr(spec.get("label_key", surface_type))
            )
            action.triggered.connect(
                lambda _checked=False, kind=surface_type, part=owner:
                self.actions.add_surface(kind, part)
            )
        candidates = {
            kind: "morphopt.BoundaryPartInterface."
            + (spec["factory"].split(".")[0] if spec["factory"] else "FixedSurface")
            for kind, spec in SURFACE_TYPES.items()
        }
        self.actions.custom_add_menu(
            menu,
            candidates,
            lambda kind, custom: self.actions.add_surface(kind, owner, custom),
        )
        return menu

    def _add_cad_collection(
        self, parent_layout: QVBoxLayout, owner: PartInterfaceNode
    ) -> None:
        group = QGroupBox(tr('ui.widgets.definition_manager.cad_feature_history'))
        col = QVBoxLayout(group)
        add_row = QHBoxLayout()
        for feature_group, label in (
            ("primitive", tr('ui.widgets.definition_manager.primitive')),
            ("boolean", tr('ui.widgets.definition_manager.boolean')),
            ("transform", tr('ui.widgets.definition_manager.transform')),
            ("import", tr('ui.widgets.definition_manager.step')),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, kind=feature_group, part=owner:
                self.actions.add_cad_operation_group(kind, part)
            )
            add_row.addWidget(button)
        add_row.addStretch(1)
        col.addLayout(add_row)

        operations = owner.cad_operations()
        for index, operation in enumerate(operations):
            card = QGroupBox(cad_operation_title_text(operation))
            self._child_groups[operation] = card
            self._focus_widgets[operation] = card
            item_col = QVBoxLayout(card)
            self._add_order_controls(
                item_col,
                operation,
                index,
                len(operations),
                lambda item=operation: self.actions.remove_cad_operation(item),
                lambda item=operation, delta=-1:
                self.actions.move_cad_operation(item, delta),
                tr('ui.widgets.definition_manager.delete_cad_operation'),
            )
            item_col.addWidget(self._node_editor(operation))
            col.addWidget(card)
        parent_layout.addWidget(group)

    def _node_editor(
        self, node: Node, *, exclude_fields: set[str] | None = None
    ) -> PropertyEditor:
        fields, code_slots, choices = fields_for_node(node, self._problem, sets=self.sets)
        if exclude_fields:
            fields = [field for field in fields if field["key"] not in exclude_fields]
        editor = PropertyEditor(compact=True)
        title = self._item_title(node)
        editor.edit_node(
            node,
            fields=fields,
            code_slots=code_slots,
            extra_choices=choices,
            title=title,
            completion_problem=self._problem,
        )
        editor.changed.connect(self.changed.emit)
        return editor

    def _add_order_controls(
        self,
        layout: QVBoxLayout,
        node: Node,
        index: int,
        count: int,
        remove,
        move,
        remove_title: str,
        *,
        allow_move: bool = True,
    ) -> None:
        bar = QHBoxLayout()
        if allow_move:
            up = self._tool_button("↑", tr('ui.widgets.definition_manager.move_up'), lambda: move(node, -1))
            down = self._tool_button("↓", tr('ui.widgets.definition_manager.move_down'), lambda: move(node, 1))
            up.setEnabled(index > 0)
            down.setEnabled(index + 1 < count)
            bar.addWidget(up)
            bar.addWidget(down)
        bar.addStretch(1)
        delete = self._tool_button(
            tr('ui.widgets.definition_manager.delete'), remove_title, remove, danger=True
        )
        cannot_remove_last = isinstance(
            node, (PartInterfaceNode, MaterialNode, InstanceNode)
        ) and count <= 1
        if isinstance(node, SurfaceNode) and self._problem is not None:
            cannot_remove_last = len(self._problem.surfaces()) <= 1
        if cannot_remove_last:
            delete.setEnabled(False)
        bar.addWidget(delete)
        layout.addLayout(bar)

    @staticmethod
    def _tool_button(label: str, tooltip: str, callback, *, danger=False) -> QToolButton:
        button = QToolButton()
        button.setText(label)
        button.setToolTip(tooltip)
        button.setStyleSheet(
            "QToolButton { color:#f5f7fa; background:#8e3434; padding:3px 7px; "
            "border-radius:3px; } QToolButton:hover { background:#b44242; }"
            if danger
            else "QToolButton { color:#d4deea; background:#27374c; padding:3px 7px; "
            "border-radius:3px; } QToolButton:hover { background:#354b65; }"
        )
        button.clicked.connect(lambda _checked=False, action=callback: action())
        return button

    @staticmethod
    def _item_title(node: Node) -> str:
        if isinstance(node, PartInterfaceNode):
            return part_interface_title_text(node)
        if isinstance(node, InterfaceNode):
            interface_type = node.interface_type
            spec = INTERFACE_TYPES.get(interface_type, {})
            return f"{node.name} · {tr(spec.get('label_key', interface_type))}"
        if isinstance(node, MaterialNode):
            material_type = node.material_type
            spec = MATERIAL_TYPES.get(material_type, {})
            return f"{node.name} · {tr(spec.get('label_key', material_type))}"
        if isinstance(node, InstanceNode):
            return instance_title_text(node)
        if isinstance(node, SurfaceNode):
            return surface_title_text(node, 0)
        if isinstance(node, CADOperationNode):
            return cad_operation_title_text(node)
        return node.name or node.kind

    def _update_titles(self) -> None:
        for node, group in self._item_groups.items():
            group.setTitle(self._item_title(node))
        for node, group in self._child_groups.items():
            if isinstance(node, SurfaceNode) and self._problem is not None:
                owner = self._problem.owner_of_surface(node)
                index = owner.surfaces().index(node) if owner is not None else 0
                group.setTitle(surface_title_text(node, index))
            else:
                group.setTitle(self._item_title(node))

    def _focus_selection(self) -> None:
        for node, widget in self._focus_widgets.items():
            focused = node is self._focus
            widget.setStyleSheet(
                "QGroupBox { border:1px solid #397ac2; margin-top:8px; }"
                if focused
                else ""
            )
        target = self._focus_widgets.get(self._focus) if self._focus is not None else None
        if target is not None:
            QTimer.singleShot(
                0,
                lambda item=target: self._scroll.ensureWidgetVisible(item, 10, 10),
            )

