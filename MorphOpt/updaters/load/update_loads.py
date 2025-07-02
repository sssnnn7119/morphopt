from scipy import interpolate
import torch
from ...GLOBAL import PATH, History
import FEA
from .. import optimizer
from . import objectivefuncs
from ...modelparams import Surfaces, Loads
from ...modelparams.params import Params
from tabulate import tabulate
from ...solvers import Morph
from ..second_derivative_element import C3D10_Sensitivity
from ..base_updater import BaseUpdater
from ...solvers.FE_result import FE_result
class UpdaterLoads(BaseUpdater):
    """
    The Updater class is responsible for updating the parameters of the optimization process.
    It contains methods to update the parameters based on the optimization algorithm used.
    """

    def __init__(self, params: Params, max_step_iter: int) -> None:
        """
        Initialize the Updater class with the given parameters.
        
        Parameters:
            loads (Loads): The loads object that contains the pressure values.
            U_dim (list[int]): The dimensions of the interest for the optimization problem.
            max_step_iter (int): The maximum number of iterations for the sub-optimization process.
        """
        
        
        super().__init__(params)

        self.max_step_iter = max_step_iter
        """
        The maximum number of iterations for the sub-optimization process.
        """
        
        self.params_update: Loads = params.loads
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

        
    def initialize(self, iter_now: int, sensitivity: list[torch.Tensor], *args,
                   **kwargs) -> None:
        
        for obj_func in self.obj_funcs.values():
            obj_func.initialize(sensitivity=sensitivity)

        self.optimizer = optimizer.LBFGS(closure=self.closure, num_limit=10)

    def closure(self, x: torch.Tensor, return_list = False) -> None:
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
        Loss, sensitivity = self._get_sensitivity(fe_result, obj_fun=obj_fun)
        sensitivity = self._refine_sensitivity(iter_now=History.iteration,
                                               sensitivity=sensitivity)

        ind_nan = torch.isnan(sensitivity.view(-1))
        sensitivity.view(-1)[ind_nan] = 0

        # initialize the optimizer
        self.initialize(iter_now=History.iteration, sensitivity=sensitivity)

        # update the objective function
        variables = self.params_update.get_variables().detach().clone()

        # print the information
        print("\n\n")
        print("Start updating the surfaces...")

        for iteration in range(self.max_step_iter):
            self.iteration_total += 1

            # get the current variables of the surfaces
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

    def _get_sensitivity(self, fe_result: FE_result, obj_fun: callable):
        """
        Get the sensitivity of the design variables.

        Parameters:
            FE_result (FE_result): The result of the finite element analysis.

        Returns:
        torch.Tensor: The sensitivity of the design variables.
        """

        # get the shape derivative
        pressure_list = self.params_update.pressure.get_pressure()
        sen_U = []
        sen_Udp = []
        for p in range(len(pressure_list)):
            sen_U_now, sen_Udp_now = self._get_shape_derivative(fe=fe_result.fe, pressure_list=pressure_list[p], GC0=fe_result.U[p], Udp0=fe_result.Udp[p], GCv=fe_result.ADJu[p], GCw=fe_result.ADJudp[p])
            sen_U.append(sen_U_now)
            sen_Udp.append(sen_Udp_now)
        sen_U = torch.stack(sen_U, dim=0)
        sen_Udp = torch.stack(sen_Udp, dim=0)

        # Get the sensitivity of the elements
        GC0_ = fe_result.U[:, self.U_dim].detach().requires_grad_()
        Udp0_ = fe_result.Udp[:, :, self.U_dim].permute([0,2,1]).detach().requires_grad_()
        Loss = obj_fun(U=GC0_, Udp=Udp0_)
        LdU = torch.autograd.grad(Loss, GC0_, retain_graph=True, allow_unused=True)[0]
        LdUdp = torch.autograd.grad(Loss, Udp0_, allow_unused=True)[0]
        if LdU is None:
            LdU = torch.zeros_like(GC0_)
        if LdUdp is None:
            LdUdp = torch.zeros_like(Udp0_)
        
        Ldot = torch.einsum('tu, txu->tx', LdU, sen_U) + \
            torch.einsum('tup, txup->tx', LdUdp, sen_Udp)

        return Loss, Ldot

    def _refine_sensitivity(self, iter_now: int, sensitivity: torch.Tensor) -> torch.Tensor:

        return sensitivity

    # endregion
    
    # region derivatives
    
    def _get_shape_derivative(self, fe: FEA.Main.FEA_Main, pressure_list: list[float], GC0: torch.Tensor, Udp0: torch.Tensor, GCv: torch.Tensor, GCw: torch.Tensor):
        
        """
        calculate the shape derivative of the design variables.
        
        Parameters:
            - fe (FEA.Main.FEA_Main): The finite element analysis object.\n
            - GC0 (torch.Tensor): The displacement vector.\n
                [DoF]
            - Udp0 (torch.Tensor): The Jacobian vector.\n
                [p, DoF]
            - GCv (torch.Tensor): The sensitivity of velocity vector.\n
                [U, DoF]
            - GCw (torch.Tensor): The sensitivity of Jacobian vector.\n
                [U, p, DoF]
                
        Returns:
            tuple: A tuple containing:
                sen_U (torch.Tensor): The sensitivity of the displacement vector.
                    [xi, U]
                sen_Udp (torch.Tensor): The sensitivity of the Jacobian vector.
                    [xi, U, p]
        """

        Kdp_indices = fe._assemble_Stiffness_Matrix(fe._GC2RGC(GC0))[1]
        def get_Kdxi(pressure_ind: int):
            def function_p0dot(p):
                p0 = fe.loads['Pressure_%d'%pressure_ind].pressure
                fe.loads['Pressure_%d'%pressure_ind].pressure = p
                result = fe._assemble_Stiffness_Matrix(fe._GC2RGC(fe.GC))[2]
                fe.loads['Pressure_%d'%pressure_ind].pressure = p0
                return result
            
            # \partial K / \partial \xi
            _, Kdp2_values = torch.autograd.functional.jvp(
                function_p0dot, torch.tensor([pressure_list[pressure_ind]], dtype=torch.float64), torch.ones([1]))

            Kdp0_values = Kdp2_values
            Kdp0 = torch.sparse_coo_tensor(Kdp_indices, Kdp0_values).coalesce()
            return Kdp0
        
        def get_Ldxi(xi_ind: int, xi_now: float):
            def function_p0dot(p):
                p0 = fe.loads['Pressure_%d'%xi_ind].pressure
                fe.loads['Pressure_%d'%xi_ind].pressure = p
                result = fe._assemble_Stiffness_Matrix(fe._GC2RGC(fe.GC))[0]
                fe.loads['Pressure_%d'%xi_ind].pressure = p0
                return result
            _, Ldxi = torch.autograd.functional.jvp(
                    function_p0dot, torch.tensor([xi_now], dtype=torch.float64), torch.ones([1]))
            return Ldxi

        sen_U = Udp0[:, self.U_dim]
        sen_Udp = torch.zeros([len(pressure_list), len(self.U_dim), len(pressure_list)])

        Kdxi_Jacobian = torch.zeros([len(pressure_list), GC0.shape[0], len(pressure_list)])
        for i in range(len(pressure_list)):
            Kdxi_now = get_Kdxi(i)
            for p in range(len(pressure_list)):
                Kdxi_Jacobian[i, :, p] = Kdxi_now @ Udp0[p]

        Ldxi = torch.zeros([len(pressure_list), GC0.shape[0]])
        for i in range(len(pressure_list)):
            Ldxi[i, :] = get_Ldxi(i, pressure_list[i])

        part_I = torch.einsum('xGp, uG->xup', (Kdxi_Jacobian), GCv)
        part_II = torch.einsum('xG, upG->xup', Ldxi, GCw)

        sen_Udp = part_I + part_II

        return sen_U, sen_Udp

    # endregion
