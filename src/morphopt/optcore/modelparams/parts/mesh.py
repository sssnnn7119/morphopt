"""Gmsh-backed volume meshing service and generic mesh Part definition."""

from __future__ import annotations

from multiprocessing.pool import Pool
from pathlib import Path

import gmsh
import numpy as np
from morphopt._torch import torch
import torchfea

from .base import BasePartDefinition


class MeshBuilder:
    """Build a tetrahedral INP mesh from ordered closed surface files."""

    def __init__(
        self,
        *,
        minimum_size: float | None = None,
        maximum_size: float | None = None,
        mesh_order: int = 1,
    ) -> None:
        self._minimum_size = minimum_size
        """Optional Gmsh minimum size."""
        self._maximum_size = maximum_size
        """Optional Gmsh maximum size."""
        self._mesh_order = int(mesh_order)
        """Requested mesh order; V4 converts elements after INP import."""
        self._surface_paths: tuple[Path, ...] = ()
        """Ordered indexed surface files."""
        self._surface_tags_by_index: dict[int, tuple[int, ...]] = {}
        """Gmsh two-dimensional entity tags by surface index."""
        self._volume_tags: tuple[int, ...] = ()
        """Gmsh volume entities created from imported surface loops."""
        self._initialized = False
        """Whether this builder owns an active Gmsh session."""

    @property
    def minimum_size(self) -> float | None:
        """Read the optional Gmsh minimum size."""
        return self._minimum_size

    @property
    def maximum_size(self) -> float | None:
        """Read the optional Gmsh maximum size."""
        return self._maximum_size

    @property
    def mesh_order(self) -> int:
        """Read the requested mesh order."""
        return self._mesh_order

    def set_surface_paths(self, paths: tuple[str | Path, ...] | list[str | Path]) -> None:
        """Store indexed surface paths after extension and ordering validation."""
        normalized_paths = tuple(Path(path) for path in paths)
        if not normalized_paths:
            raise ValueError("MeshBuilder needs at least the outer surface")
        unsupported = [
            path for path in normalized_paths if path.suffix.lower() not in {".stp", ".step", ".stl"}
        ]
        if unsupported:
            raise ValueError(f"Unsupported surface files: {unsupported}")
        if any(not path.exists() for path in normalized_paths):
            missing = [path for path in normalized_paths if not path.exists()]
            raise FileNotFoundError(f"Surface files do not exist: {missing}")
        suffixes = {path.suffix.lower() for path in normalized_paths}
        if ".stl" in suffixes and (".stp" in suffixes or ".step" in suffixes):
            raise ValueError("One BoundaryPart uses one common STP or STL export format")
        self._surface_paths = normalized_paths

    def build_volume(self) -> None:
        """Import ordered surfaces and create one volume with interior cavities."""
        if not self._surface_paths:
            raise RuntimeError("Call set_surface_paths() before build_volume()")
        self._start_session()
        self._surface_tags_by_index.clear()
        suffix = self._surface_paths[0].suffix.lower()
        if suffix in {".stp", ".step"}:
            self._import_step_surfaces()
        else:
            self._import_stl_surfaces()
        outer_tags = self._surface_tags_by_index.get(0, ())
        if not outer_tags:
            raise RuntimeError("The ordered outer surface at index 0 has no Gmsh entities")
        if suffix in {".stp", ".step"}:
            loops = [gmsh.model.occ.addSurfaceLoop(list(outer_tags))]
            for index in range(1, len(self._surface_paths)):
                tags = self._surface_tags_by_index.get(index, ())
                if tags:
                    loops.append(gmsh.model.occ.addSurfaceLoop(list(tags)))
            volume_tag = gmsh.model.occ.addVolume(loops)
            gmsh.model.occ.synchronize()
        else:
            loops = [gmsh.model.geo.addSurfaceLoop(list(outer_tags))]
            for index in range(1, len(self._surface_paths)):
                tags = self._surface_tags_by_index.get(index, ())
                if tags:
                    loops.append(gmsh.model.geo.addSurfaceLoop(list(tags)))
            volume_tag = gmsh.model.geo.addVolume(loops)
            gmsh.model.geo.synchronize()
        self._volume_tags = (int(volume_tag),)
        gmsh.model.addPhysicalGroup(3, list(self._volume_tags), name="volume_all")

    def build_mesh(self, dimension: int = 3) -> None:
        """Generate a Gmsh mesh after the volume has been defined."""
        if not self._volume_tags:
            raise RuntimeError("Call build_volume() before build_mesh()")
        gmsh.model.mesh.generate(int(dimension))

    def export_inp(self, target_path: str | Path, *, part_name: str) -> Path:
        """Write Abaqus INP data plus V4 Part and surface-set definitions."""
        if not self._initialized:
            raise RuntimeError("MeshBuilder has no active Gmsh session")
        path = Path(target_path).with_suffix(".inp")
        path.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(path))
        payload = self._build_surface_payload()
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        insertion_index = min(2, len(lines))
        lines.insert(insertion_index, f"*Part, name={part_name}\n")
        if payload:
            lines.append("\n")
            lines.extend(f"{line}\n" for line in payload)
        lines.append("*End Part\n")
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def finalize(self) -> None:
        """Release the Gmsh session owned by this builder."""
        if self._initialized:
            gmsh.finalize()
            self._initialized = False
        self._surface_tags_by_index.clear()
        self._volume_tags = ()

    @staticmethod
    def read_inp_part(inp_path: str | Path, part_name: str) -> torchfea.Part:
        """Parse an INP Part into TorchFEA geometry without material assignment.

        Geometry creation intentionally imports nodes, element topology and
        named sets only.  ``MaterialsParams`` owns finite-element material
        construction later in the Params pipeline.
        """
        inp = torchfea.FEA_INP()
        inp.read_inp(str(inp_path))
        if part_name not in inp.part:
            raise ValueError(f"INP file has no Part named {part_name!r}")
        source = inp.part[part_name]
        part = torchfea.Part(torch.as_tensor(source.nodes[:, 1:]))
        for element_type, element_data in source.elems.items():
            elements = torchfea.elements.initialize_element(
                element_type=element_type,
                elems_index=torch.as_tensor(element_data[:, 0], dtype=torch.long),
                elems=torch.as_tensor(element_data[:, 1:], dtype=torch.long),
            )
            part.add_element(elements, name=element_type)
        for name, indices in source.sets_nodes.items():
            part.add_node_set(name, np.asarray(tuple(indices), dtype=int))
        for name, indices in source.sets_elems.items():
            part.add_element_set(name, np.asarray(tuple(indices), dtype=int))
        for name, entries in source.surfaces.items():
            part.add_surface_set(name, list(entries))
        return part

    def _start_session(self) -> None:
        """Open and configure a dedicated quiet Gmsh session."""
        if self._initialized:
            self.finalize()
        gmsh.initialize()
        gmsh.option.setNumber("General.NumThreads", 0)
        gmsh.option.setNumber("General.Verbosity", 2)
        if self._minimum_size is not None:
            gmsh.option.setNumber("Mesh.MeshSizeMin", self._minimum_size)
        if self._maximum_size is not None:
            gmsh.option.setNumber("Mesh.MeshSizeMax", self._maximum_size)
        gmsh.model.add("morphopt")
        self._initialized = True

    def _import_step_surfaces(self) -> None:
        """Import OCC STEP surfaces and retain tags per ordered source file."""
        for index, path in enumerate(self._surface_paths):
            before = {tag for _, tag in gmsh.model.getEntities(2)}
            gmsh.model.occ.importShapes(str(path))
            gmsh.model.occ.synchronize()
            volumes = gmsh.model.getEntities(3)
            if volumes:
                gmsh.model.occ.remove(volumes, recursive=False)
                gmsh.model.occ.synchronize()
            after = {tag for _, tag in gmsh.model.getEntities(2)}
            self._surface_tags_by_index[index] = tuple(sorted(after - before))

    def _import_stl_surfaces(self) -> None:
        """Import discrete STL surfaces and retain tags per ordered source file."""
        for index, path in enumerate(self._surface_paths):
            before = {tag for _, tag in gmsh.model.getEntities(2)}
            gmsh.merge(str(path))
            after = {tag for _, tag in gmsh.model.getEntities(2)}
            self._surface_tags_by_index[index] = tuple(sorted(after - before))

    def _build_surface_payload(self) -> tuple[str, ...]:
        """Map Gmsh triangle faces back to Abaqus C3D4 surface definitions."""
        element_tags, element_nodes = gmsh.model.mesh.getElementsByType(4)
        if len(element_tags) == 0:
            return ()
        tetrahedra = np.asarray(element_nodes, dtype=np.int64).reshape(-1, 4)
        face_definitions = (
            ((0, 1, 2), "S1"),
            ((0, 3, 1), "S2"),
            ((1, 3, 2), "S3"),
            ((2, 3, 0), "S4"),
        )
        face_map: dict[frozenset[int], tuple[int, str]] = {}
        for local_nodes, face_name in face_definitions:
            for element_tag, nodes in zip(element_tags, tetrahedra, strict=True):
                face_map[frozenset(int(nodes[index]) for index in local_nodes)] = (
                    int(element_tag),
                    face_name,
                )
        output: list[str] = []
        for index, tags in self._surface_tags_by_index.items():
            faces_by_name: dict[str, list[int]] = {name: [] for _, name in face_definitions}
            node_tags: set[int] = set()
            for tag in tags:
                triangle_tags, triangle_nodes = gmsh.model.mesh.getElementsByType(2, tag=tag)
                triangles = np.asarray(triangle_nodes, dtype=np.int64).reshape(-1, 3)
                for triangle in triangles:
                    node_tags.update(int(node) for node in triangle)
                    mapped = face_map.get(frozenset(int(node) for node in triangle))
                    if mapped is not None:
                        faces_by_name[mapped[1]].append(mapped[0])
            surface_name = f"surface_{index}_all"
            active: list[str] = []
            for face_name, elements in faces_by_name.items():
                if not elements:
                    continue
                element_set_name = f"_{surface_name}_{face_name.lower()}"
                active.append(f"{element_set_name}, {face_name}")
                output.append(f"*ELSET, ELSET={element_set_name}, INTERNAL")
                for start in range(0, len(elements), 16):
                    output.append(", ".join(str(item) for item in elements[start : start + 16]))
            if active:
                output.append(f"*SURFACE, TYPE=ELEMENT, NAME={surface_name}")
                output.extend(active)
            if node_tags:
                output.append(f"*NSET, NSET={surface_name}")
                sorted_nodes = sorted(node_tags)
                for start in range(0, len(sorted_nodes), 16):
                    output.append(", ".join(str(item) for item in sorted_nodes[start : start + 16]))
        return tuple(output)


class MeshPart(BasePartDefinition):
    """Fixed Part created by meshing one closed STL surface."""

    def __init__(
        self,
        part_name: str,
        mesh_path: str | Path,
        *,
        element_name: str = "solid",
        fea_seed_size: float | None = None,
    ) -> None:
        super().__init__(part_name, element_names=(element_name,))
        self._mesh_path = Path(mesh_path)
        """Closed source STL mesh."""
        self._fea_seed_size = fea_seed_size
        """Optional target tetrahedral mesh size."""

    @property
    def mesh_path(self) -> Path:
        """Read the source closed mesh path."""
        return self._mesh_path

    def build_part(self, path_result: Path | None = None, pools: Pool | None = None) -> None:
        """Tetrahedralize the fixed mesh and import it as a TorchFEA Part."""
        del pools
        directory = Path(path_result) if path_result is not None else Path.cwd()
        builder = MeshBuilder(
            minimum_size=None if self._fea_seed_size is None else 0.5 * self._fea_seed_size,
            maximum_size=self._fea_seed_size,
        )
        try:
            builder.set_surface_paths((self._mesh_path,))
            builder.build_volume()
            builder.build_mesh()
            inp_path = builder.export_inp(
                directory / f"{self.part_name}.inp", part_name=self.part_name
            )
        finally:
            builder.finalize()
        self._torchfea_Part = MeshBuilder.read_inp_part(inp_path, self.part_name)
        self._rename_element_families()

    def _rename_element_families(self) -> None:
        """Map imported element families to this definition's output names."""
        if self._torchfea_Part is None:
            return
        source_names = tuple(self._torchfea_Part.elems)
        if len(source_names) != len(self.element_names):
            raise ValueError(
                f"Part '{self.part_name}' contains {len(source_names)} element families, "
                f"but {len(self.element_names)} names were configured"
            )
        self._torchfea_Part.elems = {
            target: self._torchfea_Part.elems[source]
            for source, target in zip(source_names, self.element_names, strict=True)
        }
