"""Concrete load, constraint, spring, and contact component definitions."""

from __future__ import annotations

from collections.abc import Iterable

from morphopt._torch import torch
import torchfea

from .base import BaseFEAComponent


class Pressure(BaseFEAComponent):
    """Apply one scalar pressure to an Instance surface set."""

    def __init__(
        self,
        name: str,
        surface_set: str,
        *,
        instance_name: str = "final_model",
        pressure: float = 0.0,
    ) -> None:
        super().__init__(name, default_values=(pressure,), target_names=(instance_name, surface_set))
        self._instance_name = str(instance_name)
        """Target Assembly Instance name."""
        self._surface_set = str(surface_set)
        """Target surface-set name on the Instance."""
        self._torchfea_Pressure: torchfea.loads.Pressure | None = None
        """Native pressure load built for the current Assembly."""

    @property
    def instance_name(self) -> str:
        """Return the target Instance name."""
        return self._instance_name

    @property
    def surface_set(self) -> str:
        """Return the target surface-set name."""
        return self._surface_set

    def _create_fea_object(self) -> torchfea.loads.Pressure:
        """Create the native pressure load with its default scalar value."""
        self._torchfea_Pressure = torchfea.loads.Pressure(
            instance_name=self._instance_name,
            surface_set=self._surface_set,
            pressure=self.default_values[0],
        )
        return self._torchfea_Pressure

    def _apply_values(self, values: torch.Tensor) -> None:
        """Write the active scalar pressure to TorchFEA."""
        self._torchfea_Pressure.pressure = values[0]


class BodyForce(BaseFEAComponent):
    """Apply a three-direction body-force density to one element family."""

    def __init__(
        self,
        name: str,
        element_name: str,
        *,
        instance_name: str = "final_model",
        force_density: Iterable[float] = (0.0, 0.0, -9.81e-6),
    ) -> None:
        values = tuple(float(value) for value in force_density)
        if len(values) != 3:
            raise ValueError("BodyForce requires three force-density values")
        super().__init__(name, default_values=values, target_names=(instance_name, element_name))
        self._instance_name = str(instance_name)
        """Target Assembly Instance name."""
        self._element_name = str(element_name)
        """Target element-family name."""
        self._torchfea_BodyForce: torchfea.loads.BodyForce | None = None
        """Native body-force load built for the current Assembly."""

    def _create_fea_object(self) -> torchfea.loads.BodyForce:
        """Create the native body-force load."""
        self._torchfea_BodyForce = torchfea.loads.BodyForce(
            instance_name=self._instance_name,
            element_name=self._element_name,
            force_density=list(self.default_values),
        )
        return self._torchfea_BodyForce

    def _apply_values(self, values: torch.Tensor) -> None:
        """Write the current three-direction force density to TorchFEA."""
        self._torchfea_BodyForce.force_density = values


class ConcentratedForce(BaseFEAComponent):
    """Apply a three-direction concentrated force at one reference point."""

    def __init__(
        self,
        name: str,
        reference_point_name: str,
        *,
        force: Iterable[float] = (0.0, 0.0, 0.0),
    ) -> None:
        values = tuple(float(value) for value in force)
        if len(values) != 3:
            raise ValueError("ConcentratedForce requires three force values")
        super().__init__(name, default_values=values, target_names=(reference_point_name,))
        self._reference_point_name = str(reference_point_name)
        """Target reference-point name."""
        self._torchfea_ConcentratedForce: torchfea.loads.Concentrate_Force | None = None
        """Native concentrated-force load for the current Assembly."""

    @property
    def reference_point_name(self) -> str:
        """Return the target reference-point name."""
        return self._reference_point_name

    def _create_fea_object(self) -> torchfea.loads.Concentrate_Force:
        """Create the native concentrated force."""
        self._torchfea_ConcentratedForce = torchfea.loads.Concentrate_Force(
            rp_name=self._reference_point_name,
            force=list(self.default_values),
        )
        return self._torchfea_ConcentratedForce

    def _apply_values(self, values: torch.Tensor) -> None:
        """Write the current concentrated-force vector to TorchFEA."""
        self._torchfea_ConcentratedForce.force = values


class ConcentratedMoment(BaseFEAComponent):
    """Apply a three-direction concentrated moment at one reference point."""

    def __init__(
        self,
        name: str,
        reference_point_name: str,
        *,
        moment: Iterable[float] = (0.0, 0.0, 0.0),
    ) -> None:
        values = tuple(float(value) for value in moment)
        if len(values) != 3:
            raise ValueError("ConcentratedMoment requires three moment values")
        super().__init__(name, default_values=values, target_names=(reference_point_name,))
        self._reference_point_name = str(reference_point_name)
        """Target reference-point name."""
        self._torchfea_ConcentratedMoment: torchfea.loads.Moment | None = None
        """Native concentrated-moment load for the current Assembly."""

    def _create_fea_object(self) -> torchfea.loads.Moment:
        """Create the native concentrated moment."""
        self._torchfea_ConcentratedMoment = torchfea.loads.Moment(
            rp_name=self._reference_point_name,
            moment=list(self.default_values),
        )
        return self._torchfea_ConcentratedMoment

    def _apply_values(self, values: torch.Tensor) -> None:
        """Write the current concentrated-moment vector to TorchFEA."""
        self._torchfea_ConcentratedMoment.moment = values


class Couple(BaseFEAComponent):
    """Couple a node set to one reference point."""

    def __init__(self, name: str, instance_name: str, node_set_name: str, reference_point_name: str) -> None:
        super().__init__(name, target_names=(instance_name, node_set_name, reference_point_name))
        self._instance_name = str(instance_name)
        """Instance carrying the coupled nodes."""
        self._node_set_name = str(node_set_name)
        """Node-set name coupled to the reference point."""
        self._reference_point_name = str(reference_point_name)
        """Target reference-point name."""
        self._torchfea_Couple: torchfea.constraints.Couple | None = None
        """Native coupling constraint for the current Assembly."""

    @property
    def _attachment_name(self) -> str:
        """Register couplings through ``Assembly.add_constraint()``."""
        return "constraint"

    def _create_fea_object(self) -> torchfea.constraints.Couple:
        """Create the native coupling constraint."""
        self._torchfea_Couple = torchfea.constraints.Couple(
            instance_name=self._instance_name,
            set_nodes_name=self._node_set_name,
            rp_name=self._reference_point_name,
        )
        return self._torchfea_Couple


class SpringToGround(BaseFEAComponent):
    """Connect one reference point to a fixed point with an axial spring."""

    def __init__(
        self,
        name: str,
        reference_point_name: str,
        *,
        stiffness: float = 0.0,
        rest_length: float = -1.0,
        point: Iterable[float] = (0.0, 0.0, 0.0),
    ) -> None:
        point_values = tuple(float(value) for value in point)
        if len(point_values) != 3:
            raise ValueError("SpringToGround requires a three-coordinate point")
        super().__init__(name, default_values=(stiffness, rest_length, *point_values), target_names=(reference_point_name,))
        self._reference_point_name = str(reference_point_name)
        """Reference point connected to the fixed point."""
        self._torchfea_SpringToGround: torchfea.loads.Spring_RP_Point | None = None
        """Native reference-point-to-ground spring."""

    def _create_fea_object(self) -> torchfea.loads.Spring_RP_Point:
        """Create the native reference-point-to-ground spring."""
        values = self.default_values
        self._torchfea_SpringToGround = torchfea.loads.Spring_RP_Point(
            rp_name=self._reference_point_name,
            point=list(values[2:]),
            k=values[0],
            rest_length=None if values[1] < 0 else values[1],
        )
        return self._torchfea_SpringToGround

    def _apply_values(self, values: torch.Tensor) -> None:
        """Write stiffness, rest length, and ground point to TorchFEA."""
        self._torchfea_SpringToGround.k = values[0]
        self._torchfea_SpringToGround.rest_length = values[1]
        self._torchfea_SpringToGround.point = values[2:]


class SpringBetweenRPs(BaseFEAComponent):
    """Connect two reference points with an axial spring."""

    def __init__(self, name: str, reference_point_name1: str, reference_point_name2: str, *, stiffness: float = 0.0, rest_length: float = -1.0) -> None:
        super().__init__(name, default_values=(stiffness, rest_length), target_names=(reference_point_name1, reference_point_name2))
        self._reference_point_name1 = str(reference_point_name1)
        """First reference-point name."""
        self._reference_point_name2 = str(reference_point_name2)
        """Second reference-point name."""
        self._torchfea_SpringBetweenRPs: torchfea.loads.Spring_RP_RP | None = None
        """Native reference-point-to-reference-point spring."""

    def _create_fea_object(self) -> torchfea.loads.Spring_RP_RP:
        """Create the native reference-point-to-reference-point spring."""
        values = self.default_values
        self._torchfea_SpringBetweenRPs = torchfea.loads.Spring_RP_RP(
            rp_name1=self._reference_point_name1,
            rp_name2=self._reference_point_name2,
            k=values[0],
            rest_length=None if values[1] < 0 else values[1],
        )
        return self._torchfea_SpringBetweenRPs

    def _apply_values(self, values: torch.Tensor) -> None:
        """Write stiffness and rest length to TorchFEA."""
        self._torchfea_SpringBetweenRPs.k = values[0]
        self._torchfea_SpringBetweenRPs.rest_length = values[1]


class PenaltyDoF(BaseFEAComponent):
    """Apply a quadratic penalty to one local generalized degree of freedom."""

    def __init__(self, name: str, object_name: str, local_dof_index: int, *, stiffness: float = 0.0, target: float = 0.0, object_type: str = "auto") -> None:
        super().__init__(name, default_values=(stiffness, target), target_names=(object_name,))
        self._object_name = str(object_name)
        """Name of the constrained Assembly object."""
        self._local_dof_index = int(local_dof_index)
        """Flattened degree-of-freedom index local to the target object."""
        self._object_type = str(object_type)
        """TorchFEA object-category selector for target lookup."""
        self._torchfea_PenaltyDoF: torchfea.loads.Penalty_DoF | None = None
        """Native degree-of-freedom penalty load."""

    def _create_fea_object(self) -> torchfea.loads.Penalty_DoF:
        """Create the native degree-of-freedom penalty load."""
        values = self.default_values
        self._torchfea_PenaltyDoF = torchfea.loads.Penalty_DoF(
            obj_name=self._object_name,
            s=self._local_dof_index,
            target=values[1],
            k=values[0],
            obj_type=self._object_type,
        )
        return self._torchfea_PenaltyDoF

    def _apply_values(self, values: torch.Tensor) -> None:
        """Write penalty stiffness and target value to TorchFEA."""
        self._torchfea_PenaltyDoF.k = values[0]
        self._torchfea_PenaltyDoF.target = values[1]


class Contact(BaseFEAComponent):
    """Define contact between two named Instance surface sets."""

    def __init__(self, name: str, instance_name1: str, surface_name1: str, instance_name2: str, surface_name2: str, **parameters: float) -> None:
        super().__init__(name, target_names=(instance_name1, surface_name1, instance_name2, surface_name2))
        self._instance_name1 = str(instance_name1)
        """First contact Instance name."""
        self._surface_name1 = str(surface_name1)
        """First contact surface-set name."""
        self._instance_name2 = str(instance_name2)
        """Second contact Instance name."""
        self._surface_name2 = str(surface_name2)
        """Second contact surface-set name."""
        self._parameters = {key: float(value) for key, value in parameters.items()}
        """Optional native contact penalty and search parameters."""
        self._torchfea_Contact: torchfea.loads.Contact | None = None
        """Native two-surface contact load."""

    def _create_fea_object(self) -> torchfea.loads.Contact:
        """Create the native two-surface contact load."""
        self._torchfea_Contact = torchfea.loads.Contact(
            instance_name1=self._instance_name1,
            instance_name2=self._instance_name2,
            surface_name1=self._surface_name1,
            surface_name2=self._surface_name2,
            **self._parameters,
        )
        return self._torchfea_Contact


class SelfContact(BaseFEAComponent):
    """Define self-contact on one named Instance surface set."""

    def __init__(self, name: str, instance_name: str, surface_name: str, **parameters: float) -> None:
        super().__init__(name, target_names=(instance_name, surface_name))
        self._instance_name = str(instance_name)
        """Contact Instance name."""
        self._surface_name = str(surface_name)
        """Self-contact surface-set name."""
        self._parameters = {key: float(value) for key, value in parameters.items()}
        """Optional native contact penalty and search parameters."""
        self._torchfea_SelfContact: torchfea.loads.ContactSelf | None = None
        """Native self-contact load."""

    def _create_fea_object(self) -> torchfea.loads.ContactSelf:
        """Create the native self-contact load."""
        self._torchfea_SelfContact = torchfea.loads.ContactSelf(
            instance_name=self._instance_name,
            surface_name=self._surface_name,
            **self._parameters,
        )
        return self._torchfea_SelfContact
