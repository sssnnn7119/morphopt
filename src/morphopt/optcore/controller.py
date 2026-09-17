"""V4 optimization controller and iteration lifecycle.

The controller is the orchestration boundary of MorphOpt.  It deliberately
keeps domain definitions in ``Params`` and numerical work in ``Solver``;
its job is to make their order of execution explicit and reproducible.

The run has two nested lifecycles:

* the run lifecycle creates the result directory, runtime object graph,
  history writer; ``TaskRunner`` owns the process boundary around it;
* the iteration lifecycle rebuilds an Assembly, solves all load cases,
  evaluates the objective, computes sensitivities, commits updater changes,
  and finally persists a detached record.

The next iteration always starts from the committed Params state.  The
temporary ``update_assembly()`` path is used by sensitivity analysis only,
where a differentiable trial graph is required; it is not the normal model
construction path.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Literal

import torchfea

from morphopt._torch import torch
from morphopt.logging import configure_logging, get_logger

from .design_registry import DesignKey, DesignRegistry
from .history import History, HistoryRecord
from .modelparams.params import Params
from .objective import ObjectiveFunction
from .protocols import JsonObject, JsonValue
from .sensitivity import SensitivityAnalyzer
from .solver import Solver, StaticResult
from .updaters.base import Updaters

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StepResult:
    """Named immutable replacement for the V3 positional step tuple.

    Every field is detached or serializable at the moment the result is
    returned, so the controller can persist it without retaining the FEA graph.
    """

    iteration: int
    objective: torch.Tensor
    metrics_by_case: tuple[tuple[float, ...], ...] = ()
    fe_results: tuple[StaticResult, ...] = ()
    sensitivities: Mapping[DesignKey, torch.Tensor] = field(default_factory=dict)
    changes: Mapping[DesignKey, torch.Tensor] = field(default_factory=dict)
    phase_times: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """Versioned event sent from Controller to UI and TaskRunner."""

    event_type: Literal[
        "started",
        "iteration_finished",
        "restart_requested",
        "warning",
        "failed",
        "stopped",
        "finished",
    ]
    run_id: str
    timestamp: float = field(default_factory=time.time)
    payload: Mapping[str, JsonValue] = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self) -> JsonObject:
        """Convert the event to a multiprocessing/JSON-safe dictionary."""
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, JsonValue]) -> RuntimeEvent:
        """Reconstruct an event received from a queue or checkpoint."""
        return cls(
            event_type=data["event_type"],  # type: ignore[arg-type]
            run_id=str(data["run_id"]),
            timestamp=float(data["timestamp"]),
            payload=dict(data.get("payload", {})),
            schema_version=int(data.get("schema_version", 1)),
        )


class Controller:
    """Build the runtime graph and execute the outer optimization loop.

    Controller owns orchestration only.  Geometry, materials, FEA components,
    objective evaluation, sensitivity analysis and local updates remain in
    their dedicated objects and are called in the documented lifecycle order.

    A controller-side ``device`` is reserved for orchestration tensors and
    bookkeeping.  ``solver_device_names`` belongs exclusively to the FEA
    solver and ``updater_device`` belongs exclusively to local design updates;
    changing one of them does not silently move the other two subsystems.
    """

    def __init__(
        self,
        *,
        params_factory: Callable[[], Params] | None = None,
        solver_factory: Callable[..., Solver] = Solver,
        objective_factory: Callable[[], ObjectiveFunction] = ObjectiveFunction,
        sensitivity_factory: Callable[[], SensitivityAnalyzer] = SensitivityAnalyzer,
        updaters_factory: Callable[..., Updaters] | None = None,
        result_root: str | Path = ".results",
        optimization_name: str = "untitled",
        device: str = "cpu",
        solver_device_names: tuple[str, ...] = (),
        updater_device: str = "cpu",
        maximum_iterations: int = 100,
        checkpoint_interval: int = 1,
        worker_restart_interval: int = 20,
        debug: bool = False,
        data_queue: Queue | None = None,
        stop_event: Event | None = None,
    ) -> None:
        self._params_factory = params_factory
        """Factory for the task-specific Params object."""
        self._solver_factory = solver_factory
        """Factory for the numerical Solver object."""
        self._objective_factory = objective_factory
        """Factory for the objective definition."""
        self._sensitivity_factory = sensitivity_factory
        """Factory for sensitivity analysis."""
        self._updaters_factory = updaters_factory
        """Factory for local design updaters."""
        self._result_root = Path(result_root)
        """Root directory for all run artifacts."""
        self._optimization_name = str(optimization_name)
        """Human-readable run name."""
        self._device = str(device)
        """Device used by controller-side orchestration and auxiliary tensors."""
        self._solver_device_names = tuple(str(name) for name in solver_device_names)
        """Explicit devices reserved for the finite-element Solver."""
        self._updater_device = str(updater_device)
        """Device reserved for local Updater optimization."""
        self._maximum_iterations = int(maximum_iterations)
        """Outer optimization limit."""
        self._checkpoint_interval = max(1, int(checkpoint_interval))
        """Iterations between checkpoints."""
        self._worker_restart_interval = int(worker_restart_interval)
        """Optional child-process recycle interval."""
        self._debug = bool(debug)
        """Whether to keep execution in the current process."""
        self._data_queue = data_queue
        """Queue carrying structured progress events."""
        self._stop_event = stop_event
        """Shared event used for cooperative cancellation."""

        self._params: Params | None = None
        """Runtime Params graph for the current run."""
        self._solver: Solver | None = None
        """Runtime solver orchestration object."""
        self._objective: ObjectiveFunction | None = None
        """Runtime objective evaluator."""
        self._sensitivity: SensitivityAnalyzer | None = None
        """Runtime sensitivity analyzer."""
        self._registry: DesignRegistry | None = None
        """Design-variable ownership registry."""
        self._updaters: Updaters | None = None
        """Collection of geometry/material/FEA updaters."""
        self._history: History | None = None
        """Persistent iteration history writer."""
        self._result_path: Path | None = None
        """Directory for the active optimization run."""
        # All load cases share one Assembly and one backend controller.  A
        # case index belongs to LoadStep/StaticResult, not to a controller.
        self._torchfea_FEAController: torchfea.FEAController | None = None
        """One shared multi-case backend controller."""
        self._stop_requested = False
        """Local graceful-stop flag."""
        self._restart_requested = False
        """Indicates that the worker should be recycled."""
        self._initialized = False
        """Runtime graph initialization state."""
        self._run_id = uuid.uuid4().hex
        """Stable identifier for progress events."""

    @property
    def params_factory(self) -> Callable[[], Params] | None:
        """Return the Params factory."""
        return self._params_factory

    @property
    def solver_factory(self) -> Callable[..., Solver]:
        """Return the Solver factory."""
        return self._solver_factory

    @property
    def objective_factory(self) -> Callable[[], ObjectiveFunction]:
        """Return the objective factory."""
        return self._objective_factory

    @property
    def sensitivity_factory(self) -> Callable[[], SensitivityAnalyzer]:
        """Return the sensitivity factory."""
        return self._sensitivity_factory

    @property
    def updaters_factory(self) -> Callable[..., Updaters] | None:
        """Return the Updaters factory."""
        return self._updaters_factory

    @property
    def result_root(self) -> Path:
        """Return the configured result root."""
        return self._result_root

    @property
    def optimization_name(self) -> str:
        """Return the human-readable optimization name."""
        return self._optimization_name

    @property
    def device(self) -> str:
        """Return the controller-side orchestration device."""
        return self._device

    @property
    def solver_device_names(self) -> tuple[str, ...]:
        """Return the devices reserved for finite-element solving."""
        return self._solver_device_names

    @property
    def updater_device(self) -> str:
        """Return the device reserved for local design updates."""
        return self._updater_device

    @property
    def maximum_iterations(self) -> int:
        """Return the outer iteration limit."""
        return self._maximum_iterations

    @property
    def checkpoint_interval(self) -> int:
        """Return the checkpoint interval."""
        return self._checkpoint_interval

    @property
    def worker_restart_interval(self) -> int:
        """Return the child-process recycling interval."""
        return self._worker_restart_interval

    @property
    def debug(self) -> bool:
        """Return whether the controller runs in debug mode."""
        return self._debug

    @property
    def data_queue(self) -> Queue | None:
        """Return the structured progress queue."""
        return self._data_queue

    @property
    def stop_event(self) -> Event | None:
        """Return the cross-process stop event."""
        return self._stop_event

    def start_optimization(self, main_file_path: str | Path | None = None) -> None:
        """Create a result directory and run from iteration zero.

        The method is the normal child-process entry point.  Setup is kept
        outside the ``try`` block because a failed setup must be raised to the
        caller immediately; once the loop starts, failures are also published
        as structured runtime events before being re-raised.
        """
        # 1. Establish the immutable run layout and copy the user task into it.
        self.initialize_path(main_file_path)
        # 2. Construct and connect Params, Solver, Objective, Registry,
        #    SensitivityAnalyzer, Updaters and History exactly once.
        self.initialize()
        # 3. Let the UI/supervisor know that the run has a concrete path.
        self._publish_progress("started", {"result_path": str(self._result_path)})
        try:
            # 4. Execute iteration chunks until completion, stop or worker
            #    recycling.  _opt_loop owns persistence for every step.
            self._opt_loop(0)
        except Exception as exc:
            # 5. Preserve the original exception while exposing a serializable
            #    failure event to a parent process.
            self._publish_progress("failed", {"error": repr(exc)})
            raise

    def restart_optimization(
        self, result_path: str | Path, target_iteration: int | None = None
    ) -> None:
        """Restore a checkpoint and continue at the following iteration.

        Restart uses the same construction path as a fresh run.  The only
        difference is that persisted Params/Solver/Objective/Registry/History
        state is loaded before choosing the next iteration index.  This keeps a
        restarted worker behaviorally equivalent to the original worker.
        """
        # 1. Reuse the existing run directory; a restart never creates a
        #    second result tree for the same optimization.
        self._result_path = Path(result_path)
        self._result_path.mkdir(parents=True, exist_ok=True)
        configure_logging(self._result_path / "logs" / "morphopt.log")
        # 2. Recreate the runtime object graph before loading its state.
        self.initialize()
        assert self._history is not None
        # History is a run-level log, not checkpoint state.  Parse it before
        # selecting the continuation iteration so a restart sees every
        # completed result even when no checkpoint was written that round.
        self._history.load(self._result_path, target_iteration)
        if target_iteration is not None:
            # 3. Restore one complete model checkpoint.  The log remains at
            #    the run root and is never copied into the checkpoint.
            checkpoint = (
                self._result_path
                / "checkpoints"
                / f"iteration_{int(target_iteration):06d}"
            )
            self.load(checkpoint, int(target_iteration))
        # 4. Continue strictly after the latest restored record.
        current_iteration = self._history.get_current_iteration()
        start = current_iteration + 1 if current_iteration is not None else 0
        self._publish_progress(
            "started",
            {"result_path": str(self._result_path), "restart_from": target_iteration},
        )
        try:
            # 5. The same loop handles normal completion and another recycle.
            self._opt_loop(start)
        except Exception as exc:
            self._publish_progress("failed", {"error": repr(exc)})
            raise

    def initialize_path(self, main_file_path: str | Path | None = None) -> None:
        """Create the run directory, artifact folders and task snapshot.

        All files produced by a run live below one timestamped directory.  The
        fixed subdirectory names are part of the monitoring/persistence
        contract, so readers can locate logs, checkpoints and iteration
        results without inspecting implementation details.
        """
        # The short run id prevents collisions when two launches share a
        # timestamp down to the second.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
        self._result_path = (
            self._result_root / f"{self._optimization_name}_T{stamp}_{self._run_id[:8]}"
        )
        # Create the complete artifact layout before any domain object starts
        # writing files.  This makes even an early failure diagnosable.
        for name in ("cache", "logs", "scripts", "checkpoints", "results"):
            (self._result_path / name).mkdir(parents=True, exist_ok=True)
        configure_logging(self._result_path / "logs" / "morphopt.log")
        if main_file_path is not None:
            source = Path(main_file_path)
            if source.exists() and source.is_file():
                # Keep the exact task source used for this run next to its
                # generated artifacts for reproducibility.
                shutil.copy2(source, self._result_path / "scripts" / source.name)

    def step(self, iteration: int) -> StepResult:
        """Execute one complete model, solve, objective and update cycle.

        The phase order is the central V4 runtime contract:

        ``Params → Assembly → FEA solve → objective/sensitivity → Updaters``.

        Only the final updater changes are committed to Params.  The Assembly
        used by this step is therefore disposable and will be rebuilt on the
        next call.  ``phase_times`` records the same boundaries used by the
        progress UI and history CSV.  The outer entry point calls
        ``initialize()`` once before the first step; this hot path assumes that
        lifecycle contract and performs no repeated state checks.
        """
        phase_times: dict[str, float] = {}

        # Phase 1 — rebuild the current physical model from committed Params.
        # This is the ordinary optimization path; it never applies a trial
        # design directly to the previous Assembly.
        phase_start = time.perf_counter()
        self._clear_runtime_cache()
        self._params.reinitialize(iteration)
        geometry_path = (self._result_path or self._result_root) / "cache" / f"iteration_{iteration:06d}"
        self._params.build_assembly(geometry_path)
        # Load cases are views over this newly-created Assembly.  They belong
        # to the current solve only and are rebuilt together with the FEA
        # components; no trial design values are written at this stage.
        self._params.get_fea().build_case_assemblies()
        phase_times["assembly"] = time.perf_counter() - phase_start

        # Phase 2 — register design blocks and create one shared FEA backend
        # for every load case.  Case-specific data is held by LoadStep and
        # StaticResult, not by separate backend controllers.
        phase_start = time.perf_counter()
        self._registry.reinitialize(iteration)
        self._registry.build_design_delta()
        self.build_fea_controller()
        phase_times["model"] = time.perf_counter() - phase_start

        # Phase 3 — configure the dedicated solver and solve all cases.  The
        # solver decides which devices run FEA; the outer controller device is
        # not used as an implicit override.
        phase_start = time.perf_counter()
        self._solver.reinitialize(iteration)
        self._solver.build_solvers(self._torchfea_FEAController)
        self._solver.solve(
            self._torchfea_FEAController, self._objective.jacobian_needed
        )
        fe_results = self._solver.get_results()
        phase_times["solve"] = time.perf_counter() - phase_start

        # Phase 4 — evaluate the objective and ask SensitivityAnalyzer to
        # build the differentiable trial graph.  Its temporary
        # DesignRegistry.update_assembly() calls are scoped to this phase.
        phase_start = time.perf_counter()
        self._objective.reinitialize(
            iteration, self._torchfea_FEAController, fe_results
        )
        self._objective.build_evaluation()
        self._sensitivity.reinitialize(iteration, fe_results)
        self._sensitivity.build_sensitivities()
        sensitivities = self._sensitivity.get_sensitivities()
        phase_times["objective"] = time.perf_counter() - phase_start

        # Phase 5 — let each updater compute and commit its local design
        # change.  The registry writes these changes back to the owner Params;
        # the next iteration will consume those committed values.
        phase_start = time.perf_counter()
        changes: Mapping[DesignKey, torch.Tensor] = {}
        self._updaters.reinitialize(iteration, sensitivities)
        self._updaters.update()
        changes = self._updaters.get_changes()
        if changes:
            self._registry.apply_design_delta(changes)
        phase_times["update"] = time.perf_counter() - phase_start

        # Return only detached, serializable iteration data.  Keeping the FEA
        # graph out of StepResult allows history/checkpoint code to release the
        # current Assembly immediately after this step.
        result = StepResult(
            iteration=int(iteration),
            objective=self._objective.get_objective().detach(),
            metrics_by_case=tuple(
                self._objective.get_metrics(index) for index in range(len(fe_results))
            ),
            fe_results=tuple(fe_results),
            sensitivities=sensitivities,
            changes=changes,
            phase_times=phase_times,
        )
        return result

    def build_fea_controller(self) -> None:
        """Create one shared FEA controller for the current Assembly.

        ``Params`` creates the Assembly; ``Controller`` owns the backend
        controller.  A real TorchFEA Assembly is assigned directly to that
        controller; lifecycle-only tests use the typed `_AssemblyController`
        subclass below.  Both paths expose one controller for all load cases
        and therefore share backend memory.
        """
        self._torchfea_FEAController = None
        assembly = self._params.get_assembly()
        fea = self._params.get_fea()
        num_cases = int(fea.get_num_load_steps())
        # Params only prepares the current Assembly.  Binding the Assembly to
        # a backend controller belongs to this orchestration boundary.
        has_backend_model = bool(
            assembly is not None
            and (getattr(assembly, "_parts", {}) or getattr(assembly, "_instances", {}))
        )
        if has_backend_model:
            controller = torchfea.FEAController()
            controller.assembly = assembly
            self._torchfea_FEAController = controller
            return
        self._torchfea_FEAController = _AssemblyController(assembly, num_cases)

    def get_fea_controller(self) -> torchfea.FEAController | None:
        """Return the shared multi-case FEA controller."""
        return self._torchfea_FEAController

    def get_params(self) -> Params:
        """Return initialized Params for task code and diagnostics."""
        if self._params is None:
            raise RuntimeError("Controller has not been initialized")
        return self._params

    def get_assembly(self) -> torchfea.Assembly | None:
        """Return the latest complete Assembly produced by Params."""
        params = self.get_params()
        return params.get_assembly()

    def get_history(self) -> History:
        """Return the live History object for monitoring and post-processing."""
        if self._history is None:
            raise RuntimeError("Controller has not been initialized")
        return self._history

    def request_stop(self) -> None:
        """Request a graceful stop after the current step is recorded."""
        self._stop_requested = True
        if self._stop_event is not None:
            self._stop_event.set()

    def change_device(self, device: str) -> None:
        """Change controller-side placement without changing Solver or Updaters."""
        self._device = str(device)

    def change_solver_devices(self, device_names: tuple[str, ...]) -> None:
        """Change future finite-element Solver placement explicitly."""
        self._solver_device_names = tuple(str(name) for name in device_names)
        if self._solver is not None:
            self._solver.change_devices(self._solver_device_names)

    def initialize(self) -> None:
        """Create and connect the run-time object graph once per run.

        Initialization establishes relationships and persistent writers; it
        does not build the iteration Assembly.  Assembly creation belongs to
        ``step()`` because committed design values can change between steps.
        """
        # 1. Instantiate every runtime object in the same place where its
        #    initialization order is visible.  The optional factories are
        #    injection points for task definitions and tests; the normal path
        #    uses the concrete V4 classes directly.
        from .modelparams.params import Params
        from .updaters.base import Updaters

        self._params = (self._params_factory or Params)()
        self._solver = self._solver_factory(device_names=self._solver_device_names)
        self._objective = self._objective_factory()
        self._sensitivity = self._sensitivity_factory()
        self._updaters = (self._updaters_factory or Updaters)(
            device=self._updater_device
        )

        assert (
            self._params is not None
            and self._solver is not None
            and self._objective is not None
        )
        # 2. Let Params define its three processors and static model schema.
        self._params.initialize()
        # 3. Freeze design ownership and ordering before sensitivities begin.
        self._registry = DesignRegistry()
        self._registry.initialize(self._params)
        fea = self._params.get_fea()
        # 4. Connect the shared load-case count to Solver and Objective.
        self._solver.initialize(fea.get_num_load_steps())
        self._objective.initialize(fea)
        assert self._sensitivity is not None
        # 5. Give sensitivity analysis the objective, design registry and
        # solver protocol it uses to build trial graphs.
        self._sensitivity.initialize(self._objective, self._registry, self._solver)
        assert self._updaters is not None
        # 6. Bind local updaters to Params and the same design registry.
        self._updaters.initialize(self._params, self._registry)
        # 7. Initialize durable history before the first progress event.
        self._history = History(
            self._result_path or self._result_root, self._objective.metric_names
        )
        history_file = self._history.log_directory / "history.json"
        if history_file.exists():
            self._history.load(self._result_path or self._result_root)
        else:
            self._history.initialize()
            self._history.save(self._result_path or self._result_root)
        self._initialized = True

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist one self-contained checkpoint.

        The checkpoint contains only the state needed to recreate the next
        iteration: Params, Solver, Objective and Registry, plus a manifest
        identifying the schema and completed iteration.  History remains in
        the run's ``logs`` directory and is never duplicated here.
        """
        folder = Path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
        assert self._params is not None and self._solver is not None
        assert self._objective is not None and self._registry is not None
        # Each component writes its own state so its persistence format stays
        # local to its responsibility.
        self._params.save(folder, iteration)
        self._solver.save(folder, iteration)
        self._objective.save(folder, iteration)
        self._registry.save(folder, iteration)
        (folder / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "iteration": iteration}, indent=2),
            encoding="utf-8",
        )

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Load one complete checkpoint produced by :meth:`save`."""
        folder = Path(folder_path)
        assert self._params is not None and self._solver is not None
        assert self._objective is not None and self._registry is not None
        # Restore in the same dependency order used during initialization:
        # definitions first, then numerical/runtime consumers.
        self._params.load(folder, iteration)
        self._solver.load(folder, iteration)
        self._objective.load(folder, iteration)
        self._registry.load(folder, iteration)

    def _opt_loop(self, start_iteration: int) -> None:
        """Run the outer loop and own every iteration-level side effect.

        ``step()`` computes a result.  This method gives that result a durable
        home, publishes monitoring events, and decides whether the current
        worker should finish or hand control back to :class:`TaskRunner`.
        """
        assert self._history is not None
        for iteration in range(int(start_iteration), self._maximum_iterations):
            # 1. Execute the five-phase model/solve/objective/update cycle.
            result = self.step(iteration)
            # 2. Export a stable result directory and any objective case files.
            result_path = self._export_iteration_results(result)
            if self._objective is not None:
                for case_index in range(len(result.fe_results)):
                    self._objective.export_case_result(result_path, case_index)
            record = self._build_history_record(result, result_path)
            # 3. Append a detached summary and flush JSON/CSV immediately so a
            #    monitoring process can inspect progress while the run lives.
            self._history.add_record(record)
            self._history.save(self._result_path or self._result_root, iteration)
            # 4. Save regular checkpoints after the record is durable.
            if (
                iteration % self._checkpoint_interval == 0
                and self._result_path is not None
            ):
                self.save(
                    self._result_path / "checkpoints" / f"iteration_{iteration:06d}",
                    iteration,
                )
            # 5. Publish the completed iteration only after all files exist.
            self._publish_progress(
                "iteration_finished",
                {
                    "iteration": iteration,
                    "objective": float(result.objective),
                    "result_path": str(result_path),
                },
            )
            if self._should_stop(iteration, result):
                external_stop = self._stop_requested or bool(
                    self._stop_event is not None and self._stop_event.is_set()
                )
                # A maximum-iteration stop is a normal finish; an explicit
                # request is reported separately for the UI.
                self._publish_progress(
                    "stopped" if external_stop else "finished", {"iteration": iteration}
                )
                return
            if (
                not self._debug
                and self._worker_restart_interval > 0
                and (iteration - start_iteration + 1) >= self._worker_restart_interval
            ):
                # 6. End this worker chunk at a resumable boundary.  The
                #    parent TaskRunner will launch a fresh worker from here.
                self._restart_requested = True
                # A worker recycle is itself a resumable boundary.  Persist
                # this iteration even when the regular checkpoint interval is
                # larger than the recycle interval.
                if self._result_path is not None:
                    checkpoint = (
                        self._result_path / "checkpoints" / f"iteration_{iteration:06d}"
                    )
                    if not (checkpoint / "manifest.json").exists():
                        self.save(checkpoint, iteration)
                self._publish_progress(
                    "restart_requested",
                    {
                        "iteration": iteration,
                        "result_path": (
                            str(self._result_path) if self._result_path else None
                        ),
                    },
                )
                return
        # The range can be empty after a restart at the final iteration.
        self._publish_progress(
            "finished", {"iteration": self._history.get_current_iteration()}
        )

    def _clear_runtime_cache(self) -> None:
        """Release per-iteration backend handles before rebuilding Assembly.

        Params owns committed design definitions; the FEA controller references
        only the previous iteration's Assembly and must not leak into the next
        one.
        """
        self._torchfea_FEAController = None

    def _export_iteration_results(self, step_result: StepResult) -> Path:
        """Create a stable result directory and write its manifest.

        Numerical exporters are owned by Objective/FEA components.  The
        controller only provides the deterministic location and iteration
        metadata that lets monitoring discover those files.
        """
        root = (
            (self._result_path or self._result_root)
            / "results"
            / f"iteration_{step_result.iteration:06d}"
        )
        root.mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "iteration": step_result.iteration,
                    "objective": float(step_result.objective),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return root

    def _build_history_record(
        self, step_result: StepResult, result_path: Path
    ) -> HistoryRecord:
        """Convert a StepResult into detached, CSV-safe History data."""
        converged = tuple(bool(result.converged) for result in step_result.fe_results)
        return HistoryRecord(
            iteration=step_result.iteration,
            objective=float(step_result.objective),
            metrics_by_case=step_result.metrics_by_case,
            phase_times=step_result.phase_times,
            converged_by_case=converged,
            result_path=result_path,
        )

    def _publish_progress(
        self, event_type: str, payload: Mapping[str, JsonValue]
    ) -> None:
        """Send one versioned event to both queue monitoring and logging.

        The queue receives only JSON-safe data.  Logging remains a local
        fallback, so a missing UI consumer never changes optimization logic.
        """
        event = RuntimeEvent(
            event_type=event_type, run_id=self._run_id, payload=dict(payload)
        )
        if self._data_queue is not None:
            try:
                self._data_queue.put(event.to_dict())
            except Exception:
                logger.exception("Unable to publish runtime event")
        logger.info("%s: %s", event_type, dict(payload))

    def _should_stop(self, iteration: int, step_result: StepResult) -> bool:
        """Return whether this completed step should end the current chunk."""
        return (
            self._stop_requested
            or bool(self._stop_event is not None and self._stop_event.is_set())
            or iteration + 1 >= self._maximum_iterations
        )


class _AssemblyController(torchfea.FEAController):
    """Backend-neutral FEA-controller protocol implementation.

    This object is intentionally small: it gives the Controller and Solver a
    stable shared-controller contract when a real TorchFEA installation is not
    available.  It is not a numerical solver and does not replace TorchFEA;
    its placeholder results keep lifecycle, persistence and process tests
    independent from the external backend.
    """

    def __init__(self, assembly: torchfea.Assembly | None, num_cases: int = 0) -> None:
        """Create a typed placeholder controller for lifecycle-only tests."""
        super().__init__()
        self.assembly = assembly
        """Shared Assembly used by the placeholder backend controller."""
        self.num_cases = int(num_cases)
        """Number of LoadStep result slots handled by the controller."""
        self.solver: torchfea.solver.StaticImplicitSolver | None = None
        """Placeholder solver attached by Solver.build_solvers()."""

    def solve(self, *, need_jacobian: bool = False) -> tuple[StaticResult, ...]:
        """Return one placeholder result for each registered load case."""
        return tuple(StaticResult(step_index=index) for index in range(self.num_cases))

    def change_device(self, device: str) -> None:
        """Accept the explicit FEA device for the placeholder backend."""
        return
