"""Render scene descriptions; owns actors, never reads problem definitions."""
from __future__ import annotations

from functools import singledispatchmethod
import numpy as np
import pyvista as pv
from ..visualization.scene import (
    PreviewScene,
    LoadScene,
    MeshItem,
    LabelItem,
    MessageItem,
    ArrowLoad,
    MomentLoad,
    SpringLoad,
    MarkerLoad,
)


class PreviewRenderer:
    def __init__(self, plotter):
        self.plotter = plotter
        self._overlay_actors: list = []
        self._scale = 10.0

    def draw_scene(self, scene: PreviewScene) -> None:
        self.plotter.clear()
        self._overlay_actors.clear()
        for item in scene.items:
            self.draw(item)

    def draw_loads(self, scene: LoadScene | None, legend: str = "") -> None:
        for actor in self._overlay_actors:
            self.plotter.remove_actor(actor, render=False)
        self._overlay_actors.clear()
        if scene is not None:
            self._scale = scene.scale
            for item in scene.items:
                actor = self.draw(item)
                if actor is not None:
                    self._overlay_actors.append(actor)
            if legend:
                self._overlay_actors.append(self.plotter.add_text(
                    legend,
                    position="lower_left",
                    font_size=9,
                    color="#d8dee9",
                ))
        self.plotter.render()

    @singledispatchmethod
    def draw(self, item):
        raise TypeError(f"Unsupported scene item: {type(item).__name__}")

    @draw.register
    def _(self, item: MeshItem):
        return self.plotter.add_mesh(item.mesh, **item.options)

    @draw.register
    def _(self, item: LabelItem):
        return self.plotter.add_point_labels(item.points, item.labels, **item.options)

    @draw.register
    def _(self, item: MessageItem):
        return self.plotter.add_text(item.text, **item.options)

    @draw.register
    def _(self, item: ArrowLoad):
        self._add_load_arrow(item.start, item.vector, item.color, item.label, self._scale)

    @draw.register
    def _(self, item: MomentLoad):
        self._add_moment_glyph(item.center, item.vector, self._scale, item.label)

    @draw.register
    def _(self, item: SpringLoad):
        self._add_spring_glyph(item.start, item.end, self._scale, item.label)

    @draw.register
    def _(self, item: MarkerLoad):
        self._add_marker(item.location, item.label, item.color, self._scale)

    def _add_load_arrow(
        self,
        start,
        vector,
        color: str,
        label: str,
        scale_len: float,
    ) -> None:
        vector = np.asarray(vector, dtype=float).reshape(3)
        magnitude = float(np.linalg.norm(vector))
        if magnitude <= 1e-12:
            return
        direction = vector / magnitude
        arrow = pv.Arrow(
            start=np.asarray(start, dtype=float),
            direction=direction,
            scale=_load_arrow_length(scale_len),
            tip_length=0.30,
            tip_radius=0.08,
            shaft_radius=0.025,
        )
        self._overlay_actors.append(self.plotter.add_mesh(arrow, color=color))
        if label:
            label_position = np.asarray(start, dtype=float) + direction * _load_arrow_length(scale_len) * 1.15
            self._add_label(label_position, label, color)

    def _add_moment_glyph(
        self, center, moment, scale_len: float, label: str
    ) -> None:
        axis = np.asarray(moment, dtype=float).reshape(3)
        magnitude = float(np.linalg.norm(axis))
        if magnitude <= 1e-12:
            return
        axis /= magnitude
        reference = np.array([1.0, 0.0, 0.0])
        if abs(float(axis @ reference)) > 0.85:
            reference = np.array([0.0, 1.0, 0.0])
        first = np.cross(axis, reference)
        first /= np.linalg.norm(first)
        second = np.cross(axis, first)
        radius = scale_len * 0.075
        angles = np.linspace(0.0, 1.65 * np.pi, 48)
        points = np.asarray(center, dtype=float) + radius * (
            np.cos(angles)[:, None] * first + np.sin(angles)[:, None] * second
        )
        arc = pv.PolyData()
        arc.points = points
        arc.lines = np.r_[len(points), np.arange(len(points), dtype=np.int64)]
        self._overlay_actors.append(
            self.plotter.add_mesh(
                arc.tube(radius=max(scale_len * 0.006, 1e-3)), color="#f1c40f"
            )
        )
        tangent = -np.sin(angles[-1]) * first + np.cos(angles[-1]) * second
        self._add_load_arrow(points[-1], tangent, "#f1c40f", "", scale_len * 0.45)
        self._add_label(np.asarray(center) + radius * 1.35 * first, label, "#f1c40f")

    def _add_spring_glyph(self, start, end, scale_len: float, label: str) -> None:
        start = np.asarray(start, dtype=float).reshape(3)
        end = np.asarray(end, dtype=float).reshape(3)
        axis = end - start
        length = float(np.linalg.norm(axis))
        if length <= 1e-12:
            return
        direction = axis / length
        reference = np.array([0.0, 0.0, 1.0])
        if abs(float(direction @ reference)) > 0.85:
            reference = np.array([0.0, 1.0, 0.0])
        side = np.cross(direction, reference)
        side /= np.linalg.norm(side)
        parameter = np.linspace(0.0, 1.0, 64)
        points = start + parameter[:, None] * axis
        points += np.sin(parameter * 12.0 * np.pi)[:, None] * (scale_len * 0.025) * side
        line = pv.PolyData()
        line.points = points
        line.lines = np.r_[len(points), np.arange(len(points), dtype=np.int64)]
        actor = self.plotter.add_mesh(
            line.tube(radius=max(scale_len * 0.004, 1e-3)), color="#c084fc"
        )
        self._overlay_actors.append(actor)
        self._add_label((start + end) / 2.0, label, "#c084fc")

    def _add_marker(self, location, label: str, color: str, scale_len: float) -> None:
        radius = max(scale_len * 0.012, 1e-3)
        sphere = pv.Sphere(center=np.asarray(location, dtype=float), radius=radius)
        self._overlay_actors.append(self.plotter.add_mesh(sphere, color=color))
        self._add_label(location, label, color)

    def _add_label(self, position, label: str, color: str) -> None:
        if not label:
            return
        actor = self.plotter.add_point_labels(
            np.asarray(position, dtype=float).reshape(1, 3),
            [label],
            font_size=11,
            text_color="#ffffff",
            shape="rounded_rect",
            shape_color=color,
            shape_opacity=0.92,
            show_points=False,
            always_visible=True,
        )
        self._overlay_actors.append(actor)


def _load_arrow_length(characteristic_length: float) -> float:
    return float(characteristic_length) * 0.20
