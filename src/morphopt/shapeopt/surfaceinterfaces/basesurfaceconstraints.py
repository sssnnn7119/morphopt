"""Constraint hooks and reusable control-point surface constraints."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Generic, TypeVar

import numpy as np

if TYPE_CHECKING:
    from .basesurfaceinterface import BaseSurfaceInterface, CpBasedSurfaceInterface


SurfaceInterfaceT = TypeVar("SurfaceInterfaceT", bound="BaseSurfaceInterface")
RelatedSurfaceT = TypeVar("RelatedSurfaceT", bound="CpBasedSurfaceInterface")


class BaseSurfaceConstraints(ABC, Generic[SurfaceInterfaceT]):
    """Base class for constraints owned by a surface interface.

    ``apply`` runs after parameter updates. ``reinitialize`` runs after the
    surface rebuilds its control mesh or correspondence data.
    """

    related: SurfaceInterfaceT

    def validate_surface(self, surface: SurfaceInterfaceT) -> None:
        """Check that related surfaces use the same interface type."""
        if hasattr(self, "related") and type(surface) != type(self.related):
            raise TypeError("Related surfaces must have the same interface type.")

    @abstractmethod
    def apply(self, surface: SurfaceInterfaceT) -> None:
        """Apply this constraint to the current surface geometry."""

    @abstractmethod
    def reinitialize(self, surface: SurfaceInterfaceT) -> None:
        """Refresh any cached data after the surface is rebuilt."""


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
        self.related = related
        self.pose = np.asarray(pose, dtype=float)
        if self.pose.shape != (6,):
            raise ValueError(
                "pose must have six components [tx, ty, tz, rx, ry, rz]."
            )

    def apply(self, surface: RelatedSurfaceT) -> None:
        source = surface.control_points.detach().cpu().numpy()
        rotation, shift = self._pose_transform()
        self.related.control_points = source @ rotation.T + shift
        self.related.synchronize()

    def reinitialize(self, surface: RelatedSurfaceT) -> None:
        self._copy_surface_data(surface)
        self.apply(surface)
        self._reinitialize_related()

    @abstractmethod
    def _copy_surface_data(self, surface: RelatedSurfaceT) -> None:
        """Copy backend-specific topology and configuration to ``related``."""

    @abstractmethod
    def _reinitialize_related(self) -> None:
        """Refresh backend-specific derived data on ``related``."""

    def _pose_transform(self) -> tuple[np.ndarray, np.ndarray]:
        translation = self.pose[:3]
        rotation_vector = self.pose[3:]
        angle = np.linalg.norm(rotation_vector)
        if angle < 1e-12:
            return np.eye(3), translation
        return self._axis_rotation(rotation_vector / angle, angle), translation

    @staticmethod
    def _axis_rotation(axis: np.ndarray, angle: float) -> np.ndarray:
        x, y, z = axis
        cosine, sine = np.cos(angle), np.sin(angle)
        one_minus_cosine = 1.0 - cosine
        return np.array(
            [
                [
                    cosine + x * x * one_minus_cosine,
                    x * y * one_minus_cosine - z * sine,
                    x * z * one_minus_cosine + y * sine,
                ],
                [
                    y * x * one_minus_cosine + z * sine,
                    cosine + y * y * one_minus_cosine,
                    y * z * one_minus_cosine - x * sine,
                ],
                [
                    z * x * one_minus_cosine - y * sine,
                    z * y * one_minus_cosine + x * sine,
                    cosine + z * z * one_minus_cosine,
                ],
            ]
        )
