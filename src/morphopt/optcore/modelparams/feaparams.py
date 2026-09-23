import torchfea
from torchfea import FEAController

from .baseparam import BaseParams


class FEAParams(BaseParams):
    """
    Class to handle the loads in the model.
    """

    from .feainterface import (
        BodyforceInterface,
        BoundaryConditionInterface,
        BoundaryConditionRPInterface,
        ConcentratedForceInterface,
        ConcentratedMomentInterface,
        ContactInterface,
        ContactSelfInterface,
        CoupleInterface,
        PenaltyDoFInterface,
        PressureInterface,
        ReferencePointInterface,
        SpringBetweenRPsInterface,
        SpringToGroundInterface,
    )

    def __init__(self):
        """
        Initialize the Loads class.

        Args:
            fea_mesh_order (int): The FE mesh order used by the analysis.
        """
        super().__init__()

        self.fea_steps_params: list[dict[str, list[float]]] = []
        """load_steps (list): A list to hold the load steps."""

    def define_steps(self):
        """Configure the amplitude of every load in every load step."""

    def initialize(self, *args: object, **kwargs: object) -> None:
        """Register this model's loads and load steps."""
        super().initialize(*args, **kwargs)
        if not self.fea_steps_params:
            self.define_steps()

    def set_step_num(self, num_steps: int) -> None:
        """
        Set the number of load steps.

        Args:
            num_steps (int): The number of load steps.
        """
        self.fea_steps_params = []
        for _ in range(num_steps):
            load_step = {}
            for name, load_interface in self.interfaces.items():
                load_step[name] = load_interface._values.copy()
            self.fea_steps_params.append(load_step)

    def set_step_params(
        self, step_index: int, load_name: str, values: list[float]
    ) -> None:
        """
        Set the load parameters for a specific load step.

        Args:
            step_index (int): The index of the load step.
            load_name (str): The name of the load interface.
            values (list[float]): The load parameter values.
        """
        if step_index < 0 or step_index >= len(self.fea_steps_params):
            raise IndexError("step_index out of range.")
        if load_name not in self.interfaces:
            raise KeyError(f"Load interface with name '{load_name}' does not exist.")
        self.fea_steps_params[step_index][load_name] = values

    def reinitialize(self, iteration, *args, **kwargs):
        # Sort the load interfaces and load steps parameters by their keys
        sorted_fea_interfaces = dict(sorted(self.interfaces.items()))
        sorted_fea_steps_params = [
            dict(sorted(step.items())) for step in self.fea_steps_params
        ]

        # Update the dictionaries with the sorted versions
        self.interfaces = sorted_fea_interfaces
        self.fea_steps_params = sorted_fea_steps_params
        super().reinitialize(iteration, *args, **kwargs)

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
        fe.solver = torchfea.solver.StaticImplicitSolver(tol_error=1e-7)

        # Add fea features
        for name, interface in self.interfaces.items():
            interface.modify_fea(fe, name)

        return fe

    def process_fea(self, fe: FEAController, step_index: int) -> None:
        """
        Process the FEA controller to update load-related information.

        Args:
            fe (FEAController): The FEA controller instance.
            step_index (int): The index of the load step.
        """
        load_step_now = self.fea_steps_params[step_index]
        for name, load_interface in self.interfaces.items():
            load_interface._values = load_step_now[name]
            load_interface.apply_fea_value(fe, name)
