"""Result-observation pages shared by the in-window observer.

The widgets in this module render one already-materialised result folder.
They deliberately do not start processes, poll folders, or navigate between
application pages; :mod:`morphopt.ui.observe_panel` owns that coordination.
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from pyvistaqt import QtInteractor


class PlotViewport(QWidget):
    """A PyVista viewport with a resettable scene."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)
        self.plotter.set_background("black")

    def rebuild(self, build_scene) -> None:
        """Clear the scene, call ``build_scene(plotter)``, then render it."""
        self.plotter.clear()
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

    def update_from_history(self, history, iteration: int) -> None:
        """Render all available history records up to ``iteration``."""
        objectives = list(history.history_objective)
        metrics = history.history_metrics
        deformation = history.history_deformation
        metric_count = self._metric_count(metrics)
        deformation_labels, flat_deformation = self._deformation_columns(deformation)
        headers = (
            ["Iteration", "Objective"]
            + [f"Metric {index}" for index in range(metric_count)]
            + ["Init", "FEA", "Sens", "Update", "Elements", "Nodes"]
            + deformation_labels
        )
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(objectives))

        times = getattr(history, "history_time", None)
        elements = getattr(history, "history_num_elements", None)
        nodes = getattr(history, "history_num_nodes", None)
        for row_index, objective in enumerate(objectives):
            values = self._row_values(
                row_index, objective, metrics, metric_count, times, elements,
                nodes, flat_deformation,
            )
            for column_index, value in enumerate(values):
                if value is not None:
                    self.table.setItem(
                        row_index, column_index, QTableWidgetItem(value))
        self._draw_objectives(objectives)

    @staticmethod
    def _metric_count(metrics) -> int:
        if metrics is None or metrics.size == 0:
            return 0
        return metrics.shape[-1] if metrics.ndim > 1 else 1

    @staticmethod
    def _deformation_columns(deformation) -> tuple[list[str], object]:
        if deformation is None or deformation.size == 0:
            return [], None
        if deformation.ndim == 2:
            return ([f"U0-{index}" for index in range(deformation.shape[1])],
                    deformation)
        if deformation.ndim == 3:
            tasks, dimensions = deformation.shape[1:]
            labels = [f"U{task}-{dimension}"
                      for task in range(tasks)
                      for dimension in range(dimensions)]
            return labels, deformation.reshape(deformation.shape[0], -1)
        return [], None

    @staticmethod
    def _row_values(row_index, objective, metrics, metric_count, times,
                    elements, nodes, flat_deformation) -> list[str | None]:
        values: list[str | None] = [str(row_index + 1), f"{objective:.6f}"]
        for metric_index in range(metric_count):
            if metrics is None or row_index >= len(metrics):
                values.append(None)
                continue
            metric_row = metrics[row_index] if metrics.ndim > 1 else metrics[row_index]
            metric_value = (metric_row[metric_index] if np.ndim(metric_row)
                            else metric_row)
            values.append(f"{metric_value:.6f}")
        if times is not None and row_index < len(times):
            values.extend(f"{value:.2f}" for value in times[row_index][:4])
            values.extend([None] * max(0, 4 - len(times[row_index][:4])))
        else:
            values.extend([None] * 4)
        values.append(str(elements[row_index]) if elements is not None and row_index < len(elements)
                      else None)
        values.append(str(nodes[row_index]) if nodes is not None and row_index < len(nodes)
                      else None)
        if flat_deformation is not None and row_index < len(flat_deformation):
            values.extend(f"{value:.4e}" for value in flat_deformation[row_index])
        return values

    def _draw_objectives(self, objectives: list[float]) -> None:
        plt.style.use("dark_background")
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.plot(range(1, len(objectives) + 1), objectives, marker="o", color="cyan")
        axes.set_xlabel("Iteration")
        axes.set_ylabel("Objective")
        axes.set_title("Objective vs Iteration")
        axes.grid(True, color="white", linestyle="--", linewidth=0.5)
        self.canvas.draw()

    def clear(self) -> None:
        """Drop all history data and reset the chart."""
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.axis("off")
        self.canvas.draw()


class GeometryPage(QWidget):
    """Geometry at one selected result iteration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.viewport = PlotViewport(self)
        layout.addWidget(self.viewport)
        self._last_rendered: tuple[str, int] | None = None

    def build(self, parameters, result_folder: str, iteration: int) -> None:
        """Load and render geometry unless this exact iteration is already shown."""
        marker = (result_folder, iteration)
        if marker == self._last_rendered:
            return

        def build_scene(plotter) -> None:
            plotter.enable_lightkit()
            parameters.load(foldpath=f"{result_folder}/log/", iteration=iteration)
            parameters.plot(plotter=plotter)
            plotter.show_axes()

        try:
            self.viewport.rebuild(build_scene)
            self._last_rendered = marker
        except Exception as exc:  # pragma: no cover - best-effort rendering
            print(f"Geometry preview failed at iteration {iteration}: {exc}")

    def clear_view(self) -> None:
        """Empty the viewport and forget the previous render marker."""
        self._last_rendered = None
        try:
            self.viewport.rebuild(lambda _plotter: None)
        except Exception as exc:  # pragma: no cover - best-effort rendering
            print(f"Geometry preview clear failed: {exc}")


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

    def build(self, result_folder: str, iteration: int) -> None:
        """Render this load case unless it is already current."""
        marker = (result_folder, iteration)
        if marker == self._last_rendered:
            return
        mesh_path = (
            f"{result_folder}/log/deformation/"
            f"task_{self.case_index}_iter_{iteration}.stl"
        )

        def build_scene(plotter) -> None:
            plotter.enable_lightkit()
            if os.path.exists(mesh_path):
                mesh = pv.read(mesh_path)
                plotter.add_mesh(
                    mesh, color=(40 / 255, 120 / 255, 181 / 255),
                    opacity=1.0, show_edges=True,
                )
                plotter.show_axes()

        self.viewport.rebuild(build_scene)
        self._last_rendered = marker
