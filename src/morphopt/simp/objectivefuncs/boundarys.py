import torch

from ...constants import CONSTANT
from .basefuncs import BaseConstraints


class MinValue(BaseConstraints):
    """
    Penalize material variables below a minimum bound.
    """

    def __init__(
        self,
        xmin: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.MINIMUM_VALUE,
        threshold: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.DEFAULT_THRESHOLD,
        p: int = CONSTANT.KERNEL.SIMP_CONSTRAINTS.DEFAULT_EXPONENT,
        barrier_thre: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.BARRIER_THRESHOLD,
        barrier_ratio: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.BARRIER_RATIO,
    ) -> None:
        """Initialize MinValue and its configuration state.

        Args:
            xmin (float): Lower bound of the material design variables.
            threshold (float): Offset of the bound's activation range from the nominal material
                limit.
            p (int): Polynomial penalty exponent.
            barrier_thre (float): Positive reference violation used by the material bound barrier.
            barrier_ratio (float): Activation threshold as a fraction of the barrier limit.
        """
        super().__init__()
        self.xmin = float(xmin)
        self.threshold = float(threshold)
        self.p = int(p)
        self.barrier_thre = max(
            float(barrier_thre), CONSTANT.KERNEL.SIMP_CONSTRAINTS.MINIMUM_THRESHOLD
        )
        self.barrier_ratio = float(barrier_ratio)

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """Evaluate MinValue for the supplied inputs.

        Args:
            cps (torch.Tensor): Current SIMP design control variables.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: Integrated penalty for design values below the configured lower bound.
        """
        viol = (self.xmin + self.threshold) - cps
        _, loss = self.barrier_function(
            viol.flatten(), self.barrier_thre, self.barrier_ratio, self.p
        )
        return loss.sum().reshape(1)


class MaxValue(BaseConstraints):
    """
    Penalize material variables above a maximum bound.
    """

    def __init__(
        self,
        xmax: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.MAXIMUM_VALUE,
        threshold: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.DEFAULT_THRESHOLD,
        p: int = CONSTANT.KERNEL.SIMP_CONSTRAINTS.DEFAULT_EXPONENT,
        barrier_thre: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.BARRIER_THRESHOLD,
        barrier_ratio: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.BARRIER_RATIO,
    ) -> None:
        """Initialize MaxValue and its configuration state.

        Args:
            xmax (float): Upper bound of the material design variables.
            threshold (float): Offset of the bound's activation range from the nominal material
                limit.
            p (int): Polynomial penalty exponent.
            barrier_thre (float): Positive reference violation used by the material bound barrier.
            barrier_ratio (float): Activation threshold as a fraction of the barrier limit.
        """
        super().__init__()
        self.xmax = float(xmax)
        self.threshold = float(threshold)
        self.p = int(p)
        self.barrier_thre = max(
            float(barrier_thre), CONSTANT.KERNEL.SIMP_CONSTRAINTS.MINIMUM_THRESHOLD
        )
        self.barrier_ratio = float(barrier_ratio)

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """Evaluate MaxValue for the supplied inputs.

        Args:
            cps (torch.Tensor): Current SIMP design control variables.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: Integrated penalty for design values above the configured upper bound.
        """
        viol = cps - (self.xmax - self.threshold)
        _, loss = self.barrier_function(
            viol.flatten(), self.barrier_thre, self.barrier_ratio, self.p
        )
        return loss.sum().reshape(1)
