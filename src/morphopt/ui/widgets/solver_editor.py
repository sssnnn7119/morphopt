"""Solver editor: pick compute device(s), process count and how load steps
are grouped into solver tasks (processes).

* devices are auto-detected (cpu + torch.cuda devices) and offered as
  check boxes (multiple GPU devices are allowed).
* ``task_index_list`` groups load steps that should run sequentially inside
  the same process (so the next step warm-starts from the previous result);
  the default is one step per process.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QCheckBox,
    QSpinBox, QTableWidget, QTableWidgetItem, QComboBox, QPushButton,
    QMessageBox,
)

from ..model.problem import Node


def detect_devices() -> list[str]:
    """Return a list of usable devices: CPU plus any torch cuda devices."""
    devs = ["cpu"]
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                devs.append(f"cuda:{i}")
    except Exception:
        pass
    return devs


class SolverEditor(QWidget):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        hint = QLabel("设备（可多选 GPU；勾选 CPU 则只用 CPU）")
        hint.setStyleSheet("color:#7f8c8d;")
        form.addRow(hint)
        self._device_box = QHBoxLayout()
        self._device_checks: dict[str, QCheckBox] = {}
        for dev in detect_devices():
            cb = QCheckBox(dev)
            self._device_checks[dev] = cb
            cb.toggled.connect(self._on_devices_changed)
            self._device_box.addWidget(cb)
        self._device_box.addStretch(1)
        devhost = QWidget()
        devhost.setLayout(self._device_box)
        form.addRow("设备", devhost)

        self._numproc = QSpinBox()
        self._numproc.setRange(1, 64)
        self._numproc.valueChanged.connect(self._on_numproc)
        form.addRow("进程数 num_process", self._numproc)
        lay.addLayout(form)

        grp_title = QLabel("工况(载荷步) → 进程任务分组")
        grp_title.setStyleSheet("font-weight:600;")
        lay.addWidget(grp_title)
        help = QLabel("同组工况在同一个进程内先后求解，下一步用上一步结果（热启动）。"
                      "默认：每个工况各自一个进程。")
        help.setStyleSheet("color:#7f8c8d;")
        help.setWordWrap(True)
        lay.addWidget(help)
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["载荷步", "进程组号"])
        self._table.cellChanged.connect(self._on_cell)
        lay.addWidget(self._table, 1)

        self._node: Node | None = None
        self._problem = None
        self._loading = False

    # ------------------------------------------------------------------ api
    def edit_node(self, node: Node, problem) -> None:
        self._node = node
        self._problem = problem
        self._loading = True
        try:
            params = node.params
            self._numproc.setValue(int(params.get("num_process", 1)))
            gpus = list(params.get("gpus", []) or [])
            cpu_cb = self._device_checks.get("cpu")
            for name, cb in self._device_checks.items():
                cb.blockSignals(True)
                if name == "cpu":
                    cb.setChecked(not gpus)
                else:
                    cb.setChecked(name in gpus)
                cb.blockSignals(False)
            self._fill_task_table()
        finally:
            self._loading = False

    # ------------------------------------------------------------- devices
    def _on_numproc(self, value: int) -> None:
        if self._loading or self._node is None:
            return
        self._node.params["num_process"] = int(value)
        self._emit()

    def _on_devices_changed(self, *_a) -> None:
        if self._loading or self._node is None:
            return
        gpus = [name for name, cb in self._device_checks.items()
                if name != "cpu" and cb.isChecked()]
        cpu_cb = self._device_checks.get("cpu")
        # CPU and GPU devices are mutually exclusive: picking a GPU clears CPU,
        # clearing the last GPU falls back to CPU.
        for name, cb in self._device_checks.items():
            if name == "cpu":
                desired = not gpus
            else:
                desired = name in gpus
            if cb.isChecked() != desired:
                cb.blockSignals(True)
                cb.setChecked(desired)
                cb.blockSignals(False)
        self._node.params["gpus"] = gpus
        self._emit()

    # ------------------------------------------------------------- tasks
    def _n_steps(self) -> int:
        steps = next((n for n in self._problem.root.iter_nodes() if n.kind == "steps"), None)
        return int(steps.params.get("num_steps", 1)) if steps is not None else 1

    def _task_list(self) -> list[list[int]]:
        """task_index_list stored on the solver node, or default per-step."""
        return self._node.params.get("task_index_list")

    def _fill_task_table(self) -> None:
        n = self._n_steps()
        tl = self._task_list()
        # build step->group assignment
        assign: dict[int, int] = {}
        if tl:
            for gi, steps in enumerate(tl):
                for s in steps:
                    assign[s] = gi
        self._table.blockSignals(True)
        self._table.setRowCount(n)
        self._table.setColumnCount(2)
        for s in range(n):
            self._table.setItem(s, 0, QTableWidgetItem(f"step {s}"))
            self._table.setItem(s, 1, QTableWidgetItem(str(assign.get(s, s))))
        self._table.blockSignals(False)

    def _on_cell(self, r: int, c: int) -> None:
        if self._loading or c != 1:
            return
        item = self._table.item(r, c)
        if item is None:
            return
        try:
            gi = max(0, int(item.text()))
        except ValueError:
            return
        n = self._table.rowCount()
        groups: dict[int, list[int]] = {}
        for s in range(n):
            it = self._table.item(s, 1)
            g = gi if s == r else int(it.text())
            groups.setdefault(g, []).append(s)
        tl = [groups[k] for k in sorted(groups)]
        self._node.params["task_index_list"] = tl
        self._emit()

    # ------------------------------------------------------------- misc
    def _emit(self) -> None:
        if self._node is not None:
            self.changed.emit(self._node)
