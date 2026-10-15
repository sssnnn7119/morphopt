"""Top-level window: an empty definition workbench and an observer page."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStackedWidget

from .model.problem import ProblemDefinition
from .application import ProblemLibrary
from .model.loaders import MORPH_SUFFIX
from .schemes.base import scheme_label
from .i18n import localization, tr
from .widgets.language_selector import LanguageSelector
from .workbench import Workbench
from .observe_panel import ObserverControls
from .widgets.quickstart import QuickstartDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._workbench: Workbench | None = None
        self._observer: ObserverControls | None = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._add_language_switch()
        self.resize(1500, 880)
        self.set_problem(ProblemLibrary.create_blank())

    # ------------------------------------------------------------------ api
    def current_problem(self) -> ProblemDefinition | None:
        return self._workbench.problem if self._workbench is not None else None

    # ------------------------------------------------------------ language
    def _add_language_switch(self) -> None:
        self._lang_switch = LanguageSelector()
        self._unsubscribe_locale = localization.subscribe(self._apply_language)
        self.statusBar().addPermanentWidget(self._lang_switch)

    def _apply_language(self, _locale: str | None = None) -> None:
        # Directly re-apply the current language to both parts in place: no
        # viewport is recreated, so it is safe regardless of which page is
        # currently shown (recreating a PyVista viewport while the observer's
        # GL pages are shown would blacken the observer).
        if self._observer is not None:
            self._observer.apply_language()
        if self._workbench is not None:
            self._workbench.apply_language()
        self._set_titles()
        self.statusBar().showMessage(tr('ui.mainwindow.ready'), 3000)

    def _set_titles(self) -> None:
        if self.stack.currentWidget() is self._observer:
            self.setWindowTitle(tr('ui.mainwindow.morphopt_ui_observer'))
        else:
            self.setWindowTitle(tr('ui.mainwindow.morphopt_ui_definition'))

    # ------------------------------------------------------------- creation
    def quickstart(self) -> None:
        """Generate a fresh model from the user's design intent."""
        dialog = QuickstartDialog(self.current_problem(), self)
        if dialog.exec():
            self.set_problem(dialog.problem)
            self.statusBar().showMessage(tr('ui.mainwindow.problem_created_preview_it_or_continue_editing'), 4000)

    # ---------------------------------------------------------- definition io
    def open_morph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr('ui.mainwindow.open_morph'), os.getcwd(),
            tr("ui.files.morph_and_all"))
        if not path:
            return
        try:
            problem = ProblemLibrary.load(path)
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.mainwindow.open_failed'), str(exc))
            return
        self.set_problem(problem)
        self.statusBar().showMessage(
            tr('ui.mainwindow.opened_value_value', value_0=problem.label, value_1=scheme_label(problem.scheme)), 4000)

    def export_morph(self) -> None:
        if self._workbench is not None:
            self._workbench.flush_edits()
        problem = self.current_problem()
        if problem is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr('ui.mainwindow.export_morph'), os.getcwd(),
            f"{problem.label}{MORPH_SUFFIX}", tr("ui.files.morph"))
        if path:
            out = ProblemLibrary.save(problem, path)
            self._workbench.mark_saved()
            self.statusBar().showMessage(tr('ui.mainwindow.exported') + out, 3000)

    def export_run_py(self) -> None:
        """Generate the runnable job .py from the serialized .morph model."""
        if self._workbench is not None:
            self._workbench.flush_edits()
        problem = self.current_problem()
        if problem is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr('ui.mainwindow.export_runnable_py'),
            problem.label + ".py", tr("ui.files.python"))
        if path:
            ProblemLibrary.export_python(problem, path)
            self.statusBar().showMessage(
                tr('ui.mainwindow.exported_runnable_script') + path, 3000)

    # ------------------------------------------------------------- problem
    def set_problem(self, problem: ProblemDefinition) -> None:
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
        wb.quickstartRequested.connect(self.quickstart)
        wb.openMorphRequested.connect(self.open_morph)
        wb.exportMorphRequested.connect(self.export_morph)
        wb.exportRunPyRequested.connect(self.export_run_py)
        wb.importToObserver.connect(self.goto_observer)
        self._workbench = wb

    # ------------------------------------------------ definition <-> observer
    def goto_observer(self, problem: ProblemDefinition | None = None) -> None:
        """Jump from the definition part to the in-window observer part."""
        problem = problem or self.current_problem()
        if problem is None:
            return
        self._ensure_observer()
        self._observer.set_definition(problem)
        self.stack.setCurrentWidget(self._observer)
        self._set_titles()
        self.statusBar().showMessage(
            tr('ui.mainwindow.observer_choose_a_task_source_with_0_then_start_stop'), 3000)

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
                self, tr('ui.mainwindow.exit_confirmation'),
                tr('ui.mainwindow.an_optimization_is_still_running_quitting_will_terminate_it_completed_it'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
        else:
            reply = QMessageBox.question(
                self, tr('ui.mainwindow.exit_confirmation'),
                tr('ui.mainwindow.quit_morphopt_ui'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        if self._observer is not None:
            self._observer.close_cleanup()
        event.accept()
