from __future__ import annotations

from typing import cast

import numpy as np
import torch

from ..constants import CONSTANT
from ..optcore import BaseUpdater
from ..optcore.strategies import UpdateStrategy
from .boundary_part import BoundaryPart
from .surfaces import BaseSurface


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

    from . import objectivefuncs, strategies

    update_kind: str = "geometry"
    """This updater updates a geometry collection (``params.geometry``)."""

    _lbfgs_memory_pairs = CONSTANT.KERNEL.OPTIMIZER.LBFGS_SHAPE_MEMORY_PAIRS

    target_type = BoundaryPart
    """Only boundary Parts can be updated by this shape updater."""

    def __init__(
        self,
        interface_name: str | None = None,
        max_step_iter: int = CONSTANT.KERNEL.SHAPE_UPDATE.MAX_STEP_ITERATIONS,
        max_step_length: float = CONSTANT.KERNEL.SHAPE_UPDATE.MAX_STEP_LENGTH,
        *,
        update_strategy: UpdateStrategy | None = None,
    ) -> None:
        """Initialize the Updater class with the given parameters.

        Only the name of the Part is stored; :class:`Updaters` resolves and hands over the Part
        while initializing, so a misplaced name fails before the optimization loop and this updater
        never holds the whole model parameters.

        Args:
            interface_name (str | None): Name of the boundary Part interface this updater owns.  The
                registration ``name`` supplies it when omitted.
            max_step_iter (int): Maximum optimizer steps in a single subproblem solve.
            max_step_length (float): The maximum step length for each surface in the optimization
                process.
            update_strategy (UpdateStrategy | None): Policy for step limits, penalty weights and
                subproblem candidate selection.
        """

        super().__init__(
            interface_name,
            update_strategy=(
                self.strategies.AdaptiveShapeUpdate()
                if update_strategy is None
                else update_strategy
            ),
        )

        self.max_step_iter = max_step_iter
        """
        Maximum optimizer steps in a single subproblem solve.
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
        """The boundary part interface this updater updates.

        Returns:
            BoundaryPart: The boundary part interface this updater updates.
        """
        return cast(BoundaryPart, self.target)

    @property
    def surface_interfaces(self) -> list[BaseSurface]:
        """The surface interfaces of this updater's Part, in surface order.

        Returns:
            list[BaseSurface]: The surface interfaces of this updater's Part, in surface order.
        """
        return self.part.surface_interfaces()

    def pathlog_required(self) -> list[str]:
        """Return log subdirectories required by this component.

        Returns:
            list[str]: Relative log subdirectory names required before persistence.
        """
        return ["geometryupdater"]

    def reinitialize(self, gradient: torch.Tensor, *args, **kwargs) -> None:
        """Initialize the parameters of the optimization process.

        Args:
            gradient (torch.Tensor): The gradient of the objective function.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """

        if not any(
            surface.is_updatable and surface.num_variables
            for surface in self.surface_interfaces
        ):
            return

        self._set_step_lengths(gradient)

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

        super().reinitialize(gradient)

    def initialize(self) -> None:
        """Register this updater's terms, then size the Part's step lengths.

        The Part is already bound (the updater manager resolves it and calls :meth:`bind_target`
        before this runs), so a wrong name or a Part without surfaces fails before the optimization
        loop.  Objective functions and constraints were registered when this updater was added to
        its :class:`Updaters` collection.
        """
        self._set_step_lengths(None)

    def _set_step_lengths(self, gradient: torch.Tensor | None) -> None:
        """Set one movement limit per surface control point for this outer update."""
        self._max_step_length = self.update_strategy.step_lengths(
            self,
            [
                surface.get_surface_parameters().reshape(-1, 3)
                for surface in self.surface_interfaces
            ],
            self._max_step_length_max,
            gradient,
        )

    def closure(
        self,
        x: torch.Tensor,
        return_list: bool = False,
    ) -> torch.Tensor | tuple[list[torch.Tensor], list[torch.Tensor]]:
        """Evaluate the weighted total or the two lists of unweighted terms.

        Args:
            x (torch.Tensor): Flattened design parameters or perturbation vector evaluated by this
                method.
            return_list (bool): Return separate objective and penalty contributions instead of their
                scalar sum.

        Returns:
            torch.Tensor | tuple[list[torch.Tensor], list[torch.Tensor]]: Weighted scalar objective,
                or (physical_terms, raw_penalties) when return_list is True. Target parameters are
                restored before returning.
        """
        # save the current point
        x0 = self.part.get_parameters()

        try:
            self.part.update_variables(
                x_change=x, max_step_length=self._max_step_length
            )
            r, rdu, rdu2 = self.part.get_geometry_values()
            constraints_value = [
                constraint(r=r, rdu=rdu, rdu2=rdu2)
                for constraint in self.constraints_funcs.values()
            ]
            obj_value = [
                objective(r=r, rdu=rdu, rdu2=rdu2)
                for objective in self.obj_funcs.values()
            ]
        finally:
            self.part.set_parameters(x0)

        if return_list:
            return obj_value, constraints_value
        return sum(obj_value) + sum(self._weighted_constraints(constraints_value))

    def update(self) -> torch.Tensor | None:
        """Solve the shape subproblem and screen its proposed update.

        Returns:
            torch.Tensor | None: Accepted perturbation, or None when no surface can be updated.
        """

        if not any(
            surface.is_updatable and surface.num_variables
            for surface in self.surface_interfaces
        ):
            return

        origin = torch.zeros_like(torch.cat(self.part.get_parameters()))
        return self.update_strategy.solve_update(self, origin)

    def update_variables(self, dx: torch.Tensor) -> None:
        """Commit the update using the subproblem's frozen step limits.

        Args:
            dx (torch.Tensor): Proposed design-variable increment in flattened parameter order.
        """
        self.part.update_variables(x_change=dx, max_step_length=self._max_step_length)

    def save(self, foldpath, iteration):
        """Save the UpdaterBoundaryPart state.

        Args:
            foldpath: Root log directory containing this component's namespaced state files.
            iteration: Iteration index associated with the saved or current model state.
        """
        step_length_numpy = [
            self._max_step_length[i].detach().cpu().numpy()
            for i in range(len(self._max_step_length))
        ]
        np.savez(self._state_path(foldpath, iteration), *step_length_numpy)

    def load(self, foldpath, iteration):
        """Load the UpdaterBoundaryPart state.

        Args:
            foldpath: Root log directory containing this component's namespaced state files.
            iteration: Iteration index associated with the saved or current model state.
        """
        data = np.load(self._state_path(foldpath, iteration))
        for i in range(len(self._max_step_length)):
            self._max_step_length[i] = torch.tensor(data["arr_%d" % i]).to(
                torch.get_default_device()
            )
