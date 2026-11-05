from __future__ import annotations

import logging
from typing import cast

import numpy as np
import torch
from tabulate import tabulate

from ..constants import CONSTANT
from ..optcore import BaseUpdater
from ..optcore.strategies import ConstraintWeightStrategy, StepLengthStrategy
from .simpmaterial import SIMP_BSPFieldMaterials

logger = logging.getLogger(__name__)


class UpdaterSIMPMaterial(BaseUpdater):
    """
    One SIMP material interface, updated on its own.

    It updates **one material interface of one material collection**: the
    collection comes from the adder used in ``define_updater()``, the interface
    from the ``name`` of that call::

    ```python
    class Updater(morphopt.Updaters):
        def define_updater(self) -> None:
            # this object optimizes the interface named "solid"
            self.add_material_updater(self.Density(), name="solid")

        class Density(morphopt.UpdaterSIMPMaterial):
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
        max_step_iter: int = CONSTANT.KERNEL.SIMP_UPDATE.MAX_STEP_ITERATIONS,
        max_step_length: float = CONSTANT.KERNEL.SIMP_UPDATE.MAX_STEP_LENGTH,
        *,
        step_length_strategy: StepLengthStrategy | None = None,
        constraint_weight_strategy: ConstraintWeightStrategy | None = None,
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
            step_length_strategy: Policy generating per-variable step limits.
            constraint_weight_strategy: Policy selecting named penalty coefficients.
        """

        super().__init__(
            interface_name,
            step_length_strategy=step_length_strategy,
            constraint_weight_strategy=constraint_weight_strategy,
        )

        self.max_step_iter = max_step_iter
        """
        The maximum number of iterations for the sub-optimization process.
        """

        self._max_step_length_max: float = max_step_length
        """
        The maximum step length for each surface in the optimization process.
        """

        self._max_step_length: torch.Tensor | None = None
        """
        The current maximum step length for each material variable.
        """

        self._low_step_length_tolerance: float = CONSTANT.KERNEL.SIMP_UPDATE.LOW_STEP_LENGTH_TOLERANCE
        self._low_step_length_iteration_limit: int = CONSTANT.KERNEL.SIMP_UPDATE.LOW_STEP_LENGTH_ITERATION_LIMIT
        self._status_log_interval: int = CONSTANT.KERNEL.SIMP_UPDATE.STATUS_LOG_INTERVAL

        self.if_update: bool = True
        """
        A flag indicating whether the material variables need to be updated.
        """

    def pathlog_required(self) -> list[str]:
        return ["materialupdater"]

    @property
    def material(self) -> SIMP_BSPFieldMaterials:
        """The material interface this updater updates."""
        return cast(SIMP_BSPFieldMaterials, self.target)

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
        self._max_step_length = self._prepare_step_lengths(
            [cps0.reshape(-1, 1)], self._max_step_length_max, gradient,
        )[0]
        if not self.if_update:
            self._max_step_length.zero_()

        # initialize objective functions with material variables only
        self._initialize_objectives(gradient=gradient.flatten(), cps0=cps0)

        # initialize the constraint functions
        self._initialize_constraints(cps0=cps0, sensitivity=gradient.flatten())

        self._prepare_constraint_weights(gradient)
        # initialize the optimizer
        self._initialize_optimizer()

    def initialize(self) -> None:
        """Register this updater's terms, then size the step lengths.

        The interface is already bound (the updater manager resolves it and
        calls :meth:`bind_target` before this runs), so a wrong name or an
        interface without design variables fails before the loop.  Objective
        functions and constraints were registered when this updater was added
        to its :class:`Updaters` collection.
        """
        self._max_step_length = self._prepare_step_lengths(
            [self.material.get_design_values().reshape(-1, 1)],
            self._max_step_length_max,
        )[0]
        if not self.if_update:
            self._max_step_length.zero_()

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

    def _initialize_constraints(
        self, cps0: torch.Tensor, sensitivity: torch.Tensor
    ) -> None:
        for constraints in self.constraints_funcs.values():
            constraints.initialize(
                cps0=cps0, sensitivity=sensitivity, material_params=self.material
            )

    def _initialize_optimizer(self) -> None:
        self.optimizer = UpdaterSIMPMaterial.Optimizer.LBFGS(
            closure=self.closure,
            num_limit=CONSTANT.KERNEL.OPTIMIZER.LBFGS_MATERIAL_MEMORY_PAIRS,
            tol_error=CONSTANT.KERNEL.OPTIMIZER.LBFGS_CONVERGENCE_TOLERANCE,
        )
        self.iteration_total = 0

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
            return sum(obj_value) + sum(self._weighted_constraints(constraints_value))

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
            if abs(alpha) < self._low_step_length_tolerance:
                low_step_length_iter += 1

            if low_step_length_iter > self._low_step_length_iteration_limit:
                logger.info(
                    f"Low step length detected ({low_step_length_iter} iterations), stopping optimization."
                )
                break

            # get current objective function value
            if self.iteration_total % self._status_log_interval == 0:
                with torch.no_grad():
                    obj_values, raw_constraints = self.closure(
                        x=variables, return_list=True
                    )
                    constraints_values = self._weighted_constraints(raw_constraints)

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
                    + [f"{(sum(obj_values) + sum(constraints_values)).item():.6e}"]
                    + [f"{val.item():.6e}" for val in obj_values]
                    + [f"{val.item():.6e}" for val in constraints_values]
                ]

                string = tabulate(data, headers=headers, tablefmt="grid")
                print(string, end="\r")
                logger.debug("\n" + string)

        return variables.detach().clone()

    def update_variables(self, dx: torch.Tensor) -> None:
        """Commit the update using the subproblem's frozen step limits."""
        self.material.update_variables(
            x_change=dx, max_step_length=self._max_step_length
        )

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
