"""Update policies for geometric subproblems."""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import torch

from ..constants import CONSTANT
from ..optcore.strategies import (
    FixedUpdate,
    UpdateStrategy,
)
from .objectivefuncs.surfacefairness import Fairness
from .surfaces.cpgeo_surface import CPGEOSurface

if TYPE_CHECKING:
    from ..optcore.updaters import BaseUpdater
    from .barriers import PolynomialBarrier
    from .boundary_part import BoundaryPart

__all__ = [
    "AdaptiveShapeUpdate",
    "FixedUpdate",
    "SensitivityShapeUpdate",
    "UpdateStrategy",
]

logger = logging.getLogger(__name__)
_SETTINGS = CONSTANT.KERNEL.ADAPTIVE_SHAPE_UPDATE


@dataclass(frozen=True)
class _ShapeTrial:
    """Unweighted physical proxy and sampled penalties at a shape perturbation."""

    objective: float
    penalties: dict[str, float]
    violations: dict[str, float]

    def merit(self, weights: dict[str, float]) -> float:
        """Use the inner solver's physical proxy and area-integrated penalties."""
        return self.objective + sum(
            weights[name] * value for name, value in self.penalties.items()
        )


@contextmanager
def _local_surcharges(
    barriers: dict[str, PolynomialBarrier], weights: dict[str, float]
) -> Iterator[None]:
    """Apply local surcharges for one evaluation, then return to the base penalties."""
    try:
        for name, weight in weights.items():
            barriers[name].excess_weight = weight
        yield
    finally:
        for name in weights:
            barriers[name].excess_weight = 0.0


class AdaptiveShapeUpdate(UpdateStrategy):
    """Scale each geometric term with the physical gradient and penalize excess locally.

    Solve consecutive stages from the preceding endpoint. Peak violations
    determine which local penalties to strengthen for the next solve.
    The last subproblem endpoint is the design committed to the outer loop.
    """

    def __init__(
        self,
        initial_tolerance: float = _SETTINGS.INITIAL_TOLERANCE,
        final_tolerance: float = _SETTINGS.FINAL_TOLERANCE,
        tightening_increment: float = _SETTINGS.TIGHTENING_INCREMENT,
        violation_tolerance: float = _SETTINGS.VIOLATION_TOLERANCE,
        weight_change_limit: float = _SETTINGS.WEIGHT_CHANGE_LIMIT,
        max_solves: int = _SETTINGS.MAX_SOLVES,
    ) -> None:
        """Initialize AdaptiveShapeUpdate and its configuration state.

        Args:
            initial_tolerance (float): Initial relative geometric relaxation before continuation
                begins.
            final_tolerance (float): Smallest permitted relative relaxation after continuation.
            tightening_increment (float): Relaxation decrement applied while monitored violations
                are within the continuation band.
            violation_tolerance (float): Reference violation magnitude expressed in barrier
                transition-width units.
            weight_change_limit (float): Cap on the safety factor applied to the
                predicted gain when pricing the next local surcharge.
            max_solves (int): Maximum solves per outer update, including any penalty retries.
        """
        if not 0 <= final_tolerance <= initial_tolerance < 1 / 3:
            raise ValueError(
                "Require 0 <= final_tolerance <= initial_tolerance < 1/3 for positive wall clearance."
            )
        if (
            not 0 < tightening_increment < math.inf
            or not 0 < violation_tolerance < math.inf
        ):
            raise ValueError(
                "Tightening increment and violation tolerance must be finite and positive."
            )
        if not 1 < weight_change_limit < math.inf:
            raise ValueError("weight_change_limit must be finite and exceed one.")
        self.initial_tolerance = initial_tolerance
        self.final_tolerance = final_tolerance
        self.tightening_increment = tightening_increment
        self.violation_tolerance = violation_tolerance
        self.weight_change_limit = weight_change_limit
        if type(max_solves) is not int or max_solves < 1:
            raise ValueError("max_solves must be a positive integer.")
        self.max_solves = max_solves
        self.tolerance = initial_tolerance
        self._started = False
        self._gradient_norm = 0.0
        self.state: dict[str, dict[str, float]] = {}
        self._origin_trial: _ShapeTrial | None = None
        self._repair_scale: float | None = None

    @property
    def _excess_threshold(self) -> float:
        """Peak that triggers additional local resistance, in transition-width units."""
        return 1.0 + self.tolerance / (
            _SETTINGS.DISTANCE_TRANSITION_RATIO + self.tolerance
        )

    def constraint_weights(
        self, updater: BaseUpdater, gradient: torch.Tensor
    ) -> dict[str, float]:
        """Calibrate newly active terms and scale their weights in the subproblem design coordinates.

        Args:
            updater: Geometry updater with initialized objective and penalty terms.
            gradient: Native physical gradient in design-variable order.

        Returns:
            Base penalty weights for this outer update, keyed by registered constraint name.
        """
        if updater.update_kind != "geometry":
            raise TypeError("AdaptiveShapeUpdate requires a geometry updater.")
        terms = updater.constraints_funcs
        self.state = {name: self.state[name] for name in terms if name in self.state}
        self._repair_scale = None
        if not terms:
            self._origin_trial = None
            return {}

        origin = torch.zeros_like(gradient)
        for term in terms.values():
            term.barrier_function.tolerance = self.tolerance
            term.barrier_function.excess_weight = 0.0
        trial = self._measure(updater, origin)
        upper = max(
            self._excess_threshold,
            1.0 + self.violation_tolerance * _SETTINGS.VIOLATION_BAND_RATIO,
        )
        can_tighten = self._started and self.tolerance > self.final_tolerance
        if can_tighten and max(trial.violations.values()) <= upper:
            self.tolerance = max(
                self.final_tolerance, self.tolerance - self.tightening_increment
            )
            for term in terms.values():
                term.barrier_function.tolerance = self.tolerance
            trial = self._measure(updater, origin)
        self._started = True
        self._origin_trial = trial

        # Differentiate through the same fixed controls, symmetry and step map as the solver.
        def objective(x: torch.Tensor) -> torch.Tensor:
            objectives, _ = updater.closure(x, return_list=True)
            return sum(objectives).reshape(())

        physical = torch.func.grad(objective)(origin).detach()
        norm = physical.norm().item()
        if not math.isfinite(norm):
            raise ValueError("Physical gradient norm must be finite.")
        if norm > 0:
            # A stationary objective retains its last scale so penalties can still repair the shape.
            self._gradient_norm = norm
            pending = {
                name: i for i, name in enumerate(terms) if name not in self.state
            }
            if pending:
                for name, weight in self._calibrate(
                    updater, pending, physical, norm
                ).items():
                    self.state[name] = {
                        "initial_weight": weight,
                        "reference_design_gradient_norm": norm,
                    }

        weights = dict.fromkeys(
            terms, CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT
        )
        for name, record in self.state.items():
            record["violation"] = trial.violations[name]
            weights[name] = record["initial_weight"] * (
                self._gradient_norm / record["reference_design_gradient_norm"]
            )
        # A unit move in each normalized design coordinate gives a first-order
        # work scale. A reconstruction spike can exceed it by many orders.
        rebuilt_fairness = [
            weights[name] * trial.penalties[name]
            for name, term in terms.items()
            if isinstance(term, Fairness) and any(
                isinstance(s, CPGEOSurface) and s.is_updatable and s.reconstructed
                for s in term.surfaces
            )
        ]
        if rebuilt_fairness:
            work = physical.abs().sum().item()
            if max(rebuilt_fairness) > work:
                self._repair_scale = work if work > 0 else 1.0
        logger.info(
            "Shape update: tolerance=%.6g base_weights=%s peak_z=%s base_penalties=%s",
            self.tolerance,
            weights,
            trial.violations,
            trial.penalties,
        )
        return weights

    def solve_update(
        self,
        updater: BaseUpdater,
        origin: torch.Tensor,
    ) -> torch.Tensor:
        """Commit the final inner solution, including any remaining soft violations.

        Each solve has its own full step budget. With constraints, run the first
        two solves if allowed, then continue only while a local limit is exceeded.
        If Fairness dominates after CPGEO reconstruction, condition the first
        solve and use its endpoint as the reference for subsequent retries.

        Args:
            updater: Geometry updater supplying the subproblem solver and base weights.
            origin: Starting perturbation in the updater's design coordinates.

        Returns:
            The perturbation at the end of the last solve.
        """
        initial = self._origin_trial
        if updater.max_step_iter <= 0:
            return origin
        if initial is None:
            return updater.solve_subproblem(origin)

        baseline = initial
        candidate = origin
        first_regular_stage = 1
        if self._repair_scale is not None:
            # asinh is increasing for signed objectives. It preserves descent
            # directions and stationary points while damping the initial spike.
            scale = self._repair_scale
            candidate = updater.solve_subproblem(
                origin, loss=lambda x: torch.asinh(updater.closure(x) / scale)
            )
            repaired = self._measure(updater, candidate)
            logger.info(
                "Shape reconstruction solve 1/%d: physical_change=%.6g peak_z=%s -> %s",
                self.max_solves, repaired.objective - baseline.objective,
                baseline.violations, repaired.violations,
            )
            baseline = repaired
            first_regular_stage = 2

        limits = {
            # A repair may improve fairness while temporarily thinning the wall.
            # Carry improvements forward without relaxing any other peak limit.
            name: max(self._excess_threshold, min(value, initial.violations[name]))
            for name, value in baseline.violations.items()
        }
        barriers = {
            name: term.barrier_function
            for name, term in updater.constraints_funcs.items()
        }
        # Only these terms receive an extra local penalty during the next solve.
        surcharges: dict[str, float] = {}
        for stage in range(first_regular_stage, self.max_solves + 1):
            with _local_surcharges(barriers, surcharges):
                candidate = updater.solve_subproblem(candidate)

            trial = self._measure(updater, candidate)
            logger.info(
                "Shape solve %d/%d: physical_change=%.6g peak_z=%s",
                stage,
                self.max_solves,
                trial.objective - initial.objective,
                trial.violations,
            )
            overloaded = [
                name for name, peak in trial.violations.items() if peak > limits[name]
            ]
            if stage == self.max_solves or (stage >= 2 and not overloaded):
                break
            if overloaded:
                weights = updater.constraint_weights
                gain = max(0.0, baseline.merit(weights) - trial.merit(weights))
                # A unit surcharge gives the integrated cost of the overloaded samples alone.
                for name in overloaded:
                    barriers[name].excess_start = max(
                        0.0, limits[name] - self.violation_tolerance
                    )
                with (
                    _local_surcharges(barriers, dict.fromkeys(overloaded, 1.0)),
                    torch.no_grad(),
                ):
                    _, penalties = updater.closure(candidate, return_list=True)
                unit_penalties = dict(zip(barriers, penalties, strict=True))
                factor = min(self.weight_change_limit, _SETTINGS.RETRY_WEIGHT_INCREASE)
                for name in overloaded:
                    cost = weights[name] * (
                        unit_penalties[name].item() - trial.penalties[name]
                    )
                    weight = max(1.0, factor * surcharges.get(name, 0.0))
                    surcharges[name] = (
                        max(weight, factor * gain / cost) if cost > 0 else weight
                    )
                logger.info("Shape retry: local excess coefficients=%s", surcharges)
        return candidate

    def _measure(
        self,
        updater: BaseUpdater,
        variables: torch.Tensor,
    ) -> _ShapeTrial:
        """Measure the physical proxy, integrated penalties and peak local violations together."""
        terms = updater.constraints_funcs
        with ExitStack() as stack, torch.no_grad():
            for term in terms.values():
                stack.enter_context(term.barrier_function.measure_violation())
            objectives, penalties = updater.closure(variables, return_list=True)
            scalars = [value.reshape(()) for value in (sum(objectives), *penalties)]
            objective, *values = torch.stack(scalars).tolist()
        if not math.isfinite(objective) or any(not 0 <= v < math.inf for v in values):
            raise ValueError("Shape terms must be finite and penalties nonnegative.")
        peaks = {
            name: term.barrier_function.maximum_violation
            for name, term in terms.items()
        }
        return _ShapeTrial(objective, dict(zip(terms, values, strict=True)), peaks)

    def _calibrate(
        self,
        updater: BaseUpdater,
        selected: dict[str, int],
        physical: torch.Tensor,
        physical_norm: float,
    ) -> dict[str, float]:
        """Balance each pending penalty against its strongest resolvable probe response."""

        def pending_penalties(x: torch.Tensor) -> torch.Tensor:
            _, penalties = updater.closure(x, return_list=True)
            return torch.stack([penalties[i].reshape(()) for i in selected.values()])

        probe = self._descent_probe(physical)
        derivatives = torch.func.jacrev(pending_penalties)
        with ExitStack() as stack:
            for name in selected:
                stack.enter_context(updater.constraints_funcs[name].barrier_function.calibration_probe())
            forward = derivatives(probe)
            backward = derivatives(-probe)

        weights = {}
        for name, plus, minus in zip(selected, forward, backward, strict=True):
            # A barely active endpoint must not outweigh a well-resolved opposite probe.
            plus_norm, minus_norm = plus.norm().item(), minus.norm().item()
            if not (math.isfinite(plus_norm) and math.isfinite(minus_norm)):
                raise ValueError("Penalty probe gradients must be finite.")
            penalty, norm = (plus, plus_norm) if plus_norm >= minus_norm else (minus, minus_norm)
            if norm > 0:
                conflict = max(0.0, -(physical / norm @ (penalty / norm)).item())
                weights[name] = max(
                    _SETTINGS.SAFETY_FACTOR * conflict,
                    _SETTINGS.BALANCE_RATIO * physical_norm / norm,
                )
        return weights

    @staticmethod
    def _descent_probe(gradient: torch.Tensor) -> torch.Tensor:
        """Probe a fraction of the per-point step along the feasible design descent direction."""
        vectors = gradient.detach().reshape(-1, 3)
        norms = vectors.norm(dim=1, keepdim=True)
        # Invert the updater's atan map at the desired fraction of the step limit.
        direction = torch.where(norms > 0, -vectors / norms, 0.0).flatten()
        return direction * math.tan(math.pi * _SETTINGS.PROBE_FRACTION / 2)

    def history_data(self) -> dict[str, object]:
        """Report peak violations even for terms still awaiting calibration."""
        peaks = self._origin_trial.violations if self._origin_trial is not None else {}
        return {
            "tolerance": self.tolerance,
            "penalties": {name: {"peak_z": peak} for name, peak in peaks.items()},
        }

    def save(self, foldpath: str, iteration: int) -> None:
        """Checkpoint the relaxation schedule and calibrated coefficients for restart."""
        path = Path(foldpath) / f"adaptive_weights_{iteration}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tolerance": self.tolerance,
            "started": self._started,
            "design_gradient_norm": self._gradient_norm,
            "penalties": self.state,
        }
        path.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")

    def load(self, foldpath: str, iteration: int) -> None:
        """Restore the schedule; terms without a reference gradient are calibrated again."""
        path = Path(foldpath) / f"adaptive_weights_{iteration}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.tolerance = data["tolerance"]
        self._started = data["started"]
        self._gradient_norm = data.get("design_gradient_norm", 0.0)
        self.state = {
            name: record
            for name, record in data["penalties"].items()
            if "reference_design_gradient_norm" in record
        }


class SensitivityShapeUpdate(UpdateStrategy):
    """Restore pointwise penalty weights from nearest control-point sensitivities.

    Each outer update interpolates the native gradient magnitude to surface
    quadrature points, with coordinate rescaling as in the original method.
    Zero samples use the smallest positive value on their surface; an entirely
    zero surface uses ones. The physical gradient and area weights stay intact.
    """

    def constraint_weights(
        self,
        updater: BaseUpdater,
        gradient: torch.Tensor,
    ) -> dict[str, float]:
        """Evaluate SensitivityShapeUpdate for the supplied inputs.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.

        Returns:
            dict[str, float]: Default outer coefficients for all penalty terms. Pointwise weights
                are installed on the terms as a side effect.
        """
        from scipy.interpolate import NearestNDInterpolator

        if updater.update_kind != "geometry":
            raise TypeError("SensitivityShapeUpdate requires a geometry updater.")
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
