"""Penalty calibration preserves physical scales and survives outer restarts."""

from pathlib import Path

import pytest
import torch

from morphopt.optcore.protocal import ProtocalSavable
from morphopt.shapeopt.strategies import AdaptiveShapeWeights
from morphopt.optcore.updaters import BaseUpdater
from morphopt.shapeopt.objectivefuncs.basefuncs import BaseConstraints


class AnalyticUpdater(BaseUpdater):
    update_kind = "geometry"

    def __init__(self, scale=1.0, area=1.0, boundary=0.2, offset=0.0):
        super().__init__()
        self.scale, self.area = scale, area
        self.boundary, self.offset = boundary, offset
        self.obj_funcs = {"physical": object()}
        self.constraints_funcs = {"limit": BaseConstraints()}

    def closure(self, x, return_list=False):
        physical = -self.scale * x[0]
        penalty = self.area * torch.relu(self.offset + x[0] - self.boundary) ** 2
        if return_list:
            return [physical], [penalty]
        return physical + self.constraint_weights["limit"] * penalty

    def gradient(self):
        return torch.tensor([-self.scale, 0.0, 0.0], dtype=torch.float64)


def test_inactive_penalty_is_detected_by_probe_and_opposes_violation():
    updater = AnalyticUpdater(scale=100.0)
    strategy = AdaptiveShapeWeights()
    gradient = updater.gradient()
    assert updater.closure(torch.zeros(3), return_list=True)[1][0] == 0
    weights = strategy(updater, gradient)
    # At x=1: g=-100, p=2*(1-0.2)=1.6, so the conflict threshold is 62.5.
    assert weights["limit"] == pytest.approx(125.0)
    assert strategy.state["limit"]["penalty"] == 0
    probe = torch.tensor([1.0, 0.0, 0.0], dtype=torch.float64)
    physical = torch.func.grad(lambda x: updater.closure(x, True)[0][0])(probe)
    penalty = torch.func.grad(lambda x: updater.closure(x, True)[1][0])(probe)
    restoring_direction = -penalty
    assert (physical + weights["limit"] * penalty) @ restoring_direction < 0
    torch.testing.assert_close(gradient, updater.gradient(), rtol=0, atol=0)


@pytest.mark.parametrize("scale", [1e-6, 1.0, 1e6])
@pytest.mark.parametrize("area", [0.1, 1.0, 1000.0])
def test_weight_tracks_raw_objective_scale_and_inverse_surface_measure(scale, area):
    updater = AnalyticUpdater(scale=scale, area=area)
    weight = AdaptiveShapeWeights()(updater, updater.gradient())["limit"]
    assert weight == pytest.approx(1.25 * scale / area, rel=1e-10)


def test_repeated_calibration_does_not_accumulate_penalty_weights():
    updater = AnalyticUpdater(offset=0.4)
    strategy = AdaptiveShapeWeights(tightening_steps=2)
    weights = [strategy(updater, updater.gradient())["limit"] for _ in range(5)]
    assert weights == pytest.approx([weights[0]] * 5)
    assert strategy.tolerance == 0
    assert strategy.completed_steps == 5
    assert set(strategy.state["limit"]) == {"weight", "penalty"}


def test_no_response_or_zero_physical_gradient_keeps_finite_coefficients():
    for updater in (AnalyticUpdater(boundary=3.0), AnalyticUpdater(scale=0.0)):
        strategy = AdaptiveShapeWeights()
        strategy.state["limit"] = {"weight": 7.0, "penalty": 0.0}
        weights = strategy(updater, updater.gradient())
        assert weights == {"limit": 7.0}


def test_constant_penalty_does_not_trigger_ineffective_weight_growth():
    class ConstantPenalty(AnalyticUpdater):
        def closure(self, x, return_list=False):
            return [-x[0]], [x.new_tensor(5.0)]

    updater = ConstantPenalty()
    strategy = AdaptiveShapeWeights()
    for _ in range(3):
        assert strategy(updater, updater.gradient()) == {"limit": 1.0}


def test_multiple_penalties_are_calibrated_by_name_and_scale():
    class MultiplePenalties(AnalyticUpdater):
        def closure(self, x, return_list=False):
            objectives, penalties = super().closure(x, True)
            return objectives, [penalties[0], 3 * penalties[0]]

    updater = MultiplePenalties()
    updater.constraints_funcs["second"] = BaseConstraints()
    strategy = AdaptiveShapeWeights()
    weights = strategy(updater, updater.gradient())
    assert weights["limit"] == pytest.approx(3 * weights["second"])


@pytest.mark.parametrize("previous_weight", [1e-12, 1e12])
def test_calibration_replaces_both_excessively_small_and_large_coefficients(previous_weight):
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    strategy.state["limit"] = {
        "weight": previous_weight, "penalty": 0.0,
    }
    weights = strategy(updater, updater.gradient())
    assert weights == {"limit": pytest.approx(1.25)}


def test_restart_restores_calibration_and_next_update(tmp_path: Path):
    updater = AnalyticUpdater(offset=0.4)
    original = AdaptiveShapeWeights()
    assert isinstance(original, ProtocalSavable)
    original(updater, updater.gradient())
    original(updater, updater.gradient())
    saved: ProtocalSavable = original
    saved.save(str(tmp_path), iteration=2)
    restored = AdaptiveShapeWeights()
    restored.load(str(tmp_path), iteration=2)
    assert restored.state == original.state
    assert restored(updater, updater.gradient()) == original(updater, updater.gradient())


def test_negative_auxiliary_objective_is_not_treated_as_a_penalty():
    class SignedTerm(AnalyticUpdater):
        def closure(self, x, return_list=False):
            objectives, penalties = super().closure(x, True)
            return objectives, [penalties[0] - 100.0]

    updater = SignedTerm()
    with pytest.raises(ValueError, match="nonnegative"):
        AdaptiveShapeWeights()(updater, updater.gradient())


