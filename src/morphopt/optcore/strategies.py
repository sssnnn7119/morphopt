"""Selectable policies for outer-iteration step limits and penalty weights."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

import torch

from ..constants import CONSTANT
from .protocal import ProtocalHistory, ProtocalSavable

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

        Each parameter block has shape ``(row_count, components_per_row)``. ``gradient`` is the
        unscaled physical gradient, or ``None`` during initial setup. Results stay fixed in the
        inner solve.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            parameters (Sequence[torch.Tensor]): Parameter values in the order required by the
                selected interface.
            maximum (float): Configured upper limit on each design-variable movement.
            gradient (torch.Tensor | None): Unscaled physical objective gradient in the target's
                design-variable order.

        Returns:
            list[torch.Tensor]: One limit per row of each parameter block.
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
        """Evaluate FixedStepLength for the supplied inputs.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            parameters (Sequence[torch.Tensor]): Parameter values in the order required by the
                selected interface.
            maximum (float): Configured upper limit on each design-variable movement.
            gradient (torch.Tensor | None): Unscaled physical objective gradient in the target's
                design-variable order.

        Returns:
            list[torch.Tensor]: One vector per parameter block, with each row assigned maximum on
                that block's dtype and device.
        """
        return [value.new_full((len(value),), maximum) for value in parameters]


class ConstraintWeightStrategy(ProtocalSavable, ProtocalHistory):
    """Choose named penalty coefficients before the inner optimization begins.

    The policy may retain state through the save/load protocol and expose dynamic history
    information. It must not rescale the physical FEA gradient or change coefficients while the
    inner objective is being differentiated.
    """

    # Stateful strategies implement save/load; stateless ones inherit no-op hooks.
    # The core invokes the interface without interpreting the design object.

    @abstractmethod
    def __call__(
        self, updater: BaseUpdater, gradient: torch.Tensor,
    ) -> dict[str, float]:
        """Return coefficients keyed by ``updater.constraints_funcs``.

        Terms and step limits are initialized before this call. Raw values are available through
        ``updater.closure(x, return_list=True)``. Coefficients stay fixed throughout the inner
        solve; raw gradients must not be rescaled to balance the terms.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.

        Returns:
            dict[str, float]: Coefficients keyed by ``updater.constraints_funcs``.
        """


class ConstantConstraintWeights(ConstraintWeightStrategy):
    """Assign the same explicit coefficient to every registered penalty."""

    def __init__(
        self, value: float = CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT,
    ) -> None:
        """Store the scalar coefficient assigned to every registered penalty.

        Args:
            value (float): Nonnegative penalty multiplier applied unchanged at each outer update.
        """
        self.value = value

    def __call__(
        self, updater: BaseUpdater, gradient: torch.Tensor,
    ) -> dict[str, float]:
        """Evaluate ConstantConstraintWeights for the supplied inputs.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.

        Returns:
            dict[str, float]: Registered penalty names mapped to the configured constant
                coefficient.
        """
        return {name: self.value for name in updater.constraints_funcs}
