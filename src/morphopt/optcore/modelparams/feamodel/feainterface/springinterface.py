import torch

from torchfea import FEAController
from .basefeainterface import BaseFEAInterface
from torchfea.model.loads.spring import Spring_RP_Point, Spring_RP_RP
from torchfea.model.loads import Penalty_DoF


class SpringToGroundInterface(BaseFEAInterface):
    """
    Nonlinear axial spring connecting a reference point to a fixed ground point.
    Values order (5 floats): [k, L0, Px, Py, Pz]
            k: stiffness
            L0: rest length
            P*: ground point coordinates
    """

    def __init__(self, rp_name: str) -> None:
        self.rp_name = rp_name
        super().__init__()

    @property
    def num_values(self) -> int:
        return 5

    # Convenience accessors
    @property
    def k(self) -> float:
        return float(self._values[0])

    @k.setter
    def k(self, value: float) -> None:
        self._values[0] = float(value)

    @property
    def rest_length(self) -> float:
        return float(self._values[1])

    @rest_length.setter
    def rest_length(self, value: float) -> None:
        self._values[1] = float(value)

    @property
    def point(self) -> list[float]:
        return [float(self._values[2]), float(self._values[3]), float(self._values[4])]

    @point.setter
    def point(self, value: list[float]) -> None:
        if len(value) != 3:
            raise ValueError("point must be a list of 3 floats [x, y, z].")
        self._values[2:5] = [float(value[0]), float(value[1]), float(value[2])]

    def modify_fea(self, fe: FEAController, name: str) -> None:
        loadobj = Spring_RP_Point(rp_name=self.rp_name, point=self.point, k=self.k, rest_length=self.rest_length)
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        loadobj: Spring_RP_Point = fe.assembly.get_load(name)
        loadobj.k = self.k
        loadobj.rest_length = self.rest_length
        loadobj.point = self.point


class SpringBetweenRPsInterface(BaseFEAInterface):
    """
    Nonlinear axial spring connecting two reference points (RP-RP).

    Values order (2 floats): [k, L0]
      - k: stiffness
      - L0: rest length
    """

    def __init__(self, rp_name1: str, rp_name2: str) -> None:
        self.rp_name1 = rp_name1
        self.rp_name2 = rp_name2
        super().__init__()

    @property
    def num_values(self) -> int:
        return 2

    @property
    def k(self) -> float:
        return float(self._values[0])

    @k.setter
    def k(self, value: float) -> None:
        self._values[0] = float(value)

    @property
    def rest_length(self) -> float:
        return float(self._values[1])

    @rest_length.setter
    def rest_length(self, value: float) -> None:
        self._values[1] = float(value)

    def modify_fea(self, fe: FEAController, name: str) -> None:
        loadobj = Spring_RP_RP(rp_name1=self.rp_name1, rp_name2=self.rp_name2, k=self.k, rest_length=self.rest_length)
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        loadobj: Spring_RP_RP = fe.assembly.get_load(name)
        loadobj.k = self.k
        loadobj.rest_length = self.rest_length


class PenaltyDoFInterface(BaseFEAInterface):
    """
    Quadratic penalty load on a single DoF of an object's RGC segment.

    Values order (2 floats): [k, target]
      - k: penalty coefficient
      - target: desired value of the selected DoF
    """

    def __init__(self, obj_name: str, s: int, obj_type: str = "auto") -> None:
        self.obj_name = obj_name
        self.s = int(s)
        self.obj_type = obj_type
        super().__init__()

    @property
    def num_values(self) -> int:
        return 2

    @property
    def k(self) -> float:
        return float(self._values[0])

    @k.setter
    def k(self, value: float) -> None:
        self._values[0] = float(value)

    @property
    def target(self) -> float:
        return float(self._values[1])

    @target.setter
    def target(self, value: float) -> None:
        self._values[1] = float(value)

    def modify_fea(self, fe: FEAController, name: str) -> None:
        loadobj = Penalty_DoF(
            obj_name=self.obj_name,
            s=self.s,
            target=self.target,
            k=self.k,
            obj_type=self.obj_type,
        )
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        loadobj: Penalty_DoF = fe.assembly.get_load(name)
        loadobj.k = self.k
        loadobj.target = self.target
