"""One-time calibration and geometry-only penalty feedback."""

from pathlib import Path

import pytest
import torch

from morphopt.optcore.protocal import ProtocalSavable
from morphopt.optcore.updaters import BaseUpdater
from morphopt.shapeopt.objectivefuncs.basefuncs import BaseConstraints
from morphopt.shapeopt.strategies import AdaptiveShapeWeights


class AnalyticUpdater(BaseUpdater):
    update_kind = "geometry"

    def __init__(self, scale=1.0, area=1.0):
        super().__init__()
        self.scale, self.area = scale, area
        self.z = 0.0
        self.obj_funcs = {"physical": object()}
        self.constraints_funcs = {"limit": BaseConstraints()}

    def closure(self, x, return_list=False):
        physical = -self.scale * x[0]
        # The transition runs from .8 to 1; z=1 is the declared limit.
        values = 0.8 + 0.2 * (self.z + x[:1])
        penalty = self.area * self.constraints_funcs["limit"].barrier_function(values, 1.0, 0.8, 3)[1].sum()
        if return_list:
            return [physical], [penalty]
        return physical + self.constraint_weights["limit"] * penalty

    def gradient(self):
        return torch.tensor([-self.scale, 0.0, 0.0], dtype=torch.float64)


@pytest.mark.parametrize("scale", [1e-6, 1.0, 1e6])
@pytest.mark.parametrize("area", [0.1, 1.0, 1000.0])
def test_initial_weight_balances_native_physical_and_penalty_gradients(scale, area):
    updater = AnalyticUpdater(scale, area)
    strategy = AdaptiveShapeWeights()
    gradient = updater.gradient()
    source = gradient.clone()
    weight = strategy(updater, gradient)["limit"]
    # At x=1 the cubic penalty derivative is 3*area; safety factor is 2.
    assert weight == pytest.approx(2 * scale / (3 * area))
    assert strategy.state["limit"]["initial_weight"] == weight
    torch.testing.assert_close(gradient, source, rtol=0, atol=0)


def test_later_physical_gradient_changes_do_not_recalibrate(monkeypatch):
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]

    def forbidden(*args, **kwargs):
        raise AssertionError("A calibrated term must not request new derivatives")

    monkeypatch.setattr(torch.func, "grad", forbidden)
    monkeypatch.setattr(torch.func, "jacrev", forbidden)
    updater.z = 1.1  # Inside the violation dead band.
    for scale in (1e-6, 1e6, 0.0, 1000.0):
        updater.scale = scale
        updater.objective_value = None
        assert strategy(updater, updater.gradient())["limit"] == initial
    assert set(strategy.state["limit"]) == {"weight", "initial_weight", "violation"}


@pytest.mark.parametrize("violation,factor", [(0.0, 0.9), (0.03, 0.9), (0.1, 1.0), (0.3, 1.125), (5.0, 10.0)])
def test_feedback_strengthens_holds_or_relaxes_from_violation(violation, factor):
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]
    strategy.state["limit"]["weight"] = 4 * initial
    updater.z = 1 + violation
    changed = strategy(updater, updater.gradient())["limit"]
    assert changed == pytest.approx(4 * initial * factor)
    assert strategy.state["limit"]["violation"] == pytest.approx(violation)
    assert changed > 0


def test_severe_violation_is_detected_without_waiting_for_gradient_growth():
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]
    updater.scale = 1e-12
    updater.z = 3.0
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(10 * initial)


def test_repeated_violation_reaches_an_absolute_weight_without_compounding():
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]
    updater.z = 2.0
    for _ in range(300):
        weight = strategy(updater, updater.gradient())["limit"]
    assert weight == pytest.approx(100 * initial)
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(weight)
    # A higher peak can strengthen again; it cannot restart unbounded growth.
    updater.z = 3.0
    for _ in range(300):
        weight = strategy(updater, updater.gradient())["limit"]
    assert weight == pytest.approx(400 * initial)
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(weight)
    updater.z = 1.0
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(0.9 * weight)
    for _ in range(300):
        strategy(updater, updater.gradient())
    assert 0 < strategy(updater, updater.gradient())["limit"] < initial


def test_safe_constraints_release_weight_below_the_initial_calibration():
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]
    for _ in range(20):
        weight = strategy(updater, updater.gradient())["limit"]
    assert weight == pytest.approx(initial * 0.9 ** 20)
    # Small violations below the dead band must not revive a large seed.
    updater.z = 1.03
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(0.9 * weight)
    updater.z = 1.1
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(0.9 * weight)
    # An actual violation still restores weight, with the per-call increase cap.
    updater.z = 3.0
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(9 * weight)


def test_excessive_initial_calibration_settles_below_its_seed_without_new_derivatives(monkeypatch):
    updater = AnalyticUpdater(scale=1000.0)
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]
    updater.scale = 1.0

    def forbidden(*args, **kwargs):
        raise AssertionError("A calibrated term must not request new derivatives")

    monkeypatch.setattr(torch.func, "grad", forbidden)
    monkeypatch.setattr(torch.func, "jacrev", forbidden)
    weight = initial
    tail = []
    for _ in range(200):
        updater.z = (updater.scale / (3 * weight * updater.area)) ** 0.5
        weight = strategy(updater, updater.gradient())["limit"]
        tail.append(weight)
    assert tail[-10:] == pytest.approx([weight] * 10)
    assert 0 < weight < initial / 1000
    assert 0.05 <= strategy.state["limit"]["violation"] <= 0.2
    assert strategy.state["limit"]["initial_weight"] == initial


def test_feedback_settles_after_large_sensitivity_change_without_repeated_recalibration(monkeypatch):
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    weight = strategy(updater, updater.gradient())["limit"]
    updater.scale = 1000.0

    def forbidden(*args, **kwargs):
        raise AssertionError("Only the initial coefficient is calibrated")

    monkeypatch.setattr(torch.func, "grad", forbidden)
    monkeypatch.setattr(torch.func, "jacrev", forbidden)
    tail = []
    for _ in range(100):
        # Exact solution of -scale*z + weight*area*z**3 for this subproblem.
        updater.z = (updater.scale / (3 * weight * updater.area)) ** 0.5
        weight = strategy(updater, updater.gradient())["limit"]
        tail.append(weight)
    assert tail[-10:] == pytest.approx([weight] * 10)
    violation = strategy.state["limit"]["violation"]
    assert 0 < violation < 2.0
    assert weight == pytest.approx(strategy.state["limit"]["initial_weight"] * (violation / 0.1) ** 2)


def test_alternating_violation_peaks_do_not_ratchet_weights_up():
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]
    for _ in range(100):
        for violation in (1.0, 2.0, 0.8, 1.5):
            updater.z = 1 + violation
            assert strategy(updater, updater.gradient())["limit"] <= 400 * initial * (1 + 1e-12)


def test_existing_excess_weight_decays_even_while_violation_remains_above_target():
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]
    strategy.state["limit"]["weight"] = 1e7 * initial
    updater.z = 2.0
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx((0.9e7 + 10) * initial)


@pytest.mark.parametrize("area", [1e-9, 1.0, 1e9])
def test_violation_feedback_is_independent_of_integration_measure(area):
    updater = AnalyticUpdater(area=area)
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())["limit"]
    updater.z = 3.0
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(10 * initial)
    assert strategy.state["limit"]["violation"] == pytest.approx(2.0)


def test_pending_term_calibrates_on_its_first_nonzero_response():
    updater = AnalyticUpdater()
    updater.z = -3.0
    strategy = AdaptiveShapeWeights()
    assert strategy(updater, updater.gradient()) == {"limit": 1.0}
    assert strategy.state == {}
    updater.z = 0.0
    initial = strategy(updater, updater.gradient())["limit"]
    assert initial == pytest.approx(2 / 3)
    updater.scale = 10000.0
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(0.9 * initial)
    assert strategy.state["limit"]["initial_weight"] == initial


def test_zero_physical_gradient_does_not_freeze_a_placeholder_as_calibration():
    updater = AnalyticUpdater(scale=0.0)
    strategy = AdaptiveShapeWeights()
    assert strategy(updater, updater.gradient()) == {"limit": 1.0}
    assert strategy.state == {}
    updater.scale = 1.0
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(2 / 3)


def test_restart_restores_initial_weights_violation_and_next_feedback(tmp_path: Path):
    updater = AnalyticUpdater()
    original = AdaptiveShapeWeights()
    assert isinstance(original, ProtocalSavable)
    original(updater, updater.gradient())
    updater.z = 3.0
    original(updater, updater.gradient())
    original.save(str(tmp_path), 2)
    restored = AdaptiveShapeWeights()
    restored.load(str(tmp_path), 2)
    assert restored.state == original.state
    assert restored.tolerance == original.tolerance
    updater.z = 1.02
    assert restored(updater, updater.gradient()) == original(updater, updater.gradient())
    assert restored.tolerance == original.tolerance


def test_removed_terms_are_forgotten():
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    strategy(updater, updater.gradient())
    updater.constraints_funcs.clear()
    assert strategy(updater, updater.gradient()) == {}
    assert strategy.state == {}


def test_negative_penalty_is_rejected():
    class SignedTerm(AnalyticUpdater):
        def closure(self, x, return_list=False):
            physical, penalty = super().closure(x, True)
            return physical, [penalty[0] - 100]

    updater = SignedTerm()
    with pytest.raises(ValueError, match="nonnegative"):
        AdaptiveShapeWeights()(updater, updater.gradient())
