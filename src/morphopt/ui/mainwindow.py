"""Top-level window: definition part + observer part, in ONE window.

No initial "pick a scheme" step: the app opens directly in the *definition*
part with a default problem.  The definition page owns all problem-level
actions (更换优化问题 / 打开 .morph / 导出 .morph / 导出运行 .py — it emits
request signals that MainWindow fulfils); the observer page owns the run/view
controls.  ``*.morph`` carries its own ``scheme`` so reopening a file always
shows the right problem type.  A language switch (中文 / English) sits in the
status bar and re-applies the current language to both parts.
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QMainWindow, QStackedWidget, QFileDialog, QMessageBox, QInputDialog,
)

from .model.problem import ProblemDefinition
from .model.loaders import load_morph, save_morph, MORPH_SUFFIX
from .schemes.base import get_template, scheme_label
from .i18n import LanguageSelector, T
from .workbench import Workbench
from .observe_panel import ObserverControls
from . import launcher

#: problem types offered by the "更换优化问题" dialog (definition order)
PROBLEM_TYPES = ["shapeopt", "simp", "codesign"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._problem: ProblemDefinition | None = None
        self._workbench: Workbench | None = None
        self._observer: ObserverControls | None = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._add_language_switch()
        self.resize(1500, 880)

        # open directly into the definition part (no initial scheme pick)
        self.open_scheme("shapeopt")

    # ------------------------------------------------------------------ api
    def current_problem(self) -> ProblemDefinition | None:
        return self._problem

    # ------------------------------------------------------------ language
    def _add_language_switch(self) -> None:
        self._lang_switch = LanguageSelector(on_change=self._apply_language)
        self.statusBar().addPermanentWidget(self._lang_switch)

    def _apply_language(self) -> None:
        # Directly re-apply the current language to both parts in place: no
        # viewport is recreated, so it is safe regardless of which page is
        # currently shown (recreating a PyVista viewport while the observer's
        # GL pages are shown would blacken the observer).
        if self._observer is not None:
            self._observer.apply_language()
        if self._workbench is not None:
            self._workbench.apply_language()
        self._set_titles()
        self.statusBar().showMessage(T("就绪", "Ready"), 3000)

    def _set_titles(self) -> None:
        if self.stack.currentWidget() is self._observer:
            self.setWindowTitle(T("MorphOpt UI — 优化器", "MorphOpt UI — Observer"))
        else:
            self.setWindowTitle(T("MorphOpt UI — 优化定义", "MorphOpt UI — Definition"))

    # ---------------------------------------------------------- problem type
    def change_problem(self) -> None:
        """更换优化问题: pick a type; replace the current definition."""
        entries = [T(scheme_label(s), scheme_label(s, english=True))
                   for s in PROBLEM_TYPES]
        text, ok = QInputDialog.getItem(
            self, T("更换优化问题", "Change optimization problem"),
            T("请选择优化问题类型：", "Select the optimization problem type:"),
            entries, 0, False)
        if not ok or not text:
            return
        scheme = PROBLEM_TYPES[entries.index(text)]
        self.open_scheme(scheme)

    def open_scheme(self, scheme: str) -> None:
        """Create a fresh default problem of ``scheme`` and show it."""
        tpl = get_template(scheme)
        problem = tpl.create_problem(f"{scheme}_untitled")
        self.set_problem(problem)
        self.statusBar().showMessage(
            T(f"已创建 {scheme_label(scheme)} 问题",
              f"Created: {scheme_label(scheme, english=True)}"), 3000)

    # ---------------------------------------------------------- definition io
    def open_morph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, T("打开 .morph", "Open .morph"), os.getcwd(),
            "MorphOpt problem (*.morph);;All (*)")
        if not path:
            return
        try:
            problem = load_morph(path)
        except Exception as exc:
            QMessageBox.warning(self, T("打开失败", "Open failed"), str(exc))
            return
        self.set_problem(problem)
        self.statusBar().showMessage(
            T(f"已打开：{problem.label} [{scheme_label(problem.scheme)}]",
              f"Opened: {problem.label} [{scheme_label(problem.scheme, english=True)}]"), 4000)

    def export_morph(self) -> None:
        if self._problem is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, T("导出 .morph", "Export .morph"), os.getcwd(),
            f"{self._problem.label}{MORPH_SUFFIX}", "MorphOpt problem (*.morph)")
        if path:
            out = save_morph(self._problem, path)
            self.statusBar().showMessage(T("已导出：", "Exported: ") + out, 3000)

    def export_run_py(self) -> None:
        """Generate the runnable job .py from the serialized .morph model."""
        if self._problem is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, T("导出运行用 .py", "Export runnable .py"),
            self._problem.label + ".py", "Python (*.py)")
        if path:
            launcher.export_to_py(self._problem, path)
            self.statusBar().showMessage(
                T("已导出运行脚本：", "Exported runnable script: ") + path, 3000)

    # ------------------------------------------------------------- problem
    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        if self._workbench is None:
            self._build_workbench(problem)
            self.stack.addWidget(self._workbench)
        else:
            self._workbench.set_problem(problem)
        self.stack.setCurrentWidget(self._workbench)
        self._set_titles()

    def _build_workbench(self, problem: ProblemDefinition) -> None:
        wb = Workbench(problem)
        wb.notify.connect(self.statusBar().showMessage)
        wb.changeProblemRequested.connect(self.change_problem)
        wb.openMorphRequested.connect(self.open_morph)
        wb.exportMorphRequested.connect(self.export_morph)
        wb.exportRunPyRequested.connect(self.export_run_py)
        wb.importToObserver.connect(self.goto_observer)
        self._workbench = wb

    # ------------------------------------------------ definition <-> observer
    def goto_observer(self, problem: ProblemDefinition | None = None) -> None:
        """Jump from the definition part to the in-window observer part."""
        if problem is not None:
            self._problem = problem
        self._ensure_observer()
        self._observer.set_definition(self._problem)
        self.stack.setCurrentWidget(self._observer)
        self._set_titles()
        self.statusBar().showMessage(
            T("优化器：点击 0 选择任务来源，再开始/停止优化。",
              "Observer: choose a task source with 0, then start / stop."), 3000)

    def _ensure_observer(self) -> None:
        """Create and connect the observer page once."""
        if self._observer is not None:
            return
        self._observer = ObserverControls()
        self._observer.backRequested.connect(self.show_definition)
        self.stack.addWidget(self._observer)

    def show_definition(self) -> None:
        if self._workbench is not None:
            self.stack.setCurrentWidget(self._workbench)
            self._set_titles()

    def closeEvent(self, event):  # noqa: N802
        running = self._observer is not None and self._observer.is_running()
        if running:
            reply = QMessageBox.question(
                self, T("退出确认", "Exit confirmation"),
                T(
                    "优化仍在运行。\n\n退出将终止该优化进程；"
                    "已保存的迭代仍可通过结果目录查看。\n\n确认退出吗？",
                    "An optimization is still running.\n\nQuitting will "
                    "terminate it; completed iterations remain available in "
                    "the result folder.\n\nQuit anyway?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
        else:
            reply = QMessageBox.question(
                self, T("退出确认", "Exit confirmation"),
                T("确定要退出 MorphOpt UI 吗？", "Quit MorphOpt UI?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        if self._observer is not None:
            self._observer.close_cleanup()
        event.accept()
