from pathlib import Path

import torch

from .basefuncs import BaseObjective
from ...constants import CONSTANT
from ...optcore.updaters import QuadraticHistory


class Sensitivity(BaseObjective):
    """
    Reciprocal material objective from the current physical sensitivity.
    """

    def __init__(self, normalize_gradient: bool = False) -> None:
        super().__init__()
        self.normalize_gradient = normalize_gradient
        self._cp0: torch.Tensor | None = None

        self.factor: torch.Tensor
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
        self.factor = g.new_ones(())
        if self.normalize_gradient:
            g_norm = g.norm()
            if g_norm > 0:
                self.factor = 1 / g_norm
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


class QuadraticSensitivity(Sensitivity):
    """Historical quadratic material objective using unscaled FEA gradients."""

    def __init__(
        self,
        normalize_gradient: bool = False,
        memory_size: int = CONSTANT.KERNEL.UPDATER_OBJECTIVES.QUADRATIC_MEMORY_PAIRS,
    ) -> None:
        super().__init__(normalize_gradient=normalize_gradient)
        self.history = QuadraticHistory(memory_size)

    def initialize(
        self,
        gradient: torch.Tensor,
        cps0: torch.Tensor,
        step_length: torch.Tensor,
        *args: object,
        **kwargs: object,
    ) -> None:
        super().initialize(gradient, cps0, step_length, *args, **kwargs)
        self.history.observe(cps0, gradient)

    def __call__(self, cps: torch.Tensor, *args: object, **kwargs: object) -> torch.Tensor:
        return self.history(cps) * self.factor

    def save(self, foldpath: str, iteration: int) -> None:
        self.history.save(Path(foldpath) / f"surrogate_{iteration}.npz")

    def load(self, foldpath: str, iteration: int) -> None:
        self.history.load(Path(foldpath) / f"surrogate_{iteration}.npz")
