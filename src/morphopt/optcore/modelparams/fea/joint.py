"""TorchFEA penalty joints connecting two six-DoF reference points."""

from torchfea import FEAController
from torchfea.model import loads

from ....constants import CONSTANT
from .base_component import BaseFEAComponent


class _ReferencePointJoint(BaseFEAComponent):
    """Register the two endpoints and apply the common per-case joint parameters."""

    default_values = CONSTANT.KERNEL.FEA.SPHERICAL_JOINT_VALUES

    def __init__(self, rp_name1: str, rp_name2: str) -> None:
        """Connect two distinct reference points.

        Args:
            rp_name1: Reference point carrying the joint's local frame.
            rp_name2: Reference point whose relative motion is constrained.
        """
        super().__init__()
        self.rp_name1 = rp_name1
        self.rp_name2 = rp_name2
        self._values = list(self.default_values)

    @property
    def num_values(self) -> int:
        """Number of scalar joint parameters in a load case."""
        return len(self.default_values)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """Apply the penalty stiffness and initial global connection point."""
        joint = fe.assembly.get_load(name)
        joint.k = self._values[0]
        joint.connection_point = self._values[1:4]


class SphericalJoint(_ReferencePointJoint):
    """Constrain relative translation at a point and allow all relative rotations.

    Load-case values are [k, x, y, z], with positive penalty stiffness k.
    """

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Register the spherical joint with the assembly before case selection."""
        joint = loads.SphericalJoint(
            self.rp_name1, self.rp_name2,
            connection_point=self._values[1:4], k=self._values[0],
        )
        fe.assembly.add_load(joint, name)


class SingleDoFJoint(_ReferencePointJoint):
    """Allow one relative motion in RP 1's frame and penalize the other five.

    Load-case values are [k, x, y, z, tx, ty, tz, rx, ry, rz]. The final
    six entries specify a nonzero free direction, initially in global axes.
    """

    default_values = CONSTANT.KERNEL.FEA.SINGLE_DOF_JOINT_VALUES

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Register the single-DoF joint with the assembly before case selection."""
        joint = loads.SingleDoFJoint(
            self.rp_name1, self.rp_name2,
            connection_point=self._values[1:4], free_direction=self._values[4:],
            k=self._values[0],
        )
        fe.assembly.add_load(joint, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """Apply the common joint parameters and the case's free direction."""
        super().apply_fea_value(fe, name)
        fe.assembly.get_load(name).free_direction = self._values[4:]
