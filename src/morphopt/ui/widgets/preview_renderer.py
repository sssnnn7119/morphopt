"""Render scene descriptions; owns actors, never reads problem definitions."""

from __future__ import annotations

import os
from collections.abc import Callable
from copy import deepcopy
from functools import singledispatchmethod
from pathlib import Path

import numpy as np
import pyvista as pv
from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkRenderingCore import vtkCellPicker

from ..i18n import localized_message
from ..theme import theme_manager
from ..visualization.scene import (
    ArrowLoad,
    CouplingLoad,
    FaceSelection,
    LabelItem,
    LoadScene,
    MarkerLoad,
    MeshItem,
    MessageItem,
    MomentLoad,
    PreviewScene,
    SpringLoad,
)
from .plot_style import configure_plotter

_SOURCE_CELL_ID = "morphopt_source_cell_id"


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
    def __init__(
        self,
        plotter,
        *,
        on_face_picked: Callable[[FaceSelection | None], None] | None = None,
        track_mouse_events: bool = True,
    ):
        self.plotter = plotter
        configure_plotter(self.plotter)
        self._overlay_actors: list = []
        self._scale = theme_manager.palette.viewer.scene_fallback_diagonal
        self._annotation_scale = theme_manager.palette.viewer.scene_fallback_diagonal
        self._callout_ranges: dict[float, list[tuple[float, float]]] = {}
        self._geometry_bounds: tuple[np.ndarray, np.ndarray] | None = None
        self._on_face_picked = on_face_picked
        self._face_picker = vtkCellPicker()
        self._face_picker.SetTolerance(0.0005)
        self._face_picker.PickFromListOn()
        self._face_items: dict[str, MeshItem] = {}
        self._selection_actor = None
        self._set_actors: list = []
        self._set_opacities: list = []
        self._press_position: tuple[int, int] | None = None
        self._dragged = False
        self._geometry_actors: list = []
        self._section_plane = vtkPlane()
        self._section_enabled = False
        self._section_axis = 0
        self._section_fraction = 0.5
        self._section_reverse = False
        if track_mouse_events and plotter.iren is not None:
            plotter.iren.add_observer("LeftButtonPressEvent", self._face_press)
            plotter.iren.add_observer("MouseMoveEvent", self._face_move)
            plotter.iren.add_observer("LeftButtonReleaseEvent", self._face_release)

    def draw_scene(self, scene: PreviewScene) -> None:
        self.clear_set_selection(render=False)
        self.clear_face_selection(render=False)
        self._face_picker.InitializePickList()
        self._face_items.clear()
        self._geometry_actors.clear()
        self._press_position = None
        self.plotter.clear()
        # clear() removes lights; restore the shared viewport configuration.
        configure_plotter(self.plotter)
        self._overlay_actors.clear()
        self._callout_ranges.clear()
        bounds = scene.bounds
        if bounds is not None:
            bounds = np.asarray(bounds, dtype=float)
            self._geometry_bounds = (
                bounds[::2], bounds[1::2],
            )
            self._annotation_scale = scene.diagonal
        else:
            self._geometry_bounds = None
        for item in scene.items:
            actor = self.draw(item)
            if isinstance(item, MeshItem):
                self._geometry_actors.append(actor)
            if isinstance(item, MeshItem) and item.faces is not None:
                self._face_picker.AddPickList(actor)
                self._face_items[actor.GetAddressAsString("")] = item
        self._apply_section()
        if scene.show_bounding_box and self._geometry_bounds is not None:
            self._draw_bounding_box()
        self._draw_instance_legend(scene.instance_legend)

    def _draw_bounding_box(self) -> None:
        """Draw the full Part bounds outside the picking and clipping pipelines."""
        lower, upper = self._geometry_bounds
        bounds = tuple(value for pair in zip(lower, upper) for value in pair)
        color = theme_manager.palette.viewer.render.annotation_text_color
        self.plotter.add_mesh(
            pv.Box(bounds=bounds).outline(), name="part-bounding-box",
            color=color, line_width=1, pickable=False, lighting=False,
        )
        self.plotter.show_bounds(
            bounds=bounds, color=color, location="outer", ticks="outside",
            n_xlabels=2, n_ylabels=2, n_zlabels=2,
            xtitle="X", ytitle="Y", ztitle="Z", fmt="%.6g",
            font_size=theme_manager.palette.viewer.render.label_font_size,
            use_3d_text=False,
        )

    @property
    def section_position(self) -> float | None:
        if not self._section_enabled or self._geometry_bounds is None:
            return None
        lower, upper = self._geometry_bounds
        axis = self._section_axis
        return float(lower[axis] + self._section_fraction * (upper[axis] - lower[axis]))

    def set_section(
        self,
        enabled: bool,
        axis: int,
        fraction: float,
        reverse: bool = False,
        *,
        render: bool = True,
    ) -> None:
        """Move a mapper clipping plane without rebuilding any CAD geometry."""
        if axis not in (0, 1, 2):
            raise ValueError("Section axis must be 0, 1 or 2.")
        self._section_enabled = enabled
        self._section_axis = axis
        self._section_fraction = float(np.clip(fraction, 0, 1))
        self._section_reverse = reverse
        self.clear_face_selection(render=False)
        self._apply_section()
        if render:
            self.plotter.render()

    def _apply_section(self) -> None:
        position = self.section_position
        if position is not None:
            origin = np.zeros(3)
            origin[self._section_axis] = position
            normal = np.zeros(3)
            normal[self._section_axis] = -1 if self._section_reverse else 1
            self._section_plane.SetOrigin(*origin)
            self._section_plane.SetNormal(*normal)
        for actor in [*self._geometry_actors, *self._set_actors]:
            actor.mapper.RemoveAllClippingPlanes()
            if position is not None:
                actor.mapper.AddClippingPlane(self._section_plane)

    def _face_press(self, *_args) -> None:
        self._press_position = self.plotter.iren.get_event_position()
        self._dragged = False

    def _face_move(self, *_args) -> None:
        if self._press_position is not None:
            position = self.plotter.iren.get_event_position()
            distance = np.linalg.norm(np.subtract(position, self._press_position))
            self._dragged |= (
                distance > theme_manager.palette.viewer.geometry.pick_drag_distance
            )

    def _face_release(self, *_args) -> None:
        if self._press_position is None:
            return
        self._face_move()
        self._press_position = None
        if not self._dragged:
            self.pick_face(*self.plotter.iren.get_event_position())

    def clear_face_selection(self, *, render: bool = True) -> None:
        if self._selection_actor is not None:
            self.plotter.remove_actor(self._selection_actor, render=False)
            self._selection_actor = None
        if self._on_face_picked is not None:
            self._on_face_picked(None)
        if render:
            self.plotter.render()

    def pick_face(self, x: int, y: int) -> FaceSelection | None:
        """Pick base geometry only; load glyphs and highlights cannot intercept it."""
        self.clear_set_selection(render=False)
        self.clear_face_selection(render=False)
        self._face_picker.Pick(x, y, 0, self.plotter.renderer)
        actor = self._face_picker.GetActor()
        cell_id = self._face_picker.GetCellId()
        item = self._face_items.get(actor.GetAddressAsString("")) if actor else None
        # The picker indexes the mapper's displayed dataset. Surface extraction,
        # normal generation and triangulation may change its cell ordering.
        displayed = pv.wrap(self._face_picker.GetDataSet()) if actor else None
        if (
            displayed is not None
            and _SOURCE_CELL_ID in displayed.cell_data
            and cell_id >= 0
        ):
            cell_id = int(displayed.cell_data[_SOURCE_CELL_ID][cell_id])
        if item is None or item.faces is None or not 0 <= cell_id < item.mesh.n_cells:
            self.plotter.render()
            return None
        faces = item.faces
        group_id = int(faces.cell_groups[cell_id])
        selected = item.mesh.extract_cells(faces.cell_groups == group_id)
        self._selection_actor = self.plotter.add_mesh(
            selected,
            name="picked-part-face",
            color=theme_manager.palette.viewer.geometry.picked_face_color,
            opacity=0.55,
            lighting=False,
            pickable=False,
            render=False,
        )
        # Coincident-topology offsets keep the selected shell visible without
        # moving its vertices or changing the geometry used by the picker.
        mapper = self._selection_actor.mapper
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)
        if self.section_position is not None:
            mapper.AddClippingPlane(self._section_plane)
        selection = FaceSelection(
            faces.part_name, faces.instance_name, faces.group_names[group_id]
        )
        if self._on_face_picked is not None:
            self._on_face_picked(selection)
        self.plotter.render()
        return selection

    @property
    def has_set_selection(self) -> bool:
        return bool(self._set_actors)

    def clear_set_selection(self, *, render: bool = True) -> None:
        for actor in self._set_actors:
            self.plotter.remove_actor(actor, render=False)
        self._set_actors.clear()
        for actor, opacity in self._set_opacities:
            actor.prop.opacity = opacity
        self._set_opacities.clear()
        if render:
            self.plotter.render()

    def highlight_set(self, meshes: list[pv.DataSet], *, nodes: bool = False) -> None:
        """Show set faces or actual mesh nodes independently of load overlays."""
        self.clear_set_selection(render=False)
        self.clear_face_selection(render=False)
        meshes = [mesh for mesh in meshes if mesh.n_points]
        if meshes:
            for actor in self._geometry_actors:
                self._set_opacities.append((actor, actor.prop.opacity))
                actor.prop.opacity = min(actor.prop.opacity, 0.18)
        for index, mesh in enumerate(meshes):
            actor = self.plotter.add_mesh(
                mesh, name=f"selected-part-set-{index}",
                color=theme_manager.palette.viewer.geometry.picked_face_color,
                style="points" if nodes else "surface",
                point_size=9, render_points_as_spheres=nodes,
                opacity=1.0, lighting=False, pickable=False, render=False,
                reset_camera=False,
            )
            actor.mapper.SetResolveCoincidentTopologyToPolygonOffset()
            actor.mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-2, -2)
            self._set_actors.append(actor)
        self._apply_section()
        self.plotter.render()

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
        width = min(
            theme_manager.palette.viewer.render.legend_max_width,
            max(
                theme_manager.palette.viewer.render.legend_min_width,
                theme_manager.palette.viewer.render.legend_base_width
                + theme_manager.palette.viewer.render.legend_name_width_ratio
                * max(len(name) for name, _ in entries),
            ),
        )
        height = min(
            theme_manager.palette.viewer.render.legend_max_height,
            theme_manager.palette.viewer.render.legend_row_height * len(labels),
        )
        legend = self.plotter.add_legend(
            labels,
            bcolor=theme_manager.palette.viewer.render.legend_background,
            border=False,
            size=(width, height),
            name="instance-legend",
            loc="upper left",
            font_family=theme_manager.palette.viewer.render.legend_font_family,
            background_opacity=theme_manager.palette.viewer.render.legend_background_opacity,
        )
        legend.SetPadding(theme_manager.palette.viewer.render.legend_padding)
        text = legend.GetEntryTextProperty()
        text.SetColor(*deepcopy(theme_manager.palette.viewer.render.legend_text_color))
        text.SetFontSize(theme_manager.palette.viewer.render.legend_font_size)
        text.SetShadow(False)
        font_file = _cjk_font_file()
        if font_file:
            text.SetFontFamilyAsString("File")
            text.SetFontFile(font_file)

    @singledispatchmethod
    def draw(self, item):
        raise TypeError(
            localized_message(
                "ui.errors.preview_renderer.unsupported_scene_item_value",
                value_0=type(item).__name__,
            )
        )

    @draw.register
    def _(self, item: MeshItem):
        options = {
            "ambient": theme_manager.palette.viewer.render.mesh_ambient,
            "diffuse": theme_manager.palette.viewer.render.mesh_diffuse,
            "specular": theme_manager.palette.viewer.render.mesh_specular,
            "specular_power": theme_manager.palette.viewer.render.mesh_specular_power,
            **item.options,
        }
        preview_offset = float(options.pop("preview_offset", 0.0))
        mesh = self._offset_toward_camera(item.mesh, preview_offset)
        if item.faces is not None:
            mesh = mesh.copy(deep=False)
            mesh.cell_data[_SOURCE_CELL_ID] = np.arange(mesh.n_cells, dtype=np.int64)
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
        self._add_load_arrow(
            item.start, item.vector, item.color, item.label, self._scale
        )

    @draw.register
    def _(self, item: MomentLoad):
        self._add_moment_glyph(item.center, item.vector, self._scale, item.label)

    @draw.register
    def _(self, item: SpringLoad):
        self._add_spring_glyph(item.start, item.end, self._scale, item.label)

    @draw.register
    def _(self, item: MarkerLoad):
        if item.is_reference_point:
            self._add_reference_point(
                item.location, item.label, item.color, self._scale
            )
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
                surface,
                scale_len
                * theme_manager.palette.viewer.render.coupling_normal_offset_ratio,
            )
            self._overlay_actors.append(
                self.plotter.add_mesh(
                    highlighted_surface,
                    color=theme_manager.palette.viewer.render.coupling_surface_color,
                    opacity=theme_manager.palette.viewer.render.coupling_surface_opacity,
                    smooth_shading=True,
                    ambient=theme_manager.palette.viewer.render.mesh_ambient,
                    diffuse=theme_manager.palette.viewer.render.mesh_diffuse,
                    specular=theme_manager.palette.viewer.render.mesh_specular,
                    specular_power=theme_manager.palette.viewer.render.mesh_specular_power,
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
                        boundary.tube(
                            radius=scale_len
                            * theme_manager.palette.viewer.render.coupling_boundary_width_ratio
                        ),
                        color=theme_manager.palette.viewer.render.coupling_edge_color,
                        lighting=False,
                    )
                )
            self._add_label(
                end,
                surface_label,
                theme_manager.palette.viewer.render.coupling_label_color,
                side=theme_manager.palette.viewer.render.coupling_label_side,
            )
            spoke_targets = _spread_surface_points(
                surface.points,
                end,
                count=theme_manager.palette.viewer.render.coupling_spoke_count,
            )
            if len(spoke_targets):
                spoke_points = np.vstack((start, spoke_targets))
                spoke_lines = np.asarray(
                    [
                        value
                        for index in range(1, len(spoke_points))
                        for value in (2, 0, index)
                    ],
                    dtype=np.int64,
                )
                lines = pv.PolyData()
                lines.points = spoke_points
                lines.lines = spoke_lines
                self._overlay_actors.append(
                    self.plotter.add_mesh(
                        lines.tube(
                            radius=scale_len
                            * theme_manager.palette.viewer.render.coupling_spoke_width_ratio
                        ),
                        color=theme_manager.palette.viewer.render.coupling_spoke_color,
                        opacity=theme_manager.palette.viewer.render.coupling_line_opacity,
                        lighting=False,
                    )
                )
        else:
            distance = float(np.linalg.norm(end - start))
            if distance > theme_manager.palette.viewer.loads.glyph_zero_tolerance:
                line = pv.PolyData()
                line.points = np.vstack((start, end))
                line.lines = np.array([2, 0, 1], dtype=np.int64)
                self._overlay_actors.append(
                    self.plotter.add_mesh(
                        line.tube(
                            radius=scale_len
                            * theme_manager.palette.viewer.render.coupling_line_width_ratio
                        ),
                        color=theme_manager.palette.viewer.render.coupling_spoke_color,
                        lighting=False,
                    )
                )
            self._add_label(
                (start + end) / 2.0,
                label,
                theme_manager.palette.viewer.render.coupling_spoke_color,
            )
        if surface is None or not surface.n_points:
            self._add_marker(
                end,
                "",
                theme_manager.palette.viewer.render.marker_color_reference_point,
                scale_len
                * theme_manager.palette.viewer.render.coupling_marker_scale_ratio,
            )

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
        if magnitude <= theme_manager.palette.viewer.loads.glyph_zero_tolerance:
            return
        direction = vector / magnitude
        length = _load_arrow_length(scale_len)
        arrow = pv.Arrow(
            start=np.asarray(start, dtype=float),
            direction=direction,
            scale=length,
            tip_length=theme_manager.palette.viewer.loads.load_arrow_tip_length_ratio,
            tip_radius=theme_manager.palette.viewer.loads.load_arrow_tip_radius_ratio,
            shaft_radius=theme_manager.palette.viewer.loads.load_arrow_shaft_radius_ratio,
        )
        self._overlay_actors.append(
            self.plotter.add_mesh(arrow, color=color, lighting=False)
        )
        if label:
            label_position = (
                np.asarray(start, dtype=float)
                + direction
                * length
                * theme_manager.palette.viewer.render.load_arrow_label_offset_ratio
            )
            self._add_label(label_position, label, color)

    def _add_moment_glyph(self, center, moment, scale_len: float, label: str) -> None:
        axis = np.asarray(moment, dtype=float).reshape(3)
        magnitude = float(np.linalg.norm(axis))
        if magnitude <= theme_manager.palette.viewer.loads.glyph_zero_tolerance:
            return
        axis /= magnitude
        reference = np.array([1.0, 0.0, 0.0])
        if (
            abs(float(axis @ reference))
            > theme_manager.palette.viewer.render.direction_alignment_threshold
        ):
            reference = np.array([0.0, 1.0, 0.0])
        first = np.cross(axis, reference)
        first /= np.linalg.norm(first)
        second = np.cross(axis, first)
        radius = scale_len * theme_manager.palette.viewer.render.moment_radius_ratio
        angles = np.linspace(
            0.0,
            theme_manager.palette.viewer.render.moment_arc_end_radians,
            theme_manager.palette.viewer.render.moment_arc_samples,
        )
        points = np.asarray(center, dtype=float) + radius * (
            np.cos(angles)[:, None] * first + np.sin(angles)[:, None] * second
        )
        arc = pv.PolyData()
        arc.points = points
        arc.lines = np.r_[len(points), np.arange(len(points), dtype=np.int64)]
        self._overlay_actors.append(
            self.plotter.add_mesh(
                arc.tube(
                    radius=scale_len
                    * theme_manager.palette.viewer.render.moment_tube_radius_ratio
                ),
                color=theme_manager.palette.viewer.render.marker_color_moment,
            )
        )
        tangent = -np.sin(angles[-1]) * first + np.cos(angles[-1]) * second
        self._add_load_arrow(
            points[-1],
            tangent,
            theme_manager.palette.viewer.render.marker_color_moment,
            "",
            scale_len * theme_manager.palette.viewer.render.moment_arrow_length_ratio,
        )
        self._add_label(
            np.asarray(center)
            + radius
            * theme_manager.palette.viewer.render.moment_label_offset_ratio
            * first,
            label,
            theme_manager.palette.viewer.render.marker_color_moment,
        )

    def _add_spring_glyph(self, start, end, scale_len: float, label: str) -> None:
        start = np.asarray(start, dtype=float).reshape(3)
        end = np.asarray(end, dtype=float).reshape(3)
        axis = end - start
        length = float(np.linalg.norm(axis))
        if length <= theme_manager.palette.viewer.loads.glyph_zero_tolerance:
            return
        direction = axis / length
        reference = np.array([0.0, 0.0, 1.0])
        if (
            abs(float(direction @ reference))
            > theme_manager.palette.viewer.render.direction_alignment_threshold
        ):
            reference = np.array([0.0, 1.0, 0.0])
        side = np.cross(direction, reference)
        side /= np.linalg.norm(side)
        parameter = np.linspace(
            0.0, 1.0, theme_manager.palette.viewer.render.spring_samples
        )
        points = start + parameter[:, None] * axis
        points += (
            np.sin(
                parameter
                * theme_manager.palette.viewer.render.spring_wave_cycles
                * np.pi
            )[:, None]
            * min(
                scale_len
                * theme_manager.palette.viewer.render.spring_wave_amplitude_ratio,
                length * theme_manager.palette.viewer.render.spring_wave_length_ratio,
            )
            * side
        )
        line = pv.PolyData()
        line.points = points
        line.lines = np.r_[len(points), np.arange(len(points), dtype=np.int64)]
        actor = self.plotter.add_mesh(
            line.tube(
                radius=min(
                    scale_len * theme_manager.palette.viewer.render.spring_width_ratio,
                    length
                    * theme_manager.palette.viewer.render.spring_width_length_ratio,
                )
            ),
            color=theme_manager.palette.viewer.render.marker_color_spring,
        )
        self._overlay_actors.append(actor)
        self._add_label(
            (start + end) / 2.0,
            label,
            theme_manager.palette.viewer.render.marker_color_spring,
        )

    def _add_marker(self, location, label: str, color: str, scale_len: float) -> None:
        radius = scale_len * theme_manager.palette.viewer.render.marker_radius_ratio
        sphere = pv.Sphere(center=np.asarray(location, dtype=float), radius=radius)
        self._overlay_actors.append(self.plotter.add_mesh(sphere, color=color))
        self._add_label(location, label, color)

    def _add_reference_point(
        self, location, label: str, color: str, scale_len: float
    ) -> None:
        location = np.asarray(location, dtype=float).reshape(3)
        radius = (
            scale_len * theme_manager.palette.viewer.render.reference_point_radius_ratio
        )
        sphere = pv.Sphere(
            center=location,
            radius=radius,
            theta_resolution=theme_manager.palette.viewer.render.reference_point_theta_resolution,
            phi_resolution=theme_manager.palette.viewer.render.reference_point_phi_resolution,
        )
        self._overlay_actors.append(
            self.plotter.add_mesh(
                sphere,
                color=color,
                smooth_shading=True,
                specular=theme_manager.palette.viewer.render.reference_point_specular,
            )
        )
        half_axis = (
            scale_len
            * theme_manager.palette.viewer.render.reference_point_axis_length_ratio
        )
        for axis in np.eye(3):
            line = pv.Line(location - half_axis * axis, location + half_axis * axis)
            self._overlay_actors.append(
                self.plotter.add_mesh(
                    line.tube(
                        radius=scale_len
                        * theme_manager.palette.viewer.render.reference_point_axis_width_ratio
                    ),
                    color=theme_manager.palette.viewer.render.marker_color_reference_axis,
                    lighting=False,
                )
            )
        self._add_label(
            location,
            label,
            color,
            side=theme_manager.palette.viewer.render.reference_point_label_side,
        )

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
                leader.tube(
                    radius=self._scale
                    * theme_manager.palette.viewer.render.annotation_leader_width_ratio
                ),
                color=color,
                opacity=theme_manager.palette.viewer.render.annotation_leader_opacity,
                lighting=False,
            )
        )
        actor = self.plotter.add_point_labels(
            label_position.reshape(1, 3),
            [label],
            font_size=theme_manager.palette.viewer.render.label_font_size,
            text_color=theme_manager.palette.viewer.render.annotation_text_color,
            font_family="courier",
            bold=False,
            shape="rounded_rect",
            shape_color=theme_manager.palette.viewer.render.annotation_background_color,
            shape_opacity=theme_manager.palette.viewer.render.annotation_background_opacity,
            margin=theme_manager.palette.viewer.render.annotation_margin,
            show_points=False,
            always_visible=True,
            font_file=_cjk_font_file(),
        )
        self._overlay_actors.append(actor)

    def _callout_position(
        self, anchor: np.ndarray, label: str, side_override: float | None = None
    ) -> np.ndarray:
        camera_position, focal_point, view_up = (
            np.asarray(value, dtype=float) for value in self.plotter.camera_position
        )
        forward = focal_point - camera_position
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, view_up)
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        up /= np.linalg.norm(up)

        anchor_projection = float(np.dot(anchor, right))
        if self._geometry_bounds is None:
            side = side_override or (
                -1.0 if np.dot(anchor - focal_point, right) > 0.0 else 1.0
            )
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
                sum(
                    1.0
                    if char.isascii()
                    else theme_manager.palette.viewer.render.non_ascii_character_width_ratio
                    for char in line
                )
                for line in label.splitlines()
            ),
            default=1.0,
        )
        half_card_width = self._annotation_scale * min(
            theme_manager.palette.viewer.render.callout_max_width_ratio,
            theme_manager.palette.viewer.render.callout_min_width_ratio
            + text_width * theme_manager.palette.viewer.render.callout_text_width_ratio,
        )
        horizontal_offset = (
            edge_distance
            + half_card_width
            + self._annotation_scale
            * theme_manager.palette.viewer.render.callout_gap_ratio
        )
        camera = self.plotter.camera
        if camera.GetParallelProjection():
            view_height = 2.0 * camera.GetParallelScale()
        else:
            depth = abs(float(np.dot(anchor - camera_position, forward)))
            view_height = 2.0 * depth * np.tan(np.deg2rad(camera.GetViewAngle()) / 2.0)
        world_per_pixel = view_height / self.plotter.window_size[1]
        half_height = (
            (
                len(label.splitlines())
                * theme_manager.palette.viewer.render.callout_line_height_px
                + theme_manager.palette.viewer.render.callout_vertical_padding_px
            )
            * world_per_pixel
            / 2.0
        )
        gap = theme_manager.palette.viewer.render.callout_gap_px * world_per_pixel
        vertical = float(np.dot(anchor, up))
        occupied = self._callout_ranges.setdefault(side, [])
        candidates = [vertical]
        for center, height in occupied:
            candidates.extend(
                (
                    center - height - half_height - gap,
                    center + height + half_height + gap,
                )
            )
        center = next(
            value
            for value in sorted(candidates, key=lambda value: abs(value - vertical))
            if all(
                abs(value - other)
                >= half_height
                + height
                + gap
                - theme_manager.palette.viewer.render.callout_min_separation_tolerance
                for other, height in occupied
            )
        )
        occupied.append((center, half_height))
        return anchor + right * side * horizontal_offset + up * (center - vertical)

    def _offset_toward_camera(self, mesh: pv.DataSet, distance: float) -> pv.DataSet:
        if distance <= 0.0:
            return mesh
        camera_position, focal_point, _view_up = (
            np.asarray(value, dtype=float) for value in self.plotter.camera_position
        )
        direction = camera_position - focal_point
        norm = float(np.linalg.norm(direction))
        if norm <= theme_manager.palette.viewer.loads.glyph_zero_tolerance:
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
    return (
        float(characteristic_length)
        * theme_manager.palette.viewer.loads.load_arrow_length_ratio
    )
