"""Shared polynomial penalties and optional quadratic distance relaxation."""

import torch

from ..constants import CONSTANT


class PolynomialBarrier:
    """Keep the original penalty unless an outer distance schedule is active."""

    def __init__(self) -> None:
        self.tolerance: float | None = None

    def __call__(
        self,
        f: torch.Tensor,
        f_max: torch.Tensor | float,
        ratio: float,
        p: float,
        *,
        transition_scale: torch.Tensor | float | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Return active indices and pointwise values before area integration.

        A distance caller provides f = required - current + f_max and its
        required distance as transition_scale. The schedule relaxes that
        requirement, with a fixed relative activation margin and power two.
        Other penalties continue to use their original thresholds and powers.
        """
        threshold = torch.as_tensor(f_max, dtype=f.dtype, device=f.device)
        if transition_scale is not None and self.tolerance is not None:
            scale = torch.as_tensor(transition_scale, dtype=f.dtype, device=f.device)
            width = CONSTANT.KERNEL.ADAPTIVE_SHAPE_WEIGHTS.DISTANCE_TRANSITION_RATIO * scale
            z = 1 + (f - threshold - self.tolerance * scale) / width
            p = 2
        else:
            z = (f - threshold * ratio) / (threshold * (1 - ratio))
        index = torch.where(z > 0)[0]
        return index, z[index].pow(p)
