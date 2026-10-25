"""Collection editors for geometry, loads, materials and helper definitions."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..application.cad import export_cad_step
from ..application.editor_routing import managed_nodes
from ..application.fields import fields_for_node
from ..application.part_sets import PartSetCatalog
from ..i18n import tr
from ..model.node_types.parts import BoundaryPartNode, CADPartNode
from ..model.problem import (
    CADOperationNode,
    FEAComponentNode,
    InstanceNode,
    MaterialNode,
    Node,
    PartNode,
    ProblemDefinition,
)
from ..model.registry import (
    LOAD_TYPES,
    MATERIAL_TYPES,
    PART_TYPES,
    SURFACE_TYPES,
)
from ..presentation.labels import (
    cad_operation_summary_text,
    component_update_description,
    instance_title_text,
    node_title,
    node_type_title,
)
from ..refresh import RefreshContext
from ..theme import theme_manager
from .collection_controls import (
    ActionButton,
    CollectionHeader,
    ItemActions,
    set_card_selected,
)
from .editor import PropertyEditor
from .file_dialogs import choose_save_file
from .helper_editor import HelperCodeEditor
from .part_set_list import PartSetList

if TYPE_CHECKING:
    from .definition_actions import DefinitionActions


class DefinitionManagerEditor(QWidget):
    """Edit collection members as cards within their owning definition page."""

    changed = Signal(object)
    activated = Signal(object)
    partSetSelected = Signal(object, str, str)

    def __init__(
        self,
        mode: str,
        actions: DefinitionActions,
        parent: QWidget | None = None,
        *,
        sets: PartSetCatalog | None = None,
    ):
        super().__init__(parent)
        self.mode = mode
        self.actions = actions
        self.sets = sets
        self._problem: ProblemDefinition | None = None
        self._structure: tuple[Any, ...] | None = None
        self._focus: Node | None = None
        self._focus_widgets: dict[Node, QGroupBox] = {}
        self._item_groups: dict[Node, QGroupBox] = {}
        self._child_groups: dict[Node, QGroupBox] = {}
        self._node_editors: dict[Node, tuple[PropertyEditor, set[str] | None]] = {}
        self._helper_editors: dict[Node, HelperCodeEditor] = {}
        self._updater_buttons: dict[Node, ActionButton] = {}
        self._part_set_lists: dict[PartNode, PartSetList] = {}
        self._cad_export_directory = "."

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self._add_menu = QMenu(self)
        header = CollectionHeader("", menu=self._add_menu)
        self._heading = header.title
        self._add_button = header.add_button
        outer.addWidget(header)

        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._hint.setProperty("textRole", "muted")
        outer.addWidget(self._hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        body = QWidget()
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(
            *deepcopy(theme_manager.palette.layout.widgets.collection_contents_margins)
        )
        self._layout.setSpacing(theme_manager.palette.layout.widgets.collection_spacing)
        self._layout.addStretch(1)
        self._scroll.setWidget(body)
        outer.addWidget(self._scroll, 1)

    def edit_node(
        self,
        manager: Node | None,
        problem: ProblemDefinition,
        focus: Node | None = None,
        *,
        scroll_to_focus: bool = True,
    ) -> None:
        self._problem = problem
        self._focus = focus if focus is not manager else None
        self._heading.setText(
            {
                "geometry": tr("ui.widgets.definition_manager.parts"),
                "loads": tr("ui.widgets.definition_manager.components"),
                "materials": tr("ui.widgets.definition_manager.materials"),
                "helper_variables": tr(
                    "ui.widgets.model_tree.container.helper_variables_group"
                ),
                "helper_functions": tr(
                    "ui.widgets.model_tree.container.helper_functions_group"
                ),
            }[self.mode]
        )
        self._hint.setText(
            {
                "geometry": tr(
                    "ui.widgets.definition_manager.select_a_part_in_the_model_tree_to_edit_it_edit_instance_placement_bound"
                ),
                "loads": tr(
                    "ui.widgets.definition_manager.edit_load_definitions_add_and_configure_loads_boundary_conditions_reference_points"
                ),
                "materials": tr(
                    "ui.widgets.definition_manager.select_a_material_in_the_model_tree_to_edit_its_properties_and"
                ),
                "helper_variables": tr("ui.widgets.helper_editor.variables_hint"),
                "helper_functions": tr("ui.widgets.helper_editor.functions_hint"),
            }[self.mode]
        )
        self._refresh_add_menu()
        structure = self._structure_signature()
        if structure != self._structure:
            self._structure = structure
            self._rebuild_cards()
        else:
            for node, (editor, excluded) in self._node_editors.items():
                self._bind_node_editor(editor, node, excluded)
            for node, editor in self._helper_editors.items():
                editor.edit_node(node, problem)
        self._update_titles()
        self._refresh_part_sets()
        self._focus_selection(scroll=scroll_to_focus)

    def refresh_ui(self, context: RefreshContext) -> None:
        self.edit_node(None, context.problem, self._focus, scroll_to_focus=False)

    def _on_editor_activated(self, node: Node) -> None:
        if self._focus is not node:
            self._focus = node
            self._focus_selection(scroll=False)
        self.activated.emit(node)

    def _on_node_changed(self, node: Node) -> None:
        self._on_editor_activated(node)
        if self.sets is not None:
            self.sets.invalidate()
        for editor, _ in self._node_editors.values():
            editor.refresh_choices()
        self._refresh_part_sets()
        self.changed.emit(node)

    def _refresh_part_sets(self) -> None:
        if self._problem is None:
            return
        catalog = self.sets or PartSetCatalog(self._problem)
        for part, listing in self._part_set_lists.items():
            try:
                listing.set_sets(catalog.for_part(part))
            except Exception as exc:
                listing.set_error(exc)

    def invalidate(self) -> None:
        """Refresh node forms the next time this manager page is selected."""
        self._structure = None

    def _all_items(self) -> list[Node]:
        if self._problem is None:
            return []
        if self.mode == "geometry":
            return list(self._problem.parts())
        if self.mode == "loads":
            return list(self._problem.fea_components())
        if self.mode == "helper_variables":
            return list(self._problem.helper_variables)
        if self.mode == "helper_functions":
            return list(self._problem.helper_functions)
        return list(self._problem.material_nodes())

    def _structure_signature(self) -> tuple[Any, ...]:
        items = managed_nodes(self._problem, self.mode, self._focus)
        if self.mode == "geometry":
            return (
                tuple(
                    (id(item), tuple(id(child) for child in item.children))
                    for item in items
                ),
            )
        return tuple(id(item) for item in items)

    def _refresh_add_menu(self) -> None:
        self._add_menu.clear()
        if self._problem is None:
            return
        from ..schemes.base import get_template

        template = get_template(self._problem.scheme)
        if self.mode == "geometry":
            for part_type in template.available_geometry_types():
                spec = PART_TYPES[part_type]
                action = self._add_menu.addAction(node_type_title(spec, part_type))
                action.triggered.connect(
                    lambda _checked=False, kind=part_type: self.actions.add_part(kind)
                )
            candidates = {
                kind: (
                    "morphopt.BoundaryPart" if spec.has_surfaces else f"morphopt.{kind}"
                )
                for kind, spec in PART_TYPES.items()
                if kind in template.available_geometry_types()
            }
            candidates["BasePart"] = "morphopt.BasePart"
            self.actions.custom_add_menu(
                self._add_menu, candidates, self.actions.add_part
            )
        elif self.mode == "loads":
            for component_type, spec in LOAD_TYPES.items():
                action = self._add_menu.addAction(node_type_title(spec, component_type))
                action.triggered.connect(
                    lambda _checked=False, kind=component_type: (
                        self.actions.add_component(kind)
                    )
                )
            self.actions.custom_add_menu(
                self._add_menu,
                {
                    kind: f"morphopt.FEAParams.{spec.backend_class}"
                    for kind, spec in LOAD_TYPES.items()
                },
                self.actions.add_component,
            )
        elif self.mode in {"helper_variables", "helper_functions"}:
            kind = (
                "helper_variable"
                if self.mode == "helper_variables"
                else "helper_function"
            )
            self._add_menu.addAction(
                tr(
                    "ui.workbench.add_helper_variable"
                    if kind == "helper_variable"
                    else "ui.workbench.add_helper_function"
                ),
                lambda: self.actions.add_helper(kind),
            )
        else:
            for material_type, spec in MATERIAL_TYPES.items():
                action = self._add_menu.addAction(node_type_title(spec, material_type))
                action.triggered.connect(
                    lambda _checked=False, kind=material_type: (
                        self.actions.add_material(kind)
                    )
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
        self._node_editors.clear()
        self._helper_editors.clear()
        self._updater_buttons.clear()
        self._part_set_lists.clear()
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
                tr(
                    "ui.widgets.definition_manager.select_a_part_load_or_material_in_the_model_tree_to_edit_it"
                )
                if all_items
                else tr("ui.widgets.definition_manager.no_items_have_been_added")
            )
            self._layout.addWidget(QLabel(message))
        self._layout.addStretch(1)

    def _part_card(self, node: Node, index: int, count: int) -> QGroupBox:
        assert isinstance(node, PartNode)
        group = QGroupBox(self._item_title(node))
        self._item_groups[node] = group
        self._focus_widgets[node] = group
        col = QVBoxLayout(group)
        self._add_component_update_controls(col, node)
        self._add_order_controls(
            col,
            node,
            index,
            count,
            lambda item=node: self.actions.remove_part(item),
            lambda item=node, delta=-1: self.actions.move_part(item, delta),
            tr("ui.widgets.definition_manager.delete_part"),
        )
        col.addWidget(self._node_editor(node))

        listing = PartSetList()
        listing.selected.connect(
            lambda kind, name, part=node: self.partSetSelected.emit(part, kind, name)
        )
        self._part_set_lists[node] = listing
        col.addWidget(listing)

        col.addWidget(
            self._child_collection(
                tr("ui.widgets.definition_manager.instances"),
                node.instances,
                add=lambda owner=node: self.actions.add_instance(owner),
                remove=lambda child: self.actions.remove_instance(child),
                move=lambda child, delta: self.actions.move_instance(child, delta),
                title_fn=instance_title_text,
                edit_all=True,
            )
        )
        if isinstance(node, BoundaryPartNode):
            col.addWidget(
                self._child_collection(
                    tr("ui.widgets.definition_manager.boundary_surfaces"),
                    node.surfaces,
                    add_menu=self._surface_add_menu(node),
                    remove=lambda child: self.actions.remove_surface(child),
                    move=lambda child, delta: self.actions.move_surface(child, delta),
                    title_fn=self._item_title,
                    edit_all=True,
                )
            )
        if isinstance(node, CADPartNode):
            self._add_cad_collection(col, node)
        return group

    def _simple_card(self, node: Node, index: int, count: int) -> QGroupBox:
        group = QGroupBox(self._item_title(node))
        self._item_groups[node] = group
        self._focus_widgets[node] = group
        col = QVBoxLayout(group)
        if node.kind in {"helper_variable", "helper_function"}:
            self._add_order_controls(
                col,
                node,
                index,
                count,
                lambda: self.actions.remove_helper(node),
                lambda item=node, delta=-1: self.actions.move_helper(item, delta),
                tr("ui.workbench.delete_item"),
            )
            editor = HelperCodeEditor(self.actions, embedded=True)
            editor.edit_node(node, self._problem)
            editor.changed.connect(self._on_node_changed)
            editor.activated.connect(self._on_editor_activated)
            self._helper_editors[node] = editor
            col.addWidget(editor)
            return group
        if isinstance(node, MaterialNode):
            self._add_component_update_controls(col, node)
        if isinstance(node, FEAComponentNode):
            remove = lambda item=node: self.actions.remove_component(item)
            move = lambda item=node, delta=-1: self.actions.move_component(item, delta)
            delete_title = tr("ui.widgets.definition_manager.delete_component")
        else:
            remove = lambda item=node: self.actions.remove_material(item)
            move = lambda item=node, delta=-1: self.actions.move_material(item, delta)
            delete_title = tr("ui.widgets.definition_manager.delete_material")
        self._add_order_controls(col, node, index, count, remove, move, delete_title)
        col.addWidget(self._node_editor(node))
        return group

    def _add_component_update_controls(
        self,
        layout: QVBoxLayout,
        node: PartNode | MaterialNode,
    ) -> None:
        row = QHBoxLayout()
        description = QLabel(component_update_description(node))
        description.setWordWrap(True)
        row.addWidget(description, 1)
        if node.is_updatable:
            button = ActionButton(
                tr("ui.component.create_updater"),
                lambda: self.actions.add_updater(node),
            )
            self._updater_buttons[node] = button
            row.addWidget(button)
        elif isinstance(node, CADPartNode):
            row.addWidget(
                ActionButton(
                    tr("ui.cad.convert_to_boundary"),
                    lambda part=node: self.actions.convert_cad_to_boundary(part),
                )
            )
            row.addWidget(
                ActionButton(
                    tr("ui.cad.export_step"),
                    lambda part=node: self._export_cad_step(part),
                )
            )
        layout.addLayout(row)

    def _export_cad_step(self, node: CADPartNode) -> None:
        title = tr("ui.cad.export_step")
        if not node.operations:
            QMessageBox.information(self, title, tr("ui.cad.features_required"))
            return
        selection = choose_save_file(
            self,
            title,
            self._cad_export_directory,
            node.assembly_name or "part",
            {"stp": tr("ui.cad.stp_files"), "step": tr("ui.cad.step_files")},
        )
        if selection is None:
            return
        self._cad_export_directory = str(selection.path.parent)
        try:
            export_cad_step(node, selection.path, self._problem)
        except Exception as exc:
            QMessageBox.warning(self, title, str(exc))
            return
        QMessageBox.information(
            self, title, tr("ui.cad.exported", path=str(selection.path))
        )

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
        group = QGroupBox()
        col = QVBoxLayout(group)
        if add is not None or add_menu is not None:
            col.addWidget(CollectionHeader(title, add, menu=add_menu))
        else:
            group.setTitle(title)
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
                    lambda item=child, delta=-1: (
                        move(item, delta) if move is not None else None
                    )
                ),
                tr("ui.widgets.definition_manager.delete"),
                allow_move=move is not None,
            )
            if edit_all or child is self._focus:
                item_col.addWidget(self._node_editor(child))
            col.addWidget(card)
        return group

    def _surface_add_menu(self, owner: BoundaryPartNode) -> QMenu:
        menu = QMenu(self)
        for surface_type, spec in SURFACE_TYPES.items():
            action = menu.addAction(node_type_title(spec, surface_type))
            action.triggered.connect(
                lambda _checked=False, kind=surface_type, part=owner: (
                    self.actions.add_surface(kind, part)
                )
            )
        candidates = {
            kind: "morphopt.BoundaryPart."
            + (spec.factory.split(".")[0] if spec.factory else spec.backend_class)
            for kind, spec in SURFACE_TYPES.items()
        }
        self.actions.custom_add_menu(
            menu,
            candidates,
            lambda kind, custom: self.actions.add_surface(kind, owner, custom),
        )
        return menu

    def _add_cad_collection(
        self, parent_layout: QVBoxLayout, owner: CADPartNode
    ) -> None:
        group = QGroupBox()
        col = QVBoxLayout(group)
        menu = QMenu(group)
        for feature_group, label in (
            ("primitive", tr("ui.widgets.definition_manager.primitive")),
            ("boolean", tr("ui.widgets.definition_manager.boolean")),
            ("transform", tr("ui.widgets.definition_manager.transform")),
            ("import", tr("ui.widgets.definition_manager.step")),
        ):
            menu.addAction(
                label,
                lambda _checked=False, kind=feature_group, part=owner: (
                    self.actions.add_cad_operation_group(kind, part)
                ),
            )
        col.addWidget(
            CollectionHeader(
                tr("ui.widgets.definition_manager.cad_feature_history"), menu=menu
            )
        )

        operations = owner.operations
        for index, operation in enumerate(operations):
            card = QGroupBox(self._item_title(operation))
            card.setToolTip(cad_operation_summary_text(operation))
            self._child_groups[operation] = card
            self._focus_widgets[operation] = card
            item_col = QVBoxLayout(card)
            self._add_order_controls(
                item_col,
                operation,
                index,
                len(operations),
                lambda item=operation: self.actions.remove_cad_operation(item),
                lambda item=operation, delta=-1: self.actions.move_cad_operation(
                    item, delta
                ),
                tr("ui.widgets.definition_manager.delete_cad_operation"),
            )
            item_col.addWidget(self._node_editor(operation))
            col.addWidget(card)
        parent_layout.addWidget(group)

    def _node_editor(
        self, node: Node, *, exclude_fields: set[str] | None = None
    ) -> PropertyEditor:
        editor = PropertyEditor(compact=True)
        self._bind_node_editor(editor, node, exclude_fields)
        self._node_editors[node] = editor, exclude_fields
        editor.activated.connect(self._on_editor_activated)
        editor.changed.connect(self._on_node_changed)
        return editor

    def _bind_node_editor(
        self,
        editor: PropertyEditor,
        node: Node,
        exclude_fields: set[str] | None,
    ) -> None:
        fields, code_slots, choices = fields_for_node(
            node, self._problem, sets=self.sets
        )
        if exclude_fields:
            fields = [field for field in fields if field.key not in exclude_fields]
        title = self._item_title(node)
        editor.edit_node(
            node,
            fields=fields,
            code_slots=code_slots,
            extra_choices=choices,
            title=title,
            completion_problem=self._problem,
        )

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
        cannot_remove_last = (
            isinstance(node, (MaterialNode, InstanceNode)) and count <= 1
        )
        layout.addWidget(
            ItemActions(
                index,
                count,
                remove,
                (lambda offset: move(node, offset)) if allow_move else None,
                allow_remove=not cannot_remove_last,
                remove_tooltip=remove_title,
            )
        )

    def _item_title(self, node: Node) -> str:
        return node_title(self._problem, node)

    def _update_titles(self) -> None:
        available = self.actions.commands.available_optimizer_targets()
        for node, button in self._updater_buttons.items():
            free = node in available
            button.setEnabled(free)
            button.setText(
                tr(
                    "ui.component.create_updater"
                    if free
                    else "ui.component.updater_created"
                )
            )
        for groups in (self._item_groups, self._child_groups):
            for node, group in groups.items():
                group.setTitle(self._item_title(node))
                if isinstance(node, CADOperationNode):
                    group.setToolTip(cad_operation_summary_text(node))

    def _focus_selection(self, *, scroll: bool = True) -> None:
        for node, widget in self._focus_widgets.items():
            focused = node is self._focus
            set_card_selected(widget, focused)
        target = (
            self._focus_widgets.get(self._focus) if self._focus is not None else None
        )
        if scroll and target is not None:
            QTimer.singleShot(
                0,
                self,
                lambda item=target, node=self._focus: (
                    self._scroll.ensureWidgetVisible(item, 10, 10)
                    if self._focus is node
                    else None
                ),
            )
