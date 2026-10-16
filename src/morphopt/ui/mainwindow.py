"""Top-level window: an empty definition workbench and an observer page."""

from __future__ import annotations
from copy import deepcopy

import os
from pathlib import Path

from PySide6.QtCore import QDir, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QToolButton,
)

from .theme import theme_manager
from .model.problem import ProblemDefinition
from .application import ProblemLibrary
from ..constants import CONSTANT
from .model.loaders import MORPH_SUFFIX
from .schemes.base import scheme_label
from .i18n import localization, tr
from .widgets.language_selector import LanguageSelector
from .widgets.theme_selector import ThemeSelector
from .workbench import Workbench
from .observe_panel import ObserverControls
from .widgets.quickstart import QuickstartDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._workbench: Workbench | None = None
        self._observer: ObserverControls | None = None
        self._unsubscribe_theme = theme_manager.subscribe(self._apply_theme)
        self.destroyed.connect(lambda *_args: self._unsubscribe_theme())

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._add_language_switch()
        self.resize(*deepcopy(theme_manager.palette.layout.main_window_size))
        self.set_problem(ProblemLibrary.create_blank())

    # ------------------------------------------------------------------ api
    def current_problem(self) -> ProblemDefinition | None:
        return self._workbench.problem if self._workbench is not None else None

    # ------------------------------------------------------------ language
    def _add_language_switch(self) -> None:
        self._theme_switch = ThemeSelector()
        self._lang_switch = LanguageSelector()
        self._unsubscribe_locale = localization.subscribe(self._apply_language)
        self.statusBar().addPermanentWidget(self._theme_switch)
        self.statusBar().addPermanentWidget(self._lang_switch)

    def _apply_theme(self, _theme: str | None = None) -> None:
        """Refresh theme-aware drawing without replacing either page."""
        if self._workbench is not None:
            self._workbench.apply_theme()
        if self._observer is not None:
            self._observer.apply_theme()

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
        self.statusBar().showMessage(
            tr('ui.mainwindow.ready'),
            CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
        )

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
        try:
            problem = ProblemLibrary.load(path)
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.mainwindow.open_failed'), str(exc))
            return
        self.set_problem(problem)
        self.statusBar().showMessage(
            tr('ui.mainwindow.opened_value_value', value_0=problem.label, value_1=scheme_label(problem.scheme)),
            CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.LONG,
        )

    def export_morph(self) -> None:
        workbench = self._workbench
        if workbench is None:
            return
        workbench.flush_edits()
        problem = workbench.problem
        path = self._choose_file_path(
            tr("ui.mainwindow.export_morph"),
            MORPH_SUFFIX,
            save=True,
            label=problem.label,
        )
        if path:
            out = ProblemLibrary.save(problem, path)
            workbench.mark_saved()
            self.statusBar().showMessage(
                tr('ui.mainwindow.exported') + out,
                CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
            )

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
            ProblemLibrary.export_python(problem, path)
            self.statusBar().showMessage(
                tr('ui.mainwindow.exported_runnable_script') + path,
                CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
            )

    def _choose_file_path(
        self, title: str, suffix: str, *, save: bool, label: str = ""
    ) -> str:
        """Show a consistently styled open or save dialog for one file type."""
        dialog = QFileDialog(self, title, os.getcwd())
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setOption(QFileDialog.Option.DontConfirmOverwrite, save)
        dialog.setAcceptMode(
            QFileDialog.AcceptMode.AcceptSave
            if save
            else QFileDialog.AcceptMode.AcceptOpen
        )
        dialog.setFileMode(
            QFileDialog.FileMode.AnyFile
            if save
            else QFileDialog.FileMode.ExistingFile
        )
        dialog.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )
        file_filter = (
            tr("ui.files.morph")
            if suffix.lower() == MORPH_SUFFIX.lower()
            else tr("ui.files.python")
        )
        dialog.setNameFilter(file_filter)
        if save:
            dialog.setDefaultSuffix(suffix.lstrip("."))
            dialog.selectFile(self._export_filename(label, suffix))
        QTimer.singleShot(0, lambda: self._set_file_dialog_icons(dialog))
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return ""

        selected = dialog.selectedFiles()
        if not selected:
            return ""
        path = Path(selected[0])
        if save and not path.name.lower().endswith(suffix.lower()):
            path = path.with_name(path.name + suffix)
        if save and path.exists() and not self._confirm_overwrite(path):
            return ""
        return str(path)

    def _confirm_overwrite(self, path: Path) -> bool:
        """Ask for overwrite confirmation using the active UI language."""
        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Icon.Warning)
        message_box.setWindowTitle(tr("ui.mainwindow.overwrite_confirmation"))
        message_box.setText(
            tr("ui.mainwindow.overwrite_existing_file_value", value_0=path.name)
        )
        replace_button = message_box.addButton(
            tr("ui.mainwindow.overwrite_yes"), QMessageBox.ButtonRole.YesRole
        )
        cancel_button = message_box.addButton(
            tr("ui.mainwindow.overwrite_no"), QMessageBox.ButtonRole.NoRole
        )
        message_box.setDefaultButton(cancel_button)
        message_box.setEscapeButton(cancel_button)
        message_box.exec()
        return message_box.clickedButton() is replace_button

    @staticmethod
    def _set_file_dialog_icons(dialog: QFileDialog) -> None:
        """Draw visible navigation icons instead of relying on the desktop theme."""
        icons = {
            "backButton": "back",
            "forwardButton": "forward",
            "toParentButton": "up",
            "newFolderButton": "new_folder",
            "listModeButton": "list",
            "detailModeButton": "details",
        }
        for button in dialog.findChildren(QToolButton):
            name = icons.get(button.objectName())
            if name is None:
                continue

            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(
                QPen(
                    QColor(theme_manager.palette.text),
                    2.0,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if name == "back":
                painter.drawLine(15, 5, 8, 12)
                painter.drawLine(8, 12, 15, 19)
                painter.drawLine(8, 12, 21, 12)
            elif name == "forward":
                painter.drawLine(9, 5, 16, 12)
                painter.drawLine(16, 12, 9, 19)
                painter.drawLine(3, 12, 16, 12)
            elif name == "up":
                painter.drawLine(12, 20, 12, 7)
                painter.drawLine(7, 12, 12, 7)
                painter.drawLine(12, 7, 17, 12)
            elif name in {"new_folder", "list", "details"}:
                if name == "new_folder":
                    painter.drawLine(3, 7, 9, 7)
                    painter.drawLine(9, 7, 11, 10)
                    painter.drawLine(11, 10, 21, 10)
                    painter.drawLine(21, 10, 21, 19)
                    painter.drawLine(21, 19, 3, 19)
                    painter.drawLine(3, 19, 3, 7)
                    painter.drawLine(12, 12, 12, 17)
                    painter.drawLine(9, 14, 15, 14)
                elif name == "list":
                    for y in (6, 12, 18):
                        painter.drawEllipse(3, y - 1, 2, 2)
                        painter.drawLine(9, y, 21, y)
                else:
                    painter.drawRect(3, 4, 18, 16)
                    painter.drawLine(3, 10, 21, 10)
                    painter.drawLine(3, 15, 21, 15)
                    painter.drawLine(9, 4, 9, 20)
            painter.end()
            button.setIcon(QIcon(pixmap))
            button.setIconSize(QSize(*theme_manager.palette.layout.toolbar_icon_size))
            button.setProperty("buttonLayout", "navigation")
            button.style().unpolish(button)
            button.style().polish(button)

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
            tr('ui.mainwindow.observer_choose_a_task_source_with_0_then_start_stop'),
            CONSTANT.UI.APPLICATION.STATUS_MESSAGE_DURATION_MS.SHORT,
        )

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
