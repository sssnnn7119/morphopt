"""Updaters for BoundaryPart and inward OffsetShellPart objects."""

from morphopt._torch import torch

from ..modelparams.parts.base import BasePartDefinition
from .base import BaseUpdater
from .terms import ConstraintTerm


class BoundaryPartUpdater(BaseUpdater):
    """Update one BoundaryPart with equality and penalty constraints."""

    def __init__(
        self,
        name: str,
        part: BasePartDefinition | None = None,
        *,
        device: str = "cpu",
        step_size: float = 1e-2,
    ) -> None:
        super().__init__(name, part, device=device, step_size=step_size)
        self._part = part
        """BoundaryPart or OffsetShellPart updated by this updater."""
        self._constraints: list[ConstraintTerm] = []
        """Local penalty constraints owned by this updater."""
        self._equality_constraint: ConstraintTerm | None = None
        """Single equality projection callback."""

    @property
    def constraints(self) -> tuple[ConstraintTerm, ...]:
        """Return local geometry penalty constraints."""
        return tuple(self._constraints)

    def set_equality_constraint(self, constraint: ConstraintTerm) -> None:
        """Set the single equality projection callback."""
        self._equality_constraint = constraint

    def get_equality_constraint(self) -> ConstraintTerm | None:
        """Read the configured equality projection callback."""
        return self._equality_constraint

    def add_constraint(self, constraint: ConstraintTerm) -> ConstraintTerm:
        """Append one local penalty constraint."""
        self._constraints.append(constraint)
        return constraint

    def _apply_equality_constraint(self, parameters: torch.Tensor) -> torch.Tensor:
        """Project trial parameters through the configured equality callback."""
        # TODO: Project trial control points through the unique equality constraint.
        return parameters


class OffsetShellPartUpdater(BoundaryPartUpdater):
    """Updater for inward offset shells sharing source control points."""

    def __init__(self, name: str, part: BasePartDefinition | None = None) -> None:
        super().__init__(name, part)
        self._offset_constraints: list[ConstraintTerm] = []
        """Penalty constraints evaluated on the offset geometry."""
