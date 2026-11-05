from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np
import torch

from ...constants import CONSTANT
from ...optcore.updaters import QuadraticHistory
from .basefuncs import BaseObjective

if TYPE_CHECKING:
    from ..surfaces import BaseSurface


class ShapeDerivative(BaseObjective):
    """
    First-order physical objective from the current shape gradient.
    """

    def __init__(self) -> None:
        super().__init__()

        self._cp0: list[torch.Tensor] = []
        """
        Initial control points of the surfaces, used for computing the shape derivative as the inner product of the change in control points and the sensitivity.
        """

        self.gradient: list[torch.Tensor] = []
        """Gradient of the shape derivative with respect to the control points, computed in the initialize function.
        """

    def initialize(
        self,
        gradient: torch.Tensor,
        r0: list[torch.Tensor],
        *args: object,
        surfaces: Sequence[BaseSurface] | None = None,
        **kwargs: object,
    ) -> None:
        """Map the structural gradient onto the control points of this Part.

        ``surfaces`` are the surface interfaces owned by the boundary Part this
        objective belongs to; ``r0`` are that Part's surface points.
        """

        if surfaces is None:
            raise ValueError("ShapeDerivative requires the updater's surfaces.")
        self.surfaces = list(surfaces)
        sflist = self.surfaces
        interpolate_points = [value.cpu().numpy() for value in r0]

        self._cp0 = []
        ptidx = 0
        self.gradient = []
        for sf_idx in range(len(sflist)):
            cp0_sf = (
                sflist[sf_idx].get_surface_parameters().detach().clone().reshape(-1, 3)
            )
            self._cp0.append(cp0_sf)
            self.gradient.append(
                gradient[ptidx : ptidx + cp0_sf.numel()].reshape_as(cp0_sf)
            )
            ptidx += cp0_sf.numel()

        self.sensitivity = self._sensitivity_interpolation(
            Ldot=gradient.reshape([-1, 3]),
            points_request=torch.cat(self._cp0, dim=0).reshape([-1, 3]),
            interpolated_points=interpolate_points,
        )

    def show_sensitivity(self, ind: int) -> None:
        """
        Show the shape sensitivity
        """

        import pyvista as pv

        plotter = pv.Plotter(window_size=(1000, 1000))
        plotter.set_background("white")

        r = self._r0[ind].detach().cpu().numpy()
        n = self.sensitivity[ind].detach().cpu().numpy()

        # r and n are [N, 3]
        points = r
        vectors = n

        # Debug: print statistics
        print(f"Points shape: {points.shape}")
        print(f"Vectors shape: {vectors.shape}")
        print(
            f"Vector magnitude range: [{np.linalg.norm(vectors, axis=1).min():.6e}, {np.linalg.norm(vectors, axis=1).max():.6e}]"
        )

        # Filter out zero vectors
        vector_norms = np.linalg.norm(vectors, axis=1)
        valid_mask = vector_norms > 1e-10

        if valid_mask.sum() == 0:
            print("Warning: All sensitivity vectors are zero!")
            return

        points_filtered = points[valid_mask]
        vectors_filtered = vectors[valid_mask]

        # Auto-scale magnitude based on model size
        model_size = np.max(points_filtered.max(axis=0) - points_filtered.min(axis=0))
        vector_mag = np.linalg.norm(vectors_filtered, axis=1).mean()
        mag_scale = model_size / vector_mag * 0.01  # Scale to 1% of model size

        print(f"Using {valid_mask.sum()} non-zero vectors out of {len(valid_mask)}")
        print(f"Auto-scaled magnitude: {mag_scale:.6e}")

        # Add surface mesh for context
        plotter.add_points(
            points_filtered, color="blue", point_size=5, render_points_as_spheres=True
        )

        # Add arrows with auto-scaled magnitude
        plotter.add_arrows(
            points_filtered, vectors_filtered, mag=mag_scale, color="red"
        )

        plotter.show_axes()
        plotter.show()

    def __call__(
        self,
        r: list[torch.Tensor],
        *args: object,
        **kwargs: object,
    ) -> torch.Tensor:
        loss_objective = 0.0

        if not self.surfaces:
            raise ValueError("ShapeDerivative requires the updater's surfaces.")

        for i in range(len(self.surfaces)):
            if not self.surfaces[i].is_updatable:
                continue
            # r[i], self._r0[i], self.sensitivity[i] are all [p, 3]
            # Compute inner product: sum over all points and dimensions
            loss_objective += (
                (
                    self.surfaces[i].get_surface_parameters().reshape(-1, 3)
                    - self._cp0[i]
                )
                * self.gradient[i]
            ).sum()

        return loss_objective


class QuadraticShapeDerivative(ShapeDerivative):
    """Historical quadratic shape objective with limited-memory BFGS curvature."""

    def __init__(
        self,
        memory_size: int = CONSTANT.KERNEL.UPDATER_OBJECTIVES.QUADRATIC_MEMORY_PAIRS,
    ) -> None:
        super().__init__()
        self.history = QuadraticHistory(memory_size)

    def initialize(
        self,
        gradient: torch.Tensor,
        r0: list[torch.Tensor],
        *args: object,
        surfaces: Sequence[BaseSurface],
        **kwargs: object,
    ) -> None:
        super().initialize(gradient, r0, *args, surfaces=surfaces, **kwargs)
        active_gradient = torch.cat(
            [
                value.flatten()
                for surface, value in zip(self.surfaces, self.gradient)
                if surface.is_updatable and surface.num_variables
            ]
        )
        layout = tuple(
            value
            for surface in self.surfaces
            for value in (surface.num_variables, int(surface.is_updatable))
        )
        self.history.observe(self._active_parameters(), active_gradient, layout)

    def _active_parameters(self) -> torch.Tensor:
        """Physical control coordinates of active surfaces, in gradient order."""
        return torch.cat(
            [
                surface.get_surface_parameters().flatten()
                for surface in self.surfaces
                if surface.is_updatable and surface.num_variables
            ]
        )

    def __call__(
        self, r: list[torch.Tensor], *args: object, **kwargs: object
    ) -> torch.Tensor:
        return self.history(self._active_parameters())

    def save(self, foldpath: str, iteration: int) -> None:
        self.history.save(foldpath=foldpath, iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        self.history.load(foldpath=foldpath, iteration=iteration)
