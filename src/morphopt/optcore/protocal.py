"""Protocols shared by MorphOpt model objects."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import pyvista as pv
import torch
import torchfea

__all__ = [
    "ProtocalInitializable",
    "ProtocalSavable",
    "ProtocalUpdatable",
    "ProtocalVisualizable",
]


class ProtocalInitializable(ABC):
    """Protocol for objects with initialization lifecycle hooks."""

    def initialize(self, *args: object, **kwargs: object) -> None:
        """Initialize the object before the optimization starts."""

    def reinitialize(self, iteration: int, *args: object, **kwargs: object) -> None:
        """Refresh the object at the beginning of an optimization iteration."""


class ProtocalSavable(ABC):
    """Protocol for objects with persistence and result-path hooks."""

    def save(self, foldpath: str, iteration: int) -> None:
        """Save the object state."""

    def load(self, foldpath: str, iteration: int) -> None:
        """Load the object state."""

    def pathlog_required(self) -> list[str]:
        """Return result subdirectories required by the object."""
        return []

    def save_directory(self, foldpath: str, name: str | None = None) -> str:
        """Return and create this object's namespaced save directory."""
        paths = self.pathlog_required()
        if not paths:
            raise ValueError(
                f"{type(self).__name__} must define a log path before saving state."
            )
        directory = os.path.join(str(foldpath), paths[0])
        if name:
            directory = os.path.join(directory, str(name))
        os.makedirs(directory, exist_ok=True)
        return directory


class ProtocalVisualizable(ABC):
    """Protocol for objects that expose meshes and a PyVista plot hook."""

    def get_meshes(self) -> list[pv.DataSet]:
        """Return meshes contributed by the object."""
        return []

    def plot(
        self,
        plotter: pv.Plotter | None = None,
        meshes: list[pv.DataSet] | None = None,
    ) -> pv.Plotter:
        """Add the object's visualization to a PyVista plotter."""
        if plotter is None:
            plotter = pv.Plotter()
        return plotter


class ProtocalUpdatable(ABC):
    """Protocol shared by updateable geometry and material interfaces."""

    @property
    @abstractmethod
    def num_variables(self) -> int:
        """Number of scalar design variables."""
        raise NotImplementedError

    @abstractmethod
    def get_parameters(self) -> list[torch.Tensor]:
        """Return the current parameter tensors."""
        raise NotImplementedError

    def get_variables(self) -> torch.Tensor:
        """Return the initial perturbation vector used by the updater."""
        values = self.get_parameters()
        if not values:
            return torch.zeros(0)
        return torch.cat([torch.randn_like(value.flatten()) * 1e-6 for value in values])

    @abstractmethod
    def set_parameters(self, values: list[torch.Tensor]) -> None:
        """Restore the current parameter tensors."""
        raise NotImplementedError

    @abstractmethod
    def update_variables(
        self,
        x_change: torch.Tensor,
        max_step_length: list[torch.Tensor | None] | torch.Tensor | None = None,
    ) -> None:
        """Apply a design-variable update."""
        raise NotImplementedError

    @abstractmethod
    def obtain_design_sensitivity_vars(
        self, assembly: torchfea.Assembly
    ) -> torch.Tensor:
        """Return the variables used for sensitivity analysis."""
        raise NotImplementedError

    @abstractmethod
    def modify_assembly(
        self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly
    ) -> None:
        """Apply sensitivity variables to the current assembly."""
        raise NotImplementedError
