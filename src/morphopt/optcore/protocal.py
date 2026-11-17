"""Protocols shared by MorphOpt model objects."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import pyvista as pv
import torch
import torchfea

from ..constants import CONSTANT

__all__ = [
    "ProtocalHistory",
    "ProtocalInitializable",
    "ProtocalSavable",
    "ProtocalUpdatable",
    "ProtocalVisualizable",
]


class ProtocalHistory(ABC):
    """Expose this object's iteration fields as an ordinary dictionary.

    Providers own their field names and may return nested data. History copies
    tensors and arrays when appending; this hook must not advance optimization.
    Objects without history information contribute no fields.
    """

    def history_data(self) -> dict[str, object]:
        """Return this component's current iteration fields without advancing its state.

        Returns:
            dict[str, object]: Component-owned scalar or nested observations for the current
                iteration.
        """
        return {}


class ProtocalInitializable(ABC):
    """Protocol for objects with initialization lifecycle hooks."""

    def initialize(self, *args: object, **kwargs: object) -> None:
        """Initialize the object before the optimization starts.

        Args:
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """

    def reinitialize(self, *args: object, **kwargs: object) -> None:
        """Refresh runtime state using the inputs required by the concrete object.

        Args:
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """


class ProtocalSavable(ABC):
    """Protocol for objects with persistence and result-path hooks."""

    def save(self, foldpath: str, iteration: int) -> None:
        """Save the object state.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """

    def load(self, foldpath: str, iteration: int) -> None:
        """Load the object state.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """

    def pathlog_required(self) -> list[str]:
        """Return result subdirectories required by the object.

        Returns:
            list[str]: Relative log subdirectory names required before persistence.
        """
        return []

    def save_directory(self, foldpath: str, name: str | None = None) -> str:
        """Return and create this object's namespaced save directory.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            name (str | None): Name identifying the item in its owning collection.

        Returns:
            str: Created namespaced save directory under foldpath.
        """
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
        """Return meshes contributed by the object.

        Returns:
            list[pv.DataSet]: Visualization meshes in component registration order.
        """
        return []

    def plot(
        self,
        plotter: pv.Plotter | None = None,
        meshes: list[pv.DataSet] | None = None,
    ) -> pv.Plotter:
        """Add the object's visualization to a PyVista plotter.

        Args:
            plotter (pv.Plotter | None): PyVista plotter receiving the scene; None creates a new
                plotter.
            meshes (list[pv.DataSet] | None): Optional precomputed visualization meshes; None
                obtains meshes from the model.

        Returns:
            pv.Plotter: Add the object's visualization to a PyVista plotter.
        """
        if plotter is None:
            plotter = pv.Plotter()
        return plotter


class ProtocalUpdatable(ABC):
    """Protocol shared by updateable geometry and material interfaces."""

    @property
    @abstractmethod
    def num_variables(self) -> int:
        """Number of scalar design variables.

        Returns:
            int: Number of scalar coordinates in this interface's active design vector.
        """
        raise NotImplementedError

    @abstractmethod
    def get_parameters(self) -> list[torch.Tensor]:
        """Return the current parameter tensors.

        Returns:
            list[torch.Tensor]: Parameter tensors in the interface's design-variable block order.
        """
        raise NotImplementedError

    def get_variables(self) -> torch.Tensor:
        """Return the initial perturbation vector used by the updater.

        Returns:
            torch.Tensor: Initial flattened perturbation vector used to construct the subproblem.
        """
        values = self.get_parameters()
        if not values:
            return torch.zeros(0)
        return torch.cat(
            [
                torch.randn_like(value.flatten())
                * CONSTANT.KERNEL.SIMP.INITIAL_VARIABLE_NOISE
                for value in values
            ]
        )

    @abstractmethod
    def set_parameters(self, values: list[torch.Tensor]) -> None:
        """Restore the current parameter tensors.

        Args:
            values (list[torch.Tensor]): Values aligned with the parameters or records processed by
                this interface.
        """
        raise NotImplementedError

    @abstractmethod
    def update_variables(
        self,
        x_change: torch.Tensor,
        max_step_length: list[torch.Tensor] | torch.Tensor | None = None,
    ) -> None:
        """Apply a design-variable update.

        Args:
            x_change (torch.Tensor): Design-variable increment in this interface's flattened
                parameter order.
            max_step_length (list[torch.Tensor] | torch.Tensor | None): Updater-owned movement
                limits in the target's parameter-block order.
        """
        raise NotImplementedError

    @abstractmethod
    def obtain_design_sensitivity_vars(
        self, assembly: torchfea.Assembly
    ) -> torch.Tensor:
        """Return the variables used for sensitivity analysis.

        Args:
            assembly (torchfea.Assembly): TorchFEA assembly containing the registered Parts,
                Instances, loads, and reference points.

        Returns:
            torch.Tensor: The variables used for sensitivity analysis.
        """
        raise NotImplementedError

    @abstractmethod
    def modify_assembly(
        self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly
    ) -> None:
        """Apply sensitivity variables to the current assembly.

        Args:
            design_sensitivity_vars (torch.Tensor): Differentiable design-variable tensor used to
                modify the assembly.
            assembly (torchfea.Assembly): TorchFEA assembly containing the registered Parts,
                Instances, loads, and reference points.
        """
        raise NotImplementedError
