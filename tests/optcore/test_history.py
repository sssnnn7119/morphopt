"""Generic iteration records, nested values and continuation."""

import csv
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from morphopt.optcore.controller import Controller
from morphopt.optcore.history import History
from morphopt.optcore.modelparams import Params
from morphopt.optcore.objfunc import ObjectiveFunction
from morphopt.optcore.protocal import ProtocalHistory
from morphopt.optcore.solver import Solver
from morphopt.optcore.updaters import Updaters
from morphopt.shapeopt.strategies import _ShapeTrial
from morphopt.shapeopt.update_boundary_part import UpdaterBoundaryPart
from morphopt.simp.update_simpmaterial import UpdaterSIMPMaterial


def controller_for_history(tmp_path, metrics):
    controller = Controller(path_result_folder=str(tmp_path))
    controller.objfun = ObjectiveFunction()
    controller.objfun.get_metrics = lambda: metrics
    controller.params = Params(
        geometry=SimpleNamespace(), feamodel=SimpleNamespace(), materials=SimpleNamespace(),
    )
    controller.solver = Solver(params=controller.params)
    controller.updater = Updaters()
    return controller


@pytest.mark.parametrize("metrics,names", [
    ([1.0, torch.tensor(2.0, requires_grad=True)], ["0", "1"]),
    ({"tip_ry": torch.tensor([1.0]), "伸长量": 2.0}, ["tip_ry", "伸长量"]),
])
def test_controller_records_one_complete_iteration(tmp_path, metrics, names):
    controller = controller_for_history(tmp_path, metrics)
    controller.objfun.value = torch.tensor([3.0])
    controller.record_history(0., 1., 2., 3., 4.)
    record = controller.history.records[0]
    assert controller.history.iteration == 1
    assert record["iteration"] == 1 and record["objective"] == 3.0
    assert record["metrics"] == dict(zip(names, [1.0, 2.0]))
    assert list(record["metrics"]) == names
    assert record["time"] == {"init": 1., "fea": 1., "sens": 1., "update": 1.}
    assert record["num_elements"] == record["num_nodes"] == 0
    assert record["optimizers"] == {}


def test_optimizer_snapshots_are_named_copied_and_saved_per_iteration(tmp_path):
    controller = controller_for_history(tmp_path, {})
    shape = UpdaterBoundaryPart(max_step_iter=25, max_step_length=0.2)
    material = UpdaterSIMPMaterial(max_step_iter=15, max_step_length=0.1)
    controller.updater = Updaters(updaters={"body": shape, "density": material})
    shape.constraint_weights = {"Fairness_0": 2e-5, "Distance_0": 0.5}
    shape.iteration_total = 12
    shape.solve_count = 2
    strategy = shape.update_strategy
    strategy.tolerance = 0.04
    strategy.state = {
        "Fairness_0": {"weight": 2e-5, "initial_weight": 1e-5, "violation": 0.3},
    }
    strategy._origin_trial = _ShapeTrial(0.0, {}, {"Fairness_0": 0.3, "Distance_0": 0.0})
    material.constraint_weights = {"VolFrac_0": 3.0}
    controller.objfun.value = torch.tensor(4.0)
    controller.record_history(0., 1., 2., 3., 4.)
    first = controller.history.records[0]["optimizers"]
    assert list(first) == ["body", "density"]
    assert first["body"] == {
        "iterations": 12,
        "solves": 2,
        "constraint_weights": {"Fairness_0": 2e-5, "Distance_0": 0.5},
        "update_strategy_state": {
            "tolerance": 0.04,
            "penalties": {
                "Fairness_0": {"peak_z": 0.3},
                "Distance_0": {"peak_z": 0.0},
            },
        },
    }
    assert first["density"]["constraint_weights"] == {"VolFrac_0": 3.0}
    assert first["density"]["update_strategy_state"] == {}
    assert set(first["density"]) == {"iterations", "solves", "constraint_weights", "update_strategy_state"}
    shape.constraint_weights["Fairness_0"] = 1e-5
    strategy.state["Fairness_0"]["violation"] = 0.1
    strategy._origin_trial.violations["Fairness_0"] = 0.1
    strategy.tolerance = 0.03
    controller.objfun.value = torch.tensor(3.0)
    controller.record_history(0., 1., 2., 3., 4.)
    assert first["body"]["constraint_weights"]["Fairness_0"] == 2e-5
    assert first["body"]["update_strategy_state"]["penalties"]["Fairness_0"]["peak_z"] == 0.3
    controller.history.save(str(tmp_path))
    restored = History()
    restored.load(str(tmp_path))
    assert restored.records == controller.history.records
    assert restored.records[1]["optimizers"]["body"]["update_strategy_state"]["tolerance"] == 0.03


def test_component_history_extensions_need_no_controller_or_schema_changes(tmp_path):
    class Objective(ObjectiveFunction):
        def history_data(self):
            return {**super().history_data(), "response": {"angle": torch.tensor(0.4)}}

    class Parameters(Params):
        def history_data(self):
            return {**super().history_data(), "volume": 12.0}

    class Solve(Solver):
        def history_data(self):
            return {"solver": {"residual": 1e-8}}

    controller = controller_for_history(tmp_path, {})
    controller.objfun = Objective()
    controller.objfun.value = torch.tensor(3.0)
    controller.params = Parameters(
        geometry=SimpleNamespace(), feamodel=SimpleNamespace(), materials=SimpleNamespace(),
    )
    controller.solver = Solve(params=controller.params)
    assert ProtocalHistory().history_data() == {}
    for provider in (controller.objfun, controller.params, controller.solver, controller.updater,
                     UpdaterBoundaryPart(), UpdaterBoundaryPart().update_strategy):
        assert isinstance(provider, ProtocalHistory)
    controller.record_history(0., 1., 2., 3., 4.)
    record = controller.history.records[0]
    assert record["response"]["angle"] == pytest.approx(0.4)
    assert record["volume"] == 12.0
    assert record["solver"] == {"residual": 1e-8}
    controller.history.save(str(tmp_path))
    restored = History()
    restored.load(str(tmp_path))
    assert restored.records == controller.history.records


def test_params_records_all_initialized_instances_and_element_families(tmp_path):
    assembly = SimpleNamespace(_instances={})
    instances = {
        "part1-1": SimpleNamespace(nodes=np.zeros((8, 3)), elems={
            "C3D4": SimpleNamespace(_elems=np.zeros((3, 4))),
            "C3D6": SimpleNamespace(_elems=np.zeros((2, 6))),
        }),
        "part2-1": SimpleNamespace(nodes=np.zeros((12, 3)), elems={
            "C3D10": SimpleNamespace(_elems=np.zeros((4, 10))),
        }),
    }
    fe = SimpleNamespace(assembly=assembly)
    fe.initialize = lambda: assembly._instances.update(instances)
    params = Params(
        geometry=SimpleNamespace(generate=lambda **kwargs: assembly),
        feamodel=SimpleNamespace(create_fea=lambda assembly: fe),
        materials=SimpleNamespace(set_materials=lambda model: None),
    )
    assert params.history_data() == {"num_elements": 0, "num_nodes": 0}
    assert params.create_feamodel(path_result=str(tmp_path)) is fe
    snapshot = params.history_data()
    assert snapshot == {"num_elements": 9, "num_nodes": 20}
    # Later remeshing replaces the statistics while old snapshots stay intact.
    assembly._instances.clear()
    instances.pop("part2-1")
    params.create_feamodel(path_result=str(tmp_path))
    assert params.history_data() == {"num_elements": 5, "num_nodes": 8}
    assert snapshot == {"num_elements": 9, "num_nodes": 20}


def test_nested_records_and_arbitrary_fields_round_trip_and_resume(tmp_path):
    history = History()
    record = {
        "iteration": "a user field, not a reserved counter",
        "phase_0": 1.234567890123456,
        "T0": [1., 2.],
        "U0-0": np.arange(24).reshape(2, 3, 4),
        "metrics": {"位移,末端": torch.tensor(2.), "0": 1.},
        "custom": {"converged": True, "message": "stable", "value": None},
    }
    history.append(**record)
    history.append(diagnostics={"residual": 1e-14})
    history.save(str(tmp_path))
    with (tmp_path / "history_record.csv").open(encoding="utf-8", newline="") as source:
        assert next(csv.reader(source)) == list(history.records[0]) + ["diagnostics"]
    restored = History()
    restored.load(str(tmp_path), iteration=1)
    assert restored.records == history.records[:1]
    assert restored.iteration == 1
    restored.append(**history.records[1])
    assert restored.records == history.records
    restored.save(str(tmp_path))
    again = History()
    again.load(str(tmp_path))
    assert again.records == history.records


def test_new_fields_and_metrics_require_no_schema_changes(tmp_path):
    history = History()
    history.append(metrics={"a": 1.})
    history.append(metrics={"b": 2.}, solver_status="converged")
    history.append(diagnostics={"temperature": 25.}, coefficients=[1., 2., 3.])
    history.save(str(tmp_path))
    restored = History()
    restored.load(str(tmp_path))
    assert restored.records == history.records
    assert "solver_status" not in restored.records[0]
    assert restored.records[1]["metrics"] == {"b": 2.}


def test_appended_arrays_are_detached_copies():
    history = History()
    tensor = torch.tensor([1., 2.], requires_grad=True)
    array = np.array([3., 4.])
    history.append(custom={"tensor": tensor, "array": array, "scalar": np.float64(5.)})
    with torch.no_grad():
        tensor.add_(10.)
    array[:] = 20.
    assert history.records == [{"custom": {"tensor": [1., 2.], "array": [3., 4.], "scalar": 5.}}]


def test_empty_history_and_missing_file(tmp_path):
    history = History()
    history.load(str(tmp_path))
    assert history.iteration == 0
    history.save(str(tmp_path))
    history.load(str(tmp_path))
    assert history.records == []
    with pytest.raises(ValueError, match="at least one field"):
        history.append()
    history.append(custom=1.)
    history.initialize()
    assert history.iteration == 0
