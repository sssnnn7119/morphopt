from torchfea import FEAController
from torchfea.model.loads import Concentrate_Force, Moment

from .base_component import BaseFEAComponent


class ConcentratedForce(BaseFEAComponent):
    """
    Concentrated (point) force load interface.

    Applies a force vector at a reference point (RP).

    Values (list[float], length=3):
    - [0] Fx, [1] Fy, [2] Fz
    """

    def __init__(self, rp_name: str) -> None:
        """Initialize ConcentratedForce and its configuration state.

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
        return 3

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        loadobj = Concentrate_Force(rp_name=self.rp_name, force=self.force)
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """Apply this load case's parameter values to the registered FE component.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        fe.assembly.get_load(name).force = self.force

    @property
    def force(self) -> list[float]:
        """Return the Cartesian force components [Fx, Fy, Fz].

        Returns:
            list[float]: The Cartesian force components [Fx, Fy, Fz].
        """
        return self._values.copy()

    @force.setter
    def force(self, value: list[float]) -> None:
        """Set the Cartesian force components [Fx, Fy, Fz].

        Args:
            value (list[float]): New Cartesian force components [Fx, Fy, Fz].
        """
        if len(value) != 3:
            raise ValueError("force must be a list of 3 floats [Fx, Fy, Fz].")
        self._values = list(map(float, value))


class ConcentratedMoment(BaseFEAComponent):
    """
    Concentrated (point) moment load interface.

    Applies a moment vector at a reference point (RP).

    Values (list[float], length=3):
    - [0] Mx, [1] My, [2] Mz
    """

    def __init__(self, rp_name: str) -> None:
        """Initialize ConcentratedMoment and its configuration state.

        Args:
            rp_name (str): Registered reference-point name.
        """
        super().__init__()
        self.rp_name = rp_name

    @property
    def num_values(self) -> int:
        """Return the number of load parameters supplied by each load case.

        Returns:
            int: Number of scalar load-case parameters exposed by this component.
        """
        return 3

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        loadobj = Moment(rp_name=self.rp_name, moment=self.moment)
        fe.assembly.add_load(loadobj, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """Apply this load case's parameter values to the registered FE component.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        fe.assembly.get_load(name).moment = self.moment

    @property
    def moment(self) -> list[float]:
        """Return the Cartesian moment components [Mx, My, Mz].

        Returns:
            list[float]: The Cartesian moment components [Mx, My, Mz].
        """
        return self._values.copy()

    @moment.setter
    def moment(self, value: list[float]) -> None:
        """Set the Cartesian moment components [Mx, My, Mz].

        Args:
            value (list[float]): New Cartesian moment components [Mx, My, Mz].
        """
        if len(value) != 3:
            raise ValueError("moment must be a list of 3 floats [Mx, My, Mz].")
        self._values = list(map(float, value))
