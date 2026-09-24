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
import re
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QListWidget, QStackedWidget, QSplitter, QMessageBox, QFileDialog,
    QDialog, QCheckBox, QPlainTextEdit,
)

from .application import (
    OptimizationRunSession,
    ProblemLibrary,
    ResultSession,
    RunMode,
    RunSource,
    RunSourceKind,
    last_completed_iteration,
)
from .i18n import T
from .widgets.observation_pages import (
    DeformationCasePage, MetricsPage, UpdatableStructurePage,
)
from .widgets.run_dialogs import ContinueDialog, SourceDialog


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# The optimization worker writes to a real terminal when run directly.  Its
# color and cursor-control sequences need to be removed before sending text to
# a QPlainTextEdit, which is deliberately not a terminal emulator.
_ANSI_CONTROL_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[@-_])")
_CURSOR_MOTION_RE = re.compile(r"\x1b\[[0-9;]*[ABEFG]")


def _clean_terminal_line(text: str) -> tuple[str, bool]:
    """Return printable text and whether it came from a terminal redraw."""
    is_redraw = bool(_CURSOR_MOTION_RE.search(text))
    text = _ANSI_CONTROL_RE.sub("", text).replace("\r\n", "\n")
    # A lone carriage return means "overwrite this terminal line".  Preserve
    # only the final value, which is the meaningful one in a static log.
    if "\r" in text:
        text = text.rsplit("\r", 1)[-1]
    return text.rstrip("\n"), is_redraw


def _is_progress_header(line: str) -> bool:
    """Recognize the compact iteration-table header used by the FEA solver."""
    words = line.strip().lower().split()
    return len(words) >= 3 and words[0] == "iter" and "total" in words

# ---------------------------------------------------------------------------
# observer content (slider + left options + stacked pages)
# ---------------------------------------------------------------------------

class ObserverPanel(QWidget):
    """Embedded observer content, driven purely from the result folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = ResultSession()
        self.path_result: str | None = None
        self.iteration = 0
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
        self.chk_follow = QCheckBox(T("自动跟踪最新", "Follow latest"))
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
        self.options.addItem(T("优化指标", "Metrics"))
        self.options.addItem(T("可更新结构展示", "Updatable structures"))
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

    # ------------------------------------------------------------------ api
    def ensure_loaded(self, folder: str) -> bool:
        """Bind the controller/params for a folder once (no rendering yet)."""
        loaded = self._results.bind(folder)
        self.path_result = self._results.folder
        return loaded

    def show_iteration(self, folder: str, iteration: int) -> None:
        """Render one finished iteration (history + current option page)."""
        self.iteration = iteration
        try:
            history = self._results.load_iteration(folder, iteration)
        except Exception as exc:
            print(f"history load failed: {exc}")
            return
        self.path_result = self._results.folder
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
        elif row >= 2 and row - 2 in self._case_pages:
            self._refresh_case(row - 2)

    def reset(self) -> None:
        """Drop every result-dependent piece of content.

        Called when a fresh (non-result) task source is chosen, so the viewer
        no longer keeps showing the previously browsed result.
        """
        self.path_result = None
        self.iteration = 0
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
        self.chk_follow.setText(T("自动跟踪最新", "Follow latest"))
        self.options.item(0).setText(T("优化指标", "Metrics"))
        self.options.item(1).setText(T("可更新结构展示", "Updatable structures"))
        self._metrics_page.apply_language()
        self._updatable_structure_page.apply_language()
        for row, case in enumerate(list(self._case_pages.keys())):
            if self.options.count() > row + 2:
                self.options.item(row + 2).setText(f"{T('工况', 'Case')} {case}")
        row = self.options.currentRow()
        if row == 1:
            self._refresh_updatable_structure()

    # -------------------------------------------------------------- options
    def _on_option(self, row: int) -> None:
        if row < 0 or row >= self.stack.count():
            return
        if row == 1:
            self._refresh_updatable_structure()
        elif row >= 2 and row - 2 in self._case_pages:
            self._refresh_case(row - 2)
        self.stack.setCurrentIndex(row)

    def _refresh_updatable_structure(self) -> None:
        if self.path_result and self._results.params is not None:
            self._updatable_structure_page.build(
                self._results.params, self.path_result, self.slider.value()
            )

    def _refresh_case(self, case: int) -> None:
        page = self._case_pages.get(case)
        if page is not None and self.path_result:
            page.build(self.path_result, self.slider.value())

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
                self._refresh_case(row - 2)

    def _discover_cases(self, folder: str) -> None:
        found = set(self._results.deformation_cases())
        existing = set(self._case_pages)
        for case in sorted(found - existing):
            self._case_pages[case] = DeformationCasePage(case)
            self.stack.addWidget(self._case_pages[case])
            self.options.addItem(f"{T('工况', 'Case')} {case}")


# ---------------------------------------------------------------------------
# observer page: buttons 0/1/2 + polling + job control
# ---------------------------------------------------------------------------

class ObserverControls(QWidget):
    """Definition/observer bridge: 0·选择任务来源, 1·开始/继续, 2·停止."""

    backRequested = Signal()
    outputReceived = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._problem = None
        self._run = OptimizationRunSession()
        self._last_shown = 0
        self._saved_def = set()  # result folders whose definition (.morph) was written
        self._source: RunSource | None = None
        self._save_morph_def = True              # write companion .morph for definition runs
        self._output_run_id = 0
        self._progress_headers: set[str] = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # top control bar ---------------------------------------------------
        bar = QHBoxLayout()
        self.btn_open = QPushButton(T("0 · 选择任务来源…", "0 · Choose source…"))
        self.btn_open.setToolTip(T(
            "选择任务来源：当前定义 / 已有定义脚本 (.py) / 已有结果续跑。",
            "Choose a task source: current definition, a definition script "
            "(.py), or an existing result to continue."))
        self.btn_open.clicked.connect(self._choose_source)
        bar.addWidget(self.btn_open)
        self.btn_start = QPushButton(T("1 · 开始优化", "1 · Start"))
        self.btn_start.setToolTip(T(
            "先点击 0 选择任务来源后可用；运行开始后来源即重置，需重新选择。",
            "Enabled after choosing a source via 0; the source is reset once "
            "a run starts, so choose again for another run."))
        self.btn_start.clicked.connect(self._start)
        bar.addWidget(self.btn_start)
        self.btn_stop = QPushButton(T("2 · 停止优化", "2 · Stop"))
        self.btn_stop.setToolTip(T(
            "终止当前优化任务，但保留当前可视化；续跑需重新选择来源。",
            "Stop the running task, keeping the current visualization; "
            "continue requires choosing the source again."))
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
        self.output_label = QLabel(T("运行输出", "Run output"))
        output_header.addWidget(self.output_label)
        output_header.addStretch(1)
        self.btn_clear_output = QPushButton(T("清空", "Clear"))
        self.btn_clear_output.clicked.connect(self._clear_output)
        output_header.addWidget(self.btn_clear_output)
        output_layout.addLayout(output_header)
        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output_view.setMaximumBlockCount(10_000)
        self.output_view.setPlaceholderText(T(
            "优化任务的标准输出和错误输出会显示在这里。",
            "Standard output and errors from optimization tasks appear here."))
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
        self.btn_back = QPushButton(T("◀ 返回定义", "◀ Back to Definition"))
        self.btn_back.setToolTip(T(
            "返回定义页；若优化正在运行，将先请求确认终止",
            "Return to the definition page; running tasks ask for confirmation."))
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
        """Called when the definition page hands over a finished problem."""
        self._problem = problem
        self._source = None
        self._save_morph_def = True
        self._saved_def = set()
        self._stop_job()
        self._run.clear_result()
        self.panel.reset()
        self.status.setText(T(
            f"定义已就绪：{problem.label}。点击 0 选择任务来源后开始。",
            f"Definition ready: {problem.label}. Click 0 to choose a source."))
        self._update_buttons()

    # ------------------------------------------------------------- buttons
    def _on_back(self) -> None:
        """Return to the definition page.

        If an optimization is still running, ask for confirmation first —
        going back terminates the worker process (no silent interruption).
        """
        if self._run.active:
            ret = QMessageBox.warning(
                self, T("返回定义页", "Back to Definition"),
                T(
                    "当前优化仍在运行。\n\n返回定义页将终止该优化进程；"
                    "已保存的迭代仍可通过“打开结果”查看。\n\n确认终止并返回定义页吗？",
                    "The optimization is still running.\n\nReturning to the "
                    "definition page will terminate this process; completed "
                    "iterations remain available via \u201cOpen Results\u201d."
                    "\n\nTerminate and return to the definition page?"),
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
        dlg = SourceDialog(has_definition=self._problem is not None, parent=self)
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
        """Source = the problem built on the definition page (fresh run)."""
        problem = self._problem
        if problem is None:
            QMessageBox.information(self, T("无定义", "No definition"), T(
                "请先在定义页配置问题，并点击“进入优化器”。",
                "Build a problem on the definition page and enter the observer."))
            return
        self._run.clear_result()
        self._last_shown = 0
        self.panel.reset()
        self._save_morph_def = True
        self._source = RunSource(
            kind=RunSourceKind.DEFINITION,
            label=problem.label,
        )
        self._refresh_status()
        self._update_buttons()

    def _pick_py_source(self) -> None:
        """Source = an existing runnable definition script (.py)."""
        py_path, _ = QFileDialog.getOpenFileName(
            self, T("选择定义脚本 (.py)", "Select definition script (.py)"),
            os.getcwd(), "Python (*.py)")
        if not py_path:
            return
        self._run.clear_result()
        self._last_shown = 0
        self.panel.reset()
        self._save_morph_def = False   # a foreign script: do not write our .morph
        self._source = RunSource(
            kind=RunSourceKind.PYTHON,
            path=py_path,
        )
        self._refresh_status()
        self._update_buttons()

    def _pick_continue_source(self) -> None:
        """Source = an existing result folder to continue from."""
        folder = QFileDialog.getExistingDirectory(
            self, T("选择已有结果目录（续跑）", "Select result folder (continue)"),
            os.getcwd())
        if not folder:
            return
        if not self._run.is_result_folder(folder):
            QMessageBox.warning(
                self, T("不是有效结果", "Invalid result"), T(
                    "该目录不是有效的优化结果（缺少 "
                    "scripts/MAIN_SCRIPT_FOR_RESTART.py）。",
                    "Not a valid result folder (missing "
                    "scripts/MAIN_SCRIPT_FOR_RESTART.py)."))
            return
        self._adopt(folder)   # bind + show the last iteration (browsing)
        self._source = RunSource(
            kind=RunSourceKind.CONTINUE,
            path=folder,
            label=os.path.basename(folder),
        )
        self._refresh_status()
        self._update_buttons()

    def _adopt(self, folder: str) -> None:
        self._run.adopt(folder)
        self.panel.ensure_loaded(self._run.folder)
        last = last_completed_iteration(self._run.folder)
        if last >= 1:
            self._last_shown = last
            self.panel.show_iteration(self._run.folder, last)

    def _clear_source(self) -> None:
        """Reset the chosen source (a source is used for one run only)."""
        self._source = None
        self._update_buttons()
        if not self._run.active:
            self._refresh_status()

    def _refresh_status(self) -> None:
        """Status line for the current source / idle state."""
        src = self._source
        if src is not None:
            self.status.setText(self._source_status(src))
            return
        if self._run.active:
            return  # running-status lines are set by the run methods
        if self._problem is not None:
            self.status.setText(T(
                "尚未选择任务来源：点击 0 选择。",
                "No task source yet: click 0 to choose."))
        else:
            self.status.setText(T(
                "尚未接收优化定义；请先在定义页配置问题。",
                "No definition received; build a problem first."))

    def _start(self) -> None:
        if self._run.active:
            return
        src = self._source
        if src is None:
            self.status.setText(T(
                "请先点击 0 选择任务来源。",
                "Click 0 to choose a task source first."))
            return
        launched = False
        if src.kind is RunSourceKind.CONTINUE:
            launched = self._continue_flow()
        elif src.kind is RunSourceKind.DEFINITION:
            launched = self._launch_fresh()
        elif src.kind is RunSourceKind.PYTHON:
            launched = self._launch_py_source()
        if launched:
            # a source is consumed by one run: reset it so the next run /
            # continue always requires choosing again via 0.
            self._clear_source()

    def _continue_flow(self) -> bool:
        folder = self._source.path
        last = last_completed_iteration(folder)
        dlg = ContinueDialog(max_step=last, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        target = dlg.target_iteration()
        try:
            self._run.start_continue(
                folder,
                target_iteration=target,
            )
        except Exception as exc:
            QMessageBox.warning(self, T("继续失败", "Continue failed"), str(exc))
            return False
        if self._save_morph_def:
            self._save_definition(folder)
        self._capture_process_output()
        self._last_shown = max(0, target or last)
        self.status.setText(T(
            f"正在继续优化：自第 {target if target else last} 步起。",
            f"Continuing optimization from step {target if target else last}."))
        self._timer.start()
        self._update_buttons()
        return True

    def _launch_fresh(self) -> bool:
        problem = self._problem
        if problem is None:
            return False
        try:
            self._run.start_definition(problem)
        except Exception as exc:
            QMessageBox.warning(self, T("启动失败", "Launch failed"), str(exc))
            return False
        self._save_morph_def = True
        self._last_shown = 0
        self._capture_process_output()
        self.status.setText(T(
            "正在从头开始优化…等待首轮结果。",
            "Starting optimization from scratch… waiting for the first step."))
        self._timer.start()
        self._update_buttons()
        return True

    def _launch_py_source(self) -> bool:
        """Run a fresh optimization from an existing definition ``.py``."""
        src = self._source
        py = src.path
        try:
            self._run.start_python(py)
        except Exception as exc:
            QMessageBox.warning(self, T("启动失败", "Launch failed"), str(exc))
            return False
        self._last_shown = 0
        self._capture_process_output()
        self.status.setText(T(
            f"正在从脚本优化：{os.path.basename(py)}…等待首轮结果。",
            f"Optimizing from {os.path.basename(py)}… waiting for the first step."))
        self._timer.start()
        self._update_buttons()
        return True

    def _stop(self) -> None:
        self._stop_job()
        if self._run.folder:
            self.status.setText(T(
                "优化任务已停止，当前可视化已保留。若需续跑，请点击 0 重新选择结果。",
                "Optimization stopped; current visualization kept. To continue, "
                "choose the result again via 0."))
        else:
            self.status.setText(T(
                "优化任务已停止。如需再次运行，请点击 0 选择任务来源。",
                "Optimization stopped. Choose a source via 0 to run again."))
        self._update_buttons()

    def _save_definition(self, folder: str) -> None:
        """Write the UI-defined problem next to the framework's runnable script.

        The run's ``.py`` is ``<result>/scripts/MAIN_SCRIPT_FOR_RESTART.py``
        (the controller writes it automatically); we only add its companion
        ``MAIN_SCRIPT_FOR_RESTART.morph`` in the same directory.
        """
        if self._problem is None or folder in self._saved_def:
            return
        try:
            ProblemLibrary.save_result_copy(self._problem, folder)
            self._saved_def.add(folder)
        except Exception as exc:  # pragma: no cover - best effort
            print(f"save definition to result failed: {exc}")

    def _stop_job(self) -> None:
        if not self._run.active:
            return
        self._run.stop()
        self._timer.stop()
        if self._run.folder:
            last = last_completed_iteration(self._run.folder)
            if last >= 1 and last != self._last_shown:
                self._last_shown = last
                self.panel.show_iteration(self._run.folder, last)
        self._update_buttons()

    # ------------------------------------------------------------ run output
    def _clear_output(self) -> None:
        """Remove the displayed output without affecting a running task."""
        self.output_view.clear()
        self._progress_headers.clear()

    def _capture_process_output(self) -> None:
        """Stream this UI-launched process's combined output into the log box."""
        process = self._run.process
        self._output_run_id += 1
        run_id = self._output_run_id
        self._clear_output()
        if process is None or process.stdout is None:
            self._append_process_output(
                run_id,
                T("无法捕获该任务的输出。", "Unable to capture this task's output."))
            return
        reader = threading.Thread(
            target=self._read_process_output,
            args=(process, run_id),
            name="morphopt-ui-output-reader",
            daemon=True,
        )
        reader.start()

    def _read_process_output(self, process, run_id: int) -> None:
        """Read a process pipe off the Qt thread and deliver complete lines."""
        stream = process.stdout
        if stream is None:
            return
        try:
            for raw_line in iter(stream.readline, b""):
                self.outputReceived.emit(
                    run_id, raw_line.decode("utf-8", errors="replace"))
        finally:
            stream.close()

    def _append_process_output(self, run_id: int, text: str) -> None:
        """Append current-run output in the UI thread, ignoring stale readers."""
        if run_id != self._output_run_id:
            return
        line, is_redraw = _clean_terminal_line(text)
        if not line:
            return
        header_key = " ".join(line.split())
        if _is_progress_header(line):
            if is_redraw and header_key in self._progress_headers:
                return
            self._progress_headers.add(header_key)
        self.output_view.appendPlainText(line)

    # -------------------------------------------------------------- polling
    def _poll_once(self) -> None:
        if not self._run.active:
            return
        folder = self._run.folder
        if self._run.mode is RunMode.FRESH:
            candidate = self._run.discover_folder()
            if candidate is None:
                self._check_exit()
                return
            if folder != candidate:
                folder = candidate
                self.panel.ensure_loaded(candidate)
            if self._save_morph_def:
                self._save_definition(folder)
        if folder is None:
            self._check_exit()
            return
        last = last_completed_iteration(folder)
        if last >= 1 and last != self._last_shown:
            self._last_shown = last
            self.panel.show_iteration(folder, last)
            self.status.setText(T(
                f"优化运行中：已完成第 {last} 步。",
                f"Optimization running: step {last} completed."))
        self._check_exit()

    def _check_exit(self) -> None:
        if self._run.has_exited():
            self._run.release_finished()
            self._timer.stop()
            if self._run.folder:
                last = last_completed_iteration(self._run.folder)
                if last >= 1 and last != self._last_shown:
                    self._last_shown = last
                    self.panel.show_iteration(self._run.folder, last)
            self.status.setText(T(
                "优化任务已结束。如需再次运行/续跑，请点击 0 重新选择任务来源。",
                "Optimization finished. Choose a source via 0 to run again."))
            self._update_buttons()

    def _update_buttons(self) -> None:
        running = self._run.active
        src = self._source
        self.btn_open.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        if src is not None and src.kind is RunSourceKind.CONTINUE:
            self.btn_start.setText(T("1 · 继续优化", "1 · Continue"))
        else:
            self.btn_start.setText(T("1 · 开始优化", "1 · Start"))
        self.btn_start.setEnabled(not running and src is not None)

    @staticmethod
    def _source_status(source: RunSource) -> str:
        if source.kind is RunSourceKind.DEFINITION:
            return T(
                f"当前任务：全新优化 · 定义 {source.label}",
                f"Current task: fresh run · definition {source.label}",
            )
        if source.kind is RunSourceKind.PYTHON:
            filename = os.path.basename(source.path)
            return T(
                f"当前任务：全新优化 · 脚本 {filename}",
                f"Current task: fresh run · script {filename}",
            )
        return T(
            f"当前任务：续跑已有结果 · {source.label}",
            f"Current task: continue result · {source.label}",
        )

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the observer's static texts."""
        self.btn_open.setText(T("0 · 选择任务来源…", "0 · Choose source…"))
        self.btn_open.setToolTip(T(
            "选择任务来源：当前定义 / 已有定义脚本 (.py) / 已有结果续跑。",
            "Choose a task source: current definition, a definition script "
            "(.py), or an existing result to continue."))
        self.btn_start.setToolTip(T(
            "先点击 0 选择任务来源后可用；运行开始后来源即重置，需重新选择。",
            "Enabled after choosing a source via 0; the source is reset once "
            "a run starts, so choose again for another run."))
        self.btn_stop.setText(T("2 · 停止优化", "2 · Stop"))
        self.btn_stop.setToolTip(T(
            "终止当前优化任务，但保留当前可视化；续跑需重新选择来源。",
            "Stop the running task, keeping the current visualization; "
            "continue requires choosing the source again."))
        self.btn_back.setText(T("◀ 返回定义", "◀ Back to Definition"))
        self.btn_back.setToolTip(T(
            "返回定义页；若优化正在运行，将先请求确认终止",
            "Return to the definition page; running tasks ask for confirmation."))
        self.output_label.setText(T("运行输出", "Run output"))
        self.btn_clear_output.setText(T("清空", "Clear"))
        self.output_view.setPlaceholderText(T(
            "优化任务的标准输出和错误输出会显示在这里。",
            "Standard output and errors from optimization tasks appear here."))
        self.panel.apply_language()
        self._update_buttons()
        if self._run.active:
            self.status.setText(T("优化运行中。", "Optimization running."))
        else:
            self._refresh_status()

    def close_cleanup(self) -> None:
        self._stop_job()
