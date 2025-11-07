

from scipy import interpolate
import torch
from .baseobjfun import BaseObj
from .... import GLOBAL

class ShapeDerivativeDirect(BaseObj):
    """
    Shape derivative for contact forces.
    """

    def __init__(self, reset_per_iter: int = 5):

        super().__init__()

        self.sensitivity: list[torch.Tensor] = []
        """
        Sensitivity of the shape derivative with respect to the contact forces.
        """

        self._r0: list[torch.Tensor] = []
        """
        Initial reference configuration.
        """

        self.scaler = None
        """
        The scaler for the objective function.
        """

        self.reset_per_iter = reset_per_iter
        """
        The number of iterations after which the scaler is reset.
        """


    def initialize(self, iter_now: int, r0: list[torch.Tensor], *args, **kwargs):

        objfun = GLOBAL.obj_fun
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
                GLOBAL.controller.params.loads.process_fea(fe=fe, step_index=i)
                
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

        self._reset_scaler(iter_now=iter_now, sensitivity=self.sensitivity)
        for i in range(len(self.sensitivity)):
            self.sensitivity[i] *= self.scaler
    
    def show_sensitivity(self, ind: int) -> None:
        """
        Show the shape sensitivity
        """

        def show_quiver3d(R: torch.Tensor, N: torch.Tensor):
            from mayavi import mlab
            r = R.detach().cpu().numpy()
            n = N.detach().cpu().numpy()
            mlab.quiver3d(r[0], r[1], r[2], n[0], n[1], n[2])

            
        from mayavi import mlab

        mlab.figure(size=(1000, 1000), bgcolor=(0, 0, 0))
        show_quiver3d(self._r0[ind].cpu(), self.sensitivity[ind].cpu())

        mlab.show()

    def __call__(self, weight, r: list[torch.Tensor], *args, **kwargs):
        loss_objective = 0.0

        for i in range(len(weight)):

            loss_objective += ((r[i] - self._r0[i]) * self.sensitivity[i]).sum()

        return loss_objective
    
    def _reset_scaler(self, iter_now: int, sensitivity: list[torch.Tensor]) -> None:
        """
        Reset the scaler for the objective function.

        Parameters:
            iter_now (int): The current iteration number.
        """
        if iter_now % self.reset_per_iter == 0 or self.scaler is None:
            # get the maximum sensitivity value
            max_sensitivity = 0
            for sensitivity_surf in sensitivity:
                max_sensitivity = max(max_sensitivity,
                                      sensitivity_surf.abs().max())
            self.scaler = 1 / max_sensitivity

        return sensitivity

    def _get_interpolate_points(self, *args, **kwargs):
        """
        Get the interpolated points for the design variables.

        Parameters:
        *args: Additional arguments.
        **kwargs: Additional keyword arguments.

        Returns:
            list[torch.Tensor]: The interpolated points for the design variables.
        """
        surfaces = GLOBAL.controller.params.surfaces
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
                    (interpolated_points[surf_index][0],
                    interpolated_points[surf_index][1],
                    interpolated_points[surf_index][2]),
                    method='nearest',
                    fill_value=0,
                    rescale=True)

                output_senNodes[-1][i] = torch.tensor((Part_B).tolist())

        return output_senNodes
