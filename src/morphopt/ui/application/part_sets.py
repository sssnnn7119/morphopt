"""Part-specific set catalogs for fields, independent of preview actors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from ..model.problem import PartNode, ProblemDefinition
from .cad import cad_part_from_node


@dataclass(frozen=True)
class PartSets:
    nodes: tuple[str, ...] = ()
    surfaces: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()

SetProvider = Callable[[PartNode, ProblemDefinition], PartSets]


class PartSetCatalog:
    """One field-binding snapshot; each Part is queried at most once."""

    def __init__(self, problem: ProblemDefinition):
        self.problem = problem
        self._providers: dict[str, SetProvider] = {
            "BoundaryPart": self.boundary,
            "OffsetBoundaryPart": self.boundary,
            "BoxPart": self.box,
            "CADPart": self.cad,
            "TorchFEAPart": self.imported,
            "INPPart": self.inp,
        }
        self._cache: dict[PartNode, PartSets] = {}

    def bind(self, problem: ProblemDefinition) -> None:
        self.problem = problem
        self.invalidate()

    def invalidate(self) -> None:
        self._cache.clear()

    def register(self, interface_type: str, provider: SetProvider) -> None:
        self._providers[interface_type] = provider
        self.invalidate()

    def for_instance(self, name: str) -> PartSets:
        if not name:
            return PartSets()
        part = self.problem.part_interface_for_instance(name)
        if part is None:
            return PartSets(tuple(self.problem.node_set_names(name)), tuple(self.problem.surface_set_names(name)))
        return self.for_part(part)

    def for_part(self, part: PartNode | None) -> PartSets:
        if part is None:
            return PartSets()
        if part not in self._cache:
            provider = self._providers.get(part.interface_type)
            self._cache[part] = provider(part, self.problem) if provider else PartSets()
        return self._cache[part]

    @staticmethod
    def boundary(part: PartNode, problem: ProblemDefinition) -> PartSets:
        names = [f"surface_{index}_All" for index in range(len(part.surfaces()))]
        if part.interface_type == "OffsetBoundaryPart":
            names.extend(f"surface_{index}_offset" for index in range(1, len(part.surfaces())))
        names.extend(["surface_0_Bottom", "surface_0_Head"])
        return PartSets(nodes=tuple(names), surfaces=tuple(names))

    @staticmethod
    def box(part: PartNode, problem: ProblemDefinition) -> PartSets:
        return PartSets(
            nodes=("all",) + tuple(f"nodes_{axis}{side}" for axis in "xyz" for side in ("min", "max")),
            surfaces=(part.exterior_surface or "extern",) + tuple(f"surface_{axis}{side}" for axis in "xyz" for side in ("min", "max")),
            elements=("design",),
        )

    @staticmethod
    def cad(part: PartNode, problem: ProblemDefinition) -> PartSets:
        names = cad_part_from_node(part, problem).get_face_names()
        return PartSets(
            nodes=("all", "surface_all") + tuple(f"{name}_nodes" for name in names),
            surfaces=tuple(dict.fromkeys([part.exterior_surface or "extern", *names])),
        )

    @staticmethod
    def imported(part: PartNode, problem: ProblemDefinition) -> PartSets:
        summary = problem.imported_model_summary()
        if summary is None:
            return PartSets()
        source = next(
            (item for item in summary.parts if item.name == (part.model_part_name or part.resolved_part_name())),
            None,
        )
        return PartSets(
            source.node_sets,
            source.surface_sets,
            source.element_types,
        ) if source is not None else PartSets()

    @staticmethod
    def inp(part: PartNode, problem: ProblemDefinition) -> PartSets:
        if not part.mesh_file or not Path(part.mesh_file).is_file():
            return PartSets()
        from ...optcore.modelparams.parts import INPPart
        model = INPPart(
            mesh_file=part.mesh_file,
            part_name=part.resolved_part_name(),
            inp_part_name=part.inp_part_name or None,
            exterior_surface=part.exterior_surface or None,
        ).get_part()
        model.initialize()
        return PartSets(tuple(model.set_nodes), tuple(model.surfaces), tuple(model.elems))
