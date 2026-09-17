"""Updater for material fields and material-local constraints."""

from ..modelparams.material.base import BaseMaterialInterface
from .base import BaseUpdater
from .terms import ConstraintTerm


class MaterialUpdater(BaseUpdater):
    """Update one material field and its local regularization terms."""

    def __init__(
        self, name: str, material: BaseMaterialInterface | None = None
    ) -> None:
        super().__init__(name, material)
        self._material = material
        """Material interface updated by this updater."""
        self._constraints: list[ConstraintTerm] = []
        """Material-local feasibility constraints."""
        self._regularization_terms: list[ConstraintTerm] = []
        """Material-local regularization terms."""

    @property
    def constraints(self) -> tuple[ConstraintTerm, ...]:
        """Return local material constraints."""
        return tuple(self._constraints)

    @property
    def regularization_terms(self) -> tuple[ConstraintTerm, ...]:
        """Return local material regularizers."""
        return tuple(self._regularization_terms)

    def add_constraint(self, constraint: ConstraintTerm) -> ConstraintTerm:
        """Append one material constraint."""
        self._constraints.append(constraint)
        return constraint

    def add_regularization(self, term: ConstraintTerm) -> ConstraintTerm:
        """Append one material regularization term."""
        self._regularization_terms.append(term)
        return term
