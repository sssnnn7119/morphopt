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

from ..i18n import tr
from ..application.results import ResultSession
from ..presentation.history import history_table
from ..presentation.labels import typed_title
from .plot_style import configure_plotter


class PlotViewport(QWidget):
    """A PyVista viewport with a resettable scene."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)
        configure_plotter(self.plotter)

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
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget()
        layout.addWidget(self.table, 3)
        self.figure = Figure(facecolor="#121212")
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
        plt.style.use("dark_background")
        # Prefer an installed CJK font so translated chart labels do not turn
        # into tofu boxes on Linux; Matplotlib silently falls back elsewhere.
        plt.rcParams["font.sans-serif"] = [
            "Noto Sans CJK SC", "Noto Sans CJK TC", "DejaVu Sans", "sans-serif",
        ]
        plt.rcParams["axes.unicode_minus"] = False
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.plot(range(1, len(objectives) + 1), objectives, marker="o", color="cyan")
        axes.set_xlabel(tr('ui.widgets.observation_pages.iteration'))
        axes.set_ylabel(tr('ui.widgets.observation_pages.objective'))
        axes.set_title(tr('ui.widgets.observation_pages.objective_vs_iteration'))
        axes.grid(True, color="white", linestyle="--", linewidth=0.5)
        self.canvas.draw()

    def apply_language(self) -> None:
        """Refresh translated table headers and chart labels."""
        if self._last_history is not None:
            self.update_from_history(self._last_history, self._last_iteration)

    def clear(self) -> None:
        """Drop all history data and reset the chart."""
        self._last_history = None
        self._last_iteration = 0
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.axis("off")
        self.canvas.draw()


class UpdatableStructurePage(QWidget):
    """Render one updateable interface at a selected result iteration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        self.interface_label = QLabel(tr('ui.widgets.observation_pages.display_interface'))
        controls.addWidget(self.interface_label)
        self.interface_selector = QComboBox()
        self.interface_selector.currentIndexChanged.connect(
            self._interface_changed
        )
        controls.addWidget(self.interface_selector, 1)
        layout.addLayout(controls)

        self.viewport = PlotViewport(self)
        layout.addWidget(self.viewport)
        self._results: ResultSession | None = None
        self._iteration = 0
        self._last_rendered: tuple[str, int, int | None] | None = None

    def build(self, results: ResultSession, iteration: int) -> None:
        self._results = results
        self._iteration = iteration
        self._sync_interface_selector()
        self._render_selected()

    def _interface_changed(self, _index: int) -> None:
        self._last_rendered = None
        self._render_selected()

    @staticmethod
    def _interface_label(category: str, interface) -> str:
        """Return an unambiguous label for one updateable interface."""
        name = interface.name
        part_name = getattr(interface, "part_name", None)
        if part_name and part_name != interface.name:
            name = tr("ui.observation.interface_name_with_part", name=name, part=part_name)
        category_key = {
            "Part": "ui.widgets.model_tree.container.geometry",
            "FEA": "ui.widgets.model_tree.container.loads_group",
            "Material": "ui.widgets.model_tree.container.materials",
        }[category]
        return tr(
            "ui.observation.interface_title",
            category=tr(category_key),
            title=typed_title(name, type(interface).__name__),
        )

    def _sync_interface_selector(self) -> None:
        interfaces = self._results.interfaces() if self._results else ()
        current = self.interface_selector.currentData()
        self.interface_selector.blockSignals(True)
        try:
            self.interface_selector.clear()
            for category, interface in interfaces:
                self.interface_selector.addItem(
                    self._interface_label(category, interface), interface
                )
            if not interfaces:
                self.interface_selector.addItem(
                    tr('ui.widgets.observation_pages.no_updateable_interfaces'), None
                )
                self.interface_selector.setEnabled(False)
            else:
                self.interface_selector.setEnabled(True)
                index = self.interface_selector.findData(current)
                self.interface_selector.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.interface_selector.blockSignals(False)

    def _render_selected(self) -> None:
        if self._results is None or self._results.params is None or self._results.folder is None:
            return
        selected = self.interface_selector.currentData()
        marker = (
            self._results.folder,
            self._iteration,
            id(selected) if selected is not None else None,
        )
        if marker == self._last_rendered:
            return

        def build_scene(plotter) -> None:
            if selected is not None:
                selected.plot(plotter=plotter)
            plotter.show_axes()

        try:
            self._results.load_parameters(self._iteration)
            self.viewport.rebuild(build_scene)
            self._last_rendered = marker
        except Exception as exc:  # pragma: no cover - best-effort rendering
            print(
                tr("ui.messages.structure_preview_failed", iteration=self._iteration, error=exc)
            )

    def clear_view(self) -> None:
        """Empty the viewport and forget the previous render marker."""
        self._results = None
        self._last_rendered = None
        self.interface_selector.blockSignals(True)
        try:
            self.interface_selector.clear()
            self.interface_selector.addItem(
                tr('ui.widgets.observation_pages.no_updatable_interfaces'), None
            )
            self.interface_selector.setEnabled(False)
        finally:
            self.interface_selector.blockSignals(False)
        try:
            self.viewport.rebuild(lambda _plotter: None)
        except Exception as exc:  # pragma: no cover - best-effort rendering
            print(tr("ui.messages.structure_preview_clear_failed", error=exc))

    def apply_language(self) -> None:
        """Refresh the interface selector without rebuilding the scene."""
        self.interface_label.setText(tr('ui.widgets.observation_pages.display_interface'))
        self._sync_interface_selector()


class DeformationCasePage(QWidget):
    """Deformed mesh for one load case at the selected iteration."""

    def __init__(self, case_index: int, parent=None):
        super().__init__(parent)
        self.case_index = case_index
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
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
                plotter.add_mesh(mesh, color=(40 / 255, 120 / 255, 181 / 255), opacity=1.0, show_edges=True)
                plotter.show_axes()
        self.viewport.rebuild(build_scene)
        if mesh is not None:
            self._last_rendered = marker
