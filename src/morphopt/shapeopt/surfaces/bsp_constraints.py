"""Symmetry and relation constraints for BSP control nets."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from .base_constraints import BaseSurfaceConstraints, SurfaceRelationConstraint

if TYPE_CHECKING:
    from .bsp_surface import BspSurface


class BspMirrorConstraint(BaseSurfaceConstraints["BspSurface"]):
    """Mirror a BSP control net across xz or a horizontal xy plane.

    This assumes the BSP control net stores the mirror pairs at corresponding
    grid indices. The supported planes are ``xz`` (``y = 0``) and ``xy``
    (``z = offset``).
    """

    def __init__(self, plane: str = "xz", offset: float = 0.0) -> None:
        self.plane = plane.lower()
        if self.plane not in {"xz", "xy"}:
            raise NotImplementedError(
                "BSP supports mirror symmetry only across xz (y=0) or "
                "xy (z=offset) planes."
            )
        if self.plane == "xz" and offset != 0.0:
            raise NotImplementedError("BSP xz symmetry is defined on y=0.")

        self.offset = float(offset)

    def validate_surface(self, surface: BspSurface) -> None:
        from .bsp_surface import BspSurface

        if not isinstance(surface, BspSurface):
            raise TypeError("BSP symmetry constraints require a BSP surface.")

    def apply(self, surface: BspSurface) -> None:
        num_v, num_u = surface.model.size
        control_points = surface.control_points.reshape(num_v, num_u, 3)

        if self.plane == "xz":
            reflected = control_points.flip(dims=[1])
            axis = 1
            plane_offset = 0.0
        else:
            reflected = control_points.flip(dims=[0])
            axis = 2
            plane_offset = self.offset

        projected = 0.5 * (control_points + reflected)
        anti_symmetric = plane_offset + 0.5 * (
            control_points[..., axis] - reflected[..., axis]
        )
        projected = torch.cat(
            (
                projected[..., :axis],
                anti_symmetric.unsqueeze(-1),
                projected[..., axis + 1 :],
            ),
            dim=-1,
        )
        surface.control_points = projected.reshape_as(surface.control_points)

    def reinitialize(self, surface: BspSurface) -> None:
        self.apply(surface)
        surface.synchronize()


class BspRotationalSymmetryConstraint(BaseSurfaceConstraints["BspSurface"]):
    """Repeat the first circumferential sector around the global Z axis.

    BSP cylinder control points run clockwise in U. Sector ``k`` therefore
    copies the first sector through ``-2*pi*k/order``; Z coordinates are copied
    unchanged. The circumferential control-point count must divide into equal
    sectors (use ``num_U_ratio=order`` when constructing the cylinder).
    """

    def __init__(self, order: int = 2) -> None:
        if order < 2 or int(order) != order:
            raise ValueError("order must be an integer of at least 2.")
        self.order = int(order)

    def validate_surface(self, surface: BspSurface) -> None:
        from .bsp_surface import BspSurface

        if not isinstance(surface, BspSurface):
            raise TypeError("BSP rotational symmetry requires a BSP surface.")
        if surface.model.size[1] % self.order:
            raise ValueError(
                "The circumferential control-point count must be divisible by "
                "order. Construct the BSP cylinder with num_U_ratio=order."
            )

    def apply(self, surface: BspSurface) -> None:
        num_v, num_u = surface.model.size
        points = surface.control_points.reshape(num_v, num_u, 3)
        sector = points[:, :num_u // self.order]
        sectors = []
        for step in range(self.order):
            angle = -math.tau * step / self.order
            cosine, sine = math.cos(angle), math.sin(angle)
            sectors.append(torch.stack((
                cosine * sector[..., 0] - sine * sector[..., 1],
                sine * sector[..., 0] + cosine * sector[..., 1],
                sector[..., 2],
            ), dim=-1))
        surface.control_points = torch.cat(sectors, dim=1).reshape_as(
            surface.control_points
        )

    def reinitialize(self, surface: BspSurface) -> None:
        self.validate_surface(surface)
        self.apply(surface)
        surface.synchronize()


class BspSurfaceRelationConstraint(SurfaceRelationConstraint["BspSurface"]):
    """Copy a BSP basis and transformed control points to another BSP surface."""

    def validate_surface(self, surface: BspSurface) -> None:
        super().validate_surface(surface)
        from .bsp_surface import BspSurface

        if not isinstance(surface, BspSurface):
            raise TypeError("BSP surface relations require BSP surfaces.")

    def _copy_surface_data(self, surface: BspSurface) -> None:
        self.related.model._basis = surface.model._basis
        self.related.model._size = surface.model._size
        self.related.model._degree = surface.model._degree

    def _reinitialize_related(self) -> None:
        self.related.initialize()
