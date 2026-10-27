"""Closed CAD boundaries with named topology, sets and selected NURBS faces."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

import gmsh
import numpy as np
import pyvista as pv
import torch
from torchfea import cad

from ...optcore.modelparams.parts.cad_part import CADMeshingMixin
from .base_surface import BaseSurface
from .nurbs_face import NURBSFace, read_nurbs_faces, write_nurbs_faces

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

    import torchfea
    from torchfea.cad import BREPEdge, BREPFace, BREPTopology, BREPVertex
    from torchfea.cad.builder import OCCBuilder
    from vtkmodules.vtkRenderingCore import vtkCellPicker


class BREPSurface(BaseSurface):
    """One closed shell, its face/edge/vertex graph and named selections.

    STEP contains the geometry. ``.brep.json`` stores face/edge/vertex
    identities and named sets.
    Topology inspection does not generate a display or finite-element mesh.
    """

    def __init__(
        self, path_step: str | Path,
        control_point_spacing: float | None = None,
    ) -> None:
        super().__init__()
        if control_point_spacing is not None:
            if isinstance(control_point_spacing, bool) or not np.isscalar(control_point_spacing):
                raise ValueError("control_point_spacing must be a finite positive length.")
            control_point_spacing = float(control_point_spacing)
            if not np.isfinite(control_point_spacing) or control_point_spacing <= 0:
                raise ValueError("control_point_spacing must be a finite positive length.")
        self.control_point_spacing = control_point_spacing
        self.path_step = Path(path_step).resolve()
        self._geometry_path = self.path_step
        metadata_path = self.path_step.with_suffix(".brep.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        self._face_map: dict[str, list[float]] = metadata.get("face_map", {})
        self._has_named_faces = bool(self._face_map)
        self._edge_map: dict[str, list[float]] = metadata.get("edge_map", {})
        self._vertex_map: dict[str, list[float]] = metadata.get("vertex_map", {})
        self.surface_sets: dict[str, tuple[str, ...]] = {
            name: tuple(members) for name, members in metadata.get("surface_sets", {}).items()
        }
        self.node_sets: dict[str, tuple[str, ...]] = {
            name: tuple(members) for name, members in metadata.get("node_sets", {}).items()
        }
        self._nurbs_faces: set[str] = set()
        self._design_faces: tuple[str, ...] = ()
        self._topology: BREPTopology | None = None
        self._loaded_topology: BREPTopology | None = None
        self._bound_face_names: dict[str, str] = {}
        self._nurbs_models: dict[str, NURBSFace] | None = None
        self._models_refined: set[str] = set()
        self._mesh_set_prefix: str | None = None
        self._point_weights: dict[str, torch.Tensor] = {}

    @property
    def topology(self) -> BREPTopology:
        """Named topology of the current geometry, inspected lazily."""
        if self._topology is None:
            with cad.occ_session("morphopt_brep_topology") as context:
                self._build_geometry(context)
        return self._topology

    @property
    def faces(self) -> Mapping[str, BREPFace]:
        return self.topology.faces

    @property
    def edges(self) -> Mapping[str, BREPEdge]:
        return self.topology.edges

    @property
    def vertices(self) -> Mapping[str, BREPVertex]:
        return self.topology.vertices

    @property
    def face_names(self) -> tuple[str, ...]:
        return tuple(self.faces)

    @property
    def nurbs_faces(self) -> Mapping[str, NURBSFace]:
        """Per-face bspmap models with differentiable control-point tensors."""
        if self._nurbs_models is None:
            if not any(face.is_nurbs for face in self.faces.values()):
                self._nurbs_models = {}
                return self._nurbs_models
            with TemporaryDirectory(prefix="morphopt_nurbs_") as directory:
                path = Path(directory) / "geometry.brep"
                probes = self._write_nurbs_source(path)
                self._nurbs_models = read_nurbs_faces(path, probes)
        if self.is_updatable:
            for name in self._design_names(self._nurbs_models):
                if name in self._models_refined:
                    continue
                model = self._nurbs_models[name]
                if self.control_point_spacing is not None:
                    self._nurbs_models[name] = model.refine_by_spacing(self.control_point_spacing)
                self._models_refined.add(name)
        return self._nurbs_models

    def _design_names(self, models: Mapping[str, NURBSFace]) -> tuple[str, ...]:
        names = self._design_faces
        missing = set(names) - models.keys()
        if missing:
            raise ValueError(f"Design faces are not NURBS: {', '.join(sorted(missing))}")
        return names

    @property
    def design_faces(self) -> Mapping[str, NURBSFace]:
        """NURBS faces whose poles enter this surface's design vector."""
        models = self.nurbs_faces
        return {name: models[name] for name in self._design_names(models)}

    def select_design_faces(self, faces: str | Sequence[str]) -> None:
        """Restrict shape updates to specified logical NURBS faces."""
        names = (faces,) if isinstance(faces, str) else tuple(dict.fromkeys(faces))
        missing = {name for name in names if name not in self.faces or not self.faces[name].is_nurbs}
        if missing:
            raise ValueError(f"Design faces are not NURBS: {', '.join(sorted(missing))}")
        self._design_faces = names

    @property
    def num_variables(self) -> int:
        """Number of Cartesian pole coordinates on selected NURBS faces."""
        if not self.is_updatable:
            return 0
        models = self.design_faces
        if not models:
            raise ValueError("BREP shape updating requires select_design_faces() with at least one NURBS face.")
        return sum(model.num_variables for model in models.values())

    @property
    def control_points(self) -> torch.Tensor:
        """Concatenate per-face poles in stable logical-name order."""
        models = self.design_faces
        return torch.cat([model.control_points for model in models.values()]) if models else torch.empty((0, 3))

    def get_surface_parameters(self) -> torch.Tensor:
        """Return the active faces' flattened Cartesian pole coordinates."""
        return self.control_points.flatten() if self.is_updatable else torch.empty(0)

    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """Distribute optimizer variables to each face, retaining fixed trims."""
        values = x.reshape(-1)
        if values.numel() != self.num_variables:
            raise ValueError("BREP design-variable count does not match selected face poles.")
        start = 0
        for model in self.design_faces.values():
            stop = start + model.num_variables
            model.set_surface_parameters(values[start:stop])
            start = stop

    def update_variables(self, x_change: torch.Tensor) -> None:
        """Apply a shape-updater step to the active face poles."""
        if self.is_updatable:
            self.set_surface_parameters(self.get_surface_parameters() + x_change.reshape(-1))

    def save(self, filename: str) -> None:
        """Archive the selected faces' poles for this optimization iteration."""
        np.savez(filename, **{
            name: model.control_points.detach().cpu().numpy()
            for name, model in self.design_faces.items()
        })

    def load(self, filename: str) -> None:
        """Restore archived poles using the current trim constraints."""
        with np.load(filename + ".npz") as archive:
            if set(archive.files) != set(self.design_faces):
                raise ValueError("Archived BREP faces do not match the current Part.")
            for name, model in self.design_faces.items():
                model.set_surface_parameters(torch.as_tensor(
                    archive[name], dtype=model.control_points.dtype,
                    device=model.control_points.device,
                ))

    def _write_nurbs_source(self, path: Path) -> dict[str, np.ndarray]:
        """Export current OCC shape and interior probes for logical face matching."""
        probes: dict[str, np.ndarray] = {}
        with cad.occ_session("morphopt_nurbs_supports") as context:
            self._build_geometry(context)
            for name, face in self.faces.items():
                if not face.is_nurbs:
                    continue
                tag = self.topology.face_tags[name]
                u, v = np.meshgrid(*(np.linspace(*bounds, 13)[1:-1]
                                     for bounds in face.parameter_bounds))
                uv = np.column_stack((u.ravel(), v.ravel()))
                inside = [bool(gmsh.model.isInside(2, tag, point, parametric=True)) for point in uv]
                valid = uv[inside]
                if not len(valid):
                    raise ValueError(f"Cannot sample trimmed NURBS face {name}.")
                selected = valid[np.linspace(0, len(valid) - 1, min(7, len(valid)), dtype=int)]
                probes[name] = np.asarray(gmsh.model.getValue(2, tag, selected.ravel())).reshape(-1, 3)
            gmsh.write(str(path))
        return probes

    def _capture_topology(self, topology: BREPTopology) -> None:
        self._topology = topology
        # These maps identify the source asset, whose analytic representation
        # can differ from the converted topology retained above.
        if not self._face_map:
            self._face_map = {name: list(face.signature) for name, face in topology.faces.items()}
        if not self._edge_map:
            self._edge_map = {name: list(edge.signature) for name, edge in topology.edges.items()}
        if not self._vertex_map:
            self._vertex_map = {name: list(vertex.coordinates) for name, vertex in topology.vertices.items()}

    def _read_topology(self, tags: Sequence[int]) -> BREPTopology:
        return cad.read_brep_topology(tags, self._face_map, self._edge_map, self._vertex_map)

    def _build_geometry(self, context: OCCBuilder) -> list[tuple[int, int]]:
        """Import, convert selected detached faces and rebuild their closed shell."""
        entities = context.occ.importShapes(str(self.path_step))
        context.occ.synchronize()
        volumes = [(dim, tag) for dim, tag in entities if dim == 3]
        if len(volumes) != 1:
            raise ValueError("BREPSurface requires one closed shell stored as a STEP solid.")
        shells, _ = context.occ.getSurfaceLoops(volumes[0][1])
        if len(shells) != 1:
            raise ValueError("Register each closed shell as a separate BREPSurface.")
        tags = sorted(tag for _, tag in gmsh.model.getBoundary(volumes, oriented=False, recursive=False))
        topology = self._read_topology(tags)
        self._capture_topology(topology)
        if self._nurbs_faces:
            missing = self._nurbs_faces - topology.faces.keys()
            if missing:
                raise ValueError(f"Unknown NURBS faces: {', '.join(sorted(missing))}")
            selected = [topology.face_tags[name] for name in topology.faces
                        if name in self._nurbs_faces and not topology.faces[name].is_nurbs]
            if not selected:
                return volumes
            context.occ.remove(volumes, recursive=False)
            context.occ.synchronize()
            replacements = dict(zip(selected, cad.convert_faces_to_nurbs(selected), strict=True))
            converted = [replacements.get(tag, tag) for tag in tags]
            loop = context.occ.addSurfaceLoop(converted, sewing=True)
            volume = context.occ.addVolume([loop])
            context.occ.synchronize()
            cad.remove_unused_brep_entities(volume)
            volumes = [(3, volume)]
            tags = sorted(tag for _, tag in gmsh.model.getBoundary(volumes, oriented=False, recursive=False))
            # Conversion preserves geometry; names are recovered after sewing
            # without depending on the new session's entity ordering.
            topology = cad.read_brep_topology(
                tags,
                edge_map={name: edge.signature for name, edge in topology.edges.items()},
                vertex_map={name: vertex.coordinates for name, vertex in topology.vertices.items()},
                face_loops={name: face.loops for name, face in topology.faces.items()},
            )
            for name in self._nurbs_faces:
                if not topology.faces[name].is_nurbs:
                    raise ValueError(f"Reassembled face {name} is not a NURBS surface.")
        self._capture_topology(topology)
        return volumes

    def convert_faces_to_nurbs(self, faces: str | Sequence[str]) -> BREPSurface:
        """Convert selected logical faces and retain their original names."""
        names = (faces,) if isinstance(faces, str) else tuple(faces)
        missing = set(names) - self.faces.keys()
        if missing:
            raise ValueError(f"Unknown faces: {', '.join(sorted(missing))}")
        previous = self._nurbs_faces.copy()
        self._nurbs_faces.update(names)
        self._topology = None
        try:
            self.topology
        except Exception:
            self._nurbs_faces = previous
            self._topology = None
            raise
        self.__dict__.pop("_fixed_triangles", None)
        self._nurbs_models = None
        self._models_refined.clear()
        return self

    def add_surface_set(self, name: str, faces: str | Sequence[str]) -> BREPSurface:
        """Register a union of logical faces for surface loads or contact."""
        members = (faces,) if isinstance(faces, str) else tuple(dict.fromkeys(faces))
        if not name.strip() or name == "All" or name in self.faces:
            raise ValueError(f"Invalid or reserved BREP surface set name: {name!r}")
        if not members or set(members) - self.faces.keys():
            raise ValueError(f"Surface set {name!r} must select existing faces.")
        self.surface_sets[name] = members
        return self

    def add_node_set(self, name: str, entities: str | Sequence[str]) -> BREPSurface:
        """Register nodes on named faces, edges or vertices."""
        members = (entities,) if isinstance(entities, str) else tuple(dict.fromkeys(entities))
        available = self.faces.keys() | self.edges.keys() | self.vertices.keys()
        if not name.strip() or name == "All" or name in available:
            raise ValueError(f"Invalid or reserved BREP node set name: {name!r}")
        if not members or set(members) - available:
            raise ValueError(f"Node set {name!r} must select existing topology.")
        self.node_sets[name] = members
        return self

    def metadata(self) -> dict[str, Any]:
        """Persistent topology identities and selections, independent of OCC tags."""
        self.topology
        return {
            "face_map": self._face_map,
            "edge_map": self._edge_map, "vertex_map": self._vertex_map,
            "surface_sets": {name: list(members) for name, members in self.surface_sets.items()},
            "node_sets": {name: list(members) for name, members in self.node_sets.items()},
        }

    def evaluate_face(self, name: str, uv: np.ndarray) -> np.ndarray:
        """Evaluate the supporting surface at an ``(N, 2)`` parameter array."""
        parameters = np.asarray(uv, dtype=float).reshape(-1, 2)
        with cad.occ_session("morphopt_brep_face_values") as context:
            self._build_geometry(context)
            tag = self.topology.face_tags[name]
            return np.asarray(gmsh.model.getValue(2, tag, parameters.ravel())).reshape(-1, 3)

    def evaluate_edge(self, name: str, parameters: np.ndarray) -> np.ndarray:
        """Evaluate a named edge's three-dimensional curve."""
        values = np.asarray(parameters, dtype=float).reshape(-1)
        with cad.occ_session("morphopt_brep_edge_values") as context:
            self._build_geometry(context)
            tag = self.topology.edge_tags[name]
            return np.asarray(gmsh.model.getValue(1, tag, values)).reshape(-1, 3)

    def contains_face_parameters(self, name: str, uv: np.ndarray) -> np.ndarray:
        """Classify UV points against the face's outer wire and hole wires."""
        parameters = np.asarray(uv, dtype=float).reshape(-1, 2)
        with cad.occ_session("morphopt_brep_face_domain") as context:
            self._build_geometry(context)
            tag = self.topology.face_tags[name]
            return np.asarray([
                bool(gmsh.model.isInside(2, tag, point, parametric=True))
                for point in parameters
            ], dtype=bool)

    def edge_parameters_on_face(
        self, face: str, edge: str, parameters: np.ndarray, which: int = 0,
    ) -> np.ndarray:
        """Return the edge's UV coordinates; ``which`` selects a seam branch."""
        values = np.asarray(parameters, dtype=float).reshape(-1)
        with cad.occ_session("morphopt_brep_edge_parameters") as context:
            self._build_geometry(context)
            if face not in self.edges[edge].faces:
                raise ValueError(f"Edge {edge} does not bound face {face}.")
            return np.asarray(gmsh.model.reparametrizeOnSurface(
                1, self.topology.edge_tags[edge], values,
                self.topology.face_tags[face], which=which,
            )).reshape(-1, 2)

    def export_step(self, path: str | Path) -> Path:
        """Export the current solid and its topology metadata without meshing."""
        destination = Path(path).resolve()
        if destination.suffix.lower() not in {".stp", ".step"}:
            raise ValueError("STEP export requires a .stp or .step filename.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        original_loops = {name: face.loops for name, face in self.faces.items()}
        if self._nurbs_models:
            with TemporaryDirectory(prefix="morphopt_nurbs_export_") as directory:
                source = Path(directory) / "geometry.brep"
                probes = self._write_nurbs_source(source)
                write_nurbs_faces(source, destination, probes, self._nurbs_models)
        else:
            with cad.occ_session("morphopt_brep_export") as context:
                self._build_geometry(context)
                gmsh.write(str(destination))
        with cad.occ_session("morphopt_brep_export_check") as context:
            entities = context.occ.importShapes(str(destination))
            context.occ.synchronize()
            volumes = [(dim, tag) for dim, tag in entities if dim == 3]
            if len(volumes) != 1:
                raise ValueError("Updated STEP must contain one closed solid.")
            tags = [tag for _, tag in gmsh.model.getBoundary(volumes, oriented=False)]
            topology = cad.read_brep_topology(
                tags, edge_map=self._edge_map, vertex_map=self._vertex_map,
                face_loops=original_loops,
            )
        face_map = {name: list(face.signature) for name, face in topology.faces.items()}
        metadata = {**self.metadata(), "face_map": face_map}
        destination.with_suffix(".brep.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return destination

    def prepare_geometry(
        self, path_output: str | Path, name_output: str,
        flip: bool = False, pools: Pool | None = None,
    ) -> None:
        """Materialize converted geometry before entering the Part mesh session."""
        self._geometry_path = (
            self.export_step(Path(path_output) / f"{name_output}.stp")
            if self._nurbs_faces or self._nurbs_models or (self.is_updatable and self.nurbs_faces)
            else self.path_step
        )

    def output_data(
        self, path_output: str | Path, name_output: str, seed_size: float = -1,
        flip: bool = False, pools: Pool | None = None,
    ) -> str:
        return self.export_step(Path(path_output) / f"{name_output}.stp").name

    def load_geometry(self, part: CADMeshingMixin, context: OCCBuilder) -> list[int]:
        """Bind topology names to this Part's active OCC and finite-element model."""
        tags = part.load_step_boundary(self._geometry_path, context)
        prepared_map = self._geometry_path.with_suffix(".brep.json")
        face_map = (json.loads(prepared_map.read_text(encoding="utf-8"))["face_map"]
                    if self._geometry_path != self.path_step else self._face_map)
        topology = cad.read_brep_topology(tags, face_map, self._edge_map, self._vertex_map)
        if self._has_named_faces or not part._face_names:
            conflicts = topology.faces.keys() & set(part._face_names.values())
            if conflicts:
                raise ValueError(f"Duplicate STEP face names: {', '.join(sorted(conflicts))}")
            part._face_names.update({tag: name for name, tag in topology.face_tags.items()})
        else:
            part._complete_face_names(tags)
        self._bound_face_names = {name: part._face_names[tag] for name, tag in topology.face_tags.items()}
        self._loaded_topology = topology
        self._capture_topology(topology)
        return tags

    def define_mesh_sets(self, part: torchfea.Part, prefix: str) -> None:
        """Map face unions and edge/vertex selections onto the generated FE mesh."""
        topology = self._loaded_topology
        if topology is None:
            raise RuntimeError("BREP topology must be loaded before defining mesh sets.")
        self._mesh_set_prefix = prefix

        def add_nodes(name: str, values: Sequence[np.ndarray]) -> None:
            if name in part.set_nodes:
                raise ValueError(f"Duplicate BREP node set: {name}")
            part.add_node_set(name, np.unique(np.concatenate(values)).astype(int))

        def surface_set(name: str, members: Sequence[str]) -> None:
            if name in part.surfaces:
                raise ValueError(f"Duplicate BREP surface set: {name}")
            sides: dict[int, list[np.ndarray]] = defaultdict(list)
            for member in members:
                for ids, side in part.surfaces[self._bound_face_names[member]]:
                    sides[side].append(ids)
            part.add_surface_set(name, [(np.unique(np.concatenate(ids)), side) for side, ids in sides.items()])
            add_nodes(name + "_nodes", [part._gmsh_surface_nodes[topology.face_tags[member]] for member in members])

        for name in topology.faces:
            surface_set(f"{prefix}_{name}", (name,))
        for name, members in self.surface_sets.items():
            surface_set(f"{prefix}_{name}", members)
        nodes = {
            **{name: part._gmsh_surface_nodes[tag] for name, tag in topology.face_tags.items()},
            **{name: part._gmsh_curve_nodes[tag] for name, tag in topology.edge_tags.items()},
            **{name: part._gmsh_vertex_nodes.get(tag, np.empty(0, dtype=int)) for name, tag in topology.vertex_tags.items()},
        }
        for name in (*topology.edges, *topology.vertices):
            add_nodes(f"{prefix}_{name}", [nodes[name]])
        for name, members in self.node_sets.items():
            add_nodes(f"{prefix}_{name}", [nodes[member] for member in members])

    def bind_mesh(self, part: torchfea.Part) -> None:
        """Match every final FE face node, including quadratic and shared nodes."""
        models = self.nurbs_faces
        design_names = set(self.design_faces) if self.is_updatable else set()
        if not models:
            return
        if self._mesh_set_prefix is None:
            raise RuntimeError("Define BREP mesh sets before binding nodes.")
        prefix = self._mesh_set_prefix
        coordinates = part.nodes.detach().cpu().numpy()
        updates: dict[int, np.ndarray] = {}
        with cad.occ_session("morphopt_nurbs_mesh_binding") as context:
            entities = context.occ.importShapes(str(self._geometry_path))
            context.occ.synchronize()
            volumes = [(dim, tag) for dim, tag in entities if dim == 3]
            if len(volumes) != 1:
                raise ValueError("BREP mesh binding requires one closed solid.")
            tags = [tag for _, tag in gmsh.model.getBoundary(volumes, oriented=False)]
            prepared_map = self._geometry_path.with_suffix(".brep.json")
            face_map = (json.loads(prepared_map.read_text(encoding="utf-8"))["face_map"]
                        if prepared_map.exists() else self._face_map)
            active = cad.read_brep_topology(tags, face_map, self._edge_map, self._vertex_map)
            for name, model in models.items():
                indices = np.asarray(part.set_nodes[f"{prefix}_{name}_nodes"], dtype=np.int64)
                nodes = coordinates[indices]
                tag = active.face_tags[name]
                projected, _ = gmsh.model.getClosestPoint(2, tag, nodes.ravel())
                projected = np.asarray(projected).reshape(-1, 3)
                uv = np.asarray(gmsh.model.getParametrization(2, tag, projected.ravel())).reshape(-1, 2)
                # Quadratic edge nodes begin as chord midpoints. Project them
                # onto their CAD edge before assigning the face parameter.
                for edge_name, edge in active.edges.items():
                    if name not in edge.faces:
                        continue
                    on_edge = np.isin(indices, part.set_nodes[f"{prefix}_{edge_name}"])
                    if not on_edge.any():
                        continue
                    edge_tag = active.edge_tags[edge_name]
                    points, _ = gmsh.model.getClosestPoint(1, edge_tag, nodes[on_edge].ravel())
                    parameters = gmsh.model.getParametrization(1, edge_tag, points)
                    projected[on_edge] = np.asarray(points).reshape(-1, 3)
                    uv[on_edge] = np.asarray(gmsh.model.reparametrizeOnSurface(
                        1, edge_tag, parameters, tag,
                    )).reshape(-1, 2)
                matched = model.match_coordinates(indices, projected, initial_uv=uv)
                if np.max(np.linalg.norm(matched - projected, axis=1), initial=0) > 1e-7:
                    raise ValueError(f"NURBS basis does not reproduce CAD nodes of {name}.")
                if not all(gmsh.model.isInside(2, tag, point, parametric=True) for point in model.surf_node_uv):
                    raise ValueError(f"Matched UV leaves the trimmed domain of {name}.")
                model.projection_errors = np.linalg.norm(matched - nodes, axis=1)
                if name in design_names:
                    fixed = np.zeros(model.size[0] * model.size[1], dtype=bool)
                    for edge_name, edge in active.edges.items():
                        if name not in edge.faces:
                            continue
                        edge_tag = active.edge_tags[edge_name]
                        parameters = np.linspace(*edge.parameter_bounds, 65)
                        edge_uv = np.asarray(gmsh.model.reparametrizeOnSurface(
                            1, edge_tag, parameters, tag,
                        )).reshape(-1, 2)
                        edge_uv = np.clip(edge_uv, model.parameter_bounds[:, 0],
                                          model.parameter_bounds[:, 1])
                        weights, poles = model.get_weights(edge_uv)
                        fixed[poles[np.abs(weights) > 1e-10]] = True
                    # A periodic CAD support may describe the same seam with
                    # two UV branches. Freeze both parameter-domain borders.
                    (u0, u1), (v0, v1) = model.parameter_bounds
                    samples_u = np.linspace(u0, u1, 65)
                    samples_v = np.linspace(v0, v1, 65)
                    border_uv = np.concatenate((
                        np.column_stack((np.full(65, u0), samples_v)),
                        np.column_stack((np.full(65, u1), samples_v)),
                        np.column_stack((samples_u, np.full(65, v0))),
                        np.column_stack((samples_u, np.full(65, v1))),
                    ))
                    weights, poles = model.get_weights(border_uv)
                    fixed[poles[np.abs(weights) > 1e-10]] = True
                    model.set_design_mask(~fixed)
                for index, point in zip(indices, matched, strict=True):
                    if int(index) in updates and not np.allclose(updates[int(index)], point, rtol=0, atol=1e-7):
                        raise ValueError(f"Shared node {index} has inconsistent NURBS face positions.")
                    updates[int(index)] = point
        if self.is_updatable and not any(
            models[name].design_mask is not None and models[name].design_mask.any()
            for name in design_names
        ):
            raise ValueError("Selected BREP faces have no movable interior poles after fixing trim edges.")
        if updates:
            indices = np.fromiter(updates, dtype=np.int64)
            part.nodes[indices] = torch.as_tensor(np.array(list(updates.values())),
                                                dtype=part.nodes.dtype, device=part.nodes.device)
        self._point_weights = {}
        element = part.elems["C3D4"]
        for name, model in models.items():
            position = {int(index): offset for offset, index in enumerate(model.surf_node_idx)}
            weights = torch.zeros(len(position), dtype=part.nodes.dtype, device=part.nodes.device)
            for element_ids, side in part.surfaces[f"{prefix}_{name}"]:
                faces = element._elems[element_ids][:, element.surfaceid_map[int(side)]]
                for face_nodes in faces:
                    xyz = part.nodes[face_nodes[:3]]
                    area = torch.linalg.cross(xyz[1] - xyz[0], xyz[2] - xyz[0]).norm() / 2
                    for index in face_nodes:
                        weights[position[int(index)]] += area.detach() / len(face_nodes)
            self._point_weights[name] = weights

    def map_face_nodes(self, name: str) -> torch.Tensor:
        """Evaluate bound FE nodes with gradients to this face's control points."""
        model = self.nurbs_faces[name]
        return model.map_bound_nodes()

    @property
    def uses_facewise_binding(self) -> bool:
        return True

    def map_design_nodes(self) -> tuple[np.ndarray, torch.Tensor]:
        """Merge per-face coordinates; shared nodes must remain coincident."""
        positions: dict[int, torch.Tensor] = {}
        for name, model in self.design_faces.items():
            mapped = self.map_face_nodes(name)
            for index, point in zip(model.surf_node_idx, mapped, strict=True):
                key = int(index)
                if key in positions:
                    if not torch.allclose(positions[key].detach(), point.detach(), atol=1e-7, rtol=0):
                        raise ValueError(f"Shared BREP node {key} separates across NURBS faces.")
                else:
                    positions[key] = point
        return np.fromiter(positions, dtype=np.int64), torch.stack(list(positions.values()))

    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Evaluate mapped points and first/second derivatives on active faces."""
        if not self.is_updatable:
            return super().get_geometry_values()
        values = []
        tangents = []
        curvatures = []
        for model in self.design_faces.values():
            values.append(model.map_bound_nodes())
            du, dv = model.map_bound_nodes((1, 0)), model.map_bound_nodes((0, 1))
            duu = model.map_bound_nodes((2, 0))
            duv = model.map_bound_nodes((1, 1))
            dvv = model.map_bound_nodes((0, 2))
            tangents.append(torch.stack((du if self.flip else -du, dv), dim=2))
            curvatures.append(torch.stack((torch.stack((duu, duv if self.flip else -duv), dim=2),
                                           torch.stack((duv if self.flip else -duv, dvv), dim=2)), dim=2))
        return torch.cat(values), torch.cat(tangents), torch.cat(curvatures)

    def get_points_weight(self) -> torch.Tensor:
        """Return boundary element area distributed to each mapped node."""
        if not self.is_updatable:
            return super().get_points_weight()
        if not set(self.design_faces) <= set(self._point_weights):
            raise RuntimeError("Build the BREP mesh before requesting nodal area weights.")
        return torch.cat([self._point_weights[name] for name in self.design_faces])

    def show(self, plotter: pv.Plotter | None = None) -> pv.Plotter:
        """Show logical face names on click and highlight the selected face.

        With a supplied plotter, configure the scene without opening a window;
        the caller then owns rendering and the window lifecycle.
        """
        open_window = plotter is None
        if plotter is None:
            plotter = pv.Plotter(title="BREPSurface faces")
        mesh = self.get_mesh()
        actor = plotter.add_mesh(mesh, color="lightsteelblue", show_edges=False,
                                 name="brep_geometry", pickable=True)
        prompt = "Click a face to inspect its name; click the background to clear."
        label = plotter.add_text(prompt, position="lower_left", font_size=12,
                                 name="brep_face_name")

        def select_face(_point: Sequence[float], picker: vtkCellPicker) -> None:
            plotter.remove_actor("brep_face_selection", render=False)
            cell = picker.GetCellId()
            if picker.GetActor() != actor or cell < 0:
                label.SetText(0, prompt)
            else:
                face = int(mesh.cell_data["face_index"][cell])
                selected = mesh.extract_cells(np.flatnonzero(mesh.cell_data["face_index"] == face))
                plotter.add_mesh(selected, color="gold", lighting=False,
                                 name="brep_face_selection", pickable=False,
                                 reset_camera=False, render=False)
                label.SetText(0, f"face_{face}")
            plotter.render()

        plotter.enable_surface_point_picking(
            callback=select_face, picker="cell", use_picker=True,
            left_clicking=True, pickable_window=True, show_point=False,
            show_message=False, tolerance=0.001,
        )
        plotter.add_axes()
        plotter.reset_camera()
        if open_window:
            plotter.show()
        return plotter

    def get_mesh(self) -> pv.PolyData:
        """Tessellate current geometry and retain original logical face indices."""
        names: dict[int, str] = {}
        with TemporaryDirectory(prefix="morphopt_brep_preview_") as directory:
            current = Path(directory) / "current.stp"
            if self._nurbs_models:
                self.export_step(current)

            def preview(context: OCCBuilder) -> list[tuple[int, int]]:
                if self._nurbs_models:
                    volumes = context.occ.importShapes(str(current))
                    context.occ.synchronize()
                    tags = [tag for _, tag in gmsh.model.getBoundary(volumes, oriented=False)]
                    mapping = json.loads(current.with_suffix(".brep.json").read_text(encoding="utf-8"))["face_map"]
                    topology = cad.read_brep_topology(tags, mapping, self._edge_map, self._vertex_map)
                else:
                    volumes = self._build_geometry(context)
                    topology = self.topology
                names.update({tag: name for name, tag in topology.face_tags.items()})
                return volumes

            records = cad.preview_brep([CADMeshingMixin._Operation("brep_preview", preview)])
        triangles = np.concatenate([record["triangles"] for record in records])
        nodes, local = np.unique(triangles, return_inverse=True)
        cells = np.column_stack((np.full(len(triangles), 3), local.reshape(-1, 3)))
        mesh = pv.PolyData(np.asarray(records[0]["points"])[nodes], cells)
        mesh.cell_data["face_index"] = np.concatenate([
            np.full(len(record["triangles"]), int(names[record["surface_tag"]][5:]), dtype=np.int64)
            for record in records
        ])
        return mesh
