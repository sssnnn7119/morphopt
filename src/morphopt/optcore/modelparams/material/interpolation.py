"""SIMP interpolation functions."""

from __future__ import annotations

from morphopt._torch import torch


class MaterialInterpolation:
    """SIMP density-to-material interpolation helper."""
    def __init__(self, penalty: float = 3.0) -> None:
        self._penalty = float(penalty)
        """SIMP exponent applied to clamped density."""

    @property
    def penalty(self) -> float:
        return self._penalty

    def evaluate(self, density: torch.Tensor, minimum: float = 0.0) -> torch.Tensor:
        """Return penalized material ratio for clamped density values."""
        return minimum + (density.clamp(0, 1) ** self._penalty) * (1.0 - minimum)
