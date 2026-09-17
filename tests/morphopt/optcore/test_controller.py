"""test controller tests."""

from morphopt._torch import torch
from morphopt.optcore.controller import Controller
from morphopt.optcore.design_registry import DesignKey
from morphopt.optcore.modelparams.geometry import GeometryParams
from morphopt.optcore.modelparams.params import Params
from morphopt.optcore.modelparams.parts.base import BasePartDefinition
import torchfea


class TrackingPart(BasePartDefinition):
    """Small updateable owner used to observe the controller lifecycle."""

    def __init__(self):
        super().__init__("tracked")
        self.parameters = torch.as_tensor([1.0])
        self.delta = torch.zeros_like(self.parameters)
        self.build_values = []
        self.build_paths = []
        self.build_update_calls = []
        self.update_calls = 0

    def build_part(self, path_result=None, pools=None):
        self.build_values.append(float(self.parameters[0]))
        self.build_paths.append(path_result)
        self.build_update_calls.append(self.update_calls)
        part = torchfea.Part(
            torch.as_tensor(
                ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
            )
        )
        element = torchfea.elements.initialize_element(
            "C3D4", torch.as_tensor([0]), torch.as_tensor(((0, 1, 2, 3),))
        )
        element.set_materials(torchfea.materials.LinearElastic(1.0, 0.3))
        part.add_element(element, "solid")
        self._torchfea_Part = part

    def get_parameters(self):
        return self.parameters

    def set_parameters(self, values):
        self.parameters = torch.as_tensor(values).clone()

    def get_design_delta(self):
        return self.delta

    def build_design_delta(self):
        self.delta = torch.zeros_like(self.parameters)

    def set_design_delta(self, values):
        self.delta = values

    def update_assembly(self, values):
        self.update_calls += 1
        self.delta = values

    def apply_design_delta(self, values):
        self.parameters = self.parameters + values


class TrackingGeometry(GeometryParams):
    """Geometry definition exposing one owner for iteration assertions."""

    def __init__(self, part):
        super().__init__()
        self.part = part

    def define_parts(self):
        self.add_part(self.part)


def make_tracking_params(part):
    return Params(geometry_factory=lambda: TrackingGeometry(part))


def test_controller_smoke(tmp_path):
    controller = Controller(result_root=tmp_path, maximum_iterations=1, debug=True)
    controller.initialize_path()
    controller.initialize()
    result = controller.step(0)
    assert result.iteration == 0
    assert float(result.objective) == 0.0


def test_controller_initializes_runtime_artifacts(tmp_path):
    controller = Controller(result_root=tmp_path, optimization_name="artifacts", maximum_iterations=1, debug=True)
    controller.initialize_path()
    controller.initialize()

    run_path = next(tmp_path.glob("artifacts_T*"))
    assert {"cache", "logs", "scripts", "checkpoints", "results"}.issubset(
        {item.name for item in run_path.iterdir()}
    )
    assert (run_path / "logs" / "morphopt.log").exists()
    assert (run_path / "logs" / "history.json").exists()
    assert (run_path / "logs" / "history.csv").exists()
    assert controller.get_history().get_records() == ()
    assert controller.get_params()._initialized
    assert controller.get_params().get_geometry()._initialized
    assert controller.get_params().get_materials()._initialized
    assert controller.get_params().get_fea()._initialized
    assert controller._solver._initialized
    assert controller._objective._initialized
    assert controller._sensitivity._initialized
    assert controller._updaters._initialized

    controller._opt_loop(0)
    assert (run_path / "results" / "iteration_000000" / "manifest.json").exists()
    assert not (run_path / "checkpoints" / "iteration_000000" / "history.csv").exists()
    assert (run_path / "logs" / "history.csv").exists()
    assert len(controller.get_history().get_records()) == 1


def test_controller_rebuilds_assembly_after_committed_update(tmp_path):
    part = TrackingPart()
    controller = Controller(
        params_factory=lambda: make_tracking_params(part),
        result_root=tmp_path,
        optimization_name="rebuild",
        maximum_iterations=2,
        debug=True,
    )
    controller.initialize_path()
    controller.initialize()

    controller.step(0)
    first_assembly = controller.get_assembly()
    assert part.build_values == [1.0]
    assert part.build_paths[0].name == "tracked"
    assert part.build_paths[0].parent.name == "iteration_000000"
    assert part.build_paths[0].parent.parent.name == "cache"
    assert part.build_update_calls == [0]
    assert part.update_calls == 2  # sensitivity trial and its reset
    assert float(part.parameters[0]) == 1.0  # trial did not commit

    controller._registry.apply_design_delta({DesignKey("geometry", "tracked"): torch.as_tensor([0.25])})
    assert float(part.parameters[0]) == 1.25

    controller.step(1)
    second_assembly = controller.get_assembly()
    assert second_assembly is not first_assembly
    assert part.build_values == [1.0, 1.25]
    assert part.build_update_calls == [0, 2]
    assert part.update_calls == 4


def test_worker_restart_boundary_always_has_checkpoint(tmp_path):
    controller = Controller(
        result_root=tmp_path,
        optimization_name="boundary",
        maximum_iterations=3,
        checkpoint_interval=3,
        worker_restart_interval=2,
        debug=False,
    )
    controller.initialize_path()
    controller.initialize()
    controller._opt_loop(0)
    run_path = controller._result_path
    assert run_path is not None
    assert (run_path / "checkpoints" / "iteration_000001" / "manifest.json").exists()
