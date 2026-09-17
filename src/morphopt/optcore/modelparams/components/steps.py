"""Load-step and design-value block definitions."""

from __future__ import annotations

from typing import Iterable

from morphopt._torch import torch
import torchfea

from .base import BaseFEAComponent


class LoadStep:
    """Ordered collection of FEA components forming one load case."""
    def __init__(self, name: str, components: Iterable[BaseFEAComponent] = ()) -> None:
        self._name = str(name)
        """Stable load-step name."""
        self._components: list[BaseFEAComponent] = list(components)
        """Components active in this load case."""
        self._torchfea_Step: torchfea.WorkCondition | None = None
        """Backend work-condition object."""

    @property
    def name(self) -> str:
        """Return the load-step name."""
        return self._name

    @property
    def components(self) -> tuple[BaseFEAComponent, ...]:
        """Return components in this load case."""
        return tuple(self._components)

    def add_component(self, component: BaseFEAComponent) -> BaseFEAComponent:
        """Append a component to this case."""
        self._components.append(component)
        return component

    def build_step(self, assembly: torchfea.Assembly | None = None) -> None:
        """Create/cache the backend work-condition object."""
        # TODO: Build TorchFEA work conditions for this load step.
        self._torchfea_Step = torchfea.WorkCondition()


class LoadValueBlock:
    """Design owner for one component's values in one load case."""
    def __init__(self, name: str, values: torch.Tensor | Iterable[float]) -> None:
        self._name = str(name)
        """Stable component-value owner name."""
        self._parameters = torch.as_tensor(values).clone()
        """Committed values for this load case."""
        self._design_delta = torch.zeros_like(self._parameters)
        """Trial values routed by the Registry."""
        self._torchfea_Component: torchfea.loads.BaseLoad | None = None
        """Shared backend component receiving values."""

    @property
    def name(self) -> str:
        """Return the load-value block name."""
        return self._name

    def get_parameters(self) -> torch.Tensor:
        """Read committed load values."""
        return self._parameters

    def set_parameters(self, parameters: torch.Tensor) -> None:
        """Replace committed load values."""
        self._parameters = torch.as_tensor(parameters).detach().clone()

    def build_design_delta(self) -> None:
        """Build a zero local load-value delta."""
        self._design_delta = torch.zeros_like(self._parameters)

    def get_design_delta(self) -> torch.Tensor:
        """Read the current local load-value delta."""
        return self._design_delta

    def set_design_delta(self, values: torch.Tensor) -> None:
        """Set the Registry-provided local trial view."""
        self._design_delta = torch.as_tensor(values)

    def update_assembly(self, design_delta: torch.Tensor) -> None:
        """Write trial values to the case-specific backend component."""
        self._design_delta = torch.as_tensor(design_delta)
        # TODO: Write trial values to the case-specific TorchFEA component.

    def apply_design_delta(self, changes: torch.Tensor) -> None:
        """Commit validated load-value changes."""
        self._parameters = self._parameters + torch.as_tensor(changes).detach()
        self._design_delta = torch.zeros_like(self._parameters)
