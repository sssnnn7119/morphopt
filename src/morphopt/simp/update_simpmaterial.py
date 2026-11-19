from __future__ import annotations

from typing import cast

import numpy as np
import torch

from ..constants import CONSTANT
from ..optcore import BaseUpdater
from ..optcore.strategies import UpdateStrategy
from .simpmaterial import SIMP_BSPFieldMaterials

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

    _lbfgs_memory_pairs = CONSTANT.KERNEL.OPTIMIZER.LBFGS_MATERIAL_MEMORY_PAIRS

    target_type = SIMP_BSPFieldMaterials
    """Only SIMP field materials carry the design variables being updated."""

    def __init__(
        self,
        interface_name: str = None,
        max_step_iter: int = CONSTANT.KERNEL.SIMP_UPDATE.MAX_STEP_ITERATIONS,
        max_step_length: float = CONSTANT.KERNEL.SIMP_UPDATE.MAX_STEP_LENGTH,
        *,
        update_strategy: UpdateStrategy | None = None,
    ) -> None:
        """Initialize the Updater class with the given parameters.

        Only the name of the material interface is stored; :class:`Updaters` resolves and hands over
        the interface while initializing, so a misplaced name fails before the loop and this updater
        never holds the whole model parameters.

        Args:
            interface_name (str): Name of the material interface this updater updates (the ``name``
                of its ``add_material_updater`` call does the same).
            max_step_iter (int): Maximum optimizer steps in a single subproblem solve.
            max_step_length (float): The maximum step length for each material variable.
            update_strategy (UpdateStrategy | None): Policy for step limits, penalty weights and
                subproblem candidate selection.
        """

        super().__init__(
            interface_name,
            update_strategy=update_strategy,
        )

        self.max_step_iter = max_step_iter
        """
        Maximum optimizer steps in a single subproblem solve.
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
        """Return log subdirectories required by this component.

        Returns:
            list[str]: Relative log subdirectory names required before persistence.
        """
        return ["materialupdater"]

    @property
    def material(self) -> SIMP_BSPFieldMaterials:
        """The material interface this updater updates.

        Returns:
            SIMP_BSPFieldMaterials: The material interface this updater updates.
        """
        return cast(SIMP_BSPFieldMaterials, self.target)

    @property
    def num_variables(self) -> int:
        """Number of design variables of the owned material interface.

        Returns:
            int: Number of scalar coordinates in this interface's active design vector.
        """
        return self.material.get_design_values().numel()

    def reinitialize(
        self, gradient: torch.Tensor, *args: object, **kwargs: object
    ) -> None:
        """Initialize the parameters of the optimization process.

        Args:
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """

        cps0 = torch.cat([value.flatten() for value in self.material.get_parameters()])
        self._set_step_lengths(cps0, gradient)

        # initialize objective functions with material variables only
        self._initialize_objectives(gradient=gradient.flatten(), cps0=cps0)

        # initialize the constraint functions
        self._initialize_constraints(cps0=cps0, sensitivity=gradient.flatten())

        super().reinitialize(gradient)

    def initialize(self) -> None:
        """Register this updater's terms, then size the step lengths.

        The interface is already bound (the updater manager resolves it and calls
        :meth:`bind_target` before this runs), so a wrong name or an interface without design
        variables fails before the loop.  Objective functions and constraints were registered when
        this updater was added to its :class:`Updaters` collection.
        """
        self._set_step_lengths(self.material.get_design_values(), None)

    def _set_step_lengths(self, values: torch.Tensor, gradient: torch.Tensor | None) -> None:
        """Apply the policy to material controls, using zero movement for a fixed material."""
        if self.if_update:
            self._max_step_length, = self.update_strategy.step_lengths(
                self, [values.reshape(-1, 1)], self._max_step_length_max, gradient,
            )
        else:
            self._max_step_length = values.new_zeros(values.numel())

    def _initialize_objectives(
        self, gradient: torch.Tensor, cps0: torch.Tensor
    ) -> None:
        """Initialize objectives.

        Args:
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.
            cps0 (torch.Tensor): Reference SIMP control variables at the start of the subproblem.
        """
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
        """Initialize constraints.

        Args:
            cps0 (torch.Tensor): Reference SIMP control variables at the start of the subproblem.
            sensitivity (torch.Tensor): Physical sensitivity supplied by the updater; it is not
                normalized here.
        """
        for constraints in self.constraints_funcs.values():
            constraints.initialize(
                cps0=cps0, sensitivity=sensitivity, material_params=self.material
            )

    def closure(
        self,
        x: torch.Tensor,
        return_list: bool = False,
    ) -> torch.Tensor | tuple[list[torch.Tensor], list[torch.Tensor]]:
        """Evaluate a trial material field and restore the original parameters.

        Args:
            x (torch.Tensor): Trial perturbation in material design coordinates.
            return_list (bool): Return the individual unweighted terms when true.

        Returns:
            torch.Tensor | tuple[list[torch.Tensor], list[torch.Tensor]]: Weighted loss,
                or the separate physical and penalty terms.
        """
        params0 = [value.detach().clone() for value in self.material.get_parameters()]
        try:
            self.material.update_variables(x_change=x, max_step_length=self._max_step_length)
            cps = self.material.get_design_values()
            penalties = [
                term(cps=cps, material_params=self.material) for term in self.constraints_funcs.values()
            ]
            objectives = [
                term(cps=cps, material_params=self.material) for term in self.obj_funcs.values()
            ]
        finally:
            self.material.set_parameters(params0)

        if return_list:
            return objectives, penalties
        return sum(objectives) + sum(self._weighted_constraints(penalties))

    def update(self) -> torch.Tensor:
        """Solve the material subproblem from its current design coordinates.

        Returns:
            torch.Tensor: Material update selected by the update strategy.
        """
        origin = self.material.get_variables().detach()
        return self.update_strategy.solve_update(self, origin)

    def update_variables(self, dx: torch.Tensor) -> None:
        """Commit the update using the subproblem's frozen step limits.

        Args:
            dx (torch.Tensor): Proposed design-variable increment in flattened parameter order.
        """
        self.material.update_variables(
            x_change=dx, max_step_length=self._max_step_length
        )

    def save(self, foldpath: str, iteration: int) -> None:
        """Save the UpdaterSIMPMaterial state.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        step_length_numpy = self._max_step_length.detach().cpu().numpy()
        np.savez_compressed(
            self._state_path(foldpath, iteration),
            step_length=step_length_numpy.astype(np.float16),
        )

    def load(self, foldpath: str, iteration: int) -> None:
        """Load the UpdaterSIMPMaterial state.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        data = np.load(self._state_path(foldpath, iteration))
        design = self.material.get_design_values()
        self._max_step_length = (
            torch.tensor(data["step_length"]).to(design.device).to(design.dtype)
        )
