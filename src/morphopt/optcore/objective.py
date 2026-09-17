"""Objective and result-cache base class."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pyvista
import torchfea

from morphopt._torch import torch
from morphopt.logging import get_logger

from .design_registry import DesignKey, DesignRegistry
from .modelparams.fea import FEAParams
from .solver import Solver, StaticResult

logger = get_logger(__name__)


class ObjectiveFunction:
    """Evaluate a multi-case objective through overridable pure hooks.

    Task-specific objectives override only ``compute_*`` methods.  Lifecycle
    methods own caches, case validation and result-mesh bookkeeping.
    """

    def __init__(
        self,
        *,
        jacobian_needed: tuple[str, ...] = (),
        metric_names: tuple[str, ...] = (),
        case_weights: tuple[float, ...] | None = None,
    ) -> None:
        self._jacobian_needed = tuple(jacobian_needed)
        """Load components whose Jacobians are requested."""
        self._metric_names = tuple(metric_names)
        """Stable names shown in UI/history output."""
        self._case_weights = tuple(case_weights) if case_weights is not None else None
        """Aggregate weights per case."""
        self._fea_params: FEAParams | None = None
        """FEA definition used to rebuild case views for sensitivity trials."""
        self._iteration: int | None = None
        """Iteration associated with cached results."""
        self._fea_controller: torchfea.FEAController | None = None
        """Shared controller exposing the current Assembly."""
        self._fe_results: tuple[StaticResult, ...] = ()
        """Normalized backend results by case index."""
        self._case_objectives: tuple[torch.Tensor, ...] = ()
        """Cached scalar objective for each case."""
        self._objective: torch.Tensor | None = None
        """Weighted aggregate objective tensor."""
        self._metrics_by_case: tuple[tuple[float, ...], ...] = ()
        """Detached display metrics by case."""
        self._mesh_cases: dict[int, tuple[pyvista.DataSet, ...]] = {}
        """Cached preview meshes by case index."""
        self._initialized = False
        """Objective lifecycle initialization state."""

    @property
    def jacobian_needed(self) -> tuple[str, ...]:
        """Return requested parameterized FEA component names."""
        return self._jacobian_needed

    @property
    def metric_names(self) -> tuple[str, ...]:
        """Return display metric names."""
        return self._metric_names

    @property
    def case_weights(self) -> tuple[float, ...] | None:
        """Return optional multi-case weights."""
        return self._case_weights

    @property
    def fe_results(self) -> tuple[StaticResult, ...]:
        """Return current results ordered by case index."""
        return self._fe_results

    def initialize(self, fea_params: FEAParams | None = None) -> None:
        """Validate static objective requests against FEA definitions."""
        # TODO: Validate jacobian component names against FEAParams.
        self._fea_params = fea_params
        self._initialized = True

    def reinitialize(
        self,
        iteration: int,
        fea_controller: torchfea.FEAController | None,
        fe_results: tuple[StaticResult, ...],
    ) -> None:
        """Bind controllers/results for one iteration and clear old caches."""
        self._iteration = int(iteration)
        self._fea_controller = fea_controller
        self._fe_results = tuple(fe_results)
        self._case_objectives = ()
        self._objective = None
        self._metrics_by_case = ()
        self._mesh_cases.clear()

    def build_evaluation(self) -> None:
        """Evaluate every case and cache the weighted aggregate objective."""
        objectives: list[torch.Tensor] = []
        metrics: list[tuple[float, ...]] = []
        for case_index, result in enumerate(self._fe_results):
            assembly = self._fea_controller.assembly
            value = self.compute_case_objective(case_index, assembly, result)
            value = torch.as_tensor(value, dtype=torch.float32)
            if value.numel() != 1:
                raise ValueError(f"Case objective {case_index} must be scalar")
            objectives.append(value.reshape(()))
            metrics.append(
                tuple(
                    float(item)
                    for item in self.compute_case_metrics(case_index, assembly, result)
                )
            )
        self._case_objectives = tuple(objectives)
        self._objective = self.compute_multistep_objective(self._case_objectives)
        self._metrics_by_case = tuple(metrics)

    def build_mesh_case(self, case_index: int) -> None:
        """Build and cache one case's deformation preview mesh."""
        self._validate_case_index(case_index)
        result = self._fe_results[case_index]
        self._mesh_cases[case_index] = self._build_result_mesh(
            self._fea_controller.assembly, result
        )

    def export_case_result(self, target_path: str | Path, case_index: int) -> Path:
        """Create a case manifest and reserve backend result exports."""
        self._validate_case_index(case_index)
        path = Path(target_path)
        path.mkdir(parents=True, exist_ok=True)
        # TODO: Export TorchFEA model/result/Jacobian and off-screen preview.
        manifest = path / f"case_{case_index}_manifest.json"
        manifest.write_text('{"schema_version": 1}\n', encoding="utf-8")
        return manifest

    def get_objective(self) -> torch.Tensor:
        """Read the already-built aggregate objective."""
        if self._objective is None:
            raise RuntimeError("Objective has not been built")
        return self._objective

    def get_case_objective(self, case_index: int) -> torch.Tensor:
        """Read one cached case objective."""
        self._validate_case_index(case_index)
        return self._case_objectives[case_index]

    def get_metrics(self, case_index: int) -> tuple[float, ...]:
        """Read one case's detached display metrics."""
        self._validate_case_index(case_index)
        return self._metrics_by_case[case_index]

    def get_mesh_case(self, case_index: int) -> tuple[pyvista.DataSet, ...]:
        """Read a previously built result mesh cache."""
        self._validate_case_index(case_index)
        try:
            return self._mesh_cases[case_index]
        except KeyError as exc:
            raise RuntimeError(f"Mesh case {case_index} has not been built") from exc

    def compute_case_objective(
        self, case_index: int, assembly: torchfea.Assembly, result: StaticResult
    ) -> torch.Tensor:
        """Pure task hook for one case's scalar objective."""
        # TODO: Override in the task objective.
        return torch.zeros((), dtype=torch.float32)

    def compute_multistep_objective(
        self, case_objectives: tuple[torch.Tensor, ...]
    ) -> torch.Tensor:
        """Combine case objectives using configured case weights."""
        if not case_objectives:
            return torch.zeros((), dtype=torch.float32)
        weights = self._case_weights or tuple(1.0 for _ in case_objectives)
        if len(weights) != len(case_objectives):
            raise ValueError("case_weights length does not match number of cases")
        return sum(
            (weight * value for weight, value in zip(weights, case_objectives)),
            torch.zeros_like(case_objectives[0]),
        )

    def compute_case_metrics(
        self, case_index: int, assembly: torchfea.Assembly, result: StaticResult
    ) -> tuple[float, ...]:
        """Pure task hook for detached display metrics."""
        # TODO: Override for display metrics.
        return tuple(0.0 for _ in self._metric_names)

    def compute_objective(
        self,
        case_assemblies: tuple[torchfea.Assembly, ...],
        fe_results: tuple[StaticResult, ...],
    ) -> torch.Tensor:
        """Re-evaluate the aggregate objective for sensitivity analysis."""
        values = tuple(
            self.compute_case_objective(index, assembly, result)
            for index, (assembly, result) in enumerate(zip(case_assemblies, fe_results))
        )
        return self.compute_multistep_objective(values)

    def compute_sensitivities(
        self,
        registry: DesignRegistry,
        solver: Solver,
        fe_results: tuple[StaticResult, ...],
    ) -> Mapping[DesignKey, torch.Tensor] | None:
        """Return task-provided sensitivities or ``None`` for backend analysis."""
        # Task objectives may provide an analytic or custom sensitivity hook;
        # the default delegates to SensitivityAnalyzer's backend path.
        return None

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist objective metadata and the current scalar value."""
        path = Path(folder_path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "objective.json").write_text(
            str(
                {
                    "iteration": iteration,
                    "objective": float(self.get_objective().detach())
                    if self._objective is not None
                    else None,
                }
            ),
            encoding="utf-8",
        )

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Restore objective metadata from a checkpoint."""
        # TODO: Restore objective/metrics and result manifest for Observer.
        return

    def _validate_case_index(self, case_index: int) -> None:
        if not 0 <= int(case_index) < len(self._fe_results):
            raise IndexError(
                f"case_index {case_index} is outside [0, {len(self._fe_results)})"
            )

    def _build_result_mesh(
        self, assembly: torchfea.Assembly, result: StaticResult
    ) -> tuple[pyvista.DataSet, ...]:
        # TODO: Delegate deformation mesh construction to the TorchFEA model.
        return ()
