"""Shape-specific policies chosen outside the inner optimization loop."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, cast

import torch

from ..constants import CONSTANT
from ..optcore.strategies import (
    ConstantConstraintWeights,
    ConstraintWeightStrategy,
    FixedStepLength,
    StepLengthStrategy,
)

if TYPE_CHECKING:
    from ..optcore.updaters import BaseUpdater
    from .boundary_part import BoundaryPart

__all__ = [
    "AdaptiveShapeWeights",
    "ConstantConstraintWeights",
    "ConstraintWeightStrategy",
    "FixedStepLength",
    "SensitivityShapeWeights",
    "StepLengthStrategy",
]

logger = logging.getLogger(__name__)
_SETTINGS = CONSTANT.KERNEL.ADAPTIVE_SHAPE_WEIGHTS


class AdaptiveShapeWeights(ConstraintWeightStrategy):
    """Calibrate once, then tighten on small objective changes or penalty growth.

    Monitor penalties at a fixed relaxation. Increase only deteriorating
    coefficients and keep all coefficients fixed during each inner solve.
    """

    def __init__(
        self,
        initial_tolerance: float = _SETTINGS.INITIAL_TOLERANCE,
        final_tolerance: float = _SETTINGS.FINAL_TOLERANCE,
        objective_tolerance: float = _SETTINGS.OBJECTIVE_TOLERANCE,
        tightening_increment: float = _SETTINGS.TIGHTENING_INCREMENT,
        penalty_growth_limit: float = _SETTINGS.PENALTY_GROWTH_LIMIT,
    ) -> None:
        """Configure relaxation bounds and event thresholds.

        initial_tolerance/final_tolerance are fractional distance relaxations.
        objective_tolerance bounds the absolute objective change relative to
        its historical maximum magnitude, allowing small oscillations.
        tightening_increment is the relaxation decrement per qualifying event.
        penalty_growth_limit compares a monitored penalty with its reference.
        None of these rules depends on the outer iteration number.
        """
        if not all(
            math.isfinite(value)
            for value in (
                initial_tolerance,
                final_tolerance,
                objective_tolerance,
                tightening_increment,
                penalty_growth_limit,
            )
        ):
            raise ValueError("Continuation parameters must be finite.")
        if not 0 <= final_tolerance <= initial_tolerance < 1:
            raise ValueError("Require 0 <= final_tolerance <= initial_tolerance < 1.")
        if not 0 <= objective_tolerance < 1:
            raise ValueError("objective_tolerance must lie in [0, 1).")
        if tightening_increment <= 0:
            raise ValueError("tightening_increment must be positive.")
        if penalty_growth_limit <= 1:
            raise ValueError("penalty_growth_limit must exceed one.")
        self.initial_tolerance = initial_tolerance
        self.final_tolerance = final_tolerance
        self.objective_tolerance = objective_tolerance
        self.tightening_increment = tightening_increment
        self.penalty_growth_limit = penalty_growth_limit
        self.objective_scale = 0.0
        self.tolerance = initial_tolerance
        self.previous_objective: float | None = None
        self.state: dict[str, dict[str, float]] = {}

    def __call__(
        self,
        updater: BaseUpdater,
        gradient: torch.Tensor,
    ) -> dict[str, float]:
        """Monitor, calibrate pending terms, then freeze this subproblem's weights."""
        if updater.update_kind != "geometry":
            raise TypeError("AdaptiveShapeWeights requires a geometry updater.")
        names = list(updater.constraints_funcs)
        self.state = {
            name: record for name, record in self.state.items() if name in names
        }
        if not names:
            return {}
        objective = updater.objective_value
        if objective is None or not math.isfinite(objective):
            raise ValueError(
                "AdaptiveShapeWeights requires a finite high-fidelity objective_value."
            )
        if not updater.obj_funcs:
            raise ValueError("AdaptiveShapeWeights requires a physical objective.")

        origin = torch.zeros_like(gradient)
        # Fixed monitoring thresholds separate geometric deterioration from
        # penalty growth caused by tightening the distance requirement itself.
        for constraint in updater.constraints_funcs.values():
            constraint.barrier_function.tolerance = self.initial_tolerance
        with torch.no_grad():
            monitor = dict(
                zip(names, self._values(updater, origin)[1:].tolist(), strict=True)
            )
        deteriorated = self._advance_requirements(objective, monitor)
        for constraint in updater.constraints_funcs.values():
            constraint.barrier_function.tolerance = self.tolerance

        pending = {
            name: index + 1
            for index, name in enumerate(names)
            if name not in self.state
        }
        learned = self._calibrate(updater, gradient, pending)
        if self.tolerance == self.initial_tolerance:
            penalties = monitor
        else:
            with torch.no_grad():
                penalties = dict(
                    zip(names, self._values(updater, origin)[1:].tolist(), strict=True)
                )

        weights = {}
        for name in names:
            previous = self.state.get(name)
            mode = "pending" if previous is None else "held"
            weight = (
                previous["weight"]
                if previous
                else CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT
            )
            reference = monitor[name]
            if name in learned:
                weight, mode = learned[name], "calibrated"
            elif name in deteriorated:
                weight *= _SETTINGS.WEIGHT_INCREASE
                mode = "strengthened"
            if previous is not None and name not in deteriorated:
                reference = min(reference, previous["reference_penalty"])
            if previous is not None or name in learned:
                self.state[name] = {"weight": weight, "reference_penalty": reference}
            weights[name] = weight
            logger.info(
                "Adaptive shape weight %s: tolerance=%.6g weight=%.6g "
                "penalty=%.6g weighted_penalty=%.6g monitor_penalty=%.6g "
                "reference_penalty=%.6g mode=%s",
                name,
                self.tolerance,
                weight,
                penalties[name],
                weight * penalties[name],
                monitor[name],
                previous["reference_penalty"] if previous else monitor[name],
                mode,
            )
        return weights

    @staticmethod
    def _values(updater: BaseUpdater, variables: torch.Tensor) -> torch.Tensor:
        """Evaluate the physical proxy followed by raw geometric penalties."""
        objectives, penalties = updater.closure(variables, return_list=True)
        values = torch.stack(
            [sum(objectives).reshape(())] + [p.reshape(()) for p in penalties]
        )
        if not torch.isfinite(values).all() or (values[1:] < 0).any():
            raise ValueError("Shape terms must be finite and penalties nonnegative.")
        return values

    def _calibrate(
        self,
        updater: BaseUpdater,
        gradient: torch.Tensor,
        pending: dict[str, int],
    ) -> dict[str, float]:
        """Balance pending penalties against the native gradient at the origin."""
        if not pending:
            return {}
        physical = torch.func.grad(lambda x: self._values(updater, x)[0])(
            torch.zeros_like(gradient)
        )
        if not torch.isfinite(physical).all():
            raise ValueError("Physical gradient must be finite.")
        physical_norm = physical.norm().item()
        if physical_norm == 0:
            return {}

        vectors = gradient.detach().reshape(-1, 3)
        norms = vectors.norm(dim=1, keepdim=True)
        # Zero-sensitivity points stay fixed. Invert the updater's atan mapping
        # to probe the configured fraction of its maximum displacement.
        probe = torch.where(norms > 0, -vectors / norms, 0.0).flatten()
        probe *= math.tan(math.pi * _SETTINGS.PROBE_FRACTION / 2)
        indices = list(pending.values())
        derivatives = torch.func.jacrev(lambda x: self._values(updater, x)[indices])
        weights = {}
        for sign in (1, -1):
            jacobian = derivatives(sign * probe)
            if not torch.isfinite(jacobian).all():
                raise ValueError("Penalty probe gradients must be finite.")
            for name, penalty in zip(pending, jacobian, strict=True):
                norm = penalty.norm().item()
                if norm == 0:
                    continue
                conflict = max(0.0, -(physical / norm @ (penalty / norm)).item())
                weight = max(
                    _SETTINGS.SAFETY_FACTOR * conflict,
                    _SETTINGS.BALANCE_RATIO * physical_norm / norm,
                )
                weights[name] = max(weights.get(name, 0.0), weight)
        return weights

    def _advance_requirements(
        self,
        objective: float,
        penalties: dict[str, float],
    ) -> set[str]:
        """Advance only on small objective changes or material penalty growth.

        The historical objective scale avoids division by a near-zero current
        objective. Penalty references track improvements, then reset after a
        strengthening event; an unchanged violation cannot repeatedly ratchet
        its coefficient. Each reference uses the fixed monitoring relaxation.
        """
        self.objective_scale = max(self.objective_scale, abs(objective))
        relative_change = None
        if self.previous_objective is not None:
            change = abs(self.previous_objective - objective)
            relative_change = (
                change / self.objective_scale if self.objective_scale else 0.0
            )
        significant = _SETTINGS.SIGNIFICANT_PENALTY_RATIO * self.objective_scale
        deteriorated = {
            name
            for name, record in self.state.items()
            if record["weight"] * penalties[name] > significant
            and penalties[name]
            > self.penalty_growth_limit * record["reference_penalty"]
        }
        previous_tolerance = self.tolerance
        settled = (
            relative_change is not None and relative_change <= self.objective_tolerance
        )
        if settled or deteriorated:
            self.tolerance = max(
                self.final_tolerance,
                self.tolerance - self.tightening_increment,
            )
        self.previous_objective = objective
        logger.info(
            "Shape distance continuation: objective=%.6g relative_change=%s "
            "tolerance=%.6g action=%s reason=%s",
            objective,
            relative_change,
            self.tolerance,
            "tightened" if self.tolerance < previous_tolerance else "held",
            "penalty_growth:" + ",".join(sorted(deteriorated))
            if deteriorated
            else ("small_objective_change" if settled else "objective_changing"),
        )
        return deteriorated

    def save(self, foldpath: str, iteration: int) -> None:
        """Save objective progress, relaxation and calibrated coefficients."""
        directory = Path(foldpath)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"adaptive_weights_{iteration}.json").write_text(
            json.dumps(
                {
                    "previous_objective": self.previous_objective,
                    "objective_scale": self.objective_scale,
                    "tolerance": self.tolerance,
                    "penalties": self.state,
                },
                allow_nan=False,
            ),
            encoding="utf-8",
        )

    def load(self, foldpath: str, iteration: int) -> None:
        data = json.loads(
            (Path(foldpath) / f"adaptive_weights_{iteration}.json").read_text(
                encoding="utf-8"
            )
        )
        self.previous_objective = data["previous_objective"]
        self.objective_scale = data["objective_scale"]
        self.tolerance = data["tolerance"]
        self.state = data["penalties"]


class SensitivityShapeWeights(ConstraintWeightStrategy):
    """Restore pointwise penalty weights from nearest control-point sensitivities.

    Each outer update interpolates the native gradient magnitude to surface
    quadrature points, with coordinate rescaling as in the original method.
    Zero samples use the smallest positive value on their surface; an entirely
    zero surface uses ones. The physical gradient and area weights stay intact.
    """

    def __call__(
        self,
        updater: BaseUpdater,
        gradient: torch.Tensor,
    ) -> dict[str, float]:
        from scipy.interpolate import NearestNDInterpolator

        if updater.update_kind != "geometry":
            raise TypeError("SensitivityShapeWeights requires a geometry updater.")
        names = list(updater.constraints_funcs)
        if not names:
            return {}
        if not torch.isfinite(gradient).all():
            raise ValueError("Sensitivity weights require a finite physical gradient.")

        part = cast("BoundaryPart", updater.target)
        controls = torch.cat(part.get_parameters()).reshape(-1, 3)
        interpolate = NearestNDInterpolator(
            controls.detach().cpu().numpy(),
            gradient.detach().reshape(-1, 3).norm(dim=1).cpu().numpy(),
            rescale=True,
        )
        points, _, _ = part.get_geometry_values()
        samples = []
        for surface_points in points:
            values = torch.as_tensor(
                interpolate(surface_points.detach().cpu().numpy()),
                dtype=surface_points.dtype,
                device=surface_points.device,
            )
            positive = values > 0
            values = (
                torch.where(positive, values, values[positive].min())
                if positive.any()
                else torch.ones_like(values)
            )
            samples.append(values)
        for constraint in updater.constraints_funcs.values():
            constraint.set_sample_weights(samples)
            constraint.barrier_function.tolerance = None
        return {
            name: CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT
            for name in names
        }
