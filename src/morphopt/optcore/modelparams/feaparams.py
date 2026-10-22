import torchfea
from torchfea import FEAController

from ...constants import CONSTANT
from .baseparam import BaseParams


class FEAParams(BaseParams):
    """
    Class to handle the loads in the model.
    """

    from .fea import (
        BodyForce,
        BoundaryCondition,
        ReferencePointBoundaryCondition,
        ConcentratedForce,
        ConcentratedMoment,
        Contact,
        SelfContact,
        Couple,
        PenaltyDoF,
        Pressure,
        ReferencePoint,
        SpringBetweenRPs,
        SpringToGround,
    )

    def __init__(self):
        """
        Initialize the Loads class.

        Args:
            fea_mesh_order (int): The FE mesh order used by the analysis.
        """
        super().__init__()

        self.fea_steps_params: dict[str, dict[str, list[float]]] = {}
        """Named load cases in registration order."""

    def define_steps(self):
        """Configure the amplitude of every load in every load step."""

    def initialize(self, *args: object, **kwargs: object) -> None:
        """Register this model's loads and load steps."""
        super().initialize(*args, **kwargs)
        if not self.fea_steps_params:
            self.define_steps()

    def add_step(self, name: str, values: dict[str, list[float]] | None = None) -> None:
        """Register a named load case in execution order."""
        if not isinstance(name, str) or not name.strip() or any(char in name for char in ("/", "\\", "\0")):
            raise ValueError("A load case requires a nonempty string name.")
        if name in self.fea_steps_params:
            raise ValueError(f"Duplicate load case: {name!r}")
        self.fea_steps_params[name] = {
            key: interface._values.copy() for key, interface in self.interfaces.items()
        }
        for load, amplitudes in (values or {}).items():
            self.set_step_params(name, load, amplitudes)

    def set_step_params(self, step_name: str, load_name: str, values: list[float]) -> None:
        """Assign load parameters to a registered named case."""
        if load_name not in self.interfaces:
            raise KeyError(f"Unknown load: {load_name!r}")
        self.fea_steps_params[step_name][load_name] = list(values)

    @property
    def num_load_steps(self) -> int:
        """
        Get the number of load steps.

        Returns:
            int: The number of load steps.
        """
        return len(self.fea_steps_params)

    def create_fea(self, assembly: torchfea.Assembly) -> FEAController:
        """
        Create an FEAController instance from the given FEA_INP file and add load interfaces
        Args:
            assembly (torchfea.Assembly): The FEA assembly.
        Returns:
            FEAController: The created FEAController instance with load interfaces added.
        """

        # get the FEA model

        fe = torchfea.FEAController()
        fe.assembly = assembly
        fe.solver = torchfea.solver.StaticImplicitSolver(
            tol_error=CONSTANT.KERNEL.SOLVER.STATIC_TOLERANCE_ERROR
        )

        # Add fea features
        for name, interface in self.interfaces.items():
            interface.modify_fea(fe, name)

        return fe

    def process_fea(self, fe: FEAController, step_name: str) -> None:
        """
        Process the FEA controller to update load-related information.

        Args:
            fe (FEAController): The FEA controller instance.
            step_name (str): The registered load-case name.
        """
        load_step_now = self.fea_steps_params[step_name]
        for name, load_interface in self.interfaces.items():
            load_interface._values = load_step_now[name]
            load_interface.apply_fea_value(fe, name)
