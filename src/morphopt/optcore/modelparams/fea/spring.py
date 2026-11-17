from torchfea import FEAController
from torchfea.model.loads import Penalty_DoF
from torchfea.model.loads.spring import Spring_RP_Point, Spring_RP_RP

from .base_component import BaseFEAComponent


class SpringToGround(BaseFEAComponent):
    """
    Nonlinear axial spring connecting a reference point to a fixed ground point.
    Values order (5 floats): [k, L0, Px, Py, Pz]
            k: stiffness
            L0: rest length
            P*: ground point coordinates
    """

    def __init__(self, rp_name: str) -> None:
        """Initialize SpringToGround and its configuration state.

        Args:
            rp_name (str): Registered reference-point name.
        """
        self.rp_name = rp_name
        super().__init__()

    @property
    def num_values(self) -> int:
        """Return the number of load parameters supplied by each load case.

        Returns:
            int: Number of scalar load-case parameters exposed by this component.
        """
        return 5

    # Convenience accessors
    @property
    def k(self) -> float:
        """Return the spring stiffness coefficient.

        Returns:
            float: The spring stiffness coefficient.
        """
        return float(self._values[0])

    @k.setter
    def k(self, value: float) -> None:
        """Set the spring stiffness coefficient.

        Args:
            value (float): New spring stiffness coefficient.
        """
        self._values[0] = float(value)

    @property
    def rest_length(self) -> float:
        """Return the undeformed spring length in model length units.

        Returns:
            float: The undeformed spring length in model length units.
        """
        return float(self._values[1])

    @rest_length.setter
    def rest_length(self, value: float) -> None:
        """Set the undeformed spring length in model length units.

        Args:
            value (float): New undeformed spring length in model length units.
        """
        self._values[1] = float(value)

    @property
    def point(self) -> list[float]:
        """Return the ground-anchor coordinates [x, y, z] in model length units.

        Returns:
            list[float]: The ground-anchor coordinates [x, y, z] in model length units.
        """
        return [float(self._values[2]), float(self._values[3]), float(self._values[4])]

    @point.setter
    def point(self, value: list[float]) -> None:
        """Set the ground-anchor coordinates [x, y, z] in model length units.

        Args:
            value (list[float]): New ground-anchor coordinates [x, y, z] in model length units.
        """
        if len(value) != 3:
            raise ValueError("point must be a list of 3 floats [x, y, z].")
        self._values[2:5] = [float(value[0]), float(value[1]), float(value[2])]

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        loadobj = Spring_RP_Point(
            rp_name=self.rp_name,
            point=self.point,
            k=self.k,
            rest_length=self.rest_length,
        )
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """Apply this load case's parameter values to the registered FE component.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        loadobj: Spring_RP_Point = fe.assembly.get_load(name)
        loadobj.k = self.k
        loadobj.rest_length = self.rest_length
        loadobj.point = self.point


class SpringBetweenRPs(BaseFEAComponent):
    """
    Nonlinear axial spring connecting two reference points (RP-RP).

    Values order (2 floats): [k, L0]
      - k: stiffness
      - L0: rest length
    """

    def __init__(self, rp_name1: str, rp_name2: str) -> None:
        """Initialize SpringBetweenRPs and its configuration state.

        Args:
            rp_name1 (str): Registered reference-point name at the first spring endpoint.
            rp_name2 (str): Registered reference-point name at the second spring endpoint.
        """
        self.rp_name1 = rp_name1
        self.rp_name2 = rp_name2
        super().__init__()

    @property
    def num_values(self) -> int:
        """Return the number of load parameters supplied by each load case.

        Returns:
            int: Number of scalar load-case parameters exposed by this component.
        """
        return 2

    @property
    def k(self) -> float:
        """Return the spring stiffness coefficient.

        Returns:
            float: The spring stiffness coefficient.
        """
        return float(self._values[0])

    @k.setter
    def k(self, value: float) -> None:
        """Set the spring stiffness coefficient.

        Args:
            value (float): New spring stiffness coefficient.
        """
        self._values[0] = float(value)

    @property
    def rest_length(self) -> float:
        """Return the undeformed spring length in model length units.

        Returns:
            float: The undeformed spring length in model length units.
        """
        return float(self._values[1])

    @rest_length.setter
    def rest_length(self, value: float) -> None:
        """Set the undeformed spring length in model length units.

        Args:
            value (float): New undeformed spring length in model length units.
        """
        self._values[1] = float(value)

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        loadobj = Spring_RP_RP(
            rp_name1=self.rp_name1,
            rp_name2=self.rp_name2,
            k=self.k,
            rest_length=self.rest_length,
        )
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """Apply this load case's parameter values to the registered FE component.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        loadobj: Spring_RP_RP = fe.assembly.get_load(name)
        loadobj.k = self.k
        loadobj.rest_length = self.rest_length


class PenaltyDoF(BaseFEAComponent):
    """
    Quadratic penalty load on a single DoF of an object's RGC segment.

    Values order (2 floats): [k, target]
      - k: penalty coefficient
      - target: desired value of the selected DoF
    """

    def __init__(self, obj_name: str, s: int, obj_type: str = "auto") -> None:
        """Initialize PenaltyDoF and its configuration state.

        Args:
            obj_name (str): Registered name of the objective or penalty term.
            s (int): Design-variable displacement used in the curvature update.
            obj_type (str): Expected interface class used to validate the supplied objective.
        """
        self.obj_name = obj_name
        self.s = int(s)
        self.obj_type = obj_type
        super().__init__()

    @property
    def num_values(self) -> int:
        """Return the number of load parameters supplied by each load case.

        Returns:
            int: Number of scalar load-case parameters exposed by this component.
        """
        return 2

    @property
    def k(self) -> float:
        """Return the penalty coefficient applied to the selected degree of freedom.

        Returns:
            float: The penalty coefficient applied to the selected degree of freedom.
        """
        return float(self._values[0])

    @k.setter
    def k(self, value: float) -> None:
        """Set the penalty coefficient applied to the selected degree of freedom.

        Args:
            value (float): New penalty coefficient applied to the selected degree of freedom.
        """
        self._values[0] = float(value)

    @property
    def target(self) -> float:
        """Return the prescribed generalized displacement of the constrained degree of freedom.

        Returns:
            float: The prescribed generalized displacement of the constrained degree of freedom.
        """
        return float(self._values[1])

    @target.setter
    def target(self, value: float) -> None:
        """Set the prescribed generalized displacement of the constrained degree of freedom.

        Args:
            value (float): New prescribed generalized displacement of the constrained degree of
                freedom.
        """
        self._values[1] = float(value)

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        loadobj = Penalty_DoF(
            obj_name=self.obj_name,
            s=self.s,
            target=self.target,
            k=self.k,
            obj_type=self.obj_type,
        )
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """Apply this load case's parameter values to the registered FE component.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        loadobj: Penalty_DoF = fe.assembly.get_load(name)
        loadobj.k = self.k
        loadobj.target = self.target
