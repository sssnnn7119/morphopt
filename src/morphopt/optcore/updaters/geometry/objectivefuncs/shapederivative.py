
from scipy import interpolate
import numpy as np
import torch
from .basefuncs import BaseObjective
import morphopt

class ShapeDerivative(BaseObjective):
    """
    Shape derivative for contact forces.
    """

    def __init__(self):

        super().__init__()

        self._cp0: list[torch.Tensor] = []
        """
        Initial control points of the surfaces, used for computing the shape derivative as the inner product of the change in control points and the sensitivity.
        """

        self.gradient: list[torch.Tensor] = []
        """Gradient of the shape derivative with respect to the control points, computed in the initialize function.
        """

        self.factor: float
        """A factor to scale the shape derivative, can be set in the initialize function.
        """

    def initialize(self, gradient: torch.Tensor, r0: list[torch.Tensor], *args, **kwargs):


        interpolate_points = self._get_interpolate_points()


        geoparams = morphopt.controller.params.geometry
        sflist: list[morphopt.GeometryParams.CpBasedInterface] = geoparams.surface_list

        self._cp0 = []
        ptidx = 0
        self.gradient = []
        for sf_idx in range(geoparams.num_surface):
            cp0_sf = sflist[sf_idx]._cps.detach().clone().reshape(-1, 3)
            self._cp0.append(cp0_sf)
            self.gradient.append(gradient[ptidx:ptidx + cp0_sf.numel()].reshape_as(cp0_sf))
            ptidx += cp0_sf.numel()

        self.sensitivity = self._sensitivity_interpolation(Ldot=gradient.reshape([-1, 3]), 
                                                           points_request=torch.cat(self._cp0, dim=0).reshape([-1, 3]),
                                                           interpolated_points=interpolate_points)

        self.factor = 1 / (gradient.abs().max() + 1e-20)
    def show_sensitivity(self, ind: int) -> None:
        """
        Show the shape sensitivity
        """

        import pyvista as pv
        import numpy as np

        plotter = pv.Plotter(window_size=(1000, 1000))
        plotter.set_background('white')

        r = self._r0[ind].detach().cpu().numpy()
        n = self.sensitivity[ind].detach().cpu().numpy()

        # r and n are [N, 3]
        points = r
        vectors = n
        
        # Debug: print statistics
        print(f"Points shape: {points.shape}")
        print(f"Vectors shape: {vectors.shape}")
        print(f"Vector magnitude range: [{np.linalg.norm(vectors, axis=1).min():.6e}, {np.linalg.norm(vectors, axis=1).max():.6e}]")
        
        # Filter out zero vectors
        vector_norms = np.linalg.norm(vectors, axis=1)
        valid_mask = vector_norms > 1e-10
        
        if valid_mask.sum() == 0:
            print("Warning: All sensitivity vectors are zero!")
            return
        
        points_filtered = points[valid_mask]
        vectors_filtered = vectors[valid_mask]
        
        # Auto-scale magnitude based on model size
        model_size = np.max(points_filtered.max(axis=0) - points_filtered.min(axis=0))
        vector_mag = np.linalg.norm(vectors_filtered, axis=1).mean()
        mag_scale = model_size / vector_mag * 0.01  # Scale to 1% of model size
        
        print(f"Using {valid_mask.sum()} non-zero vectors out of {len(valid_mask)}")
        print(f"Auto-scaled magnitude: {mag_scale:.6e}")
        
        # Add surface mesh for context
        plotter.add_points(points_filtered, color='blue', point_size=5, render_points_as_spheres=True)
        
        # Add arrows with auto-scaled magnitude
        plotter.add_arrows(points_filtered, vectors_filtered, mag=mag_scale, color='red')

        plotter.show_axes()
        plotter.show()

    def __call__(self, r: list[torch.Tensor], *args, **kwargs):
        loss_objective = 0.0

        surflist: list[morphopt.GeometryParams.CpBasedInterface] = morphopt.controller.params.geometry.surface_list

        for i in range(len(surflist)):
            if self.if_update is not None and not self.if_update[i]:
                continue
            # r[i], self._r0[i], self.sensitivity[i] are all [p, 3]
            # Compute inner product: sum over all points and dimensions
            loss_objective += ((surflist[i]._cps - self._cp0[i]) * self.gradient[i]).sum() * self.factor

        return loss_objective


    def _get_interpolate_points(self, *args, **kwargs):
        """
        Get the interpolated points for the design variables.

        Parameters:
        *args: Additional arguments.
        **kwargs: Additional keyword arguments.

        Returns:
            list[torch.Tensor]: The interpolated points for the design variables.
        """
        surfaces = morphopt.controller.params.geometry
        r0 = surfaces.get_geometry_values()[0]
        interpolated_points = []
        for sf in range(surfaces.num_surface):
            interpolated_points.append(r0[sf].cpu().numpy())
        return interpolated_points
    
    def _sensitivity_interpolation(
            self, Ldot: torch.Tensor, points_request: torch.Tensor,
            interpolated_points: list[torch.Tensor]) -> list[torch.Tensor]:
        """
        Interpolate the sensitivity into the structural grids.
        
        Parameters:
            Ldot (torch.Tensor): The sensitivity values for elements gaussian points.
                [num_points, 3]
            points_request (torch.Tensor): The coordinates of the elements.
                [num_points, 3]
            interpolated_points (list[torch.Tensor]): The coordinates of the interpolation points.
                [num_surface, 3]
                
        Returns:
            list[torch.Tensor]: The interpolated sensitivity values for the structural grids.
                [num_surface, sensitivity]
        """

        # interpolate the sensitivity into the structral grids
        output_senNodes = []

        for surf_index in range(len(interpolated_points)):

            output_senNodes.append(torch.zeros(interpolated_points[surf_index].shape))

            for i in range(3):
                Part_B = interpolate.griddata(
                    points_request.reshape([-1, 3]).detach().cpu().numpy(),
                    Ldot[:, i].flatten().detach().cpu().numpy(),
                    (interpolated_points[surf_index][:, 0],
                    interpolated_points[surf_index][:, 1],
                    interpolated_points[surf_index][:, 2]),
                    method='nearest',
                    fill_value=0,
                    rescale=True)

                output_senNodes[-1][:, i] = torch.tensor((Part_B).tolist())

        return output_senNodes

