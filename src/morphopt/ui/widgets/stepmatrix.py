"""Load-step matrix editor (edits the ``steps`` node)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
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
                ("删除工况", "Remove step", self._remove_step),
                ("复制上一步", "Copy previous", self._copy_previous),
                ("线性插值…", "Linear ramp…", self._ramp)]:
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
        self._nspin.setValue(int(node.params.get("num_steps", 1)))
        self._nspin.blockSignals(False)
        self._rebuild()

    # ------------------------------------------------------------- helpers
    def _amplitude_interfaces(self):
        if self._problem is None:
            return []
        out = []
        for nd in self._problem.interfaces():
            it = nd.params.get("type", "")
            nv = INTERFACE_TYPES.get(it, {}).get("num_values", 0)
            if nv and nd.name:
                out.append((nd.name, nv))
        return out

    def _step_values(self) -> list[dict]:
        return self._node.params.get("step_values") or []

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
        n = int(self._node.params.get("num_steps", 1))
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
        old = self._node.params.get("step_values") or []
        if n < len(old):
            old = old[:n]
        while len(old) < n:
            old.append({})   # empty dict -> interface amplitude zero/unset
        self._node.params["num_steps"] = n
        self._node.params["step_values"] = old
        self._rebuild()
        self.changed.emit(self._node)

    def _add_step(self):
        self._nspin.setValue(self._nspin.value() + 1)

    def _remove_step(self):
        self._nspin.setValue(max(1, self._nspin.value() - 1))

    def _copy_previous(self):
        n = int(self._node.params.get("num_steps", 1))
        if n < 2:
            return
        vals = self._node.params.get("step_values")
        if not vals:
            return
        newvals = list(vals)
        last = newvals[-2] if len(newvals) >= 2 else {}
        # grow newvals to n rows
        while len(newvals) < n - 1:
            newvals.append({})
        prev = dict(newvals[-1]) if len(newvals) >= 1 else {}
        newvals.append({k: list(v) for k, v in prev.items()})
        self._node.params["step_values"] = newvals[-n:]
        self._node.params["num_steps"] = n
        self._rebuild()
        self.changed.emit(self._node)

    def _ramp(self):
        ok = QMessageBox.getText(self, "Linear ramp", T(
            "从 0 线性增加到最后一列幅值？（y/n）",
            "Linearly ramp from 0 to the final column amplitude? (y/n)"))
        if not ok or not ok[1].lower().startswith("y"):
            return
        n = int(self._node.params.get("num_steps", 1))
        vals = self._node.params.get("step_values") or []
        if not vals or n < 2:
            return
        for name, amps in (vals[-1] or {}).items():
            if not isinstance(amps, (list, tuple)) or not amps:
                continue
            for s in range(n - 1):
                factor = (s + 1) / (n - 1) if n > 1 else 1.0
                scaled = [a * factor for a in amps]
                # ensure dict row exists
                vals[s] = {**vals[s], name: scaled}
        self._node.params["step_values"] = vals
        self._rebuild()
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
        vals = self._node.params.get("step_values") or []
        while len(vals) <= r:
            vals.append({})
        row = dict(vals[r])
        try:
            itype = next(p.params["type"] for p in self._problem.interfaces()
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
        self._node.params["step_values"] = vals
        self.changed.emit(self._node)
