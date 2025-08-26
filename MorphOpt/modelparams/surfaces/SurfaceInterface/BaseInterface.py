import torch

from ..SurfaceModel.Surface_Base import Surface_Base

class BaseInterface():
    """
    Class to handle the surface of the morphable model.
    """
    
    def __init__(self):
        pass

    def __init__(self, surface: Surface_Base, symmetric: list[int] = None) -> None:
        """
        Initialize the Surface class.

        Parameters:
            surface (Surface_Base) : The surface model.
            surf_type (int) : The type of the surface.
                - 0: bspline surface
                - 1: closed surface
            symmetric (list[int]) : The symmetry of the surface.
                - 0: no symmetry
                - 1: axis symmetry
                    0: x-axis symmetry
                    1: y-axis symmetry
                    2: z-axis symmetry
        """
        
        self.model = surface
        """
        The surface model.
        """

        self.symmetric: list[int] = symmetric
        """
        the symmetry of the surface.
        # 0: no symmetry
        # 1: axis symmetry
            ## 0: x-axis symmetry
            ## 1: y-axis symmetry
            ## 2: z-axis symmetry
        """

        self.surface_out_knots: torch.Tensor
        """record the output knots of the surface"""
        self.surface_out_coo: torch.Tensor
        """record the output coordinates of the surface"""
    
    def initialize(self) -> None:
        """
        Initialize the surface.
        """
        pass

    
    @property
    def surf_type(self) -> int:
        """
        Get the type of the surface.

        Returns:
            int: The type of the surface.
                - 0: bspline surface
                - 1: closed surface
        """
        raise NotImplementedError("The surf_type property is not implemented in the BaseInterface class. Please implement it in the derived class.")
    
    def output_data(self, path_output, name_output, seed_size=-1, flip=False, ):
        """
        Output the surface data to a file.
        """
        raise NotImplementedError("The output_data method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def get_surface_parameters(self) -> torch.Tensor:
        """
        Get the design variables of the surface.

        Returns:
            torch.Tensor: The design variables of the surface.
        """
        raise NotImplementedError("The get_variables method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """
        Set the design variables of the surface.

        Parameters:
            x (torch.Tensor): The new design variables to be set.
        """
        raise NotImplementedError("The set_variables method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the surface with the new design variables.

        Parameters:
            x_change (torch.Tensor): The change of design variables to be applied.
        """

        raise NotImplementedError("The update_variables method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get the geometry values of the surface.

        Returns:
            tuple: A tuple containing the geometry values of the surface.
                - r (torch.Tensor): The point coordinates of the surface.
                - rdu (torch.Tensor): The partial derivatives of the surface.
                - rdu2 (torch.Tensor): The second partial derivatives of the surface.
        """
        raise NotImplementedError("The get_geometry_values method is not implemented in the BaseInterface class. Please implement it in the derived class.")
    
    def get_penalty_fairness(self, r: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor) -> torch.Tensor:
        """
        Get the penalty fairness of the surface.

        Returns:
            torch.Tensor: The penalty fairness of the surface.
        """
        return 0.0
    
    def get_points_weight(self) -> torch.Tensor:
        """
        Get the points weight of the surface.

        Returns:
            torch.Tensor: The points weight of the surface.
        """
        raise NotImplementedError("The get_points_weight method is not implemented in the BaseInterface class. Please implement it in the derived class.")
    
    @staticmethod
    def barrier_function(f: torch.Tensor, f_max: torch.Tensor|float, ratio: float, p: int):
        """
        Apply a barrier function to the objective function.
        
        Args:
            f (torch.Tensor): The objective function value.
            f_max (float or torch.Tensor): The maximum value of the objective function.
            ratio (float): The ratio for the barrier function.
            p (float): The exponent for the barrier function.
            
        Returns:
            index (torch.Tensor): The indices of the elements that are greater than the barrier.
            fnew (torch.Tensor): The new objective function value after applying the barrier function.
        
        """
        if type(f_max) != torch.Tensor:
            f_max = torch.tensor(f_max).repeat(f.shape)
        index = torch.where(f > f_max * ratio)[0]

        if index.numel() > 0:
            f = f[index]
            f_max = f_max[index]
            fnew = ((f - f_max * ratio) / (f_max - f_max * ratio))**(p)
        else:
            fnew = f[index]
        return index, fnew
    
    
    
    @property
    def num_variables(self) -> int:
        """
        Get the number of design variables.

        Returns:
            int: The number of design variables.
        """
        raise NotImplementedError("The num_variables property is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def save(self, filename: str) -> None:
        """
        Save the surface data to a file.

        Parameters:
            filename (str): The name of the file to save the surface data.
        """
        raise NotImplementedError("The save method is not implemented in the BaseInterface class. Please implement it in the derived class.")
    
    def load(self, filename: str) -> None:
        """
        Load the surface data from a file.

        Parameters:
            filename (str): The name of the file to load the surface data from.
        """
        raise NotImplementedError("The load method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def plot(self, alpha: float, color: tuple[float, float, float]) -> None:
        """
        Plot the surface.

        Parameters:
            alpha (float): The transparency of the surface.
            color (tuple[float, float, float]): The color of the surface.
        """
        raise NotImplementedError("The plot method is not implemented in the BaseInterface class. Please implement it in the derived class.")