"""Abaqus-like model tree for the problem definition.

Left-hand navigation + structure editing.  Context menus:

* ``geometry`` (shape/codesign): add a surface (outer/inner), surfaces can be
  deleted / reordered.
* ``loads``: add / delete load-interface entries.

Any structural change emits :attr:`treeChanged` so the workbench can refresh
the viewer and the read-only generated code.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu,
)
from PySide6.QtGui import QAction

from ..model.problem import Node, ProblemDefinition
from ..model.schemas import SURFACE_TYPES, INTERFACE_TYPES

#: containers that hold children we show in the tree
CONTAINER_ORDER = ["geometry", "loads", "steps", "material", "objective", "solver", "updater"]

CONTAINER_LABELS = {
    "geometry": "Geometry",
    "loads": "Loads",
    "steps": "Load steps",
    "material": "Materials",
    "objective": "Objective Function",
    "solver": "Solver",
    "updater": "Updater",
}


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
        self.rebuild()

    def rebuild(self, select: Node | None = None) -> None:
        self.clear()
        self._item_node.clear()
        self._node_item.clear()
        if self._problem is None:
            return
        # top-level containers present in the model root
        root = self._problem.root
        for kind in CONTAINER_ORDER:
            node = root.child(kind) if root.kind == "problem" else None
            # find direct child of root by kind
            if node is None:
                node = next((c for c in root.children if c.kind == kind), None)
            if node is None:
                continue
            item = self._make_item(CONTAINER_LABELS.get(kind, kind), node, bold=True)
            self.addTopLevelItem(item)
            if kind == "geometry":
                for srf in node.children:
                    it = self._make_item(self._surface_title(srf), srf)
                    item.addChild(it)
            elif kind == "loads":
                # one row per load; its parameters are edited in the right pane
                for iface in node.children:
                    it = self._make_item(self._interface_title(iface), iface)
                    item.addChild(it)
        self.expandAll()
        if select is not None:
            it = self._node_item.get(select)
            if it is not None:
                self.setCurrentItem(it)

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
    def _surface_title(srf: Node) -> str:
        st = srf.params.get("type", "?")
        spec = SURFACE_TYPES.get(st, {})
        r0 = srf.params.get("r0")
        rtxt = f", r0={r0}" if r0 is not None else ""
        return f"{srf.name or spec.get('label', st)}{rtxt}"

    @staticmethod
    def _interface_title(iface: Node) -> str:
        it = iface.params.get("type", "?")
        spec = INTERFACE_TYPES.get(it, {})
        label = spec.get("label", it)
        return f"{iface.name or label}  [{label}]"

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
            sub = menu.addMenu("Add surface")
            for stype, spec in SURFACE_TYPES.items():
                act = QAction(spec["label"], sub)
                act.setData(stype)
                sub.addAction(act)
            sub.triggered.connect(lambda a: self._add_surface(a.data()))
            menu.addSeparator()

        if kind == "surface":
            act_up = QAction("Move up", menu)
            act_up.triggered.connect(lambda: self._move_surface(node, -1))
            act_dn = QAction("Move down", menu)
            act_dn.triggered.connect(lambda: self._move_surface(node, 1))
            act_del = QAction("Delete surface", menu)
            act_del.triggered.connect(lambda: self._remove_surface(node))
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

        if kind == "loads":
            sub = menu.addMenu("添加载荷 ▸")
            for itype, spec in INTERFACE_TYPES.items():
                act = QAction(spec["label"], sub)
                act.setData(itype)
                sub.addAction(act)
            sub.triggered.connect(lambda a: self._add_interface(a.data()))

        if kind == "interface":
            act_up = QAction("Move up", menu)
            act_up.triggered.connect(lambda: self._move_interface(node, -1))
            act_dn = QAction("Move down", menu)
            act_dn.triggered.connect(lambda: self._move_interface(node, 1))
            act_del = QAction("Delete", menu)
            act_del.triggered.connect(lambda: self._remove_interface(node))
            menu.addAction(act_up)
            menu.addAction(act_dn)
            menu.addSeparator()
            menu.addAction(act_del)

    # --------------------------------------------------------------- edits
    def _geometry(self) -> Node:
        return next((n for n in self._problem.root.children if n.kind == "geometry"), None)

    def _add_surface(self, stype: str) -> None:
        geo = self._geometry()
        if geo is None:
            return
        from ..schemes.base import get_template

        tpl = get_template(self._problem.scheme)
        index = len([c for c in geo.children if c.kind == "surface"])
        srf = tpl.new_surface_node(stype, index)
        geo.add_child(srf)
        self._renumber_surfaces()
        self.rebuild(select=srf)
        self.treeChanged.emit()

    def _remove_surface(self, srf: Node) -> None:
        geo = self._geometry()
        if geo is None:
            return
        surfaces = [c for c in geo.children if c.kind == "surface"]
        if len(surfaces) <= 1:
            return  # keep at least one surface
        geo.remove_child(srf)
        self._renumber_surfaces()
        self.rebuild()
        self.treeChanged.emit()

    def _move_surface(self, srf: Node, delta: int) -> None:
        geo = self._geometry()
        if geo is None:
            return
        idx = geo.children.index(srf)
        new = idx + delta
        if new < 0 or new >= len(geo.children):
            return
        geo.children[idx], geo.children[new] = geo.children[new], geo.children[idx]
        self._renumber_surfaces()
        self.rebuild(select=srf)
        self.treeChanged.emit()

    def _renumber_surfaces(self) -> None:
        geo = self._geometry()
        if geo is None:
            return
        for i, child in enumerate([c for c in geo.children if c.kind == "surface"]):
            child.params["flip"] = i > 0

    def _loads(self) -> Node:
        return next((n for n in self._problem.root.children if n.kind == "loads"), None)

    def _unique_interface_name(self, hint: str) -> str:
        existing = {i.name for i in self._loads().children}
        n = 1
        while f"{hint}{n}" in existing:
            n += 1
        return f"{hint}{n}"

    def _add_interface(self, itype: str) -> None:
        loads = self._loads()
        if loads is None:
            return
        from ..schemes.base import get_template

        tpl = get_template(self._problem.scheme)
        iface = tpl.new_interface_node(itype)
        spec = INTERFACE_TYPES.get(itype, {})
        iface.name = self._unique_interface_name(spec.get("name_hint", "load_"))
        loads.add_child(iface)
        self.rebuild(select=iface)
        self.treeChanged.emit()

    def _move_interface(self, iface: Node, delta: int) -> None:
        loads = self._loads()
        if loads is None:
            return
        idx = loads.children.index(iface)
        new = idx + delta
        if new < 0 or new >= len(loads.children):
            return
        loads.children[idx], loads.children[new] = loads.children[new], loads.children[idx]
        self.rebuild(select=iface)
        self.treeChanged.emit()

    def _remove_interface(self, iface: Node) -> None:
        loads = self._loads()
        if loads is None:
            return
        loads.remove_child(iface)
        # remove references from the load-step matrix and jacobian_needed
        steps = next((n for n in self._problem.root.iter_nodes() if n.kind == "steps"), None)
        if steps is not None:
            for row in steps.params.get("step_values", []):
                row.pop(iface.name, None)
        obj = self._problem.node("objective")
        if obj is not None:
            jac = obj.params.get("jacobian_needed", [])
            obj.params["jacobian_needed"] = [x for x in jac if x != iface.name]
        self.rebuild()
        self.treeChanged.emit()
