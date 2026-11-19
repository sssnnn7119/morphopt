"""Fixed-power polynomial penalties with optional geometric relaxation."""

from collections.abc import Iterator
from contextlib import contextmanager

import torch

from ..constants import CONSTANT


class PolynomialBarrier:
    """Apply each constraint's exponent over a configurable transition width."""

    def __init__(self) -> None:
        """Initialize PolynomialBarrier and its configuration state."""
        self.tolerance: float | None = None
        self.maximum_violation = 0.0
        self.excess_weight = 0.0
        self.excess_start = 1.0
        self._monitoring = False

    @contextmanager
    def measure_violation(self) -> Iterator[None]:
        """Record the peak violation in transition-width units during evaluation."""
        self.maximum_violation = 0.0
        self._monitoring = True
        try:
            yield
        finally:
            self._monitoring = False

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

        Adaptive relaxation extends the width
        by a fraction of the reference scale. A distance term uses its required
        separation as that scale and shifts activation by the relaxation.
        Upper-bound terms widen from their existing activation point.
        Monitoring and integration use the same normalized coordinate.

        Args:
            f (torch.Tensor): Sampled constraint quantity evaluated by the barrier.
            f_max (torch.Tensor | float): Constraint limit broadcast or aligned with f.
            ratio (float): Activation threshold as a fraction of the supplied limit.
            p (float): Polynomial penalty exponent.
            transition_scale (torch.Tensor | float | None): Scale of the smooth barrier's transition
                region.

        Returns:
            tuple[torch.Tensor, torch.Tensor]: Active indices and pointwise values before area
                integration.
        """
        threshold = torch.as_tensor(f_max, dtype=f.dtype, device=f.device)
        if transition_scale is not None and self.tolerance is not None:
            scale = torch.as_tensor(transition_scale, dtype=f.dtype, device=f.device)
            margin = CONSTANT.KERNEL.ADAPTIVE_SHAPE_UPDATE.DISTANCE_TRANSITION_RATIO
            z = ((f - threshold) / scale + (margin - self.tolerance)) / (margin + self.tolerance)
        else:
            margin = 1 - ratio
            z = (f - threshold * ratio) / (threshold * (margin + (self.tolerance or 0.0)))
        if self._monitoring and z.numel():
            if not torch.isfinite(z).all():
                raise ValueError("Constraint violation must be finite.")
            self.maximum_violation = max(
                self.maximum_violation, z.max().item(),
            )
        index = torch.where(z > 0)[0]
        active = z[index]
        penalty = active.pow(p)
        if self.excess_weight:
            # Each entry is one sample (or one distance pair). The added
            # term uses the same exponent and is confined to unsafe samples.
            penalty = penalty + self.excess_weight * (active - self.excess_start).clamp_min(0).pow(p)
        return index, penalty
