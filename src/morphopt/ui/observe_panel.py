"""In-window observer panel + controls (definition & observer share ONE window).

The definition page hands the finished problem here (:meth:`ObserverControls.
set_definition`), then the user either opens an existing result folder
(button 0 · 打开结果) or starts the optimization:

* no folder + a definition present  -> start from scratch (headless job),
* a folder present (opened or from a previous run) -> continue from the last
  saved step or from a chosen step (button 1, with a small dialog).

Progress is polled from the result folder on disk (per *finished* iteration),
so no queue / no extra process is needed.  Button 2 (停止优化) terminates the
job's whole process group but keeps the current visualization, which can still
be browsed with the slider / the left options, or continued afterwards.
"""

from __future__ import annotations

import glob
import importlib.util
import os
import re
import sys
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QListWidget, QStackedWidget, QSplitter, QMessageBox, QFileDialog,
    QDialog, QRadioButton, QSpinBox, QCheckBox,
)

from . import launcher
from .monitor import _MetricsPage, _GeometryPage, _CasePage
from .i18n import T


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def controller_class_from_folder(path_result: str):
    """Import ``ThisController`` from a result folder's frozen MAIN_SCRIPT."""
    main = os.path.join(path_result, "scripts", "MAIN_SCRIPT_FOR_RESTART.py")
    if not os.path.exists(main):
        return None
    import torch
    torch.set_default_dtype(torch.float64)
    torch.set_default_device("cpu")
    key = os.path.basename(os.path.normpath(path_result))
    name = "morphopt_run_" + re.sub(r"[^A-Za-z0-9_]", "_", key)
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, main)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:  # pragma: no cover - best effort
            sys.modules.pop(name, None)
            print(f"controller import failed for {path_result}: {exc}")
            return None
    return getattr(mod, "ThisController", None)


def _last_iteration(path_result: str) -> int:
    try:
        from ..optcore.history import History
        h = History()
        h.load(foldpath=os.path.join(path_result, "log"))
        return int(getattr(h, "iteration", 0) or 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# observer content (slider + left options + stacked pages)
# ---------------------------------------------------------------------------

class ObserverPanel(QWidget):
    """Embedded observer content, driven purely from the result folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path_result: str | None = None
        self.iteration = 0
        self._controller = None
        self._params = None
        self._history = None
        self._case_pages: dict[int, _CasePage] = {}

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
        self.options.addItem(T("几何展示", "Geometry"))
        self.options.currentRowChanged.connect(self._on_option)
        split.addWidget(self.options)

        self.stack = QStackedWidget()
        self._metrics_page = _MetricsPage()
        self._geometry_page = _GeometryPage()
        self.stack.addWidget(self._metrics_page)
        self.stack.addWidget(self._geometry_page)
        split.addWidget(self.stack)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([160, 1100])
        outer.addWidget(split, 1)
        self.options.setCurrentRow(0)

    # ------------------------------------------------------------------ api
    def ensure_loaded(self, folder: str) -> bool:
        """Bind the controller/params for a folder once (no rendering yet)."""
        if self.path_result == folder and self._controller is not None:
            return True
        self.path_result = folder
        self._controller = controller_class_from_folder(folder)
        self._params = None
        if self._controller is not None:
            try:
                self._params = self._controller.Params()
                self._params.initialize()
            except Exception as exc:
                print(f"params init failed: {exc}")
                self._params = None
        return self._controller is not None

    def show_iteration(self, folder: str, iteration: int) -> None:
        """Render one finished iteration (history + current option page)."""
        if folder != self.path_result:
            self.ensure_loaded(folder)
        self.path_result = folder
        self.iteration = iteration

        from ..optcore.history import History
        history = History()
        try:
            history.load(foldpath=os.path.join(folder, "log"), iteration=iteration)
        except Exception as exc:
            print(f"history load failed: {exc}")
            return
        self._history = history
        self._metrics_page.update_from_history(history, iteration)
        self._discover_cases(folder)

        max_iter = max(1, int(getattr(history, "iteration", iteration) or iteration))
        self.slider.blockSignals(True)
        self.slider.setMaximum(max_iter)
        if self.chk_follow.isChecked():
            self.slider.setValue(max_iter)
        self.slider.blockSignals(False)
        self.iter_label.setText(f"{self.slider.value()} / {max_iter}")

        row = self.options.currentRow()
        if row == 1:
            self._refresh_geometry()
        elif row >= 2 and row - 2 in self._case_pages:
            self._refresh_case(row - 2)

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the panel's static texts."""
        self.chk_follow.setText(T("自动跟踪最新", "Follow latest"))
        self.options.item(0).setText(T("优化指标", "Metrics"))
        self.options.item(1).setText(T("几何展示", "Geometry"))
        for row, case in enumerate(list(self._case_pages.keys())):
            if self.options.count() > row + 2:
                self.options.item(row + 2).setText(f"{T('工况', 'Case')} {case}")
        row = self.options.currentRow()
        if row == 1:
            self._refresh_geometry()

    # -------------------------------------------------------------- options
    def _on_option(self, row: int) -> None:
        if row < 0 or row >= self.stack.count():
            return
        if row == 1:
            self._refresh_geometry()
        elif row >= 2 and row - 2 in self._case_pages:
            self._refresh_case(row - 2)
        self.stack.setCurrentIndex(row)

    def _refresh_geometry(self) -> None:
        if self.path_result and self._params is not None:
            self._geometry_page.build(self._params, self.path_result,
                                      self.slider.value())

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
                self._refresh_geometry()
            elif row >= 2:
                self._refresh_case(row - 2)

    def _discover_cases(self, folder: str) -> None:
        found = set()
        for fpath in glob.glob(os.path.join(folder, "log", "deformation", "task_*_iter_*.stl")):
            base = os.path.basename(fpath)
            parts = base.split("_")
            if len(parts) >= 4 and parts[0] == "task":
                try:
                    found.add(int(parts[1]))
                except ValueError:
                    pass
        existing = set(self._case_pages)
        for case in sorted(found - existing):
            self._case_pages[case] = _CasePage(case)
            self.stack.addWidget(self._case_pages[case])
            self.options.addItem(f"{T('工况', 'Case')} {case}")


# ---------------------------------------------------------------------------
# observer page: buttons 0/1/2 + polling + job control
# ---------------------------------------------------------------------------

class _ContinueDialog(QDialog):
    """Ask whether to continue from the last step or from a chosen step."""

    def __init__(self, max_step: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("继续优化", "Continue Optimization"))
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(T(
            f"当前结果已完成至第 {max_step} 步。请选择续跑起始位置：",
            f"The result has reached step {max_step}. Choose where to resume:")))
        self.rb_last = QRadioButton(T("从结果最后一步续跑", "Resume from the last step"))
        self.rb_last.setChecked(True)
        self.rb_step = QRadioButton(T("从指定步骤续跑：", "Resume from a chosen step:"))
        self.spin = QSpinBox()
        self.spin.setRange(1, max(1, max_step))
        self.spin.setValue(max(1, max_step))
        self.spin.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.rb_step)
        row.addWidget(self.spin)
        self.rb_last.toggled.connect(lambda on: self.spin.setEnabled(not on))
        lay.addWidget(self.rb_last)
        lay.addLayout(row)
        btns = QHBoxLayout()
        ok = QPushButton(T("继续", "Continue"))
        ok.clicked.connect(self.accept)
        cancel = QPushButton(T("取消", "Cancel"))
        cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def target(self):
        if self.rb_step.isChecked():
            return self.spin.value()
        return None


class ObserverControls(QWidget):
    """Definition/observer bridge: buttons 0·打开结果, 1·开始/继续, 2·停止."""

    backRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._problem = None
        self._folder: str | None = None
        self._proc = None
        self._run_mode: str | None = None        # None | 'fresh' | 'continue'
        self._fresh_label = ""
        self._fresh_root = ""
        self._launch_t0 = 0.0
        self._last_shown = 0
        self._saved_def = set()  # result folders whose definition (.morph) was written

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # top control bar ---------------------------------------------------
        bar = QHBoxLayout()
        self.btn_open = QPushButton(T("0 · 打开结果…", "0 · Open Results…"))
        self.btn_open.setToolTip(T(
            "打开已有优化结果，查看几何 / 指标 / 载荷工况；此后可继续优化",
            "Open an existing result (geometry / metrics / load cases); "
            "may then continue the optimization."))
        self.btn_open.clicked.connect(self._open_result)
        bar.addWidget(self.btn_open)
        self.btn_start = QPushButton(T("1 · 开始优化", "1 · Start"))
        self.btn_start.setToolTip(T(
            "无结果时从头开始优化；已打开结果时变为“继续优化”",
            "Start from scratch; becomes Continue when a result is open."))
        self.btn_start.clicked.connect(self._start)
        bar.addWidget(self.btn_start)
        self.btn_stop = QPushButton(T("2 · 停止优化", "2 · Stop"))
        self.btn_stop.setToolTip(T(
            "终止当前优化任务，但保留当前可视化",
            "Stop the running task, keeping the current visualization."))
        self.btn_stop.clicked.connect(self._stop)
        bar.addWidget(self.btn_stop)
        self.status = QLabel(T("尚未接收优化定义", "No definition received yet."))
        self.status.setStyleSheet("color:#9aa4b2;")
        bar.addWidget(self.status, 1)
        outer.addLayout(bar)

        self.panel = ObserverPanel()
        outer.addWidget(self.panel, 1)

        # bottom-right: back to the definition page (mirrors the definition
        # footer's right-aligned ▶ 导入优化器 button)
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
        self._update_buttons()

    # ------------------------------------------------------------------ api
    def is_running(self) -> bool:
        """Whether an optimization task is currently running."""
        return self._proc is not None

    def set_definition(self, problem) -> None:
        """Called when the definition page hands over a finished problem."""
        self._problem = problem
        self._folder = None
        self._saved_def = set()
        self._stop_job()
        self.status.setText(T(
            f"定义已就绪：{problem.label}。可从头开始优化。",
            f"Definition ready: {problem.label}. Start from scratch."))
        self._update_buttons()

    # ------------------------------------------------------------- buttons
    def _on_back(self) -> None:
        """Return to the definition page.

        If an optimization is still running, ask for confirmation first —
        going back terminates the worker process (no silent interruption).
        """
        if self._proc is not None:
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

    def _open_result(self) -> None:
        if self._proc is not None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, T("选择优化结果文件夹", "Select result folder"), os.getcwd())
        if not folder:
            return
        self._adopt(folder)
        self.status.setText(T(
            f"已打开结果目录：{os.path.basename(folder)}。可选择“继续优化”。",
            f"Opened results: {os.path.basename(folder)}. Continue is available."))
        self._update_buttons()

    def _adopt(self, folder: str) -> None:
        self._folder = folder
        self.panel.ensure_loaded(folder)
        last = _last_iteration(folder)
        if last >= 1:
            self._last_shown = last
            self.panel.show_iteration(folder, last)
        self._run_mode = None
        self._proc = None

    def _start(self) -> None:
        if self._proc is not None:
            return
        if self._folder is not None:
            self._continue_flow()
        elif self._problem is not None:
            self._launch_fresh()
        else:
            self.status.setText(T(
                "请先更换优化问题，或打开已有结果目录。",
                "Choose a problem type or open an existing result folder."))

    def _continue_flow(self) -> None:
        folder = self._folder
        last = _last_iteration(folder)
        dlg = _ContinueDialog(max_step=last, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target = dlg.target()
        scripts = os.path.join(folder, "scripts", "MAIN_SCRIPT_FOR_RESTART.py")
        device, restart = launcher.parse_run_options(scripts)
        try:
            self._proc = launcher.run_continue(
                folder, target_iteration=target, device=device,
                restart_per_iteration=restart)
        except Exception as exc:
            QMessageBox.warning(self, T("继续失败", "Continue failed"), str(exc))
            return
        self._save_definition(folder)
        self._run_mode = "continue"
        self._launch_t0 = time.time()
        self._last_shown = max(0, target or last)
        self.status.setText(T(
            f"正在继续优化：自第 {target if target else last} 步起。",
            f"Continuing optimization from step {target if target else last}."))
        self._timer.start()
        self._update_buttons()

    def _launch_fresh(self) -> None:
        problem = self._problem
        if problem is None:
            return
        try:
            job, self._proc = launcher.run_job(problem)
        except Exception as exc:
            QMessageBox.warning(self, T("启动失败", "Launch failed"), str(exc))
            return
        self._folder = None
        self._fresh_label = launcher._sanitize(problem.label)
        self._fresh_root = launcher.run_root_for(problem)
        self._launch_t0 = time.time()
        self._last_shown = 0
        self._run_mode = "fresh"
        self.status.setText(T(
            "正在从头开始优化…等待首轮结果。",
            "Starting optimization from scratch… waiting for the first step."))
        self._timer.start()
        self._update_buttons()

    def _stop(self) -> None:
        self._stop_job()
        if self._folder:
            self.status.setText(T(
                "优化任务已停止，当前可视化已保留；可继续浏览或续跑。",
                "Optimization stopped; current visualization kept. Browse or continue."))
        else:
            self.status.setText(T("优化任务已停止。", "Optimization stopped."))
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
            from .model.loaders import save_morph
            scripts = os.path.join(folder, "scripts")
            if not os.path.isdir(scripts):
                scripts = folder
            save_morph(self._problem,
                       os.path.join(scripts, "MAIN_SCRIPT_FOR_RESTART.morph"))
            self._saved_def.add(folder)
        except Exception as exc:  # pragma: no cover - best effort
            print(f"save definition to result failed: {exc}")

    def _stop_job(self) -> None:
        if self._proc is None:
            return
        launcher.stop_job(self._proc)
        self._proc = None
        self._timer.stop()
        if self._folder:
            last = _last_iteration(self._folder)
            if last >= 1 and last != self._last_shown:
                self._last_shown = last
                self.panel.show_iteration(self._folder, last)
        self._update_buttons()

    # -------------------------------------------------------------- polling
    def _poll_once(self) -> None:
        if self._proc is None:
            return
        folder = self._folder
        if self._run_mode == "fresh":
            cand = launcher.latest_result_dir(self._fresh_root, self._fresh_label)
            # ignore folders that already existed before this run started
            if cand is None or os.path.getmtime(cand) < self._launch_t0 - 2:
                self._check_exit()
                return
            if folder != cand:
                folder = cand
                self._folder = cand
                self.panel.ensure_loaded(cand)
            self._save_definition(folder)
        if folder is None:
            self._check_exit()
            return
        last = _last_iteration(folder)
        if last >= 1 and last != self._last_shown:
            self._last_shown = last
            self.panel.show_iteration(folder, last)
            self.status.setText(T(
                f"优化运行中：已完成第 {last} 步。",
                f"Optimization running: step {last} completed."))
        self._check_exit()

    def _check_exit(self) -> None:
        if self._proc is not None and self._proc.poll() is not None:
            self._proc = None
            self._timer.stop()
            if self._folder:
                last = _last_iteration(self._folder)
                if last >= 1 and last != self._last_shown:
                    self._last_shown = last
                    self.panel.show_iteration(self._folder, last)
            self.status.setText(T("优化任务已结束。", "Optimization finished."))
            self._update_buttons()

    def _update_buttons(self) -> None:
        running = self._proc is not None
        self.btn_open.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        if self._folder is not None:
            self.btn_start.setText(T("1 · 继续优化", "1 · Continue"))
        else:
            self.btn_start.setText(T("1 · 开始优化", "1 · Start"))
        self.btn_start.setEnabled(not running and (self._folder is not None
                                                   or self._problem is not None))

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the observer's static texts."""
        self.btn_open.setText(T("0 · 打开结果…", "0 · Open Results…"))
        self.btn_open.setToolTip(T(
            "打开已有优化结果，查看几何 / 指标 / 载荷工况；此后可继续优化",
            "Open an existing result (geometry / metrics / load cases); "
            "may then continue the optimization."))
        self.btn_start.setToolTip(T(
            "无结果时从头开始优化；已打开结果时变为“继续优化”",
            "Start from scratch; becomes Continue when a result is open."))
        self.btn_stop.setText(T("2 · 停止优化", "2 · Stop"))
        self.btn_stop.setToolTip(T(
            "终止当前优化任务，但保留当前可视化",
            "Stop the running task, keeping the current visualization."))
        self.btn_back.setText(T("◀ 返回定义", "◀ Back to Definition"))
        self.btn_back.setToolTip(T(
            "返回定义页；若优化正在运行，将先请求确认终止",
            "Return to the definition page; running tasks ask for confirmation."))
        self.panel.apply_language()
        self._update_buttons()
        if self._proc is not None:
            self.status.setText(T("优化运行中。", "Optimization running."))
        elif self._folder is not None:
            self.status.setText(T("已打开结果。", "Results open."))
        elif self._problem is not None:
            self.status.setText(T("定义已就绪。", "Definition ready."))
        else:
            self.status.setText(T("尚未接收优化定义。", "No definition received yet."))

    def close_cleanup(self) -> None:
        self._stop_job()
