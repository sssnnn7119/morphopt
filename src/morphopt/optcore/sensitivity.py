"""Sensitivity-analysis orchestration boundary."""

from __future__ import annotations

from collections.abc import Mapping

import torchfea

from morphopt._torch import torch

from .design_registry import DesignKey, DesignRegistry
from .objective import ObjectiveFunction
from .solver import Solver, StaticResult


class SensitivityAnalyzer:
    """Delegate implicit/adjoint differentiation to the solver backend.

    MorphOpt owns design-vector assembly and gradient splitting; TorchFEA owns
    the equilibrium differentiation itself.
    """

    def __init__(self) -> None:
        self._objective: ObjectiveFunction | None = None
        """Objective callback and current result context."""
        self._registry: DesignRegistry | None = None
        """Design variable ownership and slicing."""
        self._solver: Solver | None = None
        """Solver-side implicit sensitivity hooks."""
        self._design_vars: torch.Tensor | None = None
        """Temporary differentiable design vector."""
        self._iteration: int | None = None
        """Iteration represented by cached derivatives."""
        self._fe_results: tuple[StaticResult, ...] = ()
        """Equilibrium results used by differentiation."""
        self._sensitivities: dict[DesignKey, torch.Tensor] = {}
        """Detached gradient per design block."""
        self._initialized = False
        """Analyzer lifecycle initialization state."""

    def initialize(
        self, objective: ObjectiveFunction, registry: DesignRegistry, solver: Solver
    ) -> None:
        """Bind objective, Registry and backend solver for a run."""
        self._objective = objective
        self._registry = registry
        self._solver = solver
        self._initialized = True

    def reinitialize(
        self, iteration: int, fe_results: tuple[StaticResult, ...]
    ) -> None:
        """Bind current equilibrium results and clear previous gradients."""
        self._iteration = int(iteration)
        self._fe_results = tuple(fe_results)
        self._sensitivities.clear()
        self._design_vars = None

    def build_sensitivities(self) -> None:
        """Build and cache one detached sensitivity tensor per design block."""
        if self._registry is None:
            raise RuntimeError("SensitivityAnalyzer is not initialized")
        values = self._objective.compute_sensitivities(
            self._registry, self._solver, self._fe_results
        )
        if values is not None:
            self._sensitivities = {
                key: torch.as_tensor(value).detach().clone()
                for key, value in values.items()
            }
            return
        design_vars = self._build_design_vars()
        self._design_vars = design_vars
        # ``update_assembly`` is deliberately restricted to this sensitivity
        # trial.  The optimization model itself was already built from the
        # committed Params state at the beginning of the step; updater changes
        # are committed only after this graph-building phase and are consumed
        # by Params on the next outer iteration.
        self._apply_design_vars(None, design_vars)
        try:
            # TODO: Call TorchFEA's get_jacobian_sensitivity_multistep() here.
            gradient = torch.zeros_like(design_vars)
        finally:
            # Updaters receive committed Params values on the next phase.  A
            # sensitivity trial must never leak into the local optimizer.
            self._apply_design_vars(None, torch.zeros_like(design_vars))
        self._sensitivities = self._split_gradients(gradient)
        self._design_vars = None

    def get_sensitivities(self) -> Mapping[DesignKey, torch.Tensor]:
        """Return the latest block-split sensitivities."""
        return dict(self._sensitivities)

    def _build_design_vars(self) -> torch.Tensor:
        assert self._registry is not None
        return self._registry.get_design_delta().detach().clone().requires_grad_(True)

    def _apply_design_vars(
        self, assembly: torchfea.Assembly | None, design_vars: torch.Tensor
    ) -> None:
        assert self._registry is not None
        self._registry.update_assembly(design_vars)
        # Case views share the same Assembly.  Rebuilding this lightweight
        # binding keeps load-component trial values visible to the backend
        # without constructing a second optimization model.
        self._objective._fea_params.build_case_assemblies()

    def _split_gradients(self, gradient: torch.Tensor) -> dict[DesignKey, torch.Tensor]:
        assert self._registry is not None
        return {
            key: value.detach().clone()
            for key, value in self._registry.compute_block_values(gradient).items()
        }
