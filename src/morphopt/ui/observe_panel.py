"""In-window observer panel + controls (definition & observer share ONE window).

The definition page hands the finished problem here (:meth:`ObserverControls.
set_definition`).  Every run now starts from an explicit *task source* chosen
with button 0 · 选择任务来源:

* ``definition`` — fresh run of the problem from the definition page,
* ``py``         — fresh run of an existing runnable definition script (.py),
* ``continue``   — resume an existing result folder (last / chosen step).

Button 1 (开始/继续) is only enabled after a source is chosen; once a run
starts the source is consumed/reset, so after stopping you must choose the
source again via 0 (nothing can be started directly).  Progress is polled from
the result folder on disk (per *finished* iteration), so no queue / no extra
process is needed.  Button 2 (停止优化) terminates the job's whole process
group but keeps the current visualization for browsing.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QListWidget, QStackedWidget, QSplitter, QMessageBox, QFileDialog,
    QDialog, QCheckBox, QPlainTextEdit,
)

from .application import (
    OptimizationRunSession,
    ResultSession,
    RunSource,
    RunSourceKind,
    last_completed_iteration,
)
from .application.runs import RunProgress
from .i18n import tr
from .widgets.observation_pages import (
    DeformationCasePage, MetricsPage, UpdatableStructurePage,
)
from .widgets.run_dialogs import ContinueDialog, SourceDialog


# ---------------------------------------------------------------------------
# observer content (slider + left options + stacked pages)
# ---------------------------------------------------------------------------

class ObserverPanel(QWidget):
    """Embedded observer content, driven purely from the result folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = ResultSession()
        self._case_pages: dict[int, DeformationCasePage] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(30)
        self.btn_prev.clicked.connect(lambda: self._nudge(-1))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(1)
        self.slider.valueChanged.connect(self._on_slider)
        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(30)
        self.btn_next.clicked.connect(lambda: self._nudge(1))
        self.iter_label = QLabel("0 / 0")
        self.iter_label.setMinimumWidth(70)
        self.chk_follow = QCheckBox(tr('ui.observe_panel.follow_latest'))
        self.chk_follow.setChecked(True)
        self.chk_follow.toggled.connect(self._on_follow)
        top.addWidget(self.btn_prev)
        top.addWidget(self.slider, 1)
        top.addWidget(self.btn_next)
        top.addWidget(self.iter_label)
        top.addWidget(self.chk_follow)
        outer.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.options = QListWidget()
        self.options.setFixedWidth(160)
        self.options.addItem(tr('ui.observe_panel.metrics'))
        self.options.addItem(tr('ui.observe_panel.updatable_structures'))
        self.options.currentRowChanged.connect(self._on_option)
        split.addWidget(self.options)

        self.stack = QStackedWidget()
        self._metrics_page = MetricsPage()
        self._updatable_structure_page = UpdatableStructurePage()
        self.stack.addWidget(self._metrics_page)
        self.stack.addWidget(self._updatable_structure_page)
        split.addWidget(self.stack)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([160, 1100])
        outer.addWidget(split, 1)
        self.options.setCurrentRow(0)

    @property
    def path_result(self) -> str | None:
        return self._results.folder

    @property
    def iteration(self) -> int:
        return self._results.iteration

    # ------------------------------------------------------------------ api
    def ensure_loaded(self, folder: str) -> bool:
        """Bind the controller/params for a folder once (no rendering yet)."""
        if self.path_result != str(Path(folder).resolve()):
            self.reset()
        return self._results.bind(folder)

    def show_iteration(self, folder: str, iteration: int) -> None:
        """Render one finished iteration (history + current option page)."""
        try:
            history = self._results.load_iteration(folder, iteration)
        except Exception as exc:
            print(f"history load failed: {exc}")
            return
        self._metrics_page.update_from_history(history, iteration)
        self._discover_cases(folder)

        max_iter = max(1, int(history.iteration or iteration))
        self.slider.blockSignals(True)
        self.slider.setMaximum(max_iter)
        if self.chk_follow.isChecked():
            self.slider.setValue(max_iter)
        self.slider.blockSignals(False)
        self.iter_label.setText(f"{self.slider.value()} / {max_iter}")

        row = self.options.currentRow()
        if row == 1:
            self._refresh_updatable_structure()
        elif row >= 2:
            self._refresh_case(self.options.item(row).data(Qt.ItemDataRole.UserRole))

    def reset(self) -> None:
        """Drop every result-dependent piece of content.

        Called when a fresh (non-result) task source is chosen, so the viewer
        no longer keeps showing the previously browsed result.
        """
        self._results.reset()
        # remove dynamic load-case pages and their option rows
        for row in reversed(range(2, self.stack.count())):
            w = self.stack.widget(row)
            self.stack.removeWidget(w)
            w.deleteLater()
        self._case_pages = {}
        while self.options.count() > 2:
            self.options.takeItem(self.options.count() - 1)
        self.options.setCurrentRow(0)
        self.slider.blockSignals(True)
        self.slider.setMaximum(1)
        self.slider.setValue(1)
        self.slider.blockSignals(False)
        self.iter_label.setText("0 / 1")
        self._metrics_page.clear()
        self._updatable_structure_page.clear_view()

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the panel's static texts."""
        self.chk_follow.setText(tr('ui.observe_panel.follow_latest'))
        self.options.item(0).setText(tr('ui.observe_panel.metrics'))
        self.options.item(1).setText(tr('ui.observe_panel.updatable_structures'))
        self._metrics_page.apply_language()
        self._updatable_structure_page.apply_language()
        for row, case in enumerate(list(self._case_pages.keys())):
            if self.options.count() > row + 2:
                self.options.item(row + 2).setText(f"{tr('ui.observe_panel.case')} {case}")
        row = self.options.currentRow()
        if row == 1:
            self._refresh_updatable_structure()

    # -------------------------------------------------------------- options
    def _on_option(self, row: int) -> None:
        if row < 0 or row >= self.stack.count():
            return
        if row == 1:
            self._refresh_updatable_structure()
        elif row >= 2:
            self._refresh_case(self.options.item(row).data(Qt.ItemDataRole.UserRole))
        self.stack.setCurrentIndex(row)

    def _refresh_updatable_structure(self) -> None:
        if self.path_result and self._results.params is not None:
            self._updatable_structure_page.build(
                self._results, self.slider.value()
            )

    def _refresh_case(self, case: int) -> None:
        page = self._case_pages.get(case)
        if page is not None and self.path_result:
            page.build(self._results, self.slider.value())

    def _nudge(self, delta: int) -> None:
        self.slider.setValue(self.slider.value() + delta)

    def _on_follow(self, checked: bool) -> None:
        if checked and self.path_result:
            self.slider.setValue(self.slider.maximum())

    def _on_slider(self, value: int) -> None:
        self.iter_label.setText(f"{value} / {self.slider.maximum()}")
        if self.slider.maximum() > 0:
            row = self.options.currentRow()
            if row == 1:
                self._refresh_updatable_structure()
            elif row >= 2:
                self._refresh_case(self.options.item(row).data(Qt.ItemDataRole.UserRole))

    def _discover_cases(self, folder: str) -> None:
        found = set(self._results.deformation_cases())
        existing = set(self._case_pages)
        for case in sorted(found - existing):
            self._case_pages[case] = DeformationCasePage(case)
            self.stack.addWidget(self._case_pages[case])
            self.options.addItem(f"{tr('ui.observe_panel.case')} {case}")
            self.options.item(self.options.count() - 1).setData(Qt.ItemDataRole.UserRole, case)


# ---------------------------------------------------------------------------
# observer page: buttons 0/1/2 + polling + job control
# ---------------------------------------------------------------------------

class ObserverControls(QWidget):
    """Definition/observer bridge: 0·选择任务来源, 1·开始/继续, 2·停止."""

    backRequested = Signal()
    outputReceived = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._run = OptimizationRunSession()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # top control bar ---------------------------------------------------
        bar = QHBoxLayout()
        self.btn_open = QPushButton(tr('ui.observe_panel.0_choose_source'))
        self.btn_open.setToolTip(tr('ui.observe_panel.choose_a_task_source_current_definition_a_definition_script_py_or_an_exi'))
        self.btn_open.clicked.connect(self._choose_source)
        bar.addWidget(self.btn_open)
        self.btn_start = QPushButton(tr('ui.observe_panel.1_start'))
        self.btn_start.setToolTip(tr('ui.observe_panel.enabled_after_choosing_a_source_via_0_the_source_is_reset_once_a_run_sta'))
        self.btn_start.clicked.connect(self._start)
        bar.addWidget(self.btn_start)
        self.btn_stop = QPushButton(tr('ui.observe_panel.2_stop'))
        self.btn_stop.setToolTip(tr('ui.observe_panel.stop_the_running_task_keeping_the_current_visualization_continue_require'))
        self.btn_stop.clicked.connect(self._stop)
        bar.addWidget(self.btn_stop)
        self.status = QLabel("")
        self.status.setStyleSheet("color:#9aa4b2;")
        bar.addWidget(self.status, 1)
        outer.addLayout(bar)

        content = QSplitter(Qt.Orientation.Vertical)
        self.panel = ObserverPanel()
        content.addWidget(self.panel)

        output_area = QWidget()
        output_layout = QVBoxLayout(output_area)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_header = QHBoxLayout()
        self.output_label = QLabel(tr('ui.observe_panel.run_output'))
        output_header.addWidget(self.output_label)
        output_header.addStretch(1)
        self.btn_clear_output = QPushButton(tr('ui.observe_panel.clear'))
        self.btn_clear_output.clicked.connect(self._clear_output)
        output_header.addWidget(self.btn_clear_output)
        output_layout.addLayout(output_header)
        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output_view.setMaximumBlockCount(10_000)
        self.output_view.setPlaceholderText(tr('ui.observe_panel.standard_output_and_errors_from_optimization_tasks_appear_here'))
        output_layout.addWidget(self.output_view, 1)
        content.addWidget(output_area)
        content.setStretchFactor(0, 5)
        content.setStretchFactor(1, 1)
        content.setSizes([700, 180])
        outer.addWidget(content, 1)

        # bottom-right: back to the definition page (mirrors the definition
        # footer's right-aligned ▶ 进入优化器 button)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.btn_back = QPushButton(tr('ui.observe_panel.back_to_definition'))
        self.btn_back.setToolTip(tr('ui.observe_panel.return_to_the_definition_page_running_tasks_ask_for_confirmation'))
        self.btn_back.setStyleSheet(
            "background-color:#37474f; font-weight:600; padding:6px 18px;")
        self.btn_back.clicked.connect(self._on_back)
        foot.addWidget(self.btn_back)
        outer.addLayout(foot)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll_once)
        self.outputReceived.connect(self._append_process_output)
        self._update_buttons()
        self._refresh_status()

    # ------------------------------------------------------------------ api
    def is_running(self) -> bool:
        """Whether an optimization task is currently running."""
        return self._run.active

    def set_definition(self, problem) -> None:
        self._timer.stop()
        self._run.set_definition(problem)
        self.panel.reset()
        self.status.setText(tr(
            'ui.observe_panel.definition_ready_value_click_0_to_choose_a_source',
            value_0=problem.label,
        ))
        self._update_buttons()

    # ------------------------------------------------------------- buttons
    def _on_back(self) -> None:
        """Return to the definition page.

        If an optimization is still running, ask for confirmation first —
        going back terminates the worker process (no silent interruption).
        """
        if self._run.active:
            ret = QMessageBox.warning(
                self, tr('ui.observe_panel.back_to_definition_04d64f97'),
                tr('ui.observe_panel.the_optimization_is_still_running_returning_to_the_definition_page_will'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                return
            self._stop_job()
        self.backRequested.emit()

    def _choose_source(self) -> None:
        """Button 0: pick where the next optimization run comes from."""
        if self._run.active:
            return
        dlg = SourceDialog(has_definition=self._run.definition is not None, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        kind = dlg.chosen()
        if kind is RunSourceKind.DEFINITION:
            self._set_definition_source()
        elif kind is RunSourceKind.PYTHON:
            self._pick_py_source()
        elif kind is RunSourceKind.CONTINUE:
            self._pick_continue_source()
        self._update_buttons()

    def _set_definition_source(self) -> None:
        problem = self._run.definition
        if problem is None:
            QMessageBox.information(
                self,
                tr('ui.observe_panel.no_definition'),
                tr('ui.observe_panel.build_a_problem_on_the_definition_page_and_enter_the_observer'),
            )
            return
        self._run.select_source(RunSource(RunSourceKind.DEFINITION, label=problem.label))
        self.panel.reset()
        self._refresh_status()
        self._update_buttons()

    def _pick_py_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr('ui.observe_panel.select_definition_script_py'),
            os.getcwd(),
            "Python (*.py)",
        )
        if path:
            self._run.select_source(RunSource(RunSourceKind.PYTHON, path=path))
            self.panel.reset()
            self._refresh_status()

    def _pick_continue_source(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            tr('ui.observe_panel.select_result_folder_continue'),
            os.getcwd(),
        )
        if not folder:
            return
        try:
            self._run.select_source(RunSource(RunSourceKind.CONTINUE, path=folder, label=os.path.basename(folder)))
        except ValueError as exc:
            QMessageBox.warning(self, tr('ui.observe_panel.invalid_result'), str(exc))
            return
        self._show_progress(self._run.poll())
        self._refresh_status()

    def _refresh_status(self) -> None:
        """Status line for the current source / idle state."""
        src = self._run.source
        if src is not None:
            self.status.setText(self._source_status(src))
            return
        if self._run.active:
            return  # running-status lines are set by the run methods
        if self._run.definition is not None:
            self.status.setText(tr('ui.observe_panel.no_task_source_yet_click_0_to_choose'))
        else:
            self.status.setText(tr('ui.observe_panel.no_definition_received_build_a_problem_first'))

    def _start(self) -> None:
        if self._run.active:
            return
        source = self._run.source
        if source is None:
            self.status.setText(tr('ui.observe_panel.click_0_to_choose_a_task_source_first'))
            return
        target = None
        if source.kind is RunSourceKind.CONTINUE:
            dialog = ContinueDialog(max_step=last_completed_iteration(source.path), parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            target = dialog.target_iteration()
        try:
            self._run.start_selected(target)
        except Exception as exc:
            key = 'ui.observe_panel.continue_failed' if source.kind is RunSourceKind.CONTINUE else 'ui.observe_panel.launch_failed'
            QMessageBox.warning(self, tr(key), str(exc))
            return
        self.output_view.clear()
        self._run.stream_output(self.outputReceived.emit)
        if source.kind is RunSourceKind.CONTINUE:
            self.status.setText(tr(
                'ui.observe_panel.continuing_optimization_from_step_value',
                value_0=target or last_completed_iteration(source.path),
            ))
        elif source.kind is RunSourceKind.DEFINITION:
            self.status.setText(tr('ui.observe_panel.starting_optimization_from_scratch_waiting_for_the_first_step'))
        else:
            self.status.setText(tr(
                'ui.observe_panel.optimizing_from_value_waiting_for_the_first_step',
                value_0=os.path.basename(source.path),
            ))
        self._timer.start()
        self._update_buttons()

    def _stop(self) -> None:
        self._stop_job()
        if self._run.folder:
            self.status.setText(tr('ui.observe_panel.optimization_stopped_current_visualization_kept_to_continue_choose_the_r'))
        else:
            self.status.setText(tr('ui.observe_panel.optimization_stopped_choose_a_source_via_0_to_run_again'))
        self._update_buttons()

    def _stop_job(self) -> None:
        if self._run.active:
            self._run.stop()
            self._timer.stop()
            self._show_progress(self._run.poll())
        self._update_buttons()

    # ------------------------------------------------------------ run output
    def _clear_output(self) -> None:
        self.output_view.clear()
        self._run.log.clear()

    def _append_process_output(self, run_id: int, text: str) -> None:
        line = self._run.consume_output(run_id, text)
        if line is not None:
            self.output_view.appendPlainText(line)

    # -------------------------------------------------------------- polling
    def _poll_once(self) -> None:
        if not self._run.active:
            return
        progress = self._run.poll()
        self._show_progress(progress)
        if progress.finished:
            self._timer.stop()
            self.status.setText(tr('ui.observe_panel.optimization_finished_choose_a_source_via_0_to_run_again'))
            self._update_buttons()
        elif progress.changed and progress.iteration:
            self.status.setText(tr(
                'ui.observe_panel.optimization_running_step_value_completed',
                value_0=progress.iteration,
            ))

    def _show_progress(self, progress: RunProgress) -> None:
        if progress.folder is None:
            return
        if self.panel.path_result != progress.folder:
            self.panel.ensure_loaded(progress.folder)
        if progress.iteration >= 1 and (progress.changed or self.panel.iteration != progress.iteration):
            self.panel.show_iteration(progress.folder, progress.iteration)

    def _update_buttons(self) -> None:
        running = self._run.active
        src = self._run.source
        self.btn_open.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        if src is not None and src.kind is RunSourceKind.CONTINUE:
            self.btn_start.setText(tr('ui.observe_panel.1_continue'))
        else:
            self.btn_start.setText(tr('ui.observe_panel.1_start'))
        self.btn_start.setEnabled(not running and src is not None)

    @staticmethod
    def _source_status(source: RunSource) -> str:
        if source.kind is RunSourceKind.DEFINITION:
            return tr('ui.observe_panel.current_task_fresh_run_definition_value', value_0=source.label)
        if source.kind is RunSourceKind.PYTHON:
            filename = os.path.basename(source.path)
            return tr('ui.observe_panel.current_task_fresh_run_script_value', value_0=filename)
        return tr('ui.observe_panel.current_task_continue_result_value', value_0=source.label)

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the observer's static texts."""
        self.btn_open.setText(tr('ui.observe_panel.0_choose_source'))
        self.btn_open.setToolTip(tr('ui.observe_panel.choose_a_task_source_current_definition_a_definition_script_py_or_an_exi'))
        self.btn_start.setToolTip(tr('ui.observe_panel.enabled_after_choosing_a_source_via_0_the_source_is_reset_once_a_run_sta'))
        self.btn_stop.setText(tr('ui.observe_panel.2_stop'))
        self.btn_stop.setToolTip(tr('ui.observe_panel.stop_the_running_task_keeping_the_current_visualization_continue_require'))
        self.btn_back.setText(tr('ui.observe_panel.back_to_definition'))
        self.btn_back.setToolTip(tr('ui.observe_panel.return_to_the_definition_page_running_tasks_ask_for_confirmation'))
        self.output_label.setText(tr('ui.observe_panel.run_output'))
        self.btn_clear_output.setText(tr('ui.observe_panel.clear'))
        self.output_view.setPlaceholderText(tr('ui.observe_panel.standard_output_and_errors_from_optimization_tasks_appear_here'))
        self.panel.apply_language()
        self._update_buttons()
        if self._run.active:
            self.status.setText(tr('ui.observe_panel.optimization_running'))
        else:
            self._refresh_status()

    def close_cleanup(self) -> None:
        self._stop_job()
