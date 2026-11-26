"""Optimization task controls and live result browsing in the analysis workspace."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..constants import CONSTANT
from ..postprocess import last_completed_iteration
from ..postprocess.visualization import camera_state
from .application import (
    OptimizationRunSession,
    ResultSession,
    RunSource,
    RunSourceKind,
)
from .application.runs import RunProgress
from .i18n import tr
from .presentation.labels import component_selection_title
from .theme import theme_manager
from .widgets.labels import ElidedLabel
from .widgets.observation_pages import (
    DeformationCasePage,
    HistorySceneCache,
    LogsPage,
    MetricsPage,
    UpdatableStructurePage,
)
from .widgets.run_dialogs import ContinueDialog

# ---------------------------------------------------------------------------
# observer content (slider + left options + stacked pages)
# ---------------------------------------------------------------------------


class ObserverPanel(QWidget):
    """Embedded observer content, driven purely from the result folder."""

    selectionChanged = Signal(str, int)

    def __init__(self, parent=None):
        """Initialize ObserverPanel and its configuration state.

        Args:
            parent: Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(parent)
        self._results = ResultSession()
        self._case_names: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*theme_manager.palette.layout.zero_margins)

        self.history_controls = QWidget()
        top = QHBoxLayout(self.history_controls)
        top.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(
            theme_manager.palette.layout.observer.step_button_width
        )
        self.btn_prev.clicked.connect(lambda: self._nudge(-1))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(1)
        self.slider.valueChanged.connect(self._on_slider)
        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(
            theme_manager.palette.layout.observer.step_button_width
        )
        self.btn_next.clicked.connect(lambda: self._nudge(1))
        self.iter_label = QLabel("0 / 0")
        self.iter_label.setMinimumWidth(
            theme_manager.palette.layout.observer.iteration_label_minimum_width
        )
        self.chk_follow = QCheckBox(tr("ui.observe_panel.follow_latest"))
        self.chk_follow.setChecked(True)
        self.chk_follow.toggled.connect(self._on_follow)
        top.addWidget(self.btn_prev)
        top.addWidget(self.slider, 1)
        top.addWidget(self.btn_next)
        top.addWidget(self.iter_label)
        top.addWidget(self.chk_follow)
        self.history_controls.hide()

        split = QSplitter(Qt.Orientation.Horizontal)
        self.options = QListWidget()
        self.options.setFixedWidth(
            theme_manager.palette.layout.observer.option_panel_width
        )
        self.options.currentRowChanged.connect(self._on_option)
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(self.options, 1)
        self.btn_export_history = QPushButton(tr("ui.observe_panel.export_history"))
        self.btn_export_history.clicked.connect(self._open_history_export)
        self.btn_export_history.setEnabled(False)
        sidebar_layout.addWidget(self.btn_export_history)
        split.addWidget(sidebar)

        self.stack = QStackedWidget()
        self._metrics_page = MetricsPage()
        self._logs_page = LogsPage()
        scene_cache = HistorySceneCache()
        self._updatable_structure_page = UpdatableStructurePage(cache=scene_cache)
        self._deformation_page = DeformationCasePage(cache=scene_cache)
        self._last_3d_page: str | None = None
        self.stack.addWidget(self._metrics_page)
        self.stack.addWidget(self._logs_page)
        self.stack.addWidget(self._updatable_structure_page)
        self.stack.addWidget(self._deformation_page)
        self.stack.currentChanged.connect(
            lambda _index: self.history_controls.setVisible(
                self.stack.currentWidget()
                in (self._updatable_structure_page, self._deformation_page)
            )
        )
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        content_layout.addWidget(self.history_controls)
        content_layout.addWidget(self.stack, 1)
        split.addWidget(content)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes(list(theme_manager.palette.layout.observer.option_split_sizes))
        outer.addWidget(split, 1)
        self._sync_design_options()
        self._refresh_current_option()

    @property
    def path_result(self) -> str | None:
        """Return path result.

        Returns:
            str | None: Path result.
        """
        return self._results.folder

    @property
    def iteration(self) -> int:
        """Return iteration.

        Returns:
            int: Iteration.
        """
        return self._results.iteration

    # ------------------------------------------------------------------ api
    def ensure_loaded(self, folder: str) -> bool:
        """Bind the controller/params for a folder once (no rendering yet).

        Args:
            folder (str): Directory containing the optimization run or archive.

        Returns:
            bool: Bind the controller/params for a folder once (no rendering yet).
        """
        if self.path_result != str(Path(folder).resolve()):
            self.reset()
        return self._results.bind(folder)

    def refresh_logs(self) -> None:
        """Read logs on every poll, independently of completed iterations."""
        if self.stack.currentWidget() is self._logs_page:
            self._logs_page.refresh(self._results)

    def show_iteration(self, folder: str, iteration: int) -> None:
        """Render one finished iteration and invalidate snapshots after a rewind.

        Args:
            folder (str): Directory containing the optimization run or archive.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        if iteration < self.iteration:
            self._updatable_structure_page.clear_view()
            self._deformation_page.clear_view()
            self._results.reset()
        try:
            history = self._results.load_iteration(folder, iteration)
        except Exception as exc:
            print(tr("ui.messages.history_load_failed", error=exc))
            return
        self._metrics_page.update_from_history(history, iteration)
        self._sync_design_options()
        has_iterations = int(history.iteration or iteration) > 0
        self.btn_export_history.setEnabled(has_iterations)

        max_iter = max(1, int(history.iteration or iteration))
        self.slider.blockSignals(True)
        self.slider.setMaximum(max_iter)
        if self.chk_follow.isChecked():
            self.slider.setValue(max_iter)
        self.slider.blockSignals(False)
        self.iter_label.setText(f"{self.slider.value()} / {max_iter}")

        self._refresh_current_option()
        self.selectionChanged.emit(self.path_result, self.slider.value())

    def select_iteration(self, iteration: int) -> None:
        """Pin the shared analysis selection, including when this page is hidden.

        Args:
            iteration (int): Iteration index associated with the saved or current model state.
        """
        self.chk_follow.setChecked(False)
        self.slider.setValue(iteration)

    def lock_selection(self, locked: bool) -> None:
        """Keep an in-flight finite-element model bound to its source iteration.

        Args:
            locked (bool): Prevent committing edits while the task is running when True.
        """
        if locked:
            self.chk_follow.setChecked(False)
        for control in (self.slider, self.btn_prev, self.btn_next, self.chk_follow):
            control.setEnabled(not locked)

    def _open_history_export(self) -> None:
        if not self.path_result or self.iteration < 1:
            return
        dialog = self.history_export_dialog()
        dialog.exec()
        dialog.deleteLater()

    def history_export_dialog(self) -> QDialog:
        """Create the export window with the active history selection as its starting point."""
        from .widgets.history_export import HistoryExportDialog

        data = self.options.currentItem().data(Qt.ItemDataRole.UserRole)
        target = {}
        if data[0] == "component":
            view = self._updatable_structure_page.current_view
            target = {"category": data[1], "name": data[2].name}
            if view is not None:
                target["view"] = view.key
        elif data[0] == "case":
            target = {"case": data[1]}
        return HistoryExportDialog(
            self._results,
            self.slider.value(),
            *self._history_gif_view(),
            initial_target=target,
            parent=self,
        )

    def _history_gif_view(
        self,
    ) -> tuple[dict[str, Any], tuple[int, int], dict[str, Any]]:
        """Snapshot the active 3D camera, viewport size, and visual palette.

        Returns:
            tuple[dict[str, Any], tuple[int, int], dict[str, Any]]: Snapshot the active 3D camera,
                viewport size, and visual palette.
        """
        page = (
            self._deformation_page
            if self._last_3d_page == "deformation"
            else self._updatable_structure_page
        )
        viewport = page.viewport
        palette = theme_manager.palette
        viewer = palette.viewer
        geometry = viewer.geometry
        settings = viewport.settings
        style = {
            "background": palette.viewer.render.background,
            "geometry_color": (
                geometry.instance_colors[0]
                if geometry.instance_colors
                else geometry.uninstanced_color
            ),
            "deformation_color": palette.deformation_mesh_color,
            "mesh_ambient": settings.ambient,
            "mesh_diffuse": settings.diffuse,
            "mesh_specular": settings.specular,
            "mesh_specular_power": settings.specular_power,
            "light_intensity": settings.light_intensity,
            "smooth_shading": settings.smooth_shading,
            "boundary_shell_opacity": geometry.boundary_shell_opacity,
        }
        if not self._last_3d_page:
            return {}, (640, 480), style
        plotter = viewport.plotter
        size = tuple(plotter.window_size)
        return camera_state(plotter), size if min(size) >= 2 else (640, 480), style

    def reset(self) -> None:
        """Drop every result-dependent piece of content.

        Called when a fresh (non-result) task source is chosen, so the viewer no longer keeps
        showing the previously browsed result.
        """
        self._results.reset()
        self.btn_export_history.setEnabled(False)
        self._last_3d_page = None
        # Keep native GL windows alive across tasks; only their scenes change.
        self._case_names.clear()
        self._sync_design_options()
        self.options.setCurrentRow(0)
        self.stack.setCurrentWidget(self._metrics_page)
        self.slider.blockSignals(True)
        self.slider.setMaximum(1)
        self.slider.setValue(1)
        self.slider.blockSignals(False)
        self.iter_label.setText("0 / 1")
        self._metrics_page.clear()
        self._logs_page.clear()
        self._updatable_structure_page.clear_view()
        self._deformation_page.clear_view()

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the panel's static texts."""
        self.chk_follow.setText(tr("ui.observe_panel.follow_latest"))
        self.btn_export_history.setText(tr("ui.observe_panel.export_history"))
        self.btn_export_history.setToolTip(tr("ui.observe_panel.export_history_hint"))
        self._sync_design_options()
        self._metrics_page.apply_language()
        self._logs_page.apply_language()
        self._updatable_structure_page.apply_language()
        self._refresh_current_option()

    def apply_theme(self) -> None:
        """Refresh chart and viewport palettes while retaining loaded results."""
        self._metrics_page.apply_theme()
        self._updatable_structure_page.apply_theme()
        self._deformation_page.apply_theme()

    # -------------------------------------------------------------- options
    def _on_option(self, row: int) -> None:
        if row < 0 or row >= self.options.count():
            return
        data = self.options.item(row).data(Qt.ItemDataRole.UserRole)
        if not data or data[0] == "metrics":
            self.stack.setCurrentWidget(self._metrics_page)
        elif data[0] == "logs":
            self.stack.setCurrentWidget(self._logs_page)
            self.refresh_logs()
        elif data[0] == "component":
            self.stack.setCurrentWidget(self._updatable_structure_page)
            self._refresh_updatable_structure(data[2])
        elif data[0] == "case":
            self.stack.setCurrentWidget(self._deformation_page)
            self._refresh_case(data[1])

    def showEvent(self, event) -> None:
        """Refresh deferred content when the widget becomes visible.

        Args:
            event: Qt event delivered to this widget or event filter.
        """
        super().showEvent(event)
        self._refresh_current_option()

    def _refresh_current_option(self) -> None:
        row = self.options.currentRow()
        if row >= 0:
            self._on_option(row)

    def _refresh_updatable_structure(self, component=None) -> None:
        if self.isVisible() and self.path_result:
            self._last_3d_page = "design"
            self._updatable_structure_page.build(
                self._results, self.slider.value(), component
            )

    def _refresh_case(self, case: str) -> None:
        if self.isVisible() and self.path_result and case in self._case_names:
            self._last_3d_page = "deformation"
            self._deformation_page.build(self._results, self.slider.value(), case)

    def _nudge(self, delta: int) -> None:
        self.slider.setValue(self.slider.value() + delta)

    def _on_follow(self, checked: bool) -> None:
        if checked and self.path_result:
            self.slider.setValue(self.slider.maximum())

    def _on_slider(self, value: int) -> None:
        self.iter_label.setText(f"{value} / {self.slider.maximum()}")
        if self.slider.maximum() > 0:
            self._refresh_current_option()
        if self.path_result and self.iteration > 0:
            self.selectionChanged.emit(self.path_result, value)

    def _option_key(self, item) -> tuple[Any, ...] | None:
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not data:
            return None
        if data[0] == "component":
            return ("component", data[1], data[2].name)
        if data[0] == "case":
            return ("case", data[1])
        return (data[0],)

    def _sync_design_options(self) -> None:
        """Flatten components and load cases into one stable left-side list."""
        selected_key = self._option_key(self.options.currentItem())
        components = self._results.fea_components()
        self._case_names = list(self._results.deformation_cases())
        self.options.blockSignals(True)
        try:
            self.options.clear()
            for kind in ("metrics", "logs"):
                self.options.addItem(tr(f"ui.observe_panel.{kind}"))
                self.options.item(self.options.count() - 1).setData(
                    Qt.ItemDataRole.UserRole, (kind, None)
                )
            for category, component in components:
                self.options.addItem(component_selection_title(category, component))
                self.options.item(self.options.count() - 1).setData(
                    Qt.ItemDataRole.UserRole, ("component", category, component)
                )
            for case in self._case_names:
                self.options.addItem(tr("ui.observe_panel.case_value", case=case))
                self.options.item(self.options.count() - 1).setData(
                    Qt.ItemDataRole.UserRole, ("case", case)
                )
            row = 0
            if selected_key is not None:
                for index in range(self.options.count()):
                    if self._option_key(self.options.item(index)) == selected_key:
                        row = index
                        break
            self.options.setCurrentRow(row)
        finally:
            self.options.blockSignals(False)


# ---------------------------------------------------------------------------
# observer page: polling and job control
# ---------------------------------------------------------------------------


class ObserverControls(QWidget):
    """Run the task selected by the definition page or File menu."""

    runStateChanged = Signal()
    resultFolderChanged = Signal(str)
    resultsUpdated = Signal()
    outputReceived = Signal(int, str)

    def __init__(self, parent=None):
        """Initialize ObserverControls and its configuration state.

        Args:
            parent: Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(parent)
        self._run = OptimizationRunSession()
        self.task_label = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*theme_manager.palette.layout.zero_margins)

        # top control bar ---------------------------------------------------
        self.task_controls = QWidget()
        bar = QHBoxLayout(self.task_controls)
        bar.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.status = ElidedLabel()
        self.status.setProperty("textRole", "muted")
        bar.addWidget(self.status, 1)
        self.btn_start = QPushButton(tr("ui.observe_panel.start"))
        self.btn_start.setProperty("actionRole", "primary")
        self.btn_start.setProperty("buttonLayout", "prominent")
        self.btn_start.setFixedWidth(CONSTANT.UI.WIDGETS.TASK_ACTION_BUTTON_WIDTH)
        self.btn_start.setToolTip(tr("ui.observe_panel.start_hint"))
        self.btn_start.clicked.connect(self._start)
        bar.addWidget(self.btn_start)
        self.btn_stop = QPushButton(tr("ui.observe_panel.stop"))
        self.btn_stop.setProperty("actionRole", "danger")
        self.btn_stop.setProperty("buttonLayout", "prominent")
        self.btn_stop.setFixedWidth(CONSTANT.UI.WIDGETS.TASK_ACTION_BUTTON_WIDTH)
        self.btn_stop.setToolTip(
            tr("ui.observe_panel.stop_and_keep_result_for_continuation")
        )
        self.btn_stop.clicked.connect(self._stop)
        bar.addWidget(self.btn_stop)
        outer.addWidget(self.task_controls)

        content = QSplitter(Qt.Orientation.Vertical)
        self.panel = ObserverPanel()
        content.addWidget(self.panel)

        output_area = QWidget()
        output_layout = QVBoxLayout(output_area)
        output_layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        output_header = QHBoxLayout()
        self.output_label = QLabel(tr("ui.observe_panel.run_output"))
        output_header.addWidget(self.output_label)
        output_header.addStretch(1)
        self.btn_clear_output = QPushButton(tr("ui.observe_panel.clear"))
        self.btn_clear_output.clicked.connect(self._clear_output)
        output_header.addWidget(self.btn_clear_output)
        output_layout.addLayout(output_header)
        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output_view.setMaximumBlockCount(
            CONSTANT.UI.OBSERVER.OUTPUT_MAXIMUM_BLOCKS
        )
        self.output_view.setPlaceholderText(
            tr(
                "ui.observe_panel.standard_output_and_errors_from_optimization_tasks_appear_here"
            )
        )
        output_layout.addWidget(self.output_view, 1)
        content.addWidget(output_area)
        stretch = deepcopy(
            theme_manager.palette.layout.observer.content_stretch_factors
        )
        content.setStretchFactor(0, stretch[0])
        content.setStretchFactor(1, stretch[1])
        content.setSizes(
            list(theme_manager.palette.layout.observer.content_split_sizes)
        )
        outer.addWidget(content, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(CONSTANT.UI.OBSERVER.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll_once)
        self.outputReceived.connect(self._append_process_output)
        self._update_buttons()
        self._refresh_status()

    # ------------------------------------------------------------------ api
    def is_running(self) -> bool:
        """Whether an optimization task is currently running.

        Returns:
            bool: True if an optimization task is currently running.
        """
        return self._run.active

    def start_definition(self, problem) -> bool:
        """Launch a validated snapshot from the definition workspace.

        Args:
            problem: Editable problem definition shared by the UI application services.

        Returns:
            bool: Launch a validated snapshot from the definition workspace.
        """
        if self.is_running():
            return False
        source = RunSource(RunSourceKind.DEFINITION, label=problem.label)
        if not self._launch(source, lambda: self._run.start_definition(problem)):
            return False
        self.task_label = problem.label
        self.panel.reset()
        return True

    def start_python(self, path: str) -> bool:
        """Launch the script chosen in the File menu.

        Args:
            path (str): Filesystem path read, restored, or written by this operation.

        Returns:
            bool: Launch the script chosen in the File menu.
        """
        source = RunSource(RunSourceKind.PYTHON, path=path)
        if not self._launch(source, lambda: self._run.start_python(path)):
            return False
        self.task_label = Path(path).name
        self.panel.reset()
        return True

    @staticmethod
    def is_result_folder(folder: str) -> bool:
        """Return is result folder.

        Args:
            folder (str): Directory containing the optimization run or archive.

        Returns:
            bool: Is result folder.
        """
        return OptimizationRunSession.is_result_folder(folder)

    def open_result(self, folder: str) -> None:
        """Browse a saved result and prepare continuation without starting a worker.

        Args:
            folder (str): Directory containing the optimization run or archive.
        """
        self._run.select_source(
            RunSource(
                RunSourceKind.CONTINUE,
                path=folder,
                label=Path(folder).name,
            )
        )
        self.task_label = Path(folder).name
        self._clear_output()
        self.panel.reset()
        self.panel.chk_follow.setChecked(True)
        self._show_progress(self._run.poll())
        self._refresh_status()
        self._update_buttons()

    def _refresh_status(self) -> None:
        """Status line for the current source / idle state."""
        src = self._run.source
        if src is not None:
            self.status.setText(self._source_status(src))
            return
        if self._run.active:
            return  # running-status lines are set by the run methods
        self.status.setText(tr("ui.observe_panel.no_task"))

    def _start(self) -> bool:
        if self._run.active:
            return False
        source = self._run.source
        if source is None:
            return False
        target = None
        if source.kind is RunSourceKind.CONTINUE:
            dialog = ContinueDialog(
                max_step=last_completed_iteration(source.path), parent=self
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
            target = dialog.target_iteration()
        return self._launch(source, lambda: self._run.start_selected(target), target)

    def _launch(
        self,
        source: RunSource,
        launch: Callable[[], object],
        target: int | None = None,
    ) -> bool:
        try:
            launch()
        except Exception as exc:
            key = (
                "ui.observe_panel.continue_failed"
                if source.kind is RunSourceKind.CONTINUE
                else "ui.observe_panel.launch_failed"
            )
            QMessageBox.warning(self, tr(key), str(exc))
            return False
        self.output_view.clear()
        self._run.stream_output(self.outputReceived.emit)
        if source.kind is RunSourceKind.CONTINUE:
            if target is not None and target < self.panel.iteration:
                self.panel.show_iteration(source.path, target)
            self.status.setText(
                tr(
                    "ui.observe_panel.continuing_optimization_from_step_value",
                    value_0=target or last_completed_iteration(source.path),
                )
            )
        elif source.kind is RunSourceKind.DEFINITION:
            self.status.setText(
                tr(
                    "ui.observe_panel.starting_optimization_from_scratch_waiting_for_the_first_step"
                )
            )
        else:
            self.status.setText(
                tr(
                    "ui.observe_panel.optimizing_from_value_waiting_for_the_first_step",
                    value_0=os.path.basename(source.path),
                )
            )
        self._timer.start()
        self._update_buttons()
        return True

    def _stop(self) -> None:
        if not self._stop_job():
            return
        if (
            self._run.source is not None
            and self._run.source.kind is RunSourceKind.CONTINUE
        ):
            self.status.setText(
                tr(
                    "ui.observe_panel.optimization_paused_at_step",
                    iteration=self._run.last_iteration,
                )
            )
        else:
            self.status.setText(
                tr("ui.observe_panel.optimization_stopped_without_checkpoint")
            )
        self._update_buttons()

    def _stop_job(self) -> bool:
        if self._run.active:
            try:
                self._run.stop()
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                QMessageBox.warning(self, tr("ui.observe_panel.stop_failed"), str(exc))
                return False
            self._timer.stop()
            self._show_progress(self._run.poll())
        self._update_buttons()
        return True

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
            if (
                progress.iteration > 0
                and self._run.folder
                and self._run.can_resume(self._run.folder)
            ):
                self._run.source = RunSource(
                    RunSourceKind.CONTINUE,
                    path=self._run.folder,
                    label=Path(self._run.folder).name,
                )
            self.status.setText(
                tr("ui.observe_panel.optimization_failed", code=progress.exit_code)
                if progress.exit_code
                else tr("ui.observe_panel.optimization_finished")
            )
            self._update_buttons()
        elif progress.changed and progress.iteration:
            self.status.setText(
                tr(
                    "ui.observe_panel.optimization_running_step_value_completed",
                    value_0=progress.iteration,
                )
            )

    def _show_progress(self, progress: RunProgress) -> None:
        if progress.folder is None:
            return
        if self.panel.path_result != progress.folder:
            self.resultFolderChanged.emit(progress.folder)
            self.panel.ensure_loaded(progress.folder)
        self.panel.refresh_logs()
        if progress.iteration >= 1 and (
            progress.changed or self.panel.iteration != progress.iteration
        ):
            self.panel.show_iteration(progress.folder, progress.iteration)
        self.resultsUpdated.emit()

    def _update_buttons(self) -> None:
        running = self._run.active
        src = self._run.source
        self.btn_stop.setEnabled(running)
        self.btn_stop.setVisible(running)
        if src is None or src.kind is RunSourceKind.CONTINUE:
            self.btn_start.setText(tr("ui.observe_panel.continue"))
        else:
            self.btn_start.setText(tr("ui.observe_panel.start"))
        can_start = src is not None and (
            src.kind is not RunSourceKind.CONTINUE or self._run.can_resume(src.path)
        )
        self.btn_start.setEnabled(not running and can_start)
        self.btn_start.setVisible(not running)
        self.btn_start.setToolTip(
            tr(
                "ui.observe_panel.continue_unavailable_hint"
                if not can_start
                else "ui.observe_panel.start_hint"
            )
        )
        self.runStateChanged.emit()

    @staticmethod
    def _source_status(source: RunSource) -> str:
        if source.kind is RunSourceKind.DEFINITION:
            return tr(
                "ui.observe_panel.current_task_fresh_run_definition_value",
                value_0=source.label,
            )
        if source.kind is RunSourceKind.PYTHON:
            filename = os.path.basename(source.path)
            return tr(
                "ui.observe_panel.current_task_fresh_run_script_value", value_0=filename
            )
        return tr(
            "ui.observe_panel.current_task_continue_result_value", value_0=source.label
        )

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the observer's static texts."""
        self.btn_start.setToolTip(tr("ui.observe_panel.start_hint"))
        self.btn_stop.setText(tr("ui.observe_panel.stop"))
        self.btn_stop.setToolTip(
            tr("ui.observe_panel.stop_and_keep_result_for_continuation")
        )
        self.output_label.setText(tr("ui.observe_panel.run_output"))
        self.btn_clear_output.setText(tr("ui.observe_panel.clear"))
        self.output_view.setPlaceholderText(
            tr(
                "ui.observe_panel.standard_output_and_errors_from_optimization_tasks_appear_here"
            )
        )
        self.panel.apply_language()
        self._update_buttons()
        if self._run.active:
            self.status.setText(tr("ui.observe_panel.optimization_running"))
        else:
            self._refresh_status()

    def apply_theme(self) -> None:
        """Apply the active theme to this view and its visualization resources."""
        self.panel.apply_theme()

    def close_cleanup(self) -> bool:
        """Return close cleanup.

        Returns:
            bool: Close cleanup.
        """
        return self._stop_job()
