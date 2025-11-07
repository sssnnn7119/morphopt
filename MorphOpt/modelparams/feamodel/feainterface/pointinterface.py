import numpy as np
import torch

from FEA import FEAController
from .basefeainterface import BaseFEAInterface
from FEA.assemble.loads import Concentrate_Force, Moment


class ConcentratedForceInterface(BaseFEAInterface):
    """
    Concentrated (point) force load interface.

    Applies a force vector at a reference point (RP).

    Values (list[float], length=3):
    - [0] Fx, [1] Fy, [2] Fz
    """

    def __init__(self, rp_name: str) -> None:
        self.rp_name = rp_name
        super().__init__()

    @property
    def num_values(self) -> int:
        return 3

    def modify_fea(self, fe: FEAController, name: str) -> None:
        loadobj = Concentrate_Force(rp_name=self.rp_name, force=self.force)
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        fe.assembly.get_load(name).force = self.force

    @property
    def force(self) -> list[float]:
        return self._values.copy()

    @force.setter
    def force(self, value: list[float]) -> None:
        if len(value) != 3:
            raise ValueError("force must be a list of 3 floats [Fx, Fy, Fz].")
        self._values = list(map(float, value))


class ConcentratedMomentInterface(BaseFEAInterface):
    """
    Concentrated (point) moment load interface.

    Applies a moment vector at a reference point (RP).

    Values (list[float], length=3):
    - [0] Mx, [1] My, [2] Mz
    """

    def __init__(self, rp_name: str) -> None:
        super().__init__()
        self.rp_name = rp_name

    @property
    def num_values(self) -> int:
        return 3

    def modify_fea(self, fe: FEAController, name: str) -> None:
        loadobj = Moment(rp_name=self.rp_name, moment=self.moment)
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        fe.assembly.get_load(name).moment = self.moment

    @property
    def moment(self) -> list[float]:
        return self._values.copy()

    @moment.setter
    def moment(self, value: list[float]) -> None:
        if len(value) != 3:
            raise ValueError("moment must be a list of 3 floats [Mx, My, Mz].")
        self._values = list(map(float, value))

