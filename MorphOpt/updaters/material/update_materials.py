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
from ..adjoints import Adjoints

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
    
    def update(self, fe_result: FE_result, adjoint: Adjoints) -> torch.Tensor:
        """
        Update the parameters of the optimization process.
        """

        # sensitivity analysis
        sensitivity, points_request = self._get_sensitivity(fe_result=fe_result, adjoint=adjoint)
        sensitivity = self._refine_sensitivity(iter_now=History.iteration,
                                               sensitivity=sensitivity)

        ind_nan = torch.isnan(sensitivity.view(-1))
        sensitivity.view(-1)[ind_nan] = 0

        # initialize the optimizer
        self.initialize(iter_now=History.iteration, sensitivity=sensitivity, points_request=points_request)

        # update the objective function
        variables = self.params_update.get_variables().detach().clone()
        gk_now = None
        # print the information
        print("\n\n")
        print("Start updating the materials parameters.")

        for iteration in range(self.max_step_iter):
            self.iteration_total += 1

            # get the current variables of the optimization problem
            alpha, delta_var, gk_now = self.optimizer.step(x_now=variables, gk_now=gk_now)
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

        return variables.detach().clone()
    # region sensitivity

    def _get_sensitivity(
            self, fe_result: FE_result, adjoint: Adjoints) -> tuple[float, torch.Tensor]:
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

            points_request.append(element_sensitive.points_request.reshape(-1, 3))
            Ldot.append(Ldot_now.flatten())

        points_request = torch.cat(points_request, dim=0)
        Ldot = torch.cat(Ldot, dim=0)

        return Ldot, points_request

    def _refine_sensitivity(self, iter_now: int,
                            sensitivity: torch.Tensor) -> torch.Tensor:

        return sensitivity

    # endregion

    # region derivatives

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
                [g, e]
        """
        
        num_U = UdF0.shape[0]
        
        
        J, F, invF, Ugrad, Ugrad2, s, C = element_sensitive.sensitivity_conponent(
            fe._GC2RGC(GC0)[0])
        
        
        sen_U = torch.zeros([J.shape[0], J.shape[1]])
        sen_Udp = torch.zeros([J.shape[0], J.shape[1], len(pressure_list)])
        sen_UdF = torch.zeros([J.shape[0], J.shape[1], num_U])
        gaussian_weights = element_sensitive.gaussian_weight
        


        # prepare the sensitivity of the adjoint variables

        ADJudpGrad_gaussian = []
        ADJudFGrad_gaussian = []
        ADJu_udpGrad_gaussian = []
        ADJu_udfGrad_gaussian = []

        ADJu_now = fe._GC2RGC_linear(ADJu)[0]

        ADJuGrad_gaussian=(
            element_sensitive.gradient_displacement(ADJu_now))
        
        for ind_pressure in range(len(pressure_list)):
            ADJudp_now = fe._GC2RGC_linear(ADJudp[ind_pressure])[0]
            ADJudpGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJudp_now))
            
            ADJu_udp_now = fe._GC2RGC_linear(ADJu_udp[ind_pressure])[0]
            ADJu_udpGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJu_udp_now))
            
        for ind_F in range(num_U):
            ADJudF_now = fe._GC2RGC_linear(ADJudf[ind_F])[0]
            ADJudFGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJudF_now))
            
            ADJu_udf_now = fe._GC2RGC_linear(ADJu_udf[ind_F])[0]
            ADJu_udfGrad_gaussian.append(
                element_sensitive.gradient_displacement(ADJu_udf_now))
                

        # calculate the sensitivity of U
        ADJuGrad = ADJuGrad_gaussian
        sen_U[:, :] = \
            torch.einsum('geij, geji->ge', s, ADJuGrad)
            
        # calculate the sensitivity of Udp
        for ind_pressure in range(len(pressure_list)):
            Udp_now = fe._GC2RGC_linear(Udp0[ind_pressure])[0]
            Ugrad_dp = element_sensitive.gradient_displacement(Udp_now)
            
            sdp = torch.einsum('geijkl, gekl->geij', C, Ugrad_dp)
            

            ADJuGrad = ADJu_udpGrad_gaussian[ind_pressure]
            ADJudpGrad = ADJudpGrad_gaussian[ind_pressure]
            sen_Udp[:, :, ind_pressure] = \
                torch.einsum('geij, geji->ge', s, ADJudpGrad) + \
                torch.einsum('geij, geji->ge', sdp, ADJuGrad)
        
        # calculate the sensitivity of UdF
        for ind_F in range(num_U):
            UdF_now = fe._GC2RGC_linear(UdF0[ind_F])[0]
            Ugrad_dF = element_sensitive.gradient_displacement(UdF_now)
            
            sdF = torch.einsum('geijkl, gekl->geij', C, Ugrad_dF)
            

            ADJuGrad = ADJu_udfGrad_gaussian[ind_F]
            ADJudFGrad = ADJudFGrad_gaussian[ind_F]
            sen_UdF[:, :, ind_F] = \
                torch.einsum('geij, geji->ge', s, ADJudFGrad) + \
                torch.einsum('geij, geji->ge', sdF, ADJuGrad)
        
        sen_U*= gaussian_weights
        sen_Udp *= gaussian_weights.unsqueeze(-1)
        sen_UdF *= gaussian_weights.unsqueeze(-1)


        return sen_U, sen_Udp, sen_UdF

    # endregion
