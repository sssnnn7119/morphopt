from __future__ import annotations

import torch

from .basefuncs import BaseConstraints

class Fairness(BaseConstraints):
    """Fairness penalty of the boundary surfaces of one Part.

    The geometry updater binds the Part's surfaces during initialization.  The
    cached list is refreshed whenever the updater is reinitialized.
    """

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
            if surface.is_updatable
        )
