"""Part-specific set catalogs for fields, independent of preview actors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar
from ..model.problem import PartNode, ProblemDefinition
from .cad import cad_part_from_node
from ..model.node_types.parts import BoundaryPartNode, OffsetBoundaryPartNode, BoxPartNode, CADPartNode, INPPartNode


@dataclass(frozen=True)
class PartSets:
    nodes: tuple[str, ...] = ()
    surfaces: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()

PartT = TypeVar("PartT", bound=PartNode)
SetProvider = Callable[[Any, ProblemDefinition], PartSets]


class PartSetCatalog:
    """One field-binding snapshot; each Part is queried at most once."""

    def __init__(self, problem: ProblemDefinition):
        self.problem = problem
        self._providers: dict[type[PartNode], SetProvider] = {
            BoundaryPartNode: self.boundary,
            BoxPartNode: self.box,
            CADPartNode: self.cad,
            INPPartNode: self.inp,
        }
        self._cache: dict[PartNode, PartSets] = {}

    def bind(self, problem: ProblemDefinition) -> None:
        self.problem = problem
        self.invalidate()

    def invalidate(self) -> None:
        self._cache.clear()

    def register(self, node_type: type[PartT], provider: Callable[[PartT, ProblemDefinition], PartSets]) -> None:
        self._providers[node_type] = provider
        self.invalidate()

    def for_instance(self, name: str) -> PartSets:
        if not name:
            return PartSets()
        part = self.problem.part_for_instance(name)
        if part is None:
            return PartSets()
        return self.for_part(part)

    def for_part(self, part: PartNode | None) -> PartSets:
        if part is None:
            return PartSets()
        if part not in self._cache:
            provider = next((self._providers[cls] for cls in type(part).__mro__ if cls in self._providers), None)
            self._cache[part] = provider(part, self.problem) if provider else PartSets()
        return self._cache[part]

    @staticmethod
    def boundary(part: BoundaryPartNode, problem: ProblemDefinition) -> PartSets:
        surface_count = len(part.surfaces)
        names = [f"surface_{index}_All" for index in range(surface_count)]
        if isinstance(part, OffsetBoundaryPartNode):
            names.extend(f"surface_{index}_offset" for index in range(1, surface_count))
        if surface_count:
            names.extend(["surface_0_Bottom", "surface_0_Head"])
        return PartSets(nodes=tuple(names), surfaces=tuple(names))

    @staticmethod
    def box(part: BoxPartNode, problem: ProblemDefinition) -> PartSets:
        return PartSets(
            nodes=("all",) + tuple(f"nodes_{axis}{side}" for axis in "xyz" for side in ("min", "max")),
            surfaces=(part.exterior_surface or "extern",) + tuple(f"surface_{axis}{side}" for axis in "xyz" for side in ("min", "max")),
            elements=("design",),
        )

    @staticmethod
    def cad(part: CADPartNode, problem: ProblemDefinition) -> PartSets:
        names = cad_part_from_node(part, problem).get_face_names()
        return PartSets(
            nodes=("all", "surface_all") + tuple(f"{name}_nodes" for name in names),
            surfaces=tuple(dict.fromkeys([part.exterior_surface or "extern", *names])),
        )

    @staticmethod
    def inp(part: INPPartNode, problem: ProblemDefinition) -> PartSets:
        if not part.mesh_file or not Path(part.mesh_file).is_file():
            return PartSets()
        from ...optcore.modelparams.parts import INPPart
        model = INPPart(
            mesh_file=part.mesh_file,
            part_name=part.assembly_name,
            inp_part_name=part.inp_part_name or None,
            exterior_surface=part.exterior_surface or None,
        ).get_part()
        model.initialize()
        return PartSets(tuple(model.set_nodes), tuple(model.surfaces), tuple(model.elems))
