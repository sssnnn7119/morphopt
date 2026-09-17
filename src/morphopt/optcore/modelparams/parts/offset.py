"""Inward offset-shell geometry derived from an editable boundary Part."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista
from morphopt._torch import torch

from .boundary import BoundaryPart
from ..surfaces.stl import STLSurface


class OffsetShellPart(BoundaryPart):
    """Build an inward-offset solid that reuses one BoundaryPart's variables."""

    def __init__(
        self,
        part_name: str,
        source_part: BoundaryPart,
        source_surface: list[bool],
        offset_distance: float,
        *,
        element_name: str = "solid",
        fea_seed_size: float | None = None,
        mesh_order: int = 1,
    ) -> None:
        super().__init__(
            part_name,
            element_name=element_name,
            fea_seed_size=fea_seed_size,
            mesh_order=mesh_order,
        )
        self._source_part = source_part
        """Editable BoundaryPart supplying the shared control-point variables."""
        self._source_surface = tuple(bool(value) for value in source_surface)
        """Surface flags: index zero is original; later True entries are offset inward."""
        self._offset_distance = float(offset_distance)
        """Fixed inward normal offset applied to selected source surfaces."""

    @property
    def source_part(self) -> BoundaryPart:
        """Return the BoundaryPart that owns this Part's design variables."""
        return self._source_part

    @property
    def source_surface(self) -> tuple[bool, ...]:
        """Return stable inward-offset selection flags in source surface order."""
        return self._source_surface

    @property
    def offset_distance(self) -> float:
        """Return the configured inward normal distance."""
        return self._offset_distance

    def define_surfaces(self) -> None:
        """Build fixed STL proxy surfaces from current source-surface geometry."""
        if len(self._source_surface) != len(self._source_part.surfaces):
            raise ValueError("source_surface must match the source Part surface count")
        if self._source_surface[0]:
            raise ValueError("source_surface[0] must be False for the original exterior")
        for index, source in enumerate(self._source_part.surfaces):
            source.build_meshes()
            mesh = source.get_meshes()[0].triangulate()
            vertices = np.asarray(mesh.points, dtype=float).copy()
            faces = np.asarray(mesh.faces, dtype=np.int64).reshape(-1, 4)[:, 1:]
            if self._source_surface[index]:
                normals = mesh.compute_normals(
                    point_normals=True, cell_normals=False, auto_orient_normals=True
                ).point_data["Normals"]
                vertices -= self._offset_distance * np.asarray(normals, dtype=float)
            self.add_surface(STLSurface(vertices=vertices, faces=faces))

    def get_parameters(self) -> torch.Tensor:
        """Read the source boundary's committed control-point vector."""
        return self._source_part.get_parameters()

    def set_parameters(self, parameters: torch.Tensor) -> None:
        """Commit parameters to the shared source boundary Part."""
        self._source_part.set_parameters(parameters)

    def build_design_delta(self) -> None:
        """Build a local delta with the source boundary's parameter layout."""
        self._design_delta = torch.zeros_like(self._source_part.get_parameters())

    def update_assembly(self, design_delta: torch.Tensor) -> None:
        """Delegate trial source updates then refresh this offset Part geometry."""
        self._source_part.update_assembly(design_delta)
        self._design_delta = torch.as_tensor(design_delta)

    def apply_design_delta(self, changes: torch.Tensor) -> None:
        """Commit through the source Part and regenerate offset proxy surfaces."""
        self._source_part.apply_design_delta(changes)
        self.reinitialize(0)

    def reinitialize(self, iteration: int) -> None:
        """Regenerate offset STL proxies after source geometry has changed."""
        self._surfaces.clear()
        self.define_surfaces()
        for index, surface in enumerate(self._surfaces):
            surface._set_name(f"surface_{index}_offset")
            surface._set_flip(index > 0)
            surface.initialize()
        self._control_point_shapes = tuple(
            surface.get_surface_parameters().shape for surface in self._surfaces
        )
        super().reinitialize(iteration)
