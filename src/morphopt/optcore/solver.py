"""Solver orchestration boundary.

The actual nonlinear/static algorithms remain in TorchFEA.  This class only
owns configuration, shared solver construction and result normalization.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import torchfea

from morphopt._torch import torch
from morphopt.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StaticResult:
    """Serializable minimum result contract used by ObjectiveFunction.

    TorchFEA result objects are normalized into this shape at the solver
    boundary so downstream code does not depend on backend internals.
    """

    GC: torch.Tensor | None = None
    converged: bool = True
    model_hash: str | None = None
    jacobian: Mapping[str, torch.Tensor] = field(default_factory=dict)
    work_conditions: tuple[torchfea.WorkCondition, ...] | None = None
    total_time: float = 0.0
    time_items: Mapping[str, float] = field(default_factory=dict)
    step_index: int = 0


class Solver:
    """Create and drive one shared static solver for all load cases.

    The initial implementation deliberately leaves numerical construction in
    TODO hooks; the shared-controller call order and result normalization are already stable.
    """

    def __init__(
        self,
        *,
        maximum_iterations: int = 10000,
        error_tolerance: float = 1e-5,
        device_names: tuple[str, ...] = (),
        num_processes: int = 4,
    ) -> None:
        self._maximum_iterations = int(maximum_iterations)
        """Nonlinear iteration limit for one solve."""
        self._error_tolerance = float(error_tolerance)
        """Convergence tolerance passed to the backend."""
        self._device_names = tuple(device_names)
        """Devices available to the numerical solver."""
        self._num_processes = int(num_processes)
        """Requested backend worker count."""
        self._num_steps = 0
        """Number of load cases registered by FEAParams."""
        self._iteration: int | None = None
        """Current outer optimization iteration."""
        self._fea_controller: torchfea.FEAController | None = None
        """Shared backend controller for all cases."""
        self._solver: torchfea.solver.StaticImplicitSolver | None = None
        """Backend static solver attached to that controller."""
        self._results: tuple[StaticResult, ...] = ()
        """Normalized results indexed by load case."""
        self._initialized = False
        """Solver lifecycle initialization state."""

    @property
    def maximum_iterations(self) -> int:
        """Return the backend nonlinear iteration limit."""
        return self._maximum_iterations

    @property
    def error_tolerance(self) -> float:
        """Return the backend convergence tolerance."""
        return self._error_tolerance

    @property
    def device_names(self) -> tuple[str, ...]:
        """Return explicitly configured solver devices."""
        return self._device_names

    @property
    def num_processes(self) -> int:
        """Return the requested backend worker count."""
        return self._num_processes

    def initialize(self, num_steps: int = 0) -> None:
        """Prepare solver configuration for the known number of cases."""
        self._num_steps = int(num_steps)
        self._initialized = True

    def reinitialize(self, iteration: int) -> None:
        """Reset per-iteration solver objects and cached results."""
        self._iteration = int(iteration)
        self._solver = None
        self._results = ()

    def build_solvers(self, fea_controller: torchfea.FEAController) -> None:
        """Create one native solver and attach it to the shared controller."""
        self._fea_controller = fea_controller
        self._solver = torchfea.solver.StaticImplicitSolver(
            maximum_iteration=self._maximum_iterations,
            tol_error=self._error_tolerance,
        )
        self._solver.assembly = fea_controller.assembly
        fea_controller.solver = self._solver
        if self._device_names:
            fea_controller.change_device(torch.device(self._device_names[0]))

    def solve(
        self,
        fea_controller: torchfea.FEAController,
        jacobian_names: tuple[str, ...] = (),
    ) -> None:
        """Solve all load cases through one shared backend controller."""
        controller = fea_controller
        results: list[StaticResult] = []
        raw_results = controller.solve(need_jacobian=bool(jacobian_names))
        if raw_results is None:
            raw_results = ()
        if not isinstance(raw_results, (tuple, list)):
            raw_results = (raw_results,)
        for index, result in enumerate(raw_results):
            if result is None:
                result = StaticResult(step_index=index)
            elif not isinstance(result, StaticResult):
                result = StaticResult(
                    GC=result.GC,
                    converged=bool(result.converged),
                    model_hash=result.model_hash,
                    jacobian=result.jacobian,
                    work_conditions=result.work_conditions,
                    total_time=float(result.total_time),
                    time_items=result.time_items,
                    step_index=index,
                )
            results.append(result)
        self._results = tuple(results)

    def get_results(self) -> tuple[StaticResult, ...]:
        """Return results from the most recent :meth:`solve` call."""
        return self._results

    def get_sensitivity_solver(self) -> torchfea.solver.StaticImplicitSolver | None:
        """Return the base solver used by implicit sensitivity analysis."""
        # TODO: Return a TorchFEA solver bound to the base Assembly.
        return None

    def change_device(self, device: str) -> None:
        """Set one finite-element device for subsequent solves."""
        self.change_devices((str(device),))

    def change_devices(self, device_names: tuple[str, ...]) -> None:
        """Set the finite-element devices without touching Controller state."""
        self._device_names = tuple(str(name) for name in device_names)
        if self._fea_controller is not None and self._device_names:
            self._fea_controller.change_device(self._device_names[0])

    def save(self, folder_path: str, iteration: int) -> None:
        """Persist solver options and convergence metadata."""
        # TODO: Persist solver settings and per-case convergence metadata.
        return

    def load(self, folder_path: str, iteration: int) -> None:
        """Restore solver options from a checkpoint."""
        # TODO: Restore solver settings and cached initial states.
        return
