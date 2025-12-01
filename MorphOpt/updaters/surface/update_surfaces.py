from socketserver import UDPServer
from scipy import interpolate
import torch
from torch.nn.init import normal_
from ...GLOBAL import PATH, History
from .. import optimizer

from ...modelparams.params import Params
from ...modelparams import GeometryParams, FEAParams, Materials
from tabulate import tabulate
from ..base_updater import BaseUpdater
from MorphOpt import GLOBAL

class UpdaterSurfaces(BaseUpdater):
    """
    The Updater class is responsible for updating the parameters of the optimization process.
    It contains methods to update the parameters based on the optimization algorithm used.
    """
    from . import objectivefuncs

    def __init__(self, params: Params, max_step_iter: int, max_step_length: float = 0.5, reset_sensitivity_scaler_per_iter: int = 1) -> None:
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

        self.constraints_funcs: dict[str, UpdaterSurfaces.objectivefuncs.BaseConstraints] = {}
        """
        A list of penalty functions to be optimized. \n
        L = sum_{i=1}^{n} w_i * f_i(x)
        """

        self.obj_funcs: dict[str, UpdaterSurfaces.objectivefuncs.BaseObjective] = {}
        """
        A list of objective functions to be optimized. \n
        L = sum_{i=1}^{n} w_i * f_i(x)
        """

        self.sensitivity_previous: list[torch.Tensor] = []
        """
        The sensitivity values for the optimization process from the previous iteration.
        """

        self._weight_points: list[torch.Tensor] = []
        """
        The weights for the points in the optimization process.
        """

        self.params_update: GeometryParams = params.geometry
        """
        The surfaces object that contains the design variables.
        """

        self._reset_sensitivity_scaler_per_iter = reset_sensitivity_scaler_per_iter
        """
        The number of iterations after which the scaler is reset.
        """

        self._sensitivity_scaler: float = None
        """
        The scaler for the shape derivative sensitivity.
        """

        self._max_step_length_max: float = max_step_length
        """
        The maximum step length for each surface in the optimization process.
        """

        self._max_step_length: list[torch.Tensor] = []
        """
        The current maximum step length for each surface in the optimization process.
        """

        self._step_length_min_ratio: float = 0.1
        """
        The minimum ratio for the step length relative to the maximum step length.
        """

        self._step_length_decay: float = 0.5
        """
        The decay factor for the step length relative to the maximum step length.
        """

        self._step_length_increase: float = 1.2
        """
        The increase factor for the step length relative to the maximum step length.
        """

    def add_constraints(self,
                               obj_func: objectivefuncs.basefuncs,
                               name: str = None) -> None:
        """
        Add an objective function to the list of objective functions.

        Parameters:
            obj_func (ObjectiveFuncs.BaseObj): The objective function to be added.
        """
        if name is None:
            name = obj_func.__class__.__name__

        extra_num = 0
        while name + '_%d' % extra_num in self.constraints_funcs.keys():
            extra_num += 1

        name = name + '_%d' % extra_num
        self.constraints_funcs[name] = obj_func

    def add_objective_function(self,
                               obj_func: objectivefuncs.basefuncs,
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

        # initialize the shape derivative sensitivity
        for obj_func in self.obj_funcs.values():
            obj_func.initialize(r0=r0, rdu0=rdu0, rdu20=rdu20)

        # reset the scaler for the shape derivative
        if iter_now % self._reset_sensitivity_scaler_per_iter == 0 or self._sensitivity_scaler is None:
            max_sensitivity = 0.
            for obj_func in self.obj_funcs.values():
                for sensitivity_surf in obj_func.sensitivity:
                    max_sensitivity = max(max_sensitivity,
                                        sensitivity_surf.abs().max())
            self._sensitivity_scaler = 1 / max_sensitivity

        # rescale the sensitivity
        for obj_func in self.obj_funcs.values():
            for surf_ind in range(len(obj_func.sensitivity)):
                obj_func.sensitivity[surf_ind] = obj_func.sensitivity[surf_ind] * self._sensitivity_scaler * self._weight_points[surf_ind]

        # get the total sensitivity
        sensitivity_all = []
        for obj_func in self.obj_funcs.values():
            sensitivity_all.append(obj_func.sensitivity)
        sensitivity: list[torch.Tensor] = sensitivity_all[0]
        for surf_ind in range(len(sensitivity)):
            for obj_ind in range(1, len(sensitivity_all)):
                sensitivity[surf_ind] += sensitivity_all[obj_ind][surf_ind]
        
        # initialize the constraint functions
        for constraints in self.constraints_funcs.values():
            constraints.initialize(iter_now=iter_now, r0=r0, rdu0=rdu0, rdu20=rdu20, sensitivity=sensitivity)
            
        # initialize the optimizer
        self.optimizer = optimizer.LBFGS(closure=self.closure, num_limit=20, tol_error=1e-10)
        self.iteration_total = 0

        # initialize the max step length
        if len(self._max_step_length) == 0:
            for i in range(self.params_update.num_surface):
                self._max_step_length.append(torch.ones(self.params.geometry.surface_list[i].num_variables // 3) * self._max_step_length_max)

        for i in range(len(self._max_step_length)):
            if (self._max_step_length[i].numel() != self.params.geometry.surface_list[i].num_variables // 3):
                    self._max_step_length[i] = self._max_step_length[i].mean().repeat(self.params.geometry.surface_list[i].num_variables // 3)

        if len(self.sensitivity_previous) != 0:
            # check if the mesh has improved
            for i in range(len(self._max_step_length)):
                sensitivity_product = (sensitivity[i] * self.sensitivity_previous[i]).sum(dim=0) / (sensitivity[i].norm(dim=0) * self.sensitivity_previous[i].norm(dim=0) + 1e-15)
                increase_index = torch.where(sensitivity_product > 0)[0]
                decrease_index = torch.where(sensitivity_product <= 0)[0]
                self._max_step_length[i][increase_index] = torch.clamp(self._max_step_length[i][increase_index] * self._step_length_increase,
                                                                        max=self._max_step_length_max)
                self._max_step_length[i][decrease_index] = torch.clamp(self._max_step_length[i][decrease_index] * self._step_length_decay,
                                                                        min=self._max_step_length_max * self._step_length_min_ratio)
          


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
        self.params_update.update_variables(x_change=x, max_step_length=self._max_step_length)

        # Calculate the objective function value
        r, rdu, rdu2 = self.params_update.get_geometry_values()

        constraints_value: list[torch.Tensor] = []
        for constraints in self.constraints_funcs.values():
            constraints_value.append(constraints(r=r, rdu=rdu, rdu2=rdu2))

        obj_value: list[torch.Tensor] = []
        for obj_func in self.obj_funcs.values():
            obj_value.append(obj_func(r=r, rdu=rdu, rdu2=rdu2))

        # enroll the design variables
        self.params_update.set_parameters(xlist=x0)

        if return_list:
            return obj_value, constraints_value
        else:
            return sum(obj_value) + sum(constraints_value)

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
            if self.iteration_total % 10 == 0:
                with torch.no_grad():
                    obj_values, constraints_values = self.closure(x=variables, return_list=True)

                # print the objective function value
                # Print a pretty table showing objective values and iteration progress
                # Clear previous output (move cursor up and clear lines)
                if iteration > 0:
                    print("\033[F\033[K" * 4, end="\r")

                headers = ["Iteration"] + ["Total"] + list(self.obj_funcs.keys()) + list(self.constraints_funcs.keys())
                data = [[f"{iteration+1}/{self.max_step_iter}"] +
                        [f"{sum(obj_values).item():.6e}"] +
                        [f"{val.item():.6e}" for val in obj_values] +
                        [f"{val.item():.6e}" for val in constraints_values]]

                string = tabulate(data, headers=headers, tablefmt="grid")
                print(string, end="\r")

        return variables.detach().clone()
