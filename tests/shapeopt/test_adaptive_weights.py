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
        self.objective_value = 1.0
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
    assert strategy.state["limit"]["reference_penalty"] == 0
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
    strategy = AdaptiveShapeWeights()
    weights = [strategy(updater, updater.gradient())["limit"] for _ in range(5)]
    assert weights == pytest.approx([weights[0]] * 5)
    assert strategy.tolerance == pytest.approx(0.046)
    assert set(strategy.state["limit"]) == {"weight", "reference_penalty"}


@pytest.mark.parametrize("curvature", [0.0, 1.0, 1000.0, 1e6])
@pytest.mark.parametrize("scale", [0.001, 1.0])
def test_quadratic_curvature_does_not_inflate_penalty_weights(curvature, scale):
    class QuadraticUpdater(AnalyticUpdater):
        def closure(self, x, return_list=False):
            objectives, penalties = super().closure(x, True)
            return [objectives[0] + 0.5 * curvature * x.square().sum()], penalties

    updater = QuadraticUpdater(scale=scale)
    gradient = updater.gradient()
    strategy = AdaptiveShapeWeights()
    weights = strategy(updater, gradient)
    assert weights["limit"] == pytest.approx(1.25 * scale)
    torch.testing.assert_close(gradient, updater.gradient(), rtol=0, atol=0)


def test_stationary_physical_objective_does_not_recalibrate_from_curvature():
    class StationaryUpdater(AnalyticUpdater):
        def closure(self, x, return_list=False):
            _, penalties = super().closure(x, True)
            return [1000 * x.square().sum()], penalties

    updater = StationaryUpdater(scale=0.0)
    strategy = AdaptiveShapeWeights()
    strategy.state["limit"] = {"weight": 7.0, "reference_penalty": 0.0}
    assert strategy(updater, updater.gradient()) == {"limit": 7.0}


def test_no_response_or_zero_physical_gradient_keeps_finite_coefficients():
    for updater in (AnalyticUpdater(boundary=3.0), AnalyticUpdater(scale=0.0)):
        strategy = AdaptiveShapeWeights()
        strategy.state["limit"] = {"weight": 7.0, "reference_penalty": 0.0}
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
def test_learned_coefficients_are_not_replaced_by_new_gradient_scales(previous_weight):
    updater = AnalyticUpdater()
    strategy = AdaptiveShapeWeights()
    strategy.state["limit"] = {
        "weight": previous_weight, "reference_penalty": 0.0,
    }
    weights = strategy(updater, updater.gradient())
    assert weights == {"limit": previous_weight}


def test_growing_seventh_power_violation_does_not_shrink_its_coefficient():
    class SeventhPowerUpdater(AnalyticUpdater):
        def closure(self, x, return_list=False):
            physical = -self.scale * x[0]
            penalty = torch.relu(self.offset + x[0] - self.boundary) ** 7
            return [physical], [penalty]

    updater = SeventhPowerUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())
    updater.offset = 100.0
    updater.scale = 0.001
    gradient = updater.gradient()
    source = gradient.clone()
    assert strategy(updater, gradient)["limit"] == pytest.approx(1.25 * initial["limit"])
    penalty = updater.closure(torch.zeros_like(gradient), True)[1][0].item()
    assert penalty > 1e13
    assert initial["limit"] * penalty > 1e13
    torch.testing.assert_close(gradient, source, rtol=0, atol=0)


def test_inactive_default_is_not_frozen_before_a_penalty_responds(tmp_path):
    updater = AnalyticUpdater(boundary=3.0)
    strategy = AdaptiveShapeWeights()
    assert strategy(updater, updater.gradient()) == {"limit": 1.0}
    assert strategy.state == {}
    strategy.save(str(tmp_path), 1)
    restored = AdaptiveShapeWeights()
    restored.load(str(tmp_path), 1)
    updater.boundary = 0.2
    assert restored(updater, updater.gradient()) == {"limit": pytest.approx(1.25)}
    assert "limit" in restored.state


def test_calibrated_terms_do_not_require_new_displaced_geometry_probes():
    class TrialRestrictedUpdater(AnalyticUpdater):
        allow_trials = True

        def closure(self, x, return_list=False):
            if not self.allow_trials and x.abs().sum() > 0:
                raise ValueError("No new displaced geometry probe is allowed")
            return super().closure(x, return_list)

    updater = TrialRestrictedUpdater()
    strategy = AdaptiveShapeWeights()
    initial = strategy(updater, updater.gradient())
    updater.allow_trials = False
    assert strategy(updater, updater.gradient()) == initial


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


def test_negative_displaced_penalty_cannot_be_used_for_initial_calibration():
    class SignedTrial(AnalyticUpdater):
        def closure(self, x, return_list=False):
            return [-x[0]], [1 - 2 * x[0].square()]

    updater = SignedTrial()
    with pytest.raises(ValueError, match="nonnegative"):
        AdaptiveShapeWeights()(updater, updater.gradient())


@pytest.mark.parametrize("relaxation", [0.0, 0.05])
def test_material_deterioration_strengthens_only_the_affected_penalty(relaxation):
    class TwoPenalties(AnalyticUpdater):
        def closure(self, x, return_list=False):
            objectives, first = super().closure(x, True)
            unchanged = torch.relu(x[0] - self.boundary) ** 2
            return objectives, [first[0], unchanged]

    updater = TwoPenalties()
    updater.constraints_funcs["unchanged"] = BaseConstraints()
    strategy = AdaptiveShapeWeights(initial_tolerance=relaxation)
    updater.objective_value = 10.0
    initial = strategy(updater, updater.gradient())
    updater.offset = 1.0
    updater.objective_value = 12.0  # Substantial objective regression does not veto repair.
    changed = strategy(updater, updater.gradient())
    assert changed["limit"] == pytest.approx(1.25 * initial["limit"])
    assert changed["unchanged"] == initial["unchanged"]
    assert strategy.tolerance == pytest.approx(max(0.0, relaxation - 0.001))
    reference = strategy.state["limit"]["reference_penalty"]
    updater.objective_value = 20.0
    assert strategy(updater, updater.gradient()) == changed
    assert strategy.state["limit"]["reference_penalty"] == reference
    assert strategy.tolerance == pytest.approx(max(0.0, relaxation - 0.001))


def test_negligible_penalty_growth_is_not_strengthened():
    updater = AnalyticUpdater(area=1e-9)
    strategy = AdaptiveShapeWeights()
    strategy.state["limit"] = {
        "weight": 1.0, "reference_penalty": 0.0,
    }
    updater.objective_value = 10.0
    strategy(updater, updater.gradient())
    updater.offset = 1.0
    updater.objective_value = 12.0
    assert strategy(updater, updater.gradient()) == {"limit": 1.0}
    assert strategy.tolerance == 0.05


def test_cumulative_penalty_growth_is_detected_and_improvement_resets_reference():
    updater = AnalyticUpdater(offset=1.0)
    strategy = AdaptiveShapeWeights()
    updater.objective_value = 10.0
    initial = strategy(updater, updater.gradient())["limit"]
    for objective, value in ((8.0, 0.9), (6.0, 1.2)):
        updater.objective_value = objective
        updater.offset = updater.boundary + value**0.5
        assert strategy(updater, updater.gradient())["limit"] == initial
    updater.objective_value = 4.0
    updater.offset = updater.boundary + 1.4**0.5
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(1.25 * initial)
    updater.objective_value = 2.0
    updater.offset = updater.boundary + 0.3**0.5
    strategy(updater, updater.gradient())
    assert strategy.state["limit"]["reference_penalty"] == pytest.approx(0.3)
    updater.objective_value = 1.0
    updater.offset = updater.boundary + 0.7**0.5
    assert strategy(updater, updater.gradient())["limit"] == pytest.approx(1.25**2 * initial)


def test_restart_preserves_penalty_growth_reference_and_objective_scale(tmp_path):
    updater = AnalyticUpdater(offset=1.0)
    strategy = AdaptiveShapeWeights()
    updater.objective_value = 10.0
    strategy(updater, updater.gradient())
    updater.objective_value = 1.0
    strategy(updater, updater.gradient())
    strategy.save(str(tmp_path), 2)
    restored = AdaptiveShapeWeights()
    restored.load(str(tmp_path), 2)
    assert restored.objective_scale == 10.0
    updater.offset = 2.0
    updater.objective_value = 1.005
    assert restored(updater, updater.gradient()) == strategy(updater, updater.gradient())
    assert restored.tolerance == strategy.tolerance
    assert restored.state == strategy.state


def test_calibration_leaves_zero_sensitivity_points_unperturbed():
    class ObservedUpdater(AnalyticUpdater):
        def __init__(self):
            super().__init__()
            self.trials = []

        def closure(self, x, return_list=False):
            self.trials.append(x.detach().clone())
            return super().closure(x, return_list)

    updater = ObservedUpdater()
    gradient = torch.tensor([-1.0, 0, 0, 0, 0, 0], dtype=torch.float64)
    weight = AdaptiveShapeWeights()(updater, gradient)["limit"]
    assert weight == pytest.approx(1.25)
    trials = [x for x in updater.trials if x.abs().sum() > 0]
    assert len(trials) == 2
    for trial in trials:
        torch.testing.assert_close(trial[1:], torch.zeros_like(trial[1:]))


def test_unrelated_large_penalty_cannot_hide_deterioration():
    class SeparatePenalties(AnalyticUpdater):
        def closure(self, x, return_list=False):
            objectives, penalties = super().closure(x, True)
            return objectives, [penalties[0], x.new_tensor(1e12)]

    updater = SeparatePenalties(offset=2.0)
    updater.constraints_funcs["other"] = BaseConstraints()
    updater.objective_value = 12.0
    strategy = AdaptiveShapeWeights()
    strategy.previous_objective = 10.0
    strategy.objective_scale = 10.0
    strategy.state = {
        "limit": {"weight": 1.0, "reference_penalty": 1.0},
        "other": {"weight": 1.0, "reference_penalty": 1e12},
    }
    assert strategy(updater, updater.gradient()) == {"limit": 1.25, "other": 1.0}
    assert strategy.tolerance == pytest.approx(0.049)
