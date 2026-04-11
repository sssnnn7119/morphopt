import torch

from .basefuncs import BaseConstraints


class MinValue(BaseConstraints):
    """
    Penalize material variables below a minimum bound.
    """

    def __init__(
        self,
        xmin: float = 0.0,
        threshold: float = 0.0,
        p: int = 3,
        barrier_thre: float = 0.05,
        barrier_ratio: float = 0.0,
    ) -> None:
        super().__init__()
        self.xmin = float(xmin)
        self.threshold = float(threshold)
        self.p = int(p)
        self.barrier_thre = max(float(barrier_thre), 1e-12)
        self.barrier_ratio = float(barrier_ratio)

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        viol = (self.xmin + self.threshold) - cps
        mask = viol > 0
        if not mask.any():
            return torch.zeros(1, device=cps.device, dtype=cps.dtype)

        index, loss = self.barrier_function(viol[mask], self.barrier_thre, self.barrier_ratio, self.p)
        if index.numel() == 0:
            return torch.zeros(1, device=cps.device, dtype=cps.dtype)

        scale = self.scaler[mask][index] if self.scaler is not None else 1.0
        return (scale * loss).sum().reshape(1)


class MaxValue(BaseConstraints):
    """
    Penalize material variables above a maximum bound.
    """

    def __init__(
        self,
        xmax: float = 1.0,
        threshold: float = 0.0,
        p: int = 3,
        barrier_thre: float = 0.05,
        barrier_ratio: float = 0.0,
    ) -> None:
        super().__init__()
        self.xmax = float(xmax)
        self.threshold = float(threshold)
        self.p = int(p)
        self.barrier_thre = max(float(barrier_thre), 1e-12)
        self.barrier_ratio = float(barrier_ratio)

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        viol = cps - (self.xmax - self.threshold)
        mask = viol > 0
        if not mask.any():
            return torch.zeros(1, device=cps.device, dtype=cps.dtype)

        index, loss = self.barrier_function(viol[mask], self.barrier_thre, self.barrier_ratio, self.p)
        if index.numel() == 0:
            return torch.zeros(1, device=cps.device, dtype=cps.dtype)

        scale = self.scaler[mask][index] if self.scaler is not None else 1.0
        return (scale * loss).sum().reshape(1)
