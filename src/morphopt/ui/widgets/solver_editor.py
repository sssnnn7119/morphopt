"""Edit solver process devices and ordered load-case sequences per group."""

from __future__ import annotations

import math
from numbers import Real

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..application.devices import detect_devices
from ..application.editing import SolverTasks
from ..application.validation import DefinitionValidation
from ..application.values import parse_field
from ..i18n import tr
from ..model.problem import ProblemDefinition, SolverNode
from ..presentation.labels import node_title
from ..refresh import RefreshContext
from ..theme import theme_manager
from .collection_controls import ActionButton


class SolverEditor(QWidget):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self._heading = QLabel()
        self._heading.setProperty("textRole", "sectionHeading")
        lay.addWidget(self._heading)

        form = QFormLayout()
        self._numproc = QLineEdit()
        self._numproc.editingFinished.connect(self._on_numproc)
        form.addRow(tr("ui.widgets.solver_editor.processes_num_process"), self._numproc)
        lay.addLayout(form)

        process_title = QLabel(
            tr("ui.widgets.solver_editor.process_device_assignments")
        )
        process_title.setProperty("textRole", "sectionHeading")
        lay.addWidget(process_title)
        self._process_hint = QLabel(tr("ui.widgets.solver_editor.process_device_help"))
        self._process_hint.setProperty("textRole", "muted")
        self._process_hint.setWordWrap(True)
        lay.addWidget(self._process_hint)
        self._process_table = QTableWidget()
        self._process_table.setColumnCount(2)
        self._process_table.setHorizontalHeaderLabels(
            [
                tr("ui.widgets.solver_editor.process"),
                tr("ui.widgets.solver_editor.device"),
            ]
        )
        self._process_table.setColumnWidth(1, 160)
        lay.addWidget(self._process_table)
        self._devices = detect_devices()

        grp_title = QLabel(
            tr("ui.widgets.solver_editor.load_steps_process_task_groups")
        )
        grp_title.setProperty("textRole", "sectionHeading")
        lay.addWidget(grp_title)
        self._group_help = QLabel()
        self._group_help.setText(
            tr(
                "ui.widgets.solver_editor.load_steps_in_the_same_group_are_solved_sequentially_in_one_process_warm"
            )
        )
        self._group_help.setProperty("textRole", "muted")
        self._group_help.setWordWrap(True)
        lay.addWidget(self._group_help)
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(
            [
                tr("ui.widgets.solver_editor.process_group"),
                tr("ui.widgets.solver_editor.case_sequence"),
            ]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.setWordWrap(True)
        lay.addWidget(self._table, 1)

        self._node: SolverNode | None = None
        self._problem = None
        self._loading = False
        self._groups: list[list[str]] = []

    # ------------------------------------------------------------------ api
    def edit_node(self, node: SolverNode, problem: ProblemDefinition) -> None:
        self._node = node
        self._problem = problem
        self._heading.setText(node_title(problem, node))
        self.tasks = SolverTasks(node, problem)
        self._groups = self.tasks.groups()
        self._loading = True
        try:
            self._numproc.setText(str(node.get_field("num_process", 1)))
            self._fill_process_table()
            self._fill_task_table()
        finally:
            self._loading = False

    def refresh_ui(self, context: RefreshContext) -> None:
        if context.problem.solver is not None:
            self.edit_node(context.problem.solver, context.problem)

    # ------------------------------------------------------------- devices
    def _on_numproc(self) -> None:
        if self._loading or self._node is None:
            return
        text = self._numproc.text().strip()
        if not text:
            return
        value = parse_field(
            text,
            SolverNode.fields[0],
            helper_names=[item.name for item in self._problem.helper_variables],
        )
        self._node.set_field("num_process", value)
        count = self._resolve_process_count(value)
        if count is None:
            self._process_table.setEnabled(False)
            self._process_hint.setText(
                tr("ui.widgets.solver_editor.process_count_must_be_positive_integer")
            )
            self._emit()
            return
        self._process_table.setEnabled(True)
        self._process_hint.setText(tr("ui.widgets.solver_editor.process_device_help"))
        self._node.resize_process_devices(count)
        self._fill_process_table()
        self._emit()

    def _resolve_process_count(self, value: object) -> int | None:
        try:
            resolved = DefinitionValidation(self._problem).literal(str(value))
        except (SyntaxError, ValueError, ArithmeticError):
            return None
        if (
            isinstance(resolved, Real)
            and not isinstance(resolved, bool)
            and math.isfinite(resolved)
            and int(resolved) == resolved
            and resolved >= 1
        ):
            return int(resolved)
        return None

    def _fill_process_table(self) -> None:
        count = self._resolve_process_count(self._node.num_process)
        if count is None:
            self._process_table.setRowCount(0)
            self._process_table.setEnabled(False)
            self._process_hint.setText(
                tr("ui.widgets.solver_editor.process_count_must_be_positive_integer")
            )
            return
        self._node.resize_process_devices(count)
        self._process_table.setEnabled(True)
        self._process_hint.setText(tr("ui.widgets.solver_editor.process_device_help"))
        self._process_table.setRowCount(count)
        for index, device in enumerate(self._node.process_devices):
            process = QTableWidgetItem(
                tr("ui.widgets.solver_editor.process_value", value_0=index + 1)
            )
            process.setFlags(process.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._process_table.setItem(index, 0, process)
            selector = QComboBox(self._process_table)
            selector.addItem(tr("ui.widgets.solver_editor.cpu_device"), "cpu")
            for available in self._devices:
                if available != "cpu":
                    selector.addItem(available, available)
            if selector.findData(device) < 0:
                selector.addItem(device, device)
            selector.setCurrentIndex(selector.findData(device))
            selector.currentIndexChanged.connect(
                lambda _index, process_index=index, control=selector: (
                    self._on_process_device_changed(
                        process_index, control.currentData()
                    )
                )
            )
            self._process_table.setCellWidget(index, 1, selector)

    def _on_process_device_changed(self, index: int, device: str) -> None:
        if self._loading or self._node is None:
            return
        devices = list(self._node.process_devices)
        devices[index] = device
        self._node.set_field("process_devices", devices)
        self._emit()

    # ------------------------------------------------------------- tasks
    def _fill_task_table(self) -> None:
        self._loading = True
        try:
            self._table.setRowCount(len(self._groups))
            for group_index, cases in enumerate(self._groups):
                group_widget = QWidget(self._table)
                group_layout = QHBoxLayout(group_widget)
                group_layout.setContentsMargins(
                    *theme_manager.palette.layout.zero_margins
                )
                group_layout.addWidget(
                    QLabel(
                        tr(
                            "ui.widgets.solver_editor.process_group_value",
                            value_0=group_index + 1,
                        ),
                        group_widget,
                    )
                )
                group_up = ActionButton(
                    "↑",
                    lambda current=group_index: self._move_group(current, -1),
                    tooltip=tr("ui.common.move_up"),
                    parent=group_widget,
                )
                group_down = ActionButton(
                    "↓",
                    lambda current=group_index: self._move_group(current, 1),
                    tooltip=tr("ui.common.move_down"),
                    parent=group_widget,
                )
                group_up.setEnabled(group_index > 0)
                group_down.setEnabled(group_index + 1 < len(self._groups))
                group_layout.addWidget(group_up)
                group_layout.addWidget(group_down)
                self._table.setCellWidget(group_index, 0, group_widget)

                sequence = QWidget(self._table)
                sequence_layout = QVBoxLayout(sequence)
                sequence_layout.setContentsMargins(
                    *theme_manager.palette.layout.zero_margins
                )
                sequence_layout.setSpacing(
                    theme_manager.palette.layout.widgets.action_grid_spacing
                )
                for case_index, name in enumerate(cases):
                    case_widget = QWidget(sequence)
                    case_layout = QHBoxLayout(case_widget)
                    case_layout.setContentsMargins(
                        *theme_manager.palette.layout.zero_margins
                    )
                    case_layout.addWidget(
                        QLabel(
                            f"{case_index + 1}. {name}",
                            case_widget,
                        ),
                        1,
                    )
                    case_up = ActionButton(
                        "↑",
                        lambda g=group_index, c=case_index: self._move_case(g, c, -1),
                        tooltip=tr("ui.common.move_up"),
                        parent=case_widget,
                    )
                    case_down = ActionButton(
                        "↓",
                        lambda g=group_index, c=case_index: self._move_case(g, c, 1),
                        tooltip=tr("ui.common.move_down"),
                        parent=case_widget,
                    )
                    split = ActionButton(
                        tr("ui.widgets.solver_editor.split_case"),
                        lambda g=group_index, c=case_index: self._split_case(g, c),
                        tooltip=tr("ui.widgets.solver_editor.split_case"),
                        parent=case_widget,
                    )
                    case_up.setEnabled(case_index > 0)
                    case_down.setEnabled(case_index + 1 < len(cases))
                    split.setEnabled(len(cases) > 1)
                    case_layout.addWidget(case_up)
                    case_layout.addWidget(case_down)
                    case_layout.addWidget(split)
                    sequence_layout.addWidget(case_widget)

                add_case = QComboBox(sequence)
                add_case.addItem(tr("ui.widgets.solver_editor.add_or_move_case"), None)
                current = set(cases)
                step_values = (
                    self._problem.steps.step_values
                    if self._problem.steps is not None
                    else {}
                )
                for name in step_values:
                    if name not in current:
                        add_case.addItem(name, name)
                add_case.currentIndexChanged.connect(
                    lambda _index, g=group_index, control=add_case: (
                        self._move_case_to_group(g, control.currentData())
                    )
                )
                sequence_layout.addWidget(add_case)
                self._table.setCellWidget(group_index, 1, sequence)
            self._table.resizeRowsToContents()
        finally:
            self._loading = False

    def _move_group(self, group: int, delta: int) -> None:
        if self._loading or self._node is None:
            return
        target = group + delta
        if not 0 <= target < len(self._groups):
            return
        self._groups[group], self._groups[target] = (
            self._groups[target],
            self._groups[group],
        )
        self._commit_groups()

    def _move_case(self, group: int, case: int, delta: int) -> None:
        if self._loading or self._node is None:
            return
        cases = self._groups[group]
        target = case + delta
        if not 0 <= target < len(cases):
            return
        cases[case], cases[target] = cases[target], cases[case]
        self._commit_groups()

    def _move_case_to_group(self, target_group: int, name: str | None) -> None:
        if self._loading or self._node is None or name is None:
            return
        target = self._groups[target_group]
        for group in self._groups:
            if name in group:
                group.remove(name)
        self._groups = [group for group in self._groups if group]
        target.append(name)
        self._commit_groups()

    def _split_case(self, group: int, case: int) -> None:
        if self._loading or self._node is None or len(self._groups[group]) < 2:
            return
        name = self._groups[group].pop(case)
        self._groups.insert(group + 1, [name])
        self._commit_groups()

    def _commit_groups(self) -> None:
        self.tasks.assign_groups(self._groups)
        self._groups = self.tasks.groups()
        self._fill_task_table()
        self._emit()

    # ------------------------------------------------------------- misc
    def _emit(self) -> None:
        if self._node is not None:
            self.changed.emit(self._node)
