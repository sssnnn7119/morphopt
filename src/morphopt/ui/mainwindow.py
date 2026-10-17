"""Persistent definition, optimization and finite-element workspaces."""

from __future__ import annotations
from copy import deepcopy

import os
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from .theme import theme_manager
from .model.problem import ProblemDefinition
from .application import ProblemLibrary
from ..constants import CONSTANT
from .model.loaders import MORPH_SUFFIX
from .schemes.base import scheme_label
from .i18n import SUPPORTED_LOCALES, localization, tr
from .workbench import Workbench
from .observe_panel import ObserverControls
from .widgets.quickstart import QuickstartDialog
from .widgets.file_dialogs import confirm_overwrite, create_file_dialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._workbench: Workbench | None = None
        self._observer: ObserverControls | None = None
        self._finite_element = None
        self._document_path: Path | None = None
        self._unsubscribe_theme = theme_manager.subscribe(self._apply_theme)
        self.destroyed.connect(lambda *_args: self._unsubscribe_theme())

        self.stack = QStackedWidget()
        shell = QWidget()
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.navigation = QTabBar()
        self.navigation.setProperty('workspaceNavigation', True)
        self.navigation.setExpanding(False)
        for key in ('definition', 'observation', 'finite_element'):
            self.navigation.addTab(tr('ui.workspace.' + key))
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self._build_menus()
        self._unsubscribe_locale = localization.subscribe(self._apply_language)
        self.destroyed.connect(lambda *_args: self._unsubscribe_locale())
        self._unsubscribe_catalog = theme_manager.subscribe_catalog(self._refresh_menu_text)
        self.destroyed.connect(lambda *_args: self._unsubscribe_catalog())
        self.resize(*deepcopy(theme_manager.palette.layout.main_window_size))
        self.set_problem(ProblemLibrary.create_blank())
        self.stack.addWidget(QWidget())
        self.stack.addWidget(QWidget())
        self.navigation.currentChanged.connect(self._switch_page)

    # ------------------------------------------------------------------ api
    def current_problem(self) -> ProblemDefinition | None:
        return self._workbench.problem if self._workbench is not None else None

    # ------------------------------------------------------------ language
    def _build_menus(self) -> None:
        self._file_menu = self.menuBar().addMenu('')
        self._settings_menu = self.menuBar().addMenu('')
        self._analysis_menu = self.menuBar().addMenu('')
        self._menu_actions = {}
        for key, slot, shortcut in (
            ('new', self.new_problem, QKeySequence.StandardKey.New),
            ('open', self.open_morph, QKeySequence.StandardKey.Open),
            ('quickstart', self.quickstart, None),
            ('save', self.save_morph, QKeySequence.StandardKey.Save),
            ('save_as', self.export_morph, QKeySequence.StandardKey.SaveAs),
            ('export_python', self.export_run_py, None),
            ('export_fea', self.export_finite_element, None),
            ('exit', self.close, QKeySequence.StandardKey.Quit),
        ):
            action = self._file_menu.addAction('')
            action.triggered.connect(slot)
            if shortcut is not None:
                action.setShortcut(shortcut)
            self._menu_actions[key] = action
            if key in {'quickstart', 'save_as', 'export_fea'}:
                self._file_menu.addSeparator()
        self._language_menu = self._settings_menu.addMenu('')
        self._theme_menu = self._settings_menu.addMenu('')
        self._send_definition_action = self._analysis_menu.addAction('')
        self._send_definition_action.triggered.connect(lambda: self._workbench.submit_to_observer())
        self._send_iteration_action = self._analysis_menu.addAction('')
        self._send_iteration_action.triggered.connect(self.import_observer_iteration)
        self._refresh_menu_text()

    def _refresh_menu_text(self, *_args) -> None:
        self._file_menu.setTitle(tr('ui.workspace.file'))
        self._settings_menu.setTitle(tr('ui.workspace.settings'))
        self._analysis_menu.setTitle(tr('ui.workspace.analysis'))
        for key, action in self._menu_actions.items():
            action.setText(tr('ui.workspace.' + key))
        self._send_definition_action.setText(tr('ui.workspace.import_definition'))
        self._send_iteration_action.setText(tr('ui.workspace.analyze_iteration'))
        self._language_menu.setTitle(tr('ui.workspace.language'))
        self._theme_menu.setTitle(tr('ui.workspace.theme'))
        self._language_menu.clear()
        self._theme_menu.clear()
        for name in ('_language_group', '_theme_group'):
            group = getattr(self, name, None)
            if group is not None:
                group.deleteLater()
        self._language_group = QActionGroup(self)
        self._theme_group = QActionGroup(self)
        for code in SUPPORTED_LOCALES:
            action = self._language_menu.addAction(localization.load_locale(code)['locale.name'])
            action.setCheckable(True)
            action.setChecked(localization.locale == code)
            self._language_group.addAction(action)
            action.triggered.connect(lambda _checked=False, code=code: self._set_locale(code))
        for name in theme_manager.names:
            action = self._theme_menu.addAction(tr('ui.theme.' + name))
            action.setCheckable(True)
            action.setChecked(theme_manager.name == name)
            self._theme_group.addAction(action)
            action.triggered.connect(lambda _checked=False, name=name: theme_manager.set_theme(name))

    def _set_locale(self, code: str) -> None:
        QSettings('MorphOptUI', 'ui').setValue('language', code)
        localization.set_locale(code)

    def _switch_page(self, index: int) -> None:
        if index == 1:
            self._ensure_observer()
        elif index == 2:
            self._ensure_finite_element()
        self.stack.setCurrentIndex(index)
        self._set_titles()

    def _apply_theme(self, _theme: str | None = None) -> None:
        """Refresh theme-aware drawing without replacing either page."""
        if self._workbench is not None:
            self._workbench.apply_theme()
        if self._observer is not None:
            self._observer.apply_theme()
        if self._finite_element is not None:
            self._finite_element.apply_theme()
        self._refresh_menu_text()

    def _apply_language(self, _locale: str | None = None) -> None:
        # Directly re-apply the current language to both parts in place: no
        # viewport is recreated, so it is safe regardless of which page is
        # currently shown (recreating a PyVista viewport while the observer's
        # GL pages are shown would blacken the observer).
        if self._observer is not None:
            self._observer.apply_language()
        if self._workbench is not None:
            self._workbench.apply_language()
        if self._finite_element is not None:
            self._finite_element.apply_language()
        for index, key in enumerate(('definition', 'observation', 'finite_element')):
            self.navigation.setTabText(index, tr('ui.workspace.' + key))
        self._refresh_menu_text()
        self._set_titles()
        self.statusBar().showMessage(
            tr('ui.mainwindow.ready'),
            CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
        )

    def _set_titles(self) -> None:
        page = ('definition', 'observation', 'finite_element')[max(0, self.stack.currentIndex())]
        name = self._document_path.name if self._document_path else tr('ui.workspace.untitled')
        self.setWindowTitle(f'MorphOpt — {tr("ui.workspace." + page)} · {name}[*]')
        if self._workbench is not None:
            self.setWindowModified(self._workbench.session.history.is_modified)

    def _confirm_discard(self) -> bool:
        if self._workbench is None:
            return True
        self._workbench.flush_edits()
        if not self._workbench.session.history.is_modified:
            return True
        answer = QMessageBox.question(self, tr('ui.workspace.save_changes'),
            tr('ui.workspace.save_changes_prompt'),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        return answer == QMessageBox.StandardButton.Discard or self.save_morph()

    def new_problem(self) -> None:
        if self._confirm_discard():
            self.set_problem(ProblemLibrary.create_blank())

    # ------------------------------------------------------------- creation
    def quickstart(self) -> None:
        """Generate a fresh model from the user's design intent."""
        dialog = QuickstartDialog(self.current_problem(), self)
        if dialog.exec():
            if not self._confirm_discard():
                return
            self.set_problem(dialog.problem)
            self.statusBar().showMessage(
                tr('ui.mainwindow.problem_created_preview_it_or_continue_editing'),
                CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.LONG,
            )

    # ---------------------------------------------------------- definition io
    def open_morph(self) -> None:
        path = self._choose_file_path(
            tr("ui.mainwindow.open_morph"), MORPH_SUFFIX, save=False
        )
        if not path:
            return
        if not self._confirm_discard():
            return
        try:
            problem = ProblemLibrary.load(path)
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.mainwindow.open_failed'), str(exc))
            return
        self.set_problem(problem, path=path)
        self.statusBar().showMessage(
            tr('ui.mainwindow.opened_value_value', value_0=problem.label, value_1=scheme_label(problem.scheme)),
            CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.LONG,
        )

    def save_morph(self) -> bool:
        if self._document_path is None:
            return self.export_morph()
        return self._save_to(self._document_path)

    def _save_to(self, path: str | Path) -> bool:
        try:
            self._workbench.flush_edits()
            out = ProblemLibrary.save(self._workbench.problem, path)
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.workspace.save_failed'), str(exc))
            return False
        self._document_path = Path(out).resolve()
        self._workbench.mark_saved()
        self._set_titles()
        self.statusBar().showMessage(tr('ui.mainwindow.exported') + str(out))
        return True

    def export_morph(self) -> bool:
        workbench = self._workbench
        if workbench is None:
            return False
        workbench.flush_edits()
        problem = workbench.problem
        path = self._choose_file_path(
            tr("ui.workspace.save_as"),
            MORPH_SUFFIX,
            save=True,
            label=problem.label,
        )
        if path:
            return self._save_to(path)
        return False

    def export_run_py(self) -> None:
        """Generate the runnable job .py from the serialized .morph model."""
        workbench = self._workbench
        if workbench is None:
            return
        workbench.flush_edits()
        problem = workbench.problem
        path = self._choose_file_path(
            tr("ui.mainwindow.export_runnable_py"),
            ".py",
            save=True,
            label=problem.label,
        )
        if path:
            try:
                ProblemLibrary.export_python(problem, path)
            except Exception as exc:
                QMessageBox.warning(self, tr('ui.workspace.save_failed'), str(exc))
                return
            self.statusBar().showMessage(
                tr('ui.mainwindow.exported_runnable_script') + path,
                CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
            )

    def _choose_file_path(
        self, title: str, suffix: str, *, save: bool, label: str = ""
    ) -> str:
        """Show a consistently styled open or save dialog for one file type."""
        directory = str(self._document_path.parent) if self._document_path else os.getcwd()
        dialog = create_file_dialog(self, title, directory, save=save)
        file_filter = (
            tr("ui.files.morph")
            if suffix.lower() == MORPH_SUFFIX.lower()
            else tr("ui.files.python")
        )
        dialog.setNameFilter(file_filter)
        if save:
            dialog.setDefaultSuffix(suffix.lstrip("."))
            dialog.selectFile(self._export_filename(label, suffix))
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return ""

        selected = dialog.selectedFiles()
        if not selected:
            return ""
        path = Path(selected[0])
        if save and not path.name.lower().endswith(suffix.lower()):
            path = path.with_name(path.name + suffix)
        if save and path.exists() and not confirm_overwrite(self, path):
            return ""
        return str(path)

    @staticmethod
    def _export_filename(label: str, suffix: str) -> str:
        """Create the suggested basename used by the save dialog."""
        stem = (label or "").strip()
        if stem.lower().endswith(suffix.lower()):
            stem = stem[: -len(suffix)]
        invalid = '<>:/\\|?*'
        stem = "".join(
            "_" if character in invalid or ord(character) < 32 else character
            for character in stem
        ).strip(" .")
        return f"{stem or 'Untitled'}{suffix}"

    # ------------------------------------------------------------- problem
    def set_problem(self, problem: ProblemDefinition, *, path: str | None = None) -> None:
        self._document_path = Path(path).resolve() if path else None
        if self._workbench is None:
            self._build_workbench(problem)
            self.stack.addWidget(self._workbench)
        else:
            self._workbench.set_problem(problem)
        self.stack.setCurrentWidget(self._workbench)
        self.navigation.setCurrentIndex(0)
        self._set_titles()

    def _build_workbench(self, problem: ProblemDefinition) -> None:
        wb = Workbench(problem)
        wb.notify.connect(self.statusBar().showMessage)
        wb.notify.connect(lambda _text: self._set_titles())
        wb.importToObserver.connect(self.goto_observer)
        self._workbench = wb

    # ------------------------------------------------ definition <-> observer
    def goto_observer(self, problem: ProblemDefinition | None = None) -> None:
        """Import the current definition and show the prepared optimization task."""
        problem = problem or self.current_problem()
        if problem is None:
            return
        self._ensure_observer()
        self._observer.import_definition(problem)
        self.navigation.setCurrentIndex(1)
        self._switch_page(1)
        self.statusBar().showMessage(
            tr(
                'ui.workspace.definition_staged'
                if self._observer.is_running()
                else 'ui.workspace.definition_imported',
                label=problem.label,
            ),
            CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
        )

    def _ensure_observer(self) -> None:
        """Create and connect the observer page once."""
        if self._observer is not None:
            return
        self._observer = ObserverControls()
        self._observer.backRequested.connect(self.show_definition)
        self._observer.importDefinitionRequested.connect(lambda: self._workbench.submit_to_observer())
        self._observer.finiteElementRequested.connect(self.open_finite_element_iteration)
        self._observer.set_definition(self.current_problem())
        self._replace_page(1, self._observer)

    def _replace_page(self, index: int, page: QWidget) -> None:
        old = self.stack.widget(index)
        self.stack.removeWidget(old)
        old.deleteLater()
        self.stack.insertWidget(index, page)

    def _ensure_finite_element(self) -> None:
        if self._finite_element is not None:
            return
        from .widgets.finite_element import FiniteElementPage
        self._finite_element = FiniteElementPage()
        self._finite_element.importObserverRequested.connect(self.import_observer_iteration)
        self._replace_page(2, self._finite_element)

    def import_observer_iteration(self) -> None:
        if self._observer is None or not self._observer.panel.path_result:
            QMessageBox.information(self, tr('ui.workspace.finite_element'), tr('ui.fea.no_observer_result'))
            return
        self.open_finite_element_iteration(self._observer.panel.path_result, self._observer.panel.slider.value())

    def open_finite_element_iteration(self, folder: str, iteration: int) -> None:
        self._ensure_finite_element()
        self.navigation.setCurrentIndex(2)
        self._switch_page(2)
        self._finite_element.import_iteration(folder, iteration)

    def export_finite_element(self) -> None:
        self._ensure_finite_element()
        self.navigation.setCurrentIndex(2)
        self._switch_page(2)
        self._finite_element.export_results()

    def show_definition(self) -> None:
        if self._workbench is not None:
            self.navigation.setCurrentIndex(0)
            self._switch_page(0)

    def closeEvent(self, event):  # noqa: N802
        running = ((self._observer is not None and self._observer.is_running())
                   or (self._finite_element is not None and self._finite_element.is_running()))
        if running:
            reply = QMessageBox.question(
                self, tr('ui.mainwindow.exit_confirmation'),
                tr('ui.workspace.running_on_close'),
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
        if not self._confirm_discard():
            event.ignore()
            return
        if self._observer is not None:
            self._observer.close_cleanup()
        if self._finite_element is not None:
            self._finite_element.close_cleanup()
        event.accept()
