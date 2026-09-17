"""test device boundaries tests."""

from morphopt.optcore.controller import Controller, _AssemblyController
from morphopt.optcore.solver import Solver, StaticResult
from morphopt.optcore.updaters import Updaters


def test_controller_solver_and_updater_devices_are_independent(tmp_path):
    controller = Controller(
        result_root=tmp_path,
        maximum_iterations=1,
        debug=True,
        device="meta:0",
        solver_device_names=("cuda:0",),
        updater_device="cuda:1",
    )
    controller.initialize_path()
    controller.initialize()

    assert controller.device == "meta:0"
    assert controller.solver_device_names == ("cuda:0",)
    assert controller.updater_device == "cuda:1"
    assert controller._solver.device_names == ("cuda:0",)
    assert controller._updaters.device == "cuda:1"

    controller.change_device("cpu")
    assert controller.device == "cpu"
    assert controller._solver.device_names == ("cuda:0",)

    controller.change_solver_devices(("cpu",))
    assert controller.solver_device_names == ("cpu",)
    assert controller._solver.device_names == ("cpu",)


def test_shared_placeholder_controller_returns_all_cases():
    results = _AssemblyController(object(), 2).solve()
    assert len(results) == 2
    assert all(isinstance(result, StaticResult) for result in results)
