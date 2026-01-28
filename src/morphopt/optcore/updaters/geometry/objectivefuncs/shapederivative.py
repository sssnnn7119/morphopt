

from scipy import interpolate
import torch
from .basefuncs import BaseConstraints
import morphopt

class ShapeDerivativeDisplacement(BaseConstraints):
    """
    Shape derivative for contact forces.
    """

    def __init__(self):

        super().__init__()

        self._r0: list[torch.Tensor] = []
        """
        Initial reference configuration.
        """

    def initialize(self, r0: list[torch.Tensor], *args, **kwargs):

        objfun = morphopt.controller.objfun
        fe = objfun.fe

        self._r0 = [r0[i].detach().clone() for i in range(len(r0))]

        ins = fe.assembly.get_instance('final_model')
        part = fe.assembly.get_part('final_model')
        grad_pos = torch.zeros_like(ins.nodes)

        def closure_work(nodes_diff: torch.Tensor):
            nodes0 = part.nodes
            part.nodes = nodes_diff
            fe.initialize()

            # compute the sensitivity of the displacement
            work = objfun.get_objective().to(part.nodes.device)
            for i in range(len(objfun.U)):
                GC0 = objfun.U[i].to(part.nodes.device)
                fe.assembly.GC = GC0
                fe.assembly.RGC = fe.assembly._GC2RGC(GC0)
                morphopt.controller.params.feamodel.process_fea(fe=fe, step_index=i)
                
                R = fe.assembly.assemble_Stiffness_Matrix(GC=GC0)[0]
                ADJu = objfun.ADJu[i].to(part.nodes.device)
                work = work + (R*ADJu).sum()
            part.nodes = nodes0
            fe.initialize()
            return work
        grad_pos += torch.autograd.functional.jacobian(closure_work, part.nodes.detach().clone())

        i=0

        interpolate_points = self._get_interpolate_points()

        self.sensitivity = self._sensitivity_interpolation(Ldot=grad_pos, points_request=part.nodes, interpolated_points=interpolate_points)

    
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

        for i in range(len(self.sensitivity)):
            # r[i], self._r0[i], self.sensitivity[i] are all [p, 3]
            # Compute inner product: sum over all points and dimensions
            loss_objective += ((r[i] - self._r0[i]) * self.sensitivity[i]).sum()

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
