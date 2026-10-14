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
    QLineEdit, QTableWidget, QTableWidgetItem,
)

from ..model.problem import SolverNode, ProblemDefinition
from ..i18n import tr
from ..application.devices import detect_devices
from ..application.editing import SolverTasks
from ..application.values import parse_field


class SolverEditor(QWidget):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        hint = QLabel(tr('ui.widgets.solver_editor.devices_multi_select_gpus_checking_cpu_uses_cpu_only'))
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
        form.addRow(tr('ui.widgets.solver_editor.devices'), devhost)

        self._numproc = QLineEdit()
        self._numproc.editingFinished.connect(self._on_numproc)
        form.addRow(tr('ui.widgets.solver_editor.processes_num_process'), self._numproc)
        lay.addLayout(form)

        grp_title = QLabel(tr('ui.widgets.solver_editor.load_steps_process_task_groups'))
        grp_title.setStyleSheet("font-weight:600;")
        lay.addWidget(grp_title)
        help = QLabel(tr('ui.widgets.solver_editor.load_steps_in_the_same_group_are_solved_sequentially_in_one_process_warm'))
        help.setStyleSheet("color:#7f8c8d;")
        help.setWordWrap(True)
        lay.addWidget(help)
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(
            [tr('ui.widgets.solver_editor.step'), tr('ui.widgets.solver_editor.process_group')])
        self._table.cellChanged.connect(self._on_cell)
        lay.addWidget(self._table, 1)

        self._node: SolverNode | None = None
        self._problem = None
        self._loading = False

    # ------------------------------------------------------------------ api
    def edit_node(self, node: SolverNode, problem: ProblemDefinition) -> None:
        self._node = node
        self._problem = problem
        self.tasks = SolverTasks(node, problem)
        self._loading = True
        try:
            self._numproc.setText(str(node.get_field("num_process", 1)))
            gpus = list(node.get_field("gpus", []) or [])
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
    def _on_numproc(self) -> None:
        if self._loading or self._node is None:
            return
        text = self._numproc.text().strip()
        if not text:
            return
        value = parse_field(text, {"type": "int"})
        self._node.set_field("num_process", value)
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
        self._node.set_field("gpus", gpus)
        self._emit()

    # ------------------------------------------------------------- tasks
    def _fill_task_table(self) -> None:
        assignments = self.tasks.assignments()
        n = len(assignments)
        self._table.blockSignals(True)
        self._table.setRowCount(n)
        self._table.setColumnCount(2)
        for s in range(n):
            self._table.setItem(s, 0, QTableWidgetItem(
                tr('ui.widgets.solver_editor.step_value', value_0=s)))
            self._table.setItem(s, 1, QTableWidgetItem(str(assignments[s])))
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
        try:
            assignments = [gi if row == r else int(self._table.item(
                row,
                1,
            ).text()) for row in range(self._table.rowCount())]
        except ValueError:
            return
        self.tasks.assign(assignments)
        self._emit()

    # ------------------------------------------------------------- misc
    def _emit(self) -> None:
        if self._node is not None:
            self.changed.emit(self._node)
