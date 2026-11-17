"""Symmetry constraints for CPGEO control meshes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np
import torch

from .base_constraints import (
    BaseSurfaceConstraints,
    SurfaceRelationConstraint,
    axis_rotation,
)

if TYPE_CHECKING:
    from .cpgeo_surface import CPGEOSurface


class _CPGEOSymmetryConstraint(BaseSurfaceConstraints["CPGEOSurface"]):
    """Share CPGEO control-mesh reconstruction and tensor-assignment helpers between symmetry
    projections.
    """
    def validate_surface(self, surface: CPGEOSurface) -> None:
        """Validate surface.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
        """
        from .cpgeo_surface import CPGEOSurface

        if not isinstance(surface, CPGEOSurface):
            raise TypeError("CPGEO symmetry constraints require a CPGEO surface.")

    @staticmethod
    def _finish_reinitialize(
        surface: CPGEOSurface,
        vertices: np.ndarray,
        faces: np.ndarray,
    ) -> None:
        """Install the reconstructed control mesh and rebuild the backend and preload caches.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
            vertices (np.ndarray): Cartesian vertex coordinates with shape (num_vertices, 3).
            faces (np.ndarray): Face selection or mesh connectivity required by the selected surface
                operation.
        """
        surface.control_points = vertices
        surface.model._control_points = vertices
        surface.model._cp_faces = faces
        surface.model.initialize()
        surface._num_knots = surface.model._knots.shape[0]
        surface.pre_load()

    @staticmethod
    def _set_control_points(surface: CPGEOSurface, points: torch.Tensor) -> None:
        """Set control points.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
            points (torch.Tensor): Point coordinates in the representation expected by this
                operation.
        """
        surface.control_points = points.reshape(-1, 3)


class CPGEOMirrorConstraint(_CPGEOSymmetryConstraint):
    """Mirror a CPGEO control mesh across a coordinate plane."""

    def __init__(self, plane: str = "yz", offset: float = 0.0) -> None:
        """Initialize CPGEOMirrorConstraint and its configuration state.

        Args:
            plane (str): Coordinate plane used for mirror symmetry.
            offset (float): Signed plane or surface offset in model length units.
        """
        self.plane = plane.lower()
        if self.plane not in {"xy", "xz", "yz"}:
            raise ValueError("plane must be one of 'xy', 'xz' or 'yz'.")
        self.offset = float(offset)

    def apply(self, surface: CPGEOSurface) -> None:
        """Apply the CPGEOMirrorConstraint state.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
        """
        axis = {"yz": 0, "xz": 1, "xy": 2}[self.plane]
        points = surface.control_points.reshape(2, -1, 3)[0]
        reflected = points.clone()
        reflected[:, axis] = 2.0 * self.offset - reflected[:, axis]
        self._set_control_points(surface, torch.cat((points, reflected), dim=0))

    def reinitialize(self, surface: CPGEOSurface) -> None:
        """Reinitialize the CPGEOMirrorConstraint state.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
        """
        import cpgeo

        axis = {"yz": 0, "xz": 1, "xy": 2}[self.plane]
        vertices = surface.control_points.detach().cpu().numpy().copy()
        vertices[:, axis] -= self.offset
        vertices, faces = cpgeo.utils.enforce_axial_symmetry(
            vertices,
            surface.model._cp_faces.copy(),
            plane=self.plane,
        )
        vertices[:, axis] += self.offset
        self._finish_reinitialize(surface, vertices, faces)


class CPGEORotationalSymmetryConstraint(_CPGEOSymmetryConstraint):
    """Apply finite rotational symmetry to a CPGEO control mesh."""

    def __init__(
        self,
        axis: str | Sequence[float] = "z",
        order: int = 2,
        center: Sequence[float] = (0.0, 0.0, 0.0),
    ) -> None:
        """Initialize CPGEORotationalSymmetryConstraint and its configuration state.

        Args:
            axis (str | Sequence[float]): Rotation or section axis in the form accepted by the
                operation.
            order (int): Rotational repetition count, or interpolation order for the selected
                operation.
            center (Sequence[float]): Cartesian center of the rotation or geometric construction.
        """
        if isinstance(axis, str):
            axes = {
                "x": (1.0, 0.0, 0.0),
                "y": (0.0, 1.0, 0.0),
                "z": (0.0, 0.0, 1.0),
            }
            if axis.lower() not in axes:
                raise ValueError("axis must be 'x', 'y', 'z' or a 3-vector.")
            axis = axes[axis.lower()]
        direction = np.asarray(axis, dtype=float)
        norm = np.linalg.norm(direction)
        if direction.shape != (3,) or norm == 0:
            raise ValueError("axis must be a non-zero 3-vector.")
        self.axis = direction / norm
        self.order = int(order)
        if self.order < 2:
            raise ValueError("order must be at least 2.")
        self.center = np.asarray(center, dtype=float)
        if self.center.shape != (3,):
            raise ValueError("center must contain three coordinates.")

    def apply(self, surface: CPGEOSurface) -> None:
        """Apply the CPGEORotationalSymmetryConstraint state.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
        """
        points = surface.control_points.reshape(self.order, -1, 3)[0]
        center = torch.as_tensor(self.center, dtype=points.dtype, device=points.device)
        sectors = []
        for step in range(self.order):
            angle = 2.0 * np.pi * step / self.order
            rotation = torch.as_tensor(
                axis_rotation(self.axis, angle),
                dtype=points.dtype,
                device=points.device,
            )
            sectors.append((points - center) @ rotation.T + center)
        self._set_control_points(surface, torch.cat(sectors, dim=0))

    def reinitialize(self, surface: CPGEOSurface) -> None:
        """Reinitialize the CPGEORotationalSymmetryConstraint state.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
        """
        import cpgeo

        vertices = surface.control_points.detach().cpu().numpy().copy()
        align = self._align_axis_to_z(self.axis)
        vertices = (vertices - self.center) @ align.T
        vertices, faces = cpgeo.utils.enforce_rotational_symmetry_z(
            vertices,
            surface.model._cp_faces.copy(),
            periods=self.order,
        )
        vertices = vertices @ align + self.center
        self._finish_reinitialize(surface, vertices, faces)

    @staticmethod
    def _align_axis_to_z(axis: np.ndarray) -> np.ndarray:
        """Construct a rotation that aligns the normalized symmetry axis with positive Z.

        Args:
            axis (np.ndarray): Rotation or section axis in the form accepted by the operation.

        Returns:
            np.ndarray: Rotation matrix with shape (3, 3).
        """
        target = np.array([0.0, 0.0, 1.0])
        cross = np.cross(axis, target)
        cosine = float(np.dot(axis, target))
        if np.linalg.norm(cross) < 1e-12:
            return np.eye(3) if cosine > 0 else np.diag([1.0, -1.0, -1.0])
        skew = np.array(
            [
                [0.0, -cross[2], cross[1]],
                [cross[2], 0.0, -cross[0]],
                [-cross[1], cross[0], 0.0],
            ]
        )
        return np.eye(3) + skew + skew @ skew / (1.0 + cosine)

class CPGEOSurfaceRelationConstraint(SurfaceRelationConstraint["CPGEOSurface"]):
    """Copy CPGEO topology and transformed control points to another surface."""

    def validate_surface(self, surface: CPGEOSurface) -> None:
        """Validate surface.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
        """
        super().validate_surface(surface)
        from .cpgeo_surface import CPGEOSurface

        if not isinstance(surface, CPGEOSurface):
            raise TypeError("CPGEO surface relations require CPGEO surfaces.")

    def _copy_surface_data(self, surface: CPGEOSurface) -> None:
        """Copy surface data.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
        """
        source = surface.model
        target = self.related.model
        target._cp_faces = source._cp_faces.copy()
        target._knot_influence_num = source._knot_influence_num
        match = source._symmetry_points_match
        target._symmetry_points_match = None if match is None else match.copy()
        self.related._is_first_initialize = surface._is_first_initialize
        if hasattr(surface, "_output_rsphere"):
            self.related._output_rsphere = surface._output_rsphere.copy()
        if hasattr(surface, "_output_cpfaces"):
            self.related._output_cpfaces = surface._output_cpfaces.copy()

    def _reinitialize_related(self) -> None:
        """Reinitialize related."""
        self.related.initialize()
        self.related._num_knots = self.related.model._knots.shape[0]
        self.related.pre_load()
