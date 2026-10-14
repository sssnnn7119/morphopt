"""Abaqus-like model tree for the problem definition.

Left-hand navigation + structure editing.  Context menus:

* ``geometry`` (shape): add a surface (outer/inner), surfaces can be
  deleted / reordered.
* ``loads``: add / delete load-interface entries.
* ``updater``: choose the global objective, geometry/material optimizer, or
  one of the optimizer's objective/symmetry/penalty sections.

Any structural change emits :attr:`treeChanged` so the workbench can refresh
the viewer and the read-only generated code.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
)

from ..i18n import tr
from ..model.problem import (
    CADOperationNode,
    InstanceNode,
    MaterialNode,
    Node,
    PartInterfaceNode,
    ProblemDefinition,
)
from ..model.schemas import (
    CAD_OPERATION_TYPES,
    UPDATER_CONSTRAINTS,
    UPDATER_OBJECTIVES,
    INTERFACE_TYPES,
    MATERIAL_TYPES,
    PART_INTERFACE_TYPES,
    SURFACE_TYPES,
    SURFACE_SYMMETRY_CONSTRAINTS,
    available_surface_symmetry_types,
)

from ..presentation.labels import schema_label, cad_operation_title_text, display_node_title
from ..presentation.navigation import (
    UpdaterTreeNode,
    DefinitionNavigation,
    NavigationEntry,
    node_key,
)
from .definition_actions import DefinitionActions


class ModelTree(QTreeWidget):
    nodeSelected = Signal(object)  # Node
    treeChanged = Signal()  # structure edited

    def __init__(self, parent=None, *, actions: DefinitionActions | None = None):
        super().__init__(parent)
        self.actions = actions or DefinitionActions(self)
        self.actions.selectionRequested.connect(lambda node: self.rebuild(select=node))
        self.actions.changed.connect(self.treeChanged.emit)
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_menu)
        self.currentItemChanged.connect(self._on_current)
        self._problem: ProblemDefinition | None = None
        self._item_node: dict[QTreeWidgetItem, Node] = {}
        self._node_item: dict[Node, QTreeWidgetItem] = {}

    # ------------------------------------------------------------------ api
    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self.actions.set_problem(problem)
        self.rebuild()

    def rebuild(self, select: Node | None = None, *, notify: bool = True) -> None:
        selected_key = node_key(select)
        self.blockSignals(True)
        try:
            self.clear()
            self._item_node.clear()
            self._node_item.clear()
            if self._problem is None:
                return
            for entry in DefinitionNavigation(self._problem).build():
                self.addTopLevelItem(self._render_entry(entry))
            self.expandAll()
            item = next((item for node, item in self._node_item.items() if node_key(node) == selected_key), None)
            if item is not None:
                self.setCurrentItem(item)
        finally:
            self.blockSignals(False)
        if notify and item is not None:
            self.nodeSelected.emit(self._item_node[item])

    def _render_entry(self, entry: NavigationEntry) -> QTreeWidgetItem:
        item = self._make_item(entry.title, entry.node, entry.bold)
        for child in entry.children:
            item.addChild(self._render_entry(child))
        return item

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        if self._problem is None:
            return
        projection = DefinitionNavigation(self._problem)
        for item, node in self._item_node.items():
            item.setText(0, display_node_title(self._problem, projection.title(node), node))

    # ------------------------------------------------------------ rendering
    def _make_item(self, text: str, node: Node, bold: bool = False) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        if isinstance(node, PartInterfaceNode):
            item.setToolTip(
                0,
                tr(
                    "ui.widgets.model_tree.part_instances_tooltip",
                    value_0=node.resolved_part_name(),
                    value_1=", ".join(node.resolved_instance_names()),
                ),
            )
        elif isinstance(node, InstanceNode):
            item.setToolTip(
                0,
                tr(
                    "ui.widgets.model_tree.instance_transform_tooltip",
                    value_0=node.translation,
                    value_1=node.rotation,
                ),
            )
        elif isinstance(node, CADOperationNode):
            item.setToolTip(0, cad_operation_title_text(node))
        elif isinstance(node, MaterialNode):
            item.setToolTip(
                0,
                tr(
                    "ui.widgets.model_tree.material_assignment_tooltip",
                    value_0=node.part_name,
                    value_1=node.elementname or tr("ui.widgets.model_tree.all_elements"),
                ),
            )
        if bold:
            f = item.font(0)
            f.setBold(True)
            item.setFont(0, f)
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        self._item_node[item] = node
        self._node_item[node] = item
        return item

    # -------------------------------------------------------------- events
    def _on_current(self, cur, _prev) -> None:
        if cur is not None:
            node = self._item_node.get(cur)
            if node is not None:
                self.nodeSelected.emit(node)

    def _open_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None:
            return
        node = self._item_node.get(item)
        if node is None:
            return
        menu = QMenu(self)
        self._build_node_menu(menu, node)
        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _build_node_menu(self, menu: QMenu, node: Node) -> None:
        kind = node.kind
        scheme = self._problem.scheme if self._problem else "shapeopt"

        if kind in {"helper_code", "helper_variables_group"}:
            menu.addAction(tr('ui.widgets.model_tree.add_helper_variable'),
                           lambda: self.actions.add_helper("helper_variable"))
        if kind in {"helper_code", "helper_functions_group"}:
            menu.addAction(tr('ui.widgets.model_tree.add_helper_function'),
                           lambda: self.actions.add_helper("helper_function"))
        if kind in {"helper_variable", "helper_function"}:
            menu.addAction(tr('ui.widgets.model_tree.delete'), lambda: self.actions.remove_helper(node))

        if kind == "geometry":
            sub = menu.addMenu(tr('ui.widgets.model_tree.add_geometry_interface'))
            from ..schemes.base import get_template

            for itype in get_template(scheme).available_geometry_types():
                spec = PART_INTERFACE_TYPES.get(itype, {})
                act = QAction(schema_label(spec, itype), sub)
                act.setData(itype)
                sub.addAction(act)
                act.triggered.connect(lambda _=False, kind=itype: self.actions.add_part_interface(kind))
            candidates = {kind: "morphopt.BoundaryPartInterface" if PART_INTERFACE_TYPES[kind].get("surfaces")
                          else f"morphopt.{kind}" for kind in get_template(scheme).available_geometry_types()}
            candidates["BasePartInterface"] = "morphopt.BasePartInterface"
            self.actions.custom_add_menu(sub, candidates, self.actions.add_part_interface)

        if kind == "part_interface":
            act_instance = QAction(tr('ui.widgets.model_tree.add_instance'), menu)
            act_instance.triggered.connect(lambda _=False, owner=node: self.actions.add_instance(owner))
            menu.addAction(act_instance)
            menu.addSeparator()
            if node.has_surfaces:
                sub = menu.addMenu(tr('ui.widgets.model_tree.add_surface'))
                for stype, spec in SURFACE_TYPES.items():
                    act = QAction(schema_label(spec, stype), sub)
                    act.setData(stype)
                    sub.addAction(act)
                    act.triggered.connect(lambda _=False, kind=stype, owner=node: self.actions.add_surface(
                        kind,
                        owner,
                    ))
                candidates = {kind: "morphopt.BoundaryPartInterface." + (spec["factory"].split(".")[0] if spec["factory"] else "FixedSurface")
                              for kind, spec in SURFACE_TYPES.items()}
                self.actions.custom_add_menu(
                    sub,
                    candidates,
                    lambda kind, custom: self.actions.add_surface(kind, node, custom),
                )
                menu.addSeparator()
            elif isinstance(node, PartInterfaceNode) and node.interface_type == "CADPartInterface":
                for group, title in (
                    ("primitive", tr('ui.widgets.model_tree.add_primitive_494ebece')),
                    ("boolean", tr('ui.widgets.model_tree.add_boolean')),
                    ("transform", tr('ui.widgets.model_tree.add_transform_aad8bcb1')),
                ):
                    sub = menu.addMenu(title)
                    for operation_type, spec in CAD_OPERATION_TYPES.items():
                        if spec["group"] != group:
                            continue
                        action = QAction(
                            tr(spec["label_key"]), sub
                        )
                        sub.addAction(action)
                        action.triggered.connect(
                            lambda _=False, kind=operation_type, owner=node:
                                self.actions.add_cad_operation(kind, owner)
                        )
                import_action = QAction(
                    tr('ui.widgets.model_tree.import_step'), menu
                )
                import_action.triggered.connect(
                    lambda _=False, owner=node:
                        self.actions.add_cad_operation("StepImport", owner)
                )
                menu.addAction(import_action)
                menu.addSeparator()

            act_copy = QAction(tr('ui.widgets.model_tree.copy'), menu)
            act_copy.triggered.connect(lambda: self.actions.copy_part_interface(node))
            act_up = QAction(tr('ui.widgets.model_tree.move_up'), menu)
            act_up.triggered.connect(lambda: self.actions.move_part_interface(node, -1))
            act_dn = QAction(tr('ui.widgets.model_tree.move_down'), menu)
            act_dn.triggered.connect(lambda: self.actions.move_part_interface(node, 1))
            act_del = QAction(tr('ui.widgets.model_tree.delete_geometry_interface'), menu)
            act_del.triggered.connect(lambda: self.actions.remove_part_interface(node))
            menu.addAction(act_copy)
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if kind == "instance":
            act_up = QAction(tr('ui.widgets.model_tree.move_up'), menu)
            act_up.triggered.connect(lambda: self.actions.move_instance(node, -1))
            act_dn = QAction(tr('ui.widgets.model_tree.move_down'), menu)
            act_dn.triggered.connect(lambda: self.actions.move_instance(node, 1))
            act_del = QAction(tr('ui.widgets.model_tree.delete_instance'), menu)
            act_del.triggered.connect(lambda _=False: self.actions.remove_instance(node))
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if isinstance(node, CADOperationNode):
            act_up = QAction(tr('ui.widgets.model_tree.move_up'), menu)
            act_up.triggered.connect(lambda: self.actions.move_cad_operation(node, -1))
            act_dn = QAction(tr('ui.widgets.model_tree.move_down'), menu)
            act_dn.triggered.connect(lambda: self.actions.move_cad_operation(node, 1))
            act_del = QAction(tr('ui.widgets.model_tree.delete_cad_operation'), menu)
            act_del.triggered.connect(lambda: self.actions.remove_cad_operation(node))
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if kind == "materials":
            sub = menu.addMenu(tr('ui.widgets.model_tree.add_material_interface'))
            from ..schemes.base import get_template

            available = get_template(scheme).available_material_types()
            for mtype in available:
                spec = MATERIAL_TYPES[mtype]
                act = QAction(schema_label(spec, mtype), sub)
                act.setData(mtype)
                sub.addAction(act)
                act.triggered.connect(lambda _=False, kind=mtype: self.actions.add_material(kind))
            self.actions.custom_add_menu(
                sub,
                {kind: f"morphopt.{kind}" for kind in available},
                self.actions.add_material,
            )

        if kind == "material":
            act_copy = QAction(tr('ui.widgets.model_tree.copy'), menu)
            act_copy.triggered.connect(lambda: self.actions.copy_material(node))
            act_up = QAction(tr('ui.widgets.model_tree.move_up'), menu)
            act_up.triggered.connect(lambda: self.actions.move_material(node, -1))
            act_dn = QAction(tr('ui.widgets.model_tree.move_down'), menu)
            act_dn.triggered.connect(lambda: self.actions.move_material(node, 1))
            act_del = QAction(tr('ui.widgets.model_tree.delete'), menu)
            act_del.triggered.connect(lambda: self.actions.remove_material(node))
            menu.addAction(act_copy)
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if kind == "surface":
            act_copy = QAction(tr('ui.widgets.model_tree.copy'), menu)
            act_copy.triggered.connect(lambda: self.actions.copy_surface(node))
            act_up = QAction(tr('ui.widgets.model_tree.move_up'), menu)
            act_up.triggered.connect(lambda: self.actions.move_surface(node, -1))
            act_dn = QAction(tr('ui.widgets.model_tree.move_down'), menu)
            act_dn.triggered.connect(lambda: self.actions.move_surface(node, 1))
            act_del = QAction(tr('ui.widgets.model_tree.delete_surface'), menu)
            act_del.triggered.connect(lambda: self.actions.remove_surface(node))
            menu.addAction(act_copy)
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if kind == "updater":
            act = QAction(tr('ui.widgets.model_tree.add_geometry_optimizer'), menu)
            act.triggered.connect(self.actions.add_geometry_updater)
            menu.addAction(act)

        if kind == "updater":
            act = QAction(tr('ui.widgets.model_tree.add_material_optimizer'), menu)
            act.triggered.connect(self.actions.add_materials_updater)
            menu.addAction(act)

        if kind == "updater_geometry":
            act_del = QAction(
                tr('ui.widgets.model_tree.delete_this_geometry_optimizer'), menu
            )
            act_del.triggered.connect(lambda: self.actions.remove_geometry_updater(node))
            menu.addAction(act_del)

        if kind == "updater_materials":
            act_del = QAction(
                tr('ui.widgets.model_tree.delete_this_material_optimizer'), menu
            )
            act_del.triggered.connect(lambda: self.actions.remove_materials_updater(node))
            menu.addAction(act_del)

        if isinstance(node, UpdaterTreeNode) and node.group in {
            "geometry_objectives",
            "geometry_penalty",
            "materials_objectives",
            "materials_penalty",
        }:
            category = "objectives" if node.group.endswith("objectives") else "constraints"
            catalog = UPDATER_OBJECTIVES if category == "objectives" else UPDATER_CONSTRAINTS
            section = node.section_group
            sub = menu.addMenu(
                (tr('ui.widgets.model_tree.add_objective') if category == "objectives" else tr('ui.widgets.model_tree.add_penalty_constraint'))
            )
            for item_type, spec in catalog.items():
                if spec.get("group") != section or spec.get("hidden", False):
                    continue
                action = sub.addAction(
                    tr(spec.get("label_key", item_type))
                )
                action.triggered.connect(
                    lambda _checked=False, entry=node, kind=item_type, cat=category:
                    self.actions.add_updater_item(entry, kind, cat)
                )

        if isinstance(node, UpdaterTreeNode) and node.group == "geometry_symmetry":
            config = node.config()
            target = (
                self._problem.config_part_node(config)
                if self._problem is not None and config is not None
                else None
            )
            surfaces = target.surfaces() if target is not None else []
            available = set(
                available_surface_symmetry_types(
                    surface.surface_type for surface in surfaces
                )
            )
            sub = menu.addMenu(tr('ui.widgets.model_tree.add_symmetry_constraint'))
            for item_type, spec in SURFACE_SYMMETRY_CONSTRAINTS.items():
                if item_type != "Custom" and item_type not in available:
                    continue
                action = sub.addAction(
                    tr(spec.get("label_key", item_type))
                )
                action.triggered.connect(
                    lambda _checked=False, entry=node, kind=item_type:
                    self.actions.add_symmetry_constraint(entry, kind)
                )

        if kind == "loads":
            sub = menu.addMenu(tr('ui.widgets.model_tree.add_load'))
            for itype, spec in INTERFACE_TYPES.items():
                act = QAction(schema_label(spec, itype), sub)
                act.setData(itype)
                sub.addAction(act)
                act.triggered.connect(lambda _=False, kind=itype: self.actions.add_interface(kind))
            self.actions.custom_add_menu(
                sub,
                {kind: f"morphopt.FEAParams.{kind}Interface" for kind in INTERFACE_TYPES},
                self.actions.add_interface,
            )

        if kind == "interface":
            act_copy = QAction(tr('ui.widgets.model_tree.copy'), menu)
            act_copy.triggered.connect(lambda: self.actions.copy_interface(node))
            act_up = QAction(tr('ui.widgets.model_tree.move_up'), menu)
            act_up.triggered.connect(lambda: self.actions.move_interface(node, -1))
            act_dn = QAction(tr('ui.widgets.model_tree.move_down'), menu)
            act_dn.triggered.connect(lambda: self.actions.move_interface(node, 1))
            act_del = QAction(tr('ui.widgets.model_tree.delete'), menu)
            act_del.triggered.connect(lambda: self.actions.remove_interface(node))
            menu.addAction(act_copy)
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

    def refresh_node_label(self, node: Node) -> None:
        item = self._node_item.get(node)
        if item is not None and self._problem is not None:
            item.setText(
                0,
                display_node_title(self._problem, DefinitionNavigation(self._problem).title(node), node),
            )
