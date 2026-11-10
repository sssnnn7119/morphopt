"""Selectable policies for outer-iteration step limits and penalty weights."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

import torch

from ..constants import CONSTANT
from .protocal import ProtocalSavable

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

        Each parameter block has shape ``(row_count, components_per_row)``.
        ``gradient`` is the unscaled physical gradient,
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


class ConstraintWeightStrategy(ProtocalSavable):
    """Choose fixed coefficients for one outer-iteration subproblem."""

    # Stateful strategies implement save/load; stateless ones inherit no-op hooks.
    # The core invokes the interface without interpreting the design object.

    @abstractmethod
    def __call__(
        self, updater: BaseUpdater, gradient: torch.Tensor,
    ) -> dict[str, float]:
        """Return coefficients keyed by ``updater.constraints_funcs``.

        Terms and step limits are initialized before this call. Raw values are
        available through ``updater.closure(x, return_list=True)``.
        Coefficients stay fixed throughout the inner solve; raw gradients must
        not be rescaled to balance the terms.
        """


class ConstantConstraintWeights(ConstraintWeightStrategy):
    """Assign the same explicit coefficient to every registered penalty."""

    def __init__(
        self, value: float = CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT,
    ) -> None:
        self.value = value

    def __call__(
        self, updater: BaseUpdater, gradient: torch.Tensor,
    ) -> dict[str, float]:
        return {name: self.value for name in updater.constraints_funcs}
