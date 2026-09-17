"""Native node-set and reference-point boundary component definitions."""

from __future__ import annotations

from collections.abc import Iterable

import torchfea

from .base import BaseFEAComponent


class BoundaryCondition(BaseFEAComponent):
    """Constrain selected translational degrees of freedom on a node set."""

    def __init__(
        self,
        name: str,
        instance_name: str,
        node_set_name: str,
        *,
        index_dof: Iterable[int] = (0, 1, 2),
    ) -> None:
        super().__init__(name, target_names=(instance_name, node_set_name))
        self._instance_name = str(instance_name)
        """Instance carrying the constrained nodes."""
        self._node_set_name = str(node_set_name)
        """Target node-set name."""
        self._index_dof = tuple(int(index) for index in index_dof)
        """Constrained node degree-of-freedom indices."""
        self._torchfea_BoundaryCondition: torchfea.boundarys.Boundary_Condition | None = None
        """Native node-set boundary condition."""

    @property
    def _attachment_name(self) -> str:
        """Register this component with ``Assembly.add_boundary()``."""
        return "boundary"

    def _create_fea_object(self) -> torchfea.boundarys.Boundary_Condition:
        """Create the native node-set boundary condition."""
        self._torchfea_BoundaryCondition = torchfea.boundarys.Boundary_Condition(
            instance_name=self._instance_name,
            set_nodes_name=self._node_set_name,
            indexDoF=list(self._index_dof),
        )
        return self._torchfea_BoundaryCondition


class BoundaryConditionRP(BaseFEAComponent):
    """Constrain selected degrees of freedom on one reference point."""

    def __init__(
        self,
        name: str,
        reference_point_name: str,
        *,
        index_dof: Iterable[int] = (0, 1, 2, 3, 4, 5),
    ) -> None:
        super().__init__(name, target_names=(reference_point_name,))
        self._reference_point_name = str(reference_point_name)
        """Target reference-point name."""
        self._index_dof = tuple(int(index) for index in index_dof)
        """Constrained reference-point degree-of-freedom indices."""
        self._torchfea_BoundaryConditionRP: torchfea.boundarys.Boundary_Condition_RP | None = None
        """Native reference-point boundary condition."""

    @property
    def _attachment_name(self) -> str:
        """Register this component with ``Assembly.add_boundary()``."""
        return "boundary"

    def _create_fea_object(self) -> torchfea.boundarys.Boundary_Condition_RP:
        """Create the native reference-point boundary condition."""
        self._torchfea_BoundaryConditionRP = torchfea.boundarys.Boundary_Condition_RP(
            rp_name=self._reference_point_name,
            indexDoF=list(self._index_dof),
        )
        return self._torchfea_BoundaryConditionRP
