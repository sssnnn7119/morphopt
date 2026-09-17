"""Shared lifecycle for all native TorchFEA components."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from morphopt._torch import torch
import pyvista
import torchfea


class BaseFEAComponent:
    """Declare one load, boundary, constraint, or interaction.

    A component carries only definition data and default load values.  It
    creates one native TorchFEA object for the current Assembly.  Per-case
    values live in ``LoadValueBlock`` objects, so all load cases share this
    same native component and Assembly without copying the finite-element
    model.
    """

    def __init__(
        self,
        name: str,
        *,
        default_values: Iterable[float] = (),
        target_names: Iterable[str] = (),
    ) -> None:
        self._name = str(name)
        """Stable component name used for registration and Jacobians."""
        self._default_values = tuple(float(value) for value in default_values)
        """Values used to initialize a new load step."""
        self._target_names = tuple(str(name) for name in target_names)
        """Declared Instance, set, or reference-point names."""
        self._torchfea_Assembly: torchfea.Assembly | None = None
        """Assembly currently bound by ``reinitialize()``."""
        self._torchfea_Component: torchfea.Serializable | None = None
        """Native load, boundary, constraint, or interaction object."""
        self._meshes: tuple[pyvista.DataSet, ...] = ()
        """Cached component visualization meshes."""

    @property
    def name(self) -> str:
        """Return the stable component name."""
        return self._name

    @property
    def default_values(self) -> tuple[float, ...]:
        """Return values assigned to each newly created load step."""
        return self._default_values

    @default_values.setter
    def default_values(self, values: Iterable[float]) -> None:
        """Replace default values after validating their fixed length."""
        value_tuple = tuple(float(value) for value in values)
        if len(value_tuple) != self.num_values:
            raise ValueError(f"{self._name} requires {self.num_values} values")
        self._default_values = value_tuple

    @property
    def num_values(self) -> int:
        """Return the number of scalar values controlled in each load step."""
        return len(self._default_values)

    @property
    def target_names(self) -> tuple[str, ...]:
        """Return declared backend object names without resolving them."""
        return self._target_names

    def initialize(self) -> None:
        """Prepare definition-only component state."""
        return None

    def reinitialize(self, iteration: int, assembly: torchfea.Assembly) -> None:
        """Bind the current Assembly before creating a native component."""
        self._torchfea_Assembly = assembly
        self._torchfea_Component = None

    def build_fea(self) -> None:
        """Create and cache this component's native TorchFEA object."""
        self._torchfea_Component = self._create_fea_object()
        self._apply_values(torch.tensor(self._default_values))

    def get_fea_object(self) -> torchfea.Serializable:
        """Read the native object created by ``build_fea()``."""
        if self._torchfea_Component is None:
            raise RuntimeError(f"Component {self._name!r} has not been built")
        return self._torchfea_Component

    def assign_fea(self) -> None:
        """Attach the cached native component to the current Assembly."""
        assembly = self._torchfea_Assembly
        component = self.get_fea_object()
        if self._attachment_name == "load":
            assembly.add_load(component, self._name)
        elif self._attachment_name == "boundary":
            assembly.add_boundary(component, self._name)
        else:
            assembly.add_constraint(component, self._name)

    def update_fea(self, values: torch.Tensor) -> None:
        """Write one load case's values to the already-built native object."""
        values = torch.as_tensor(values, dtype=torch.get_default_dtype())
        if values.numel() != self.num_values:
            raise ValueError(f"{self._name} requires {self.num_values} values")
        self._apply_values(values.reshape(-1))

    def build_meshes(self) -> None:
        """Build and cache component preview geometry."""
        self._meshes = self._build_preview_meshes()

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Read already-built component preview geometry."""
        return self._meshes

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Save definition metadata for one result iteration."""
        return None

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Load definition metadata for one result iteration."""
        return None

    @property
    def _attachment_name(self) -> str:
        """Return the Assembly registration method selected by subclasses."""
        return "load"

    def _create_fea_object(self) -> torchfea.Serializable:
        """Create the component-specific native TorchFEA object."""
        raise NotImplementedError

    def _apply_values(self, values: torch.Tensor) -> None:
        """Write a validated per-step value vector to the native object."""
        return None

    def _build_preview_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Create component-specific preview geometry for the shared viewer."""
        return ()
