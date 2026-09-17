"""FEA component and load-step definition processor."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from ..protocols import Updatable
import pyvista
import torchfea
from .components.base import BaseFEAComponent
from .components.steps import LoadStep


class FEAParams:
    """Register FEA components and prepare shared multi-case work conditions."""

    def __init__(self) -> None:
        self._components: dict[str, BaseFEAComponent] = {}
        """Registered FEA components keyed by name."""
        self._steps: list[LoadStep] = []
        """LoadStep definitions in case order."""
        self._case_assemblies: tuple[torchfea.Assembly, ...] = ()
        """Views that all reference the shared Assembly."""
        self._assembly: torchfea.Assembly | None = None
        """Assembly receiving FEA components and load values."""
        self._iteration: int | None = None
        """Iteration represented by current FEA state."""
        self._meshes: tuple[pyvista.DataSet, ...] = ()
        """Cached result visualization meshes."""
        self._initialized = False
        """FEAParams lifecycle initialization state."""

    @property
    def components(self) -> MappingProxyType:
        """Return the read-only component registry."""
        return MappingProxyType(self._components)

    @property
    def steps(self) -> tuple[LoadStep, ...]:
        """Return load steps in case order."""
        return tuple(self._steps)

    def define_components(self) -> None:
        """Task hook for registering loads, boundaries and interactions."""
        # TODO: User task definitions call add_component() here.
        return None

    def add_component(
        self, component: BaseFEAComponent, name: str | None = None
    ) -> BaseFEAComponent:
        """Register one FEA component under a stable name."""
        component_name = name or str(component.name)
        self._components[component_name] = component
        return component

    def define_steps(self) -> None:
        """Task hook for registering load steps."""
        # TODO: User task definitions call add_step() here.
        return None

    def add_step(self, step: LoadStep) -> LoadStep:
        """Append one load step in its stable case order."""
        self._steps.append(step)
        return step

    def get_design_owners(self) -> tuple[tuple[str, int | None, BaseFEAComponent], ...]:
        """Return load value owners keyed by component and case."""
        owners: list[tuple[str, int | None, BaseFEAComponent]] = []
        for index, step in enumerate(self._steps):
            for component in step.components:
                if (
                    isinstance(component, Updatable)
                    and component.get_design_delta().numel() > 0
                ):
                    owners.append((str(component.name), index, component))
        return tuple(owners)

    def get_num_load_steps(self) -> int:
        """Return the number of registered load cases."""
        return len(self._steps)

    def get_component(self, name: str) -> BaseFEAComponent:
        """Read one registered component."""
        return self._components[name]

    def get_steps(self) -> tuple[LoadStep, ...]:
        """Read load steps in case order."""
        return tuple(self._steps)

    def initialize(self) -> None:
        """Reset registries and execute component/step definition hooks."""
        self._components.clear()
        self._steps.clear()
        self.define_components()
        self.define_steps()
        self._initialized = True

    def reinitialize(
        self, iteration: int, assembly: torchfea.Assembly | None = None
    ) -> None:
        """Bind the current base Assembly and clear case clones."""
        self._iteration = int(iteration)
        self._assembly = assembly
        self._case_assemblies = ()
        for component in self._components.values():
            component.reinitialize(iteration, assembly)

    def build_components(self) -> None:
        """Build and cache backend FEA components."""
        # TODO: Create and cache TorchFEA component objects.
        return None

    def assign_components(self) -> None:
        """Attach cached components and load steps to the Assembly."""
        # TODO: Attach components and load steps to the current Assembly.
        return None

    def build_case_assemblies(self) -> None:
        """Prepare case views while retaining one shared Assembly object."""
        # LoadStep stores the values that differ by case; geometry/material
        # state remains on the single Assembly owned by Params.
        self._case_assemblies = tuple(self._assembly for _ in self._steps)

    def get_case_assemblies(self) -> tuple[torchfea.Assembly, ...]:
        """Read already-built case Assemblies."""
        return self._case_assemblies

    def build_meshes(self) -> None:
        """Build FEA result preview caches."""
        self._meshes = ()

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Read the FEA preview cache."""
        return self._meshes

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist component and load-step metadata."""
        # TODO: Persist component definitions and step metadata.
        return None

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Restore component and load-step metadata."""
        # TODO: Restore component definitions and step metadata.
        return None
