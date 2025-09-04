
from __future__ import annotations
import imp
from typing import Optional, TYPE_CHECKING

from PIL.ExifTags import Base
import pypardiso
from sympy.abc import B
from torch.nn.modules import loss

if TYPE_CHECKING:
    from MorphOpt.solvers import FE_result
    from MorphOpt.updaters import Adjoints

import FEA
from scipy import interpolate
import torch

from MorphOpt.updaters.second_derivative_element import SensitivityElement
from .BaseObj import BaseObj
from .... import GLOBAL

from FEA.loads import ContactSelf

import scipy.sparse as sp

class ShapeDerivativePneumatic(BaseObj):
    """
    Sensitivity objective function for MorphOpt.
    """

    def __init__(self, reset_per_iter: int = 5):
        """
        Initialize the Sensitivity objective function with a name.
        """
        super().__init__()
        
        self.sensitivity: list[torch.Tensor] = []
        """
        the sensivities of the surfaces.
        """
        
        self.R0: list[torch.Tensor] = []
        """
        The initial point coordinates of the surfaces.
        """
        
        self.normal0: list[torch.Tensor] = []
        """
        The normal vectors of the surfaces.
        """
        
        self.reset_per_iter = reset_per_iter
        """
        The number of iterations after which the scaler is reset.
        """

        self.scaler = None
        """
        The scaler for the objective function.
        """

    def initialize(self, iter_now: int, r0: list[torch.Tensor], rdu0: list[torch.Tensor], *args, **kwargs) -> None:
        """
        Set the sensivities of the surfaces.

        Args:
            sensivities (list[torch.Tensor]): The sensivities of the surfaces.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
        """
        
        self.R0 = [r0[i].detach().clone() for i in range(len(r0))]

        
        self.normal0 = []
        for i in range(len(r0)):
            normal_vector = torch.cross(rdu0[i][:, 1], rdu0[i][:, 0], dim=0)
            normal_vector /= normal_vector.norm(dim=0)
            self.normal0.append(normal_vector.detach().clone())

        # sensitivity analysis
        adjoint = GLOBAL.controller.updater.adjoint
        fe_result = GLOBAL.controller.solver.fe_result
        History = GLOBAL.History

        sensitivity = self._get_sensitivity(fe_result=fe_result, adjoint=adjoint)
        sensitivity = self._refine_sensitivity(iter_now=History.iteration,
                                               sensitivity=sensitivity)
                                               
        for sensitivity_surf in sensitivity:
            ind_nan = torch.isnan(sensitivity_surf.view(-1))
            sensitivity_surf.view(-1)[ind_nan] = 0

            
        # reset the scaler
        self._reset_scaler(iter_now, sensitivity=sensitivity)
        sensitivity = [
            sensitivity_surf * self.scaler for sensitivity_surf in sensitivity
        ]

        self.sensitivity = sensitivity
        
    def show_sensitivity(self, ind: int) -> None:
        """
        Show the shape sensitivity
        """

        def show_quiver3d(R: torch.Tensor, N: torch.Tensor):
            from mayavi import mlab
            r = R.detach().cpu().numpy()
            n = N.detach().cpu().numpy()
            mlab.quiver3d(r[0], r[1], r[2], n[0], n[1], n[2])
            

        r0, rdu0 = GLOBAL.controller.params.surfaces.get_geometry_values()[:2]
        interpolated_points = []
        normal_list = []
        for sf in range(GLOBAL.controller.params.surfaces.num_surface):

            normal = torch.cross(rdu0[sf][:, 1], rdu0[sf][:, 0], dim=0)

            normal = normal / torch.norm(normal, dim=0, keepdim=True)

            interpolated_points.append(
                r0[sf].cpu())
            normal_list.append(normal.cpu())
            
        from mayavi import mlab

        mlab.figure(size=(1000, 1000), bgcolor=(0, 0, 0))
        show_quiver3d(interpolated_points[ind], self.sensitivity[ind].cpu() * normal_list[ind].cpu())


        mlab.show()

    def __call__(self, weight: list[torch.Tensor], r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor]) -> float:
        """
        Call the fairness objective function.

        Args:
            weight (list[torch.Tensor]): The weights for each point.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the fairness objective function.
        """
        loss_objective = 0.0
        
        for i in range(len(weight)):

            normal_velocity = ((r[i] - self.R0[i]) * self.normal0[i]).sum(dim=0)
            loss_objective += (normal_velocity * self.sensitivity[i] *
                            weight[i]).sum()
        
        return loss_objective
    
    # region sensitivity
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
    
    def _get_sensitivity(
            self, fe_result: FE_result,
            adjoint: Adjoints) -> tuple[float, list[torch.Tensor]]:
        """
        Get the sensitivity of the design variables.

        Parameters:
            FE_result (FE_result): The result of the finite element analysis.

        Returns:
        torch.Tensor: The sensitivity of the design variables.
        """

        # Get the interpolated points for the design variables
        interpolated_points = self._get_interpolate_points()

        # Get the sensitivity of the design variables
        points_request, Ldot = self._get_shape_derivative(fe_result=fe_result,
                                                          adjoint=adjoint)

        # Interpolate the sensitivity into the structural grids
        sensitivity = self._sensitivity_interpolation(Ldot, points_request,
                                                      interpolated_points)

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
            self, Ldot: dict[str,
                             torch.Tensor], points_request: dict[str,
                                                                 torch.Tensor],
            interpolated_points: list[torch.Tensor]) -> list[torch.Tensor]:
        """
        Interpolate the sensitivity into the structural grids.
        
        Parameters:
            Ldot (dict[str, torch.Tensor]): The sensitivity values for elements gaussian points.
                [num_points, num_surface]
            points_request (dict[str, torch.Tensor]): The coordinates of the elements.
                [num_points, 3]
            interpolated_points (list[torch.Tensor]): The coordinates of the interpolation points.
                [num_surface, 3]
                
        Returns:
            list[torch.Tensor]: The interpolated sensitivity values for the structural grids.
                [num_surface, sensitivity]
        """

        # merge the origin coordinates
        Ldot = torch.cat(
            [Ldot[element_str] for element_str in points_request.keys()], dim=0)
        points_request = torch.cat(
            [points_request[element_str].reshape([-1, 3]) for element_str in points_request.keys()],
            dim=0)

        # interpolate the sensitivity into the structral grids
        output_senNodes = []
        Part_A = 0
        for surf_index in range(len(interpolated_points)):

            Part_B = interpolate.griddata(
                points_request.reshape([-1, 3]).detach().cpu().numpy(),
                Ldot[:, surf_index].flatten().detach().cpu().numpy(),
                (interpolated_points[surf_index][0],
                 interpolated_points[surf_index][1],
                 interpolated_points[surf_index][2]),
                method='nearest',
                fill_value=0,
                rescale=True)

            output_senNodes.append(torch.tensor((Part_A + Part_B).tolist()))

        return output_senNodes

    def _get_shape_derivative(
            self, fe_result: FE_result, adjoint: Adjoints
            ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Get the shape derivative of the design variables.
        
        Args:
            fe_result (FE_result): The result of the finite element analysis.
            LdU (torch.Tensor): The sensitivity of the displacement vector.
            LdUdp (torch.Tensor): The sensitivity of the Jacobian vector.
            L
        Returns:
            tuple: A tuple containing:
                - point_sensitivity dict[str, torch.Tensor]: The sensitivity of the design variables at the points.
                - Ldot dict[str, torch.Tensor]: The sensitivity of the design variables at the points.
        """
        
        device = torch.zeros(1).device
        pressure_list = fe_result.pressure_list.to(device)

        points_request = {}
        Ldot = {}

        for element_str in fe_result.fe.elems.keys():
            if element_str != 'element-sensitivity':
                continue
            elems = fe_result.fe.elems[element_str]
            element_sensitive = SensitivityElement.get_sensitivity_element(elems=elems, fe=fe_result.fe)
            

            for p in range(len(pressure_list)):
                sen_U, sen_Udp, sen_UdF = self._cal_shape_derivative_displacement_jacobian(
                    fe=fe_result.fe,
                    element_sensitive=element_sensitive,
                    pressure_list=pressure_list[p],
                    GC0=fe_result.U[p].to(device),
                    Udp0=fe_result.Udp[p].to(device),
                    UdF0=fe_result.UdF[p].to(device),
                    ADJu=adjoint.ADJu[p].to(device),
                    ADJudp=adjoint.ADJudp[p].to(device),
                    ADJu_udp=adjoint.ADJu_udp[p].to(device),
                    ADJudf=adjoint.ADJudf[p].to(device),
                    ADJu_udf=adjoint.ADJu_udf[p].to(device))

                if p == 0:
                    Ldot_now = sen_U + sen_Udp.sum(-1) + sen_UdF.sum(-1)
                else:
                    Ldot_now += sen_U + sen_Udp.sum(-1) + sen_UdF.sum(-1)

            points_request[element_str] = (element_sensitive.points_request)
            Ldot[element_str] = (Ldot_now.reshape([-1, Ldot_now.shape[-1]]))

        return points_request, Ldot

    def _refine_sensitivity(self, iter_now: int,
                            sensitivity: list[torch.Tensor]) -> list[torch.Tensor]:

        surfaces = GLOBAL.controller.params.surfaces
        for i in range(len(sensitivity)):
            # sensitivity_surf[i] *= 100
            if surfaces.surface_list[i].surf_type == 0:
                index0 = (
                    surfaces.surface_list[i].model.coordinates[0]
                    < surfaces.surface_list[i].model.interval_size[0]
                    * 3
                ) | (surfaces.surface_list[i].model.coordinates[0]
                     > 1 -
                     surfaces.surface_list[i].model.interval_size[0]
                     * 3)
                sensitivity[i].data[index0.view(-1)] = 0

        return sensitivity

    # endregion

    # region shape derivative

    def _cal_shape_derivative_displacement_jacobian(
            self, fe: FEA.Main.FEA_Main, element_sensitive: SensitivityElement,
            pressure_list: list[float], GC0: torch.Tensor, Udp0: torch.Tensor, UdF0: torch.Tensor,
            ADJu: torch.Tensor, 
            ADJudp: torch.Tensor, ADJu_udp: torch.Tensor,
            ADJudf: torch.Tensor, ADJu_udf: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        calculate the shape derivative of the design variables.
        
        Parameters:
            fe (FEA.Main.FEA_Main): The finite element analysis object.
            element_sensitive (SensitivityElement): The element sensitivity object.
            pressure_list (list[float]): The list of pressure values.
            GC0 (torch.Tensor): The displacement vector.
              [DoF]
            Udp0 (torch.Tensor): The Jacobian vector.
              [num_pressure, DoF]
            UdF0 (torch.Tensor): The derivative of the displacement vector with respect to the external force on the end-effector.
              [F, DoF]
            ADJu (torch.Tensor): The sensitivity of velocity vector.
              [DoF]
            ADJudp (torch.Tensor): The sensitivity of Jacobian vector.
              [num_pressure, DoF]
            ADJu_udp (torch.Tensor): The sensitivity of Jacobian vector_ displacement term.
                [num_pressure, DoF]
            ADJudf (torch.Tensor): The sensitivity of compliance.
                [F, DoF]
            ADJu_udf (torch.Tensor): The sensitivity of compliance_ displacement term.
                [F, DoF]

        Returns:
            sensitivity (torch.Tensor): The sensitivity of the design variables.
                [g, e, s]
        """
        num_surface = GLOBAL.controller.params.surfaces.num_surface
        num_U = UdF0.shape[0]

        # # prepare the data
        RGC = fe._GC2RGC(GC0)
        RGC = fe.refine_RGC(RGC)
        J, F, invF, Ugrad, Ugrad2, s, C = element_sensitive.sensitivity_conponent(
            RGC[0])
        invFdual = torch.einsum('geij, gekl-> geijkl', invF, invF)
        invFdual2 = invFdual - invFdual.transpose(3, 5)

        # prepare the sensitivity tensors
        sen_U = torch.zeros([J.shape[0], J.shape[1], num_surface])  # surface
        sen_Udp = torch.zeros(
            [J.shape[0], J.shape[1], num_surface, len(pressure_list)])  # surface, p
        sen_UdF = torch.zeros(
            [J.shape[0], J.shape[1], num_surface, num_U]) # surface, F


        ADJudp_gaussian: list[torch.Tensor] = []
        ADJudpGrad_gaussian: list[torch.Tensor] = []
        ADJu_udp_gaussian: list[torch.Tensor] = []
        ADJu_udpGrad_gaussian: list[torch.Tensor] = []

        ADJudf_gaussian: list[torch.Tensor] = []
        ADJudfGrad_gaussian: list[torch.Tensor] = []
        ADJu_udf_gaussian: list[torch.Tensor] = []
        ADJu_udfGrad_gaussian: list[torch.Tensor] = []

        ADJu_now = fe._GC2RGC_linear(ADJu)[0]
        ADJu_gaussian=(element_sensitive.displacement(ADJu_now))
        ADJuGrad_gaussian=(
            element_sensitive.gradient_displacement(ADJu_now))
        
        for ind_pressure in range(len(pressure_list)):
            ADJudp_now = fe._GC2RGC_linear(ADJudp[ind_pressure])[0]
            ADJudp_gaussian.append(
                element_sensitive.displacement(ADJudp_now))
            ADJudpGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJudp_now))
            
            ADJu_udp_now = fe._GC2RGC_linear(ADJu_udp[ind_pressure])[0]
            ADJu_udp_gaussian.append(
                element_sensitive.displacement(ADJu_udp_now))
            ADJu_udpGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJu_udp_now))
            
        for ind_F in range(num_U):
            ADJudf_now = fe._GC2RGC_linear(ADJudf[ind_F])[0]
            ADJudf_gaussian.append(
                element_sensitive.displacement(ADJudf_now))
            ADJudfGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJudf_now))
            
            ADJu_udf_now = fe._GC2RGC_linear(ADJu_udf[ind_F])[0]
            ADJu_udf_gaussian.append(
                element_sensitive.displacement(ADJu_udf_now))
            ADJu_udfGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJu_udf_now))
                

        # calculate the sensitivity of U
        adju = ADJu_gaussian
        adjuGrad = ADJuGrad_gaussian
        sen_U[:, :, :] = \
            torch.einsum('geij, geji->ge', s, adjuGrad).unsqueeze(-1)
        sen_U[:, :, 1:] += \
                \
            torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, J, invFdual2, adju, Ugrad2) + \
                \
            torch.einsum('s, ge, geij, geji->ges', pressure_list, J, invF, adjuGrad)

        # calculate the sensitivity of Udp
        for ind_pressure in range(len(pressure_list)):
            Udp_now = fe._GC2RGC_linear(Udp0[ind_pressure])[0]
            Ugrad_dp = element_sensitive.gradient_displacement(Udp_now)
            Ugrad2_dp = element_sensitive.gradient_2nd_displacement(Udp_now)

            sdp = torch.einsum('geijkl, gekl->geij', C, Ugrad_dp)
            Jdp = torch.einsum('ge, gelk, gekl->ge', J, invF, Ugrad_dp)
            invFdp = -torch.einsum('geik, gelj, gekl->geij', invF, invF,
                                   Ugrad_dp)
            invFdualdp = torch.einsum('geij, gemn->geijmn', invFdp, invF)
            invFdualdp = invFdualdp + invFdualdp.transpose(2, 4).transpose(
                3, 5)
            invFdual2dp = invFdualdp - invFdualdp.transpose(3, 5)

            adju = ADJu_udp_gaussian[ind_pressure]
            adjudp = ADJudp_gaussian[ind_pressure]
            adjuGrad = ADJu_udpGrad_gaussian[ind_pressure]
            adjudpGrad = ADJudpGrad_gaussian[ind_pressure]

            sen_Udp[:, :, :, ind_pressure] = \
                torch.einsum('geij, geji->ge', s, adjudpGrad).unsqueeze(-1) + \
                torch.einsum('geij, geji->ge', sdp, adjuGrad).unsqueeze(-1)

            sen_Udp[:, :, ind_pressure + 1, ind_pressure] += \
                    \
                torch.einsum('ge, geijnm, gej, gemni->ge', J, invFdual2, adju, Ugrad2) + \
                    \
                torch.einsum('ge, geij, geji->ge', J, invF, adjuGrad)

            sen_Udp[:, :, 1:, ind_pressure] += \
                    \
                torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, Jdp, invFdual2, adju, Ugrad2) + \
                torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, J, invFdual2dp, adju, Ugrad2) + \
                torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, J, invFdual2, adjudp, Ugrad2) + \
                torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, J, invFdual2, adju, Ugrad2_dp) + \
                    \
                torch.einsum('s, ge, geij, geji->ges', pressure_list, Jdp, invF, adjuGrad) + \
                torch.einsum('s, ge, geij, geji->ges', pressure_list, J, invFdp, adjuGrad) + \
                torch.einsum('s, ge, geij, geji->ges', pressure_list, J, invF, adjudpGrad)

        for ind_F in range(num_U):
            UdF_now = fe._GC2RGC_linear(UdF0[ind_F])[0]
            Ugrad_dF = element_sensitive.gradient_displacement(UdF_now)
            Ugrad2_dF = element_sensitive.gradient_2nd_displacement(UdF_now)

            sdF = torch.einsum('geijkl, gekl->geij', C, Ugrad_dF)
            JdF = torch.einsum('ge, gelk, gekl->ge', J, invF, Ugrad_dF)
            invFdF = -torch.einsum('geik, gelj, gekl->geij', invF, invF,
                                   Ugrad_dF)
            invFdualdF = torch.einsum('geij, gemn->geijmn', invFdF, invF)
            invFdualdF = invFdualdF + invFdualdF.transpose(2, 4).transpose(
                3, 5)
            invFdual2dF = invFdualdF - invFdualdF.transpose(3, 5)

            adju = ADJu_udf_gaussian[ind_F]
            adjudF = ADJudf_gaussian[ind_F]
            adjuGrad = ADJu_udfGrad_gaussian[ind_F]
            adjudFGrad = ADJudfGrad_gaussian[ind_F]

            sen_UdF[:, :, :, ind_F] = \
                torch.einsum('geij, geji->ge', s, adjudFGrad).unsqueeze(-1) + \
                torch.einsum('geij, geji->ge', sdF, adjuGrad).unsqueeze(-1)

            sen_UdF[:, :, 1:, ind_F] += \
                    \
                torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, JdF, invFdual2, adju, Ugrad2) + \
                torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, J, invFdual2dF, adju, Ugrad2) + \
                torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, J, invFdual2, adjudF, Ugrad2) + \
                torch.einsum('s, ge, geijnm, gej, gemni->ges', pressure_list, J, invFdual2, adju, Ugrad2_dF) + \
                    \
                torch.einsum('s, ge, geij, geji->ges', pressure_list, JdF, invF, adjuGrad) + \
                torch.einsum('s, ge, geij, geji->ges', pressure_list, J, invFdF, adjuGrad) + \
                torch.einsum('s, ge, geij, geji->ges', pressure_list, J, invF, adjudFGrad)
 
        return sen_U, sen_Udp, sen_UdF

    # endregion

class ShapeDerivativeContactSelf(BaseObj):
    """
    Shape derivative for contact forces.
    """

    def __init__(self, shapederivative_pneumatic: ShapeDerivativePneumatic):

        super().__init__()

        self.shapederivative_pneumatic = shapederivative_pneumatic

        self.sensitivity: list[torch.Tensor] = []
        """
        Sensitivity of the shape derivative with respect to the contact forces.
        """

        self.contact_force: list[ContactSelf] = []
        """
        Contact forces acting on the structure.
        """

        self._r0: list[torch.Tensor] = []
        """
        Initial reference configuration.
        """


    def initialize(self, r0: list[torch.Tensor], *args, **kwargs):

        fe_result = GLOBAL.controller.solver.fe_result
        adjoint = GLOBAL.controller.updater.adjoint
        fe = fe_result.fe

        self._r0 = [r0[i].detach().clone() for i in range(len(r0))]

        i=0

        surface_nodes = []
        self.contact_force = []
        while True:
            if 'ContactSelf_%d' % i not in fe.loads.keys():
                break
            self.contact_force.append(fe.loads['ContactSelf_%d' % i])
            surface_nodes.append(self.contact_force[-1].surface_element._elems.flatten().unique())
            i += 1

        surface_nodes_index: torch.Tensor = torch.cat(surface_nodes).unique()

        def get_residual_work(nodes_diff: torch.Tensor):
            fe.nodes = nodes_diff
            fe.initialize(RGC0=RGC0)
            residual_force = torch.zeros([fe.RGC_list_indexStart[-1]])

            for contact in self.contact_force:
                F_indices, F_values = contact.get_stiffness(RGC=RGC0)[:2]
                residual_force.scatter_add_(0, F_indices, F_values)

            residual_force_assembled = fe.assemble_force(residual_force, GC0=GC0)
            return (residual_force_assembled * ADJu).sum()

        GC0 = fe_result.U[0].to(fe.nodes.device)
        RGC0 = fe._GC2RGC(GC0)

        ADJu = adjoint.ADJu[0].to(fe.nodes.device)

        nodes0 = fe.nodes.clone().detach()

        grad_pos = torch.autograd.functional.jacobian(get_residual_work, nodes0)

        grads_remain = grad_pos[surface_nodes_index]
        nodes_remain = nodes0[surface_nodes_index]

        interpolate_points = self._get_interpolate_points()

        self.sensitivity = self._sensitivity_interpolation(Ldot=grads_remain, points_request=nodes_remain, interpolated_points=interpolate_points)

        for i in range(len(self.sensitivity)):
            self.sensitivity[i] *= self.shapederivative_pneumatic.scaler

    def __call__(self, weight, r: list[torch.Tensor], *args, **kwargs):
        loss_objective = 0.0

        for i in range(len(weight)):

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
    
