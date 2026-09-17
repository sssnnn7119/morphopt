"""Small optimization algorithms used by updater implementations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from morphopt._torch import torch


@dataclass(frozen=True, slots=True)
class OptimizerResult:
    """Detached summary returned by a local optimizer."""

    parameters: torch.Tensor
    objective: float
    converged: bool = False
    iterations: int = 0


class BaseOptimizer:
    """Minimal optimizer protocol used by updater implementations."""

    def minimize(
        self, closure: Callable[[torch.Tensor], torch.Tensor], parameters: torch.Tensor
    ) -> OptimizerResult:
        """Minimize the local closure and return detached result data."""
        """Evaluate a closure and return a baseline result."""
        value = closure(parameters)
        return OptimizerResult(parameters.detach(), float(value.detach()), True, 0)


class BacktrackingLineSearch(BaseOptimizer):
    """Placeholder for the updater fallback line-search algorithm."""

    def minimize(
        self, closure: Callable[[torch.Tensor], torch.Tensor], parameters: torch.Tensor
    ) -> OptimizerResult:
        """Run the future Armijo line-search implementation."""
        # TODO: Add Armijo backtracking around the local objective closure.
        return super().minimize(closure, parameters)


class LBFGSOptimizer(BaseOptimizer):
    """Placeholder for the bounded local LBFGS optimizer."""

    def __init__(
        self, *, maximum_iterations: int = 20, learning_rate: float = 1.0
    ) -> None:
        self._maximum_iterations = int(maximum_iterations)
        """Maximum local optimizer iterations."""
        self._learning_rate = float(learning_rate)
        """Initial local step length."""

    def minimize(
        self, closure: Callable[[torch.Tensor], torch.Tensor], parameters: torch.Tensor
    ) -> OptimizerResult:
        """Run the future LBFGS implementation."""
        # TODO: Use torch.optim.LBFGS once concrete updater constraints exist.
        return super().minimize(closure, parameters)
