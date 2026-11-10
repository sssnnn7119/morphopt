"""Generic iteration records, nested values and continuation."""

import csv
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from morphopt.optcore.controller import Controller
from morphopt.optcore.history import History


@pytest.mark.parametrize("metrics,names", [
    ([1.0, torch.tensor(2.0, requires_grad=True)], ["0", "1"]),
    ({"tip_ry": torch.tensor([1.0]), "伸长量": 2.0}, ["tip_ry", "伸长量"]),
])
def test_controller_records_one_complete_iteration(tmp_path, metrics, names):
    controller = Controller(path_result_folder=str(tmp_path))
    controller.objfun = SimpleNamespace(
        get_metrics=lambda: metrics,
        fe=SimpleNamespace(assembly=SimpleNamespace(_instances={})),
    )
    controller.record_history(torch.tensor([3.0]), 0., 1., 2., 3., 4.)
    record = controller.history.records[0]
    assert controller.history.iteration == 1
    assert record["iteration"] == 1 and record["objective"] == 3.0
    assert record["metrics"] == dict(zip(names, [1.0, 2.0]))
    assert list(record["metrics"]) == names
    assert record["time"] == {"init": 1., "fea": 1., "sens": 1., "update": 1.}
    assert record["num_elements"] == record["num_nodes"] == 0


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
