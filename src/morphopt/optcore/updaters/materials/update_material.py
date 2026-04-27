
import numpy as np

import torch
from .. import optimizer

from ...modelparams.params import Params
from ...modelparams import SIMPMaterials
from tabulate import tabulate
from ..base_updater import BaseUpdater

class UpdaterMaterials(BaseUpdater):
    """
    The Updater class is responsible for updating the parameters of the optimization process.
    It contains methods to update the parameters based on the optimization algorithm used.
    """
    from . import objectivefuncs

    def __init__(self, params: Params, max_step_iter: int = 50, max_step_length: float = 0.1, reset_sensitivity_scaler_per_iter: int = 1) -> None:
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

        self.constraints_funcs: dict[str, UpdaterMaterials.objectivefuncs.BaseConstraints] = {}
        """
        A list of penalty functions to be optimized. \n
        L = sum_{i=1}^{n} w_i * f_i(x)
        """

        self.obj_funcs: dict[str, UpdaterMaterials.objectivefuncs.BaseObjective] = {}
        """
        A list of objective functions to be optimized. \n
        L = sum_{i=1}^{n} w_i * f_i(x)
        """

        self._delta_control_points_previous: np.ndarray | None = None
        """
        The previous change in material control points.
        """

        self.params_update: SIMPMaterials = params.materials
        """
        The materials object that contains the design variables.
        """

        self._reset_sensitivity_scaler_per_iter = reset_sensitivity_scaler_per_iter
        """
        The number of iterations after which the scaler is reset.
        """

        self._max_step_length_max: float = max_step_length
        """
        The maximum step length for each surface in the optimization process.
        """

        self._max_step_length: torch.Tensor | None = None
        """
        The current maximum step length for each material variable.
        """

        self._step_length_min_ratio: float = 0.1
        """
        The minimum ratio for the step length relative to the maximum step length.
        """

        self._step_length_decay: float = 0.5
        """
        The decay factor for the step length relative to the maximum step length.
        """

        self._step_length_increase: float = 1.5
        """
        The increase factor for the step length relative to the maximum step length.
        """
 
        self.if_update: bool = True
        """
        A flag indicating whether the material variables need to be updated.
        """

    def pathlog_required(self):
        return ['materialupdater']

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

    def reinitialize(self, gradient: torch.Tensor, *args, **kwargs) -> None:
        """
        Initialize the parameters of the optimization process.

        Parameters:
            iter_now (int): The current iteration number.
        """

        cps0 = self.params_update._cps.detach().clone()

        # initialize objective functions with material variables only
        self._initialize_objectives(gradient=gradient, cps0=cps0)
        
        # get the total sensitivity
        sensitivity = self._get_total_sensitivity()

        # initialize the constraint functions
        self._initialize_constraints(cps0=cps0, sensitivity=sensitivity)
            
        # initialize the optimizer
        self._initialize_optimizer()

        # initialize the step length
        num_vars = self.params_update._cps.numel()
        if self._max_step_length is None or self._max_step_length.numel() != num_vars:
            if self._max_step_length is None:
                self._max_step_length = torch.ones(num_vars, device=torch.get_default_device()) * self._max_step_length_max * 0.5
            else:
                self._max_step_length = self._max_step_length.mean().repeat(num_vars)

        # save the sensitivity for the next iteration
        self.sensitivity_previous = sensitivity
          
    def initialize(self):
        num_vars = self.params_update._cps.numel()
        if self._max_step_length is None:
            self._max_step_length = torch.ones(num_vars, device=torch.get_default_device()) * self._max_step_length_max * 0.5
        elif self._max_step_length.numel() != num_vars:
            self._max_step_length = self._max_step_length.mean().repeat(num_vars)

        if not self.if_update:
            self._max_step_length *= 0.0

    def _initialize_objectives(self, gradient: torch.Tensor, cps0: torch.Tensor) -> None:
        for obj_func in self.obj_funcs.values():
            obj_func.initialize(gradient=gradient, cps0=cps0, material_params=self.params_update)

    def _get_total_sensitivity(self) -> torch.Tensor:
        sensitivity_all = []
        for obj_func in self.obj_funcs.values():
            sensitivity_all.append(obj_func.sensitivity)
        if len(sensitivity_all) == 0:
            return torch.zeros_like(self.params_update._cps)

        sensitivity = sensitivity_all[0].clone()
        for obj_ind in range(1, len(sensitivity_all)):
            sensitivity = sensitivity + sensitivity_all[obj_ind]
        return sensitivity
    
    def _initialize_constraints(self, cps0: torch.Tensor, sensitivity: torch.Tensor) -> None:
        for constraints in self.constraints_funcs.values():
            constraints.initialize(cps0=cps0, sensitivity=sensitivity, material_params=self.params_update)

    def _initialize_optimizer(self) -> None:
        self.optimizer = optimizer.LBFGS(closure=self.closure, num_limit=20, tol_error=1e-10)
        self.iteration_total = 0

    def _update_step_length(self, delta_control_points: np.ndarray) -> None:

        # update the step length based on the number of variables
        if self._delta_control_points_previous is not None:
            if self._delta_control_points_previous.shape != delta_control_points.shape:
                self._max_step_length = self._max_step_length.mean().repeat(delta_control_points.size)
            else:
                denom = np.linalg.norm(delta_control_points) * np.linalg.norm(self._delta_control_points_previous)
                if denom > 0:
                    delta_difference = np.sum(self._delta_control_points_previous * delta_control_points) / denom
                else:
                    delta_difference = 0.0

                if delta_difference > -0.5:
                    self._max_step_length = torch.clamp(self._max_step_length * self._step_length_increase,
                                                        max=self._max_step_length_max)
                else:
                    self._max_step_length = torch.clamp(self._max_step_length * self._step_length_decay,
                                                        min=self._max_step_length_max * self._step_length_min_ratio)

        if not self.if_update:
            self._max_step_length *= 0.0

    def closure(self, x: torch.Tensor, return_list=False) -> float:
        """
        The closure function for the optimization process.

        Parameters:
            x (torch.Tensor): The current point in the optimization process.

        Returns:
            float: The objective function value at the current point.
        """
        # save the current point
        cps0 = self.params_update._cps.detach().clone()

        # Set the design variables to the current point
        self.params_update.update_variables(x_change=x, max_step_length=self._max_step_length)

        # Calculate the objective function value
        cps_now = self.params_update._cps
        
        constraints_value: list[torch.Tensor] = []
        for constraints in self.constraints_funcs.values():
            constraints_value.append(constraints(cps=cps_now, material_params=self.params_update))

        obj_value: list[torch.Tensor] = []
        for obj_func in self.obj_funcs.values():
            obj_value.append(obj_func(cps=cps_now, material_params=self.params_update))

        # enroll the design variables
        self.params_update._cps = cps0

        if return_list:
            return obj_value, constraints_value
        else:
            return sum(obj_value) + sum(constraints_value)

    def update(self, gradient: torch.Tensor) -> torch.Tensor:
        """
        Update the parameters of the optimization process.
        """

        # initialize the optimizer
        self.reinitialize(gradient=gradient)

        # update the objective function
        variables = self.params_update.get_variables().detach().clone()

        # print the information
        print("\n\n")
        print("Start updating the materials...")


        low_step_length_iter = 0
        gk_new = None
        for iteration in range(self.max_step_iter):
            self.iteration_total += 1

            # get the current material variables
            alpha, delta_var, gk_new = self.optimizer.step(x_now=variables, gk_now= gk_new)
            variables.data += delta_var * alpha

            # check if the step length is too small
            if abs(alpha) < 1e-10:
                low_step_length_iter += 1

            if low_step_length_iter > 10:
                print(
                    f"Low step length detected ({low_step_length_iter} iterations), stopping optimization."
                )
                # break

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

    def update_variables(self, dx: torch.Tensor) -> None:
        """
        Update the variables of the materials.
        """
        control_points0 = self.params_update.get_control_points_list()[0].detach().clone().cpu().numpy()

        self.params_update.update_variables(x_change=dx, max_step_length=self._max_step_length)

        self.params_update._cps = torch.clamp(self.params_update._cps, 0.0, 1.0)

        control_points_new = self.params_update.get_control_points_list()[0].detach().clone().cpu().numpy()
        delta_control_points = control_points_new - control_points0
        self._update_step_length(delta_control_points=delta_control_points)

        self._delta_control_points_previous = delta_control_points.copy()

    def save(self, foldpath, iteration):
        step_length_numpy = self._max_step_length.detach().cpu().numpy()
        np.savez_compressed(foldpath + self.pathlog_required()[0] + f"/step_length_{iteration}.npz", 
                            step_length=step_length_numpy.astype(np.float16))

    def load(self, foldpath, iteration):
        data = np.load(foldpath + self.pathlog_required()[0] + f"/step_length_{iteration}.npz")
        self._max_step_length = torch.tensor(data['step_length']).to(self.params_update._cps.device).to(self.params_update._cps.dtype)