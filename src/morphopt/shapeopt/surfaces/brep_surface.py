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

from ...optcore.modelparams.parts import CADPart
from .base_surface import BaseSurface
from .nurbs_face import NURBSFace, read_nurbs_faces

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

    import torchfea
    from torchfea.cad import BREPEdge, BREPFace, BREPTopology, BREPVertex
    from torchfea.cad.builder import OCCBuilder


class BREPSurface(BaseSurface):
    """One closed shell, its face/edge/vertex graph and named selections.

    STEP contains the geometry. ``.faces.json`` preserves source face names;
    ``.brep.json`` stores edge/vertex identities, sets and NURBS selections.
    Topology inspection does not generate a display or finite-element mesh.
    """

    def __init__(self, path_step: str | Path) -> None:
        super().__init__()
        self.path_step = Path(path_step).resolve()
        self._geometry_path = self.path_step
        mapping = self.path_step.with_suffix(".faces.json")
        self._face_map: dict[str, list[float]] = (
            json.loads(mapping.read_text(encoding="utf-8")) if mapping.exists() else {}
        )
        self._has_named_faces = bool(self._face_map)
        metadata_path = self.path_step.with_suffix(".brep.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        self._edge_map: dict[str, list[float]] = metadata.get("edge_map", {})
        self._vertex_map: dict[str, list[float]] = metadata.get("vertex_map", {})
        self.surface_sets: dict[str, tuple[str, ...]] = {
            name: tuple(members) for name, members in metadata.get("surface_sets", {}).items()
        }
        self.node_sets: dict[str, tuple[str, ...]] = {
            name: tuple(members) for name, members in metadata.get("node_sets", {}).items()
        }
        self._nurbs_faces: set[str] = set(metadata.get("nurbs_faces", []))
        self._topology: BREPTopology | None = None
        self._loaded_topology: BREPTopology | None = None
        self._bound_face_names: dict[str, str] = {}
        self._nurbs_models: dict[str, NURBSFace] | None = None
        self._mesh_set_prefix: str | None = None

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
            probes: dict[str, np.ndarray] = {}
            with TemporaryDirectory(prefix="morphopt_nurbs_") as directory:
                path = Path(directory) / "geometry.brep"
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
                    if probes:
                        gmsh.write(str(path))
                self._nurbs_models = read_nurbs_faces(path, probes) if probes else {}
        return self._nurbs_models

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
            "edge_map": self._edge_map, "vertex_map": self._vertex_map,
            "surface_sets": {name: list(members) for name, members in self.surface_sets.items()},
            "node_sets": {name: list(members) for name, members in self.node_sets.items()},
            "nurbs_faces": sorted(self._nurbs_faces),
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
        """Export the current solid and both topology sidecars without meshing."""
        destination = Path(path).resolve()
        if destination.suffix.lower() not in {".stp", ".step"}:
            raise ValueError("STEP export requires a .stp or .step filename.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with cad.occ_session("morphopt_brep_export") as context:
            self._build_geometry(context)
            gmsh.write(str(destination))
        face_map = {name: list(face.signature) for name, face in self.faces.items()}
        destination.with_suffix(".faces.json").write_text(json.dumps(face_map, indent=2), encoding="utf-8")
        destination.with_suffix(".brep.json").write_text(json.dumps(self.metadata(), indent=2), encoding="utf-8")
        return destination

    def prepare_geometry(
        self, path_output: str | Path, name_output: str,
        flip: bool = False, pools: Pool | None = None,
    ) -> None:
        """Materialize converted geometry before entering the Part mesh session."""
        self._geometry_path = (
            self.export_step(Path(path_output) / f"{name_output}.stp")
            if self._nurbs_faces else self.path_step
        )

    def output_data(
        self, path_output: str | Path, name_output: str, seed_size: float = -1,
        flip: bool = False, pools: Pool | None = None,
    ) -> str:
        return self.export_step(Path(path_output) / f"{name_output}.stp").name

    def load_geometry(self, part: CADPart, context: OCCBuilder) -> list[int]:
        """Bind topology names to this Part's active OCC and finite-element model."""
        tags = part.load_step_boundary(self._geometry_path, context)
        face_map = (
            {name: face.signature for name, face in self.topology.faces.items()}
            if self._geometry_path != self.path_step else self._face_map
        )
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
        if not models:
            return
        if self._mesh_set_prefix is None:
            raise RuntimeError("Define BREP mesh sets before binding nodes.")
        prefix = self._mesh_set_prefix
        coordinates = part.nodes.detach().cpu().numpy()
        updates: dict[int, np.ndarray] = {}
        with cad.occ_session("morphopt_nurbs_mesh_binding") as context:
            self._build_geometry(context)
            for name, model in models.items():
                indices = np.asarray(part.set_nodes[f"{prefix}_{name}_nodes"], dtype=np.int64)
                nodes = coordinates[indices]
                tag = self.topology.face_tags[name]
                projected, _ = gmsh.model.getClosestPoint(2, tag, nodes.ravel())
                projected = np.asarray(projected).reshape(-1, 3)
                uv = np.asarray(gmsh.model.getParametrization(2, tag, projected.ravel())).reshape(-1, 2)
                # Quadratic edge nodes begin as chord midpoints. Project them
                # onto their CAD edge before assigning the face parameter.
                for edge_name, edge in self.edges.items():
                    if name not in edge.faces:
                        continue
                    on_edge = np.isin(indices, part.set_nodes[f"{prefix}_{edge_name}"])
                    if not on_edge.any():
                        continue
                    edge_tag = self.topology.edge_tags[edge_name]
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
                for index, point in zip(indices, matched, strict=True):
                    if int(index) in updates and not np.allclose(updates[int(index)], point, rtol=0, atol=1e-7):
                        raise ValueError(f"Shared node {index} has inconsistent NURBS face positions.")
                    updates[int(index)] = point
        if updates:
            indices = np.fromiter(updates, dtype=np.int64)
            part.nodes[indices] = torch.as_tensor(np.array(list(updates.values())),
                                                dtype=part.nodes.dtype, device=part.nodes.device)

    def map_face_nodes(self, name: str) -> torch.Tensor:
        """Evaluate bound FE nodes with gradients to this face's control points."""
        model = self.nurbs_faces[name]
        uv = torch.as_tensor(model.surf_node_uv, dtype=model.control_points.dtype,
                             device=model.control_points.device)
        return model.map(uv)

    def _preview_geometry(self, context: OCCBuilder) -> list[tuple[int, int]]:
        return self._build_geometry(context)

    def get_mesh(self) -> pv.PolyData:
        """Tessellate current geometry and retain original logical face indices."""
        records = cad.preview_brep([CADPart._Operation("brep_preview", self._preview_geometry)])
        names = {tag: name for name, tag in self.topology.face_tags.items()}
        triangles = np.concatenate([record["triangles"] for record in records])
        nodes, local = np.unique(triangles, return_inverse=True)
        cells = np.column_stack((np.full(len(triangles), 3), local.reshape(-1, 3)))
        mesh = pv.PolyData(np.asarray(records[0]["points"])[nodes], cells)
        mesh.cell_data["face_index"] = np.concatenate([
            np.full(len(record["triangles"]), int(names[record["surface_tag"]][5:]), dtype=np.int64)
            for record in records
        ])
        return mesh
