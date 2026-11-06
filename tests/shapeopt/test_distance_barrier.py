"""Distance relaxation tightens outside a fixed quadratic subproblem."""

from pathlib import Path

import pytest
import torch

from morphopt.optcore.updaters import BaseUpdater
from morphopt.shapeopt.barriers import PolynomialBarrier
from morphopt.shapeopt.objectivefuncs.distancesurface import Distance
from morphopt.shapeopt.strategies import AdaptiveShapeWeights


def test_default_barrier_preserves_the_original_polynomial():
    barrier = PolynomialBarrier()
    f = torch.tensor([0.7, 0.8, 0.9, 1.0, 1.2], dtype=torch.float64)
    index, values = barrier(f, 1.0, 0.8, 5)
    assert index.tolist() == [2, 3, 4]
    torch.testing.assert_close(values, ((f[index] - 0.8) / 0.2) ** 5)


def test_distance_relaxation_is_quadratic_with_constant_active_curvature():
    barrier = PolynomialBarrier()
    barrier.tolerance = 0.2
    # Required distance is 1.0; initially 0.8 is acceptable. The margin is 0.05.
    f = torch.tensor([0.11, 0.17, 0.21, 0.51], dtype=torch.float64)
    value = lambda x: barrier(x, 0.01, 0.8, 5, transition_scale=1.0)[1].sum()
    hessian = torch.func.hessian(value)(f).diagonal()
    assert hessian[0] == 0
    torch.testing.assert_close(hessian[1:], torch.full_like(hessian[1:], 800.0))
    assert torch.autograd.gradcheck(value, (f.requires_grad_(),))
    assert torch.autograd.gradgradcheck(value, (f,))
    # A non-distance penalty still uses its original exponent and threshold.
    index, values = barrier(torch.tensor([1.1]), 1.0, 0.8, 5)
    torch.testing.assert_close(values, torch.tensor([1.5**5]))


class DistanceUpdater(BaseUpdater):
    update_kind = "geometry"

    def __init__(self, required: float = 1.0) -> None:
        super().__init__()
        self.obj_funcs = {"physical": object()}
        self.constraints_funcs = {"distance": Distance([[0.0, required], [required, 0.0]])}
        self.required = required
        self.r = [torch.zeros(1, 3, dtype=torch.float64), torch.tensor([[0.9 * required, 0, 0]], dtype=torch.float64)]
        self.rdu = [
            torch.tensor([[[0., 0.], [1., 0.], [0., 1.]]], dtype=torch.float64),
            torch.tensor([[[0., 0.], [1., 0.], [0., -1.]]], dtype=torch.float64),
        ]
        self.constraints_funcs["distance"].initialize(
            r0=self.r, rdu0=self.rdu, rdu20=[torch.zeros(1, 3, 2, 2)] * 2,
            weights=[torch.ones(1, dtype=torch.float64)] * 2, surfaces=[],
        )

    def closure(self, x: torch.Tensor, return_list: bool = False):
        physical = x[0]
        penalty = self.constraints_funcs["distance"]([self.r[0], self.r[1] + self.required * x], self.rdu)
        if return_list:
            return [physical], [penalty]
        return physical + self.constraint_weights["distance"] * penalty


def test_early_relaxation_releases_distance_and_late_schedule_restores_it():
    updater = DistanceUpdater()
    strategy = AdaptiveShapeWeights(tightening_steps=2)
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    origin = torch.zeros_like(gradient)
    tolerances, penalties = [], []
    for _ in range(4):
        updater.constraint_weights = strategy(updater, gradient)
        tolerances.append(strategy.tolerance)
        penalties.append(updater.closure(origin, True)[1][0].item())
        snapshot = {key: dict(value) for key, value in strategy.state.items()}
        weights = dict(updater.constraint_weights)
        # Inner objective/gradient evaluations must not advance or change policy.
        for trial in (origin, gradient, -gradient):
            updater.closure(trial)
            torch.func.grad(updater.closure)(trial)
        assert strategy.state == snapshot
        assert updater.constraint_weights == weights
    assert tolerances == pytest.approx([0.2, 0.1, 0.0, 0.0])
    assert penalties[0] == 0
    assert penalties[0] < penalties[1] < penalties[2]
    assert penalties[2] == penalties[3]
    torch.testing.assert_close(gradient, torch.tensor([1.0, 0, 0], dtype=torch.float64))


def test_relative_distance_penalty_does_not_depend_on_length_units():
    results = []
    for required in (1.0, 0.001):
        updater = DistanceUpdater(required)
        barrier = updater.constraints_funcs["distance"].barrier_function
        barrier.tolerance = 0.0
        origin = torch.zeros(3, dtype=torch.float64)
        penalty = lambda x: updater.closure(x, True)[1][0]
        results.append((penalty(origin), torch.func.grad(penalty)(origin)))
    for original, converted in zip(*results):
        torch.testing.assert_close(original, converted, rtol=1e-6, atol=1e-6)


def test_zero_relaxations_keep_the_nominal_distance_from_the_first_step():
    updater = DistanceUpdater()
    strategy = AdaptiveShapeWeights(initial_tolerance=0.0, final_tolerance=0.0)
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    penalties = []
    for _ in range(3):
        strategy(updater, gradient)
        assert strategy.tolerance == 0
        penalties.append(updater.closure(torch.zeros_like(gradient), True)[1][0].item())
    assert penalties[0] > 0
    assert penalties == pytest.approx([penalties[0]] * 3)


def test_restart_restores_outer_progress_and_calibration(tmp_path: Path):
    updater = DistanceUpdater()
    strategy = AdaptiveShapeWeights(tightening_steps=3)
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    strategy(updater, gradient)
    strategy(updater, gradient)
    strategy.save(str(tmp_path), 2)
    restored = AdaptiveShapeWeights(tightening_steps=3)
    restored.load(str(tmp_path), 2)
    assert restored.completed_steps == strategy.completed_steps
    assert restored.state == strategy.state
    assert restored(DistanceUpdater(), gradient) == strategy(updater, gradient)
    assert restored.tolerance == strategy.tolerance


@pytest.mark.parametrize("parameters", [
    {"tightening_steps": 0}, {"tightening_steps": 2.5}, {"tightening_steps": True},
    {"initial_tolerance": 1.0}, {"initial_tolerance": float("inf")},
    {"final_tolerance": -0.1}, {"final_tolerance": 0.3},
    {"final_tolerance": float("nan")},
])
def test_invalid_schedule_parameters_are_rejected(parameters):
    with pytest.raises(ValueError):
        AdaptiveShapeWeights(**parameters)
