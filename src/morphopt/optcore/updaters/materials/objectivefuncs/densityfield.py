import torch

from .basefuncs import BaseObjective


class DensityFieldMinimize(BaseObjective):
    """
    Small regularization objective that minimizes the SIMP density field.

    This objective encourages the density field to approach zero everywhere
    outside the solid material domain. It is scaled by a very small factor so
    that it only acts as a gentle regularization term.
    """

    def __init__(self, scale: float = 1e-10) -> None:
        super().__init__()
        self.scale = float(scale)

    def initialize(self, gradient: torch.Tensor, cps0: torch.Tensor, *args, **kwargs) -> None:
        # This objective does not require gradient initialization from the FE model.
        self.sensitivity = torch.zeros_like(cps0)

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        cps_now = cps.reshape_as(self.sensitivity if self.sensitivity is not None else cps)
        return self.scale * (cps_now.sum() + 1)**2
