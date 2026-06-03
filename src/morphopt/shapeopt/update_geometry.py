
import numpy as np

import torch

from ..optcore.modelparams.params import Params
from . import GeometryParams
from tabulate import tabulate
from ..optcore import BaseUpdater

class UpdaterGeometries(BaseUpdater):
    """
    The Updater class is responsible for updating the parameters of the optimization process.
    It contains methods to update the parameters based on the optimization algorithm used.
    """
    from . import objectivefuncs

    def __init__(self, params: Params, max_step_iter: int = 100, max_step_length: float = 0.5, reset_sensitivity_scaler_per_iter: int = 1) -> None:
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

        self._delta_control_points_previous: list[np.ndarray] = None
        """
        The previous change in control points for each surface.
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

        self._step_length_increase: float = 1.5
        """
        The increase factor for the step length relative to the maximum step length.
        """
 
        self.if_update: list[bool] = None
        """
        A list indicating whether each surface needs to be updated.
        True means the surface needs to be updated, False means it does not.
        """

    def pathlog_required(self):
        return ['geometryupdater']

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

        # get the weights for the points in the optimization process
        self._weight_points = self.params_update.get_points_weight()

        # initialize the objective function
        r0, rdu0, rdu20 = self.params_update.get_geometry_values()

        # initialize the shape derivative sensitivity
        self._initialize_objectives(gradient=gradient, r0=r0, rdu0=rdu0, rdu20=rdu20)
        
        # get the total sensitivity
        sensitivity = self._get_total_sensitivity()

        # initialize the constraint functions
        self._initialize_constraints(r0=r0, rdu0=rdu0, rdu20=rdu20, sensitivity=sensitivity)
            
        # initialize the optimizer
        self._initialize_optimizer()

        # initialize the step length
        for i in range(len(self._max_step_length)):
            if (self._max_step_length[i].shape[0] != self.params.geometry.surface_list[i].control_points.flatten().shape[0] // 3):
                self._max_step_length[i] = self._max_step_length[i].mean().repeat(self.params.geometry.surface_list[i].num_variables // 3)

        # save the sensitivity for the next iteration
        self.sensitivity_previous = sensitivity
          
    def initialize(self):

        if self.if_update is None:
            self.if_update = [True for _ in range(self.params.geometry.num_surface)]

        if len(self._max_step_length) == 0:
            for i in range(self.params_update.num_surface):
                self._max_step_length.append(torch.ones(self.params.geometry.surface_list[i].num_variables // 3) * self._max_step_length_max * 0.5)

        for i in range(len(self._max_step_length)):
            if not self.if_update[i]:
                self._max_step_length[i] *= 0.0

    def _initialize_objectives(self, gradient: torch.Tensor, r0: list[torch.Tensor], rdu0: list[torch.Tensor], rdu20: list[torch.Tensor]) -> None:
        for obj_func in self.obj_funcs.values():
            obj_func.initialize(gradient=gradient, r0=r0, rdu0=rdu0, rdu20=rdu20, weights=self._weight_points)

    def _get_total_sensitivity(self) -> None:
        # get the total sensitivity
        sensitivity_all = []
        for obj_func in self.obj_funcs.values():
            sensitivity_all.append(obj_func.sensitivity)
        sensitivity: list[torch.Tensor] = sensitivity_all[0]
        for surf_ind in range(len(sensitivity)):
            for obj_ind in range(1, len(sensitivity_all)):
                sensitivity[surf_ind] += sensitivity_all[obj_ind][surf_ind]
        return sensitivity
    
    def _initialize_constraints(self, r0: list[torch.Tensor], rdu0: list[torch.Tensor], rdu20: list[torch.Tensor], sensitivity: list[torch.Tensor]) -> None:
        for constraints in self.constraints_funcs.values():
            constraints.initialize(r0=r0, rdu0=rdu0, rdu20=rdu20, sensitivity=sensitivity, weights=self._weight_points, if_update=self.if_update)

    def _initialize_optimizer(self) -> None:
        self.optimizer = UpdaterGeometries.Optimizer.LBFGS(closure=self.closure, num_limit=20, tol_error=1e-10)
        self.iteration_total = 0

    def _update_step_length(self, delta_control_points: list[np.ndarray]) -> None:

        # update the step length based on the number of variables
        if self._delta_control_points_previous is not None:
            for i in range(len(self._max_step_length)):
                # check if the mesh has improved
                if (self._delta_control_points_previous[i].shape != self.params.geometry.surface_list[i].control_points.shape):
                    self._max_step_length[i] = self._max_step_length[i].mean().repeat(self.params.geometry.surface_list[i].num_variables // 3)
                else:
                    delta_difference: np.ndarray = np.sum(self._delta_control_points_previous[i] * delta_control_points[i], axis=-1) / (np.linalg.norm(delta_control_points[i], axis=-1)) / np.linalg.norm(self._delta_control_points_previous[i], axis=-1)
                    delta_difference[np.isnan(delta_difference)] = 0.0

                    index_increase = (delta_difference > -0.5).flatten()
                    index_decrease = (delta_difference <= -0.5).flatten()
                    self._max_step_length[i][index_increase] = torch.clamp(self._max_step_length[i][index_increase] * self._step_length_increase,
                                                                          max=self._max_step_length_max)
                    self._max_step_length[i][index_decrease] = torch.clamp(self._max_step_length[i][index_decrease] * self._step_length_decay,
                                                                          min=self._max_step_length_max * self._step_length_min_ratio)
        for i in range(len(self._max_step_length)):
            if not self.if_update[i]:
                self._max_step_length[i] *= 0.0

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

    def update_variables(self, dx: torch.Tensor) -> None:
        """
        Update the variables of the surfaces.
        """
        control_points0 = self.params_update.get_control_points_list()
        control_points0 = [cp.detach().clone().cpu().numpy() for cp in control_points0]

        self.params_update.update_variables(x_change=dx, max_step_length=self._max_step_length)

        control_points_new = self.params_update.get_control_points_list()
        control_points_new = [cp.detach().clone().cpu().numpy() for cp in control_points_new]
        delta_control_points = [control_points_new[i] - control_points0[i] for i in range(len(control_points0))]
        self._update_step_length(delta_control_points=delta_control_points)

        self._delta_control_points_previous = [cp.copy() for cp in delta_control_points]

    def save(self, foldpath, iteration):
        step_length_numpy = [self._max_step_length[i].detach().cpu().numpy() for i in range(len(self._max_step_length))]
        data = np.savez(foldpath + self.pathlog_required()[0] + f"/step_length_{iteration}.npz", *step_length_numpy)

    def load(self, foldpath, iteration):
        data = np.load(foldpath + self.pathlog_required()[0] + f"/step_length_{iteration}.npz")
        for i in range(len(self._max_step_length)):
            self._max_step_length[i] = torch.tensor(data['arr_%d' % i]).to(torch.get_default_device())