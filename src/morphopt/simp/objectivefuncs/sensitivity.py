import torch

from .basefuncs import BaseObjective
from ..simpmaterial import SIMP_BSPFieldMaterials
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

        self.factor: float
        """A factor to scale the shape derivative, can be set in the initialize function. 
        """

        self.ind_neg: torch.Tensor | None = None
        """Indices of negative sensitivity, can be set in the initialize function.
        """

        self.ind_pos: torch.Tensor | None = None
        """Indices of positive sensitivity, can be set in the initialize function.
        """

    def initialize(self, gradient: torch.Tensor, cps0: torch.Tensor, step_length: torch.Tensor, *args, **kwargs) -> None:
        self._cp0 = cps0.reshape_as(cps0).detach().clone().flatten()

        g = gradient.detach().clone().reshape_as(self._cp0)
        if self.normalize_gradient:
            g_norm = g.norm()
            if g_norm > 0:
                g = g / g_norm

        self.sensitivity = g.flatten()

        self.step_length = step_length

        self.ind_pos = torch.where(self.sensitivity > 0)[0]
        self.ind_neg = torch.where(self.sensitivity < 0)[0]

    def __call__(self, cps: torch.Tensor | None = None, *args, **kwargs) -> torch.Tensor:
        cps_now = cps.flatten()

        loss_pos = ((self.step_length[self.ind_pos]**2 / (self.step_length[self.ind_pos] + self._cp0[self.ind_pos] - cps_now[self.ind_pos]) - self.step_length[self.ind_pos]) * self.sensitivity[self.ind_pos]).sum()
        loss_neg = ((self.step_length[self.ind_neg]**2 / (-self.step_length[self.ind_neg] + self._cp0[self.ind_neg] - cps_now[self.ind_neg]) + self.step_length[self.ind_neg]) * self.sensitivity[self.ind_neg]).sum()

        return loss_pos + loss_neg
