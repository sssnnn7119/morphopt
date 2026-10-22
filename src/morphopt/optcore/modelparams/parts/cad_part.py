"""Shared CAD and closed-boundary Part construction."""

from __future__ import annotations

import math
import json
from collections.abc import Callable, Iterable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import gmsh
import torchfea
from torchfea import cad as torchfea_cad
from torchfea.cad.builder import OCCBuilder

from ....constants import CONSTANT
from .base_part import BasePart

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

    from ....shapeopt.boundary_part import BoundaryPart


class CADPart(BasePart):
    """Build a Part from an ordered sequence of TorchFEA CAD operations.

    Subclasses override :meth:`define_operations` and add native TorchFEA CAD
    objects with :meth:`add_operation`::

        class Housing(morphopt.CADPart):
            def define_operations(self) -> None:
                body = torchfea.cad.Box(
                    id="body", x=0, y=0, z=0, dx=20, dy=12, dz=8
                )
                bore = torchfea.cad.Cylinder(
                    id="bore", x=10, y=6, z=0, dz=8, radius=2
                )
                self.add_operation(body)
                self.add_operation(bore)
                self.add_operation(
                    torchfea.cad.Cut(
                        id="housing", object_id="body", tool_id="bore"
                    )
                )

    Boolean and transform operations refer to earlier operations by their
    IDs. The order in which :meth:`add_operation` is called is the CAD
    history order. Every OCC face and its nodes are named automatically as
    ``face_N`` and ``face_N_nodes`` after meshing.
    """

    cache_part = True

    @dataclass
    class _Operation(torchfea_cad.CADOperation):
        """Bridge a Part method into TorchFEA's managed Gmsh execution session."""

        action: Callable[[OCCBuilder], list[tuple[int, int]]]
        kind: ClassVar[str] = "morphopt_geometry"
        non_parameter_fields: ClassVar[tuple[str, ...]] = ("action",)

        def apply_occ(self, context: OCCBuilder) -> list[tuple[int, int]]:
            """Execute the callback and return Gmsh (dimension, entity tag) pairs."""
            return self.action(context)

    def __init__(
        self,
        mesh_size: float = CONSTANT.KERNEL.MESH.DEFAULT_CAD_MESH_SIZE,
        mesh_order: int = CONSTANT.KERNEL.MESH.DEFAULT_ELEMENT_ORDER,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not math.isfinite(mesh_size) or mesh_size <= 0:
            raise ValueError("mesh_size must be finite and positive.")
        if mesh_order not in (1, 2):
            raise ValueError("mesh_order must be 1 or 2.")
        self.mesh_size = float(mesh_size)
        self.mesh_order = mesh_order
        self.operations: list[torchfea_cad.CADOperation] = []
        self._face_names: dict[int, str] = {}

    def define_operations(self) -> None:
        """Override to declare CAD operations in their execution order."""

    def add_operation(self, operation: torchfea_cad.CADOperation) -> CADPart:
        """Append one native TorchFEA CAD operation to the history."""
        if not isinstance(operation, torchfea_cad.CADOperation):
            raise TypeError("operation must be a TorchFEA CADOperation.")
        self.operations.append(operation)
        return self

    def initialize(self, *args: object, **kwargs: object) -> None:
        """Declare Instances and the CAD history once during initialization."""
        super().initialize(*args, **kwargs)
        self.operations.clear()
        self.define_operations()

    def prepare_geometry(
        self, path_result: str | None = None, pools: Pool | None = None,
    ) -> list[torchfea_cad.CADOperation]:
        """Provide the declared CAD operations; subclasses prepare their inputs."""
        self._face_names.clear()
        return self.operations

    def assemble_geometry(
        self, geometry: Sequence[torchfea_cad.CADOperation],
    ) -> torchfea_cad.CADHistory:
        """Construct the native CAD history used by the shared mesher."""
        return torchfea_cad.CADHistory(
            operations=geometry,
            mesh_size=self.mesh_size,
            exterior_surface=self.exterior_surface or "extern",
        )

    def mesh_geometry(self, geometry: torchfea_cad.CADHistory) -> torchfea.Part:
        """Use TorchFEA's shared Gmsh mesh extraction for either geometry kernel."""
        return geometry.mesh(self.mesh_size)

    def define_mesh_sets(self, part: torchfea.Part) -> None:
        """Map geometric face identities onto the FE mesh."""
        self._name_geometry_faces(part)

    def _postprocess_part(self, part: torchfea.Part) -> torchfea.Part:
        """Extend the linear mesh, for example with offset-layer elements."""
        return part

    def postprocess_mesh(self, part: torchfea.Part) -> torchfea.Part:
        """Apply element extensions before the shared quadratic conversion."""
        part = self._postprocess_part(part)
        if self.mesh_order == 2:
            element_names = list(part.elems)
            part.convert_linear_to_quadratic_elements(element_names, element_names)
        return part

    def build_part(
        self, path_result: str | None = None, pools: Pool | None = None,
    ) -> torchfea.Part:
        """Prepare, assemble, mesh, name and postprocess one Part."""
        geometry = self.assemble_geometry(self.prepare_geometry(path_result, pools))
        part = self.mesh_geometry(geometry)
        self.define_mesh_sets(part)
        return self.postprocess_mesh(part)

    def _complete_face_names(self, tags: Iterable[int]) -> None:
        """Assign unused face names while retaining identities from source CAD."""
        names = set(self._face_names.values())
        index = 0
        for tag in sorted(tags):
            if tag in self._face_names:
                continue
            while f"face_{index}" in names:
                index += 1
            self._face_names[tag] = f"face_{index}"
            names.add(f"face_{index}")

    def _name_geometry_faces(self, part: torchfea.Part) -> None:
        """Name geometric boundary faces using source identities or tag order."""
        face_names = [
            name for name in part.surfaces.keys() if name.startswith("gmsh_surface_")
        ]
        face_names.sort(key=lambda name: int(name.rsplit("_", 1)[1]))

        tags = [int(name.rsplit("_", 1)[1]) for name in face_names]
        self._complete_face_names(tags)
        identities = {tag: self._face_names[tag] for tag in tags}
        reserved_surfaces = set(identities.values())
        reserved_nodes = {f"{name}_nodes" for name in reserved_surfaces}
        surface_conflicts = reserved_surfaces.intersection(part.surfaces.keys())
        node_conflicts = reserved_nodes.intersection(part.set_nodes)
        if surface_conflicts or node_conflicts:
            names = ", ".join(sorted(surface_conflicts | node_conflicts))
            raise ValueError(
                f"CAD set names {names} are reserved for OCC faces and nodes."
            )

        renamed_surfaces = type(part.surfaces)()
        renamed_names = {
            old: identities[int(old.rsplit("_", 1)[1])] for old in face_names
        }
        for old_name in part.surfaces.keys():
            renamed_surfaces[renamed_names.get(old_name, old_name)] = part.surfaces[old_name]
        part.surfaces = renamed_surfaces

        for old_name in face_names:
            tag = old_name.rsplit("_", 1)[1]
            old_node_name = f"gmsh_nodes_{tag}"
            name = identities[int(tag)]
            nodes = part.set_nodes[old_node_name]

            part.delete_node_set(old_node_name)
            part.add_node_set(f"{name}_nodes", nodes)

    def get_face_names(self) -> list[str]:
        """Return geometric face identities in the preview's face order."""
        history = self.assemble_geometry(self.prepare_geometry())
        if not history.operations:
            return []
        records = history.preview()
        self._complete_face_names(record["surface_tag"] for record in records)
        return [self._face_names[record["surface_tag"]] for record in records]

    @staticmethod
    def _single_solid(
        operations: Sequence[torchfea_cad.CADOperation],
    ) -> tuple[int, list[int]]:
        """Replay operations and return the single volume tag and sorted face tags."""
        volumes = OCCBuilder(gmsh).replay(operations)
        if len(volumes) != 1:
            raise ValueError(
                "CAD-to-boundary conversion requires one final solid. "
                "Define disconnected solids as separate CADParts."
            )
        volume = volumes[0]
        faces = sorted(tag for _, tag in gmsh.model.getBoundary(
            [(3, volume)], oriented=False, recursive=False,
        ))
        return volume, faces

    @staticmethod
    def load_step_boundary(path: str | Path, context: OCCBuilder) -> list[int]:
        """Import a STEP boundary while retaining its geometric faces."""
        before = set(gmsh.model.getEntities(2))
        imported = context.occ.importShapes(str(path))
        context.occ.synchronize()
        volumes = [(dim, tag) for dim, tag in imported if dim == 3]
        if volumes:
            context.occ.remove(volumes, recursive=False)
            context.occ.synchronize()
        tags = sorted(tag for _, tag in set(gmsh.model.getEntities(2)) - before)
        if not tags:
            raise ValueError(f"No boundary faces in {path}")
        return tags

    @staticmethod
    def load_mesh_boundary(path: str | Path) -> list[int]:
        """Import a closed STL boundary into the active geometry session."""
        before = set(gmsh.model.getEntities(2))
        gmsh.merge(str(path))
        tags = sorted(tag for _, tag in set(gmsh.model.getEntities(2)) - before)
        if not tags:
            raise ValueError(f"No boundary faces in {path}")
        return tags

    @staticmethod
    def get_face_signature(tag: int) -> list[float]:
        """Describe a face by its area, centroid and inertia in local coordinates."""
        return [
            float(gmsh.model.occ.getMass(2, tag)),
            *map(float, gmsh.model.occ.getCenterOfMass(2, tag)),
            *map(float, gmsh.model.occ.getMatrixOfInertia(2, tag)),
        ]

    @staticmethod
    def _inspect_shells(
        context: OCCBuilder,
        *,
        operations: tuple[torchfea_cad.CADOperation, ...],
        shells: list[tuple[int, ...]],
    ) -> list[tuple[int, int]]:
        """Fill shell face indices in exterior-first order inside a CAD session."""
        volume, faces = CADPart._single_solid(operations)
        indices = {tag: index for index, tag in enumerate(faces)}
        loops, shell_faces = context.occ.getSurfaceLoops(volume)
        ordered = []
        for loop, tags in zip(loops, shell_faces):
            solid = context.occ.addVolume([int(loop)])
            mass = abs(context.occ.getMass(3, solid))
            context.occ.remove([(3, solid)], recursive=False)
            ordered.append((mass, tuple(sorted(indices[abs(int(tag))] for tag in tags))))
        context.occ.synchronize()
        ordered.sort(key=lambda item: (-item[0], item[1]))
        shells[:] = [indices for _, indices in ordered]
        if not shells:
            raise ValueError("The CAD solid has no closed boundary shell.")
        return [(3, volume)]

    def split_shells(self) -> tuple[
        tuple[torchfea_cad.CADOperation, ...],
        list[tuple[int, ...]],
    ]:
        """Return copied operations and exterior-first closed-shell face indices.

        Each shell contains zero-based indices into the source CAD face order.
        """
        operations = tuple(deepcopy(self.operations))
        if not operations:
            raise ValueError("The CAD history is empty; initialize the CADPart before conversion.")
        shells: list[tuple[int, ...]] = []
        action = partial(self._inspect_shells, operations=operations, shells=shells)
        torchfea_cad.preview_brep([self._Operation("inspect", action)])
        return operations, shells

    @staticmethod
    def _build_shell(
        context: OCCBuilder,
        *,
        operations: tuple[torchfea_cad.CADOperation, ...],
        face_indices: tuple[int, ...],
        face_map: dict[str, list[float]],
    ) -> list[tuple[int, int]]:
        """Reconstruct one shell as a solid for standalone STEP export."""
        volume, faces = CADPart._single_solid(operations)
        context.occ.remove([(3, volume)], recursive=False)
        selected = [faces[index] for index in face_indices]
        loop = context.occ.addSurfaceLoop(selected)
        solid = context.occ.addVolume([loop])
        context.occ.synchronize()
        unused = [(2, tag) for tag in faces if tag not in selected]
        if unused:
            context.occ.remove(unused, recursive=True)
            context.occ.synchronize()
        face_map.update({
            f"face_{index}": CADPart.get_face_signature(tag)
            for index, tag in zip(face_indices, selected)
        })
        return [(3, solid)]

    @staticmethod
    def export_shell_step(
        operations: tuple[torchfea_cad.CADOperation, ...],
        face_indices: tuple[int, ...],
        path: str | Path,
    ) -> None:
        """Export a closed shell and its original face identities as STEP assets."""
        path = Path(path)
        face_map: dict[str, list[float]] = {}
        action = partial(
            CADPart._build_shell, operations=operations,
            face_indices=face_indices, face_map=face_map,
        )
        torchfea_cad.export_step([CADPart._Operation("shell", action)], str(path))
        path.with_suffix(".faces.json").write_text(
            json.dumps(face_map, indent=2), encoding="utf-8",
        )

    def to_boundary_part(
        self, asset_directory: str | Path = "morphopt_assets",
    ) -> BoundaryPart:
        """Export an initialized single-solid CAD Part as fixed STEP boundaries.

        Write one STEP and face map per shell under asset_directory/part_name.
        Preserve original face identities, mesh settings and Instance poses;
        the resulting surfaces retain file references, not source CAD history.
        """
        from ....shapeopt.boundary_part import BoundaryPart
        from ....shapeopt.surfaces.brep_surface import BREPSurface

        operations, shells = self.split_shells()
        directory = Path(asset_directory) / self.part_name
        directory.mkdir(parents=True, exist_ok=True)
        boundary = BoundaryPart(
            fea_seed_size=self.mesh_size,
            mesh_order=self.mesh_order,
            part_name=self.part_name,
            exterior_surface=self.exterior_surface or "extern",
        )
        boundary._name = self.name
        boundary._instance_definitions = deepcopy(self._instance_definitions)
        for index, face_indices in enumerate(shells):
            path = directory / f"surface_{index}.stp"
            self.export_shell_step(operations, face_indices, path)
            surface = BREPSurface(path)
            surface.flip = index != 0
            boundary.add_surface_interface(surface)
        boundary.initialize()
        return boundary
