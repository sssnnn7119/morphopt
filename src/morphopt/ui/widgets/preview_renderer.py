"""Render scene descriptions; owns actors, never reads problem definitions."""
from __future__ import annotations

from functools import singledispatchmethod
import os
from pathlib import Path

import numpy as np
import pyvista as pv
from .plot_style import configure_plotter
from ..i18n import localized_message
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
    CouplingLoad,
)


def _cjk_font_file() -> str | None:
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = (
        Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        windows / "msyh.ttc",
    )
    return next((str(path) for path in candidates if path.is_file()), None)


class PreviewRenderer:
    def __init__(self, plotter):
        self.plotter = plotter
        configure_plotter(self.plotter)
        self._overlay_actors: list = []
        self._scale = 10.0
        self._annotation_scale = 10.0
        self._callout_ranges: dict[float, list[tuple[float, float]]] = {}
        self._geometry_bounds: tuple[np.ndarray, np.ndarray] | None = None

    def draw_scene(self, scene: PreviewScene) -> None:
        self.plotter.clear()
        # clear() removes lights; restore the shared viewport configuration.
        configure_plotter(self.plotter)
        self._overlay_actors.clear()
        self._callout_ranges.clear()
        bounds = [mesh.bounds for _, mesh, _item in scene.base_meshes if mesh.n_points]
        if bounds:
            bounds = np.asarray(bounds, dtype=float)
            self._geometry_bounds = (
                np.array([bounds[:, 0].min(), bounds[:, 2].min(), bounds[:, 4].min()]),
                np.array([bounds[:, 1].max(), bounds[:, 3].max(), bounds[:, 5].max()]),
            )
            self._annotation_scale = scene.diagonal
        else:
            self._geometry_bounds = None
        for item in scene.items:
            self.draw(item)
        self._draw_instance_legend(scene.instance_legend)

    def draw_loads(self, scene: LoadScene | None) -> None:
        for actor in self._overlay_actors:
            self.plotter.remove_actor(actor, render=False)
        self._overlay_actors.clear()
        self._callout_ranges.clear()
        if scene is not None:
            self._scale = scene.scale
            self._annotation_scale = scene.annotation_scale or scene.scale
            for item in scene.items:
                actor = self.draw(item)
                if actor is not None:
                    self._overlay_actors.append(actor)
        self.plotter.render()

    def _draw_instance_legend(self, entries: list[tuple[str, str]]) -> None:
        if not entries:
            return
        labels = [[name, color, "rectangle"] for name, color in entries]
        width = min(0.28, max(0.13, 0.055 + 0.008 * max(len(name) for name, _ in entries)))
        height = min(0.4, 0.025 * len(labels))
        legend = self.plotter.add_legend(
            labels,
            bcolor="#1a202a",
            border=False,
            size=(width, height),
            name="instance-legend",
            loc="upper left",
            font_family="arial",
            background_opacity=0.80,
        )
        legend.SetPadding(4)
        text = legend.GetEntryTextProperty()
        text.SetColor(0.86, 0.90, 0.95)
        text.SetFontSize(10)
        text.SetShadow(False)
        font_file = _cjk_font_file()
        if font_file:
            text.SetFontFamilyAsString("File")
            text.SetFontFile(font_file)

    @singledispatchmethod
    def draw(self, item):
        raise TypeError(localized_message("ui.errors.preview_renderer.unsupported_scene_item_value", value_0=type(item).__name__))

    @draw.register
    def _(self, item: MeshItem):
        options = {
            "ambient": 0.17,
            "diffuse": 0.78,
            "specular": 0.24,
            "specular_power": 30,
            **item.options,
        }
        preview_offset = float(options.pop("preview_offset", 0.0))
        mesh = self._offset_toward_camera(item.mesh, preview_offset)
        return self.plotter.add_mesh(mesh, **options)

    @draw.register
    def _(self, item: LabelItem):
        options = {"font_file": _cjk_font_file(), **item.options}
        return self.plotter.add_point_labels(item.points, item.labels, **options)

    @draw.register
    def _(self, item: MessageItem):
        options = {"font_file": _cjk_font_file(), **item.options}
        return self.plotter.add_text(item.text, **options)

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
        if item.is_reference_point:
            self._add_reference_point(item.location, item.label, item.color, self._scale)
        else:
            self._add_marker(item.location, item.label, item.color, self._scale)

    @draw.register
    def _(self, item: CouplingLoad):
        self._add_coupling_glyph(
            item.reference_point,
            item.node_set_center,
            self._scale,
            item.label,
            item.surface,
            item.surface_label,
        )

    def _add_coupling_glyph(
        self,
        reference_point,
        node_set_center,
        scale_len: float,
        label: str,
        surface: pv.DataSet | None,
        surface_label: str,
    ) -> None:
        start = np.asarray(reference_point, dtype=float).reshape(3)
        end = np.asarray(node_set_center, dtype=float).reshape(3)
        if surface is not None and surface.n_points:
            surface = (
                surface
                if isinstance(surface, pv.PolyData)
                else surface.extract_surface(algorithm="dataset_surface")
            )
            highlighted_surface = self._offset_toward_camera(
                surface, scale_len * 0.0015
            )
            self._overlay_actors.append(
                self.plotter.add_mesh(
                    highlighted_surface,
                    color="#dcae67",
                    opacity=0.46,
                    smooth_shading=True,
                    ambient=0.18,
                    diffuse=0.78,
                    specular=0.24,
                    specular_power=30,
                    show_edges=False,
                )
            )
            boundary = surface.extract_feature_edges(
                boundary_edges=True,
                feature_edges=False,
                manifold_edges=False,
                non_manifold_edges=False,
            )
            if boundary.n_points:
                self._overlay_actors.append(
                    self.plotter.add_mesh(
                        boundary.tube(radius=scale_len * 0.0015),
                        color="#edc27e",
                        lighting=False,
                    )
                )
            self._add_label(end, surface_label, "#edc27e", side=1.0)
            spoke_targets = _spread_surface_points(surface.points, end, count=8)
            if len(spoke_targets):
                spoke_points = np.vstack((start, spoke_targets))
                spoke_lines = np.asarray(
                    [value for index in range(1, len(spoke_points)) for value in (2, 0, index)],
                    dtype=np.int64,
                )
                lines = pv.PolyData()
                lines.points = spoke_points
                lines.lines = spoke_lines
                self._overlay_actors.append(
                    self.plotter.add_mesh(
                        lines.tube(radius=scale_len * 0.0011),
                        color="#dfad62",
                        opacity=0.82,
                        lighting=False,
                    )
                )
        else:
            distance = float(np.linalg.norm(end - start))
            if distance > 1e-12:
                line = pv.PolyData()
                line.points = np.vstack((start, end))
                line.lines = np.array([2, 0, 1], dtype=np.int64)
                self._overlay_actors.append(
                    self.plotter.add_mesh(
                        line.tube(radius=scale_len * 0.0015),
                        color="#dfad62",
                        lighting=False,
                    )
                )
            self._add_label((start + end) / 2.0, label, "#dfad62")
        if surface is None or not surface.n_points:
            self._add_marker(end, "", "#dfad62", scale_len * 0.65)

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
        length = _load_arrow_length(scale_len)
        arrow = pv.Arrow(
            start=np.asarray(start, dtype=float),
            direction=direction,
            scale=length,
            tip_length=0.25,
            tip_radius=0.055,
            shaft_radius=0.015,
        )
        self._overlay_actors.append(self.plotter.add_mesh(arrow, color=color, lighting=False))
        if label:
            label_position = np.asarray(start, dtype=float) + direction * length * 1.15
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
        radius = scale_len * 0.045
        angles = np.linspace(0.0, 1.65 * np.pi, 48)
        points = np.asarray(center, dtype=float) + radius * (
            np.cos(angles)[:, None] * first + np.sin(angles)[:, None] * second
        )
        arc = pv.PolyData()
        arc.points = points
        arc.lines = np.r_[len(points), np.arange(len(points), dtype=np.int64)]
        self._overlay_actors.append(
            self.plotter.add_mesh(
                arc.tube(radius=scale_len * 0.0025), color="#f1c40f"
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
        points += np.sin(parameter * 12.0 * np.pi)[:, None] * min(scale_len * 0.015, length * 0.04) * side
        line = pv.PolyData()
        line.points = points
        line.lines = np.r_[len(points), np.arange(len(points), dtype=np.int64)]
        actor = self.plotter.add_mesh(
            line.tube(radius=min(scale_len * 0.0025, length * 0.01)), color="#c084fc"
        )
        self._overlay_actors.append(actor)
        self._add_label((start + end) / 2.0, label, "#c084fc")

    def _add_marker(self, location, label: str, color: str, scale_len: float) -> None:
        radius = scale_len * 0.008
        sphere = pv.Sphere(center=np.asarray(location, dtype=float), radius=radius)
        self._overlay_actors.append(self.plotter.add_mesh(sphere, color=color))
        self._add_label(location, label, color)

    def _add_reference_point(
        self, location, label: str, color: str, scale_len: float
    ) -> None:
        location = np.asarray(location, dtype=float).reshape(3)
        radius = scale_len * 0.010
        sphere = pv.Sphere(
            center=location,
            radius=radius,
            theta_resolution=20,
            phi_resolution=16,
        )
        self._overlay_actors.append(
            self.plotter.add_mesh(
                sphere,
                color=color,
                smooth_shading=True,
                specular=0.55,
            )
        )
        half_axis = scale_len * 0.018
        for axis in np.eye(3):
            line = pv.Line(location - half_axis * axis, location + half_axis * axis)
            self._overlay_actors.append(
                self.plotter.add_mesh(
                    line.tube(radius=scale_len * 0.0012),
                    color="#fff0c2",
                    lighting=False,
                )
            )
        self._add_label(location, label, color, side=-1.0)

    def _add_label(
        self, position, label: str, color: str, *, side: float | None = None
    ) -> None:
        if not label:
            return
        anchor = np.asarray(position, dtype=float).reshape(3)
        label_position = self._callout_position(anchor, label, side)
        leader = pv.Line(anchor, label_position)
        self._overlay_actors.append(
            self.plotter.add_mesh(
                leader.tube(radius=self._scale * 0.001),
                color=color,
                opacity=0.68,
                lighting=False,
            )
        )
        actor = self.plotter.add_point_labels(
            label_position.reshape(1, 3),
            [label],
            font_size=10,
            text_color="#dce4ee",
            font_family="courier",
            bold=False,
            shape="rounded_rect",
            shape_color="#202833",
            shape_opacity=0.97,
            margin=6,
            show_points=False,
            always_visible=True,
            font_file=_cjk_font_file(),
        )
        self._overlay_actors.append(actor)

    def _callout_position(
        self, anchor: np.ndarray, label: str, side_override: float | None = None
    ) -> np.ndarray:
        camera_position, focal_point, view_up = (
            np.asarray(value, dtype=float)
            for value in self.plotter.camera_position
        )
        forward = focal_point - camera_position
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, view_up)
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        up /= np.linalg.norm(up)

        anchor_projection = float(np.dot(anchor, right))
        if self._geometry_bounds is None:
            side = side_override or (-1.0 if np.dot(anchor - focal_point, right) > 0.0 else 1.0)
            edge_distance = 0.0
        else:
            lower, upper = self._geometry_bounds
            corners = np.array(
                [
                    [x, y, z]
                    for x in (lower[0], upper[0])
                    for y in (lower[1], upper[1])
                    for z in (lower[2], upper[2])
                ]
            )
            projected_bounds = corners @ right
            distance_to_left = anchor_projection - projected_bounds.min()
            distance_to_right = projected_bounds.max() - anchor_projection
            if side_override is not None:
                side = side_override
                edge_distance = distance_to_left if side < 0 else distance_to_right
            elif distance_to_left <= distance_to_right:
                side = -1.0
                edge_distance = max(0.0, distance_to_left)
            else:
                side = 1.0
                edge_distance = max(0.0, distance_to_right)

        text_width = max(
            (
                sum(1.0 if char.isascii() else 1.65 for char in line)
                for line in label.splitlines()
            ),
            default=1.0,
        )
        half_card_width = self._annotation_scale * min(
            0.25, 0.11 + text_width * 0.0018
        )
        horizontal_offset = edge_distance + half_card_width + self._annotation_scale * 0.035
        camera = self.plotter.camera
        if camera.GetParallelProjection():
            view_height = 2.0 * camera.GetParallelScale()
        else:
            depth = abs(float(np.dot(anchor - camera_position, forward)))
            view_height = 2.0 * depth * np.tan(np.deg2rad(camera.GetViewAngle()) / 2.0)
        world_per_pixel = view_height / self.plotter.window_size[1]
        half_height = (len(label.splitlines()) * 14.0 + 12.0) * world_per_pixel / 2.0
        gap = 8.0 * world_per_pixel
        vertical = float(np.dot(anchor, up))
        occupied = self._callout_ranges.setdefault(side, [])
        candidates = [vertical]
        for center, height in occupied:
            candidates.extend((center - height - half_height - gap, center + height + half_height + gap))
        center = next(
            value for value in sorted(candidates, key=lambda value: abs(value - vertical))
            if all(abs(value - other) >= half_height + height + gap - 1e-12 for other, height in occupied)
        )
        occupied.append((center, half_height))
        return (
            anchor + right * side * horizontal_offset
            + up * (center - vertical)
        )

    def _offset_toward_camera(self, mesh: pv.DataSet, distance: float) -> pv.DataSet:
        if distance <= 0.0:
            return mesh
        camera_position, focal_point, _view_up = (
            np.asarray(value, dtype=float) for value in self.plotter.camera_position
        )
        direction = camera_position - focal_point
        norm = float(np.linalg.norm(direction))
        if norm <= 1e-12:
            return mesh
        offset_mesh = mesh.copy()
        offset_mesh.translate(direction * (distance / norm), inplace=True)
        return offset_mesh


def _spread_surface_points(
    points: np.ndarray, center: np.ndarray, *, count: int
) -> np.ndarray:
    """Choose well-spaced deterministic endpoints for coupling spokes."""
    candidates = np.unique(np.asarray(points, dtype=float).reshape(-1, 3), axis=0)
    if not len(candidates):
        return np.empty((0, 3), dtype=float)
    if len(candidates) <= count:
        return candidates

    selected = [int(np.argmax(np.linalg.norm(candidates - center, axis=1)))]
    min_distance_squared = np.sum((candidates - candidates[selected[0]]) ** 2, axis=1)
    while len(selected) < count:
        next_index = int(np.argmax(min_distance_squared))
        selected.append(next_index)
        distance_squared = np.sum((candidates - candidates[next_index]) ** 2, axis=1)
        min_distance_squared = np.minimum(min_distance_squared, distance_squared)
    return candidates[selected]


def _load_arrow_length(characteristic_length: float) -> float:
    return float(characteristic_length) * 0.04
