"""Top-level window: definition part + observer part, in ONE window.

No initial "pick a scheme" step: the app opens directly in the *definition*
part with a default problem.  The definition page owns all problem-level
actions (更换优化问题 / 打开 .morph / 导出 .morph / 导出运行 .py — it emits
request signals that MainWindow fulfils); the observer page owns the run/view
controls.  ``*.morph`` carries its own ``scheme`` so reopening a file always
shows the right problem type.
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QMainWindow, QStackedWidget, QFileDialog, QMessageBox, QInputDialog,
)

from .model.problem import ProblemDefinition
from .model.loaders import load_morph, save_morph, MORPH_SUFFIX
from .model.schemas import SCHEME_LABELS
from .schemes.base import get_template
from .workbench import Workbench
from .observe_panel import ObserverControls
from . import launcher

#: problem types offered by the "更换优化问题" dialog (definition order)
PROBLEM_TYPES = ["shapeopt", "simp", "codesign"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MorphOpt UI — 定义部分")
        self.resize(1500, 880)

        self._problem: ProblemDefinition | None = None
        self._workbench: Workbench | None = None
        self._observer: ObserverControls | None = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.statusBar().showMessage("就绪")

        # open directly into the definition part (no initial scheme pick)
        self.open_scheme("shapeopt")

    # ------------------------------------------------------------------ api
    def current_problem(self) -> ProblemDefinition | None:
        return self._problem

    # ---------------------------------------------------------- problem type
    def change_problem(self) -> None:
        """更换优化问题: pick a type; replace the current definition."""
        entries = [f"{SCHEME_LABELS.get(s, s)} ({s})" for s in PROBLEM_TYPES]
        text, ok = QInputDialog.getItem(
            self, "更换优化问题", "请选择优化问题类型：", entries, 0, False)
        if not ok or not text:
            return
        scheme = PROBLEM_TYPES[entries.index(text)]
        self.open_scheme(scheme)

    def open_scheme(self, scheme: str) -> None:
        """Create a fresh default problem of ``scheme`` and show it."""
        tpl = get_template(scheme)
        problem = tpl.create_problem(f"{scheme}_untitled")
        self.set_problem(problem)
        self.statusBar().showMessage(f"已创建{SCHEME_LABELS.get(scheme, scheme)}问题", 3000)

    # ---------------------------------------------------------- definition io
    def open_morph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 .morph", os.getcwd(),
                                              "MorphOpt problem (*.morph);;All (*)")
        if not path:
            return
        try:
            problem = load_morph(path)
        except Exception as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
            return
        self.set_problem(problem)
        self.statusBar().showMessage(
            f"已打开：{problem.label} [{SCHEME_LABELS.get(problem.scheme, problem.scheme)}]", 4000)

    def export_morph(self) -> None:
        if self._problem is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 .morph", os.getcwd(),
                                              f"{self._problem.label}{MORPH_SUFFIX}",
                                              "MorphOpt problem (*.morph)")
        if path:
            out = save_morph(self._problem, path)
            self.statusBar().showMessage(f"已导出：{out}", 3000)

    def export_run_py(self) -> None:
        """Generate the runnable job .py from the serialized .morph model."""
        if self._problem is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出运行用 .py",
                                              self._problem.label + ".py", "Python (*.py)")
        if path:
            launcher.export_to_py(self._problem, path)
            self.statusBar().showMessage(f"已导出运行脚本：{path}", 3000)

    # ------------------------------------------------------------- problem
    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        if self._workbench is None:
            self._workbench = Workbench(problem)
            self._workbench.notify.connect(self.statusBar().showMessage)
            # problem-level requests (buttons inside the definition header)
            self._workbench.changeProblemRequested.connect(self.change_problem)
            self._workbench.openMorphRequested.connect(self.open_morph)
            self._workbench.exportMorphRequested.connect(self.export_morph)
            self._workbench.exportRunPyRequested.connect(self.export_run_py)
            # definition -> observer bridge (footer button)
            self._workbench.importToObserver.connect(self.goto_observer)
            self.stack.addWidget(self._workbench)
        else:
            self._workbench.set_problem(problem)
        self.stack.setCurrentWidget(self._workbench)
        self.setWindowTitle("MorphOpt UI — 定义部分")

    # ------------------------------------------------ definition <-> observer
    def goto_observer(self, problem: ProblemDefinition | None = None) -> None:
        """Jump from the definition part to the in-window observer part."""
        if problem is not None:
            self._problem = problem
        if self._observer is None:
            self._observer = ObserverControls()
            self._observer.backRequested.connect(self.show_definition)
            self.stack.addWidget(self._observer)
        self._observer.set_definition(self._problem)
        self.stack.setCurrentWidget(self._observer)
        self.setWindowTitle("MorphOpt UI — 观察部分")
        self.statusBar().showMessage("观察部分：可打开结果、开始/继续/停止优化。", 3000)

    def show_definition(self) -> None:
        if self._workbench is not None:
            self.stack.setCurrentWidget(self._workbench)
            self.setWindowTitle("MorphOpt UI — 定义部分")

    def closeEvent(self, event):  # noqa: N802
        if self._observer is not None:
            self._observer.close_cleanup()
        event.accept()
