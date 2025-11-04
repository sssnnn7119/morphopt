import numpy as np
import torch

from .baseloadinterface import BaseLoadInterface
from FEA.assemble.loads import Concentrate_Force, Moment


class ConcentratedForceInterface(BaseLoadInterface):
    """
    Concentrated (point) force load interface.

    Applies a force vector at a reference point.
    """

    def __init__(self, rp_name: str) -> None:
        self.rp_name = rp_name
        super().__init__()

    @property
    def num_values(self) -> int:
        return 3

    def get_fea_load(self):
        return Concentrate_Force(rp_name=self.rp_name, force=self.force)
    
    def apply_load(self, load_fea: Concentrate_Force):
        load_fea.force = self._values

    @property
    def force(self) -> list[float]:
        return self._values.copy()

    @force.setter
    def force(self, value: list[float]) -> None:
        if len(value) != 3:
            raise ValueError("force must be a list of 3 floats [Fx, Fy, Fz].")
        self.values = list(value)


class ConcentratedMomentInterface(BaseLoadInterface):
    """
    Concentrated (point) moment load interface.

    Applies a moment vector at a reference point.
    """

    def __init__(self, rp_name: str) -> None:
        super().__init__()
        self.rp_name = rp_name

    @property
    def num_values(self) -> int:
        return 3

    def get_fea_load(self):
        return Moment(rp_name=self.rp_name, moment=self.moment)
    
    def apply_load(self, load_fea: Moment):
        load_fea.moment = self.moment

    @property
    def moment(self) -> list[float]:
        return self._values.copy()

    @moment.setter
    def moment(self, value: list[float]) -> None:
        if len(value) != 3:
            raise ValueError("moment must be a list of 3 floats [Mx, My, Mz].")
        self._values = value.copy()

