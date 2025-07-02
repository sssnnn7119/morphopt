
import torch
from .BaseObj import BaseObj
from ....modelparams import Loads

class SensitivityPressure(BaseObj):
    """
    Class for the sensitivity objective function in MorphOpt.
    This class is used to calculate the sensitivity of the pressure distribution on the surface.
    """

    def __init__(self, loads: Loads) -> None:
        """
        Initialize the SensitivityPressure class with the given parameters.

        Parameters:
            loads (Loads): The loads object that contains the pressure values.
            U_dim (list[int]): The dimensions of the interest for the optimization problem.
        """
        self.pressure0: torch.Tensor = None
        """
        pressure0: The initial pressure values.
        """

        self.sensitivity: torch.Tensor = None
        """
        sensitivity: The sensitivity of the pressure distribution on the surface.
        """

        self.loads: Loads = loads
        """ 
        Loads: An instance of the Loads class from the ModelParams module.
        """


    def initialize(self, sensitivity: torch.Tensor) -> None:
        self.pressure0 = self.loads.pressure.get_pressure().detach().clone()
        self.sensitivity = sensitivity
        
    
    def __call__(self):

        pressure_now = self.loads.pressure.get_pressure()

        delta_pressure = pressure_now - self.pressure0
        
        objective = (self.sensitivity[:, :delta_pressure.shape[1]] * delta_pressure)

        return objective.sum()
    
class BoundaryPressure(BaseObj):
    """
    Class for the boundary pressure objective function in MorphOpt.
    This class is used to calculate the boundary pressure distribution on the surface.
    """

    def __init__(self, loads: Loads, p_max: float, p_min: float) -> None:
        """
        Initialize the BoundaryPressure class with the given parameters.

        Parameters:
            loads (Loads): The loads object that contains the pressure values.
            U_dim (list[int]): The dimensions of the interest for the optimization problem.
        """
        self.loads: Loads = loads
        """
        Loads: An instance of the Loads class from the ModelParams module.
        """
                
        self._thre = 0.001
        """
        thre: The threshold value for the barrier function.
        """
        
        self.p_max: float = p_max - self._thre
        """
        p_max: The maximum pressure value.
        """
        
        self.p_min: float = p_min + self._thre
        """
        p_min: The minimum pressure value.
        """


    def __call__(self) -> torch.Tensor:
        """
        Calculate the boundary pressure distribution on the surface.

        Parameters:
            C (torch.Tensor): The pressure distribution on the surface.

        Returns:
            torch.Tensor: The boundary pressure distribution on the surface.
        """
        
        pressure_now = self.loads.pressure.get_pressure()
        
        loss = torch.zeros(1, device=pressure_now.device, dtype=pressure_now.dtype)
        
        loss_max, ind_max = self.barrier_function(pressure_now - self.p_max, self._thre, 0., 3)
        loss_min, ind_min = self.barrier_function(self.p_min - pressure_now, self._thre, 0., 3)
        
        if len(ind_max) > 0:
            loss += loss_max.sum()
        if len(ind_min) > 0:
            loss += loss_min.sum()
            
        return loss