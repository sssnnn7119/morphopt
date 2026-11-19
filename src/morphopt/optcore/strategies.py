"""Update strategies shared by geometry and material subproblems."""

from __future__ import annotations

import math
from abc import abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

import torch

from ..constants import CONSTANT
from .protocal import ProtocalHistory, ProtocalSavable

if TYPE_CHECKING:
    from .updaters import BaseUpdater

__all__ = ["UpdateStrategy", "FixedUpdate"]


class UpdateStrategy(ProtocalSavable, ProtocalHistory):
    """Choose step limits, initial penalty weights, and the candidate to commit.

    Each updater owns one policy instance across outer iterations. Its save/load and
    history hooks cover state shared by all three decisions.
    """

    def step_lengths(
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
            list[torch.Tensor]: A finite, nonnegative limit per row of each parameter block.
        """
        return [value.new_full((len(value),), maximum) for value in parameters]

    @abstractmethod
    def constraint_weights(
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
            dict[str, float]: One finite, nonnegative coefficient per registered constraint.
        """

    def solve_update(
        self, updater: BaseUpdater, origin: torch.Tensor,
    ) -> torch.Tensor:
        """Select an update from solves of the current outer subproblem.

        Args:
            updater (BaseUpdater): Owner of the objective and current constraint weights.
            origin (torch.Tensor): Starting design coordinates of the outer update.

        Returns:
            torch.Tensor: Candidate to commit. The default accepts the first solution.
                A policy can adjust weights between calls and select a different candidate.
        """
        return updater.solve_subproblem(origin)


class FixedUpdate(UpdateStrategy):
    """Assign the same explicit coefficient to every registered penalty."""

    def __init__(
        self, value: float = CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT,
    ) -> None:
        """Store the scalar coefficient assigned to every registered penalty.

        Args:
            value (float): Nonnegative penalty multiplier applied unchanged at each outer update.
        """
        if not math.isfinite(value) or value < 0:
            raise ValueError("Fixed penalty weight must be finite and nonnegative.")
        self.value = value

    def constraint_weights(
        self, updater: BaseUpdater, gradient: torch.Tensor,
    ) -> dict[str, float]:
        """Evaluate FixedUpdate for the supplied inputs.

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
