"""Constraint hooks and reusable control-point surface constraints."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Generic, TypeVar

import numpy as np
import torch

if TYPE_CHECKING:
    from .base_surface import BaseSurface, ControlPointSurface


SurfaceT = TypeVar("SurfaceT", bound="BaseSurface")
RelatedSurfaceT = TypeVar("RelatedSurfaceT", bound="ControlPointSurface")


def axis_rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    """Return the Rodrigues rotation matrix for a unit axis and angle in radians.

    Args:
        axis (np.ndarray): Rotation or section axis in the form accepted by the operation.
        angle (float): Rotation angle in radians.

    Returns:
        np.ndarray: The Rodrigues rotation matrix for a unit axis and angle in radians.
    """
    x, y, z = axis
    cosine, sine = np.cos(angle), np.sin(angle)
    one_minus_cosine = 1.0 - cosine
    return np.array(
        [
            [cosine + x * x * one_minus_cosine,
             x * y * one_minus_cosine - z * sine,
             x * z * one_minus_cosine + y * sine],
            [y * x * one_minus_cosine + z * sine,
             cosine + y * y * one_minus_cosine,
             y * z * one_minus_cosine - x * sine],
            [z * x * one_minus_cosine - y * sine,
             z * y * one_minus_cosine + x * sine,
             cosine + z * z * one_minus_cosine],
        ]
    )


class BaseSurfaceConstraints(ABC, Generic[SurfaceT]):
    """Base class for constraints owned by a surface.

    ``apply`` runs after parameter updates. ``reinitialize`` runs after the
    surface rebuilds its control mesh or correspondence data.
    """

    related: SurfaceT

    def validate_surface(self, surface: SurfaceT) -> None:
        """Check that related surfaces use the same interface type.

        Args:
            surface (SurfaceT): Surface interface to register, evaluate, or constrain.
        """
        if hasattr(self, "related") and type(surface) != type(self.related):
            raise TypeError("Related surfaces must have the same interface type.")

    @abstractmethod
    def apply(self, surface: SurfaceT) -> None:
        """Project control tensors without NumPy conversion or CAD synchronization.

        This hook also runs inside the differentiable subproblem. External geometry is synchronized
        during reinitialization and mesh preparation.

        Args:
            surface (SurfaceT): Surface interface to register, evaluate, or constrain.
        """

    @abstractmethod
    def reinitialize(self, surface: SurfaceT) -> None:
        """Refresh any cached data after the surface is rebuilt.

        Args:
            surface (SurfaceT): Surface interface to register, evaluate, or constrain.
        """


class SurfaceRelationConstraint(
    BaseSurfaceConstraints[RelatedSurfaceT], Generic[RelatedSurfaceT]
):
    """Base class for copying one control-point surface to another."""

    def __init__(
        self,
        related: RelatedSurfaceT,
        pose: Sequence[float] | np.ndarray = (
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ),
    ) -> None:
        """Initialize SurfaceRelationConstraint and its configuration state.

        Args:
            related (RelatedSurfaceT): Follower surface receiving the source surface's transformed
                geometry.
            pose (Sequence[float] | np.ndarray): Rigid pose [tx, ty, tz, rx, ry, rz]; the last three
                entries form a rotation vector in radians.
        """
        self.related = related
        self.pose = np.asarray(pose, dtype=float)
        if self.pose.shape != (6,):
            raise ValueError("pose must have six components [tx, ty, tz, rx, ry, rz].")

    def apply(self, surface: RelatedSurfaceT) -> None:
        """Apply the SurfaceRelationConstraint state.

        Args:
            surface (RelatedSurfaceT): Surface interface to register, evaluate, or constrain.
        """
        source = surface.control_points
        rotation, shift = self._pose_transform()
        rotation = torch.as_tensor(rotation, dtype=source.dtype, device=source.device)
        shift = torch.as_tensor(shift, dtype=source.dtype, device=source.device)
        self.related.control_points = source @ rotation.T + shift

    def reinitialize(self, surface: RelatedSurfaceT) -> None:
        """Reinitialize the SurfaceRelationConstraint state.

        Args:
            surface (RelatedSurfaceT): Surface interface to register, evaluate, or constrain.
        """
        self._copy_surface_data(surface)
        self.apply(surface)
        self.related.synchronize()
        self._reinitialize_related()

    @abstractmethod
    def _copy_surface_data(self, surface: RelatedSurfaceT) -> None:
        """Copy backend-specific topology and configuration to ``related``.

        Args:
            surface (RelatedSurfaceT): Surface interface to register, evaluate, or constrain.
        """

    @abstractmethod
    def _reinitialize_related(self) -> None:
        """Refresh backend-specific derived data on ``related``."""

    def _pose_transform(self) -> tuple[np.ndarray, np.ndarray]:
        """Convert the stored translation and rotation vector to a rigid transformation.

        Returns:
            tuple[np.ndarray, np.ndarray]: Rotation matrix with shape (3, 3) and translation vector
                with shape (3,).
        """
        translation = self.pose[:3]
        rotation_vector = self.pose[3:]
        angle = np.linalg.norm(rotation_vector)
        if angle < 1e-12:
            return np.eye(3), translation
        return axis_rotation(rotation_vector / angle, angle), translation
