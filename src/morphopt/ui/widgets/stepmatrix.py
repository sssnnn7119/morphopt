"""Load-step matrix editor (edits the ``steps`` node)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from ..model.problem import StepsNode, ProblemDefinition
from ..application.editing import LoadCaseSession
from ..i18n import tr


class StepMatrix(QWidget):
    changed = Signal(object)   # steps Node

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(tr('ui.widgets.stepmatrix.load_steps')))
        self._nspin = QSpinBox()
        self._nspin.setRange(1, 200)
        self._nspin.valueChanged.connect(self._on_n_steps)
        bar.addWidget(self._nspin)
        for key, fn in [
                ("ui.widgets.stepmatrix.add_step", self._add_step),
                ("ui.widgets.stepmatrix.copy_selected_row", self._copy_selected_row),
                ("ui.widgets.stepmatrix.delete_selected_row", self._remove_selected_row)]:
            b = QPushButton(tr(key))
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)

        hint = QLabel(tr('ui.widgets.stepmatrix.amplitude_interfaces_rows_steps_empty_cells_keep_the_previous_value_zero'))
        hint.setStyleSheet("color:#7f8c8d; font-size:11px;")
        lay.addWidget(hint)

        self._table = QTableWidget()
        self._table.setMinimumHeight(220)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.cellChanged.connect(self._on_cell_changed)
        lay.addWidget(self._table, 1)

        self._node: StepsNode | None = None
        self._problem = None
        self._loading = False
        self._structure = None

    # ------------------------------------------------------------------ api
    def edit_node(self, node: StepsNode, problem: ProblemDefinition) -> None:
        self._node = node
        self._problem = problem
        self.session = LoadCaseSession(node, problem)
        self._nspin.blockSignals(True)
        self._nspin.setValue(int(node.num_steps))
        self._nspin.blockSignals(False)
        self._rebuild()

    # ------------------------------------------------------------- helpers
    def _rebuild(self) -> None:
        if self._node is None:
            return
        cols = self.session.columns()
        n = int(self._node.num_steps)
        signature = (id(self._node), n, tuple((id(interface), component, caption) for interface, component, caption in cols))
        if signature == self._structure:
            return
        self._structure = signature
        self._loading = True
        self._table.blockSignals(True)
        self._table.clear()
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels([h for _, _, h in cols])
        self._table.setRowCount(n)
        for s in range(n):
            for ci, (interface, comp, _h) in enumerate(cols):
                value = self.session.value(s, interface, comp)
                item = QTableWidgetItem(value if isinstance(value, str) else f"{value:.6g}")
                self._table.setItem(s, ci, item)
        self._table.blockSignals(False)
        self._loading = False

    # ------------------------------------------------------------- actions
    def _on_n_steps(self, n: int) -> None:
        if self._node is None:
            return
        self.session.resize(n)
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
        self.session.copy(r)
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
        self.session.remove(r)
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
        if self.session.set_value(r, c, item.text()):
            self.changed.emit(self._node)
