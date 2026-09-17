"""V4 end-to-end bending-actuator workflow smoke example.

The V4 architecture keeps the numerical TorchFEA adapter behind ``Solver``.
This example therefore uses a small differentiable surrogate controller with
the same multi-case result contract.  It exercises the complete public
pipeline: Params, DesignRegistry, Solver, ObjectiveFunction, sensitivity,
Updater, History, checkpoints and the task runner.  Replacing
``BendingAssemblyController`` with the TorchFEA adapter leaves the task
definition and device boundaries unchanged.
"""

from __future__ import annotations

from pathlib import Path

import morphopt
from morphopt._torch import torch
from morphopt.optcore.controller import _AssemblyController
from morphopt.optcore.modelparams.components.steps import LoadStep
from morphopt.optcore.modelparams.geometry import GeometryParams
from morphopt.optcore.modelparams.parts.boundary import BoundaryPart
from morphopt.optcore.modelparams.params import Params
from morphopt.optcore.objective import ObjectiveFunction
from morphopt.optcore.solver import Solver, StaticResult
from morphopt.optcore.updaters.base import Updaters
from morphopt.optcore.updaters.geometry import BoundaryPartUpdater


# Device domains are independent: change any one without changing the other
# two (for example, use ``cuda:0`` for the solver and keep the updater on CPU).
CONTROLLER_DEVICE = "cpu"
SOLVER_DEVICE_NAMES = ("cpu",)
UPDATER_DEVICE = "cpu"


class BendingGeometry(GeometryParams):
    """Minimal boundary Part representing the actuator design variables."""

    def define_parts(self) -> None:
        # The real task can replace this Part with a BSP/OffsetShell Part.
        # The control-point tensor is deliberately small so this smoke run is
        # fast in CPU-only development environments.
        control_points = torch.zeros((8, 3), dtype=torch.float32)
        control_points[:, 0] = torch.linspace(0.0, 1.0, 8)
        self.add_part(BoundaryPart("actuator", control_points=control_points))


class BendingParams(Params):
    """Assembly pipeline for the bending-actuator smoke problem."""

    def __init__(self) -> None:
        super().__init__(geometry_factory=BendingGeometry)

    def initialize(self) -> None:
        super().initialize()
        self.get_fea().add_step(LoadStep("pressure", ()))


class BendingAssemblyController(_AssemblyController):
    """Small multi-case backend stand-in with TorchFEA-compatible results."""

    def solve(self, *, need_jacobian: bool = False) -> tuple[StaticResult, ...]:
        part = self.assembly.parts[0]
        parameters = part.get_parameters().reshape(-1)
        # ``GC[-2]`` mirrors the legacy bending-actuator objective: the first
        # generalized coordinate is the tip displacement and the second is a
        # small rotation response used only as a diagnostic metric.
        tip_displacement = 1.0 - parameters.mean()
        tip_rotation = 0.1 * tip_displacement
        gc = torch.stack((tip_displacement, tip_rotation))
        return tuple(StaticResult(GC=gc, step_index=index) for index in range(self.num_cases))


class BendingSolver(Solver):
    """Solver configuration with an explicitly independent FEA device."""

    def __init__(self, *, device_names: tuple[str, ...] = ()) -> None:
        super().__init__(device_names=device_names, num_processes=1, maximum_iterations=50)


class BendingObjective(ObjectiveFunction):
    """Minimize the squared tip displacement over all load cases."""

    def __init__(self) -> None:
        super().__init__(metric_names=("tip_displacement",))
        self._target = 0.0
        """Desired tip displacement of the surrogate response."""

    def compute_case_objective(self, case_index: int, assembly: object, result: StaticResult) -> torch.Tensor:
        displacement = result.GC[-2]
        return (displacement - self._target) ** 2

    def compute_case_metrics(self, case_index: int, assembly: object, result: StaticResult) -> tuple[float, ...]:
        return (float(result.GC[-2]),)

    def compute_sensitivities(self, registry: object, solver: object, fe_results: tuple[StaticResult, ...]):
        """Return the analytic surrogate gradient for the current Assembly."""
        if not fe_results:
            return {}
        displacement = fe_results[0].GC[-2]
        gradients = {}
        for block in registry.get_blocks():
            owner = block.owner
            values = owner.get_parameters()
            gradients[block.key] = torch.full_like(values, -2.0 * displacement / values.numel())
        return gradients


class BendingUpdaters(Updaters):
    """One geometry updater with an independently selected device."""

    def define_updaters(self) -> None:
        params = self._params
        part = params.get_geometry().get_part("actuator")
        self.add_updater(BoundaryPartUpdater("actuator_geometry", part, step_size=0.25))

    def initialize(self, params: object | None = None, registry: object | None = None) -> None:
        self._params = params
        """Problem graph used to resolve the updater owner."""
        super().initialize(params, registry)


class BendingController(morphopt.Controller):
    """Controller with three explicit device domains.

    ``device`` is reserved for controller-side tensors, ``solver_device_names``
    is reserved for TorchFEA, and ``updater_device`` is reserved for local
    design updates.  They are intentionally configured independently.
    """

    def __init__(self, **kwargs: object) -> None:
        defaults = {
            "params_factory": BendingParams,
            "solver_factory": BendingSolver,
            "objective_factory": BendingObjective,
            "updaters_factory": BendingUpdaters,
            "optimization_name": "bendingactuator",
            "result_root": Path(__file__).resolve().parents[1] / ".results",
            "device": CONTROLLER_DEVICE,
            "solver_device_names": SOLVER_DEVICE_NAMES,
            "updater_device": UPDATER_DEVICE,
            "maximum_iterations": 5,
            "checkpoint_interval": 1,
            "worker_restart_interval": 0,
            "debug": True,
        }
        defaults.update(kwargs)
        super().__init__(**defaults)

    def build_fea_controller(self) -> None:
        assembly = self.get_assembly()
        num_cases = self.get_params().get_fea().get_num_load_steps()
        self._torchfea_FEAController = BendingAssemblyController(assembly, num_cases)


def build_controller(**options: object) -> BendingController:
    """Top-level factory usable by both debug and spawn task runners."""
    result_root = Path(__import__("os").environ.get("MORPHOPT_RESULT_ROOT", "/tmp/morphopt4-results"))
    return BendingController(result_root=result_root, **options)


def main() -> int:
    """Run five iterations and print the generated result directory."""
    # ``MORPHOPT_RESULT_ROOT`` lets CI/read-only source checkouts choose a
    # writable artifact directory; normal installations may point it at
    # ``.results`` in the project root.
    debug = __import__("os").environ.get("MORPHOPT_DEBUG", "0").lower() in {"1", "true", "yes"}
    runner = morphopt.start_optimization(build_controller, main_file_path=__file__, debug=debug)
    if not debug:
        runner.wait()
    print(f"MorphOpt V4 result: {runner.get_result_path()}")
    return int(runner.exit_code or 0)


if __name__ == "__main__":
    raise SystemExit(main())
