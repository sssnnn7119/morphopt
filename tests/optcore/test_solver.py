from __future__ import annotations

from types import SimpleNamespace

import torch
import torchfea

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
        params=SimpleNamespace(feamodel=SimpleNamespace(num_load_steps=2)),
    )

    guess = solver._previous_solution()

    assert guess.tolist() == [[1.0], [2.0]]
    assert loaded_paths == [
        "/tmp/morphopt-run/log/femodel&results/result_0_iter_3.npz",
        "/tmp/morphopt-run/log/femodel&results/result_1_iter_3.npz",
    ]
