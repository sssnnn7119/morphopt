"""Part-specific set catalogs for fields, independent of preview actors."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from torchfea import Part

from ...constants import CONSTANT
from ..model.node_types.parts import (
    BoundaryPartNode,
    BoxPartNode,
    CADPartNode,
    INPPartNode,
    OffsetBoundaryPartNode,
)
from ..model.node_types.surfaces import BREPSurfaceNode
from ..model.problem import PartNode, ProblemDefinition
from .cad import cad_part_from_node


@dataclass(frozen=True)
class PartSets:
    """Describe available Part node, element, and surface selections for definition editors."""
    nodes: tuple[str, ...] = ()
    surfaces: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()


@lru_cache(maxsize=16)
def _read_inp_sets(path: str, modified_ns: int, size: int) -> dict[str, PartSets]:
    """Read selection names without constructing elements or importing materials.

    The file stamp keeps cached names current when an INP is replaced in place. Only
    declarations inside a Part belong to its catalog; assembly sets do not.

    Args:
        path (str): Filesystem path read, restored, or written by this operation.
        modified_ns (int): File modification timestamp in nanoseconds used by cache
            invalidation.
        size (int): Requested dimensions or size of the constructed object.

    Returns:
        dict[str, PartSets]: Read selection names without constructing elements or importing
            materials.
    """
    declarations: dict[str, dict[str, list[str]]] = {}
    current = None
    with open(path, encoding="utf-8-sig") as source:
        for line in source:
            line = line.strip()
            if not line.startswith("*") or line.startswith("**"):
                continue
            keyword, *options = (item.strip() for item in line.split(","))
            keyword = keyword.lower()
            parameters = {}
            for option in options:
                key, separator, value = option.partition("=")
                if separator:
                    parameters[key.strip().lower()] = value.strip().strip('"')
            if keyword == "*part":
                name = parameters.get("name")
                current = (
                    declarations.setdefault(
                        name, {"nodes": [], "surfaces": [], "elements": []}
                    )
                    if name
                    else None
                )
            elif keyword == "*end part":
                current = None
            elif current is not None:
                target = {
                    "*nset": ("nodes", "nset"),
                    "*surface": ("surfaces", "name"),
                    "*element": ("elements", "type"),
                }.get(keyword)
                if target is not None:
                    kind, key = target
                    name = parameters.get(key)
                    if name:
                        current[kind].append(
                            name.upper() if kind == "elements" else name
                        )
    return {
        name: PartSets(
            **{kind: tuple(dict.fromkeys(names)) for kind, names in sets.items()}
        )
        for name, sets in declarations.items()
    }


PartT = TypeVar("PartT", bound=PartNode)
SetProvider = Callable[[Any, ProblemDefinition], PartSets]


class PartSetCatalog:
    """One field-binding snapshot; each Part is queried at most once."""

    def __init__(self, problem: ProblemDefinition):
        """Initialize PartSetCatalog and its configuration state.

        Args:
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.
        """
        self.problem = problem
        self._providers: dict[type[PartNode], SetProvider] = {
            BoundaryPartNode: self.boundary,
            BoxPartNode: self.box,
            CADPartNode: self.cad,
            INPPartNode: self.inp,
        }
        self._cache: dict[PartNode, PartSets] = {}
        self._meshes: dict[PartNode, Part] = {}

    def bind(self, problem: ProblemDefinition) -> None:
        """Bind the PartSetCatalog state.

        Args:
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.
        """
        self.problem = problem
        self.invalidate()

    def invalidate(self) -> None:
        """Return invalidate."""
        self._cache.clear()
        self._meshes.clear()

    def mesh_for_part(self, part: PartNode) -> Part:
        """Build one kernel mesh per snapshot for both named selections and preview."""
        from .part_mesh import build_part_mesh

        if part not in self._meshes:
            self._meshes[part] = build_part_mesh(part, self.problem)
        return self._meshes[part]

    def register(
        self,
        node_type: type[PartT],
        provider: Callable[[PartT, ProblemDefinition], PartSets],
    ) -> None:
        """Register the PartSetCatalog state.

        Args:
            node_type (type[PartT]): Registered definition-node class to instantiate or validate.
            provider (Callable[[PartT, ProblemDefinition], PartSets]): Registered physical-field
                provider being evaluated.
        """
        self._providers[node_type] = provider
        self.invalidate()

    def for_instance(self, name: str) -> PartSets:
        """Return for instance.

        Args:
            name (str): Name identifying the item in its owning collection.

        Returns:
            PartSets: For instance.
        """
        if not name:
            return PartSets()
        part = self.problem.part_for_instance(name)
        if part is None:
            return PartSets()
        return self.for_part(part)

    def for_part(self, part: PartNode | None) -> PartSets:
        """Return for part.

        Args:
            part (PartNode | None): Part whose geometry, mesh, or named sets are processed.

        Returns:
            PartSets: For part.
        """
        if part is None:
            return PartSets()
        if part not in self._cache:
            provider = next(
                (
                    self._providers[cls]
                    for cls in type(part).__mro__
                    if cls in self._providers
                ),
                None,
            )
            if part.custom_class:
                model = self.mesh_for_part(part)
                self._cache[part] = PartSets(
                    tuple(model.set_nodes),
                    tuple(model.surfaces.keys()),
                    tuple(model.elems),
                )
            else:
                self._cache[part] = (
                    provider(part, self.problem) if provider else PartSets()
                )
        return self._cache[part]

    @staticmethod
    def element_type(part: PartNode | None, name: str) -> str:
        """Describe built-in element types without changing stable block names.

        Args:
            part (PartNode | None): Part whose geometry, mesh, or named sets are processed.
            name (str): Name identifying the item in its owning collection.

        Returns:
            str: Describe built-in element types without changing stable block names.
        """
        if (
            isinstance(part, (BoundaryPartNode, CADPartNode, BoxPartNode))
            and not part.custom_class
            and part.mesh_order == 2
        ):
            return CONSTANT.KERNEL.MESH.QUADRATIC_ELEMENT_TYPES.get(name, name)
        return name

    @staticmethod
    def boundary(part: BoundaryPartNode, problem: ProblemDefinition) -> PartSets:
        """Return boundary.

        Args:
            part (BoundaryPartNode): Part whose geometry, mesh, or named sets are processed.
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.

        Returns:
            PartSets: Boundary.
        """
        surface_count = len(part.surfaces)
        names = [f"surface_{index}_All" for index in range(surface_count)]
        if isinstance(part, OffsetBoundaryPartNode):
            names.extend(f"surface_{index}_offset" for index in range(1, surface_count))
        end_nodes = (
            tuple(f"surface_0_{name}" for name in part.surfaces[0].end_node_set_names)
            if surface_count
            else ()
        )
        faces = [
            name
            for surface in part.surfaces
            if isinstance(surface, BREPSurfaceNode)
            for name in json.loads(surface.brep_metadata).get("face_map", {})
        ]
        surface_sets: list[str] = []
        node_sets: list[str] = []
        for index, surface in enumerate(part.surfaces):
            if not isinstance(surface, BREPSurfaceNode):
                continue
            prefix = f"surface_{index}"
            metadata = json.loads(surface.brep_metadata)
            selections = [
                *json.loads(surface.brep_metadata).get("face_map", {}),
                *metadata.get("surface_sets", {}),
            ]
            surface_sets.extend(f"{prefix}_{name}" for name in selections)
            node_sets.extend(f"{prefix}_{name}_nodes" for name in selections)
            node_sets.extend(
                f"{prefix}_{name}"
                for name in (
                    *metadata.get("edge_map", {}),
                    *metadata.get("vertex_map", {}),
                    *metadata.get("node_sets", {}),
                )
            )
        return PartSets(
            nodes=("all", "surface_all")
            + tuple(names)
            + end_nodes
            + tuple(f"{name}_nodes" for name in faces)
            + tuple(node_sets),
            surfaces=tuple(
                dict.fromkeys(
                    [
                        "extern",
                        part.exterior_surface or "extern",
                        *names,
                        *faces,
                        *surface_sets,
                    ]
                )
            ),
            elements=("C3D4", "C3D6")
            if isinstance(part, OffsetBoundaryPartNode)
            else ("C3D4",),
        )

    @staticmethod
    def box(part: BoxPartNode, problem: ProblemDefinition) -> PartSets:
        """Return box.

        Args:
            part (BoxPartNode): Part whose geometry, mesh, or named sets are processed.
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.

        Returns:
            PartSets: Box.
        """
        return PartSets(
            nodes=("all",)
            + tuple(f"nodes_{axis}{side}" for axis in "xyz" for side in ("min", "max")),
            surfaces=(part.exterior_surface or "extern",)
            + tuple(
                f"surface_{axis}{side}" for axis in "xyz" for side in ("min", "max")
            ),
            elements=("C3D8",),
        )

    @staticmethod
    def cad(part: CADPartNode, problem: ProblemDefinition) -> PartSets:
        """Return cad.

        Args:
            part (CADPartNode): Part whose geometry, mesh, or named sets are processed.
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.

        Returns:
            PartSets: Cad.
        """
        names = cad_part_from_node(part, problem).get_face_names()
        return PartSets(
            nodes=("all", "surface_all") + tuple(f"{name}_nodes" for name in names),
            surfaces=tuple(dict.fromkeys([part.exterior_surface or "extern", *names])),
            # Quadratic conversion preserves the element block's name.
            elements=("C3D4",),
        )

    @staticmethod
    def inp_parts(mesh_file: str) -> dict[str, PartSets]:
        """Return inp parts.

        Args:
            mesh_file (str): Input mesh-asset filename.

        Returns:
            dict[str, PartSets]: Inp parts.
        """
        if not mesh_file:
            return {}
        try:
            path = Path(mesh_file).resolve()
            stat = path.stat()
            return _read_inp_sets(str(path), stat.st_mtime_ns, stat.st_size)
        except (OSError, UnicodeError):
            # Missing or unreadable imports remain editable unfinished definitions.
            return {}

    @staticmethod
    def inp(part: INPPartNode, problem: ProblemDefinition | None = None) -> PartSets:
        """Return inp.

        Args:
            part (INPPartNode): Part whose geometry, mesh, or named sets are processed.
            problem (ProblemDefinition | None): Editable problem definition shared by the UI
                application services.

        Returns:
            PartSets: Inp.
        """
        parts = PartSetCatalog.inp_parts(part.mesh_file)
        name = part.inp_part_name
        if not name and len(parts) == 1:
            name = next(iter(parts))
        return parts.get(name, PartSets())
