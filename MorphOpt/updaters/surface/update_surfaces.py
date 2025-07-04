from math import e
from socketserver import UDPServer
from scipy import interpolate
import torch
from torch.nn.init import normal_
from ...GLOBAL import PATH, History
import FEA
from .. import optimizer
from . import objectivefuncs
from ...modelparams.params import Params
from ...modelparams import Surfaces, Loads, Materials
from tabulate import tabulate
from ...solvers import Morph
from ..second_derivative_element import SensitivityElement
from ..base_updater import BaseUpdater
from ...solvers.FE_result import FE_result


class UpdaterSurfaces(BaseUpdater):
    """
    The Updater class is responsible for updating the parameters of the optimization process.
    It contains methods to update the parameters based on the optimization algorithm used.
    """

    def __init__(self, params: Params, max_step_iter: int, reset_per_iter: int = 5) -> None:
        """
        Initialize the Updater class with the given parameters.
        
        Parameters:
            surfaces (Surfaces): The surfaces object that contains the design variables.
            max_step_iter (int): The maximum number of iterations for the sub-optimization process.
            max_step_length_surf (list[float]): The maximum step length for each surface in the optimization process.
        """

        super().__init__(params)

        self.max_step_iter = max_step_iter
        """
        The maximum number of iterations for the sub-optimization process.
        """

        self.reset_per_iter = reset_per_iter
        """
        The number of iterations after which the scaler is reset.
        """

        self.scaler = None
        """
        The scaler for the objective function.
        """

        self.obj_funcs: dict[str, objectivefuncs.BaseObj] = {}
        """
        A list of penalty functions to be optimized. \n
        L = \sum_{i=1}^{n} w_i * f_i(x)
        """

        self._weight_points: list[torch.Tensor] = []
        """
        The weights for the points in the optimization process.
        """

        self.params_update: Surfaces = params.surfaces
        """
        The surfaces object that contains the design variables.
        """

        self._r0: list[torch.Tensor] = []
        """
        The initial coordinates of the surfaces.
        """

        self._normal0: list[torch.Tensor] = []
        """
        The initial normal vectors of the surfaces.
        """

    def add_objective_function(self,
                               obj_func: objectivefuncs.BaseObj,
                               name: str = None) -> None:
        """
        Add an objective function to the list of objective functions.

        Parameters:
            obj_func (ObjectiveFuncs.BaseObj): The objective function to be added.
        """
        if name is None:
            name = obj_func.__class__.__name__

        extra_num = 0
        while name + '_%d' % extra_num in self.obj_funcs.keys():
            extra_num += 1

        name = name + '_%d' % extra_num
        self.obj_funcs[name] = obj_func

    def _reset_scaler(self, iter_now: int, sensitivity: list[torch.Tensor]) -> None:
        """
        Reset the scaler for the objective function.

        Parameters:
            iter_now (int): The current iteration number.
        """
        self.scaler = []
        for i in range(len(sensitivity)):
            scaler_now = sensitivity[i].abs()

            scaler_now[scaler_now < 1e-15] = scaler_now[scaler_now > 1e-15].min()

            self.scaler.append(scaler_now)

            

    def initialize(self, iter_now: int, sensitivity: list[torch.Tensor], *args,
                   **kwargs) -> None:
        """
        Initialize the parameters of the optimization process.

        Parameters:
            iter_now (int): The current iteration number.
        """

        # reset the scaler
        self._reset_scaler(iter_now, sensitivity=sensitivity)
        # sensitivity = [
        #     sensitivity_surf * self.scaler for sensitivity_surf in sensitivity
        # ]

        # get the weights for the points in the optimization process
        self._weight_points = self.params_update.get_points_weight()

        # initialize the objective function
        r0, rdu0, rdu20 = self.params_update.get_geometry_values()
        self._r0 = [r0[i].detach().clone().cpu() for i in range(len(r0))]
        self._normal0 = [torch.cross(rdu0[i][:, 1], rdu0[i][:, 0]).detach().clone().cpu() 
                            for i in range(len(rdu0))]  
        self._normal0 = [normal / normal.norm(dim=0) for normal in self._normal0]

        for obj_func in self.obj_funcs.values():
            obj_func.initialize(r0=r0, rdu0=rdu0, sensitivity=sensitivity)

        # initialize the optimizer
        self.optimizer = optimizer.LBFGS(closure=self.closure, num_limit=100, tol_error=1e-10)

        self.iteration_total = 0

    def closure(self, x: torch.Tensor, return_list=False) -> float:
        """
        The closure function for the optimization process.

        Parameters:
            x (torch.Tensor): The current point in the optimization process.

        Returns:
            float: The objective function value at the current point.
        """
        # save the current point
        x0 = self.params_update.get_parameters()

        # Set the design variables to the current point
        self.params_update.update_variables(x_change=x)

        # Calculate the objective function value
        r, rdu, rdu2 = self.params_update.get_geometry_values()

        obj_value = []
        for obj_func in self.obj_funcs.values():
            if obj_func.__class__.__name__ != 'Sensitivity':
                # Calculate the objective function value
                weight_now = [self.scaler[i] * self._weight_points[i] for i in range(len(self._weight_points))]
                obj_value.append(obj_func(weight_now, r, rdu, rdu2))
            else:
                obj_value.append(obj_func(self._weight_points, r, rdu, rdu2))

        # enroll the design variables
        self.params_update.set_parameters(xlist=x0)

        if return_list:
            return obj_value
        else:
            return sum(obj_value)

    def update(self, fe_result: FE_result, obj_fun: callable) -> torch.Tensor:
        """
        Update the parameters of the optimization process.
        """

        # sensitivity analysis
        Loss, sensitivity = self._get_sensitivity(fe_result, obj_fun=obj_fun)
        sensitivity = self._refine_sensitivity(iter_now=History.iteration,
                                               sensitivity=sensitivity)
        for sensitivity_surf in sensitivity:
            ind_nan = torch.isnan(sensitivity_surf.view(-1))
            sensitivity_surf.view(-1)[ind_nan] = 0

        # initialize the optimizer
        self.initialize(iter_now=History.iteration, sensitivity=sensitivity)

        # update the objective function
        variables = self.params_update.get_variables().detach().clone()

        # print the information
        print("\n\n")
        print("Start updating the surfaces...")


        low_step_length_iter = 0
        for iteration in range(self.max_step_iter):
            self.iteration_total += 1

            # get the current variables of the surfaces
            alpha, delta_var = self.optimizer.step(x_now=variables)
            variables.data += delta_var * alpha

            # check if the step length is too small
            if abs(alpha) < 1e-10:
                low_step_length_iter += 1

            if low_step_length_iter > 10:
                print(
                    f"Low step length detected ({low_step_length_iter} iterations), stopping optimization."
                )
                break

            # get current objective function value
            with torch.no_grad():
                obj_values = self.closure(x=variables, return_list=True)

            # print the objective function value
            # Print a pretty table showing objective values and iteration progress
            # Clear previous output (move cursor up and clear lines)
            if iteration > 0:
                print("\033[F\033[K" * 4, end="\r")

            headers = ["Iteration"] + ["Total"] + list(self.obj_funcs.keys())
            data = [[f"{iteration+1}/{self.max_step_iter}"] +
                    [f"{sum(obj_values).item():.6e}"] +
                    [f"{val.item():.6e}" for val in obj_values]]

            string = tabulate(data, headers=headers, tablefmt="grid")
            print(string, end="\r")

        return Loss, variables.detach().clone()

    # region sensitivity

    def _get_interpolate_points(self, *args, **kwargs):
        """
        Get the interpolated points for the design variables.

        Parameters:
        *args: Additional arguments.
        **kwargs: Additional keyword arguments.

        Returns:
            list[torch.Tensor]: The interpolated points for the design variables.
        """
        r0 = self.params_update.get_geometry_values()[0]
        interpolated_points = []
        for sf in range(self.params_update.num_surface):
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
            [points_request[element_str] for element_str in points_request.keys()],
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

    def _get_sensitivity(
            self, fe_result: FE_result,
            obj_fun: callable) -> tuple[float, list[torch.Tensor]]:
        """
        Get the sensitivity of the design variables.

        Parameters:
            FE_result (FE_result): The result of the finite element analysis.

        Returns:
        torch.Tensor: The sensitivity of the design variables.
        """

        # Get the interpolated points for the design variables
        interpolated_points = self._get_interpolate_points()

        # Get the derivative of the objective function with respect to the displacement and Jacobian
        Loss, LdU, LdUdp, LdUdF = self._get_LdU_LdUdp(fe_result=fe_result,
                                               obj_fun=obj_fun)

        # Get the sensitivity of the design variables
        points_request, Ldot = self._get_shape_derivative(fe_result=fe_result,
                                                          LdU=LdU,
                                                          LdUdp=LdUdp,
                                                          LdUdF=LdUdF)

        # Interpolate the sensitivity into the structural grids
        sensitivity = self._sensitivity_interpolation(Ldot, points_request,
                                                      interpolated_points)

        return Loss, sensitivity

    def _get_LdU_LdUdp(self, fe_result: FE_result,
                       obj_fun: callable) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Get the sensitivity of the design variables.
        Parameters:
            fe_result (FE_result): The result of the finite element analysis.
            obj_fun (callable): The objective function to be optimized.
        Returns:
            tuple: A tuple containing:
                - loss (float): The loss function
                - LdU (torch.Tensor): The sensitivity of the displacement vector.
                - LdUdp (torch.Tensor): The sensitivity of the Jacobian vector.
                - LdUdF (torch.Tensor): The sensitivity of the derivative of the displacement vector with respect to the external force on the end-effector.
        """
        device = torch.zeros(1).device

        # Get the sensitivity of the elements
        GC0_ = fe_result.U[:, self.U_dim].detach().to(device).requires_grad_()
        Udp0_ = fe_result.Udp[:, :, self.U_dim].permute(
            [0, 2, 1]).detach().to(device).requires_grad_()
        UdF0_ = fe_result.UdF[:, :, self.U_dim].permute(
            [0, 2, 1]).detach().to(device).requires_grad_()
        
        Loss = obj_fun(U=GC0_, Udp=Udp0_, UdF=UdF0_)
        LdU = torch.autograd.grad(Loss,
                                  GC0_,
                                  retain_graph=True,
                                  allow_unused=True)[0]
        LdUdp = torch.autograd.grad(Loss, Udp0_, retain_graph=True, allow_unused=True)[0]
        LdUdF = torch.autograd.grad(Loss, UdF0_, retain_graph=True, allow_unused=True)[0]

        if LdU is None:
            LdU = torch.zeros_like(GC0_)
        if LdUdp is None:
            LdUdp = torch.zeros_like(Udp0_)
        if LdUdF is None:
            LdUdF = torch.zeros_like(UdF0_)

        return Loss, LdU, LdUdp, LdUdF

    def _get_shape_derivative(
            self, fe_result: FE_result, LdU: torch.Tensor,
            LdUdp: torch.Tensor, LdUdF: torch.Tensor
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

            elems = fe_result.fe.elems[element_str]
            element_sensitive = SensitivityElement.get_sensitivity_element(elems=elems, fe=fe_result.fe)
            

            for p in range(len(pressure_list)):
                sen_U_now, sen_Udp_now, sen_UdF_now = self._cal_shape_derivative_displacement_jacobian(
                    fe=fe_result.fe,
                    element_sensitive=element_sensitive,
                    pressure_list=pressure_list[p],
                    GC0=fe_result.U[p].to(device),
                    Udp0=fe_result.Udp[p].to(device),
                    UdF0=fe_result.UdF[p].to(device),
                    ADJu=fe_result.ADJu[p].to(device),
                    ADJudp=fe_result.ADJudp[p].to(device),
                    ADJudf=fe_result.ADJudf[p].to(device))

                if p == 0:
                    Ldot_now = torch.einsum('u, gesu->ges', LdU[p], sen_U_now) + \
                        torch.einsum('up, gesup->ges', LdUdp[p], sen_Udp_now) + \
                        torch.einsum('uf, gesuf->ges', LdUdF[p], sen_UdF_now)
                else:
                    Ldot_now += torch.einsum('u, gesu->ges', LdU[p], sen_U_now) + \
                        torch.einsum('up, gesup->ges', LdUdp[p], sen_Udp_now) + \
                        torch.einsum('uf, gesuf->ges', LdUdF[p], sen_UdF_now)

            points_request[element_str] = (element_sensitive.points_request)
            Ldot[element_str] = (Ldot_now.reshape([-1, Ldot_now.shape[-1]]))

        return points_request, Ldot

    def _refine_sensitivity(self, iter_now: int,
                            sensitivity: list) -> list[torch.Tensor]:

        for i in range(len(sensitivity)):
            # sensitivity_surf[i] *= 100
            if self.params_update.surface_list[i].surf_type == 0:
                index0 = (
                    self.params_update.surface_list[i].model.coordinates[0]
                    < self.params_update.surface_list[i].model.interval_size[0]
                    * 2
                ) | (self.params_update.surface_list[i].model.coordinates[0]
                     > 1 -
                     self.params_update.surface_list[i].model.interval_size[0]
                     * 2)
                sensitivity[i].data[index0.view(-1)] = 0

        return sensitivity

    # endregion

    # region shape derivative

    def _cal_shape_derivative_displacement_jacobian(
            self, fe: FEA.Main.FEA_Main, element_sensitive: SensitivityElement,
            pressure_list: list[float], GC0: torch.Tensor, Udp0: torch.Tensor, UdF0: torch.Tensor,
            ADJu: torch.Tensor, ADJudp: torch.Tensor, ADJudf: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
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
              [U, DoF]
            ADJudp (torch.Tensor): The sensitivity of Jacobian vector.
              [U, p, DoF]
            ADJudf (torch.Tensor): The sensitivity of compliance.
                [U, F, DoF]

        Returns:
            tuple: A tuple containing:
                sen_U (torch.Tensor): The sensitivity of the displacement vector.
                    [num_gauss, num_element, num_surface, U]
                sen_Udp (torch.Tensor): The sensitivity of the Jacobian vector.
                    [num_gauss, num_element, num_surface, U, p]
                sen_Udf (torch.Tensor): The sensitivity of the derivative of the displacement vector with respect to the external force on the end-effector.
                    [num_gauss, num_element, num_surface, U, F]
        """

        num_surface = self.params_update.num_surface
        num_U = ADJu.shape[0]

        # # prepare the data
        J, F, invF, Ugrad, Ugrad2, s, C = element_sensitive.sensitivity_conponent(
            fe._GC2RGC(GC0)[0])
        invFdual = torch.einsum('geij, gekl-> geijkl', invF, invF)
        invFdual2 = invFdual - invFdual.transpose(3, 5)

        # prepare the sensitivity tensors
        sen_U = torch.zeros([J.shape[0], J.shape[1], num_surface,
                             num_U])  # surface, u
        sen_Udp = torch.zeros(
            [J.shape[0], J.shape[1], num_surface, num_U,
             len(pressure_list)])  # surface, u, p
        sen_UdF = torch.zeros(
            [J.shape[0], J.shape[1], num_surface, num_U, num_U])

        ADJu_gaussian = []
        ADJuGrad_gaussian = []
        ADJudp_gaussian = []
        ADJudpGrad_gaussian = []
        ADJudf_gaussian = []
        ADJudfGrad_gaussian = []
        for ind_target in range(num_U):
            ADJu_now = fe._GC2RGC_linear(ADJu[ind_target])[0]
            ADJu_gaussian.append(element_sensitive.displacement(ADJu_now))
            ADJuGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJu_now))

            ADJudp_gaussian.append([])
            ADJudpGrad_gaussian.append([])
            
            ADJudf_gaussian.append([])
            ADJudfGrad_gaussian.append([])

            for ind_pressure in range(len(pressure_list)):
                ADJudp_now = fe._GC2RGC_linear(ADJudp[ind_target, ind_pressure])[0]
                ADJudp_gaussian[ind_target].append(
                    element_sensitive.displacement(ADJudp_now))
                ADJudpGrad_gaussian[ind_target].append(
                    element_sensitive.gradient_displacement(ADJudp_now))
                
            for ind_F in range(num_U):
                ADJudf_now = fe._GC2RGC_linear(ADJudf[ind_target, ind_F])[0]
                ADJudf_gaussian[ind_target].append(
                    element_sensitive.displacement(ADJudf_now))
                ADJudfGrad_gaussian[ind_target].append(
                    element_sensitive.gradient_displacement(ADJudf_now))
                

        # calculate the sensitivity of U
        for ind_target in range(num_U):

            adju = ADJu_gaussian[ind_target]
            adjuGrad = ADJuGrad_gaussian[ind_target]
            sen_U[:, :, :, ind_target] = \
                torch.einsum('geij, geji->ge', s, adjuGrad).unsqueeze(-1)
            sen_U[:, :, 1:, ind_target] += \
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
            for ind_target in range(num_U):
                adju = ADJu_gaussian[ind_target]
                adjudp = ADJudp_gaussian[ind_target][ind_pressure]
                adjuGrad = ADJuGrad_gaussian[ind_target]
                adjudpGrad = ADJudpGrad_gaussian[ind_target][ind_pressure]

                sen_Udp[:, :, :, ind_target, ind_pressure] = \
                    torch.einsum('geij, geji->ge', s, adjudpGrad).unsqueeze(-1) + \
                    torch.einsum('geij, geji->ge', sdp, adjuGrad).unsqueeze(-1)

                sen_Udp[:, :, ind_pressure + 1, ind_target, ind_pressure] += \
                        \
                    torch.einsum('ge, geijnm, gej, gemni->ge', J, invFdual2, adju, Ugrad2) + \
                        \
                    torch.einsum('ge, geij, geji->ge', J, invF, adjuGrad)

                sen_Udp[:, :, 1:, ind_target, ind_pressure] += \
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
            for ind_target in range(num_U):
                adju = ADJu_gaussian[ind_target]
                adjudF = ADJudf_gaussian[ind_target][ind_F]
                adjuGrad = ADJuGrad_gaussian[ind_target]
                adjudFGrad = ADJudfGrad_gaussian[ind_target][ind_F]

                sen_UdF[:, :, :, ind_target, ind_F] = \
                    torch.einsum('geij, geji->ge', s, adjudFGrad).unsqueeze(-1) + \
                    torch.einsum('geij, geji->ge', sdF, adjuGrad).unsqueeze(-1)

                sen_UdF[:, :, 1:, ind_target, ind_F] += \
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

    def show_sensitivity(self, sensitivity: list[torch.Tensor], ind: int) -> None:
        """
        Show the shape sensitivity
        """

        def show_quiver3d(R: torch.Tensor, N: torch.Tensor):
            from mayavi import mlab
            r = R.detach().cpu().numpy()
            n = N.detach().cpu().numpy()
            mlab.quiver3d(r[0], r[1], r[2], n[0], n[1], n[2])
            

        r0, rdu0 = self.params_update.get_geometry_values()[:2]
        interpolated_points = []
        normal_list = []
        for sf in range(self.params_update.num_surface):

            normal = torch.cross(rdu0[sf][:, 1], rdu0[sf][:, 0], dim=0)

            normal = normal / torch.norm(normal, dim=0, keepdim=True)

            interpolated_points.append(
                r0[sf].cpu())
            normal_list.append(normal.cpu())
            
        from mayavi import mlab

        mlab.figure(size=(1000, 1000), bgcolor=(0, 0, 0))
        show_quiver3d(interpolated_points[ind], sensitivity[ind].cpu() * normal_list[ind].cpu())


        mlab.show()