import torch

from .basefuncs import BaseObjective

class Sensitivity(BaseObjective):
    """
    First-order objective from material design sensitivity.

    This objective uses the sensitivity returned by global objective sensitivity
    analysis and builds a linearized objective around the current material state.
    """

    def __init__(self, normalize_gradient: bool = False) -> None:
        super().__init__()
        self.normalize_gradient = normalize_gradient
        self._cp0: torch.Tensor | None = None

    def initialize(self, gradient: torch.Tensor, cps0: torch.Tensor, *args, **kwargs) -> None:
        self._cp0 = cps0.reshape_as(cps0).detach().clone()

        g = gradient.detach().clone().reshape_as(self._cp0)
        if self.normalize_gradient:
            g_norm = g.norm()
            if g_norm > 0:
                g = g / g_norm

        self.sensitivity = g

    def __call__(self, cps: torch.Tensor | None = None, *args, **kwargs) -> torch.Tensor:
        cps_now = cps

        return ((cps_now - self._cp0) * self.sensitivity).sum()
