"""Load-step matrix editor (edits the ``steps`` node)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from ..model.problem import Node
from ..model.schemas import INTERFACE_TYPES
from ..i18n import T


class StepMatrix(QWidget):
    changed = Signal(object)   # steps Node

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(T("载荷工况：", "Load steps:")))
        self._nspin = QSpinBox()
        self._nspin.setRange(1, 200)
        self._nspin.valueChanged.connect(self._on_n_steps)
        bar.addWidget(self._nspin)
        for zh, en, fn in [
                ("添加工况", "Add step", self._add_step),
                ("复制选中行", "Copy selected row", self._copy_selected_row),
                ("删除选中行", "Delete selected row", self._remove_selected_row)]:
            b = QPushButton(T(zh, en))
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)

        hint = QLabel(T(
            "幅值载荷接口（行=工况）。空格沿用上一工况/置零。",
            "Amplitude interfaces (rows = steps). Empty cells keep the previous value / zero."))
        hint.setStyleSheet("color:#7f8c8d; font-size:11px;")
        lay.addWidget(hint)

        self._table = QTableWidget()
        self._table.setMinimumHeight(220)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.cellChanged.connect(self._on_cell_changed)
        lay.addWidget(self._table, 1)

        self._node: Node | None = None
        self._problem = None
        self._loading = False

    # ------------------------------------------------------------------ api
    def edit_node(self, node: Node, problem=None) -> None:
        self._node = node
        self._problem = problem
        self._nspin.blockSignals(True)
        self._nspin.setValue(int(node.num_steps))
        self._nspin.blockSignals(False)
        self._rebuild()

    # ------------------------------------------------------------- helpers
    def _amplitude_interfaces(self):
        if self._problem is None:
            return []
        return [
            (interface.name, INTERFACE_TYPES[interface.interface_type]["num_values"])
            for interface in self._problem.amplitude_interfaces()
        ]

    def _step_values(self) -> list[dict]:
        return list(self._node.step_values)

    def _value(self, step: int, name: str, comp: int):
        d = self._step_values()
        if step < len(d):
            amps = d[step].get(name)
            if amps is not None and comp < len(amps):
                return amps[comp]
        return 0.0

    def _rebuild(self) -> None:
        if self._node is None:
            return
        self._loading = True
        amps = self._amplitude_interfaces()
        # each column = (interface name, component index, header)
        cols: list[tuple[str, int, str]] = []
        for name, nv in amps:
            if nv == 1:
                cols.append((name, 0, name))
            else:
                for c in range(nv):
                    cols.append((name, c, f"{name}.{c}"))
        n = int(self._node.num_steps)
        self._table.blockSignals(True)
        self._table.clear()
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels([h for _, _, h in cols])
        self._table.setRowCount(n)
        for s in range(n):
            for ci, (name, comp, _h) in enumerate(cols):
                item = QTableWidgetItem(f"{self._value(s, name, comp):.6g}")
                self._table.setItem(s, ci, item)
        self._table.blockSignals(False)
        self._loading = False

    # ------------------------------------------------------------- actions
    def _on_n_steps(self, n: int) -> None:
        if self._node is None:
            return
        old = list(self._node.step_values)
        if n < len(old):
            old = old[:n]
        while len(old) < n:
            old.append({})   # empty dict -> interface amplitude zero/unset
        self._node.num_steps = n
        self._node.step_values = old
        self._rebuild()
        self.changed.emit(self._node)

    def _add_step(self):
        self._nspin.setValue(self._nspin.value() + 1)

    def _selected_row(self) -> int:
        """The currently selected row, or -1 when none is selected."""
        return self._table.currentRow()

    def _copy_selected_row(self):
        """Insert a copy of the selected row right below it."""
        if self._node is None or self._problem is None:
            return
        n = int(self._node.num_steps)
        r = self._selected_row()
        if r < 0:
            r = n - 1  # nothing selected -> treat the last row as the source
        if r < 0 or r >= n or n >= self._nspin.maximum():
            return
        vals = list(self._node.step_values)
        while len(vals) < n:
            vals.append({})
        src = dict(vals[r] or {})
        new_row = {k: list(v) for k, v in src.items()}
        newvals = list(vals)
        newvals.insert(r + 1, new_row)
        self._node.step_values = newvals
        self._node.num_steps = n + 1
        self._nspin.blockSignals(True)
        self._nspin.setValue(n + 1)
        self._nspin.blockSignals(False)
        self._rebuild()
        if r + 1 < self._table.rowCount():
            self._table.setCurrentCell(r + 1, 0)
        self.changed.emit(self._node)

    def _remove_selected_row(self):
        """Delete the selected row (keeps at least one load step)."""
        if self._node is None or self._problem is None:
            return
        n = int(self._node.num_steps)
        r = self._selected_row()
        if r < 0:
            r = n - 1
        if r < 0 or r >= n or n <= 1:
            return
        vals = list(self._node.step_values)
        while len(vals) < n:
            vals.append({})
        del vals[r]
        self._node.step_values = vals
        self._node.num_steps = n - 1
        self._nspin.blockSignals(True)
        self._nspin.setValue(n - 1)
        self._nspin.blockSignals(False)
        self._rebuild()
        # keep a sensible row selected after the deletion
        new_r = min(r, n - 2)
        if new_r >= 0:
            self._table.setCurrentCell(new_r, 0)
        self.changed.emit(self._node)

    # ------------------------------------------------------------- cells
    def _on_cell_changed(self, r: int, c: int) -> None:
        if self._loading or self._node is None:
            return
        item = self._table.item(r, c)
        if item is None:
            return
        try:
            value = float(item.text())
        except ValueError:
            return
        amps = self._amplitude_interfaces()
        name = None
        comp = 0
        idx = 0
        for nm, nv in amps:
            if idx + nv > c:
                name = nm
                comp = c - idx
                break
            idx += nv
        if name is None:
            return
        vals = list(self._node.step_values)
        while len(vals) <= r:
            vals.append({})
        row = dict(vals[r])
        try:
            itype = next(p.interface_type for p in self._problem.interfaces()
                         if p.name == name)
            nvals = INTERFACE_TYPES[itype].get("num_values", 1)
        except (StopIteration, KeyError):
            nvals = 1
        cur = list(row.get(name, [0.0] * nvals))
        while len(cur) <= comp:
            cur.append(0.0)
        cur[comp] = value
        row[name] = cur
        vals[r] = row
        self._node.step_values = vals
        self.changed.emit(self._node)
