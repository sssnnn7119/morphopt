"""Definition and shared result-analysis workspaces with independent workers."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ..constants import CONSTANT
from .application import ProblemLibrary
from .application.results import ResultSelection
from .application_icon import application_icon
from .i18n import SUPPORTED_LOCALES, localization, tr
from .model.loaders import MORPH_SUFFIX
from .model.problem import ProblemDefinition
from .observe_panel import ObserverControls
from .schemes.base import scheme_label
from .theme import theme_manager
from .widgets.file_dialogs import (
    choose_directory,
    choose_save_directory,
    confirm_overwrite,
    create_file_dialog,
)
from .widgets.font_settings import FontSettingsDialog
from .widgets.labels import ResultPathLabel
from .widgets.quickstart import QuickstartDialog
from .workbench import Workbench


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(application_icon())
        self._workbench: Workbench | None = None
        self._observer: ObserverControls | None = None
        self._finite_element = None
        self._document_path: Path | None = None
        self._analysis_ready = False
        self._result_selection: ResultSelection | None = None
        self._has_analysis_model = False
        self._starting_optimization = False
        self._syncing_selection = False
        self._unsubscribe_theme = theme_manager.subscribe(self._apply_theme)
        self.destroyed.connect(lambda *_args: self._unsubscribe_theme())

        self.stack = QStackedWidget()
        shell = QWidget()
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.navigation = QTabBar()
        self.navigation.setProperty("workspaceNavigation", True)
        self.navigation.setExpanding(False)
        for key in ("definition", "results"):
            self.navigation.addTab(tr("ui.workspace." + key))
        self.navigation.setTabEnabled(1, False)
        workspace_header = QHBoxLayout()
        self._workspace_header = workspace_header
        workspace_header.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        workspace_header.addWidget(self.navigation, 1)
        self.start_button = QPushButton(tr("ui.workspace.start_optimization"))
        self.start_button.setProperty("actionRole", "primary")
        self.start_button.setProperty("buttonLayout", "prominent")
        self.start_button.clicked.connect(self._request_start_optimization)
        workspace_header.addWidget(self.start_button)
        layout.addLayout(workspace_header)
        self.analysis_header = QWidget()
        header = QHBoxLayout(self.analysis_header)
        header.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.analysis_navigation = QTabBar()
        self.analysis_navigation.setProperty("analysisNavigation", True)
        self.analysis_navigation.setExpanding(False)
        for key in ("observation", "finite_element"):
            self.analysis_navigation.addTab(tr("ui.workspace." + key))
        self.analysis_navigation.setTabEnabled(1, False)
        header.addWidget(self.analysis_navigation)
        self.result_context = ResultPathLabel()
        self.result_context.setProperty("textRole", "muted")
        self.result_context.setProperty("toolbarContext", True)
        self.result_context.setMinimumWidth(0)
        self.result_context.pathCopied.connect(
            lambda: self.statusBar().showMessage(
                tr("ui.workspace.result_path_copied"),
                CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
            )
        )
        header.addWidget(self.result_context)
        self._analysis_toolbar = header
        self.analysis_header.hide()
        workspace_header.insertWidget(1, self.analysis_header, 1)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self._build_menus()
        self._unsubscribe_locale = localization.subscribe(self._apply_language)
        self.destroyed.connect(lambda *_args: self._unsubscribe_locale())
        self._unsubscribe_catalog = theme_manager.subscribe_catalog(
            self._refresh_menu_text
        )
        self.destroyed.connect(lambda *_args: self._unsubscribe_catalog())
        self.resize(*deepcopy(theme_manager.palette.layout.main_window_size))
        self.set_problem(ProblemLibrary.create_blank())
        self.stack.addWidget(QWidget())
        self.stack.addWidget(QWidget())
        self.navigation.currentChanged.connect(self._switch_workspace)
        self.analysis_navigation.currentChanged.connect(self._switch_analysis_page)

    # ------------------------------------------------------------------ api
    def current_problem(self) -> ProblemDefinition | None:
        return self._workbench.problem if self._workbench is not None else None

    # ------------------------------------------------------------ language
    def _build_menus(self) -> None:
        menu_bar = self.menuBar()
        # Keep navigation inside the window even with a desktop global menu.
        menu_bar.setNativeMenuBar(False)
        self._file_menu = menu_bar.addMenu("")
        self._settings_menu = menu_bar.addMenu("")
        self._analysis_menu = menu_bar.addMenu("")
        self._menu_actions = {}
        for key, slot, shortcut in (
            ("new", self.new_problem, QKeySequence.StandardKey.New),
            ("open", self.open_morph, QKeySequence.StandardKey.Open),
            ("quickstart", self.quickstart, None),
            ("open_result", self.open_optimization_result, None),
            ("open_python", self.open_python_optimization, None),
            ("save", self.save_morph, QKeySequence.StandardKey.Save),
            ("save_as", self.export_morph, QKeySequence.StandardKey.SaveAs),
            ("export_python", self.export_run_py, None),
            ("exit", self.close, QKeySequence.StandardKey.Quit),
        ):
            action = QAction("", self._file_menu)
            self._file_menu.addAction(action)
            action.triggered.connect(slot)
            if shortcut is not None:
                action.setShortcut(shortcut)
            self._menu_actions[key] = action
            if key in {"quickstart", "open_python", "save_as", "export_python"}:
                self._file_menu.addSeparator()
        self._language_menu = self._settings_menu.addMenu("")
        self._theme_menu = self._settings_menu.addMenu("")
        self._font_settings_action = QAction("", self._settings_menu)
        self._settings_menu.addAction(self._font_settings_action)
        self._font_settings_action.triggered.connect(self._show_font_settings)
        self._design_options_menu = self._settings_menu.addMenu("")
        self._history_limit_action = QAction("", self._design_options_menu)
        self._design_options_menu.addAction(self._history_limit_action)
        self._history_limit_action.triggered.connect(self._set_history_limit)
        self._start_optimization_action = QAction("", self._analysis_menu)
        self._analysis_menu.addAction(self._start_optimization_action)
        self._start_optimization_action.triggered.connect(
            self._request_start_optimization
        )
        self._show_finite_element_action = QAction("", self._analysis_menu)
        self._analysis_menu.addAction(self._show_finite_element_action)
        self._show_finite_element_action.triggered.connect(self.show_finite_element)
        self._refresh_menu_text()

    def _refresh_menu_text(self, *_args) -> None:
        self._file_menu.setTitle(tr("ui.workspace.file"))
        self._settings_menu.setTitle(tr("ui.workspace.settings"))
        self._analysis_menu.setTitle(tr("ui.workspace.analysis"))
        for key, action in self._menu_actions.items():
            action.setText(tr("ui.workspace." + key))
        self._start_optimization_action.setText(tr("ui.workspace.start_optimization"))
        self._show_finite_element_action.setText(tr("ui.workspace.analyze_iteration"))
        self._language_menu.setTitle(tr("ui.workspace.language"))
        self._theme_menu.setTitle(tr("ui.workspace.theme"))
        self._font_settings_action.setText(tr("ui.appearance.fonts"))
        self._design_options_menu.setTitle(tr("ui.workspace.design_options"))
        self._history_limit_action.setText(tr("ui.history.maximum_nodes"))
        self._language_menu.clear()
        self._theme_menu.clear()
        for name in ("_language_group", "_theme_group"):
            group = getattr(self, name, None)
            if group is not None:
                group.deleteLater()
        self._language_group = QActionGroup(self)
        self._theme_group = QActionGroup(self)
        for code in SUPPORTED_LOCALES:
            action = QAction(
                localization.load_locale(code)["locale.name"], self._language_menu
            )
            self._language_menu.addAction(action)
            action.setCheckable(True)
            action.setChecked(localization.locale == code)
            self._language_group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, code=code: self._set_locale(code)
            )
        for name in theme_manager.names:
            action = QAction(tr("ui.theme." + name), self._theme_menu)
            self._theme_menu.addAction(action)
            action.setCheckable(True)
            action.setChecked(theme_manager.name == name)
            self._theme_group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, name=name: theme_manager.set_theme(name)
            )
        self._theme_menu.addSeparator()
        self._visualization_action = QAction(
            tr("ui.visualization.title"), self._theme_menu
        )
        self._theme_menu.addAction(self._visualization_action)
        self._visualization_action.triggered.connect(self._show_visualization_settings)
        self._update_analysis_actions()

    def _show_font_settings(self) -> None:
        FontSettingsDialog(self).exec()

    def _show_visualization_settings(self) -> None:
        from .widgets.visualization_settings import VisualizationSettingsDialog

        dialog = VisualizationSettingsDialog(self)
        dialog.exec()
        dialog.deleteLater()

    def _set_locale(self, code: str) -> None:
        QSettings("MorphOptUI", "ui").setValue("language", code)
        localization.set_locale(code)

    def _set_history_limit(self) -> None:
        history = self._workbench.session.history
        limit, accepted = QInputDialog.getInt(
            self,
            tr("ui.history.maximum_nodes"),
            tr("ui.history.maximum_nodes_prompt", count=history.node_count),
            history.max_nodes,
            1,
            2_147_483_647,
        )
        if accepted:
            self._workbench.set_history_limit(limit)

    def _switch_workspace(self, index: int) -> None:
        if index == 1 and not self._analysis_ready:
            self.navigation.setCurrentIndex(0)
            return
        self.analysis_header.setVisible(index == 1)
        self.start_button.setVisible(index == 0)
        self._workspace_header.setStretchFactor(self.navigation, 1 if index == 0 else 0)
        if index == 0:
            self.stack.setCurrentIndex(0)
        else:
            self._switch_analysis_page(self.analysis_navigation.currentIndex())
        self._set_titles()
        self._update_analysis_actions()

    def _switch_analysis_page(self, index: int) -> None:
        if not self._analysis_ready or self.navigation.currentIndex() != 1:
            return
        if index == 1:
            if not self._has_analysis_model or self._result_selection is None:
                self.analysis_navigation.setCurrentIndex(0)
                return
            selection = self._result_selection
            self._observer.panel.select_iteration(selection.iteration)
            self._ensure_finite_element()
            self._finite_element.synchronize_result(
                selection.folder, selection.iteration
            )
        self.stack.setCurrentIndex(index + 1)
        self._set_titles()

    def _show_analysis(self, *, finite_element: bool = False) -> None:
        self._analysis_ready = True
        self.navigation.setTabEnabled(1, True)
        # Block intermediate switches so a previous finite-element selection
        # cannot import stale data while a new task is being opened.
        self.analysis_navigation.blockSignals(True)
        self.analysis_navigation.setCurrentIndex(1 if finite_element else 0)
        self.analysis_navigation.blockSignals(False)
        if self.navigation.currentIndex() == 1:
            self._switch_workspace(1)
        else:
            self.navigation.setCurrentIndex(1)
        self._update_analysis_actions()

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
        for index, key in enumerate(("definition", "results")):
            self.navigation.setTabText(index, tr("ui.workspace." + key))
        for index, key in enumerate(("observation", "finite_element")):
            self.analysis_navigation.setTabText(index, tr("ui.workspace." + key))
        self._update_result_context()
        self._refresh_menu_text()
        self._set_titles()
        self.statusBar().showMessage(
            tr("ui.mainwindow.ready"),
            CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
        )

    def _set_titles(self) -> None:
        page = ("definition", "observation", "finite_element")[
            max(0, self.stack.currentIndex())
        ]
        name = (
            self._document_path.name
            if self._document_path
            else tr("ui.workspace.untitled")
        )
        if self.stack.currentIndex() > 0 and self._observer is not None:
            name = self._observer.task_label or name
        self.setWindowTitle(f"MorphOpt — {tr('ui.workspace.' + page)} · {name}[*]")
        if self._workbench is not None:
            self.setWindowModified(self._workbench.session.history.is_modified)

    def _confirm_discard(self) -> bool:
        if self._workbench is None:
            return True
        self._workbench.flush_edits()
        if not self._workbench.session.history.is_modified:
            return True
        answer = QMessageBox.question(
            self,
            tr("ui.workspace.save_changes"),
            tr("ui.workspace.save_changes_prompt"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
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
                tr("ui.mainwindow.problem_created_preview_it_or_continue_editing"),
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
            QMessageBox.warning(self, tr("ui.mainwindow.open_failed"), str(exc))
            return
        self.set_problem(problem, path=path)
        self.statusBar().showMessage(
            tr(
                "ui.mainwindow.opened_value_value",
                value_0=problem.label,
                value_1=scheme_label(problem.scheme),
            ),
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
            QMessageBox.warning(self, tr("ui.workspace.save_failed"), str(exc))
            return False
        self._document_path = Path(out).resolve()
        self._workbench.mark_saved()
        self._set_titles()
        self.statusBar().showMessage(tr("ui.mainwindow.exported") + str(out))
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
        """Export a runnable Python module and its assets into one directory."""
        workbench = self._workbench
        if workbench is None:
            return
        workbench.flush_edits()
        problem = workbench.problem
        folder = choose_save_directory(
            self,
            tr("ui.mainwindow.export_runnable_folder"),
            str(self._document_path.parent) if self._document_path else os.getcwd(),
            self._export_folder_name(problem.label),
        )
        if not folder:
            return
        output_directory = Path(folder)
        if output_directory.exists():
            if not output_directory.is_dir():
                QMessageBox.warning(
                    self,
                    tr("ui.workspace.save_failed"),
                    tr(
                        "ui.mainwindow.export_folder_not_directory_value",
                        value_0=folder,
                    ),
                )
                return
            if not confirm_overwrite(
                self,
                output_directory,
                message_key="ui.mainwindow.export_folder_exists_value",
            ):
                return
        try:
            ProblemLibrary.export_python_bundle(problem, output_directory)
        except Exception as exc:
            QMessageBox.warning(self, tr("ui.workspace.save_failed"), str(exc))
            return
        self.statusBar().showMessage(
            tr("ui.mainwindow.exported_runnable_script") + str(output_directory),
            CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
        )

    def _choose_file_path(
        self, title: str, suffix: str, *, save: bool, label: str = ""
    ) -> str:
        """Show a consistently styled open or save dialog for one file type."""
        directory = (
            str(self._document_path.parent) if self._document_path else os.getcwd()
        )
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
        return MainWindow._export_folder_name(stem) + suffix

    @staticmethod
    def _export_folder_name(label: str) -> str:
        stem = (label or "").strip()
        invalid = "<>:/\\|?*"
        stem = "".join(
            "_" if character in invalid or ord(character) < 32 else character
            for character in stem
        ).strip(" .")
        return stem or "Untitled"

    # ------------------------------------------------------------- problem
    def set_problem(
        self, problem: ProblemDefinition, *, path: str | None = None
    ) -> None:
        self._document_path = Path(path).resolve() if path else None
        if self._workbench is None:
            self._build_workbench(problem)
            self.stack.addWidget(self._workbench)
        else:
            self._workbench.set_problem(problem)
        self.stack.setCurrentWidget(self._workbench)
        self.navigation.setCurrentIndex(0)
        self.analysis_header.hide()
        self._set_titles()
        self._update_analysis_actions()

    def _build_workbench(self, problem: ProblemDefinition) -> None:
        wb = Workbench(problem)
        wb.notify.connect(self.statusBar().showMessage)
        wb.notify.connect(lambda _text: self._set_titles())
        wb.startOptimizationRequested.connect(self.start_optimization)
        self._workbench = wb

    # ------------------------------------------------ analysis workspace
    def _can_replace_task(self) -> bool:
        if (
            self._starting_optimization
            or (self._observer is not None and self._observer.is_running())
            or (self._finite_element is not None and self._finite_element.is_running())
        ):
            self.statusBar().showMessage(tr("ui.workspace.task_busy"))
            return False
        return True

    def _request_start_optimization(self) -> None:
        """Reject busy requests before flushing or validating definition widgets."""
        if self._can_replace_task():
            self._workbench.start_optimization()

    def start_optimization(self, problem: ProblemDefinition) -> None:
        """Start the validated definition and enter the live analysis workspace."""
        if not self._can_replace_task():
            return
        self._starting_optimization = True
        self._update_analysis_actions()
        try:
            self._ensure_observer()
            if self._observer.start_definition(problem):
                self._begin_analysis_task()
                self._show_analysis()
        finally:
            self._starting_optimization = False
            self._update_analysis_actions()

    def open_python_optimization(self) -> None:
        if not self._can_replace_task():
            return
        path = self._choose_file_path(tr("ui.workspace.open_python"), ".py", save=False)
        if not path:
            return
        self._ensure_observer()
        if self._observer.start_python(path):
            self._begin_analysis_task()
            self._show_analysis()

    def open_optimization_result(self) -> None:
        if not self._can_replace_task():
            return
        folder = choose_directory(
            self,
            tr("ui.workspace.open_result"),
            os.getcwd(),
        )
        if not folder:
            return
        if not ObserverControls.is_result_folder(folder):
            QMessageBox.warning(
                self,
                tr("ui.observe_panel.invalid_result"),
                tr(
                    "ui.errors.runs.missing_scripts_main_script_for_restart_py_in_the_selected"
                ),
            )
            return
        self._ensure_observer()
        self._begin_analysis_task()
        self._observer.open_result(folder)
        self._show_analysis()

    def _begin_analysis_task(self) -> None:
        self._result_selection = None
        self.result_context.set_folder(None)
        self._refresh_analysis_model()
        self._update_result_context()

    def _ensure_observer(self) -> None:
        """Create the live task view once; navigation never stops its timer."""
        if self._observer is not None:
            return
        self._observer = ObserverControls()
        self._observer.resultFolderChanged.connect(self._set_result_folder)
        self._observer.resultsUpdated.connect(self._refresh_analysis_model)
        self._analysis_toolbar.addWidget(self._observer.task_controls, 1)
        self._observer.runStateChanged.connect(self._update_analysis_actions)
        self._observer.panel.selectionChanged.connect(self._select_result)
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
        self._finite_element.selectionChanged.connect(self._select_result)
        self._finite_element.busyChanged.connect(self._finite_element_busy_changed)
        self._replace_page(2, self._finite_element)

    def _select_result(self, folder: str, iteration: int) -> None:
        """Share a single folder/iteration selection between both result views."""
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self._result_selection = ResultSelection(folder, iteration)
            if self.sender() is self._finite_element:
                self._observer.panel.select_iteration(iteration)
            self._refresh_analysis_model()
            if self.stack.currentIndex() == 2 and self._finite_element is not None:
                self._finite_element.synchronize_result(folder, iteration)
            self._update_result_context()
            self._update_analysis_actions()
        finally:
            self._syncing_selection = False

    def _refresh_analysis_model(self) -> None:
        """Recheck the selected task's archive even if its iteration is unchanged."""
        from ..postprocess import IterationModel

        selection = self._result_selection
        self._has_analysis_model = (
            selection is not None
            and IterationModel(
                selection.folder, selection.iteration
            ).model_path.is_file()
        )
        self.analysis_navigation.setTabEnabled(1, self._has_analysis_model)
        self._show_finite_element_action.setEnabled(self._has_analysis_model)

    def _set_result_folder(self, folder: str) -> None:
        self.result_context.set_folder(folder)
        self._update_result_context()

    def _update_result_context(self) -> None:
        if self._result_selection is None:
            if self.result_context.folder:
                text = Path(self.result_context.folder).name
            elif self._observer is not None:
                text = self._observer.task_label
            else:
                text = ""
            self.result_context.setText(text)
        else:
            selection = self._result_selection
            self.result_context.set_folder(selection.folder)
            self.result_context.setText(
                tr(
                    "ui.workspace.result_context",
                    name=Path(selection.folder).name,
                    iteration=selection.iteration,
                )
            )
        self._set_titles()

    def _update_analysis_actions(self) -> None:
        running = self._observer is not None and self._observer.is_running()
        busy = (
            self._starting_optimization
            or running
            or (self._finite_element is not None and self._finite_element.is_running())
        )
        for key in ("open_result", "open_python"):
            self._menu_actions[key].setEnabled(not busy)
        self._start_optimization_action.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.start_button.setText(
            tr(
                "ui.workspace.optimization_running"
                if running
                else "ui.workspace.start_optimization"
            )
        )
        self.start_button.setToolTip(tr("ui.workspace.task_busy") if busy else "")
        self._show_finite_element_action.setEnabled(self._has_analysis_model)

    def _finite_element_busy_changed(self, busy: bool) -> None:
        if self._observer is not None:
            self._observer.panel.lock_selection(busy)
        self._update_analysis_actions()

    def show_finite_element(self) -> None:
        if self._has_analysis_model:
            self._show_analysis(finite_element=True)

    def show_definition(self) -> None:
        self.navigation.setCurrentIndex(0)
        self._switch_workspace(0)

    def closeEvent(self, event):
        running = (self._observer is not None and self._observer.is_running()) or (
            self._finite_element is not None and self._finite_element.is_running()
        )
        if running:
            reply = QMessageBox.question(
                self,
                tr("ui.mainwindow.exit_confirmation"),
                tr("ui.workspace.running_on_close"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            reply = QMessageBox.question(
                self,
                tr("ui.mainwindow.exit_confirmation"),
                tr("ui.mainwindow.quit_morphopt_ui"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        if reply != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        if not self._confirm_discard():
            event.ignore()
            return
        if self._observer is not None:
            if not self._observer.close_cleanup():
                event.ignore()
                return
        if self._finite_element is not None:
            self._finite_element.close_cleanup()
        event.accept()
