"""Updater for parameterized FEA load components."""

from ..modelparams.components.base import BaseFEAComponent
from .base import BaseUpdater
from .terms import ConstraintTerm


class FEAUpdater(BaseUpdater):
    """Update one load-value owner in one FEA case."""

    def __init__(self, name: str, component: BaseFEAComponent | None = None) -> None:
        super().__init__(name, component)
        self._component = component
        """LoadValueBlock or FEA component updated by this updater."""
        self._constraints: list[ConstraintTerm] = []
        """Local load-value constraints."""

    @property
    def constraints(self) -> tuple[ConstraintTerm, ...]:
        """Return local load constraints."""
        return tuple(self._constraints)

    def add_constraint(self, constraint: ConstraintTerm) -> ConstraintTerm:
        """Append one local load constraint."""
        self._constraints.append(constraint)
        return constraint
