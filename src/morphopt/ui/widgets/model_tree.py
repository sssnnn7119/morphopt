"""Abaqus-like model tree for the problem definition.

Left-hand navigation + structure editing.  Context menus:

* ``geometry`` (shape): add a surface (outer/inner), surfaces can be
  deleted / reordered.
* ``loads``: add / delete load-interface entries.
* ``updater``: choose the global objective, geometry/material optimizer, or
  one of the optimizer's objective/equality/penalty sections.

Any structural change emits :attr:`treeChanged` so the workbench can refresh
the viewer and the read-only generated code.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
)

from ..i18n import T, pick
from ..model.problem import (
    InstanceNode,
    InterfaceNode,
    MaterialNode,
    Node,
    PartInterfaceNode,
    ProblemDefinition,
    SurfaceNode,
)
from ..model.schemas import (
    INTERFACE_TYPES,
    MATERIAL_TYPES,
    PART_INTERFACE_TYPES,
    SURFACE_TYPES,
)

#: containers that hold children we show in the tree
CONTAINER_ORDER = ["geometry", "loads_group", "materials", "solver", "updater"]

#: Localized tree labels.  The parenthesized suffix is a generated-code
#: location, not a translation.
CONTAINER_TITLES_ZH = {
    "geometry": "几何（初始构型）",
    "loads_group": "载荷",
    "loads": "载荷定义",
    "steps": "载荷工况",
    "materials": "材料",
    "objective": "优化目标",
    "solver": "求解器",
    "updater": "优化问题定义",
}
CONTAINER_TITLES_EN = {
    "geometry": "Geometry — Initial configuration",
    "loads_group": "Loads",
    "loads": "Load definition",
    "steps": "Load cases",
    "materials": "Materials",
    "objective": "Optimization objective",
    "solver": "Solver",
    "updater": "Optimization definition",
}

CODE_REFERENCES = {
    "geometry": "GeometryParams",
    "loads_group": "FEAParams",
    "loads": "define_interface",
    "steps": "define_steps",
    "materials": "MaterialsParams",
    "objective": "ObjectiveFunction",
    "solver": "Solver",
    "updater": "Updater",
}


class LoadsTreeNode(Node):
    """Transient parent for load definitions and load-step cases."""

    def __init__(self) -> None:
        super().__init__(kind="loads_group", name=T("载荷", "Loads"))


class UpdaterTreeNode(Node):
    """Transient tree entry for an updater section or one of its groups.

    Updater configuration remains owned by :class:`UpdaterNode`; these nodes
    are navigation handles only and are intentionally not inserted into the
    persisted problem tree.  Both sections carry ``config_index``: the model may
    run several sub-optimizers side by side, one per target (a boundary part
    interface for geometry, a material interface for materials).
    """

    def __init__(self, updater: Node, group: str, config_index: int = 0) -> None:
        label = {
            "geometry": T("几何优化器", "Geometry optimizer"),
            "materials": T("材料优化器", "Material optimizer"),
            "geometry_objectives": T("子优化目标函数", "Sub-optimizer objectives"),
            "geometry_equality": T("几何等式约束", "Geometry equality constraints"),
            "geometry_penalty": T("几何罚函数约束", "Geometry penalty constraints"),
            "materials_objectives": T("子优化目标函数", "Sub-optimizer objectives"),
            "materials_penalty": T("材料罚函数约束", "Material penalty constraints"),
        }.get(group, group)
        super().__init__(kind=f"updater_{group}", name=label)
        self.updater_parent = updater
        self.group = group
        self.config_index = int(config_index)
        self.code_reference = (
            "UpdaterBoundaryPart" if group.startswith("geometry") else "UpdaterSIMPMaterial"
        )

    @property
    def section_group(self) -> str:
        """Canonical updater section owning this navigation entry."""
        return "geometry" if self.group.startswith("geometry") else "materials"

    def config(self) -> dict | None:
        """Config dict this entry points at."""
        configs = (
            self.updater_parent.geometry
            if self.section_group == "geometry"
            else self.updater_parent.materials
        )
        return configs[self.config_index] if self.config_index < len(configs) else None


def container_title(kind: str) -> str:
    """Localized title with its generated-code location in parentheses."""
    label = pick(CONTAINER_TITLES_ZH.get(kind, kind), CONTAINER_TITLES_EN.get(kind))
    reference = CODE_REFERENCES.get(kind)
    return f"{label} ({reference})" if reference else label


def _full_label(spec: dict, key: str) -> str:
    """Localized full label ``解释 (TypeName)`` of a schema entry."""
    return pick(spec.get("label", key), spec.get("label_en"))


def _short_phrase(spec: dict, key: str) -> str:
    """``解释 (TypeName)`` -> just the readable phrase ``解释``."""
    full = _full_label(spec, key)
    return re.sub(r"\s*\([^)]*\)\s*$", "", full).strip() or full


def surface_title_text(srf: Node, index: int) -> str:
    """Tree/editor label for one geometry surface: ``"0: 圆柱面"``.

    Surfaces are *not* given descriptive names; they are identified by their
    0-based index inside their Part interface (0 = outer boundary, >= 1 =
    inner cavity).  The index comes from the current position, so moving a
    surface up/down renumbers it automatically.
    """
    st = srf.surface_type or "?"
    spec = SURFACE_TYPES.get(st, {})
    return f"{index}: {_short_phrase(spec, st)}"


def part_interface_title_text(interface: Node) -> str:
    """Tree label for one geometry interface: ``"body  [Part: body, 实体: body-1]"``.

    Shows the interface (Part) name and its instances, which are the names
    every load / material / contact interface refers to.
    """
    itype = interface.interface_type or "?"
    spec = PART_INTERFACE_TYPES.get(itype, {})
    phrase = _short_phrase(spec, itype)
    instances = interface.resolved_instance_names()
    instance_text = ", ".join(instances) if instances else "?"
    name = f"{interface.name}: " if interface.name else ""
    return (
        f"{name}{phrase}  [part={interface.resolved_part_name()}, 实体={instance_text}]"
    )


def instance_title_text(instance: InstanceNode) -> str:
    """Tree label for one Part Instance and its six-component pose."""
    pose = ", ".join(f"{value:g}" for value in instance.pose)
    return f"{instance.name}: [{pose}]"


def surface_index(problem: ProblemDefinition | None, srf: Node) -> int | None:
    """Return the 0-based position of ``srf`` inside its Part interface."""
    if problem is None:
        return None
    owner = problem.owner_of_surface(srf)
    if owner is None:
        return None
    for i, s in enumerate(owner.surfaces()):
        if s is srf:
            return i
    return None


class ModelTree(QTreeWidget):
    nodeSelected = Signal(object)  # Node
    treeChanged = Signal()  # structure edited

    def __init__(self, parent=None):
        super().__init__(parent)
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
        # Loaded definitions can predate the current number of surfaces.
        problem.align_surface_dependent_state()
        self.rebuild()

    def rebuild(self, select: Node | None = None) -> None:
        select_key = self._node_key(select) if select is not None else None
        self.clear()
        self._item_node.clear()
        self._node_item.clear()
        if self._problem is None:
            return
        # Top-level sections are supplied by the model aggregate; the widget
        # only turns them into rows.  Loads and load cases share one visual
        # parent even though they remain separate model sections and are
        # serialized unchanged.
        for kind in CONTAINER_ORDER:
            if kind == "loads_group":
                group_node = LoadsTreeNode()
                group_item = self._make_item(
                    container_title("loads_group"), group_node, bold=True
                )
                self.addTopLevelItem(group_item)
                self._add_loads_children(group_item)
                continue
            node = self._problem.section(kind)
            if node is None:
                continue
            item = self._make_item(container_title(kind), node, bold=True)
            self.addTopLevelItem(item)
            if kind == "geometry":
                for interface in self._problem.part_interfaces():
                    interface_item = self._make_item(
                        part_interface_title_text(interface), interface
                    )
                    item.addChild(interface_item)
                    for instance in interface.instances():
                        instance_item = self._make_item(
                            instance_title_text(instance), instance
                        )
                        interface_item.addChild(instance_item)
                    for i, srf in enumerate(interface.surfaces()):
                        srf_item = self._make_item(self._surface_title(srf, i), srf)
                        interface_item.addChild(srf_item)
            elif kind == "materials":
                for material in self._problem.material_nodes():
                    material_item = self._make_item(
                        self._material_title(material), material
                    )
                    item.addChild(material_item)
            elif kind == "updater":
                self._add_updater_children(item, node)
        self.expandAll()
        if select is not None:
            it = self._node_item.get(select)
            if it is None and select_key is not None:
                it = next(
                    (
                        candidate_item
                        for candidate_item, candidate_node in self._node_item.items()
                        if self._node_key(candidate_node) == select_key
                    ),
                    None,
                )
            if it is not None:
                self.setCurrentItem(it)

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-localize the tree titles in place (keeps the selection)."""
        for item, node in list(self._item_node.items()):
            if node.kind in CONTAINER_ORDER:
                item.setText(0, container_title(node.kind))
            elif node.kind == "part_interface":
                item.setText(0, part_interface_title_text(node))
            elif node.kind == "instance":
                item.setText(0, instance_title_text(node))
            elif node.kind == "surface":
                idx = surface_index(self._problem, node)
                if idx is not None:
                    item.setText(0, self._surface_title(node, idx))
            elif node.kind == "interface":
                item.setText(0, self._interface_title(node))
            elif node.kind == "material":
                item.setText(0, self._material_title(node))
            elif node.kind in {"loads", "steps"}:
                item.setText(0, container_title(node.kind))
            elif node.kind == "objective":
                item.setText(0, container_title("objective"))
            elif node.kind.startswith("updater_"):
                item.setText(0, self._updater_title(node))

    # ------------------------------------------------------------ rendering
    def _make_item(self, text: str, node: Node, bold: bool = False) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        if bold:
            f = item.font(0)
            f.setBold(True)
            item.setFont(0, f)
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        self._item_node[item] = node
        self._node_item[node] = item
        return item

    @staticmethod
    def _surface_title(srf: Node, index: int) -> str:
        return surface_title_text(srf, index)

    @staticmethod
    def _interface_title(iface: Node) -> str:
        it = iface.interface_type or "?"
        spec = INTERFACE_TYPES.get(it, {})
        phrase = _short_phrase(spec, it)
        return f"{iface.name}  [{phrase}]" if iface.name else phrase

    @staticmethod
    def _material_title(material: Node) -> str:
        mtype = material.material_type or "?"
        spec = MATERIAL_TYPES.get(mtype, {})
        type_label = _full_label(spec, mtype)
        part_name = str(material.part_name or "<Part?>").strip()
        elem_name = str(material.elementname or "").strip()
        elem_name = elem_name or T("全部 elems", "all elems")
        name = f"{material.name}: " if material.name else ""
        return f"{name}{type_label}  [part={part_name}, elem={elem_name}]"

    def _updater_title(self, node: Node) -> str:
        """Return the localized title for a transient updater tree entry."""
        if node.kind.startswith("updater_"):
            labels = {
                "geometry": ("几何优化器", "Geometry optimizer"),
                "materials": ("材料优化器", "Material optimizer"),
                "geometry_objectives": ("子优化目标函数", "Sub-optimizer objectives"),
                "geometry_equality": ("几何等式约束", "Geometry equality constraints"),
                "geometry_penalty": ("几何罚函数约束", "Geometry penalty constraints"),
                "materials_objectives": ("子优化目标函数", "Sub-optimizer objectives"),
                "materials_penalty": ("材料罚函数约束", "Material penalty constraints"),
            }
            if node.group not in labels:
                return container_title("updater")
            label = T(
                *labels[node.group],
            )
            part = ""
            if node.section_group == "geometry":
                config = node.config() or {}
                target = (
                    self._problem.config_part_node(config)
                    if self._problem is not None
                    else None
                )
                if target is not None:
                    part = T(f" · Part {target.name}", f" · Part {target.name}")
            elif node.section_group == "materials":
                config = node.config() or {}
                target = (
                    self._problem.config_material_node(config)
                    if self._problem is not None
                    else None
                )
                if target is not None:
                    part = T(
                        f" · 材料 {target.name}", f" · material {target.name}"
                    )
                elif len(node.updater_parent.materials) > 1:
                    part = f" · {node.config_index}"
            return f"{label} ({node.code_reference}){part}"
        return container_title("updater")

    @staticmethod
    def _node_key(node: Node | None):
        """Stable identity for transient updater entries across rebuilds."""
        if node is None:
            return None
        if isinstance(node, UpdaterTreeNode):
            return (
                "updater",
                id(node.updater_parent),
                node.group,
                node.config_index,
            )
        return ("node", id(node))

    def _add_updater_children(
        self, parent_item: QTreeWidgetItem, updater: Node
    ) -> None:
        """Render objective plus nested geometry/material updater groups."""
        if self._problem is not None and self._problem.objective is not None:
            objective = self._problem.objective
            objective_item = self._make_item(
                container_title("objective"), objective, bold=True
            )
            parent_item.addChild(objective_item)

        for index, _config in enumerate(updater.geometry):
            geometry_node = UpdaterTreeNode(updater, "geometry", index)
            geometry_item = self._make_item(
                self._updater_title(geometry_node), geometry_node, bold=True
            )
            parent_item.addChild(geometry_item)
            for group in (
                "geometry_objectives",
                "geometry_equality",
                "geometry_penalty",
            ):
                child_node = UpdaterTreeNode(updater, group, index)
                child_item = self._make_item(
                    self._updater_title(child_node), child_node
                )
                geometry_item.addChild(child_item)

        for index, _config in enumerate(updater.materials):
            materials_node = UpdaterTreeNode(updater, "materials", index)
            materials_item = self._make_item(
                self._updater_title(materials_node), materials_node, bold=True
            )
            parent_item.addChild(materials_item)
            for group in ("materials_objectives", "materials_penalty"):
                child_node = UpdaterTreeNode(updater, group, index)
                child_item = self._make_item(
                    self._updater_title(child_node), child_node
                )
                materials_item.addChild(child_item)

    def _add_loads_children(self, parent_item: QTreeWidgetItem) -> None:
        """Render load definitions and load cases under the shared parent."""
        loads = self._problem.loads if self._problem is not None else None
        if loads is not None:
            loads_item = self._make_item(container_title("loads"), loads, bold=True)
            parent_item.addChild(loads_item)
            for iface in self._problem.interfaces():
                interface_item = self._make_item(self._interface_title(iface), iface)
                loads_item.addChild(interface_item)

        steps = self._problem.steps if self._problem is not None else None
        if steps is not None:
            steps_item = self._make_item(container_title("steps"), steps, bold=True)
            parent_item.addChild(steps_item)

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

        if kind == "geometry":
            sub = menu.addMenu(T("添加几何接口 ▸", "Add geometry interface ▸"))
            from ..schemes.base import get_template

            for itype in get_template(scheme).available_geometry_types():
                spec = PART_INTERFACE_TYPES.get(itype, {})
                act = QAction(_full_label(spec, itype), sub)
                act.setData(itype)
                sub.addAction(act)
            sub.triggered.connect(lambda a: self._add_part_interface(a.data()))

        if kind == "part_interface":
            act_instance = QAction(T("添加实体 Instance", "Add Instance"), menu)
            act_instance.triggered.connect(lambda _=False, owner=node: self._add_instance(owner))
            menu.addAction(act_instance)
            menu.addSeparator()
            if node.has_surfaces:
                sub = menu.addMenu(T("添加曲面 ▸", "Add surface ▸"))
                for stype, spec in SURFACE_TYPES.items():
                    act = QAction(_full_label(spec, stype), sub)
                    act.setData(stype)
                    sub.addAction(act)
                sub.triggered.connect(
                    lambda a, owner=node: self._add_surface(a.data(), owner)
                )
                menu.addSeparator()

            act_copy = QAction(T("复制", "Copy"), menu)
            act_copy.triggered.connect(lambda: self._copy_part_interface(node))
            act_up = QAction(T("上移", "Move up"), menu)
            act_up.triggered.connect(lambda: self._move_part_interface(node, -1))
            act_dn = QAction(T("下移", "Move down"), menu)
            act_dn.triggered.connect(lambda: self._move_part_interface(node, 1))
            act_del = QAction(T("删除几何接口", "Delete geometry interface"), menu)
            act_del.triggered.connect(lambda: self._remove_part_interface(node))
            menu.addAction(act_copy)
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if kind == "instance":
            act_del = QAction(T("删除实体 Instance", "Delete Instance"), menu)
            act_del.triggered.connect(lambda _=False: self._remove_instance(node))
            menu.addAction(act_del)

        if kind == "materials":
            sub = menu.addMenu(T("添加材料接口 ▸", "Add material interface ▸"))
            from ..schemes.base import get_template

            available = get_template(scheme).available_material_types()
            for mtype in available:
                spec = MATERIAL_TYPES[mtype]
                act = QAction(_full_label(spec, mtype), sub)
                act.setData(mtype)
                sub.addAction(act)
            sub.triggered.connect(lambda a: self._add_material(a.data()))

        if kind == "material":
            act_copy = QAction(T("复制", "Copy"), menu)
            act_copy.triggered.connect(lambda: self._copy_material(node))
            act_up = QAction(T("上移", "Move up"), menu)
            act_up.triggered.connect(lambda: self._move_material(node, -1))
            act_dn = QAction(T("下移", "Move down"), menu)
            act_dn.triggered.connect(lambda: self._move_material(node, 1))
            act_del = QAction(T("删除", "Delete"), menu)
            act_del.triggered.connect(lambda: self._remove_material(node))
            menu.addAction(act_copy)
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if kind == "surface":
            act_copy = QAction(T("复制", "Copy"), menu)
            act_copy.triggered.connect(lambda: self._copy_surface(node))
            act_up = QAction(T("上移", "Move up"), menu)
            act_up.triggered.connect(lambda: self._move_surface(node, -1))
            act_dn = QAction(T("下移", "Move down"), menu)
            act_dn.triggered.connect(lambda: self._move_surface(node, 1))
            act_del = QAction(T("删除曲面", "Delete surface"), menu)
            act_del.triggered.connect(lambda: self._remove_surface(node))
            menu.addAction(act_copy)
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if kind == "updater":
            act = QAction(T("添加几何优化器", "Add geometry optimizer"), menu)
            act.triggered.connect(self._add_geometry_updater)
            menu.addAction(act)

        if kind == "updater":
            act = QAction(T("添加材料优化器", "Add material optimizer"), menu)
            act.triggered.connect(self._add_materials_updater)
            menu.addAction(act)

        if kind == "updater_geometry":
            act_del = QAction(
                T("删除该几何优化器", "Delete this geometry optimizer"), menu
            )
            act_del.triggered.connect(lambda: self._remove_geometry_updater(node))
            menu.addAction(act_del)

        if kind == "updater_materials":
            act_del = QAction(
                T("删除该材料优化器", "Delete this material optimizer"), menu
            )
            act_del.triggered.connect(lambda: self._remove_materials_updater(node))
            menu.addAction(act_del)

        if kind == "loads":
            sub = menu.addMenu(T("添加载荷 ▸", "Add load ▸"))
            for itype, spec in INTERFACE_TYPES.items():
                act = QAction(_full_label(spec, itype), sub)
                act.setData(itype)
                sub.addAction(act)
            sub.triggered.connect(lambda a: self._add_interface(a.data()))

        if kind == "interface":
            act_copy = QAction(T("复制", "Copy"), menu)
            act_copy.triggered.connect(lambda: self._copy_interface(node))
            act_up = QAction(T("上移", "Move up"), menu)
            act_up.triggered.connect(lambda: self._move_interface(node, -1))
            act_dn = QAction(T("下移", "Move down"), menu)
            act_dn.triggered.connect(lambda: self._move_interface(node, 1))
            act_del = QAction(T("删除", "Delete"), menu)
            act_del.triggered.connect(lambda: self._remove_interface(node))
            menu.addAction(act_copy)
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

    # --------------------------------------------------------------- edits
    def _add_geometry_updater(self) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        boundary = self._problem.boundary_part_nodes()
        if not boundary:
            QMessageBox.information(
                self,
                "Geometry optimizer",
                "This model has no boundary part interface (INP / TorchFEA parts "
                "have no design surfaces), so there is nothing to shape-optimize.",
            )
            return
        taken = {
            target
            for config in self._problem.updater.geometry
            if (target := self._problem.config_part_node(config)) is not None
        }
        free = next((part for part in boundary if part not in taken), None)
        if free is None:
            QMessageBox.information(
                self,
                "Geometry optimizer",
                "Every boundary part already has its own geometry optimizer.",
            )
            return
        self._problem.add_geometry_updater(free)
        self.rebuild(select=self._problem.updater)
        self.treeChanged.emit()

    def _remove_geometry_updater(self, node: Node) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        index = node.config_index if isinstance(node, UpdaterTreeNode) else 0
        if 0 <= index < len(self._problem.updater.geometry):
            del self._problem.updater.geometry[index]
        self.rebuild(select=self._problem.updater)
        self.treeChanged.emit()

    def _add_materials_updater(self) -> None:
        """Add one material optimizer, bound to a free design material interface."""
        if self._problem is None or self._problem.updater is None:
            return
        design = [
            material
            for material in self._problem.material_nodes()
            if material.name in self._problem.design_material_names()
        ]
        if not design:
            QMessageBox.information(
                self,
                "Material optimizer",
                "This model has no design-carrying material interface (SIMP "
                "density field), so there is nothing to update.",
            )
            return
        taken = {
            target
            for config in self._problem.updater.materials
            if (target := self._problem.config_material_node(config)) is not None
        }
        free = next((material for material in design if material not in taken), None)
        if free is None:
            QMessageBox.information(
                self,
                "Material optimizer",
                "Every design material already has its own material optimizer.",
            )
            return
        self._problem.add_material_updater(free)
        self.rebuild(select=self._problem.updater)
        self.treeChanged.emit()

    def _remove_materials_updater(self, node: Node) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        index = node.config_index if isinstance(node, UpdaterTreeNode) else 0
        if 0 <= index < len(self._problem.updater.materials):
            del self._problem.updater.materials[index]
        self.rebuild(select=self._problem.updater)
        self.treeChanged.emit()

    def _add_part_interface(self, itype: str) -> None:
        if self._problem is None:
            return
        from ..schemes.base import get_template

        tpl = get_template(self._problem.scheme)
        name = self._problem.suggest_part_interface_name()
        interface = tpl.make_part_interface(itype, name=name)
        self._problem.add_part_interface(interface)
        self.rebuild(select=interface)
        self.treeChanged.emit()

    def _copy_part_interface(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartInterfaceNode):
            return
        copy = self._problem.clone_part_interface(interface)
        self.rebuild(select=copy)
        self.treeChanged.emit()

    def _remove_part_interface(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartInterfaceNode):
            return
        try:
            self._problem.remove_part_interface(interface)
        except ValueError:
            return  # keep at least one geometry interface
        self.rebuild()
        self.treeChanged.emit()

    def _move_part_interface(self, interface: Node, delta: int) -> None:
        if self._problem is None or not isinstance(interface, PartInterfaceNode):
            return
        if not self._problem.move_part_interface(interface, delta):
            return
        self.rebuild(select=interface)
        self.treeChanged.emit()

    def _add_instance(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartInterfaceNode):
            return
        name = self._problem.suggest_instance_name(interface)
        instance = InstanceNode(name=name)
        self._problem.add_instance(interface, instance)
        self.rebuild(select=instance)
        self.treeChanged.emit()

    def _remove_instance(self, instance: Node) -> None:
        if self._problem is None or not isinstance(instance, InstanceNode):
            return
        try:
            self._problem.remove_instance(instance)
        except ValueError:
            return
        self.rebuild()
        self.treeChanged.emit()

    def _add_surface(self, stype: str, owner: Node | None = None) -> None:
        if self._problem is None:
            return
        from ..schemes.base import get_template

        if owner is None:
            owner = self._problem.default_surface_part_node()
        if owner is None:
            return
        tpl = get_template(self._problem.scheme)
        index = len(owner.surfaces())
        srf = tpl.make_surface(stype, index)
        self._problem.add_surface(srf, interface=owner)
        self.rebuild(select=srf)
        self.treeChanged.emit()

    def _copy_surface(self, srf: Node) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        copy = self._problem.clone_surface(srf)
        self.rebuild(select=copy)
        self.treeChanged.emit()

    def _remove_surface(self, srf: Node) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        try:
            self._problem.remove_surface(srf)
        except ValueError:
            return  # keep at least one surface
        self.rebuild()
        self.treeChanged.emit()

    def _move_surface(self, srf: Node, delta: int) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        if not self._problem.move_surface(srf, delta):
            return
        self.rebuild(select=srf)
        self.treeChanged.emit()

    def _add_interface(self, itype: str) -> None:
        if self._problem is None:
            return
        from ..schemes.base import get_template

        tpl = get_template(self._problem.scheme)
        iface = tpl.make_interface(itype)
        spec = INTERFACE_TYPES.get(itype, {})
        iface.name = self._problem.suggest_interface_name(
            spec.get("name_hint", "load_")
        )
        self._problem.add_interface(iface)
        self.rebuild(select=iface)
        self.treeChanged.emit()

    def _add_material(self, material_type: str) -> None:
        if self._problem is None:
            return
        from ..schemes.base import get_template

        tpl = get_template(self._problem.scheme)
        material = tpl.make_material(material_type=material_type)
        self._problem.add_material(material)
        self.rebuild(select=material)
        self.treeChanged.emit()

    def _copy_material(self, material: Node) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        copy = self._problem.clone_material(material)
        self.rebuild(select=copy)
        self.treeChanged.emit()

    def _move_material(self, material: Node, delta: int) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        if not self._problem.move_material(material, delta):
            return
        self.rebuild(select=material)
        self.treeChanged.emit()

    def _remove_material(self, material: Node) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        try:
            self._problem.remove_material(material)
        except ValueError:
            return
        self.rebuild()
        self.treeChanged.emit()

    def _copy_interface(self, iface: Node) -> None:
        if self._problem is None or not isinstance(iface, InterfaceNode):
            return
        # a copied load is a new load: give it a fresh unique name so it does
        # not collide with the original (it starts unset / zero in the steps)
        itype = iface.interface_type
        hint = INTERFACE_TYPES.get(itype, {}).get("name_hint", "load_")
        copy = self._problem.clone_interface(iface, hint)
        self.rebuild(select=copy)
        self.treeChanged.emit()

    def _move_interface(self, iface: Node, delta: int) -> None:
        if self._problem is None or not isinstance(iface, InterfaceNode):
            return
        if not self._problem.move_interface(iface, delta):
            return
        self.rebuild(select=iface)
        self.treeChanged.emit()

    def _remove_interface(self, iface: Node) -> None:
        if self._problem is None or not isinstance(iface, InterfaceNode):
            return
        self._problem.remove_interface(iface)
        self.rebuild()
        self.treeChanged.emit()
