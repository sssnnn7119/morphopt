"""Updateable SIMP material density field."""

from __future__ import annotations

from morphopt._torch import torch
import pyvista

from .base import BaseMaterialInterface
from .parameters import MaterialParameters


class SIMPFieldMaterial(BaseMaterialInterface):
    """Updateable BSP density field used by SIMP material optimization."""
    def __init__(self, name: str, part_name: str, element_name: str, material_parameters: MaterialParameters, *, control_points: torch.Tensor | None = None, initial_ratio: float = 0.5, mumax: float = 1.0, kappamax: float = 1.0) -> None:
        super().__init__(name, part_name, element_name, material_parameters)
        self._control_points = torch.as_tensor(control_points if control_points is not None else torch.zeros((0,))).clone()
        """Editable density-field parameters."""
        self._design_delta = torch.zeros_like(self._control_points)
        """Trial density-field delta."""
        self._density_meshes: tuple[pyvista.DataSet, ...] = ()
        """Cached density visualization meshes."""
        self._initial_ratio = float(initial_ratio)
        """Initial density ratio used to seed the field."""
        self._mumax = float(mumax)
        """Maximum shear interpolation parameter."""
        self._kappamax = float(kappamax)
        """Maximum bulk interpolation parameter."""

    @property
    def mumax(self) -> float:
        """Return the maximum shear/material interpolation value."""
        return self._mumax

    @property
    def kappamax(self) -> float:
        """Return the maximum bulk/material interpolation value."""
        return self._kappamax

    @property
    def initial_ratio(self) -> float:
        """Return the initial density ratio."""
        return self._initial_ratio

    @property
    def degree(self) -> int:
        """Return the density-field BSP degree."""
        return 0

    def get_parameters(self) -> torch.Tensor:
        """Read committed density-field control points."""
        return self._control_points

    def set_parameters(self, parameters: torch.Tensor) -> None:
        """Replace committed density-field control points."""
        self._control_points = torch.as_tensor(parameters).detach().clone()

    def build_design_delta(self) -> None:
        """Build a zero local delta with the density-field shape."""
        self._design_delta = torch.zeros_like(self._control_points)

    def get_design_delta(self) -> torch.Tensor:
        """Read the current density trial delta."""
        return self._design_delta

    def set_design_delta(self, values: torch.Tensor) -> None:
        """Set the Registry-provided density trial view."""
        self._design_delta = torch.as_tensor(values)

    def update_assembly(self, design_delta: torch.Tensor) -> None:
        """Update backend material values for a trial density field."""
        self._design_delta = torch.as_tensor(design_delta)
        # TODO: Update TorchFEA material parameters while preserving autograd.

    def apply_design_delta(self, changes: torch.Tensor) -> None:
        """Commit a validated density-field change."""
        self._control_points = self._control_points + torch.as_tensor(changes).detach()
        self._design_delta = torch.zeros_like(self._control_points)

    def build_material(self) -> None:
        """Build and cache interpolated backend material values."""
        # TODO: Build density field and write interpolated material values.
        self._torchfea_Material = None

    def build_meshes(self) -> None:
        """Build/cache density-field preview meshes."""
        self._density_meshes = ()

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Read density-field preview meshes."""
        return self._density_meshes
