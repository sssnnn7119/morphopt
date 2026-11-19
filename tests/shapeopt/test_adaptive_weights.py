"""One-time calibration, sensitivity scaling, and geometric penalty feedback."""

from pathlib import Path

import pytest
import torch

from morphopt.optcore.protocal import ProtocalSavable
from morphopt.optcore.updaters import BaseUpdater
from morphopt.shapeopt.objectivefuncs.basefuncs import BaseConstraints
from morphopt.shapeopt.strategies import AdaptiveShapeUpdate


class AnalyticUpdater(BaseUpdater):
    update_kind = "geometry"

    def __init__(self, scale=1.0, area=1.0):
        super().__init__()
        self.max_step_iter = 5
        self.scale, self.area = scale, area
        self.z = 0.0
        self.obj_funcs = {"physical": object()}
        self.constraints_funcs = {"limit": BaseConstraints()}

    def closure(self, x, return_list=False):
        physical = -self.scale * x[0]
        # Test coefficient feedback in units of the current transition width.
        barrier = self.constraints_funcs["limit"].barrier_function
        values = 0.8 + (0.2 + (barrier.tolerance or 0.0)) * (self.z + x[:1])
        penalty = self.area * barrier(values, 1.0, 0.8, 3)[1].sum()
        if return_list:
            return [physical], [penalty]
        return physical + self.constraint_weights["limit"] * penalty

    def gradient(self):
        return torch.tensor([-self.scale, 0.0, 0.0], dtype=torch.float64)


@pytest.mark.parametrize("scale", [1e-6, 1.0, 1e6])
@pytest.mark.parametrize("area", [0.1, 1.0, 1000.0])
def test_initial_weight_balances_native_physical_and_penalty_gradients(scale, area):
    updater = AnalyticUpdater(scale, area)
    strategy = AdaptiveShapeUpdate()
    gradient = updater.gradient()
    source = gradient.clone()
    weight = strategy.constraint_weights(updater, gradient)["limit"]
    # At x=1 the cubic penalty derivative is 3*area; safety factor is 2.
    assert weight == pytest.approx(2 * scale / (3 * area))
    assert strategy.state["limit"]["initial_weight"] == weight
    torch.testing.assert_close(gradient, source, rtol=0, atol=0)


def test_later_physical_gradient_changes_scale_weights_without_recalibration(monkeypatch):
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeUpdate()
    initial = strategy.constraint_weights(updater, updater.gradient())["limit"]

    def forbidden(*args, **kwargs):
        raise AssertionError("A calibrated term must not request new derivatives")

    monkeypatch.setattr(torch.func, "grad", forbidden)
    monkeypatch.setattr(torch.func, "jacrev", forbidden)
    updater.z = 1.1  # Inside the violation dead band.
    for scale, weight_factor in ((1e-6, 1e-6), (1e6, 1e6), (0.0, 1e6), (1000.0, 1000.0)):
        updater.scale = scale
        assert strategy.constraint_weights(updater, updater.gradient())["limit"] == pytest.approx(initial * weight_factor)
    assert strategy.state["limit"]["initial_weight"] == initial
    assert strategy.state["limit"]["reference_gradient_norm"] == 1.0


@pytest.mark.parametrize("area", [1e-9, 1.0, 1e9])
def test_local_violation_does_not_change_the_outer_coefficient(area):
    updater = AnalyticUpdater(area=area)
    strategy = AdaptiveShapeUpdate()
    initial = strategy.constraint_weights(updater, updater.gradient())["limit"]
    for z in (3., 1., 20., 0.):
        updater.z = z
        assert strategy.constraint_weights(updater, updater.gradient())["limit"] == pytest.approx(initial)
        assert strategy.state["limit"]["violation"] == pytest.approx(max(z, 0))


def test_extra_resistance_and_gradient_are_local_to_the_violating_sample():
    updater = AnalyticUpdater()
    AdaptiveShapeUpdate().constraint_weights(updater, updater.gradient())
    barrier = updater.constraints_funcs["limit"].barrier_function
    z = torch.tensor([-.5, .5, 1., 1.5], dtype=torch.float64)

    def contributions(x):
        return barrier(0.8 + (0.2 + barrier.tolerance) * x, 1., 0.8, 3)[1]

    barrier.excess_start = 1.2
    for gain in (0., 4.):
        barrier.excess_weight = gain
        values = contributions(z)
        gradient = torch.func.grad(lambda x: contributions(x).sum())(z)
        torch.testing.assert_close(values, z[1:]**3 + gain * (z[1:] - 1.2).relu()**3)
        torch.testing.assert_close(gradient, 3 * z.relu()**2 + 3 * gain * (z - 1.2).relu()**2)


def test_retry_strengthens_only_excess_and_resets_at_the_next_outer_step():
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeUpdate()
    gradient = updater.gradient()
    updater.constraint_weights = strategy.constraint_weights(updater, gradient)
    updater.constraint_weights["limit"] = 0.01
    initial = dict(updater.constraint_weights)
    barrier = updater.constraints_funcs["limit"].barrier_function
    attempts = []

    def solve(origin):
        attempts.append((origin[0].item(), updater.max_step_iter, barrier.excess_weight))
        candidate = origin.clone()
        candidate[0] = 3 if len(attempts) == 1 else 1.1
        return candidate

    updater.solve_subproblem = solve
    accepted = strategy.solve_update(updater, torch.zeros_like(gradient))
    assert accepted[0] == pytest.approx(1.1)
    assert attempts[0] == (0.0, 5, 0.0)
    position, budget, surcharge = attempts[1]
    assert (position, budget) == (3.0, 5)
    unsafe_merit = -3 + 0.01 * 3**3
    extra_cost = surcharge * 0.01 * (3 - barrier.excess_start)**3
    assert extra_cost == pytest.approx(4 * -unsafe_merit)
    assert updater.constraint_weights == initial
    strategy.constraint_weights(updater, gradient)
    assert barrier.excess_weight == 0


def test_surcharges_survive_a_change_in_which_constraint_is_overloaded():
    class TwoLimits(AnalyticUpdater):
        def closure(self, x, return_list=False):
            penalties = []
            for index, term in enumerate(self.constraints_funcs.values()):
                barrier = term.barrier_function
                value = 0.8 + (0.2 + barrier.tolerance) * x[index:index + 1]
                penalties.append(barrier(value, 1.0, 0.8, 3)[1].sum())
            return [-x.sum()], penalties

    updater = TwoLimits()
    updater.constraints_funcs["second"] = BaseConstraints()
    strategy = AdaptiveShapeUpdate(max_solves=3)
    origin = torch.zeros(3, dtype=torch.float64)
    updater.constraint_weights = strategy.constraint_weights(updater, -torch.ones_like(origin))
    barriers = [term.barrier_function for term in updater.constraints_funcs.values()]
    stages = []

    def solve(start):
        stages.append([barrier.excess_weight for barrier in barriers])
        return start.new_tensor([3, 0, 0] if len(stages) == 1 else [0, 3, 0])

    updater.solve_subproblem = solve
    strategy.solve_update(updater, origin)
    assert stages[0] == [0, 0]
    assert stages[1][0] > 0 and stages[1][1] == 0
    assert stages[2][0] == stages[1][0] and stages[2][1] > 0
    assert all(barrier.excess_weight == 0 for barrier in barriers)


@pytest.mark.parametrize(("first", "retry", "expected"), [
    (0.5, 2.1, 2.1),   # Keep the final solution even if the first endpoint was feasible.
    (3.0, 1.1, 1.1),   # The repriced third solve recovers a feasible descent.
    (3.0, 2.0, 2.0),   # Residual excess is carried into the next outer step.
])
def test_retry_from_overloaded_second_endpoint(first, retry, expected):
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeUpdate()
    gradient = updater.gradient()
    updater.constraint_weights = strategy.constraint_weights(updater, gradient)
    updater.constraint_weights["limit"] = 0.01
    origin = torch.zeros_like(gradient)
    endpoints = [first, 2.0, retry]
    starts, budgets, surcharges = [], [], []
    barrier = updater.constraints_funcs["limit"].barrier_function

    def solve(start):
        starts.append(start[0].item())
        budgets.append(updater.max_step_iter)
        surcharges.append(barrier.excess_weight)
        return -endpoints[len(starts) - 1] * gradient

    updater.solve_subproblem = solve
    chosen = strategy.solve_update(updater, origin)
    torch.testing.assert_close(chosen, -expected * gradient, rtol=0, atol=0)
    assert starts == [0.0, *endpoints[:-1]]
    assert budgets == [5, 5, 5]
    assert surcharges[2] > surcharges[1] >= 0
    assert barrier.excess_weight == 0


def test_pending_term_calibrates_on_its_first_nonzero_response():
    updater = AnalyticUpdater()
    updater.z = -3.0
    strategy = AdaptiveShapeUpdate()
    assert strategy.constraint_weights(updater, updater.gradient()) == {"limit": 1.0}
    assert strategy.state == {}
    assert strategy.history_data()["penalties"] == {"limit": {"peak_z": 0.0}}
    updater.z = 0.0
    initial = strategy.constraint_weights(updater, updater.gradient())["limit"]
    assert initial == pytest.approx(2 / 3)
    updater.scale = 10000.0
    assert strategy.constraint_weights(updater, updater.gradient())["limit"] == pytest.approx(initial * updater.scale)
    assert strategy.state["limit"]["initial_weight"] == initial


def test_history_records_violations_even_when_calibration_has_no_physical_gradient():
    updater = AnalyticUpdater(scale=0.0)
    updater.z = 2.0
    strategy = AdaptiveShapeUpdate()
    assert strategy.constraint_weights(updater, updater.gradient()) == {"limit": 1.0}
    assert strategy.state == {}
    assert strategy.history_data()["penalties"]["limit"]["peak_z"] == pytest.approx(2.0)
    updater.constraints_funcs.clear()
    assert strategy.constraint_weights(updater, updater.gradient()) == {}
    assert strategy.history_data()["penalties"] == {}


def test_zero_physical_gradient_does_not_freeze_a_placeholder_as_calibration():
    updater = AnalyticUpdater(scale=0.0)
    strategy = AdaptiveShapeUpdate()
    assert strategy.constraint_weights(updater, updater.gradient()) == {"limit": 1.0}
    assert strategy.state == {}
    updater.scale = 1.0
    assert strategy.constraint_weights(updater, updater.gradient())["limit"] == pytest.approx(2 / 3)


def test_restart_restores_initial_weights_violation_and_next_feedback(tmp_path: Path):
    updater = AnalyticUpdater()
    original = AdaptiveShapeUpdate()
    assert isinstance(original, ProtocalSavable)
    original.constraint_weights(updater, updater.gradient())
    updater.scale = 3.0
    updater.z = 3.0
    original.constraint_weights(updater, updater.gradient())
    original.save(str(tmp_path), 2)
    restored = AdaptiveShapeUpdate()
    restored.load(str(tmp_path), 2)
    assert restored.state == original.state
    assert restored.tolerance == original.tolerance
    updater.scale = 0.0
    updater.z = 1.02
    assert restored.constraint_weights(updater, updater.gradient()) == original.constraint_weights(updater, updater.gradient())
    assert restored.tolerance == original.tolerance


def test_legacy_checkpoint_recalibrates_when_no_reference_norm_was_saved(tmp_path: Path):
    (tmp_path / "adaptive_weights_2.json").write_text(
        '{"tolerance": 0.05, "started": true, "penalties": '
        '{"limit": {"weight": 0.001, "initial_weight": 0.001, "violation": 0.0}}}'
    )
    updater = AnalyticUpdater(scale=10.0)
    strategy = AdaptiveShapeUpdate()
    strategy.load(str(tmp_path), 2)
    assert strategy.constraint_weights(updater, updater.gradient())["limit"] == pytest.approx(20 / 3)
    updater.scale = 100.0
    updater.z = 1.1
    assert strategy.constraint_weights(updater, updater.gradient())["limit"] == pytest.approx(200 / 3)


def test_removed_terms_are_forgotten():
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeUpdate()
    strategy.constraint_weights(updater, updater.gradient())
    updater.constraints_funcs.clear()
    assert strategy.constraint_weights(updater, updater.gradient()) == {}
    assert strategy.state == {}


def test_negative_penalty_is_rejected():
    class SignedTerm(AnalyticUpdater):
        def closure(self, x, return_list=False):
            physical, penalty = super().closure(x, True)
            return physical, [penalty[0] - 100]

    updater = SignedTerm()
    with pytest.raises(ValueError, match="nonnegative"):
        AdaptiveShapeUpdate().constraint_weights(updater, updater.gradient())

@pytest.mark.parametrize(("budget", "limit", "count"), [(0, 3, 0), (1, 1, 1), (1, 2, 2), (7, 4, 4)])
def test_per_solve_step_budget_and_total_solve_limit(budget, limit, count):
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeUpdate(max_solves=limit)
    gradient = updater.gradient()
    updater.constraint_weights = strategy.constraint_weights(updater, gradient)
    updater.max_step_iter = budget
    stages = []

    def solve(origin):
        stages.append(updater.max_step_iter)
        return -3 * gradient

    updater.solve_subproblem = solve
    chosen = strategy.solve_update(updater, torch.zeros_like(gradient))
    assert stages == [budget] * count
    torch.testing.assert_close(chosen, -3 * gradient if budget else torch.zeros_like(gradient))
    assert updater.constraints_funcs["limit"].barrier_function.excess_weight == 0
