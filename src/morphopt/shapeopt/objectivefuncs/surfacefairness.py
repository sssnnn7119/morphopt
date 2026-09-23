from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import torch

from .basefuncs import BaseConstraints

if TYPE_CHECKING:
    from ..surfaceinterfaces import BaseSurfaceInterface


class Fairness(BaseConstraints):
    """Fairness penalty of the boundary surfaces of one Part.

    The geometry updater binds the Part's surfaces during initialization.  The
    cached list is refreshed whenever the updater is reinitialized.
    """

    def __init__(self) -> None:
        """Initialize an unbound fairness constraint."""
        super().__init__()
        self.surfaces: list[BaseSurfaceInterface] = []
        """Surfaces bound by the owning geometry updater."""

    def initialize(
        self,
        *args: object,
        surfaces: Sequence[BaseSurfaceInterface] | None = None,
        **kwargs: object,
    ) -> None:
        """Bind the current Part's surfaces before evaluating fairness."""
        super().initialize(*args, **kwargs)
        if surfaces is None:
            raise ValueError("Fairness requires the updater's surfaces.")
        self.surfaces = list(surfaces)

    def __call__(
        self,
        r: list[torch.Tensor],
        rdu: list[torch.Tensor],
        rdu2: list[torch.Tensor],
        *args: object,
        **kwargs: object,
    ) -> torch.Tensor:
        """
        Call the fairness objective function.

        Args:
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.

        Returns:
            The value of the fairness objective function.
        """
        if not self.surfaces:
            raise ValueError(
                f"{type(self).__name__} has no bound surfaces; initialize it "
                "through the owning geometry updater first."
            )
        return sum(
            surface.get_penalty_fairness(self.scaler[i], r[i], rdu[i], rdu2[i])
            for i, surface in enumerate(self.surfaces)
        )
