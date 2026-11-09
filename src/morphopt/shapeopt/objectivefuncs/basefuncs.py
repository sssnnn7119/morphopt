from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import torch

from ...optcore.protocal import ProtocalSavable
from ..barriers import PolynomialBarrier

if TYPE_CHECKING:
    from ..surfaces import BaseSurface


class BaseConstraints:
    """Geometric penalties evaluated with reference surface quadrature."""

    def __init__(self) -> None:
        self.barrier_function = PolynomialBarrier()
        self.area_weights: list[torch.Tensor] = []
        """Reference area weights, fixed throughout one subproblem."""
        self.sample_weights: list[torch.Tensor] | None = None
        """Optional optimization weights, separate from geometric area weights."""
        self.surfaces: list[BaseSurface] = []

    def initialize(
        self,
        r0: list[torch.Tensor],
        rdu0: list[torch.Tensor],
        rdu20: list[torch.Tensor],
        weights: list[torch.Tensor],
        *args: object,
        surfaces: Sequence[BaseSurface],
        **kwargs: object,
    ) -> None:
        """Bind reference area weights without physical sensitivity scaling."""
        self.area_weights = [weight.detach().clone() for weight in weights]
        self.sample_weights = None
        self.surfaces = list(surfaces)
        self.barrier_function = PolynomialBarrier()

    def set_sample_weights(self, weights: list[torch.Tensor] | None) -> None:
        """Bind the strategy's frozen factors in surface quadrature order."""
        if weights is not None:
            if len(weights) != len(self.area_weights) or any(
                value.shape != area.shape
                for value, area in zip(weights, self.area_weights)
            ):
                raise ValueError("Sample weights must match the surface quadrature blocks.")
            if any(not torch.isfinite(value).all() or (value < 0).any() for value in weights):
                raise ValueError("Sample weights must be finite and nonnegative.")
            weights = [
                value.detach().to(area).clone()
                for value, area in zip(weights, self.area_weights)
            ]
        self.sample_weights = weights

    @property
    def integration_weights(self) -> list[torch.Tensor]:
        """Compose area and pointwise factors without changing either input."""
        if self.sample_weights is None:
            return self.area_weights
        return [area * value for area, value in zip(self.area_weights, self.sample_weights)]

    def __call__(
        self,
        r: list[torch.Tensor],
        rdu: list[torch.Tensor],
        rdu2: list[torch.Tensor],
        *args,
        **kwargs,
    ) -> float:
        """
        Call the objective function.

        Args:
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the objective function.
        """
        raise NotImplementedError("Objective function not implemented.")

class BaseObjective(ProtocalSavable):
    """
    Base class for objective functions in MorphOpt.
    """

    def __init__(self):
        """
        Initialize the objective function.
        """
        self.gradient: list[torch.Tensor] = []
        """
        Sensitivity of the shape derivative with respect to the contact forces.
        """

        self.surfaces: list[BaseSurface] = []

    def initialize(
        self,
        gradient: torch.Tensor,
        r0: list[torch.Tensor],
        rdu0: list[torch.Tensor],
        rdu20: list[torch.Tensor],
        *args: object,
        surfaces: Sequence[BaseSurface],
        **kwargs: object,
    ) -> None:
        """
        Initialize the objective function with the given parameters.

        Args:
            gradient (torch.Tensor): The gradient of the objective function.
            r0 (list[torch.Tensor]): The initial point coordinates of the surfaces.
            rdu0 (list[torch.Tensor]): The initial partial derivatives of the surfaces.
            rdu20 (list[torch.Tensor]): The initial second partial derivatives of the surfaces.
            weights (list[torch.Tensor]): The weights for each point.
            surfaces (Sequence[BaseSurface]): Surfaces owned by the boundary Part.
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        """
        self.surfaces = list(surfaces)

    def __call__(
        self,
        r: list[torch.Tensor],
        rdu: list[torch.Tensor],
        rdu2: list[torch.Tensor],
        *args,
        **kwargs,
    ) -> float:
        """
        Call the objective function.

        Args:
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the objective function.
        """
        raise NotImplementedError("Objective function not implemented.")
