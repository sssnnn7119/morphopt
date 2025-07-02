
import torch
from .SurfaceInterface.BaseInterface import BaseInterface
from ..base_params import BaseParams
from ... import GLOBAL

class Surfaces(BaseParams):
    """
    Class to handle the surfaces of the morphable model.
    """
    from .SurfaceInterface.CSInterface import CsInterface as CS
    from .SurfaceInterface.BSPInterface import BspInterface as BSP
    from .SurfaceInterface.CPGEOSphereInterface import CPGEOSurfaceInterface as CPGEO

    def __init__(self, max_step_length: list[float], reinitialize_per_iter: int = 1, *args, **kwargs) -> None:
        """
        Initialize the Surfaces class.

        Parameters:
            thickness (list[float]): The minimum distance between the surfaces.
        """

        self.surface_list: list[BaseInterface] = []
        """
        List of surface objects.
        """
        
        self._max_step_length: list[float] = max_step_length
        """
        The maximum step length for each surface in the optimization process.
        """
        
        self.if_update = []
        """
        A list indicating whether each surface needs to be updated.
        True means the surface needs to be updated, False means it does not.
        """

        self.reinitialize_per_iter = reinitialize_per_iter
        """
        The number of iterations after which the surfaces are reinitialized.
        This is useful for ensuring that the surfaces are updated periodically during the optimization process.
        """
    
    def initialize(self, iteration: int):
        """
        Initialize the surfaces for the optimization process.
            determine which surfaces need to be updated.
            initialize the surfaces.
        """
        
        self.if_update = [True for _ in range(self.num_surface)]
        if iteration % self.reinitialize_per_iter == 0:
            for i in range(self.num_surface):
                self.surface_list[i].initialize()

    def add_surface(self, surface_new: BaseInterface) -> None:
        """
        Add a surface object to the list.

        Parameters
        ----------
        surface : Surface
            The surface object to be added.
        """
        self.surface_list.append(surface_new)
        
    @property
    def num_surface(self) -> int:
        """
        Get the number of surfaces.

        Returns:
            length (int) :The number of surfaces.
        """
        return len(self.surface_list)
    
    def get_geometry_values(self) -> list[torch.Tensor]:
        """
        Get the geometry values of the surfaces.

        Returns:
            list[tuple]: A tuple containing the geometry values of the surfaces.
                - r (list[torch.Tensor]): The point coordinates of the surfaces.
                - rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
                - rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
        """
        
        rlist = [self.surface_list[i].get_geometry_values() for i in range(self.num_surface)]
        r = [rlist[i][0] for i in range(self.num_surface)]
        rdu = [rlist[i][1] for i in range(self.num_surface)]
        rdu2 = [rlist[i][2] for i in range(self.num_surface)]
        return r, rdu, rdu2
    
    def get_penalty_fairness(self, weight: list[torch.Tensor], r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor]) -> torch.Tensor:
        """
        Get the penalty fairness of the surfaces.

        Parameters:
            weight (list[torch.Tensor]): The weights for the points in the optimization process.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.

        Returns:
            torch.Tensor: The penalty fairness of the surfaces.
        """
        
        penalty = []
        for i in range(self.num_surface):
            penalty.append(self.surface_list[i].get_penalty_fairness(weight[i], r[i], rdu[i], rdu2[i]))
        
        return penalty
    
    def get_points_weight(self) -> list[torch.Tensor]:
        """
        Get the weights for the points in the optimization process.

        Returns:
            list[torch.Tensor]: The weights for the points in the optimization process.
        """
        
        weight = [self.surface_list[i].get_points_weight() for i in range(self.num_surface)]
        return weight
    
    def get_parameters(self) -> torch.Tensor:
        """
        Get the current variables of the surfaces.

        Returns:
            list[torch.Tensor]: The current variables of the surfaces.
        """
        
        xlist = []
        for i in range(self.num_surface):
            if not self.if_update[i]:
                xlist.append(torch.zeros([0]))
                continue
            xlist.append(self.surface_list[i].get_surface_parameters().flatten().detach().clone())
        return xlist
    
    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the current variables of the surfaces.

        Parameters:
            xlist (list[torch.Tensor]): The new variables for the surfaces.
        """
        for i in range(self.num_surface):
            if not self.if_update[i]:
                continue
            self.surface_list[i].set_surface_parameters(xlist[i].detach().clone())
            
    def get_variables(self) -> torch.Tensor:
        """
        Get the current variables of the surfaces.

        Returns:
            torch.Tensor: The current variables of the surfaces.
        """
        xlist = self.get_parameters()
        x_flatten = torch.cat([torch.randn_like(xlist[i].flatten())*1e-6 for i in range(len(xlist))])
        return x_flatten
    
    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the surfaces with the new variables.

        Parameters:
            xlist_change (torch.Tensor): The change of variables for the surfaces.
        """
        
        x_change_list = []
        start = 0
        for i in range(self.num_surface):
            
            if self.if_update[i]:
                end = start + self.surface_list[i].num_variables
            else:
                end = start + 0
            x_change_list.append(x_change[start:end].reshape([3, -1]))
            start = end

        for i in range(self.num_surface):
            
            if not self.if_update[i]:
                continue
            
            r = x_change_list[i].norm(dim=0)
            
            dx = 2/torch.pi * torch.atan(r) * x_change_list[i] / (r + 1e-15) * self._max_step_length[i]
            
            self.surface_list[i].update_variables(dx)

    def save(self, filepath):
        for i in range(self.num_surface):
            self.surface_list[i].save(filepath + '/Surface-%d_iter-%d' %
                              (i, GLOBAL.History.iteration))

    def load(self, filepath, iteration):
        for i in range(self.num_surface):
            self.surface_list[i].load(filepath + '/Surface-%d_iter-%d' %
                              (i, iteration))
            # self.surface_list[i].initialize()
            
    def plot(self):
        for sf in range(self.num_surface):
            if sf == 0:
                alpha = 0.6
            else:
                alpha = 1
            self.surface_list[sf].plot(alpha=alpha, color=(40.0 / 255, 120.0 / 255, 181.0 / 255))

    def save_figure(self, filepath):
        from mayavi import mlab

        fig = mlab.figure(bgcolor=(1, 1, 1), size=(800, 800))
        fig.scene.parallel_projection = True

        self.plot()
        
        # Get all points to determine bounding box
        all_points = []
        for i in range(self.num_surface):
            r, _, _ = self.surface_list[i].get_geometry_values()
            all_points.append(r)

        all_points = torch.cat(all_points, dim=1)
        x_min, x_max = all_points[0].min().item(), all_points[0].max().item()
        y_min, y_max = all_points[1].min().item(), all_points[1].max().item()
        z_min, z_max = all_points[2].min().item(), all_points[2].max().item()

        # Add some padding to the bounds
        padding = 0.05 * max(x_max-x_min, y_max-y_min, z_max-z_min)
        axes = mlab.axes(xlabel='X', ylabel='Y', zlabel='Z', 
                        color=(0, 0, 0),
                        extent=[x_min-padding, x_max+padding, 
                               y_min-padding, y_max+padding, 
                               z_min-padding, z_max+padding])
        axes.label_text_property.color = (0, 0, 0)  # Set text color to black
        axes.axes.property.color = (0, 0, 0)       # Set axes lines color to black
        
        mlab.view(azimuth=210, elevation=70, distance=300)
        mlab.savefig(filepath + '%d.jpg'%GLOBAL.History.iteration)
        mlab.close()

    def export_data(self, filepath) -> list[str]:
        name = []
        for i in range(self.num_surface):
            surf_name0 = '__surface-%d' % i
            name_now = self.surface_list[i].output_data(path_output=filepath, name_output=surf_name0, flip=(i!=0))
            name.append(name_now)

        return name