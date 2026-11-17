import torch

from .basefuncs import BaseObjective
from ...constants import CONSTANT
from ...optcore.updaters import QuadraticHistory


class Sensitivity(BaseObjective):
    """
    Reciprocal material objective from the current physical sensitivity.
    """

    def __init__(self) -> None:
        """Initialize Sensitivity and its configuration state."""
        super().__init__()
        self._cp0: torch.Tensor | None = None

        self.ind_neg: torch.Tensor | None = None
        """Indices of negative sensitivity, can be set in the initialize function.
        """

        self.ind_pos: torch.Tensor | None = None
        """Indices of positive sensitivity, can be set in the initialize function.
        """

    def initialize(self, gradient: torch.Tensor, cps0: torch.Tensor, step_length: torch.Tensor, *args, **kwargs) -> None:
        """Initialize the Sensitivity state.

        Args:
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.
            cps0 (torch.Tensor): Reference SIMP control variables at the start of the subproblem.
            step_length (torch.Tensor): Frozen per-variable movement limits for the current
                subproblem.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """
        self._cp0 = cps0.reshape_as(cps0).detach().clone().flatten()

        self.sensitivity = gradient.detach().clone().reshape_as(self._cp0)

        self.step_length = step_length

        self.ind_pos = torch.where(self.sensitivity > 0)[0]
        self.ind_neg = torch.where(self.sensitivity < 0)[0]

    def __call__(self, cps: torch.Tensor | None = None, *args, **kwargs) -> torch.Tensor:
        """Evaluate Sensitivity for the supplied inputs.

        Args:
            cps (torch.Tensor | None): Current SIMP design control variables.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: Reciprocal physical objective approximation using positive and negative
                raw sensitivity components.
        """
        cps_now = cps.flatten()

        loss_pos = ((self.step_length[self.ind_pos]**2 / (self.step_length[self.ind_pos] + self._cp0[self.ind_pos] - cps_now[self.ind_pos]) - self.step_length[self.ind_pos]) * self.sensitivity[self.ind_pos]).sum()
        loss_neg = ((self.step_length[self.ind_neg]**2 / (-self.step_length[self.ind_neg] + self._cp0[self.ind_neg] - cps_now[self.ind_neg]) + self.step_length[self.ind_neg]) * self.sensitivity[self.ind_neg]).sum()

        return loss_pos + loss_neg


class QuadraticSensitivity(Sensitivity):
    """Limited-memory SR1 material objective using unscaled FEA gradients."""

    def __init__(
        self,
        memory_size: int = CONSTANT.KERNEL.UPDATER_OBJECTIVES.QUADRATIC_MEMORY_PAIRS,
    ) -> None:
        """Initialize QuadraticSensitivity and its configuration state.

        Args:
            memory_size (int): Positive maximum number of retained design/gradient difference pairs.
        """
        super().__init__()
        self.history = QuadraticHistory(memory_size, update_method="sr1")

    def initialize(
        self,
        gradient: torch.Tensor,
        cps0: torch.Tensor,
        step_length: torch.Tensor,
        *args: object,
        **kwargs: object,
    ) -> None:
        """Initialize the QuadraticSensitivity state.

        Args:
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.
            cps0 (torch.Tensor): Reference SIMP control variables at the start of the subproblem.
            step_length (torch.Tensor): Frozen per-variable movement limits for the current
                subproblem.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """
        super().initialize(gradient, cps0, step_length, *args, **kwargs)
        self.history.observe(cps0, gradient)

    def __call__(self, cps: torch.Tensor, *args: object, **kwargs: object) -> torch.Tensor:
        """Evaluate QuadraticSensitivity for the supplied inputs.

        Args:
            cps (torch.Tensor): Current SIMP design control variables.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: Physical objective-change approximation with limited-memory SR1 curvature.
        """
        return self.history(cps)

    def save(self, foldpath: str, iteration: int) -> None:
        """Save the QuadraticSensitivity state.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        self.history.save(foldpath=foldpath, iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        """Load the QuadraticSensitivity state.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        self.history.load(foldpath=foldpath, iteration=iteration)
