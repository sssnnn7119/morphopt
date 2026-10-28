"""Per-Part preview visitors and cached model queries. No Qt or VTK actors."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from colorsys import hsv_to_rgb
from copy import deepcopy
from typing import Any, Generic, TypeVar, cast

import numpy as np
import pyvista as pv
import torchfea

from ...optcore.modelparams.parts import (
    BoxPart,
    INPPart,
)
from ..application.cad import cad_brep_records_from_node
from ..application.expressions import DefinitionValues
from ..i18n import localized_message
from ..model.node_types.materials import SIMPFieldMaterialNode
from ..model.node_types.parts import (
    BoundaryPartNode,
    BoxPartNode,
    CADPartNode,
    INPPartNode,
)
from ..model.node_types.surfaces import (
    BREPSurfaceNode,
    BspCylinderSurfaceNode,
    CPGEOCylinderSurfaceNode,
    CPGEOSphereSurfaceNode,
    MeshSurfaceNode,
)
from ..model.problem import (
    FEAComponentNode,
    InstanceNode,
    PartNode,
    ProblemDefinition,
    SurfaceNode,
)
from ..theme import theme_manager
from .scene import MeshFaces, PreviewScene

_CAD_FACE_ID = "morphopt_cad_face_id"


def apply_instance_pose(
    mesh: pv.DataSet,
    instance: InstanceNode,
    values: DefinitionValues | None = None,
) -> pv.DataSet:
    transformed = mesh.copy()
    rotation = np.asarray(
        values.resolve(instance.rotation) if values else instance.rotation, dtype=float
    )
    angle = float(np.linalg.norm(rotation))
    if angle > theme_manager.palette.viewer.geometry.rotation_zero_tolerance:
        transformed.rotate_vector(
            rotation / angle, np.degrees(angle), point=(0, 0, 0), inplace=True
        )
    transformed.translate(
        np.asarray(
            values.resolve(instance.translation) if values else instance.translation,
            dtype=float,
        ),
        inplace=True,
    )
    return transformed


PartT = TypeVar("PartT", bound=PartNode)


class PartPreviewAdapter(Generic[PartT]):
    """Extension point for geometry, surface selections and node-set queries."""

    def preview(
        self,
        context: PreviewGeometry,
        part: PartT,
        instance: InstanceNode | None,
    ) -> None:
        raise NotImplementedError

    def surface(
        self,
        context: PreviewGeometry,
        part: PartT,
        name: str,
    ) -> pv.DataSet | None:
        return None

    def model_part(self, context: PreviewGeometry, part: PartT) -> torchfea.Part | None:
        return None


class PartPreviewVisitor:
    def __init__(self) -> None:
        self._adapters: dict[type[PartNode], PartPreviewAdapter[Any]] = {}

    def register(
        self, node_type: type[PartT], adapter: PartPreviewAdapter[PartT]
    ) -> None:
        self._adapters[node_type] = adapter

    def adapter(self, part: PartT) -> PartPreviewAdapter[PartT]:
        for node_type in type(part).__mro__:
            if node_type in self._adapters:
                return cast(PartPreviewAdapter[PartT], self._adapters[node_type])
        raise NotImplementedError(
            localized_message(
                "ui.errors.geometry.no_preview_adapter_registered_for_value",
                value_0=part.type,
            )
        )

    def visit(
        self,
        context: PreviewGeometry,
        part: PartNode,
        instance: InstanceNode | None,
    ) -> None:
        self.adapter(part).preview(context, part, instance)


class BoundaryPreviewAdapter(PartPreviewAdapter[BoundaryPartNode]):
    def preview(
        self,
        context: PreviewGeometry,
        part: BoundaryPartNode,
        instance: InstanceNode | None,
    ) -> None:
        surfaces = part.surfaces
        for index, surface in enumerate(surfaces):
            mesh = context.surface_mesh(surface)
            if mesh is None:
                continue
            face_groups = np.zeros(mesh.n_cells, dtype=np.int64)
            face_names = [(f"surface_{index}_All",)]
            if isinstance(surface, BREPSurfaceNode) and json.loads(
                surface.brep_metadata
            ).get("face_map", {}):
                ids = np.asarray(mesh.cell_data["face_index"], dtype=np.int64)
                for face_id in np.unique(ids):
                    face_groups[ids == face_id] = len(face_names)
                    face_names.append((f"face_{face_id}", f"surface_{index}_All"))
            if index == 0:
                for end in surface.end_node_set_names:
                    cap = _boundary_end_cells(mesh, end)
                    for group in np.unique(face_groups[cap]):
                        mask = cap & (face_groups == group)
                        face_groups[mask] = len(face_names)
                        face_names.append((*face_names[int(group)], f"surface_0_{end}"))
            if instance is not None:
                mesh = apply_instance_pose(mesh, instance, context.values)
            name = instance.name if instance is not None else part.name
            options = {
                "color": (
                    context.instance_color(instance.name)
                    if instance is not None
                    else theme_manager.palette.viewer.geometry.uninstanced_color
                ),
                # Both sides of the exterior shell cover the cavity. Keep
                # their combined opacity low enough to see internal loads.
                "opacity": (
                    theme_manager.palette.viewer.geometry.boundary_shell_opacity
                    if len(surfaces) > 1 and index == 0
                    else 1.0
                ),
                # Tessellation edges are display subdivisions, not geometric
                # boundaries; drawing them produces stripes on curved shells.
                "show_edges": False,
                "smooth_shading": True,
            }
            context.scene.add_base(
                name,
                mesh,
                name=f"boundary:{name}:surface-{index}",
                faces=MeshFaces(
                    part.name,
                    instance.name if instance else None,
                    face_groups,
                    tuple(face_names),
                ),
                **options,
            )

    def surface(
        self,
        context: PreviewGeometry,
        part: BoundaryPartNode,
        name: str,
    ) -> pv.DataSet | None:
        face_name = _cad_face_name(name)
        if face_name is not None:
            face_id = int(face_name[5:])
            for surface in part.surfaces:
                if not isinstance(
                    surface, BREPSurfaceNode
                ) or face_name not in json.loads(surface.brep_metadata).get(
                    "face_map", {}
                ):
                    continue
                mesh = context.surface_mesh(surface)
                if mesh is not None:
                    cells = np.flatnonzero(
                        np.asarray(mesh.cell_data["face_index"]) == face_id
                    )
                    return mesh.extract_cells(cells).extract_surface(
                        algorithm="dataset_surface"
                    )
            return None
        index = _surface_index_from_name(name)
        surfaces = part.surfaces
        if not 0 <= index < len(surfaces):
            return None
        mesh = context.surface_mesh(surfaces[index])
        if mesh is None:
            return None
        end = name.rsplit("_", 1)[-1]
        if end in {"Head", "Bottom"}:
            if index != 0 or end not in surfaces[index].end_node_set_names:
                return None
            return _boundary_end_surface(mesh, end)
        return mesh


class BoxPreviewAdapter(PartPreviewAdapter[BoxPartNode]):
    @staticmethod
    def mesh(length: float, height: float, depth: float) -> pv.PolyData:
        """Build the six-face preview shell without generating an FE mesh."""
        return pv.Box(bounds=[0.0, length, 0.0, height, 0.0, depth])

    def preview(
        self,
        context: PreviewGeometry,
        part: BoxPartNode,
        instance: InstanceNode | None,
    ) -> None:
        box = context.box_part(part)
        mesh = self.mesh(box.length, box.height, box.depth)
        centers = mesh.cell_centers().points
        bounds = np.asarray(mesh.bounds).reshape(3, 2)
        distances = np.abs(centers[:, :, None] - bounds[None, :, :])
        face_groups = distances.reshape(-1, 6).argmin(axis=1)
        face_names = tuple(
            (f"surface_{axis}{side}",) for axis in "xyz" for side in ("min", "max")
        )
        name = instance.name if instance is not None else part.name
        if instance is not None:
            mesh = apply_instance_pose(mesh, instance, context.values)
        context.scene.add_base(
            name,
            mesh,
            name=f"box:{name}",
            faces=MeshFaces(
                part.name, instance.name if instance else None, face_groups, face_names
            ),
            color=context.instance_color(instance.name)
            if instance
            else theme_manager.palette.viewer.geometry.uninstanced_color,
            opacity=1.0,
            show_edges=instance is None,
        )

    def model_part(self, context: PreviewGeometry, part: BoxPartNode) -> torchfea.Part:
        return context.cached_part(part, lambda: context.box_part(part).get_part())

    def surface(
        self,
        context: PreviewGeometry,
        part: BoxPartNode,
        name: str,
    ) -> pv.DataSet | None:
        node_faces = {
            f"nodes_{axis}{side}": f"surface_{axis}{side}"
            for axis in "xyz"
            for side in ("min", "max")
        }
        name = node_faces.get(name, name)
        if name in {"", "extern", part.exterior_surface or "extern"}:
            box = context.box_part(part)
            return self.mesh(box.length, box.height, box.depth)
        return self.model_part(context, part).get_mesh(surf_name=name)


class INPPreviewAdapter(PartPreviewAdapter[INPPartNode]):
    def model_part(self, context: PreviewGeometry, part: INPPartNode) -> torchfea.Part:
        return context.cached_part(
            part,
            lambda: INPPart(
                mesh_file=part.mesh_file,
                part_name=part.assembly_name,
                inp_part_name=part.inp_part_name or None,
                exterior_surface=part.exterior_surface or None,
            ).get_part(),
        )

    def surface(
        self,
        context: PreviewGeometry,
        part: INPPartNode,
        name: str,
    ) -> pv.DataSet | None:
        return self.model_part(context, part).get_mesh(surf_name=name or None)

    def preview(
        self,
        context: PreviewGeometry,
        part: INPPartNode,
        instance: InstanceNode | None,
    ) -> None:
        mesh = self.surface(context, part, part.exterior_surface or "")
        if mesh is not None:
            faces = _inp_mesh_faces(
                self.model_part(context, part), mesh, part, instance
            )
            name = instance.name if instance is not None else part.name
            if instance is not None:
                mesh = apply_instance_pose(mesh, instance, context.values)
            context.scene.add_base(
                name,
                mesh,
                name=f"inp:{name}",
                faces=faces,
                color=context.instance_color(instance.name)
                if instance
                else theme_manager.palette.viewer.geometry.uninstanced_color,
                opacity=1.0,
                show_edges=instance is None,
                smooth_shading=True,
            )


class CADPreviewAdapter(PartPreviewAdapter[CADPartNode]):
    def preview(
        self,
        context: PreviewGeometry,
        part: CADPartNode,
        instance: InstanceNode | None,
    ) -> None:
        scene = context.scene
        instance_name = instance.name if instance is not None else part.name or "part"
        face_mesh, edge_mesh = context.cad_meshes(part)
        if not face_mesh.n_cells:
            return
        face_ids = np.asarray(face_mesh.cell_data[_CAD_FACE_ID], dtype=np.int64)
        faces = MeshFaces(
            part.name,
            instance.name if instance else None,
            face_ids,
            tuple((f"face_{index}",) for index in range(int(face_ids.max()) + 1)),
        )
        if instance is not None:
            face_mesh = apply_instance_pose(face_mesh, instance, context.values)
            edge_mesh = apply_instance_pose(edge_mesh, instance, context.values)

        # A Part is rendered as one face actor and one edge actor.  CAD models
        # routinely contain hundreds of topological faces, so creating an actor
        # per face (and another per edge) makes a viewport refresh prohibitively
        # expensive.  The face index remains in cell data for set lookup.
        scene.add_base(
            instance_name,
            face_mesh,
            name=f"cad:{instance_name}",
            faces=faces,
            color=context.instance_color(instance.name)
            if instance
            else theme_manager.palette.viewer.geometry.uninstanced_color,
            opacity=1.0,
            show_edges=False,
            smooth_shading=True,
            ambient=theme_manager.palette.viewer.geometry.cad_face_ambient,
            diffuse=theme_manager.palette.viewer.geometry.cad_face_diffuse,
            specular=theme_manager.palette.viewer.geometry.cad_face_specular,
            specular_power=theme_manager.palette.viewer.geometry.cad_face_specular_power,
        )
        if edge_mesh.n_lines:
            scene.add_mesh(
                edge_mesh,
                name=f"cad-edges:{instance_name}",
                color=theme_manager.palette.viewer.geometry.cad_edge_color,
                line_width=theme_manager.palette.viewer.geometry.cad_edge_width,
                render_lines_as_tubes=False,
                lighting=False,
            )

    def surface(
        self,
        context: PreviewGeometry,
        part: CADPartNode,
        name: str,
    ) -> pv.DataSet | None:
        face_name = _cad_face_name(name)
        if face_name is None:
            return None
        return context.cad_face_mesh(part, face_name)


class KernelPreviewAdapter(INPPreviewAdapter):
    """Custom Parts use their kernel mesh for geometry and named sets."""

    def model_part(self, context: PreviewGeometry, part: PartNode) -> torchfea.Part:
        from ..application.part_mesh import build_part_mesh

        return context.cached_part(part, lambda: build_part_mesh(part, context.problem))


def default_part_visitor() -> PartPreviewVisitor:
    visitor = PartPreviewVisitor()
    visitor.register(PartNode, KernelPreviewAdapter())
    visitor.register(BoundaryPartNode, BoundaryPreviewAdapter())
    visitor.register(BoxPartNode, BoxPreviewAdapter())
    visitor.register(CADPartNode, CADPreviewAdapter())
    visitor.register(INPPartNode, INPPreviewAdapter())
    return visitor


SurfaceT = TypeVar("SurfaceT", bound=SurfaceNode)


class SurfacePreviewVisitor:
    def __init__(self) -> None:
        self._builders: dict[
            type[SurfaceNode], Callable[[Any, DefinitionValues], pv.DataSet | None]
        ] = {}
        self.register(BspCylinderSurfaceNode, self.cylinder)
        self.register(CPGEOCylinderSurfaceNode, self.cylinder)
        self.register(CPGEOSphereSurfaceNode, self.sphere)
        self.register(MeshSurfaceNode, self.mesh)
        self.register(BREPSurfaceNode, self.brep)

    def register(
        self,
        node_type: type[SurfaceT],
        builder: Callable[[SurfaceT, DefinitionValues], pv.DataSet | None],
    ) -> None:
        self._builders[node_type] = builder

    def visit(
        self, surface: SurfaceNode, values: DefinitionValues
    ) -> pv.DataSet | None:
        builder = next(
            (
                self._builders[cls]
                for cls in type(surface).__mro__
                if cls in self._builders
            ),
            None,
        )
        return builder(surface, values) if builder else None

    @staticmethod
    def cylinder(
        surface: BspCylinderSurfaceNode | CPGEOCylinderSurfaceNode,
        values: DefinitionValues,
    ) -> pv.PolyData:
        location = np.asarray(
            values.resolve(surface.init_location or [0.0, 0.0, 0.0]), dtype=float
        )
        length = float(values.resolve(surface.length))
        center = location + [0.0, 0.0, length / 2]
        return pv.Cylinder(
            center=center,
            direction=(0.0, 0.0, 1.0),
            radius=float(values.resolve(surface.r0)),
            height=length,
            resolution=theme_manager.palette.viewer.geometry.cylinder_resolution,
        )

    @staticmethod
    def sphere(
        surface: CPGEOSphereSurfaceNode, values: DefinitionValues
    ) -> pv.PolyData:
        return pv.Sphere(
            center=values.resolve(surface.init_location or [0.0, 0.0, 0.0]),
            radius=float(values.resolve(surface.r0)),
            theta_resolution=theme_manager.palette.viewer.geometry.sphere_theta_resolution,
            phi_resolution=theme_manager.palette.viewer.geometry.sphere_phi_resolution,
        )

    @staticmethod
    def mesh(surface: MeshSurfaceNode, values: DefinitionValues) -> pv.DataSet | None:
        return (
            pv.read(surface.path_stl)
            if surface.path_stl and os.path.exists(surface.path_stl)
            else None
        )

    @staticmethod
    def brep(surface: BREPSurfaceNode, values: DefinitionValues) -> pv.PolyData | None:
        """Preview the embedded STEP asset with its original geometric face IDs."""
        import base64
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from ...shapeopt.surfaces import BREPSurface

        if not surface.data:
            return None
        with TemporaryDirectory(prefix="morphopt_stp_preview_") as directory:
            path = Path(directory) / surface.filename
            path.write_bytes(base64.b64decode(surface.data, validate=True))
            path.with_suffix(".brep.json").write_text(
                surface.brep_metadata, encoding="utf-8"
            )
            return BREPSurface(path).get_mesh()


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
        self._cad_face_meshes: dict[tuple[str, str], pv.DataSet] = {}
        self._local_cad_faces: dict[tuple[int, str], pv.DataSet] = {}
        self._part_cache: dict[int, torchfea.Part] = {}
        self._box_cache: dict[int, BoxPart] = {}
        self._cad_cache: dict[int, list[dict[str, Any]]] = {}
        self._cad_mesh_cache: dict[int, tuple[pv.PolyData, pv.PolyData]] = {}
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
        self._cad_mesh_cache = {}
        self._instance_colors = {}
        self.values = DefinitionValues(problem)
        if mode == "part":
            self.scene.show_bounding_box = True
            parts = [selected] if selected is not None else []
        elif mode == "assembly":
            parts = problem.parts()
            for part in parts:
                for instance in part.instances:
                    if instance.name not in self._instance_colors:
                        color_index = len(self._instance_colors)
                        self._instance_colors[instance.name] = _instance_color(
                            color_index
                        )
        else:
            raise ValueError(
                localized_message(
                    "ui.errors.geometry.unknown_preview_mode_value", value_0=mode
                )
            )
        for part in parts:
            instances = part.instances if mode == "assembly" else [None]
            for instance in instances:
                try:
                    self.parts.visit(self, part, instance)
                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    OSError,
                    RuntimeError,
                    NotImplementedError,
                    NameError,
                    SyntaxError,
                ) as exc:
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
        return self._instance_colors.get(
            instance_name, theme_manager.palette.viewer.geometry.instance_colors[0]
        )

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

    def box_part(self, part: BoxPartNode) -> BoxPart:
        if id(part) not in self._box_cache:
            self._box_cache[id(part)] = BoxPart(
                length=self.values.resolve(part.length),
                height=self.values.resolve(part.height),
                depth=self.values.resolve(part.depth),
                mesh_size=self.values.resolve(part.mesh_size),
                mesh_order=self.values.resolve(part.mesh_order),
                exterior_surface=part.exterior_surface or "extern",
                part_name=part.assembly_name,
            )
        return self._box_cache[id(part)]

    def cad_records(self, part: CADPartNode) -> list[dict[str, Any]]:
        if id(part) not in self._cad_cache:
            self._cad_cache[id(part)] = cad_brep_records_from_node(part, self.problem)
        return self._cad_cache[id(part)]

    def cad_meshes(self, part: CADPartNode) -> tuple[pv.PolyData, pv.PolyData]:
        """Build one face mesh and one edge mesh for a CAD Part preview.

        The combined face mesh keeps the originating OCC face index in cell
        data, so individual ``face_N`` selections can be extracted on demand
        without multiplying viewport actors.  Points are duplicated across
        topological faces to retain their independent face normals.
        """
        key = id(part)
        if key in self._cad_mesh_cache:
            return self._cad_mesh_cache[key]

        records = self.cad_records(part)
        if not records:
            empty = pv.PolyData()
            self._cad_mesh_cache[key] = (empty, empty)
            return empty, empty

        points = np.asarray(records[0]["points"], dtype=float).reshape(-1, 3)
        face_points: list[np.ndarray] = []
        face_cells: list[np.ndarray] = []
        face_ids: list[np.ndarray] = []
        edge_cells: list[np.ndarray] = []
        seen_edges: set[int] = set()
        face_point_offset = 0
        for face_index, record in enumerate(records):
            triangles = np.asarray(record["triangles"], dtype=np.int64).reshape(-1, 3)
            if not len(triangles):
                raise ValueError(
                    localized_message(
                        "ui.errors.geometry.cad_face_value_has_no_display_triangles",
                        value_0=face_index,
                    )
                )
            point_ids = np.unique(triangles)
            face_points.append(points[point_ids])
            local_triangles = np.searchsorted(point_ids, triangles) + face_point_offset
            face_cells.append(
                np.column_stack(
                    (
                        np.full(len(local_triangles), 3, dtype=np.int64),
                        local_triangles,
                    )
                ).ravel()
            )
            face_ids.append(np.full(len(triangles), face_index, dtype=np.int64))
            face_point_offset += len(point_ids)

            for edge in record.get("edge_lines", []):
                edge_tag = int(edge.get("edge_tag", -1))
                lines = np.asarray(edge.get("lines", []), dtype=np.int64).reshape(-1, 2)
                if edge_tag < 0 or edge_tag in seen_edges or not len(lines):
                    continue
                seen_edges.add(edge_tag)
                edge_cells.append(
                    np.column_stack(
                        (np.full(len(lines), 2, dtype=np.int64), lines)
                    ).ravel()
                )

        faces = pv.PolyData(np.concatenate(face_points), np.concatenate(face_cells))
        faces.cell_data[_CAD_FACE_ID] = np.concatenate(face_ids)
        edges = pv.PolyData()
        if edge_cells:
            edges.points = points
            edges.lines = np.concatenate(edge_cells)
        self._cad_mesh_cache[key] = (faces, edges)
        return faces, edges

    def cad_face_mesh(self, part: CADPartNode, face_name: str) -> pv.PolyData | None:
        """Return one local CAD face only when a load or set query requests it."""
        key = (id(part), face_name)
        if key in self._local_cad_faces:
            return self._local_cad_faces[key]
        try:
            face_index = int(face_name.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return None
        mesh, _edges = self.cad_meshes(part)
        if _CAD_FACE_ID not in mesh.cell_data:
            return None
        cell_ids = np.flatnonzero(
            np.asarray(mesh.cell_data[_CAD_FACE_ID], dtype=np.int64) == face_index
        )
        if not len(cell_ids):
            return None
        face = mesh.extract_cells(cell_ids).extract_surface(algorithm="dataset_surface")
        self._local_cad_faces[key] = face
        return face

    def mesh_for_surface(
        self, component: FEAComponentNode, surface_name: str
    ) -> pv.DataSet | None:
        instance = component.instance
        name = instance.name if instance is not None else component.instance_name or ""
        face = _cad_face_name(surface_name)
        if face is not None and (name, face) in self._cad_face_meshes:
            return self._cad_face_meshes[(name, face)]
        part = self.problem.part_for_instance(instance or name)
        if part is None:
            part = next(
                (p for p in self.problem.parts() if p.assembly_name == name), None
            )
        if part is None:
            return None
        try:
            mesh = self.parts.adapter(part).surface(self, part, surface_name)
            if instance is None:
                instance = next(
                    (item for item in part.instances if item.name == name), None
                )
            mesh = (
                apply_instance_pose(
                    mesh,
                    instance,
                    self.values,
                )
                if mesh is not None and instance is not None
                else mesh
            )
            if face is not None and mesh is not None:
                self._cad_face_meshes[(name, face)] = mesh
            return mesh
        except (KeyError, ValueError, NotImplementedError):
            return None

    def node_set_center(self, instance_name: str, set_name: str) -> np.ndarray | None:
        part = self.problem.part_for_instance(instance_name)
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
            instance = next(
                (i for i in part.instances if i.name == instance_name), None
            )
            return (
                apply_instance_pose(point, instance, self.values).points[0]
                if instance
                else point.points[0]
            )
        except (KeyError, IndexError, ValueError, NotImplementedError):
            return None

    def mesh_for_set(self, part: PartNode, kind: str, name: str) -> pv.DataSet:
        """Extract an actual mesh set in Part coordinates, meshing only on demand."""
        from ..application.part_mesh import build_part_mesh

        model = self._part_cache.get(id(part))
        if model is None:
            model = self.parts.adapter(part).model_part(self, part)
        if model is None:
            model = self.cached_part(part, lambda: build_part_mesh(part, self.problem))
        if kind == "nodes":
            indices = np.asarray(model.set_nodes[name], dtype=int)
            return pv.PolyData(model.nodes.detach().cpu().numpy()[indices])
        if kind == "surfaces":
            return model.get_mesh(surf_name=name).clean()
        raise ValueError(f"Unknown mesh set kind: {kind}")

    def _draw_material_boxes(self) -> None:
        scene = self.scene
        for material in self.problem.material_nodes():
            if not isinstance(material, SIMPFieldMaterialNode):
                continue
            bounds = self.values.resolve(material.bounding_box)
            if not bounds or not any(bounds) or len(bounds) != 6:
                continue
            target = material.part
            instances = target.instances if target is not None else []
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
                    color=theme_manager.palette.viewer.geometry.material_region_color,
                    opacity=theme_manager.palette.viewer.geometry.material_region_opacity,
                )
                scene.add_mesh(
                    box,
                    name=f"{name}:fill",
                    color=theme_manager.palette.viewer.geometry.material_region_color,
                    opacity=theme_manager.palette.viewer.geometry.material_region_fill_opacity,
                )

    def _show_preview_message(self, message: str) -> None:
        self.scene.add_text(
            message,
            position="upper_left",
            color=theme_manager.palette.viewer.render.marker_color_annotation_error,
            font_size=theme_manager.palette.viewer.render.label_font_size,
        )

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
                for item in self.problem.parts()
                if item.name == object_name or item.assembly_name == object_name
            ),
            None,
        )
        if part is None:
            return None
        centers = [self.instance_center(instance.name) for instance in part.instances]
        centers = [item for item in centers if item is not None]
        return np.mean(centers, axis=0) if centers else None


def _cad_face_name(surface_name: str) -> str | None:
    """Map a CAD face or face node-set name to its face surface name."""
    import re

    match = re.match(r"(face_\d+)(?:_|$)", surface_name)
    return match.group(1) if match else None


def _inp_mesh_faces(
    model: torchfea.Part,
    mesh: pv.PolyData,
    part: INPPartNode,
    instance: InstanceNode | None,
) -> MeshFaces:
    """Map display triangles to original INP surface sets, including overlaps."""
    memberships: dict[tuple[int, ...], list[str]] = {}
    for name in model.surfaces.keys():
        if not model.surfaces.get_elements(name):
            continue
        triangles = model.surfaces.get_trimesh(name).detach().cpu().numpy()
        for triangle in np.sort(triangles, axis=1):
            memberships.setdefault(tuple(triangle), []).append(name)
    groups: dict[tuple[str, ...], int] = {}
    cell_groups = []
    for triangle in mesh.faces.reshape(-1, 4)[:, 1:]:
        names = tuple(dict.fromkeys(memberships.get(tuple(sorted(triangle)), ())))
        if not names:
            names = (part.exterior_surface or "extern",)
        if names not in groups:
            groups[names] = len(groups)
        cell_groups.append(groups[names])
    return MeshFaces(
        part.name,
        instance.name if instance else None,
        np.asarray(cell_groups, dtype=np.int64),
        tuple(groups),
    )


def _instance_color(index: int) -> str:
    if index < len(theme_manager.palette.viewer.geometry.instance_colors):
        return theme_manager.palette.viewer.geometry.instance_colors[index]
    hue = (
        (index - len(theme_manager.palette.viewer.geometry.instance_colors))
        * theme_manager.palette.viewer.geometry.extra_instance_hue_step
        + theme_manager.palette.viewer.geometry.extra_instance_hue_offset
    ) % 1.0
    red, green, blue = hsv_to_rgb(
        hue,
        theme_manager.palette.viewer.geometry.extra_instance_saturation,
        theme_manager.palette.viewer.geometry.extra_instance_value,
    )
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


def _surface_index_from_name(surface_name: str) -> int:
    """surface_1_All / surface_1_offset -> 1"""
    import re

    m = re.match(r"surface_(\d+)_", surface_name)
    return int(m.group(1)) if m else -1


def _boundary_end_surface(mesh: pv.DataSet, end: str) -> pv.DataSet:
    """Extract the actual cap cells used by a boundary-part end node set."""
    if not mesh.n_cells or not mesh.n_points:
        return mesh
    cap_cells = _boundary_end_cells(mesh, end)
    if not np.any(cap_cells):
        return mesh
    return mesh.extract_cells(cap_cells).extract_surface(algorithm="dataset_surface")


def _boundary_end_cells(mesh: pv.DataSet, end: str) -> np.ndarray:
    """Identify cap cells in local coordinates for set queries and picking."""
    if not mesh.n_cells or not mesh.n_points:
        return np.zeros(mesh.n_cells, dtype=bool)
    centers = mesh.cell_centers().points
    bounds = mesh.bounds
    target = bounds[5] if end == "Head" else bounds[4]
    tolerance = max(
        (bounds[5] - bounds[4])
        * theme_manager.palette.viewer.geometry.boundary_relative_tolerance,
        theme_manager.palette.viewer.geometry.boundary_absolute_tolerance,
    )
    return np.abs(centers[:, 2] - target) <= tolerance


def _preview_node_set_points(
    part: PartNode, set_name: str, points: np.ndarray
) -> np.ndarray:
    """Approximate a named boundary node set from its preview surface."""
    if part.type not in {"BoundaryPart", "OffsetBoundaryPart"}:
        return points
    suffix = set_name.rsplit("_", 1)[-1]
    if suffix not in {"Head", "Bottom"}:
        return points
    z = points[:, 2]
    target = float(z.max() if suffix == "Head" else z.min())
    tolerance = max(
        float(np.ptp(points, axis=0).max())
        * theme_manager.palette.viewer.geometry.boundary_relative_tolerance,
        theme_manager.palette.viewer.geometry.boundary_absolute_tolerance,
    )
    return points[np.abs(z - target) <= tolerance]


class InitialDesignGeometry:
    """Prepared isometric triangles and outlines; painting contains no geometry work."""

    horizontal = np.array([1.0, -1.0, 0.0]) / np.sqrt(2)
    vertical = np.array([1.0, 1.0, -2.0]) / np.sqrt(6)
    depth = np.array([1.0, 1.0, 1.0]) / np.sqrt(3)

    def __init__(self, options):
        if options.method == "shapeopt":
            meshes = _layered_chamber_preview_meshes(options.geometry_layout())
        else:
            meshes = {
                "body": BoxPreviewAdapter.mesh(
                    length=options.length,
                    height=options.height,
                    depth=options.depth,
                )
            }
        palette = theme_manager.palette.quickstart_preview.cavities
        self.triangles = []
        self.lines = []
        for name, mesh in meshes.items():
            mesh = mesh.triangulate()
            xyz = mesh.points[mesh.faces.reshape(-1, 4)[:, 1:]]
            normals = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
            light_direction = np.asarray(
                deepcopy(theme_manager.palette.quickstart_preview.light_direction),
                dtype=float,
            )
            normal_length = np.maximum(
                np.linalg.norm(normals, axis=1),
                theme_manager.palette.quickstart_preview.surface_normal_tolerance,
            )
            light = theme_manager.palette.quickstart_preview.light_ambient + (
                theme_manager.palette.quickstart_preview.light_contrast
                * np.abs(normals @ light_direction)
                / (normal_length * np.linalg.norm(light_direction))
            )
            color = (
                theme_manager.palette.quickstart_preview.body
                if name == "body"
                else palette[int(name.split(":")[0].split("-")[1]) % len(palette)]
            )
            alpha = (
                theme_manager.palette.quickstart_preview.body_transparency_alpha
                if name == "body" and options.method == "shapeopt"
                else theme_manager.palette.quickstart_preview.opaque_alpha
            )
            for points, brightness in zip(xyz, light):
                self.triangles.append(
                    (
                        float(points.mean(axis=0) @ self.depth),
                        self.coordinates(points),
                        color,
                        int(
                            theme_manager.palette.quickstart_preview.light_intensity
                            * brightness
                        ),
                        alpha,
                    )
                )
        self.triangles.sort(key=lambda item: item[0])
        vertices = np.concatenate([mesh.points for mesh in meshes.values()])
        projected = self.coordinates(vertices)
        self.lower, self.upper = projected.min(axis=0), projected.max(axis=0)
        if options.method == "shapeopt":
            for sign in (-1.0, 1.0):
                xy = sign * options.radius * self.horizontal[:2]
                self.lines.append(
                    self.coordinates(
                        np.array([[*xy, 0.0], [*xy, options.total_length]])
                    )
                )
            angles = np.linspace(
                0.0,
                2 * np.pi,
                theme_manager.palette.quickstart_preview.outline_circle_samples,
            )
            for z in (0.0, options.total_length):
                self.lines.append(
                    self.coordinates(
                        np.column_stack(
                            (
                                options.radius * np.cos(angles),
                                options.radius * np.sin(angles),
                                np.full_like(
                                    angles,
                                    z,
                                ),
                            )
                        )
                    )
                )

    @classmethod
    def coordinates(cls, points: np.ndarray) -> np.ndarray:
        return np.column_stack((points @ cls.horizontal, points @ cls.vertical))

    def transform(self, width: int, height: int) -> tuple[float, np.ndarray]:
        span = np.maximum(
            self.upper - self.lower,
            theme_manager.palette.quickstart_preview.minimum_projected_span,
        )
        scale = min(
            (width - theme_manager.palette.quickstart_preview.horizontal_margin)
            / span[0],
            (height - theme_manager.palette.quickstart_preview.vertical_margin)
            / span[1],
        )
        return scale, np.array([width / 2, height / 2]) - scale * (
            self.lower + self.upper
        ) / 2


def _layered_chamber_preview_meshes(layout) -> dict[str, pv.PolyData]:
    """Build Quickstart-only preview meshes using the active theme's quality."""
    style = theme_manager.palette.quickstart_preview
    meshes = {
        "body": pv.Cylinder(
            center=[0.0, 0.0, layout.length / 2],
            direction=[0.0, 0.0, 1.0],
            radius=layout.body_radius,
            height=layout.length,
            resolution=style.body_resolution,
        )
    }
    for index, cavity in enumerate(layout.cavity_specs()):
        center = [cavity.x, cavity.y, cavity.z + cavity.length / 2]
        meshes[f"layer-{cavity.layer}:cavity-{index}"] = (
            pv.Sphere(
                center=center,
                radius=cavity.radius,
                theta_resolution=style.sphere_theta_resolution,
                phi_resolution=style.sphere_phi_resolution,
            )
            if cavity.shape == "sphere"
            else pv.Cylinder(
                center=center,
                direction=[0.0, 0.0, 1.0],
                radius=cavity.radius,
                height=cavity.length,
                resolution=style.cavity_cylinder_resolution,
            )
        )
    return meshes
