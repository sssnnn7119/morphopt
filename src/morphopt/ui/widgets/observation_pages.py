"""Result-observation pages shared by the in-window observer.

The widgets in this module render one already-materialised result folder.
They deliberately do not start processes, poll folders, or navigate between
application pages; :mod:`morphopt.ui.observe_panel` owns that coordination.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

import pyvista as pv
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...constants import CONSTANT
from ...postprocess.visualization import (
    add_deformation_mesh,
    add_design_component,
    design_view_options,
)
from ..application.results import ResultLogReader, ResultSession
from ..i18n import tr
from ..presentation.labels import design_view_title
from ..presentation.history import history_table
from ..theme import theme_manager
from ..theme.fonts import chart_font, font_manager
from .viewport import PlotViewport


class LogsPage(QWidget):
    """Display saved task logs; polling is owned by ObserverControls."""

    def __init__(self, parent=None) -> None:
        """Initialize LogsPage and its configuration state.

        Args:
            parent: Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(parent)
        self._reader = ResultLogReader()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        controls = QHBoxLayout()
        self.file_label = QLabel()
        controls.addWidget(self.file_label)
        self.file_selector = QComboBox()
        self.file_selector.currentIndexChanged.connect(self._read_current)
        controls.addWidget(self.file_selector, 1)
        self.follow = QCheckBox()
        self.follow.setChecked(True)
        self.follow.toggled.connect(self._scroll_to_end)
        controls.addWidget(self.follow)
        layout.addLayout(controls)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setMaximumBlockCount(CONSTANT.UI.OBSERVER.OUTPUT_MAXIMUM_BLOCKS)
        self._scroll_maximum = self.text.verticalScrollBar().maximum()
        self.text.verticalScrollBar().rangeChanged.connect(self._scroll_range_changed)
        layout.addWidget(self.text, 1)
        self.apply_language()
        self.file_selector.setEnabled(False)

    def refresh(self, results: ResultSession) -> None:
        """Refresh the LogsPage state.

        Args:
            results (ResultSession): Results retained in their registered load-case or export order.
        """
        files = results.log_files
        current_files = tuple(
            self.file_selector.itemData(index)
            for index in range(self.file_selector.count())
        )
        if tuple(map(str, files)) != current_files:
            selected = self.file_selector.currentData()
            self.file_selector.blockSignals(True)
            try:
                self.file_selector.clear()
                for path in files:
                    self.file_selector.addItem(path.name, str(path))
                    self.file_selector.setItemData(
                        self.file_selector.count() - 1, str(path), Qt.ItemDataRole.ToolTipRole
                    )
                self.file_selector.setCurrentIndex(
                    max(0, self.file_selector.findData(selected)) if files else -1
                )
                self.file_selector.setEnabled(bool(files))
            finally:
                self.file_selector.blockSignals(False)
        self._read_current()

    def _read_current(self) -> None:
        path = self.file_selector.currentData()
        if path is None:
            self._reader.clear()
            self.text.clear()
            self.file_selector.setToolTip("")
            self.text.setPlaceholderText(tr("ui.observe_panel.no_logs"))
            return
        self.file_selector.setToolTip(path)
        file_changed = self._reader.path != Path(path)
        try:
            replace, content = self._reader.read(Path(path))
        except OSError as exc:
            self._reader.clear()
            self.text.clear()
            self.text.setPlaceholderText(tr("ui.observe_panel.log_read_failed", error=exc))
            return
        bar = self.text.verticalScrollBar()
        follow = (
            self._can_follow()
            and (file_changed or bar.value() == bar.maximum())
        )
        # A cursor follows its block when old lines are trimmed from the head.
        # Restoring a scrollbar value alone would change the text being read.
        anchor = QTextCursor(self.text.firstVisibleBlock())
        anchor.setKeepPositionOnInsert(True)
        offset = bar.value() - anchor.blockNumber()
        if replace:
            self.text.clear()
        if content:
            cursor = QTextCursor(self.text.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(content)
        if follow:
            self._scroll_to_end(True)
        else:
            bar.setValue(anchor.blockNumber() + offset)

    def _can_follow(self) -> bool:
        return (
            self.follow.isChecked()
            and not self.text.verticalScrollBar().isSliderDown()
            and not self.text.textCursor().hasSelection()
        )

    def _scroll_range_changed(self, _minimum: int, maximum: int) -> None:
        previous = self._scroll_maximum
        self._scroll_maximum = maximum
        # Layout can change the range after insertion, for example when the
        # horizontal scrollbar appears. Keep following only from the old end.
        if self._can_follow() and self.text.verticalScrollBar().value() == previous:
            self._scroll_to_end(True)

    def _scroll_to_end(self, checked: bool) -> None:
        if checked:
            bar = self.text.verticalScrollBar()
            bar.setValue(bar.maximum())

    def clear(self) -> None:
        """Clear the LogsPage state."""
        self._reader.clear()
        self.file_selector.clear()
        self.file_selector.setEnabled(False)
        self.text.clear()

    def apply_language(self) -> None:
        """Update visible labels using the active application locale."""
        self.file_label.setText(tr("ui.observe_panel.log_file"))
        self.follow.setText(tr("ui.observe_panel.log_follow"))
        self.follow.setToolTip(tr("ui.observe_panel.log_follow_hint"))
        self.text.setPlaceholderText(tr("ui.observe_panel.no_logs"))


class MetricsPage(QWidget):
    """History table and a selectable objective or metric curve."""

    def __init__(self, parent=None):
        """Initialize MetricsPage and its configuration state.

        Args:
            parent: Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.table = QTableWidget()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(
            theme_manager.palette.layout.history.minimum_column_width
        )
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 3)
        controls = QHBoxLayout()
        self.curve_label = QLabel(tr("ui.widgets.observation_pages.display_curve"))
        controls.addWidget(self.curve_label)
        self.curve_selector = QComboBox()
        self.curve_selector.setEnabled(False)
        self.curve_selector.currentIndexChanged.connect(self._draw_curve)
        controls.addWidget(self.curve_selector, 1)
        layout.addLayout(controls)
        self.figure = Figure(
            facecolor=theme_manager.palette.chart.background, layout="constrained"
        )
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas, 2)
        self._last_history = None
        self._last_iteration = 0
        self._curves: list[tuple[str, list[float]]] = []
        font_manager.changed.connect(self._font_changed)

    def update_from_history(self, history, iteration: int) -> None:
        """Render all available history records up to ``iteration``.

        Args:
            history: Iteration records supplying the table, curves, or result selection.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        self._last_history = history
        self._last_iteration = iteration
        table = history_table(history)
        self.table.setColumnCount(len(table.headers))
        self.table.setHorizontalHeaderLabels(table.headers)
        self.table.setRowCount(len(table.rows))
        self.table.clearContents()
        for row_index, values in enumerate(table.rows):
            for column_index, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else value)
                item.setToolTip(item.text())
                self.table.setItem(
                    row_index,
                    column_index,
                    item,
                )
        for column, title in enumerate(table.headers):
            item = self.table.horizontalHeaderItem(column)
            if item is not None:
                item.setToolTip(title)
        self._configure_history_widths()
        self._curves = table.curves
        selected = self.curve_selector.currentIndex()
        self.curve_selector.blockSignals(True)
        try:
            self.curve_selector.clear()
            self.curve_selector.addItems([title for title, _values in self._curves])
            self.curve_selector.setCurrentIndex(
                max(0, min(selected, self.curve_selector.count() - 1))
            )
            self.curve_selector.setEnabled(bool(self._curves))
        finally:
            self.curve_selector.blockSignals(False)
        self._draw_curve()

    def _configure_history_widths(self) -> None:
        """Use a few title-based widths and allow horizontal scrolling."""
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        metrics = header.fontMetrics()
        layout = theme_manager.palette.layout.history
        widths = layout.column_widths
        for column in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(column)
            title = item.text() if item is not None else ""
            required = metrics.horizontalAdvance(title) + layout.column_width_padding
            width = next((size for size in widths if required <= size), widths[-1])
            self.table.setColumnWidth(column, width)

    def _draw_curve(self) -> None:
        index = self.curve_selector.currentIndex()
        title, values = (
            self._curves[index] if 0 <= index < len(self._curves) else ("", [])
        )
        self.figure.clear()
        self.figure.set_facecolor(theme_manager.palette.chart.background)
        axes = self.figure.add_subplot(111)
        axes.set_facecolor(theme_manager.palette.chart.background)
        axes.plot(
            range(1, len(values) + 1),
            values,
            marker="o",
            color=theme_manager.palette.chart.line,
            linewidth=theme_manager.palette.chart.line_width,
            markersize=theme_manager.palette.chart.marker_size,
        )
        axes.set_xlabel(tr("ui.widgets.observation_pages.iteration"))
        axes.set_ylabel(title)
        axes.set_title(
            tr("ui.widgets.observation_pages.series_vs_iteration", value_0=title)
        )
        axes.tick_params(colors=theme_manager.palette.chart.text)
        axes.xaxis.label.set_color(theme_manager.palette.chart.text)
        axes.yaxis.label.set_color(theme_manager.palette.chart.text)
        axes.title.set_color(theme_manager.palette.chart.text)
        for spine in axes.spines.values():
            spine.set_color(theme_manager.palette.chart.grid)
        axes.grid(
            True,
            color=theme_manager.palette.chart.grid,
            linestyle="--",
            linewidth=theme_manager.palette.chart.grid_width,
        )
        labels = [
            axes.title,
            axes.xaxis.label,
            axes.yaxis.label,
            *axes.get_xticklabels(),
            *axes.get_yticklabels(),
            axes.xaxis.get_offset_text(),
            axes.yaxis.get_offset_text(),
        ]
        font = chart_font()
        point_size = font_manager.font("chart").pointSizeF()
        for label in labels:
            size = label.get_fontsize() * (point_size if point_size > 0 else 10) / 10
            label.set_fontproperties(font)
            label.set_fontsize(size)
        self.canvas.draw()

    def _font_changed(self, role: str) -> None:
        if role == "chart" and self._last_history is not None:
            self._draw_curve()

    def apply_language(self) -> None:
        """Refresh translated table headers and chart labels."""
        self.curve_label.setText(tr("ui.widgets.observation_pages.display_curve"))
        if self._last_history is not None:
            self.update_from_history(self._last_history, self._last_iteration)

    def apply_theme(self) -> None:
        """Apply the active theme to this view and its visualization resources."""
        if self._last_history is not None:
            self._configure_history_widths()
            self._draw_curve()
        else:
            self.figure.set_facecolor(theme_manager.palette.chart.background)
            self.canvas.draw()

    def clear(self) -> None:
        """Drop all history data and reset the chart."""
        self._last_history = None
        self._last_iteration = 0
        self._curves = []
        self.curve_selector.clear()
        self.curve_selector.setEnabled(False)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.figure.clear()
        self.figure.set_facecolor(theme_manager.palette.chart.background)
        axes = self.figure.add_subplot(111)
        axes.set_facecolor(theme_manager.palette.chart.background)
        axes.axis("off")
        self.canvas.draw()


class HistorySceneCache:
    """Share one mesh-data budget across the history viewports, keeping each camera independent."""

    def __init__(self) -> None:
        self._frames: OrderedDict[tuple, tuple[tuple, int]] = OrderedDict()
        self._mesh_bytes = 0
        self._selected: dict[PlotViewport, tuple] = {}

    def clear(self, viewport: PlotViewport) -> None:
        """Forget the selected scene and all snapshots belonging to this viewport."""
        self._selected.pop(viewport, None)
        for key in list(self._frames):
            if key[0] is viewport:
                _, size = self._frames.pop(key)
                self._mesh_bytes -= size

    def show(
        self,
        viewport: PlotViewport,
        marker: tuple,
        draw: Callable[[pv.Plotter], bool],
        *,
        copy_meshes: bool = False,
    ) -> None:
        """Draw on first visit and reattach the saved props on subsequent visits.

        An unavailable result is retried on the next refresh. The viewport defers
        construction until visible and coalesces rapid slider movements.
        """
        key = (viewport, marker)
        if self._selected.get(viewport) == marker:
            if key in self._frames:
                self._frames.move_to_end(key)
            return
        self._selected[viewport] = marker

        def build(plotter: pv.Plotter) -> None:
            if key in self._frames:
                actors, _ = self._frames[key]
                for actor in actors:
                    plotter.renderer.AddViewProp(actor)
                self._frames.move_to_end(key)
                plotter.show_axes()
                return
            try:
                if not draw(plotter):
                    self._selected.pop(viewport, None)
                    return
                actors = tuple(plotter.actors.values())
                mappers = [
                    actor.mapper
                    for actor in actors
                    if isinstance(actor, pv.Actor)
                    and isinstance(actor.mapper, pv.DataSetMapper)
                    and actor.mapper.dataset is not None
                ]
                for mapper in mappers:
                    mapper.update()
                size = sum(mapper.dataset.GetActualMemorySize() * 1024 for mapper in mappers)
                budget = CONSTANT.UI.OBSERVER.PREVIEW_CACHE_BYTES
                if not size or size > budget:
                    return
                while self._mesh_bytes + size > budget:
                    _, (_, evicted_bytes) = self._frames.popitem(last=False)
                    self._mesh_bytes -= evicted_bytes
                if copy_meshes:
                    # Params can reuse array storage when restoring the next iteration.
                    for mapper in mappers:
                        mapper.dataset = mapper.dataset.copy(deep=True)
                        mapper.update()
                self._frames[key] = actors, size
                self._mesh_bytes += size
            except Exception:
                self._selected.pop(viewport, None)
                raise

        viewport.rebuild(build)


class UpdatableStructurePage(QWidget):
    """Render one updateable component and one of its available views."""

    def __init__(self, parent=None, *, cache: HistorySceneCache | None = None):
        """Initialize UpdatableStructurePage and its configuration state.

        Args:
            parent: Parent Qt widget; None creates a top-level widget.
            cache: Scene cache shared by the optimization history pages.
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)

        controls = QHBoxLayout()
        self.view_label = QLabel(tr("ui.widgets.observation_pages.display_view"))
        controls.addWidget(self.view_label)
        self.view_selector = QComboBox()
        self.view_selector.currentIndexChanged.connect(self._view_changed)
        controls.addWidget(self.view_selector, 1)
        layout.addLayout(controls)

        self.viewport = PlotViewport(self)
        layout.addWidget(self.viewport)
        self._results: ResultSession | None = None
        self._iteration = 0
        self._component = None
        self._views = ()
        self._scenes = cache if cache is not None else HistorySceneCache()
        self._theme_pending = False

    def build(self, results: ResultSession, iteration: int, component=None) -> None:
        """Build the UpdatableStructurePage state.

        Args:
            results (ResultSession): Results retained in their registered load-case or export order.
            iteration (int): Iteration index associated with the saved or current model state.
            component: Model, result, or interface component processed by the operation.
        """
        self._results = results
        self._iteration = iteration
        if component is None:
            components = results.fea_components()
            component = components[0][1] if components else None
        self._component = component
        self._sync_view_selector()
        self._render_selected()

    def _view_changed(self, _index: int) -> None:
        self._render_selected()

    @property
    def component(self):
        """Return the component currently shown in the viewport."""
        return self._component

    @property
    def current_view(self):
        """Return the selected design view descriptor, if any."""
        return self._selected_view()

    def _sync_view_selector(self) -> None:
        current = self.view_selector.currentData()
        self._views = design_view_options(self._component)
        self.view_selector.blockSignals(True)
        try:
            self.view_selector.clear()
            for view in self._views:
                self.view_selector.addItem(design_view_title(view), view.key)
            if not self._views:
                self.view_selector.addItem(
                    tr("ui.widgets.observation_pages.no_updateable_components"), None
                )
                self.view_selector.setEnabled(False)
            else:
                self.view_selector.setEnabled(True)
                index = self.view_selector.findData(current)
                self.view_selector.setCurrentIndex(max(index, 0))
        finally:
            self.view_selector.blockSignals(False)

    def _selected_view(self):
        key = self.view_selector.currentData()
        return next((view for view in self._views if view.key == key), None)

    def _render_selected(self) -> None:
        if (
            self._results is None
            or self._results.params is None
            or self._results.folder is None
        ):
            return
        selected = self._component
        view = self._selected_view()
        marker = (
            self._results.folder,
            self._iteration,
            id(selected) if selected is not None else None,
            view.key if view is not None else None,
        )
        results = self._results
        iteration = self._iteration

        def build_scene(plotter) -> bool:
            component = (
                results.load_design_component(selected, iteration) if selected is not None else None
            )
            style = theme_manager.palette.viewer
            add_design_component(
                plotter,
                component,
                geometry_color=(
                    style.geometry.instance_colors[0]
                    if style.geometry.instance_colors
                    else style.geometry.uninstanced_color
                ),
                ambient=style.render.mesh_ambient,
                diffuse=style.render.mesh_diffuse,
                specular=style.render.mesh_specular,
                specular_power=style.render.mesh_specular_power,
                boundary_shell_opacity=style.geometry.boundary_shell_opacity,
                view=view,
            )

            return True

        self._scenes.show(self.viewport, marker, build_scene, copy_meshes=True)

    def clear_view(self) -> None:
        """Empty the viewport and forget the previous render marker."""
        self._results = None
        self._component = None
        self._views = ()
        self._scenes.clear(self.viewport)
        self.view_selector.blockSignals(True)
        try:
            self.view_selector.clear()
            self.view_selector.addItem(
                tr("ui.widgets.observation_pages.no_updatable_components"), None
            )
            self.view_selector.setEnabled(False)
        finally:
            self.view_selector.blockSignals(False)
        try:
            self.viewport.rebuild(lambda _plotter: None)
        except Exception as exc:  # pragma: no cover - best-effort rendering
            print(tr("ui.messages.structure_preview_clear_failed", error=exc))

    def apply_language(self) -> None:
        """Refresh the view selector without rebuilding the scene."""
        self.view_label.setText(tr("ui.widgets.observation_pages.display_view"))
        self._sync_view_selector()

    def apply_theme(self) -> None:
        """Apply the active theme to this view and its visualization resources."""
        self.viewport.apply_theme()
        self._scenes.clear(self.viewport)
        if self.isVisible():
            self._render_selected()
        else:
            self._theme_pending = True

    def showEvent(self, event) -> None:
        """Refresh deferred content when the widget becomes visible.

        Args:
            event: Qt event delivered to this widget or event filter.
        """
        super().showEvent(event)
        if self._theme_pending:
            self._theme_pending = False
            self._render_selected()


class DeformationCasePage(QWidget):
    """One persistent viewport shared by all load cases and result tasks."""

    def __init__(self, parent=None, *, cache: HistorySceneCache | None = None):
        """Initialize DeformationCasePage and its configuration state.

        Args:
            parent: Parent Qt widget; None creates a top-level widget.
            cache: Scene cache shared by the optimization history pages.
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.viewport = PlotViewport(self)
        layout.addWidget(self.viewport)
        self._scenes = cache if cache is not None else HistorySceneCache()

    def build(self, results: ResultSession, iteration: int, case_name: str) -> None:
        """Build the DeformationCasePage state.

        Args:
            results (ResultSession): Results retained in their registered load-case or export order.
            iteration (int): Iteration index associated with the saved or current model state.
            case_name (str): Registered string load-case name.
        """
        marker = (results.folder, iteration, case_name)

        def build_scene(plotter) -> bool:
            mesh = results.deformation_mesh(case_name, iteration)
            if mesh is None:
                return False
            add_deformation_mesh(plotter, mesh, theme_manager.palette.deformation_mesh_color)
            return True

        self._scenes.show(self.viewport, marker, build_scene)

    def clear_view(self) -> None:
        """Drop old task data without destroying the native rendering window."""
        self._scenes.clear(self.viewport)
        self.viewport.rebuild(lambda _plotter: None)

    def apply_theme(self) -> None:
        """Apply the active theme to this view and its visualization resources."""
        self.viewport.apply_theme()
        self._scenes.clear(self.viewport)
        actor = self.viewport.plotter.actors.get("deformation-mesh")
        if actor is not None:
            actor.prop.color = theme_manager.palette.deformation_mesh_color
            if self.viewport.isVisible():
                self.viewport.plotter.render()
