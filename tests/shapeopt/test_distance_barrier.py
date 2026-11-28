"""Distance schedules move thresholds without overriding penalty exponents."""

from pathlib import Path

import pytest
import torch

from morphopt.optcore.updaters import BaseUpdater
from morphopt.shapeopt.barriers import PolynomialBarrier
from morphopt.shapeopt.objectivefuncs.distancesurface import Distance
from morphopt.shapeopt.strategies import AdaptiveShapeUpdate


def test_default_barrier_preserves_the_original_polynomial():
    barrier = PolynomialBarrier()
    f = torch.tensor([0.7, 0.8, 0.9, 1.0, 1.2], dtype=torch.float64)
    index, values = barrier(f, 1.0, 0.8, 5)
    assert index.tolist() == [2, 3, 4]
    torch.testing.assert_close(values, ((f[index] - 0.8) / 0.2) ** 5)


@pytest.mark.parametrize("relaxed", [False, True])
def test_cubic_penalty_has_zero_value_gradient_and_curvature_at_activation(relaxed):
    barrier = PolynomialBarrier()
    barrier.tolerance = 0.05 if relaxed else None
    activation = 1.0 if relaxed else 0.8

    def penalty(x):
        return barrier(
            x, 1.0, 0.8, 3, transition_scale=1.0 if relaxed else None,
        )[1].sum()

    point = torch.tensor([activation], dtype=torch.float64)
    assert penalty(point) == 0
    torch.testing.assert_close(torch.func.grad(penalty)(point), torch.zeros_like(point))
    torch.testing.assert_close(torch.func.hessian(penalty)(point), point.new_zeros((1, 1)))
    assert penalty(point - 1e-4) == 0
    assert penalty(point + 1e-4) > 0
    assert torch.func.grad(penalty)(point + 1e-4)[0] > 0


@pytest.mark.parametrize("power", [3, 5, 7])
def test_distance_relaxation_preserves_the_requested_power_and_derivatives(power):
    barrier = PolynomialBarrier()
    barrier.tolerance = 0.2
    # Required distance is 1.0; the activation deficit is 0.15 and the early width is 0.25.
    f = torch.tensor([0.11, 0.17, 0.21, 0.51], dtype=torch.float64)
    pointwise = lambda x: barrier(x, 0.01, 0.8, power, transition_scale=1.0)[1]
    value = lambda x: pointwise(x).sum()
    z = (f - 0.01 - 0.15) / 0.25
    torch.testing.assert_close(value(f), z[z > 0].pow(power).sum())
    hessian = torch.func.hessian(value)(f).diagonal()
    assert hessian[0] == 0
    torch.testing.assert_close(hessian[1:], power * (power - 1) * z[1:].pow(power - 2) / 0.25**2)
    # Check pointwise values so finite differences do not subtract a tiny
    # transition contribution from a much larger, unrelated violation.
    assert torch.autograd.gradcheck(pointwise, (f.requires_grad_(),))
    assert torch.autograd.gradgradcheck(pointwise, (f,))
    # An upper-bound term widens from the same activation point.
    index, values = barrier(torch.tensor([1.1]), 1.0, 0.8, 5)
    torch.testing.assert_close(values, torch.tensor([(0.3 / 0.4)**5]))


def test_higher_power_keeps_safe_points_zero_and_penalizes_large_violations_more():
    barrier = PolynomialBarrier()
    f = torch.tensor([0.7, 0.8, 0.9, 1.0, 1.2], dtype=torch.float64)
    low = lambda x: barrier(x, 1.0, 0.8, 2)[1].sum()
    high = lambda x: barrier(x, 1.0, 0.8, 7)[1].sum()
    indices, values = barrier(f, 1.0, 0.8, 7)
    assert indices.tolist() == [2, 3, 4]
    # The transition stays soft; beyond the nominal limit the power dominates.
    assert values[0] < 0.5**2
    assert values[-1] > 2.0**2
    assert torch.func.grad(high)(f)[-1] > torch.func.grad(low)(f)[-1]
    torch.testing.assert_close(torch.func.grad(high)(f)[:2], torch.zeros_like(f[:2]))


class DistanceUpdater(BaseUpdater):
    update_kind = "geometry"

    def __init__(self, required: float = 1.0) -> None:
        super().__init__()
        self.objective_value = 1.0
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


def test_distance_rescreens_trial_normals_and_preserves_angular_gradient(monkeypatch):
    from morphopt.constants import CONSTANT

    monkeypatch.setattr(CONSTANT.KERNEL.SHAPE_CONSTRAINTS, "DISTANCE_PAIR_BATCH_SIZE", 1)
    left = torch.tensor([[0., 0., 0.], [0., 8., 0.]], dtype=torch.float64)
    right = left + left.new_tensor([0.9, 0., 0.])
    tangent = left.new_tensor([[0., 0.], [1., 0.], [0., 1.]]).expand(2, -1, -1)
    term = Distance([[0., 1.], [1., 0.]])
    term.initialize(r0=[left, right], rdu0=[tangent, tangent], rdu20=[],
                    weights=[left.new_ones(2)] * 2, surfaces=[])
    term.barrier_function.tolerance = 0.05
    assert term([left, right], [tangent, tangent]) == 0

    # Tilt only the second patch into the smooth angular transition.
    trial = tangent.clone()
    trial[1, :, 1] = left.new_tensor([1., 0., -0.4])

    def evaluate(points, tangents):
        return term([left, points], [tangent, tangents])

    grad_r, grad_du = torch.func.grad(evaluate, argnums=(0, 1))(right, trial)
    assert grad_r[0].count_nonzero() == grad_du[0].count_nonzero() == 0
    assert grad_r[1].norm() > 0 and grad_du[1].norm() > 0
    assert torch.autograd.gradcheck(evaluate, (right.requires_grad_(), trial.requires_grad_()))


def test_thin_wall_retry_only_changes_forces_at_the_thin_pair():
    updater = DistanceUpdater()
    term = updater.constraints_funcs["distance"]
    # Two separated wall patches. One violates the relaxed limit, while
    # the other lies in the soft transition and has a nonzero base force.
    left = torch.tensor([[0., 0., 0.], [0., 10., 0.]], dtype=torch.float64)
    right = left + left.new_tensor([[.8, 0., 0.], [.95, 0., 0.]])
    tangents = [du.expand(2, -1, -1) for du in updater.rdu]
    term.initialize(r0=[left, right], rdu0=tangents, rdu20=[], weights=[left.new_ones(2)] * 2, surfaces=[])
    term.barrier_function.tolerance = .05
    force = torch.func.grad(lambda points: term([left, points], tangents))
    term.barrier_function.excess_weight = 100
    before = force(right)
    term.barrier_function.excess_weight *= 4
    after = force(right)
    assert after[0, 0] < before[0, 0] < 0
    assert before[1, 0] < 0
    torch.testing.assert_close(after[1], before[1], rtol=0, atol=0)


@pytest.mark.parametrize("initial_tolerance", [0.05, 0.1])
def test_weight_strategy_moves_distance_threshold_without_changing_cubic_power(initial_tolerance):
    updater = DistanceUpdater()
    strategy = AdaptiveShapeUpdate(initial_tolerance=initial_tolerance)
    origin = torch.zeros(3, dtype=torch.float64)
    for _ in range(3):
        updater.constraint_weights = strategy.constraint_weights(updater, torch.tensor([1., 0, 0], dtype=torch.float64))
        z = (0.15 - strategy.tolerance) / (0.05 + strategy.tolerance)
        actual = updater.closure(origin, True)[1][0]
        assert actual.item() == pytest.approx(z**3)


def test_early_relaxation_releases_distance_and_late_schedule_restores_it():
    updater = DistanceUpdater()
    strategy = AdaptiveShapeUpdate(initial_tolerance=0.2, tightening_increment=0.1)
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    origin = torch.zeros_like(gradient)
    tolerances, penalties = [], []
    for _ in range(4):
        updater.constraint_weights = strategy.constraint_weights(updater, gradient)
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


@pytest.mark.parametrize("distance", [2.3, 2.375, 2.45])
def test_default_early_distance_penalty_activates_before_large_violations(distance):
    updater = DistanceUpdater(required=2.5)
    updater.r[1][0, 0] = distance
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    origin = torch.zeros_like(gradient)
    policy = AdaptiveShapeUpdate()
    policy.constraint_weights(updater, gradient)
    assert policy.initial_tolerance == pytest.approx(0.05)
    penalty = lambda x: updater.closure(x, True)[1][0]
    assert penalty(origin) > 0
    # Moving the second surface away reduces the penalty from the first step.
    assert torch.func.grad(penalty)(origin)[0] < 0
    updater.constraints_funcs["distance"].barrier_function.tolerance = 0.2
    assert penalty(origin) == 0
    torch.testing.assert_close(gradient, torch.tensor([1.0, 0, 0], dtype=torch.float64))


@pytest.mark.parametrize("distance", [2.5, 2.6])
def test_default_early_distance_penalty_is_zero_at_safe_distances(distance):
    updater = DistanceUpdater(required=2.5)
    updater.r[1][0, 0] = distance
    AdaptiveShapeUpdate().constraint_weights(updater, torch.tensor([1.0, 0, 0], dtype=torch.float64))
    assert updater.closure(torch.zeros(3, dtype=torch.float64), True)[1][0] == 0


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
    strategy = AdaptiveShapeUpdate(initial_tolerance=0.0, final_tolerance=0.0)
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    penalties = []
    for _ in range(3):
        strategy.constraint_weights(updater, gradient)
        assert strategy.tolerance == 0
        penalties.append(updater.closure(torch.zeros_like(gradient), True)[1][0].item())
    assert penalties[0] > 0
    assert penalties == pytest.approx([penalties[0]] * 3)


def test_restart_restores_outer_progress_and_calibration(tmp_path: Path):
    updater = DistanceUpdater()
    strategy = AdaptiveShapeUpdate()
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    strategy.constraint_weights(updater, gradient)
    strategy.constraint_weights(updater, gradient)
    strategy.save(str(tmp_path), 2)
    restored = AdaptiveShapeUpdate()
    restored.load(str(tmp_path), 2)
    assert restored._started == strategy._started
    assert restored.state == strategy.state
    assert restored.constraint_weights(DistanceUpdater(), gradient) == strategy.constraint_weights(updater, gradient)
    assert restored.tolerance == strategy.tolerance


@pytest.mark.parametrize("objective", [None, float("nan"), float("inf"), -1e9, 1e9])
def test_threshold_updates_depend_on_geometry_not_physical_objective(objective):
    updater = DistanceUpdater()
    updater.r[1][0, 0] = 1.1
    strategy = AdaptiveShapeUpdate()
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    updater.objective_value = objective
    strategy.constraint_weights(updater, gradient)
    assert strategy.tolerance == 0.05
    strategy.constraint_weights(updater, gradient)
    assert strategy.tolerance == pytest.approx(0.0498)


def test_large_violation_pauses_tightening_without_changing_the_base_coefficient():
    updater = DistanceUpdater()
    updater.r[1][0, 0] = 0.8
    strategy = AdaptiveShapeUpdate()
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    initial = strategy.constraint_weights(updater, gradient)["distance"]
    assert strategy.state["distance"]["violation"] == pytest.approx(2.0)
    strengthened = strategy.constraint_weights(updater, gradient)["distance"]
    assert strengthened == pytest.approx(initial)
    assert strategy.tolerance == 0.05
    updater.r[1][0, 0] = 1.1
    assert strategy.constraint_weights(updater, gradient)["distance"] == pytest.approx(initial)
    assert strategy.tolerance == pytest.approx(0.0498)


def test_tightening_waits_for_geometry_and_stops_at_the_final_tolerance():
    updater = DistanceUpdater()
    updater.r[1][0, 0] = 0.96
    strategy = AdaptiveShapeUpdate()
    gradient = torch.tensor([1.0, 0, 0], dtype=torch.float64)
    for _ in range(300):
        strategy.constraint_weights(updater, gradient)
    # A fixed 4% shortfall reaches the candidate floor when 3*t = 0.04.
    assert strategy.tolerance == pytest.approx(0.04 / 3, abs=strategy.tightening_increment)
    assert strategy.state["distance"]["violation"] > strategy._excess_threshold
    updater.r[1][0, 0] = 1.1
    for _ in range(300):
        strategy.constraint_weights(updater, gradient)
    assert strategy.tolerance == 0


@pytest.mark.parametrize("parameters", [
    {"violation_tolerance": 0}, {"violation_tolerance": float("nan")},
    {"tightening_increment": 0}, {"tightening_increment": -0.01},
    {"tightening_increment": float("inf")},
    {"weight_change_limit": 1.0}, {"weight_change_limit": float("nan")},
    {"initial_tolerance": 1 / 3}, {"initial_tolerance": 1.0}, {"initial_tolerance": float("inf")},
    {"final_tolerance": -0.1}, {"final_tolerance": 0.3},
    {"final_tolerance": float("nan")},
])
def test_invalid_schedule_parameters_are_rejected(parameters):
    with pytest.raises(ValueError):
        AdaptiveShapeUpdate(**parameters)


@pytest.mark.parametrize("power", [3, 5, 7])
def test_monitored_violation_is_local_and_independent_of_penalty_power(power):
    barrier = PolynomialBarrier()
    with barrier.measure_violation():
        barrier(torch.tensor([0.8, 0.9, 1.1], dtype=torch.float64), 1.0, 0.8, power)
        barrier(torch.tensor([1.3], dtype=torch.float64), 1.0, 0.8, power)
    assert barrier.maximum_violation == pytest.approx(2.5)
    assert not barrier._monitoring
    value = lambda x: barrier(x, 1.0, 0.8, power)[1].sum()
    point = torch.tensor([1.1], dtype=torch.float64)
    assert torch.isfinite(torch.func.grad(value)(point)).all()
    assert barrier.maximum_violation == pytest.approx(2.5)


def test_violation_monitor_cleans_up_after_an_invalid_geometry_value():
    barrier = PolynomialBarrier()
    with pytest.raises(ValueError, match="violation must be finite"):
        with barrier.measure_violation():
            barrier(torch.tensor([float("nan")]), 1.0, 0.8, 3)
    assert not barrier._monitoring


@pytest.mark.parametrize("required", [0.001, 1.0, 1000.0])
def test_distance_violation_has_the_same_meaning_in_all_length_units(required):
    updater = DistanceUpdater(required)
    updater.r[1][0, 0] = 0.85 * required
    strategy = AdaptiveShapeUpdate()
    strategy.constraint_weights(updater, torch.tensor([1.0, 0, 0], dtype=torch.float64))
    assert strategy.state["distance"]["violation"] == pytest.approx(1.5)

@pytest.mark.parametrize("required", [0.0025, 2.5])
@pytest.mark.parametrize("tolerance", [0.05, 0.025, 0.0])
def test_distance_surcharge_threshold_at_each_width(required, tolerance):
    updater = DistanceUpdater(required)
    policy = AdaptiveShapeUpdate(initial_tolerance=tolerance)
    gradient = torch.tensor([1., 0., 0.], dtype=torch.float64)
    updater.r[1][0, 0] = required
    policy.constraint_weights(updater, gradient)
    for offset in (1e-5, -1e-5):
        step = torch.tensor([-3 * tolerance + offset, 0., 0.], dtype=gradient.dtype)
        peak = policy._measure(updater, step).violations["distance"]
        assert (peak > policy._excess_threshold) == (offset < 0)


def test_upper_bound_relaxation_widens_the_same_polynomial():
    barrier = PolynomialBarrier()
    point = torch.tensor([1.1], dtype=torch.float64)
    for tolerance in (0.05, 0.025, 0.0):
        barrier.tolerance = tolerance
        width = 0.2 + tolerance
        with barrier.measure_violation():
            _, penalties = barrier(point, 1.0, 0.8, 3)
        assert penalties.item() == pytest.approx((0.3 / width)**3)
        assert barrier.maximum_violation == pytest.approx(0.3 / width)
