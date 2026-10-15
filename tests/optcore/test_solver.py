from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import torch
import torchfea
from torchfea.model.assembly import WorkCondition

import morphopt
from morphopt.optcore.solver import Solver


def test_core_solver_restores_previous_iteration_for_warm_start(monkeypatch) -> None:
    loaded_paths: list[str] = []

    class Result:
        def __init__(self, value: float) -> None:
            self.GC = torch.tensor([value])

    def load(path: str) -> Result:
        loaded_paths.append(path)
        return Result(float(len(loaded_paths)))

    monkeypatch.setattr(torchfea.solver.StaticResult, "load", staticmethod(load))
    monkeypatch.setattr(
        morphopt,
        "controller",
        SimpleNamespace(
            history=SimpleNamespace(iteration=3),
            path_result="/tmp/morphopt-run",
        ),
    )
    solver = Solver(
        params=SimpleNamespace(
            geometry=SimpleNamespace(interfaces={"fixed": morphopt.BasePart()}),
            feamodel=SimpleNamespace(num_load_steps=2),
        ),
    )

    guess = solver._previous_solution()

    assert [step.tolist() for step in guess] == [[1.0], [2.0]]
    assert loaded_paths == [
        "/tmp/morphopt-run/log/femodel&results/result_0_iter_3.npz",
        "/tmp/morphopt-run/log/femodel&results/result_1_iter_3.npz",
    ]


@pytest.mark.parametrize("iteration,variable", [(0, False), (3, True)])
def test_previous_solution_is_empty_for_first_iteration_or_variable_geometry(
    monkeypatch, iteration, variable
) -> None:
    def unexpected_load(path):
        pytest.fail(f"Must not load a previous result: {path}")

    monkeypatch.setattr(torchfea.solver.StaticResult, "load", staticmethod(unexpected_load))
    monkeypatch.setattr(morphopt, "controller", SimpleNamespace(
        history=SimpleNamespace(iteration=iteration), path_result="/tmp/morphopt-run",
    ))
    part = morphopt.BoundaryPart() if variable else morphopt.BasePart()
    solver = Solver(params=SimpleNamespace(
        geometry=SimpleNamespace(interfaces={"fixed": morphopt.BasePart(), "part": part}),
        feamodel=SimpleNamespace(num_load_steps=2),
    ))

    assert solver._previous_solution() is None


@pytest.mark.parametrize("has_saved_result", [True, False])
def test_previous_solution_loads_saved_result_and_leaves_missing_step_empty(
    monkeypatch, tmp_path, has_saved_result
) -> None:
    directory = tmp_path / "log" / "femodel&results"
    directory.mkdir(parents=True)
    if has_saved_result:
        result = torchfea.solver.StaticResult(
            GC=torch.tensor([1.0, 2.0]), work_conditions=WorkCondition(), model_hash="fixed-mesh",
        )
        result.save(str(directory / "result_0_iter_3.npz"))
    monkeypatch.setattr(morphopt, "controller", SimpleNamespace(
        history=SimpleNamespace(iteration=3), path_result=str(tmp_path),
    ))
    solver = Solver(params=SimpleNamespace(
        geometry=SimpleNamespace(interfaces={"fixed": morphopt.BasePart()}),
        feamodel=SimpleNamespace(num_load_steps=2),
    ))

    guesses = solver._previous_solution()

    if has_saved_result:
        np.testing.assert_array_equal(guesses[0], [1.0, 2.0])
        assert guesses[1] is None
    else:
        assert guesses is None
    # Geometry can become variable after an earlier solve; then even existing
    # saved results are ineligible as automatic initial guesses.
    solver.params.geometry.interfaces["fixed"].is_variable = True
    assert solver._previous_solution() is None


@pytest.mark.parametrize("variable", [False, True])
def test_part_interface_transfers_variable_marker_to_assembly(variable) -> None:
    class Part(morphopt.BasePart):
        def build_part(self, path_result=None, pools=None):
            return torchfea.Part(torch.zeros((1, 3)))

    interface = Part(part_name="part")
    interface.is_variable = variable
    interface.initialize()
    assembly = torchfea.Assembly()

    interface.add_to_assembly(assembly)

    assert assembly.get_part("part").is_variable is variable


@pytest.mark.parametrize("debug_mode", [False, True])
def test_solve_passes_previous_result_or_empty_guess_to_each_task(monkeypatch, debug_mode) -> None:
    guesses = [np.array([7.0]), None, np.array([9.0]), None]
    submitted = []
    debug_calls = []

    class Model:
        def change_device(self, device):
            pass

        def _change_device_recursive(self, result, device):
            pass

    class Pool:
        def apply_async(self, function, kwds):
            submitted.append(kwds)
            results = [
                SimpleNamespace(GC=torch.tensor([float(step)]), converged=True)
                for step in kwds["task_index"]
            ]
            return SimpleNamespace(get=lambda: results)

    monkeypatch.setattr(morphopt, "controller", SimpleNamespace(
        objfun=SimpleNamespace(fe=Model()), _debug_mode=debug_mode, pools=Pool(),
        path_result="/tmp/morphopt-run",
    ))
    solver = Solver(params=SimpleNamespace(feamodel=object()), task_index_list=[[2, 0], [3, 1]])
    monkeypatch.setattr(solver, "_previous_solution", lambda: guesses)
    monkeypatch.setattr(solver, "_solve_FEA", lambda **kwargs: debug_calls.append(kwargs))

    results = solver.solve()

    np.testing.assert_array_equal(submitted[0]["U_guess"], [[9.0], [7.0]])
    assert submitted[1]["U_guess"] == [None, None]
    assert [result.GC.item() for result in results] == [0, 1, 2, 3]
    if debug_mode:
        np.testing.assert_array_equal(debug_calls[0]["U_guess"], [[9.0], [7.0]])

    submitted.clear()
    solver.solve(U_guess=np.array([[3.0], [4.0], [5.0], [6.0]]))
    np.testing.assert_array_equal(submitted[0]["U_guess"], [[5.0], [3.0]])
    np.testing.assert_array_equal(submitted[1]["U_guess"], [[6.0], [4.0]])


@pytest.mark.parametrize("guesses,expected", [
    (None, [100.0, 103.0, 104.0, 106.0]),
    ([None, None, None, None], [100.0, 103.0, 104.0, 106.0]),
    ([10.0, 20.0, 30.0, 40.0], [10.0, 20.0, 30.0, 40.0]),
    ([None, 20.0, None, 40.0], [100.0, 20.0, 21.0, 40.0]),
])
def test_worker_selects_each_guess_or_previous_load_step(monkeypatch, guesses, expected) -> None:
    monkeypatch.setattr(torchfea, "enable_logging", lambda **kwargs: None)
    monkeypatch.setattr(torch, "set_default_device", lambda device: None)
    monkeypatch.setattr(torch, "set_default_dtype", lambda dtype: None)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    used_guesses = []
    processed_steps = []

    class Model:
        assembly = SimpleNamespace(_GC=torch.tensor([100.0], dtype=torch.float64))

        def change_device(self, device):
            pass

        def solve(self, GC0, if_initialize):
            used_guesses.append(GC0.detach().clone())
            assert not if_initialize
            return SimpleNamespace(GC=GC0 + self.step + 1)

        def _change_device_recursive(self, result, device):
            pass

    def process_fea(fe, step_index):
        processed_steps.append(step_index)
        fe.step = step_index

    initial_guesses = None if guesses is None else [
        None if value is None else np.array([value], dtype=np.float32)
        for value in guesses
    ]
    results = Solver._solve_FEA(
        fe=Model(), feamodel=SimpleNamespace(process_fea=process_fea),
        task_index=[2, 0, 1, 3], available_gpus=[],
        U_guess=initial_guesses, path_result="/tmp/morphopt-run",
    )

    assert processed_steps == [2, 0, 1, 3]
    assert [guess.item() for guess in used_guesses] == expected
    assert all(guess.dtype == torch.float64 for guess in used_guesses)
    assert [result.GC.item() for result in results] == [
        guess + step + 1 for guess, step in zip(expected, processed_steps)
    ]
