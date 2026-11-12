"""Shape-specific policies chosen outside the inner optimization loop."""

from __future__ import annotations

import json
import logging
import math
from contextlib import ExitStack
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
    """Calibrate each term once, then adjust only from geometric violation.

    Violation is the maximum sampled limit excess in transition-width units.
    Each target coefficient is measured from the initial calibration, so a
    persistent violation cannot compound the coefficient indefinitely. A dead
    band avoids reacting to small excess; surplus weight decays gradually.
    Distance requirements tighten only while all monitored terms remain mild.

    Above the dead band, the target is w0 * (v / v_target)**2.
    Below the band, the target is zero, allowing an excessive calibration to
    decay. Each call closes 10% of the gap, subject to the increase cap.
    """

    def __init__(
        self,
        initial_tolerance: float = _SETTINGS.INITIAL_TOLERANCE,
        final_tolerance: float = _SETTINGS.FINAL_TOLERANCE,
        tightening_increment: float = _SETTINGS.TIGHTENING_INCREMENT,
        violation_tolerance: float = _SETTINGS.VIOLATION_TOLERANCE,
        weight_change_limit: float = _SETTINGS.WEIGHT_CHANGE_LIMIT,
    ) -> None:
        parameters = (
            initial_tolerance,
            final_tolerance,
            tightening_increment,
            violation_tolerance,
            weight_change_limit,
        )
        if not all(math.isfinite(value) for value in parameters):
            raise ValueError("Adaptive weight parameters must be finite.")
        if not 0 <= final_tolerance <= initial_tolerance < 1:
            raise ValueError("Require 0 <= final_tolerance <= initial_tolerance < 1.")
        if tightening_increment <= 0 or violation_tolerance <= 0:
            raise ValueError(
                "Tightening increment and violation tolerance must be positive."
            )
        if weight_change_limit <= 1:
            raise ValueError("weight_change_limit must exceed one.")
        self.initial_tolerance = initial_tolerance
        self.final_tolerance = final_tolerance
        self.tightening_increment = tightening_increment
        self.violation_tolerance = violation_tolerance
        self.weight_change_limit = weight_change_limit
        self.tolerance = initial_tolerance
        self._started = False
        self.state: dict[str, dict[str, float]] = {}

    def __call__(
        self, updater: BaseUpdater, gradient: torch.Tensor
    ) -> dict[str, float]:
        """Freeze violation-driven coefficients for the next inner solve."""
        if updater.update_kind != "geometry":
            raise TypeError("AdaptiveShapeWeights requires a geometry updater.")
        names = list(updater.constraints_funcs)
        self.state = {
            name: value for name, value in self.state.items() if name in names
        }
        if not names:
            return {}
        origin = torch.zeros_like(gradient)
        for constraint in updater.constraints_funcs.values():
            constraint.barrier_function.tolerance = self.tolerance
        penalties, violations = self._measure(updater, origin)
        upper = self.violation_tolerance * _SETTINGS.VIOLATION_BAND_RATIO
        previous_tolerance = self.tolerance
        if self._started and max(violations.values()) <= upper:
            self.tolerance = max(
                self.final_tolerance, self.tolerance - self.tightening_increment
            )
        self._started = True
        if self.tolerance != previous_tolerance:
            for constraint in updater.constraints_funcs.values():
                constraint.barrier_function.tolerance = self.tolerance
            penalties, violations = self._measure(updater, origin)
        logger.info(
            "Shape distance continuation: tolerance=%.6g max_violation=%.6g action=%s",
            self.tolerance,
            max(violations.values()),
            "tightened" if self.tolerance < previous_tolerance else "held",
        )

        pending = {
            name: index + 1
            for index, name in enumerate(names)
            if name not in self.state
        }
        learned = {}
        if pending:
            if not updater.obj_funcs:
                raise ValueError(
                    "Initial weight calibration requires a physical objective."
                )
            physical = torch.func.grad(lambda x: self._values(updater, x)[0])(origin)
            if not torch.isfinite(physical).all():
                raise ValueError("Physical gradient must be finite.")
            learned = self._calibrate(updater, gradient, pending, physical)

        weights = {}
        lower = self.violation_tolerance / _SETTINGS.VIOLATION_BAND_RATIO
        for name in names:
            previous = self.state.get(name)
            violation = violations[name]
            weight = (
                previous["weight"]
                if previous
                else learned.get(
                    name,
                    CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT,
                )
            )
            target = weight
            mode = (
                "held" if previous else ("calibrated" if name in learned else "pending")
            )
            if previous:
                # Use an absolute target, not another multiplier of the last
                # weight. Repeated peaks of the same size must not ratchet it up.
                target = (
                    previous["initial_weight"]
                    * (violation / self.violation_tolerance)
                    ** _SETTINGS.VIOLATION_WEIGHT_POWER
                )
                if violation < lower:
                    # The calibration is a scale, not a lower weight bound.
                    target = 0.0
                if violation > upper or violation < lower:
                    weight = min(
                        weight + _SETTINGS.WEIGHT_UPDATE_FRACTION * (target - weight),
                        weight * self.weight_change_limit,
                    )
                    if weight != previous["weight"]:
                        mode = (
                            "strengthened" if weight > previous["weight"] else "relaxed"
                        )
            if previous or name in learned:
                self.state[name] = {
                    "weight": weight,
                    "initial_weight": previous["initial_weight"]
                    if previous
                    else weight,
                    "violation": violation,
                }
            weights[name] = weight
            logger.info(
                "Adaptive shape weight %s: tolerance=%.6g violation=%.6g "
                "weight=%.6g target_weight=%.6g penalty=%.6g weighted_penalty=%.6g mode=%s",
                name,
                self.tolerance,
                violation,
                weight,
                target,
                penalties[name],
                weight * penalties[name],
                mode,
            )
        return weights

    def _measure(
        self,
        updater: BaseUpdater,
        origin: torch.Tensor,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Reuse each penalty's barrier calls; no geometry formulas are duplicated."""
        with ExitStack() as stack, torch.no_grad():
            for constraint in updater.constraints_funcs.values():
                stack.enter_context(constraint.barrier_function.measure_violation())
            values = self._values(updater, origin)[1:].tolist()
        penalties = dict(zip(updater.constraints_funcs, values, strict=True))
        violations = {
            name: constraint.barrier_function.maximum_violation
            for name, constraint in updater.constraints_funcs.items()
        }
        return penalties, violations

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
        selected: dict[str, int],
        physical: torch.Tensor,
    ) -> dict[str, float]:
        """Set each selected term's initial physical-to-penalty gradient balance."""
        if not selected:
            return {}
        physical_norm = physical.norm().item()
        if physical_norm == 0:
            return {}

        vectors = gradient.detach().reshape(-1, 3)
        norms = vectors.norm(dim=1, keepdim=True)
        # Zero-sensitivity points stay fixed. Invert the updater's atan mapping
        # to probe the configured fraction of its maximum displacement.
        probe = torch.where(norms > 0, -vectors / norms, 0.0).flatten()
        probe *= math.tan(math.pi * _SETTINGS.PROBE_FRACTION / 2)
        indices = list(selected.values())
        derivatives = torch.func.jacrev(lambda x: self._values(updater, x)[indices])
        weights = {}
        for sign in (1, -1):
            jacobian = derivatives(sign * probe)
            if not torch.isfinite(jacobian).all():
                raise ValueError("Penalty probe gradients must be finite.")
            for name, penalty in zip(selected, jacobian, strict=True):
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

    def save(self, foldpath: str, iteration: int) -> None:
        directory = Path(foldpath)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"adaptive_weights_{iteration}.json").write_text(
            json.dumps(
                {
                    "tolerance": self.tolerance,
                    "started": self._started,
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
        self.tolerance = data["tolerance"]
        self._started = data["started"]
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
