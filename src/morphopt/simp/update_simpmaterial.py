from __future__ import annotations

import logging

import numpy as np
import torch
from tabulate import tabulate

from ..optcore import BaseUpdater
from .simpmaterial import SIMP_BSPFieldMaterials

logger = logging.getLogger(__name__)


class UpdaterSIMPMaterial(BaseUpdater):
    """
    One SIMP material interface, updated on its own.

    It updates **one material interface of one material collection**: the
    collection comes from the adder used in ``define_updater()``, the interface
    from the ``name`` of that call::

    ```python
    class Updater(morphopt.simp.Updaters):
        def define_updater(self) -> None:
            # this object optimizes the interface named "solid"
            self.add_material_updater(self.Density(), name="solid")

        class Density(morphopt.simp.UpdaterSIMPMaterial):
            def __init__(self):
                super().__init__(max_step_iter=50)   # no target here
    ```

    The updater is constructed empty: it holds neither ``Params`` nor the
    material collection, only the **name** of its interface.  The updater
    manager resolves and hands that one interface over while initializing
    (:meth:`bind_target`), and from then on :attr:`material` is the only model
    object this updater keeps.  Because the class is target-free, the same
    class can be registered again for another interface, each object resolving
    its own one.
    """

    from . import objectivefuncs

    update_kind: str = "materials"
    """This updater updates a material collection (``params.materials``)."""

    target_type = SIMP_BSPFieldMaterials
    """Only SIMP field materials carry the design variables being updated."""

    def __init__(
        self,
        interface_name: str = None,
        max_step_iter: int = 50,
        max_step_length: float = 1.0,
    ) -> None:
        """
        Initialize the Updater class with the given parameters.

        Only the name of the material interface is stored; :class:`Updaters`
        resolves and hands over the interface while initializing, so a
        misplaced name fails before the loop and this updater never holds the
        whole model parameters.

        Parameters:
            interface_name (str): Name of the material interface this updater
                updates (the ``name`` of its ``add_material_updater`` call does
                the same).
            max_step_iter (int): The maximum number of iterations for the sub-optimization process.
            max_step_length (float): The maximum step length for each material variable.
        """

        super().__init__(interface_name)

        self.max_step_iter = max_step_iter
        """
        The maximum number of iterations for the sub-optimization process.
        """

        self._delta_control_points_previous: np.ndarray | None = None
        """
        The previous change in material control points.
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

    def pathlog_required(self) -> list[str]:
        return ["materialupdater"]

    @property
    def material(self) -> SIMP_BSPFieldMaterials:
        """The material interface this updater updates."""
        if self._target is None:
            raise ValueError(
                f"{type(self).__name__} has no material interface yet: the "
                "updater manager hands it over while initializing, so give "
                "the updater the name used in "
                "add_material_updater(..., name=...)."
            )
        return self._target

    @property
    def num_variables(self) -> int:
        """Number of design variables of the owned material interface."""
        return self.material.get_design_values().numel()

    def reinitialize(
        self, gradient: torch.Tensor, *args: object, **kwargs: object
    ) -> None:
        """
        Initialize the parameters of the optimization process.

        Parameters:
            iter_now (int): The current iteration number.
        """

        params0 = [
            value.detach().clone() for value in self.material.get_parameters()
        ]
        cps0 = torch.cat([value.flatten() for value in params0])

        # initialize objective functions with material variables only
        self._initialize_objectives(gradient=gradient.flatten(), cps0=cps0)

        # initialize the constraint functions
        self._initialize_constraints(cps0=cps0, sensitivity=gradient.flatten())

        # initialize the optimizer
        self._initialize_optimizer()

        # initialize the step length
        num_vars = self.material.get_design_values().numel()
        if self._max_step_length is None or self._max_step_length.numel() != num_vars:
            if self._max_step_length is None:
                self._max_step_length = (
                    torch.ones(num_vars, device=torch.get_default_device())
                    * self._max_step_length_max
                    * 0.5
                )
            else:
                self._max_step_length = self._max_step_length.mean().repeat(num_vars)

        # save the sensitivity for the next iteration
        self.sensitivity_previous = gradient.flatten()

    def initialize(self) -> None:
        """Register this updater's terms, then size the step lengths.

        The interface is already bound (the updater manager resolves it and
        calls :meth:`bind_target` before this runs), so a wrong name or an
        interface without design variables fails before the loop.  Objective
        functions and constraints were registered when this updater was added
        to its :class:`Updaters` collection.
        """
        num_vars = self.material.get_design_values().numel()
        if self._max_step_length is None:
            self._max_step_length = (
                torch.ones(num_vars, device=torch.get_default_device())
                * self._max_step_length_max
                * 0.5
            )
        elif self._max_step_length.numel() != num_vars:
            self._max_step_length = self._max_step_length.mean().repeat(num_vars)

        if not self.if_update:
            self._max_step_length *= 0.0

    def _initialize_objectives(
        self, gradient: torch.Tensor, cps0: torch.Tensor
    ) -> None:
        for obj_func in self.obj_funcs.values():
            obj_func.initialize(
                gradient=gradient,
                cps0=cps0,
                material_params=self.material,
                step_length=self._max_step_length,
            )

    def _get_total_sensitivity(self) -> torch.Tensor:
        sensitivity_all = []
        for obj_func in self.obj_funcs.values():
            sensitivity_all.append(obj_func.sensitivity)
        if len(sensitivity_all) == 0:
            return torch.zeros_like(self.material.get_design_values())

        sensitivity = sensitivity_all[0].clone()
        for obj_ind in range(1, len(sensitivity_all)):
            sensitivity = sensitivity + sensitivity_all[obj_ind]
        return sensitivity

    def _initialize_constraints(
        self, cps0: torch.Tensor, sensitivity: torch.Tensor
    ) -> None:
        for constraints in self.constraints_funcs.values():
            constraints.initialize(
                cps0=cps0, sensitivity=sensitivity, material_params=self.material
            )

    def _initialize_optimizer(self) -> None:
        self.optimizer = UpdaterSIMPMaterial.Optimizer.LBFGS(
            closure=self.closure, num_limit=20, tol_error=1e-10
        )
        self.iteration_total = 0

    def _update_step_length(self, delta_control_points: np.ndarray) -> None:

        # update the step length based on the number of variables
        if self._delta_control_points_previous is not None:
            if self._delta_control_points_previous.shape != delta_control_points.shape:
                pass
            else:
                delta_difference = (
                    delta_control_points * self._delta_control_points_previous
                ).flatten()

                idx_positive = delta_difference > 0
                idx_negative = delta_difference < 0

                self._max_step_length[idx_positive] = torch.clamp(
                    self._max_step_length[idx_positive] * self._step_length_increase,
                    max=self._max_step_length_max,
                )

                self._max_step_length[idx_negative] = torch.clamp(
                    self._max_step_length[idx_negative] * self._step_length_decay,
                    min=self._max_step_length_max * self._step_length_min_ratio,
                )

        if not self.if_update:
            self._max_step_length *= 0.0

    def closure(
        self,
        x: torch.Tensor,
        return_list: bool = False,
    ) -> torch.Tensor | tuple[list[torch.Tensor], list[torch.Tensor]]:
        """
        The closure function for the optimization process.

        Parameters:
            x (torch.Tensor): The current point in the optimization process.

        Returns:
            float: The objective function value at the current point.
        """
        # Save every interface's current design tensor; one aggregate may
        # contain several independent SIMP fields.
        params0 = [
            value.detach().clone() for value in self.material.get_parameters()
        ]

        # Set the design variables to the current point
        self.material.update_variables(
            x_change=x, max_step_length=self._max_step_length
        )

        # Calculate the objective function value
        cps_now = self.material.get_design_values()

        constraints_value: list[torch.Tensor] = []
        for constraints in self.constraints_funcs.values():
            constraints_value.append(
                constraints(cps=cps_now, material_params=self.material)
            )

        obj_value: list[torch.Tensor] = []
        for obj_func in self.obj_funcs.values():
            obj_value.append(obj_func(cps=cps_now, material_params=self.material))

        # enroll the design variables
        # Restore every design interface after evaluating the trial point.
        self.material.set_parameters(params0)

        if return_list:
            return obj_value, constraints_value
        else:
            return sum(obj_value) + sum(constraints_value)

    def update(self) -> torch.Tensor:
        """
        Update the parameters of the optimization process.
        """

        # update the objective function
        variables = self.material.get_variables().detach().clone()

        # print the information
        logger.info("Start updating the materials...")

        low_step_length_iter = 0
        gk_new = None
        for iteration in range(self.max_step_iter):
            self.iteration_total += 1

            # get the current material variables
            alpha, delta_var, gk_new = self.optimizer.step(
                x_now=variables, gk_now=gk_new
            )
            variables.data += delta_var * alpha

            # check if the step length is too small
            if abs(alpha) < 1e-10:
                low_step_length_iter += 1

            if low_step_length_iter > 10:
                logger.info(
                    f"Low step length detected ({low_step_length_iter} iterations), stopping optimization."
                )
                break

            # get current objective function value
            if self.iteration_total % 10 == 0:
                with torch.no_grad():
                    obj_values, constraints_values = self.closure(
                        x=variables, return_list=True
                    )

                # print the objective function value
                # Print a pretty table showing objective values and iteration progress
                # Clear previous output (move cursor up and clear lines)
                if iteration > 0:
                    print("\033[F\033[K" * 4, end="\r")

                headers = (
                    ["Iteration"]
                    + ["Total"]
                    + list(self.obj_funcs.keys())
                    + list(self.constraints_funcs.keys())
                )
                data = [
                    [f"{iteration + 1}/{self.max_step_iter}"]
                    + [f"{sum(obj_values).item():.6e}"]
                    + [f"{val.item():.6e}" for val in obj_values]
                    + [f"{val.item():.6e}" for val in constraints_values]
                ]

                string = tabulate(data, headers=headers, tablefmt="grid")
                print(string, end="\r")
                logger.debug("\n" + string)

        return variables.detach().clone()

    def update_variables(self, dx: torch.Tensor) -> None:
        """
        Update the variables of the materials.
        """
        design_values0 = (
            self.material.get_design_values().detach().clone().cpu().numpy()
        )

        self.material.update_variables(
            x_change=dx, max_step_length=self._max_step_length
        )

        design_values_new = (
            self.material.get_design_values().detach().clone().cpu().numpy()
        )
        delta_design_values = design_values_new - design_values0
        self._update_step_length(delta_control_points=delta_design_values)

        self._delta_control_points_previous = delta_design_values.copy()

    def save(self, foldpath: str, iteration: int) -> None:
        step_length_numpy = self._max_step_length.detach().cpu().numpy()
        np.savez_compressed(
            self._state_path(foldpath, iteration),
            step_length=step_length_numpy.astype(np.float16),
        )

    def load(self, foldpath: str, iteration: int) -> None:
        data = np.load(self._state_path(foldpath, iteration))
        design = self.material.get_design_values()
        self._max_step_length = (
            torch.tensor(data["step_length"]).to(design.device).to(design.dtype)
        )
