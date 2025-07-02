from scipy import interpolate
import torch
from ...GLOBAL import PATH, History
import FEA
from .. import optimizer
from . import objectivefuncs
from ...modelparams import Surfaces, Loads, Materials
from ...modelparams.params import Params
from tabulate import tabulate
from ...solvers import Morph
from ..second_derivative_element import SensitivityElement
from ..base_updater import BaseUpdater
from ...solvers.FE_result import FE_result
from FEA.elements.materials import NeoHookean

class UpdaterMaterials(BaseUpdater):
    """
    The Updater class is responsible for updating the parameters of the optimization process.
    It contains methods to update the parameters based on the optimization algorithm used.
    """

    def __init__(self, params: Params,
                 max_step_iter: int) -> None:
        """
        Initialize the Updater class with the given parameters.
        
        Parameters:
            materials (Materials): The materials object that contains the pressure values.
            U_dim (list[int]): The dimensions of the interest for the optimization problem.
            max_step_iter (int): The maximum number of iterations for the sub-optimization process.
        """
        
        super().__init__(params)

        self.max_step_iter = max_step_iter
        """
        The maximum number of iterations for the sub-optimization process.
        """

        self.params_update: Materials = params.materials
        """
        The loads object that contains the pressure values.
        """

        self.obj_funcs: dict[str, objectivefuncs.BaseObj] = {}
        """
        A list of penalty functions to be optimized. \n
        L = \sum_{i=1}^{n} w_i * f_i(x)
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

    def initialize(self, iter_now: int, sensitivity: torch.Tensor, points_request: torch.Tensor, *args,
                   **kwargs) -> None:

        for obj_func in self.obj_funcs.values():
            obj_func.initialize(sensitivity=sensitivity, points_request=points_request, *args, **kwargs)

        self.optimizer = optimizer.LBFGS(closure=self.closure, num_limit=10)

    def closure(self, x: torch.Tensor, return_list=False) -> None:
        """
        This method is called to update the design variables based on the optimization algorithm used.
        """
        # save the current point
        x0 = self.params_update.get_parameters()

        # Set the design variables to the current point
        self.params_update.update_variables(x_change=x)

        # Calculate the objective function value
        obj_value = []
        for obj_func in self.obj_funcs.values():
            obj_value.append(obj_func())

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
        Loss, sensitivity, points_request = self._get_sensitivity(fe_result, obj_fun=obj_fun)
        sensitivity = self._refine_sensitivity(iter_now=History.iteration,
                                               sensitivity=sensitivity)

        ind_nan = torch.isnan(sensitivity.view(-1))
        sensitivity.view(-1)[ind_nan] = 0

        # initialize the optimizer
        self.initialize(iter_now=History.iteration, sensitivity=sensitivity, points_request=points_request)

        # update the objective function
        variables = self.params_update.get_variables().detach().clone()

        # print the information
        print("\n\n")
        print("Start updating the materials parameters.")

        for iteration in range(self.max_step_iter):
            self.iteration_total += 1

            # get the current variables of the optimization problem
            alpha, delta_var = self.optimizer.step(x_now=variables)
            variables.data += delta_var * alpha

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

    def _get_sensitivity(
            self, fe_result: FE_result,
            obj_fun: callable) -> tuple[float, torch.Tensor]:
        """
        Get the sensitivity of the design variables.

        Parameters:
            FE_result (FE_result): The result of the finite element analysis.

        Returns:
            tuple: A tuple containing:
                - Loss (float): The loss value.
                - sensitivity (torch.Tensor): The sensitivity of the design variables.
                - points_request (torch.Tensor): [N, 3] The points where the sensitivity is requested.
        """

        # get the shape derivative
        pressure_list = fe_result.pressure_list

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
        LdUdF = torch.autograd.grad(Loss, UdF0_, allow_unused=True)[0]

        if LdU is None:
            LdU = torch.zeros_like(GC0_)
        if LdUdp is None:
            LdUdp = torch.zeros_like(Udp0_)
        if LdUdF is None:
            LdUdF = torch.zeros_like(UdF0_)

        points_request = []
        Ldot = []

        for element_str in fe_result.fe.elems.keys():
            if element_str.startswith('element'):
                elems = fe_result.fe.elems[element_str]
                element_sensitive = SensitivityElement.get_sensitivity_element(elems=elems, fe=fe_result.fe)
                element_sensitive.set_materials(NeoHookean(mu=self.params.materials.mu, kappa=self.params.materials.kappa))
            else:
                continue
            
            
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
                    ADJudF=fe_result.ADJudf[p].to(device))

                if p == 0:
                    Ldot_now = torch.einsum('u, geu->ge', LdU[p], sen_U_now) + \
                        torch.einsum('up, geup->ge', LdUdp[p], sen_Udp_now) + \
                        torch.einsum('uf, geuf->ge', LdUdF[p], sen_UdF_now)
                else:
                    Ldot_now += torch.einsum('u, geu->ge', LdU[p], sen_U_now) + \
                        torch.einsum('up, geup->ge', LdUdp[p], sen_Udp_now) + \
                        torch.einsum('uf, gef->ge', LdUdF[p], sen_UdF_now)

            points_request.append(element_sensitive.points_request.reshape(-1, 3))
            Ldot.append(Ldot_now.flatten())

        points_request = torch.cat(points_request, dim=0)
        Ldot = torch.cat(Ldot, dim=0)

        return Loss, Ldot, points_request

    def _refine_sensitivity(self, iter_now: int,
                            sensitivity: torch.Tensor) -> torch.Tensor:

        return sensitivity

    # endregion

    # region derivatives

    def _cal_shape_derivative_displacement_jacobian(self, fe: FEA.Main.FEA_Main, element_sensitive: SensitivityElement,
                              pressure_list: list[float], GC0: torch.Tensor,
                              Udp0: torch.Tensor, UdF0: torch.Tensor, ADJu: torch.Tensor,
                              ADJudp: torch.Tensor, ADJudF: torch.Tensor):
        """
        calculate the shape derivative of the design variables.
        
        Parameters:
            fe (FEA.Main.FEA_Main): The finite element analysis object.
            element_sensitive (C3D10_Sensitivity): The element sensitivity object.
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
            ADJudF (torch.Tensor): The sensitivity of compliance.
                [U, F, DoF]

        Returns:
            tuple: A tuple containing:
                sen_U (torch.Tensor): The sensitivity of the displacement vector.
                    [num_gauss, num_element, U]
                sen_Udp (torch.Tensor): The sensitivity of the Jacobian vector.
                    [num_gauss, num_element, U, p]
                sen_Udf (torch.Tensor): The sensitivity of the derivative of the displacement vector with respect to the external force on the end-effector.
                    [num_gauss, num_element, U, F]
        """
        
        num_U = ADJu.shape[0]
        

        
        
        J, F, invF, Ugrad, Ugrad2, s, C = element_sensitive.sensitivity_conponent(
            fe._GC2RGC(GC0)[0])
        
        
        sen_U = torch.zeros([J.shape[0], J.shape[1],
                             num_U])
        sen_Udp = torch.zeros([J.shape[0], J.shape[1],
                                   num_U, len(pressure_list)])
        sen_UdF = torch.zeros([J.shape[0], J.shape[1],
                                   num_U, num_U])
        gaussian_weights = element_sensitive.gaussian_weight
        


        # prepare the sensitivity of the adjoint variables
        ADJuGrad_gaussian = []
        ADJudpGrad_gaussian = []
        ADJudFGrad_gaussian = []
        for ind_target in range(num_U):
            ADJu_now = fe._GC2RGC_linear(ADJu[ind_target])[0]

            ADJuGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJu_now))

            ADJudpGrad_gaussian.append([])
            ADJudFGrad_gaussian.append([])
            
            for ind_pressure in range(len(pressure_list)):
                ADJudp_now = fe._GC2RGC_linear(ADJudp[ind_target, ind_pressure])[0]

                ADJudpGrad_gaussian[ind_target].append(
                    element_sensitive.gradient_displacement(ADJudp_now))
                
            for ind_F in range(num_U):
                ADJudF_now = fe._GC2RGC_linear(ADJudF[ind_target, ind_F])[0]

                ADJudFGrad_gaussian[ind_target].append(
                    element_sensitive.gradient_displacement(ADJudF_now))
                

        # calculate the sensitivity of U
        for ind_target in range(num_U):
            ADJuGrad = ADJuGrad_gaussian[ind_target]
            sen_U[:, :, ind_target] = \
                torch.einsum('geij, geji->ge', s, ADJuGrad)
            
        # calculate the sensitivity of Udp
        for ind_pressure in range(len(pressure_list)):
            Udp_now = fe._GC2RGC_linear(Udp0[ind_pressure])[0]
            Ugrad_dp = element_sensitive.gradient_displacement(Udp_now)
            
            sdp = torch.einsum('geijkl, gekl->geij', C, Ugrad_dp)
            
            for ind_target in range(num_U):
                ADJuGrad = ADJuGrad_gaussian[ind_target]
                ADJudpGrad = ADJudpGrad_gaussian[ind_target][ind_pressure]
                sen_Udp[:, :, ind_target, ind_pressure] = \
                    torch.einsum('geij, geji->ge', s, ADJudpGrad) + \
                    torch.einsum('geij, geji->ge', sdp, ADJuGrad)
        
        # calculate the sensitivity of UdF
        for ind_F in range(num_U):
            UdF_now = fe._GC2RGC_linear(UdF0[ind_F])[0]
            Ugrad_dF = element_sensitive.gradient_displacement(UdF_now)
            
            sdF = torch.einsum('geijkl, gekl->geij', C, Ugrad_dF)
            
            for ind_target in range(num_U):
                ADJuGrad = ADJuGrad_gaussian[ind_target]
                ADJudFGrad = ADJudFGrad_gaussian[ind_target][ind_F]
                sen_UdF[:, :, ind_target, ind_F] = \
                    torch.einsum('geij, geji->ge', s, ADJudFGrad) + \
                    torch.einsum('geij, geji->ge', sdF, ADJuGrad)
        
        sen_U*= gaussian_weights.unsqueeze(-1)
        sen_Udp *= gaussian_weights.unsqueeze(-1).unsqueeze(-1)
        sen_UdF *= gaussian_weights.unsqueeze(-1).unsqueeze(-1)


        return sen_U, sen_Udp, sen_UdF

    # endregion
