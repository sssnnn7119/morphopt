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
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu,
)
from PySide6.QtGui import QAction

from ..model.problem import (
    Node, ProblemDefinition, SurfaceNode, InterfaceNode,
)
from ..model.schemas import SURFACE_TYPES, INTERFACE_TYPES
from ..i18n import T, pick

#: containers that hold children we show in the tree
CONTAINER_ORDER = ["geometry", "loads_group", "material", "solver", "updater"]

#: Localized tree labels.  The parenthesized suffix is a generated-code
#: location, not a translation.
CONTAINER_TITLES_ZH = {
    "geometry": "几何（初始构型）",
    "loads_group": "载荷",
    "loads": "载荷定义",
    "steps": "载荷工况",
    "material": "材料",
    "objective": "优化目标",
    "solver": "求解器",
    "updater": "优化问题定义",
}
CONTAINER_TITLES_EN = {
    "geometry": "Geometry — Initial configuration",
    "loads_group": "Loads",
    "loads": "Load definition",
    "steps": "Load cases",
    "material": "Materials",
    "objective": "Optimization objective",
    "solver": "Solver",
    "updater": "Optimization definition",
}

CODE_REFERENCES = {
    "geometry": "GeometryParams",
    "loads_group": "FEAParams",
    "loads": "define_interface",
    "steps": "define_steps",
    "material": "MaterialParams",
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
    persisted problem tree.
    """

    def __init__(self, updater: Node, group: str) -> None:
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
        self.code_reference = (
            "UpdaterGeometries"
            if group.startswith("geometry") else
            "UpdaterMaterials"
        )

    @property
    def section_group(self) -> str:
        """Canonical updater section owning this navigation entry."""
        return "geometry" if self.group.startswith("geometry") else "materials"


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
    0-based index inside the Geometry node (0 = outer boundary, >= 1 = inner
    cavity).  The index comes from the current position, so moving a surface
    up/down renumbers it automatically.
    """
    st = srf.surface_type or "?"
    spec = SURFACE_TYPES.get(st, {})
    return f"{index}: {_short_phrase(spec, st)}"


def surface_index(problem: ProblemDefinition | None, srf: Node) -> int | None:
    """Return the 0-based position of ``srf`` inside the Geometry node."""
    if problem is None:
        return None
    for i, s in enumerate(problem.surfaces()):
        if s is srf:
            return i
    return None


class ModelTree(QTreeWidget):
    nodeSelected = Signal(object)   # Node
    treeChanged = Signal()          # structure edited

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
                    container_title("loads_group"), group_node, bold=True)
                self.addTopLevelItem(group_item)
                self._add_loads_children(group_item)
                continue
            node = self._problem.section(kind)
            if node is None:
                continue
            item = self._make_item(container_title(kind), node, bold=True)
            self.addTopLevelItem(item)
            if kind == "geometry":
                for i, srf in enumerate(self._problem.surfaces()):
                    it = self._make_item(self._surface_title(srf, i), srf)
                    item.addChild(it)
            elif kind == "updater":
                self._add_updater_children(item, node)
        self.expandAll()
        if select is not None:
            it = self._node_item.get(select)
            if it is None and select_key is not None:
                it = next(
                    (candidate_item for candidate_item, candidate_node in self._node_item.items()
                     if self._node_key(candidate_node) == select_key),
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
            elif node.kind == "surface":
                idx = surface_index(self._problem, node)
                if idx is not None:
                    item.setText(0, self._surface_title(node, idx))
            elif node.kind == "interface":
                item.setText(0, self._interface_title(node))
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
    def _updater_title(node: Node) -> str:
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
            return f"{label} ({node.code_reference})"
        return container_title("updater")

    @staticmethod
    def _node_key(node: Node | None):
        """Stable identity for transient updater entries across rebuilds."""
        if node is None:
            return None
        if hasattr(node, "updater_parent"):
            return (
                "updater",
                id(node.updater_parent),
                getattr(node, "group", None),
            )
        return ("node", id(node))

    def _add_updater_children(self, parent_item: QTreeWidgetItem,
                              updater: Node) -> None:
        """Render objective plus nested geometry/material updater groups."""
        if self._problem is not None and self._problem.objective is not None:
            objective = self._problem.objective
            objective_item = self._make_item(
                container_title("objective"), objective, bold=True)
            parent_item.addChild(objective_item)

        if updater.geometry_config() is not None:
            geometry_node = UpdaterTreeNode(updater, "geometry")
            geometry_item = self._make_item(
                self._updater_title(geometry_node), geometry_node, bold=True)
            parent_item.addChild(geometry_item)
            for group in ("geometry_objectives", "geometry_equality", "geometry_penalty"):
                child_node = UpdaterTreeNode(updater, group)
                child_item = self._make_item(
                    self._updater_title(child_node), child_node)
                geometry_item.addChild(child_item)

        if updater.materials_config() is not None:
            materials_node = UpdaterTreeNode(updater, "materials")
            materials_item = self._make_item(
                self._updater_title(materials_node), materials_node, bold=True)
            parent_item.addChild(materials_item)
            for group in ("materials_objectives", "materials_penalty"):
                child_node = UpdaterTreeNode(updater, group)
                child_item = self._make_item(
                    self._updater_title(child_node), child_node)
                materials_item.addChild(child_item)

    def _add_loads_children(self, parent_item: QTreeWidgetItem) -> None:
        """Render load definitions and load cases under the shared parent."""
        loads = self._problem.loads if self._problem is not None else None
        if loads is not None:
            loads_item = self._make_item(
                container_title("loads"), loads, bold=True)
            parent_item.addChild(loads_item)
            for iface in self._problem.interfaces():
                interface_item = self._make_item(
                    self._interface_title(iface), iface)
                loads_item.addChild(interface_item)

        steps = self._problem.steps if self._problem is not None else None
        if steps is not None:
            steps_item = self._make_item(
                container_title("steps"), steps, bold=True)
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

        if kind == "geometry" and scheme != "simp":
            sub = menu.addMenu(T("添加曲面 ▸", "Add surface ▸"))
            for stype, spec in SURFACE_TYPES.items():
                act = QAction(_full_label(spec, stype), sub)
                act.setData(stype)
                sub.addAction(act)
            sub.triggered.connect(lambda a: self._add_surface(a.data()))
            menu.addSeparator()

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
    def _add_surface(self, stype: str) -> None:
        if self._problem is None:
            return
        from ..schemes.base import get_template

        tpl = get_template(self._problem.scheme)
        index = len(self._problem.surfaces())
        srf = tpl.make_surface(stype, index)
        self._problem.add_surface(srf)
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
            spec.get("name_hint", "load_"))
        self._problem.add_interface(iface)
        self.rebuild(select=iface)
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
