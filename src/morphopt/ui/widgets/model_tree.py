"""Abaqus-like model tree for the problem definition.

Left-hand navigation + structure editing.  Context menus:

* ``geometry`` (shape/codesign): add a surface (outer/inner), surfaces can be
  deleted / reordered.
* ``loads``: add / delete load-interface entries.

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
CONTAINER_ORDER = ["geometry", "loads", "steps", "material", "objective", "solver", "updater"]

#: top-level container row titles: 中文 (带英文括号) / 纯英文 (English mode).
CONTAINER_TITLES_ZH = {
    "geometry": "几何 (Geometry)",
    "loads": "载荷 (Loads)",
    "steps": "载荷工况 (Load steps)",
    "material": "材料 (Materials)",
    "objective": "目标函数 (Objective)",
    "solver": "求解器 (Solver)",
    "updater": "更新器 (Updater)",
}
CONTAINER_TITLES_EN = {
    "geometry": "Geometry",
    "loads": "Loads",
    "steps": "Load steps",
    "material": "Materials",
    "objective": "Objective function",
    "solver": "Solver",
    "updater": "Updater",
}


def container_title(kind: str) -> str:
    """Localized title of one top-level container row in the model tree."""
    return pick(CONTAINER_TITLES_ZH.get(kind, kind), CONTAINER_TITLES_EN.get(kind))


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
        self.clear()
        self._item_node.clear()
        self._node_item.clear()
        if self._problem is None:
            return
        # Top-level sections are supplied by the model aggregate; the widget
        # only turns them into rows.
        for kind in CONTAINER_ORDER:
            node = self._problem.section(kind)
            if node is None:
                continue
            item = self._make_item(container_title(kind), node, bold=True)
            self.addTopLevelItem(item)
            if kind == "geometry":
                for i, srf in enumerate(self._problem.surfaces()):
                    it = self._make_item(self._surface_title(srf, i), srf)
                    item.addChild(it)
            elif kind == "loads":
                # one row per load; its parameters are edited in the right pane
                for iface in self._problem.interfaces():
                    it = self._make_item(self._interface_title(iface), iface)
                    item.addChild(it)
        self.expandAll()
        if select is not None:
            it = self._node_item.get(select)
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
