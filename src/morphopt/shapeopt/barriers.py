"""Fixed-power polynomial penalties with optional distance relaxation."""

from collections.abc import Iterator
from contextlib import contextmanager

import torch

from ..constants import CONSTANT


class PolynomialBarrier:
    """Apply each constraint's exponent while allowing threshold relaxation."""

    def __init__(self) -> None:
        self.tolerance: float | None = None
        self.maximum_violation = 0.0
        self._monitoring = False

    @contextmanager
    def measure_violation(self) -> Iterator[None]:
        """Measure limit excess in transition-width units without integration."""
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

        A distance caller provides f = required - current + f_max and its
        required distance as transition_scale. The schedule relaxes that
        requirement with a fixed relative activation margin. The caller's
        exponent remains unchanged with or without a distance schedule.
        """
        threshold = torch.as_tensor(f_max, dtype=f.dtype, device=f.device)
        if transition_scale is not None and self.tolerance is not None:
            scale = torch.as_tensor(transition_scale, dtype=f.dtype, device=f.device)
            width = CONSTANT.KERNEL.ADAPTIVE_SHAPE_WEIGHTS.DISTANCE_TRANSITION_RATIO * scale
            z = 1 + (f - threshold - self.tolerance * scale) / width
        else:
            z = (f - threshold * ratio) / (threshold * (1 - ratio))
        if self._monitoring and z.numel():
            if not torch.isfinite(z).all():
                raise ValueError("Constraint violation must be finite.")
            self.maximum_violation = max(
                self.maximum_violation, (z - 1).clamp_min(0).max().item(),
            )
        index = torch.where(z > 0)[0]
        return index, z[index].pow(p)
