"""Result-observation pages shared by the in-window observer.

The widgets in this module render one already-materialised result folder.
They deliberately do not start processes, poll folders, or navigate between
application pages; :mod:`morphopt.ui.observe_panel` owns that coordination.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor

from ..application.results import ResultSession
from ..i18n import tr
from ..presentation.history import history_table
from ..presentation.labels import typed_title
from ..theme import theme_manager
from .plot_style import apply_plotter_theme, configure_plotter


class PlotViewport(QWidget):
    """A PyVista viewport with a resettable scene."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        layout.setSpacing(theme_manager.palette.layout.zero_spacing)
        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)
        configure_plotter(self.plotter)
        self._theme_pending = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._theme_pending:
            self._theme_pending = False
            apply_plotter_theme(self.plotter)
            self.plotter.render()

    def apply_theme(self) -> None:
        if not self.isVisible():
            self._theme_pending = True
            return
        apply_plotter_theme(self.plotter)
        self.plotter.render()

    def rebuild(self, build_scene) -> None:
        """Clear the scene, call ``build_scene(plotter)``, then render it."""
        self.plotter.clear()
        configure_plotter(self.plotter)
        build_scene(self.plotter)
        self.plotter.reset_camera()
        self.plotter.render()


class MetricsPage(QWidget):
    """History table and objective-versus-iteration chart."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.table = QTableWidget()
        layout.addWidget(self.table, 3)
        self.figure = Figure(facecolor=theme_manager.palette.chart.background)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas, 2)
        self._last_history = None
        self._last_iteration = 0

    def update_from_history(self, history, iteration: int) -> None:
        """Render all available history records up to ``iteration``."""
        self._last_history = history
        self._last_iteration = iteration
        table = history_table(history)
        self.table.setColumnCount(len(table.headers))
        self.table.setHorizontalHeaderLabels(table.headers)
        self.table.setRowCount(len(table.rows))
        self.table.clearContents()
        for row_index, values in enumerate(table.rows):
            for column_index, value in enumerate(values):
                if value is not None:
                    self.table.setItem(row_index, column_index, QTableWidgetItem(value))
        self._draw_objectives(table.objectives)

    def _draw_objectives(self, objectives: list[float]) -> None:
        # Prefer an installed CJK font so translated chart labels do not turn
        # into tofu boxes on Linux; Matplotlib silently falls back elsewhere.
        plt.rcParams["font.sans-serif"] = [
            "Noto Sans CJK SC",
            "Noto Sans CJK TC",
            "DejaVu Sans",
            "sans-serif",
        ]
        plt.rcParams["axes.unicode_minus"] = False
        self.figure.clear()
        self.figure.set_facecolor(theme_manager.palette.chart.background)
        axes = self.figure.add_subplot(111)
        axes.set_facecolor(theme_manager.palette.chart.background)
        axes.plot(
            range(1, len(objectives) + 1),
            objectives,
            marker="o",
            color=theme_manager.palette.chart.line,
            linewidth=theme_manager.palette.chart.line_width,
            markersize=theme_manager.palette.chart.marker_size,
        )
        axes.set_xlabel(tr("ui.widgets.observation_pages.iteration"))
        axes.set_ylabel(tr("ui.widgets.observation_pages.objective"))
        axes.set_title(tr("ui.widgets.observation_pages.objective_vs_iteration"))
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
        self.canvas.draw()

    def apply_language(self) -> None:
        """Refresh translated table headers and chart labels."""
        if self._last_history is not None:
            self.update_from_history(self._last_history, self._last_iteration)

    def apply_theme(self) -> None:
        if self._last_history is not None:
            self._draw_objectives(history_table(self._last_history).objectives)
        else:
            self.figure.set_facecolor(theme_manager.palette.chart.background)
            self.canvas.draw()

    def clear(self) -> None:
        """Drop all history data and reset the chart."""
        self._last_history = None
        self._last_iteration = 0
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.figure.clear()
        self.figure.set_facecolor(theme_manager.palette.chart.background)
        axes = self.figure.add_subplot(111)
        axes.set_facecolor(theme_manager.palette.chart.background)
        axes.axis("off")
        self.canvas.draw()


class UpdatableStructurePage(QWidget):
    """Render one updateable component at a selected result iteration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)

        controls = QHBoxLayout()
        self.component_label = QLabel(
            tr("ui.widgets.observation_pages.display_component")
        )
        controls.addWidget(self.component_label)
        self.component_selector = QComboBox()
        self.component_selector.currentIndexChanged.connect(self._component_changed)
        controls.addWidget(self.component_selector, 1)
        layout.addLayout(controls)

        self.viewport = PlotViewport(self)
        layout.addWidget(self.viewport)
        self._results: ResultSession | None = None
        self._iteration = 0
        self._last_rendered: tuple[str, int, int | None] | None = None
        self._theme_pending = False

    def build(self, results: ResultSession, iteration: int) -> None:
        self._results = results
        self._iteration = iteration
        self._sync_component_selector()
        self._render_selected()

    def _component_changed(self, _index: int) -> None:
        self._last_rendered = None
        self._render_selected()

    @staticmethod
    def _component_label(category: str, component) -> str:
        """Return an unambiguous label for one updateable component."""
        name = component.name
        part_name = getattr(component, "part_name", None)
        if part_name and part_name != component.name:
            name = tr(
                "ui.observation.component_name_with_part", name=name, part=part_name
            )
        category_key = {
            "Part": "ui.widgets.model_tree.container.geometry",
            "FEA": "ui.widgets.model_tree.container.loads_group",
            "Material": "ui.widgets.model_tree.container.materials",
        }[category]
        return tr(
            "ui.observation.component_title",
            category=tr(category_key),
            title=typed_title(name, type(component).__name__),
        )

    def _sync_component_selector(self) -> None:
        components = self._results.fea_components() if self._results else ()
        current = self.component_selector.currentData()
        self.component_selector.blockSignals(True)
        try:
            self.component_selector.clear()
            for category, component in components:
                self.component_selector.addItem(
                    self._component_label(category, component), component
                )
            if not components:
                self.component_selector.addItem(
                    tr("ui.widgets.observation_pages.no_updateable_components"), None
                )
                self.component_selector.setEnabled(False)
            else:
                self.component_selector.setEnabled(True)
                index = self.component_selector.findData(current)
                self.component_selector.setCurrentIndex(max(index, 0))
        finally:
            self.component_selector.blockSignals(False)

    def _render_selected(self) -> None:
        if (
            self._results is None
            or self._results.params is None
            or self._results.folder is None
        ):
            return
        selected = self.component_selector.currentData()
        marker = (
            self._results.folder,
            self._iteration,
            id(selected) if selected is not None else None,
        )
        if marker == self._last_rendered:
            return

        def build_scene(plotter) -> None:
            if selected is not None:
                existing = set(plotter.actors)
                selected.plot(plotter=plotter)
                style = theme_manager.palette.viewer
                surface_count = int(getattr(selected, "num_surface_interfaces", 0) or 0)
                for name, actor in plotter.actors.items():
                    if name in existing:
                        continue
                    mapper = actor.mapper
                    if mapper is not None and mapper.scalar_visibility:
                        # Density and other scalar maps encode result data.
                        continue
                    actor.prop.color = (
                        style.geometry.instance_colors[0]
                        if style.geometry.instance_colors
                        else style.geometry.uninstanced_color
                    )
                    actor.prop.ambient = style.render.mesh_ambient
                    actor.prop.diffuse = style.render.mesh_diffuse
                    actor.prop.specular = style.render.mesh_specular
                    actor.prop.specular_power = style.render.mesh_specular_power
                    if surface_count > 1 and str(name).endswith("surface-0"):
                        actor.prop.opacity = style.geometry.boundary_shell_opacity
            plotter.show_axes()

        try:
            self._results.load_parameters(self._iteration)
            self.viewport.rebuild(build_scene)
            self._last_rendered = marker
        except Exception as exc:  # pragma: no cover - best-effort rendering
            print(
                tr(
                    "ui.messages.structure_preview_failed",
                    iteration=self._iteration,
                    error=exc,
                )
            )

    def clear_view(self) -> None:
        """Empty the viewport and forget the previous render marker."""
        self._results = None
        self._last_rendered = None
        self.component_selector.blockSignals(True)
        try:
            self.component_selector.clear()
            self.component_selector.addItem(
                tr("ui.widgets.observation_pages.no_updatable_components"), None
            )
            self.component_selector.setEnabled(False)
        finally:
            self.component_selector.blockSignals(False)
        try:
            self.viewport.rebuild(lambda _plotter: None)
        except Exception as exc:  # pragma: no cover - best-effort rendering
            print(tr("ui.messages.structure_preview_clear_failed", error=exc))

    def apply_language(self) -> None:
        """Refresh the component selector without rebuilding the scene."""
        self.component_label.setText(
            tr("ui.widgets.observation_pages.display_component")
        )
        self._sync_component_selector()

    def apply_theme(self) -> None:
        self.viewport.apply_theme()
        if self.isVisible():
            self._last_rendered = None
            self._render_selected()
        else:
            self._theme_pending = True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._theme_pending:
            self._theme_pending = False
            self._last_rendered = None
            self._render_selected()


class DeformationCasePage(QWidget):
    """Deformed mesh for one load case at the selected iteration."""

    def __init__(self, case_index: int, parent=None):
        super().__init__(parent)
        self.case_index = case_index
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.viewport = PlotViewport(self)
        layout.addWidget(self.viewport)
        self._last_rendered: tuple[str, int] | None = None

    def build(self, results: ResultSession, iteration: int) -> None:
        marker = (results.folder, iteration)
        if marker == self._last_rendered:
            return
        mesh = results.deformation_mesh(self.case_index, iteration)

        def build_scene(plotter) -> None:
            if mesh is not None:
                plotter.add_mesh(
                    mesh,
                    color=theme_manager.palette.deformation_mesh_color,
                    opacity=1.0,
                    show_edges=True,
                    name="deformation-mesh",
                )
                plotter.show_axes()

        self.viewport.rebuild(build_scene)
        if mesh is not None:
            self._last_rendered = marker

    def apply_theme(self) -> None:
        self.viewport.apply_theme()
        actor = self.viewport.plotter.actors.get("deformation-mesh")
        if actor is not None:
            actor.prop.color = theme_manager.palette.deformation_mesh_color
            if self.viewport.isVisible():
                self.viewport.plotter.render()
