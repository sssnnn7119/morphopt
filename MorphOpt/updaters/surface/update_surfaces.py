from socketserver import UDPServer
from scipy import interpolate
import torch
from torch.nn.init import normal_
from ...GLOBAL import PATH, History
from .. import optimizer

from ...modelparams.params import Params
from ...modelparams import SurfacesParams, FEAParams, Materials
from tabulate import tabulate
from ..base_updater import BaseUpdater
from MorphOpt import GLOBAL

class UpdaterSurfaces(BaseUpdater):
    """
    The Updater class is responsible for updating the parameters of the optimization process.
    It contains methods to update the parameters based on the optimization algorithm used.
    """
    from . import objectivefuncs

    def __init__(self, params: Params, max_step_iter: int) -> None:
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

        self.obj_funcs: dict[str, UpdaterSurfaces.objectivefuncs.BaseObj] = {}
        """
        A list of penalty functions to be optimized. \n
        L = \sum_{i=1}^{n} w_i * f_i(x)
        """

        self._weight_points: list[torch.Tensor] = []
        """
        The weights for the points in the optimization process.
        """

        self.params_update: SurfacesParams = params.geometry
        """
        The surfaces object that contains the design variables.
        """

    def add_objective_function(self,
                               obj_func: objectivefuncs.baseobjfun,
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

    def initialize(self, iter_now: int, *args, **kwargs) -> None:
        """
        Initialize the parameters of the optimization process.

        Parameters:
            iter_now (int): The current iteration number.
        """

        # get the weights for the points in the optimization process
        self._weight_points = self.params_update.get_points_weight()

        # initialize the objective function
        r0, rdu0, rdu20 = self.params_update.get_geometry_values()

        for obj_func in self.obj_funcs.values():
            obj_func.initialize(iter_now=iter_now, r0=r0, rdu0=rdu0, rdu20=rdu20, weight=self._weight_points)

        # initialize the optimizer
        self.optimizer = optimizer.LBFGS(closure=self.closure, num_limit=20, tol_error=1e-10)

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
            obj_value.append(obj_func(self._weight_points, r, rdu, rdu2))

        # enroll the design variables
        self.params_update.set_parameters(xlist=x0)

        if return_list:
            return obj_value
        else:
            return sum(obj_value)

    def update(self) -> torch.Tensor:
        """
        Update the parameters of the optimization process.
        """

        # initialize the optimizer
        self.initialize(iter_now=History.iteration)

        # update the objective function
        variables = self.params_update.get_variables().detach().clone()

        # print the information
        print("\n\n")
        print("Start updating the surfaces...")


        low_step_length_iter = 0
        gk_new = None
        for iteration in range(self.max_step_iter):
            self.iteration_total += 1

            # get the current variables of the surfaces
            alpha, delta_var, gk_new = self.optimizer.step(x_now=variables, gk_now= gk_new)
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

        return variables.detach().clone()
