"""Selectable policies for outer-iteration step limits and penalty weights."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

import torch

from ..constants import CONSTANT

if TYPE_CHECKING:
    from .updaters import BaseUpdater

__all__ = [
    "ConstantConstraintWeights",
    "ConstraintWeightStrategy",
    "FixedStepLength",
    "StepLengthStrategy",
]


class StepLengthStrategy(ABC):
    """Choose limits before building a subproblem; never change FEA gradients."""

    @abstractmethod
    def __call__(
        self,
        updater: BaseUpdater,
        parameters: Sequence[torch.Tensor],
        maximum: float,
        gradient: torch.Tensor | None,
    ) -> list[torch.Tensor]:
        """Return one limit per row of each parameter block.

        Shape blocks have shape ``(control_points, 3)``; material blocks have
        shape ``(variables, 1)``. ``gradient`` is the unscaled physical gradient,
        or ``None`` during initial setup. Results stay fixed in the inner solve.
        """


class FixedStepLength(StepLengthStrategy):
    """Use the configured maximum for every point and every outer iteration."""

    def __call__(
        self,
        updater: BaseUpdater,
        parameters: Sequence[torch.Tensor],
        maximum: float,
        gradient: torch.Tensor | None,
    ) -> list[torch.Tensor]:
        return [value.new_full((len(value),), maximum) for value in parameters]


class ConstraintWeightStrategy(ABC):
    """Choose named penalty coefficients once per outer iteration."""

    @abstractmethod
    def __call__(
        self, updater: BaseUpdater, gradient: torch.Tensor,
    ) -> dict[str, float]:
        """Return coefficients keyed by ``updater.constraints_funcs``.

        Terms and step limits are initialized before this call. Raw values are
        available through ``updater.closure(x, return_list=True)``.
        """


class ConstantConstraintWeights(ConstraintWeightStrategy):
    """Assign the same explicit coefficient to every registered penalty."""

    def __init__(
        self, value: float = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.DEFAULT_WEIGHT,
    ) -> None:
        self.value = value

    def __call__(
        self, updater: BaseUpdater, gradient: torch.Tensor,
    ) -> dict[str, float]:
        return {name: self.value for name in updater.constraints_funcs}
