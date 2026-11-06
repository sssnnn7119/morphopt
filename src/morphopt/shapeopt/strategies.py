"""Shape-specific policies chosen outside the inner optimization loop."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING

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

__all__ = [
    "AdaptiveShapeWeights",
    "ConstantConstraintWeights",
    "ConstraintWeightStrategy",
    "FixedStepLength",
    "StepLengthStrategy",
]

logger = logging.getLogger(__name__)


class AdaptiveShapeWeights(ConstraintWeightStrategy):
    """Tighten distance requirements and calibrate geometric penalty weights.

    One outer call sets the distance relaxation, then probes both directions
    of the physical gradient to balance each penalty. The resulting distance
    target and coefficients stay fixed throughout the inner solve. Neither
    physical sensitivities nor reference integration weights are rescaled.
    """

    def __init__(
        self,
        tightening_steps: int = CONSTANT.KERNEL.ADAPTIVE_SHAPE_WEIGHTS.TIGHTENING_STEPS,
        initial_tolerance: float = CONSTANT.KERNEL.ADAPTIVE_SHAPE_WEIGHTS.INITIAL_TOLERANCE,
        final_tolerance: float = CONSTANT.KERNEL.ADAPTIVE_SHAPE_WEIGHTS.FINAL_TOLERANCE,
    ) -> None:
        """Configure the outer distance schedule.

        Args:
            tightening_steps: Positive number of completed outer updates needed
                to reach the final relaxation.
            initial_tolerance: Initial fractional reduction of nominal distance;
                0.2 applies 80 percent of the nominal requirement.
            final_tolerance: Final fractional reduction, usually zero.
                Set both tolerances equal for a fixed distance requirement.
        """
        if (
            not isinstance(tightening_steps, int)
            or isinstance(tightening_steps, bool)
            or tightening_steps < 1
        ):
            raise ValueError("tightening_steps must be a positive integer.")
        if not all(
            math.isfinite(value) for value in (initial_tolerance, final_tolerance)
        ):
            raise ValueError("Distance tolerances must be finite.")
        if not 0 <= final_tolerance <= initial_tolerance < 1:
            raise ValueError("Require 0 <= final_tolerance <= initial_tolerance < 1.")
        self.tightening_steps = tightening_steps
        self.initial_tolerance = initial_tolerance
        self.final_tolerance = final_tolerance
        self.completed_steps = 0
        self.tolerance = initial_tolerance
        self.state: dict[str, dict[str, float]] = {}
        self.diagnostics: dict[str, dict[str, float]] = {}

    def __call__(
        self,
        updater: BaseUpdater,
        gradient: torch.Tensor,
    ) -> dict[str, float]:
        """Configure one subproblem without changing the physical gradient."""
        if updater.update_kind != "geometry":
            raise TypeError("AdaptiveShapeWeights requires a geometry updater.")
        names = list(updater.constraints_funcs)
        if not names:
            self.state, self.diagnostics = {}, {}
            return {}
        if not updater.obj_funcs:
            raise ValueError("AdaptiveShapeWeights requires a physical objective.")

        progress = min(self.completed_steps / self.tightening_steps, 1.0)
        self.tolerance = (
            1 - progress
        ) * self.initial_tolerance + progress * self.final_tolerance
        for constraint in updater.constraints_funcs.values():
            # Only distance penalties supply a scale and use this relaxation.
            constraint.barrier_function.tolerance = self.tolerance

        def terms(variables: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            objectives, penalties = updater.closure(variables, return_list=True)
            values = torch.stack(
                [sum(objectives).reshape(())] + [p.reshape(()) for p in penalties]
            )
            return values, values.detach()

        with torch.no_grad():
            _, current = terms(torch.zeros_like(gradient))
        settings = CONSTANT.KERNEL.ADAPTIVE_SHAPE_WEIGHTS
        vectors = gradient.detach().reshape(-1, 3)
        norms = vectors.norm(dim=1, keepdim=True)
        # Normalize only the probe direction; retain native physical gradients.
        # Zero-gradient points use the same unit diagonal in both probes.
        direction = torch.where(
            norms > 0,
            -vectors / norms.clamp_min(torch.finfo(vectors.dtype).tiny),
            torch.full_like(vectors, 1 / math.sqrt(3)),
        ).flatten()
        # Invert the existing atan displacement mapping to probe half a step.
        probe = direction * math.tan(math.pi * settings.PROBE_FRACTION / 2)
        forward, forward_values = torch.func.jacrev(terms, has_aux=True)(probe)
        backward, backward_values = torch.func.jacrev(terms, has_aux=True)(-probe)
        values = (current, forward_values, backward_values)
        if not all(
            torch.isfinite(value).all() for value in (*values, forward, backward)
        ):
            raise ValueError(
                "Adaptive weight probes produced non-finite geometry terms or gradients."
            )
        if any((value[1:] < 0).any() for value in values):
            raise ValueError("AdaptiveShapeWeights requires nonnegative penalty terms.")

        state: dict[str, dict[str, float]] = {}
        diagnostics: dict[str, dict[str, float]] = {}
        for index, name in enumerate(names, start=1):
            previous = self.state.get(name)
            weight = (
                CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT
                if previous is None
                else previous["weight"]
            )
            candidates: list[tuple[float, float, float]] = []
            for jacobian in (forward, backward):
                physical, penalty = jacobian[0], jacobian[index]
                physical_norm, penalty_norm = (
                    physical.norm().item(),
                    penalty.norm().item(),
                )
                if penalty_norm > 0 and physical_norm > 0:
                    # The conflict term balances descent along -penalty. The
                    # smaller norm floor covers nearly orthogonal gradients.
                    conflict = max(
                        0.0,
                        -(physical / penalty_norm @ (penalty / penalty_norm)).item(),
                    )
                    candidate = max(
                        settings.SAFETY_FACTOR * conflict,
                        settings.BALANCE_RATIO * physical_norm / penalty_norm,
                    )
                    candidates.append((candidate, physical_norm, penalty_norm))
            physical_norm = penalty_norm = 0.0
            if candidates:
                weight, physical_norm, penalty_norm = max(candidates)
            # Inactive terms retain their last calibration. No feedback factor
            # accumulates while the distance requirement itself is changing.
            state[name] = {"weight": weight, "penalty": current[index].item()}
            diagnostics[name] = {
                "physical_gradient_norm": physical_norm,
                "penalty_gradient_norm": penalty_norm,
            }
            logger.info(
                "Adaptive shape weight %s: step=%d tolerance=%.6g weight=%.6g penalty=%.6g",
                name,
                self.completed_steps,
                self.tolerance,
                weight,
                state[name]["penalty"],
            )
        self.state, self.diagnostics = state, diagnostics
        self.completed_steps += 1
        return {name: record["weight"] for name, record in state.items()}

    def save(self, foldpath: str, iteration: int) -> None:
        """Save outer progress and calibrated coefficients for worker restarts."""
        directory = Path(foldpath)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"adaptive_weights_{iteration}.json").write_text(
            json.dumps(
                {"completed_steps": self.completed_steps, "penalties": self.state},
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
        self.completed_steps = data["completed_steps"]
        self.state = data["penalties"]
        self.diagnostics = {}
