"""Per-Part preview visitors and cached model queries. No Qt or VTK actors."""
from __future__ import annotations
from copy import deepcopy

import os
from colorsys import hsv_to_rgb
from typing import Any, Callable

import numpy as np
import pyvista as pv
import torchfea

from ...constants import CONSTANT
from ...optcore.modelparams.parts import (
    BoxPart,
    INPPart,
    load_model_assembly,
    resolve_model_path,
)
from ..i18n import localized_message
from ..application.cad import cad_brep_records_from_node
from ..application.expressions import DefinitionValues
from ..model.problem import (
    FEAComponentNode,
    InstanceNode,
    PartNode,
    ProblemDefinition,
    SurfaceNode,
    resolve_model_directory,
)
from .scene import PreviewScene


_INSTANCE_COLORS = tuple(deepcopy(CONSTANT.UI.VIEWER.GEOMETRY.INSTANCE_COLORS))
_UNINSTANCED_COLOR = CONSTANT.UI.VIEWER.GEOMETRY.BASE_UNINSTANCED_COLOR


def apply_instance_pose(
    mesh: pv.DataSet,
    instance: InstanceNode,
    values: DefinitionValues | None = None,
) -> pv.DataSet:
    transformed = mesh.copy()
    rotation = np.asarray(values.resolve(instance.rotation) if values else instance.rotation, dtype=float)
    angle = float(np.linalg.norm(rotation))
    if angle > CONSTANT.UI.VIEWER.GEOMETRY.ROTATION_ZERO_TOLERANCE:
        transformed.rotate_vector(rotation / angle, np.degrees(angle), point=(0, 0, 0), inplace=True)
    transformed.translate(
        np.asarray(values.resolve(instance.translation) if values else instance.translation, dtype=float),
        inplace=True,
    )
    return transformed


class PartPreviewAdapter:
    """Extension point for geometry, surface selections and node-set queries."""
    def preview(
        self,
        context: PreviewGeometry,
        part: PartNode,
        instance: InstanceNode | None,
    ) -> None:
        raise NotImplementedError

    def surface(
        self,
        context: PreviewGeometry,
        part: PartNode,
        name: str,
    ) -> pv.DataSet | None:
        return None

    def model_part(self, context: PreviewGeometry, part: PartNode) -> torchfea.Part | None:
        return None


class PartPreviewVisitor:
    def __init__(self) -> None:
        self._adapters: dict[str, PartPreviewAdapter] = {}

    def register(self, interface_type: str, adapter: PartPreviewAdapter) -> None:
        self._adapters[interface_type] = adapter

    def adapter(self, part: PartNode) -> PartPreviewAdapter:
        try:
            return self._adapters[part.interface_type]
        except KeyError:
            raise NotImplementedError(localized_message("ui.errors.geometry.no_preview_adapter_registered_for_value", value_0=part.interface_type)) from None

    def visit(
        self,
        context: PreviewGeometry,
        part: PartNode,
        instance: InstanceNode | None,
    ) -> None:
        self.adapter(part).preview(context, part, instance)


class BoundaryPreviewAdapter(PartPreviewAdapter):
    def preview(
        self,
        context: PreviewGeometry,
        part: PartNode,
        instance: InstanceNode | None,
    ) -> None:
        surfaces = part.surfaces()
        for index, surface in enumerate(surfaces):
            mesh = context.surface_mesh(surface)
            if mesh is None:
                continue
            if instance is not None:
                mesh = apply_instance_pose(mesh, instance, context.values)
            name = instance.name if instance is not None else part.name
            options = dict(
                color=(
                    context.instance_color(instance.name)
                    if instance is not None
                    else _UNINSTANCED_COLOR
                ),
                # Both sides of the exterior shell cover the cavity. Keep
                # their combined opacity low enough to see internal loads.
                opacity=(
                    CONSTANT.UI.VIEWER.BOUNDARY_SHELL_OPACITY
                    if len(surfaces) > 1 and index == 0
                    else 1.0
                ),
                show_edges=instance is None,
                smooth_shading=True,
            )
            context.scene.add_base(name, mesh, name=f"boundary:{name}:surface-{index}", **options)

    def surface(
        self,
        context: PreviewGeometry,
        part: PartNode,
        name: str,
    ) -> pv.DataSet | None:
        index = _surface_index_from_name(name)
        surfaces = part.surfaces()
        if not 0 <= index < len(surfaces):
            return None
        mesh = context.surface_mesh(surfaces[index])
        if mesh is None:
            return None
        end = name.rsplit("_", 1)[-1]
        if end in {"Head", "Bottom"}:
            return _boundary_end_surface(mesh, end)
        return mesh


class BoxPreviewAdapter(PartPreviewAdapter):
    @staticmethod
    def mesh(length: float, height: float, depth: float) -> pv.PolyData:
        """Build the six-face preview shell without generating an FE mesh."""
        return pv.Box(bounds=[0.0, length, 0.0, height, 0.0, depth])

    def preview(
        self,
        context: PreviewGeometry,
        part: PartNode,
        instance: InstanceNode | None,
    ) -> None:
        box = context.box_interface(part)
        mesh = self.mesh(box.length, box.height, box.depth)
        name = instance.name if instance is not None else part.name
        if instance is not None:
            mesh = apply_instance_pose(mesh, instance, context.values)
        context.scene.add_base(
            name,
            mesh,
            name=f"box:{name}",
            color=context.instance_color(instance.name) if instance else _UNINSTANCED_COLOR,
            opacity=1.0,
            show_edges=instance is None,
        )

    def model_part(self, context: PreviewGeometry, part: PartNode) -> torchfea.Part:
        return context.cached_part(part, lambda: context.box_interface(part).get_part())

    def surface(
        self,
        context: PreviewGeometry,
        part: PartNode,
        name: str,
    ) -> pv.DataSet | None:
        node_faces = {f"nodes_{axis}{side}": f"surface_{axis}{side}" for axis in "xyz" for side in ("min", "max")}
        name = node_faces.get(name, name)
        if name in {"", "extern", part.exterior_surface or "extern"}:
            box = context.box_interface(part)
            return self.mesh(box.length, box.height, box.depth)
        return self.model_part(context, part).get_mesh(surf_name=name)


class INPPreviewAdapter(PartPreviewAdapter):
    def model_part(self, context: PreviewGeometry, part: PartNode) -> torchfea.Part:
        return context.cached_part(
            part,
            lambda: INPPart(
                mesh_file=part.mesh_file,
                part_name=part.resolved_part_name(),
                inp_part_name=part.inp_part_name or None,
                exterior_surface=part.exterior_surface or None,
            ).get_part(),
        )

    def surface(
        self,
        context: PreviewGeometry,
        part: PartNode,
        name: str,
    ) -> pv.DataSet | None:
        return self.model_part(context, part).get_mesh(surf_name=name or None)

    def preview(
        self,
        context: PreviewGeometry,
        part: PartNode,
        instance: InstanceNode | None,
    ) -> None:
        mesh = self.surface(context, part, part.exterior_surface or "")
        if mesh is not None:
            name = instance.name if instance is not None else part.name
            if instance is not None:
                mesh = apply_instance_pose(mesh, instance, context.values)
            context.scene.add_base(
                name,
                mesh,
                name=f"inp:{name}",
                color=context.instance_color(instance.name) if instance else _UNINSTANCED_COLOR,
                opacity=1.0,
                show_edges=instance is None,
                smooth_shading=True,
            )


class CADPreviewAdapter(PartPreviewAdapter):
    def preview(
        self,
        context: PreviewGeometry,
        part: PartNode,
        instance: InstanceNode | None,
    ) -> None:
        records = context.cad_records(part)
        scene = context.scene
        instance_name = (
            instance.name
            if instance is not None
            else part.name or "part"
        )
        face_centers = []
        face_labels = []
        seen_edges: set[int] = set()

        for face_index, record in enumerate(records):
            points = np.asarray(record["points"], dtype=float).reshape(-1, 3)
            triangles = np.asarray(record["triangles"], dtype=np.int64).reshape(-1, 3)
            if not len(points) or not len(triangles):
                raise ValueError(
                    localized_message("ui.errors.geometry.cad_face_value_has_no_display_triangles", value_0=face_index)
                )
            face_point_ids = np.unique(triangles)
            face_points = points[face_point_ids]
            face_triangles = np.searchsorted(face_point_ids, triangles)
            faces = np.column_stack(
                (
                    np.full(len(face_triangles), 3, dtype=np.int64),
                    face_triangles,
                )
            ).ravel()
            face = pv.PolyData(face_points, faces)
            context._local_cad_faces[(id(part), f"face_{face_index}")] = face
            if instance is not None:
                face = apply_instance_pose(face, instance, context.values)
            context._cad_face_meshes[(instance_name, f"face_{face_index}")] = face
            scene.add_base(
                instance_name,
                face,
                name=f"cad-face:{instance_name}:{face_index}",
                color=context.instance_color(instance.name) if instance else _UNINSTANCED_COLOR,
                opacity=1.0,
                show_edges=False,
                smooth_shading=True,
                ambient=CONSTANT.UI.VIEWER.GEOMETRY.CAD_FACE_AMBIENT,
                diffuse=CONSTANT.UI.VIEWER.GEOMETRY.CAD_FACE_DIFFUSE,
                specular=CONSTANT.UI.VIEWER.GEOMETRY.CAD_FACE_SPECULAR,
                specular_power=CONSTANT.UI.VIEWER.GEOMETRY.CAD_FACE_SPECULAR_POWER,
            )
            centers = face.cell_centers().points
            if len(centers):
                face_centers.append(centers.mean(axis=0))
                face_labels.append(str(face_index))

            for edge in record.get("edge_lines", []):
                edge_tag = int(edge.get("edge_tag", -1))
                lines = np.asarray(edge.get("lines", []), dtype=np.int64).reshape(-1, 2)
                if edge_tag < 0 or edge_tag in seen_edges or not len(lines):
                    continue
                seen_edges.add(edge_tag)
                edge_point_ids = np.unique(lines)
                edge_points = points[edge_point_ids]
                edge_lines = np.searchsorted(edge_point_ids, lines)
                edge_cells = np.column_stack(
                    (np.full(len(edge_lines), 2, dtype=np.int64), edge_lines)
                ).ravel()
                edge_mesh = pv.PolyData()
                edge_mesh.points = edge_points
                edge_mesh.lines = edge_cells
                if instance is not None:
                    edge_mesh = apply_instance_pose(edge_mesh, instance, context.values)
                scene.add_mesh(
                    edge_mesh,
                    name=f"cad-edge:{instance_name}:{edge_tag}",
                    color=CONSTANT.UI.VIEWER.GEOMETRY.CAD_EDGE_COLOR,
                    line_width=CONSTANT.UI.VIEWER.GEOMETRY.CAD_EDGE_WIDTH,
                    render_lines_as_tubes=True,
                    lighting=False,
                )

        if face_centers:
            scene.add_point_labels(
                np.asarray(face_centers),
                face_labels,
                font_size=CONSTANT.UI.VIEWER.GEOMETRY.CAD_LABEL_FONT_SIZE,
                text_color="#ffffff",
                shape="rounded_rect",
                shape_color=CONSTANT.UI.VIEWER.GEOMETRY.CAD_LABEL_SHAPE_COLOR,
                shape_opacity=CONSTANT.UI.VIEWER.GEOMETRY.CAD_LABEL_SHAPE_OPACITY,
                show_points=False,
                always_visible=True,
                name=f"cad-face-labels:{instance_name}",
            )

    def surface(
        self,
        context: PreviewGeometry,
        part: PartNode,
        name: str,
    ) -> pv.DataSet | None:
        face_name = _cad_face_name(name)
        if face_name is None:
            return None
        # Faces are already built in local coordinates before Instance placement.
        return context._local_cad_faces.get((id(part), face_name))


class TorchFEAPreviewAdapter(PartPreviewAdapter):
    def model_part(self, context: PreviewGeometry, part: PartNode) -> torchfea.Part:
        linked = context.problem.imported_model_part_node()
        if linked is None:
            raise ValueError(localized_message("ui.errors.geometry.no_linked_torchfea_model"))
        assembly = context._ensure_torchfea_model(linked)
        return assembly.get_part(part.resolved_part_name())

    def surface(
        self,
        context: PreviewGeometry,
        part: PartNode,
        name: str,
    ) -> pv.DataSet | None:
        return self.model_part(context, part).get_mesh(surf_name=name or None)

    def preview(
        self,
        context: PreviewGeometry,
        part: PartNode,
        instance: InstanceNode | None,
    ) -> None:
        mesh = self.surface(context, part, part.exterior_surface or "")
        if mesh is not None:
            name = instance.name if instance is not None else part.name
            if instance is not None:
                mesh = apply_instance_pose(mesh, instance, context.values)
            context.scene.add_base(
                name,
                mesh,
                name=f"torchfea:{name}",
                color=context.instance_color(instance.name) if instance else _UNINSTANCED_COLOR,
                opacity=1.0,
                show_edges=instance is None,
                smooth_shading=True,
            )


def default_part_visitor() -> PartPreviewVisitor:
    visitor = PartPreviewVisitor()
    for kind, adapter in {
        "BoundaryPart": BoundaryPreviewAdapter(),
        "OffsetBoundaryPart": BoundaryPreviewAdapter(),
        "BoxPart": BoxPreviewAdapter(),
        "CADPart": CADPreviewAdapter(),
        "INPPart": INPPreviewAdapter(),
        "TorchFEAPart": TorchFEAPreviewAdapter(),
    }.items():
        visitor.register(kind, adapter)
    return visitor


class SurfacePreviewVisitor:
    def __init__(self) -> None:
        self._builders: dict[str, Callable[[SurfaceNode, DefinitionValues], pv.DataSet | None]] = {}
        self.register("bsp_cylinder", self.cylinder)
        self.register("cpgeo_cylinder", self.cylinder)
        self.register("cpgeo_sphere", self.sphere)
        self.register("fixed_stl", self.stl)

    def register(
        self,
        surface_type: str,
        builder: Callable[[SurfaceNode, DefinitionValues], pv.DataSet | None],
    ) -> None:
        self._builders[surface_type] = builder

    def visit(self, surface: SurfaceNode, values: DefinitionValues) -> pv.DataSet | None:
        builder = self._builders.get(surface.surface_type)
        return builder(surface, values) if builder else None

    @staticmethod
    def cylinder(surface: SurfaceNode, values: DefinitionValues) -> pv.PolyData:
        location = np.asarray(values.resolve(surface.init_location or [0., 0., 0.]), dtype=float)
        length = float(values.resolve(surface.length))
        center = location + [0., 0., length / 2]
        return pv.Cylinder(
            center=center,
            direction=(0., 0., 1.),
            radius=float(values.resolve(surface.r0)),
            height=length,
            resolution=CONSTANT.UI.VIEWER.GEOMETRY.CYLINDER_RESOLUTION,
        )

    @staticmethod
    def sphere(surface: SurfaceNode, values: DefinitionValues) -> pv.PolyData:
        return pv.Sphere(
            center=values.resolve(surface.init_location or [0., 0., 0.]),
            radius=float(values.resolve(surface.r0)),
            theta_resolution=CONSTANT.UI.VIEWER.GEOMETRY.SPHERE_THETA_RESOLUTION,
            phi_resolution=CONSTANT.UI.VIEWER.GEOMETRY.SPHERE_PHI_RESOLUTION,
        )

    @staticmethod
    def stl(surface: SurfaceNode, values: DefinitionValues) -> pv.DataSet | None:
        return pv.read(surface.path_stl) if surface.path_stl and os.path.exists(surface.path_stl) else None


class PreviewGeometry:
    def __init__(
        self,
        parts: PartPreviewVisitor | None = None,
        surfaces: SurfacePreviewVisitor | None = None,
    ) -> None:
        self.parts = parts or default_part_visitor()
        self.surfaces = surfaces or SurfacePreviewVisitor()
        self.problem: ProblemDefinition
        self.scene = PreviewScene()
        self._model_cache_key: tuple[object, ...] | None = None
        self._model_assembly: torchfea.Assembly | None = None
        self._cad_face_meshes: dict[tuple[str, str], pv.DataSet] = {}
        self._local_cad_faces: dict[tuple[int, str], pv.DataSet] = {}
        self._part_cache: dict[int, torchfea.Part] = {}
        self._box_cache: dict[int, BoxPart] = {}
        self._cad_cache: dict[int, list[dict[str, Any]]] = {}
        self._instance_colors: dict[str, str] = {}
        self.values = DefinitionValues(None)

    def build(
        self,
        problem: ProblemDefinition,
        mode: str,
        selected: PartNode | None = None,
    ) -> PreviewScene:
        self.problem = problem
        self.scene = PreviewScene()
        self._cad_face_meshes = {}
        self._local_cad_faces = {}
        self._part_cache = {}
        self._box_cache = {}
        self._cad_cache = {}
        self._instance_colors = {}
        self.values = DefinitionValues(problem)
        if problem.imported_model_part_node() is None:
            self._clear_model_preview()
        if mode == "part":
            parts = [selected] if selected is not None else []
        elif mode == "assembly":
            parts = problem.part_interfaces()
            for part in parts:
                for instance in part.instances():
                    if instance.name not in self._instance_colors:
                        color_index = len(self._instance_colors)
                        self._instance_colors[instance.name] = _instance_color(
                            color_index
                        )
        else:
            raise ValueError(localized_message("ui.errors.geometry.unknown_preview_mode_value", value_0=mode))
        for part in parts:
            instances = part.instances() if mode == "assembly" else [None]
            for instance in instances:
                try:
                    self.parts.visit(self, part, instance)
                except (ValueError, TypeError, KeyError, OSError, RuntimeError, NotImplementedError, NameError, SyntaxError) as exc:
                    self._show_preview_message(str(exc))
        if mode == "assembly":
            try:
                self._draw_material_boxes()
            except (ValueError, TypeError, NameError, SyntaxError) as exc:
                self._show_preview_message(str(exc))
            legend: dict[str, str] = {}
            for name, _mesh, item in self.scene.base_meshes:
                if name in self._instance_colors:
                    legend.setdefault(name, self._instance_colors[name])
            self.scene.instance_legend = list(legend.items())
        return self.scene

    def instance_color(self, instance_name: str) -> str:
        """Return a stable assembly color for a named Instance."""
        return self._instance_colors.get(instance_name, _INSTANCE_COLORS[0])

    def surface_mesh(self, surface: SurfaceNode) -> pv.DataSet | None:
        return self.surfaces.visit(surface, self.values)

    def cached_part(
        self,
        part: PartNode,
        factory: Callable[[], torchfea.Part],
    ) -> torchfea.Part:
        if id(part) not in self._part_cache:
            model_part = factory()
            model_part.initialize()
            self._part_cache[id(part)] = model_part
        return self._part_cache[id(part)]

    def box_interface(self, part: PartNode) -> BoxPart:
        if id(part) not in self._box_cache:
            self._box_cache[id(part)] = BoxPart(
                length=self.values.resolve(part.length),
                height=self.values.resolve(part.height),
                depth=self.values.resolve(part.depth),
                mesh_size=self.values.resolve(part.mesh_size),
                mesh_order=self.values.resolve(part.mesh_order),
                exterior_surface=part.exterior_surface or "extern",
                part_name=part.resolved_part_name(),
            )
        return self._box_cache[id(part)]

    def cad_records(self, part: PartNode) -> list[dict[str, Any]]:
        if id(part) not in self._cad_cache:
            self._cad_cache[id(part)] = cad_brep_records_from_node(part, self.problem)
        return self._cad_cache[id(part)]

    def mesh_for_surface(self, interface: FEAComponentNode, surface_name: str) -> pv.DataSet | None:
        instance = interface.instance
        name = instance.name if instance is not None else interface.instance_name or ""
        face = _cad_face_name(surface_name)
        if face is not None and (name, face) in self._cad_face_meshes:
            return self._cad_face_meshes[(name, face)]
        part = self.problem.part_interface_for_instance(instance or name)
        if part is None:
            part = next((p for p in self.problem.part_interfaces() if p.resolved_part_name() == name), None)
        if part is None:
            return None
        try:
            mesh = self.parts.adapter(part).surface(self, part, surface_name)
            if instance is None:
                instance = next((item for item in part.instances() if item.name == name), None)
            return apply_instance_pose(
                mesh,
                instance,
                self.values,
            ) if mesh is not None and instance is not None else mesh
        except (KeyError, ValueError, NotImplementedError):
            return None

    def node_set_center(self, instance_name: str, set_name: str) -> np.ndarray | None:
        part = self.problem.part_interface_for_instance(instance_name)
        if part is None:
            return None
        try:
            adapter = self.parts.adapter(part)
            model = adapter.model_part(self, part)
            points = None
            if model is not None:
                ids = np.asarray(model.set_nodes.get(set_name, []), dtype=int)
                if len(ids):
                    points = model.nodes.detach().cpu().numpy()[ids]

            if points is None:
                mesh = adapter.surface(self, part, set_name)
                if mesh is None or not mesh.n_points:
                    return None
                points = np.asarray(mesh.points, dtype=float)
                points = _preview_node_set_points(part, set_name, points)
                if not len(points):
                    return None

            point = pv.PolyData(points.mean(axis=0).reshape(1, 3))
            instance = next((i for i in part.instances() if i.name == instance_name), None)
            return apply_instance_pose(point, instance, self.values).points[0] if instance else point.points[0]
        except (KeyError, IndexError, ValueError, NotImplementedError):
            return None

    def _draw_material_boxes(self) -> None:
        scene = self.scene
        for material in self.problem.material_nodes():
            bounds = self.values.resolve(material.bounding_box)
            if not bounds or not any(bounds) or len(bounds) != 6:
                continue
            target = material.part
            instances = target.instances() if target is not None else []
            if not instances:
                instances = [None]
            for instance in instances:
                box = pv.Box(bounds=list(bounds))
                if instance is not None:
                    box = apply_instance_pose(box, instance, self.values)
                name = f"material-box:{material.name}"
                if instance is not None:
                    name += f":{instance.name}"
                scene.add_mesh(
                    box,
                    name=name,
                    style="wireframe",
                    color=CONSTANT.UI.VIEWER.GEOMETRY.MATERIAL_REGION_COLOR,
                    opacity=CONSTANT.UI.VIEWER.GEOMETRY.MATERIAL_REGION_OPACITY,
                )
                scene.add_mesh(
                    box,
                    name=f"{name}:fill",
                    color=CONSTANT.UI.VIEWER.GEOMETRY.MATERIAL_REGION_COLOR,
                    opacity=CONSTANT.UI.VIEWER.GEOMETRY.MATERIAL_REGION_FILL_OPACITY,
                )

    def _show_preview_message(self, message: str) -> None:
        self.scene.add_text(
            message,
            position="upper_left",
            color=CONSTANT.UI.VIEWER.RENDER.MARKER_COLOR_ANNOTATION_ERROR,
            font_size=CONSTANT.UI.VIEWER.RENDER.LABEL_FONT_SIZE,
        )

    def _ensure_torchfea_model(self, geometry: PartNode) -> torchfea.Assembly:
        if not geometry.model_directory:
            self._clear_model_preview()
            raise ValueError(localized_message("ui.errors.geometry.no_torchfea_model_is_linked_from_initial_geometry"))
        model_directory = resolve_model_directory(geometry.model_directory)
        path = resolve_model_path(model_directory, geometry.model_filename or "")
        placement_key = tuple(
            (
                interface.resolved_part_name(),
                interface.model_part_name,
                tuple(
                    (instance.name, *self.values.resolve(instance.translation), *self.values.resolve(instance.rotation))
                    for instance in interface.instances()
                ),
            )
            for interface in self.problem.part_interfaces()
            if interface.interface_type == "TorchFEAPart"
        )
        cache_key = (str(path), path.stat().st_mtime_ns, placement_key)
        if cache_key == self._model_cache_key and self._model_assembly is not None:
            return self._model_assembly
        source = load_model_assembly(model_directory, geometry.model_filename or "")
        assembly = self._assembly_for_problem(source)
        assembly.initialize()
        self._model_assembly = assembly
        self._model_cache_key = cache_key
        return assembly

    def _clear_model_preview(self) -> None:
        """Forget the cached Assembly when the preview switches model type."""
        self._model_cache_key = None
        self._model_assembly = None

    def _assembly_for_problem(self, source: torchfea.Assembly) -> torchfea.Assembly:
        """Build a preview Assembly from the UI's Part/Instance definitions."""
        assembly = torchfea.Assembly()
        interfaces = [
            interface
            for interface in self.problem.part_interfaces()
            if interface.interface_type == "TorchFEAPart"
        ]
        if not interfaces:
            return source

        for interface in interfaces:
            source_part_name = (
                interface.model_part_name or interface.resolved_part_name()
            )
            part = source.get_part(source_part_name)
            part_name = interface.resolved_part_name()
            assembly.add_part(part=part, name=part_name)
            for instance in interface.instances():
                assembly.add_instance(
                    instance=torchfea.Instance(
                        part_name=part_name,
                        translation=self.values.resolve(instance.translation),
                        rotation=self.values.resolve(instance.rotation),
                    ),
                    name=instance.name,
                )
        return assembly

    def instance_center(self, instance_name: str) -> np.ndarray | None:
        meshes = [
            mesh
            for name, mesh, _item in self.scene.base_meshes
            if name == instance_name and mesh.n_points
        ]
        if not meshes:
            return None
        bounds = np.asarray([mesh.bounds for mesh in meshes], dtype=float)
        return np.array(
            [
                (bounds[:, 0].min() + bounds[:, 1].max()) / 2.0,
                (bounds[:, 2].min() + bounds[:, 3].max()) / 2.0,
                (bounds[:, 4].min() + bounds[:, 5].max()) / 2.0,
            ]
        )

    def object_center(self, object_name: str) -> np.ndarray | None:
        center = self.instance_center(object_name)
        if center is not None:
            return center
        part = next(
            (
                item
                for item in self.problem.part_interfaces()
                if item.name == object_name
                or item.resolved_part_name() == object_name
            ),
            None,
        )
        if part is None:
            return None
        centers = [
            self.instance_center(instance.name)
            for instance in part.instances()
        ]
        centers = [item for item in centers if item is not None]
        return np.mean(centers, axis=0) if centers else None


def _cad_face_name(surface_name: str) -> str | None:
    """Map a CAD face or face node-set name to its face surface name."""
    import re

    match = re.match(r"(face_\d+)(?:_|$)", surface_name)
    return match.group(1) if match else None


def _instance_color(index: int) -> str:
    if index < len(_INSTANCE_COLORS):
        return _INSTANCE_COLORS[index]
    hue = (
        (index - len(_INSTANCE_COLORS))
        * CONSTANT.UI.VIEWER.GEOMETRY.EXTRA_INSTANCE_HUE_STEP
        + CONSTANT.UI.VIEWER.GEOMETRY.EXTRA_INSTANCE_HUE_OFFSET
    ) % 1.0
    red, green, blue = hsv_to_rgb(
        hue,
        CONSTANT.UI.VIEWER.GEOMETRY.EXTRA_INSTANCE_SATURATION,
        CONSTANT.UI.VIEWER.GEOMETRY.EXTRA_INSTANCE_VALUE,
    )
    return (
        f"#{round(red * 255):02x}"
        f"{round(green * 255):02x}"
        f"{round(blue * 255):02x}"
    )


def _surface_index_from_name(surface_name: str) -> int:
    """surface_1_All / surface_1_offset -> 1"""
    import re

    m = re.match(r"surface_(\d+)_", surface_name)
    return int(m.group(1)) if m else -1


def _boundary_end_surface(mesh: pv.DataSet, end: str) -> pv.DataSet:
    """Extract the actual cap cells used by a boundary-part end node set."""
    if not mesh.n_cells or not mesh.n_points:
        return mesh
    centers = mesh.cell_centers().points
    bounds = mesh.bounds
    target = bounds[5] if end == "Head" else bounds[4]
    tolerance = max(
        (bounds[5] - bounds[4])
        * CONSTANT.UI.VIEWER.GEOMETRY.BOUNDARY_RELATIVE_TOLERANCE,
        CONSTANT.UI.VIEWER.GEOMETRY.BOUNDARY_ABSOLUTE_TOLERANCE,
    )
    cap_cells = np.abs(centers[:, 2] - target) <= tolerance
    if not np.any(cap_cells):
        return mesh
    return mesh.extract_cells(cap_cells).extract_surface(
        algorithm="dataset_surface"
    )


def _preview_node_set_points(
    part: PartNode, set_name: str, points: np.ndarray
) -> np.ndarray:
    """Approximate a named boundary node set from its preview surface."""
    if part.interface_type not in {"BoundaryPart", "OffsetBoundaryPart"}:
        return points
    suffix = set_name.rsplit("_", 1)[-1]
    if suffix not in {"Head", "Bottom"}:
        return points
    z = points[:, 2]
    target = float(z.max() if suffix == "Head" else z.min())
    tolerance = max(
        float(np.ptp(points, axis=0).max())
        * CONSTANT.UI.VIEWER.GEOMETRY.BOUNDARY_RELATIVE_TOLERANCE,
        CONSTANT.UI.VIEWER.GEOMETRY.BOUNDARY_ABSOLUTE_TOLERANCE,
    )
    return points[np.abs(z - target) <= tolerance]


class InitialDesignGeometry:
    """Prepared isometric triangles and outlines; painting contains no geometry work."""
    horizontal = np.array([1., -1., 0.]) / np.sqrt(2)
    vertical = np.array([1., 1., -2.]) / np.sqrt(6)
    depth = np.array([1., 1., 1.]) / np.sqrt(3)

    def __init__(self, options):
        meshes = options.geometry_layout().get_initial_meshes() if options.method == "shapeopt" else {
            "body": BoxPreviewAdapter.mesh(
                length=options.length,
                height=options.height,
                depth=options.depth,
            )
        }
        palette = CONSTANT.UI.QUICKSTART.PREVIEW.CAVITY_COLORS
        self.triangles = []
        self.lines = []
        for name, mesh in meshes.items():
            mesh = mesh.triangulate()
            xyz = mesh.points[mesh.faces.reshape(-1, 4)[:, 1:]]
            normals = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
            light_direction = np.asarray(
                deepcopy(CONSTANT.UI.VIEWER.GEOMETRY.MESH_LIGHT_DIRECTION), dtype=float
            )
            normal_length = np.maximum(
                np.linalg.norm(normals, axis=1),
                CONSTANT.UI.VIEWER.GEOMETRY.SURFACE_NORMAL_TOLERANCE,
            )
            light = CONSTANT.UI.VIEWER.GEOMETRY.MESH_LIGHT_AMBIENT + (
                CONSTANT.UI.VIEWER.GEOMETRY.MESH_LIGHT_CONTRAST
                * np.abs(normals @ light_direction)
                / (normal_length * np.linalg.norm(light_direction))
            )
            color = (
                CONSTANT.UI.QUICKSTART.PREVIEW.BODY_COLOR
                if name == "body"
                else palette[int(name.split(":")[0].split("-")[1]) % len(palette)]
            )
            alpha = (
                CONSTANT.UI.QUICKSTART.PREVIEW.BODY_TRANSPARENCY_ALPHA
                if name == "body" and options.method == "shapeopt"
                else CONSTANT.UI.QUICKSTART.PREVIEW.OPAQUE_ALPHA
            )
            for points, brightness in zip(xyz, light):
                self.triangles.append((
                    float(points.mean(axis=0) @ self.depth),
                    self.coordinates(points),
                    color,
                    int(CONSTANT.UI.QUICKSTART.PREVIEW.LIGHT_INTENSITY_SCALE * brightness),
                    alpha,
                ))
        self.triangles.sort(key=lambda item: item[0])
        vertices = np.concatenate([mesh.points for mesh in meshes.values()])
        projected = self.coordinates(vertices)
        self.lower, self.upper = projected.min(axis=0), projected.max(axis=0)
        if options.method == "shapeopt":
            for sign in (-1., 1.):
                xy = sign * options.radius * self.horizontal[:2]
                self.lines.append(self.coordinates(np.array([[*xy, 0.], [*xy, options.total_length]])))
            angles = np.linspace(
                0.0, 2 * np.pi, CONSTANT.UI.QUICKSTART.PREVIEW.OUTLINE_CIRCLE_SAMPLES
            )
            for z in (0., options.total_length):
                self.lines.append(self.coordinates(np.column_stack((options.radius * np.cos(angles), options.radius * np.sin(angles), np.full_like(
                    angles,
                    z,
                )))))

    @classmethod
    def coordinates(cls, points: np.ndarray) -> np.ndarray:
        return np.column_stack((points @ cls.horizontal, points @ cls.vertical))

    def transform(self, width: int, height: int) -> tuple[float, np.ndarray]:
        span = np.maximum(
            self.upper - self.lower, CONSTANT.UI.QUICKSTART.PREVIEW.MINIMUM_PROJECTED_SPAN
        )
        scale = min(
            (width - CONSTANT.UI.QUICKSTART.PREVIEW.HORIZONTAL_MARGIN) / span[0],
            (height - CONSTANT.UI.QUICKSTART.PREVIEW.VERTICAL_MARGIN) / span[1],
        )
        return scale, np.array([width / 2, height / 2]) - scale * (self.lower + self.upper) / 2
