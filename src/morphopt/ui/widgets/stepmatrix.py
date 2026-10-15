"""Load-step matrix editor (edits the ``steps`` node)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from ..model.problem import StepsNode, ProblemDefinition
from ..application.editing import LoadCaseSession
from ..i18n import tr
from ..refresh import RefreshContext
from ..presentation.labels import interface_title_text
from .collection_controls import ActionButton, AddButton


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
        bar.addStretch(1)
        self._copy_button = ActionButton(tr('ui.widgets.stepmatrix.copy_selected_row'), self._copy_selected_row)
        bar.addWidget(self._copy_button)
        self._delete_button = ActionButton(
            tr('ui.common.delete'), self._remove_selected_row, danger=True,
            tooltip=tr('ui.widgets.stepmatrix.delete_selected_row'),
        )
        bar.addWidget(self._delete_button)
        self._add_button = AddButton(self._add_step)
        self._add_button.setToolTip(tr('ui.widgets.stepmatrix.add_step'))
        bar.addWidget(self._add_button)
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

    def refresh_ui(self, context: RefreshContext) -> None:
        if context.problem.steps is not None:
            self.edit_node(context.problem.steps, context.problem)

    # ------------------------------------------------------------- helpers
    def _rebuild(self) -> None:
        if self._node is None:
            return
        cols = self.session.columns()
        n = int(self._node.num_steps)
        signature = (
            id(self._node), n,
            tuple(
                (id(interface), interface.interface_type, interface.custom_class, component, caption)
                for interface, component, caption in cols
            ),
        )
        rebuild = signature != self._structure
        self._structure = signature
        self._loading = True
        self._table.blockSignals(True)
        if rebuild:
            self._table.clear()
            self._table.setColumnCount(len(cols))
            self._table.setHorizontalHeaderLabels([h for _, _, h in cols])
            for column, (interface, _component, _caption) in enumerate(cols):
                self._table.horizontalHeaderItem(column).setToolTip(interface_title_text(interface))
            self._table.setRowCount(n)
        for s in range(n):
            for ci, (interface, comp, _h) in enumerate(cols):
                value = self.session.value(s, interface, comp)
                text = value if isinstance(value, str) else f"{value:.6g}"
                item = self._table.item(s, ci)
                if item is None:
                    self._table.setItem(s, ci, QTableWidgetItem(text))
                elif item.text() != text:
                    item.setText(text)
        self._table.blockSignals(False)
        self._loading = False
        self._delete_button.setEnabled(n > 1)
        self._add_button.setEnabled(n < self._nspin.maximum())
        self._copy_button.setEnabled(n < self._nspin.maximum())

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
