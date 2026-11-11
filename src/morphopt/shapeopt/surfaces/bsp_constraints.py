"""Symmetry and relation constraints for BSP control nets."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from ...constants import CONSTANT
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
        surface.control_points = self._project(surface)

    def _project(self, surface: BspSurface) -> torch.Tensor:
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
        return projected.reshape_as(surface.control_points)

    def reinitialize(self, surface: BspSurface) -> None:
        self.apply(surface)
        surface.synchronize()


class BspZMirrorConstraint(BspMirrorConstraint):
    """Mirror about the initial axial mid-plane and preserve fixed end coordinates."""

    def __init__(self) -> None:
        super().__init__(plane="xy")

    def validate_surface(self, surface: BspSurface) -> None:
        super().validate_surface(surface)
        points = surface.model.control_points.reshape(*surface.model.size, 3)
        self.offset = float((points[0, :, 2].mean() + points[-1, :, 2].mean()) / 2)

    def apply(self, surface: BspSurface) -> None:
        change = self._project(surface) - surface.control_points
        surface.control_points = surface.control_points + surface.constrain_displacements(change)

    def reinitialize(self, surface: BspSurface) -> None:
        self.validate_surface(surface)
        super().reinitialize(surface)


class BspZAntisymmetryConstraint(BspZMirrorConstraint):
    """Turn the upper/lower halves by 180 degrees about their mid-height X axis.

    The axis passes through the initial cross-section center in Y. The U roll
    accounts for the clockwise cylindrical control-net phase before reflecting
    Y, so an undeformed cylinder and its fixed end rings remain unchanged.
    """

    def validate_surface(self, surface: BspSurface) -> None:
        super().validate_surface(surface)
        points = surface.model.control_points.reshape(*surface.model.size, 3)
        self._center_y = float(points[0, :, 1].mean())

    def _project(self, surface: BspSurface) -> torch.Tensor:
        points = surface.control_points.reshape(*surface.model.size, 3)
        reflected = torch.roll(points.flip(dims=(0, 1)), shifts=-1, dims=1)
        projected = torch.stack((
            (points[..., 0] + reflected[..., 0]) / 2,
            self._center_y + (points[..., 1] - reflected[..., 1]) / 2,
            self.offset + (points[..., 2] - reflected[..., 2]) / 2,
        ), dim=-1)
        return projected.reshape_as(surface.control_points)


class BspZPeriodicityConstraint(BaseSurfaceConstraints["BspSurface"]):
    """Repeat an axial control block while leaving both end guards untouched.

    Each end guard has FIXED_END_CONTROL_POINT_ROWS rows. The remaining net
    stores ``periods`` blocks plus ``degree`` wrapping rows. With the cylinder's
    uniform V knots this gives that many full translation periods in the
    interior; the clamped ends retain smooth B-spline transitions.
    """

    def __init__(self, periods: int = 2) -> None:
        if periods < 2 or int(periods) != periods:
            raise ValueError("periods must be an integer of at least 2.")
        self.periods = int(periods)
        self.period_length: float

    def validate_surface(self, surface: BspSurface) -> None:
        from .bsp_surface import BspSurface

        if not isinstance(surface, BspSurface):
            raise TypeError("BSP axial periodicity requires a BSP surface.")
        num_v = surface.model.size[0]
        guard = CONSTANT.KERNEL.SURFACE.FIXED_END_CONTROL_POINT_ROWS
        intervals = num_v - 2 * guard - surface.model.degree
        if intervals < self.periods * (surface.model.degree + 1) or intervals % self.periods:
            raise ValueError(
                "The axial control net must contain equal periods and wrapping "
                "rows outside the fixed ends. Construct the BSP cylinder with "
                "num_V_ratio=periods."
            )
        points = surface.model.control_points.reshape(*surface.model.size, 3)
        height = float(points[-1, :, 2].mean() - points[0, :, 2].mean())
        self.period_length = height * intervals / ((num_v - 1) * self.periods)

    def apply(self, surface: BspSurface) -> None:
        points = surface.control_points.reshape(*surface.model.size, 3)
        guard = CONSTANT.KERNEL.SURFACE.FIXED_END_CONTROL_POINT_ROWS
        degree = surface.model.degree
        count = (len(points) - 2 * guard - degree) // self.periods
        block = points[guard:guard + count]
        shift = points.new_tensor([0.0, 0.0, self.period_length])
        copies = [block + step * shift for step in range(self.periods)]
        wrapped = block[:degree] + self.periods * shift
        surface.control_points = torch.cat(
            [points[:guard], *copies, wrapped, points[-guard:]], dim=0,
        ).reshape_as(surface.control_points)

    def reinitialize(self, surface: BspSurface) -> None:
        self.validate_surface(surface)
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
