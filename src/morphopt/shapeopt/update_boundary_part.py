from __future__ import annotations

import logging
from typing import cast

import numpy as np
import torch
from tabulate import tabulate

from ..constants import CONSTANT
from ..optcore import BaseUpdater
from ..optcore.strategies import ConstraintWeightStrategy, StepLengthStrategy
from .boundary_part import BoundaryPart
from .surfaces import BaseSurface

logger = logging.getLogger(__name__)


class UpdaterBoundaryPart(BaseUpdater):
    """
    One boundary part interface, updated on its own.

    It updates **one boundary Part of one geometry collection**: the collection
    comes from the adder used in ``define_updater()``, the Part from the
    ``name`` of that call::

    ```python
    class Updater(morphopt.Updaters):
        def define_updater(self) -> None:
            # this object optimizes the Part named "body"
            self.add_geometry_updater(self.Shape(), name="body")

        class Shape(morphopt.UpdaterBoundaryPart):
            def __init__(self):
                super().__init__(max_step_iter=200)   # no target here

            def define_objective(self) -> None:
                self.add_objective_function(self.objectivefuncs.ShapeDerivative())
    ```

    The updater is constructed empty: it holds neither ``Params`` nor the
    geometry collection, only the **name** of its Part.  The updater manager
    resolves and hands that one Part over while initializing
    (:meth:`bind_target`), and from then on :attr:`part` is the only model
    object this updater keeps.  Because the
    class is target-free, the same class can be registered again for another
    Part (``name="leg"``), each object resolving its own Part.
    """

    from . import objectivefuncs

    update_kind: str = "geometry"
    """This updater updates a geometry collection (``params.geometry``)."""

    target_type = BoundaryPart
    """Only boundary Parts can be updated by this shape updater."""

    def __init__(
        self,
        interface_name: str | None = None,
        max_step_iter: int = CONSTANT.KERNEL.SHAPE_UPDATE.MAX_STEP_ITERATIONS,
        max_step_length: float = CONSTANT.KERNEL.SHAPE_UPDATE.MAX_STEP_LENGTH,
        *,
        step_length_strategy: StepLengthStrategy | None = None,
        constraint_weight_strategy: ConstraintWeightStrategy | None = None,
    ) -> None:
        """
        Initialize the Updater class with the given parameters.

        Only the name of the Part is stored; :class:`Updaters` resolves and
        hands over the Part while initializing, so a misplaced name fails
        before the optimization loop and this updater never holds the whole
        model parameters.

        Parameters:
            interface_name (str): Name of the boundary Part interface this
                updater owns.  The registration ``name`` supplies it when
                omitted.
            max_step_iter (int): The maximum number of iterations for the sub-optimization process.
            max_step_length (float): The maximum step length for each surface in the optimization process.
            step_length_strategy: Policy generating per-control-point step limits.
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

        self._weight_points: list[torch.Tensor] = []
        """
        The weights for the points in the optimization process.
        """

        self._max_step_length_max: float = max_step_length
        """
        The maximum step length for each surface in the optimization process.
        """

        self._max_step_length: list[torch.Tensor] = []
        """
        The current maximum step length for each surface in the optimization process.
        """

        self._low_step_length_tolerance: float = (
            CONSTANT.KERNEL.SHAPE_UPDATE.LOW_STEP_LENGTH_TOLERANCE
        )
        self._low_step_length_iteration_limit: int = (
            CONSTANT.KERNEL.SHAPE_UPDATE.LOW_STEP_LENGTH_ITERATION_LIMIT
        )
        self._status_log_interval: int = (
            CONSTANT.KERNEL.SHAPE_UPDATE.STATUS_LOG_INTERVAL
        )

    @property
    def part(self) -> BoundaryPart:
        """The boundary part interface this updater updates."""
        return cast(BoundaryPart, self.target)

    @property
    def surface_interfaces(self) -> list[BaseSurface]:
        """The surface interfaces of this updater's Part, in surface order."""
        return self.part.surface_interfaces()

    def pathlog_required(self) -> list[str]:
        return ["geometryupdater"]

    def reinitialize(self, gradient: torch.Tensor, *args, **kwargs) -> None:
        """
        Initialize the parameters of the optimization process.

        Parameters:
            gradient (torch.Tensor): The gradient of the objective function.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """

        if not any(
            surface.is_updatable and surface.num_variables
            for surface in self.surface_interfaces
        ):
            return

        self._max_step_length = self._prepare_step_lengths(
            [
                surface.get_surface_parameters().reshape(-1, 3)
                for surface in self.surface_interfaces
            ],
            self._max_step_length_max,
            gradient,
        )

        # get the weights for the points of this Part in the optimization process
        self._weight_points = self.part.get_points_weight()

        # initialize the objective function
        r0, rdu0, rdu20 = self.part.get_geometry_values()

        # initialize the shape derivative sensitivity
        for obj_func in self.obj_funcs.values():
            obj_func.initialize(
                gradient=gradient,
                r0=r0,
                rdu0=rdu0,
                rdu20=rdu20,
                weights=self._weight_points,
                surfaces=self.surface_interfaces,
                part_interface=self.part,
            )

        # initialize the constraint functions
        for constraints in self.constraints_funcs.values():
            constraints.initialize(
                r0=r0,
                rdu0=rdu0,
                rdu20=rdu20,
                weights=self._weight_points,
                surfaces=self.surface_interfaces,
                part_interface=self.part,
            )

        self._prepare_constraint_weights(gradient)
        self._initialize_optimizer()

    def initialize(self) -> None:
        """Register this updater's terms, then size the Part's step lengths.

        The Part is already bound (the updater manager resolves it and calls
        :meth:`bind_target` before this runs), so a wrong name or a Part without
        surfaces fails before the optimization loop.  Objective functions and
        constraints were registered when this updater was added to its
        :class:`Updaters` collection.
        """
        self._max_step_length = self._prepare_step_lengths(
            [
                surface.get_surface_parameters().reshape(-1, 3)
                for surface in self.surface_interfaces
            ],
            self._max_step_length_max,
        )

    def _initialize_optimizer(self) -> None:
        self.optimizer = UpdaterBoundaryPart.Optimizer.LBFGS(
            closure=self.closure,
            num_limit=CONSTANT.KERNEL.OPTIMIZER.LBFGS_SHAPE_MEMORY_PAIRS,
            tol_error=CONSTANT.KERNEL.OPTIMIZER.LBFGS_CONVERGENCE_TOLERANCE,
        )
        self.iteration_total = 0

    def closure(
        self,
        x: torch.Tensor,
        return_list: bool = False,
    ) -> torch.Tensor | tuple[list[torch.Tensor], list[torch.Tensor]]:
        """Evaluate the weighted total or the two lists of unweighted terms."""
        # save the current point
        x0 = self.part.get_parameters()

        # Set the design variables to the current point
        self.part.update_variables(x_change=x, max_step_length=self._max_step_length)

        # Calculate the objective function value
        r, rdu, rdu2 = self.part.get_geometry_values()

        constraints_value: list[torch.Tensor] = []
        for constraints in self.constraints_funcs.values():
            constraints_value.append(constraints(r=r, rdu=rdu, rdu2=rdu2))

        obj_value: list[torch.Tensor] = []
        for obj_func in self.obj_funcs.values():
            obj_value.append(obj_func(r=r, rdu=rdu, rdu2=rdu2))

        # enroll the design variables
        self.part.set_parameters(x0)

        if return_list:
            return obj_value, constraints_value
        return sum(obj_value) + sum(self._weighted_constraints(constraints_value))

    def update(self) -> None:
        """
        Update the parameters of the optimization process.
        """

        if not any(
            surface.is_updatable and surface.num_variables
            for surface in self.surface_interfaces
        ):
            return

        # update the objective function
        variables = self.part.get_variables().detach().clone()

        # print the information
        logger.info("Start updating the surfaces...")

        low_step_length_iter = 0
        gk_new = None
        for iteration in range(self.max_step_iter):
            self.iteration_total += 1

            # get the current variables of the surfaces
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
        self.part.update_variables(x_change=dx, max_step_length=self._max_step_length)

    def save(self, foldpath, iteration):
        step_length_numpy = [
            self._max_step_length[i].detach().cpu().numpy()
            for i in range(len(self._max_step_length))
        ]
        np.savez(self._state_path(foldpath, iteration), *step_length_numpy)

    def load(self, foldpath, iteration):
        data = np.load(self._state_path(foldpath, iteration))
        for i in range(len(self._max_step_length)):
            self._max_step_length[i] = torch.tensor(data["arr_%d" % i]).to(
                torch.get_default_device()
            )
