import os
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal, TypeAlias

import numpy as np
import torch

import morphopt

from ..constants import CONSTANT
from .modelparams import GeometryParams, MaterialsParams, Params
from .modelparams.materials.base_material import BaseMaterial
from .modelparams.parts.base_part import BasePart
from .protocal import ProtocalHistory, ProtocalInitializable, ProtocalSavable
from .strategies import (
    ConstantConstraintWeights,
    ConstraintWeightStrategy,
    FixedStepLength,
    StepLengthStrategy,
)

UpdaterCollection: TypeAlias = GeometryParams | MaterialsParams
"""Collections from which :class:`Updaters` resolves a target."""

UpdaterTarget: TypeAlias = BasePart | BaseMaterial
"""Objects that a :class:`BaseUpdater` can own after binding."""

UpdaterTargetType: TypeAlias = type[UpdaterTarget] | tuple[type[UpdaterTarget], ...]
"""Accepted class specification for an updater target."""


class QuadraticHistory(ProtocalSavable):
    """Limited-memory SR1 or BFGS history, without dense Hessian storage.

    Each consumer owns an independent instance in its parameter coordinates.
    Physical objectives use SR1 to retain either sign of curvature, starting
    from a zero Hessian. Inner L-BFGS uses positive-curvature BFGS pairs and
    the matching inverse products. Without a pair the physical model is
    linear and the optimizer uses the identity preconditioner.
    Products require O(memory_size * num_parameters) work and storage;
    no dense Hessian or inverse Hessian is constructed.
    """

    def __init__(
        self,
        memory_size: int = CONSTANT.KERNEL.UPDATER_OBJECTIVES.QUADRATIC_MEMORY_PAIRS,
        *,
        update_method: Literal["bfgs", "sr1"] = "bfgs",
    ) -> None:
        """Initialize QuadraticHistory and its configuration state.

        Args:
            memory_size (int): Positive maximum number of retained design/gradient difference pairs.
            update_method (Literal['bfgs', 'sr1']): Curvature update: "sr1" retains either sign;
                "bfgs" accepts positive-curvature pairs.
        """
        if (
            isinstance(memory_size, bool)
            or not isinstance(memory_size, int)
            or memory_size < 1
        ):
            raise ValueError("memory_size must be a positive integer.")
        if update_method not in ("bfgs", "sr1"):
            raise ValueError("update_method must be 'bfgs' or 'sr1'.")
        self.memory_size = memory_size
        self.update_method = update_method
        self.clear()

    def clear(self) -> None:
        """Discard observations and matrix factors, preserving the memory limit."""
        self.point: torch.Tensor | None = None
        self.gradient: torch.Tensor | None = None
        self._layout: tuple[int, ...] = ()
        self._steps: list[torch.Tensor] = []
        self._changes: list[torch.Tensor] = []
        self._products: list[torch.Tensor] = []
        self._step_products: list[torch.Tensor] = []
        self._curvatures: list[torch.Tensor] = []
        self._scale: torch.Tensor | None = None

    @property
    def history_size(self) -> int:
        """Number of retained observation pairs.

        Returns:
            int: Number of retained design/gradient difference pairs.
        """
        return len(self._steps)

    def observe(
        self,
        point: torch.Tensor,
        gradient: torch.Tensor,
        layout: tuple[int, ...] = (),
    ) -> None:
        """Record one point and the gradient of the consumer's objective.

        A changed parameter count or block layout discards previous pairs. BFGS requires positive
        curvature; SR1 requires a sufficiently large residual denominator, of either sign. Rejected
        pairs still replace the observation anchor. Physical objectives supply unscaled FEA
        gradients; optimizers supply gradients of the complete inner objective.

        Args:
            point (torch.Tensor): Current design coordinates, flattened and copied as the new
                observation anchor.
            gradient (torch.Tensor): Objective gradient in the same parameter coordinates;
                physical-proxy consumers supply native, unscaled FEA derivatives.
            layout (tuple[int, ...]): Parameter-block sizes used to invalidate history after a
                variable-layout change.
        """
        point = point.detach().clone().flatten()
        gradient = gradient.detach().clone().flatten().to(point)
        if point.shape != gradient.shape:
            raise ValueError(
                "Surrogate parameters and gradient must have the same size."
            )
        if not torch.isfinite(point).all() or not torch.isfinite(gradient).all():
            raise ValueError("Surrogate parameters and gradient must be finite.")
        if self.point is not None and (
            self.point.shape != point.shape or self._layout != layout
        ):
            self.clear()
        if self.point is not None:
            step = point - self.point
            change = gradient - self.gradient
            if self.update_method == "sr1":
                retain = self._sr1_factors(step, change) is not None
            else:
                retain = step @ change > (
                    CONSTANT.KERNEL.OPTIMIZER.BFGS_CURVATURE_TOLERANCE
                    * step.norm()
                    * change.norm()
                )
            if retain:
                self._steps.append(step)
                self._changes.append(change)
                self._steps = self._steps[-self.memory_size :]
                self._changes = self._changes[-self.memory_size :]
        self.point, self.gradient, self._layout = point, gradient, layout
        self._build_hessian()

    def _sr1_factors(
        self, step: torch.Tensor, change: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor] | None:
        """Form the signed rank-one correction; skip unreliable denominators.

        Args:
            step (torch.Tensor): Registered load-case name whose work conditions must be active.
            change (torch.Tensor): Difference between the current and previous physical gradients.

        Returns:
            tuple[torch.Tensor, torch.Tensor] | None: Form the signed rank-one correction; skip
                unreliable denominators.
        """
        residual = change - self.hessian_product(step)
        denominator = residual @ step
        threshold = (
            CONSTANT.KERNEL.UPDATER_OBJECTIVES.SR1_DENOMINATOR_TOLERANCE
            * residual.norm()
            * step.norm()
        )
        if denominator.abs() > threshold:
            return residual, denominator
        return None

    def _build_hessian(self) -> None:
        """Replay retained pairs to rebuild the selected Hessian factors."""
        self._products = []
        self._step_products = []
        self._curvatures = []
        self._scale = None
        if not self._steps:
            return
        if self.update_method == "sr1":
            # A zero base leaves unobserved directions linear. Recheck each
            # denominator because evicting an old pair changes the replay.
            for step, change in zip(self._steps, self._changes):
                factors = self._sr1_factors(step, change)
                if factors is not None:
                    residual, denominator = factors
                    self._products.append(residual)
                    self._step_products.append(denominator)
            return
        step, change = self._steps[-1], self._changes[-1]
        self._scale = (change @ change) / (step @ change)
        for step, change in zip(self._steps, self._changes):
            product = self.hessian_product(step)
            self._products.append(product)
            self._step_products.append(step @ product)
            self._curvatures.append(step @ change)

    def hessian_product(self, vector: torch.Tensor) -> torch.Tensor:
        """Apply B, rather than the inverse-Hessian used for search directions.

        Args:
            vector (torch.Tensor): Vector multiplied by the stored Hessian or inverse-Hessian
                approximation.

        Returns:
            torch.Tensor: Hessian-vector product in the observed design-parameter coordinates.
        """
        if self.update_method == "sr1":
            result = torch.zeros_like(vector)
            for residual, denominator in zip(self._products, self._step_products):
                result = result + residual * (residual @ vector) / denominator
            return result
        if self._scale is None:
            return torch.zeros_like(vector)
        result = self._scale * vector
        for product, denominator, change, curvature in zip(
            self._products, self._step_products, self._changes, self._curvatures
        ):
            result = result - product * (product @ vector) / denominator
            result = result + change * (change @ vector) / curvature
        return result

    def inverse_hessian_product(self, vector: torch.Tensor) -> torch.Tensor:
        """Apply the matching inverse BFGS approximation by two-loop recursion.

        Before the first retained pair, return the input for a steepest-descent search direction.
        The outer objective independently uses a zero quadratic term until physical curvature
        becomes available.

        Args:
            vector (torch.Tensor): Vector multiplied by the stored Hessian or inverse-Hessian
                approximation.

        Returns:
            torch.Tensor: Inverse-BFGS product used to construct the inner search direction.

        Raises:
            ValueError: The history uses SR1; inverse products are defined here only for the inner BFGS optimizer.
        """
        if self.update_method != "bfgs":
            raise ValueError("Inverse Hessian products are only used with BFGS history.")
        if not self._steps:
            return vector.clone()
        result = vector.clone()
        coefficients = []
        for step, change, curvature in zip(
            reversed(self._steps), reversed(self._changes), reversed(self._curvatures)
        ):
            coefficient = (step @ result) / curvature
            coefficients.append(coefficient)
            result = result - coefficient * change
        result = result / self._scale
        for step, change, curvature, coefficient in zip(
            self._steps, self._changes, self._curvatures, reversed(coefficients)
        ):
            result = result + step * (coefficient - (change @ result) / curvature)
        return result

    def __call__(self, point: torch.Tensor) -> torch.Tensor:
        """Return g.T d + 0.5 d.T B d, with zero value at the anchor.

        Args:
            point (torch.Tensor): Design-vector coordinates at which the physical gradient was
                evaluated.

        Returns:
            torch.Tensor: Scalar g.T @ delta + 0.5 * delta.T @ B @ delta, with zero value at the
                latest observed point.
        """
        if self.point is None:
            raise RuntimeError(
                "Observe a gradient before evaluating the quadratic model."
            )
        delta = point.flatten() - self.point
        return self.gradient @ delta + 0.5 * (delta @ self.hessian_product(delta))

    def _state_path(self, foldpath: str, iteration: int) -> Path:
        """Locate this iteration inside the owner's history directory.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.

        Returns:
            Path: Locate this iteration inside the owner's history directory.
        """
        return Path(foldpath) / f"surrogate_{iteration}.npz"

    def save(self, foldpath: str, iteration: int) -> None:
        """Persist the latest observation and retained curvature pairs.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        path = self._state_path(foldpath, iteration)
        path.parent.mkdir(parents=True, exist_ok=True)
        size = self.point.numel() if self.point is not None else 0
        np.savez_compressed(
            path,
            observed=self.point is not None,
            point=(self.point.cpu().numpy() if self.point is not None else np.empty(0)),
            gradient=(
                self.gradient.cpu().numpy()
                if self.gradient is not None
                else np.empty(0)
            ),
            layout=np.asarray(self._layout, dtype=np.int64),
            steps=(
                torch.stack(self._steps).cpu().numpy()
                if self._steps
                else np.empty((0, size))
            ),
            changes=(
                torch.stack(self._changes).cpu().numpy()
                if self._changes
                else np.empty((0, size))
            ),
        )

    def load(self, foldpath: str, iteration: int) -> None:
        """Restore observations on the active default device and rebuild B.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        with np.load(self._state_path(foldpath, iteration), allow_pickle=False) as state:
            observed = state["observed"].item()
            self.point = torch.tensor(state["point"]) if observed else None
            self.gradient = torch.tensor(state["gradient"]) if observed else None
            self._layout = tuple(int(value) for value in state["layout"])
            self._steps = [
                torch.tensor(value) for value in state["steps"][-self.memory_size :]
            ]
            self._changes = [
                torch.tensor(value) for value in state["changes"][-self.memory_size :]
            ]
        self._build_hessian()


class BaseUpdater(ProtocalInitializable, ProtocalSavable, ProtocalHistory):
    """Base class for all sub-updaters.

    A sub-updater updates **one interface of one params collection**.  Both come
    from the ``add_*_updater`` call that registers it:

    * the **adder** states the collection (``add_geometry_updater`` ->
      ``params.geometry`` or ``add_material_updater`` -> ``params.materials``),
    * the ``name`` of that call is the interface it owns.

    The sub-updater itself stays empty: it holds neither ``Params`` nor the
    collection, only the **name** of its interface.  At initialization,
    :class:`Updaters` resolves that name in the owning collection and hands the
    updater the single resolved target.

    ```python
    class Updater(morphopt.Updaters):
        def define_updater(self) -> None:
            # one class, two objects, two different Parts:
            self.add_geometry_updater(self.Shape(), name="body")
            self.add_geometry_updater(self.Shape(), name="leg")
    ```

    ``update_kind`` names the collection of ``Params`` it works on (and is the
    key of the design gradient it consumes); the interface name names the object
    inside that collection (a boundary Part for geometry, a material interface
    for materials); ``interface_name=`` may also be given to the constructor,
    and then it wins over the registration name.

    A concrete sub-updater declares its accepted ``target_type`` and implements
    ``define_objective()``.  :class:`Updaters` resolves the target by name (or
    by the single matching interface) and passes that object to
    :meth:`bind_target`; the updater then keeps only that model object.

    The ``define_objective()`` hook registers objective functions and
    constraints.  The updater collection calls it once when the updater is
    registered, before initialization resolves the target interface.

    The constructor stays empty of model knowledge.  Runtime initialization is
    handled separately after the target has been resolved. Lifecycle hooks
    come from ``ProtocalInitializable``: concrete updaters implement
    ``initialize()`` for the bound target and ``reinitialize(gradient)`` for
    each new subproblem.
    """

    from . import strategies

    update_kind: str = ""
    """Kind of collection this updater updates (``geometry`` / ``materials``)."""

    target_type: UpdaterTargetType | None = None
    """Interface type accepted by this updater, or ``None`` for any target."""

    @property
    def interface_name(self) -> str:
        """Name of the interface this updater owns inside its collection.

        Returns:
            str: Name of the interface this updater owns inside its collection.
        """
        return self._interface_name

    @interface_name.setter
    def interface_name(self, value: str) -> None:
        """Set the interface name.

        Args:
            value (str): New interface name.
        """
        new_name = str(value).strip() if value else ""
        if new_name != self._interface_name:
            self._target = None
        self._interface_name = new_name

    @property
    def target(self) -> UpdaterTarget:
        """The model interface resolved for this updater.

        Returns:
            UpdaterTarget: The model interface resolved for this updater.
        """
        if self._target is None:
            raise ValueError(
                f"{type(self).__name__} has no target yet; the updater manager "
                "binds it during initialization."
            )
        return self._target

    def bind_target(self, target: UpdaterTarget | None = None) -> UpdaterTarget:
        """Store the already-resolved model target.

        Target lookup and type validation are centralized in :class:`Updaters`; subclasses only
        expose a domain-specific property such as ``part`` or ``material``.

        Args:
            target (UpdaterTarget | None): Target interface or selection receiving the operation.

        Returns:
            UpdaterTarget: Store the already-resolved model target.
        """
        if target is None:
            raise ValueError(
                f"{type(self).__name__} was initialized without a model target."
            )
        self._target = target
        resolved_name = target.name
        if resolved_name:
            self._interface_name = str(resolved_name)
        return target

    def _state_path(self, foldpath: str, iteration: int) -> str:
        """Return the namespaced state-file path for this updater.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.

        Returns:
            str: The namespaced state-file path for this updater.
        """
        directory = self.save_directory(foldpath, self.interface_name or "all")
        return os.path.join(directory, f"step_length_{iteration}.npz")

    class Optimizer:
        """Namespace for inner optimizers used by geometry and material updaters."""
        class BaseOpt:
            """Provide a differentiable objective, its gradient, and backtracking line search."""
            def __init__(self, closure: Callable[[torch.Tensor], float]):
                """Initialize BaseOpt and its configuration state.

                Args:
                    closure (Callable[[torch.Tensor], float]): Differentiable scalar subproblem objective
                        called by the inner optimizer.
                """
                self.closure = closure
                """
                the objective function to be optimized, which should return the objective value
                """

                self.grad = torch.func.jacrev(self.closure)
                """        the gradient of the objective function, which should return the gradient vector
                """

                # params for line search
                self._c1 = CONSTANT.KERNEL.OPTIMIZER.LINE_SEARCH_C1
                self._rou1 = CONSTANT.KERNEL.OPTIMIZER.LINE_SEARCH_BACKTRACK_RATIO

            def set_line_search_params(self, c1: float = None, rou1: float = None):
                """Set the parameters for the line search method.

                Args:
                    c1 (float): The parameter for the Wolfe condition.
                    rou1 (float): The parameter for the backtracking line search.
                """
                if c1 is not None:
                    self._c1 = c1
                if rou1 is not None:
                    self._rou1 = rou1

            def _LineSearchBacktracking(
                self,
                x0: torch.Tensor,
                dx: torch.Tensor,
                direction: torch.Tensor,
                alpha0: float = 1.0,
                obj0: float = None,
            ):
                """Backtracking line search to find the step length for the optimization process.

                Args:
                    x0 (torch.Tensor): The current point in the optimization process.
                    dx (torch.Tensor): The gradient vector at the current point.
                    direction (torch.Tensor): The search direction.
                    alpha0 (float): The initial step length.
                    obj0 (float): The initial objective value.

                Returns:
                    float: The step length that satisfies the Wolfe condition.
                """

                if obj0 is None:
                    obj0 = self.closure(x0)

                alpha = alpha0
                while True:
                    x_new = x0 + alpha * direction
                    with torch.no_grad():
                        obj_new = self.closure(x_new)
                    if (
                        ~torch.isnan(obj_new)
                        and ~torch.isinf(obj_new)
                        and obj_new < obj0 + self._c1 * alpha * dx.dot(direction)
                    ):
                        return alpha, obj_new
                    alpha *= self._rou1
                    if (
                        (alpha * direction).abs().max()
                        < CONSTANT.KERNEL.OPTIMIZER.LINE_SEARCH_MIN_STEP_TOLERANCE
                    ):
                        return 0.0, obj0

        class LBFGS(BaseOpt):
            """Solve the current inner objective using limited-memory positive-curvature BFGS updates.

            This optimizer approximates the complete inner loss. It is separate from the SR1 history
            used to model physical curvature across outer finite-element iterations.
            """
            def __init__(
                self,
                closure: Callable[[torch.Tensor], float],
                num_limit: int = CONSTANT.KERNEL.OPTIMIZER.LBFGS_MEMORY_PAIRS,
                tol_error: float = CONSTANT.KERNEL.OPTIMIZER.LBFGS_CONVERGENCE_TOLERANCE,
            ) -> None:
                """Initialize LBFGS and its configuration state.

                Args:
                    closure (Callable[[torch.Tensor], float]): Differentiable scalar subproblem objective
                        called by the inner optimizer.
                    num_limit (int): Maximum number of retained inner BFGS correction pairs.
                    tol_error (float): Convergence tolerance for the optimization or solver residual.
                """
                super().__init__(closure=closure)
                self.history = QuadraticHistory(memory_size=num_limit)

                self.tol_error = tol_error
                """
                the tolerance for the convergence of the optimization process
                """

            def step(
                self, x_now: torch.Tensor, gk_now: torch.Tensor | None = None
            ) -> tuple[float, torch.Tensor, torch.Tensor]:

                """Perform one limited-memory BFGS step with backtracking line search.

                Args:
                    x_now (torch.Tensor): Current flattened inner-optimization iterate.
                    gk_now (torch.Tensor | None): Gradient at x_now; None evaluates it using the objective
                        closure.

                Returns:
                    tuple[float, torch.Tensor, torch.Tensor]: Accepted line-search factor, design increment,
                        and gradient at the new inner iterate.
                """
                obj_now = self.closure(x_now)
                if gk_now is None:
                    gk_now: torch.Tensor = self.grad(x_now).flatten()

                gk_now.view(-1)[gk_now.view(-1).isnan()] = 0

                if self.history.point is None:
                    self.history.observe(x_now, gk_now)
                dk = self.history.inverse_hessian_product(-gk_now)
                if not torch.isfinite(dk).all() or (dk * gk_now).sum() > 0:
                    self.history.clear()
                    self.history.observe(x_now, gk_now)
                    dk = -gk_now

                # Without curvature, choose a trial displacement in variable
                # coordinates. Keep the objective, gradient and direction raw;
                # a fixed alpha=1 would stall objectives with small units.
                alpha0 = 1.0
                direction_size = dk.abs().max().item()
                if self.history.history_size == 0 and direction_size > 0:
                    alpha0 = (
                        CONSTANT.KERNEL.OPTIMIZER.LBFGS_INITIAL_VARIABLE_STEP
                        / direction_size
                    )
                # line search
                alpha, obj_new = self._LineSearchBacktracking(
                    x0=x_now, dx=gk_now, direction=dk, alpha0=alpha0, obj0=obj_now
                )

                if alpha == 0 or obj_new > obj_now:
                    self.history.clear()
                    return 0.0, torch.zeros_like(x_now), gk_now

                x_new = x_now + alpha * dk
                gk_new: torch.Tensor = self.grad(x_new).flatten()
                if (alpha * dk).abs().max() <= self.tol_error:
                    self.history.clear()
                else:
                    self.history.observe(x_new, gk_new)

                return alpha, dk, gk_new

    def __init__(
        self,
        interface_name: str | None = None,
        *,
        step_length_strategy: StepLengthStrategy | None = None,
        constraint_weight_strategy: ConstraintWeightStrategy | None = None,
    ) -> None:
        """Initialize the BaseUpdater.

        Only the name of the interface it owns is kept: the updater manager resolves and hands over
        the interface while initializing.

        Args:
            interface_name (str | None): Registered target name; None allows the updater collection
                to supply the name.
            step_length_strategy (StepLengthStrategy | None): Policy that freezes movement limits
                before solving the inner subproblem.
            constraint_weight_strategy (ConstraintWeightStrategy | None): Policy that freezes named
                penalty coefficients before the inner solve.
        """

        self._interface_name: str = (
            str(interface_name).strip() if interface_name else ""
        )
        """Name of the interface inside the owned collection ("" = infer it)."""

        self._target: UpdaterTarget | None = None
        """The model interface handed over during updater initialization."""

        self.obj_funcs: dict[str, object] = {}
        """Objective functions registered by this updater."""

        self.constraints_funcs: dict[str, object] = {}
        """Constraints registered by this updater."""

        self.step_length_strategy = (
            FixedStepLength() if step_length_strategy is None else step_length_strategy
        )
        self.constraint_weight_strategy = (
            ConstantConstraintWeights()
            if constraint_weight_strategy is None else constraint_weight_strategy
        )
        self.constraint_weights: dict[str, float] = {}
        self.iteration_total: int = 0
        self.objective_value: float | None = None
        """Current high-fidelity objective, supplied before building a subproblem."""

        self.optimizer: BaseUpdater.Optimizer.BaseOpt = None
        """The optimization algorithm used to update the design variables.
        This should be set to an instance of a subclass of Optimizer.BaseOpt.
        """

    def history_data(self) -> dict[str, object]:
        """Describe this iteration's coefficients without reevaluating the loss.

        Returns:
            dict[str, object]: Component-owned scalar or nested observations for the current
                iteration.
        """
        return {
            "iterations": self.iteration_total,
            "constraint_weights": self.constraint_weights,
            "constraint_weight_state": self.constraint_weight_strategy.history_data(),
        }

    def _prepare_step_lengths(
        self,
        parameters: Sequence[torch.Tensor],
        maximum: float,
        gradient: torch.Tensor | None = None,
    ) -> list[torch.Tensor]:
        """Evaluate the selected policy and freeze its per-block limits.

        Args:
            parameters (Sequence[torch.Tensor]): Parameter values in the order required by the
                selected interface.
            maximum (float): Configured upper limit on each design-variable movement.
            gradient (torch.Tensor | None): Unscaled physical objective gradient in the target's
                design-variable order.

        Returns:
            list[torch.Tensor]: Frozen per-row movement limits, in target parameter-block order.
        """
        steps = self.step_length_strategy(self, parameters, maximum, gradient)
        if len(steps) != len(parameters):
            raise ValueError("Step lengths must match the parameter blocks.")
        for step, parameter in zip(steps, parameters):
            if step.shape != (len(parameter),):
                raise ValueError("Step lengths must contain one value per parameter row.")
            if not torch.isfinite(step).all() or (step < 0).any():
                raise ValueError("Step lengths must be finite and nonnegative.")
        return [step.detach().clone() for step in steps]

    def _prepare_constraint_weights(self, gradient: torch.Tensor) -> None:
        """Evaluate the selected policy once, after initializing all terms.

        Args:
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.
        """
        weights = self.constraint_weight_strategy(self, gradient)
        if weights.keys() != self.constraints_funcs.keys():
            raise ValueError("Constraint weights must match the registered constraint names.")
        if any(not math.isfinite(weight) or weight < 0 for weight in weights.values()):
            raise ValueError("Constraint weights must be finite and nonnegative.")
        self.constraint_weights = {name: float(weight) for name, weight in weights.items()}

    def _weighted_constraints(self, values: list[torch.Tensor]) -> list[torch.Tensor]:
        """Weighted penalty contributions shared by loss evaluation and logging.

        Args:
            values (list[torch.Tensor]): Values aligned with the parameters or records processed by
                this interface.

        Returns:
            list[torch.Tensor]: Weighted penalty contributions shared by loss evaluation and
                logging.
        """
        return [
            self.constraint_weights[name] * value
            for name, value in zip(self.constraints_funcs, values, strict=True)
        ]

    def define_objective(self) -> None:
        """Register this updater's objective functions and constraints.

        Scheme-specific updaters override this hook and call :meth:`add_objective_function` /
        :meth:`add_constraints`.  It is called once by :meth:`Updaters.add_updater`, so this hook
        should only declare the updater's functions and constraints and must not depend on a bound
        target.
        """

    @staticmethod
    def _add_named_function(
        functions: dict[str, object], function: object, name: str | None = None
    ) -> None:
        """Add a function under the existing ``name_0``, ``name_1`` policy.

        Args:
            functions (dict[str, object]): Named callable terms registered by the updater.
            function (object): Callable registered or evaluated by this operation.
            name (str | None): Name identifying the item in its owning collection.
        """
        base_name = type(function).__name__ if name is None else name
        index = 0
        final_name = f"{base_name}_{index}"
        while final_name in functions:
            index += 1
            final_name = f"{base_name}_{index}"
        functions[final_name] = function

    def add_objective_function(self, obj_func: object, name: str | None = None) -> None:
        """Register one objective function for this updater.

        Args:
            obj_func (object): Callable objective or penalty term evaluated inside the subproblem.
            name (str | None): Name identifying the item in its owning collection.
        """
        self._add_named_function(self.obj_funcs, obj_func, name)

    def add_constraints(self, obj_func: object, name: str | None = None) -> None:
        """Register one constraint function for this updater.

        Args:
            obj_func (object): Callable objective or penalty term evaluated inside the subproblem.
            name (str | None): Name identifying the item in its owning collection.
        """
        self._add_named_function(self.constraints_funcs, obj_func, name)

    def closure(self, x: torch.Tensor, return_list: bool = False) -> torch.Tensor:
        """This method is called to update the design variables based on the optimization algorithm
        used.

        Args:
            x (torch.Tensor): The current design variables.
            return_list (bool): If True, returns a list of objective function values; otherwise,
                returns their sum.

        Returns:
            torch.Tensor: The objective function value(s).
        """
        raise NotImplementedError("This method should be overridden by subclasses.")

    def update_variables(self, dx: torch.Tensor) -> None:
        """Write one updater's result back to its bound target.

        Args:
            dx (torch.Tensor): Proposed design-variable increment in flattened parameter order.
        """
        raise NotImplementedError

    def update(self) -> torch.Tensor:
        """Update the parameters of the optimization process.

        Returns:
            torch.Tensor: Update the parameters of the optimization process.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")


class Updaters(ProtocalInitializable, ProtocalSavable, ProtocalHistory):
    """
    The sub-updaters of the optimization problem, held in a named dict.

    Every sub-updater behaves the same way: it owns *one* target of the model
    (a boundary Part for geometry or a material interface for materials), takes
    only that target's slice of
    the design gradient, and is updated, saved and restored on its own.

    Declaring happens in one hook, :meth:`define_updater`, where each
    ``add_*_updater`` call states what it updates, while the target itself is
    stated by the ``name`` of that call (and looked up **by name in that
    collection** when the updater initializes):

    ```python
    class Updater(morphopt.Updaters):
        def define_updater(self) -> None:
            self.add_geometry_updater(self.Shape(), name="body")
            self.add_material_updater(self.Solid(), name="solid")

        class Shape(morphopt.UpdaterBoundaryPart):
            def __init__(self):
                super().__init__(max_step_iter=200)
    ```

    The updater classes stay target-free, so one class can be added several
    times for different Parts / material interfaces.
    """

    #: how each kind of updater finds its collection.  The kind is also the
    #: key of the corresponding entry in the sensitivity dictionary.
    _KIND_TARGETS: dict[str, Callable[[Params], UpdaterCollection]] = {
        "geometry": lambda params: params.geometry,
        "materials": lambda params: params.materials,
    }

    def __init__(
        self,
        params: Params | None = None,
        updaters: dict[str, BaseUpdater] | list[BaseUpdater] | None = None,
        device: str | None = None,
    ) -> None:
        """Initialize the updater collection.

        Args:
            params (Params | None): The model parameters shared by the sub-updaters; they resolve
                their targets from it.
            updaters (dict[str, BaseUpdater] | list[BaseUpdater] | None): sub-updaters to register
                before ``define_updater()`` runs.  A dict is used as is (name -> updater), a list
                gets default names.
            device (str | None): The device used for the objective function and the sensitivity
                analysis.  Defaults to the current one.
        """
        self.params: Params = params
        """The model parameters the sub-updaters resolve their targets from."""

        self.updaters: dict[str, BaseUpdater] = {}
        """The sub-updaters by name, in registration order."""

        self._var_updaters: dict[str, torch.Tensor] = {}
        """The updated design variables of each sub-updater, by name."""

        self._device: str = device
        """The device used for objectives and sensitivity; None keeps the default."""

        self._updater_defined = False
        """Whether ``define_updater`` has already run."""

        if updaters:
            if isinstance(updaters, dict):
                for name, updater in updaters.items():
                    self.add_updater(updater, name=name)
            else:
                for updater in updaters:
                    self.add_updater(updater)

    # ------------------------------------------------------------ registration
    def define_updater(self) -> None:
        """Register the sub-updaters (override this hook).

        The **adder** says what each sub-updater updates -- geometry or materials -- so the kind is
        unambiguous and the target is the ``name``:

        ```python
        def define_updater(self) -> None:
            self.add_geometry_updater(self.Shape(), name="body")
            self.add_material_updater(self.Solid(), name="solid")
        ```
        """

    def add_geometry_updater(
        self, updater: BaseUpdater, name: str | None = None
    ) -> str:
        """Register a sub-updater that owns a Part of ``params.geometry``.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            name (str | None): Name identifying the item in its owning collection.

        Returns:
            str: Register a sub-updater that owns a Part of ``params.geometry``.
        """
        return self.add_updater(updater, name=name, kind="geometry")

    def add_material_updater(
        self, updater: BaseUpdater, name: str | None = None
    ) -> str:
        """Register a sub-updater that owns a material interface.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            name (str | None): Name identifying the item in its owning collection.

        Returns:
            str: Register a sub-updater that owns a material interface.
        """
        return self.add_updater(updater, name=name, kind="materials")

    def add_updater(
        self,
        updater: BaseUpdater,
        name: str | None = None,
        kind: str | None = None,
    ) -> str:
        """Register one sub-updater and return its final name.

        ``kind`` is normally supplied by :meth:`add_geometry_updater` /
        :meth:`add_material_updater`, which state
        which collection the sub-updater belongs to.  An updater that declares a
        *different* ``update_kind`` is rejected; one that declares none adopts
        the kind of the hook it was registered in.

        ``name`` names the sub-updater *and* is the interface it owns (a Part name for geometry, a
        material interface name for materials), unless the constructor already got an explicit
        ``interface_name=``.  Nothing is resolved here: the target object itself is looked up in
        :meth:`initialize`.  The updater's :meth:`BaseUpdater.define_objective` hook is called here,
        once, after registration validation succeeds.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            name (str | None): Name identifying the item in its owning collection.
            kind (str | None): Registered category or provider identifier used to dispatch the
                operation.

        Returns:
            str: Register one sub-updater and return its final name.
        """
        if not isinstance(updater, BaseUpdater):
            raise TypeError(
                f"updater must be a BaseUpdater (got {type(updater).__name__})."
            )
        declared = updater.update_kind
        if kind is None:
            kind = declared
        elif declared and declared != kind:
            raise ValueError(
                f"{type(updater).__name__} declares update_kind={declared!r} but "
                f"was added as a {kind!r} updater."
            )
        if not kind:
            raise ValueError(
                f"{type(updater).__name__} must be registered with one of "
                "add_geometry_updater() / add_material_updater() so its kind "
                "is unambiguous."
            )
        if kind not in self._KIND_TARGETS:
            raise ValueError(
                f"Unknown updater kind {kind!r}; known kinds: "
                f"{sorted(self._KIND_TARGETS)}."
            )
        updater.update_kind = kind

        # The registration name *is* the interface the updater owns: that is
        # where the target is declared, so the same updater class can be added
        # several times for different parts / material interfaces.  An explicit
        # ``interface_name=`` in the constructor wins.
        if name is not None and not updater.interface_name:
            updater.interface_name = name
        if name is None:
            name = updater.interface_name or None
        if name is None:
            prefix = type(updater).__name__
            index = 0
            name = f"{prefix}_{index}"
            while name in self.updaters:
                index += 1
                name = f"{prefix}_{index}"
        name = str(name).strip()
        if not name:
            raise ValueError("Updater name cannot be empty.")
        if name in self.updaters:
            raise ValueError(f"Updater {name!r} already exists.")
        if updater in self.updaters.values():
            raise ValueError("The same updater instance cannot be registered twice.")

        updater.define_objective()
        self.updaters[name] = updater
        return name

    # ------------------------------------------------------------- gradient io
    def _gradient_bounds(self, update_kind: str) -> dict[str, tuple[int, int]]:
        """Gradient slice (start, stop) of every target of one kind.

        The design gradient of a kind is ordered like its collection: target by target, so a
        sub-updater takes the block of the target it owns.

        Args:
            update_kind (str): Target parameter collection, such as geometry or materials.

        Returns:
            dict[str, tuple[int, int]]: Gradient slice (start, stop) of every target of one kind.
        """
        params = self.params
        accessor = self._KIND_TARGETS.get(update_kind)
        if params is None or accessor is None:
            return {}
        collection = accessor(params)
        if collection is None:
            return {}

        bounds: dict[str, tuple[int, int]] = {}
        offset = 0
        for interface in collection.design_interfaces():
            name = interface.name
            size = interface.num_variables
            if size:
                bounds[name] = (offset, offset + size)
                offset += size
        return bounds

    @staticmethod
    def _slice_of(
        updater: BaseUpdater, bounds: dict[str, tuple[int, int]]
    ) -> tuple[int, int]:
        """Slice of one target inside already computed bounds.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            bounds (dict[str, tuple[int, int]]): Axis-aligned bounds in [xmin, xmax, ymin, ymax,
                zmin, zmax] order.

        Returns:
            tuple[int, int]: Slice of one target inside already computed bounds.
        """
        target = updater.interface_name
        if target in bounds:
            return bounds[target]
        if len(bounds) == 1:
            # A single-target collection needs no explicit name; geometry and
            # material names are already validated during initialization.
            return next(iter(bounds.values()))
        return (0, 0)

    @staticmethod
    def _resolve_target(
        updater: BaseUpdater, collection: UpdaterCollection | None
    ) -> UpdaterTarget:
        """Resolve one updater's interface from its owning collection.

        Geometry and material collections expose different collection methods, but the selection
        policy is identical: an explicit name wins; without one, exactly one interface of the
        updater's declared ``target_type`` must exist. Keeping this policy here prevents every
        concrete updater from growing its own copy of the same lookup and ambiguity checks.

        Args:
            updater (BaseUpdater): Updater bound to the target whose policy or state is being
                evaluated.
            collection (UpdaterCollection | None): Owning named interface collection.

        Returns:
            UpdaterTarget: Resolve one updater's interface from its owning collection.
        """
        if collection is None:
            raise ValueError(
                f"{type(updater).__name__} has no collection for update kind "
                f"{updater.update_kind!r}."
            )

        if updater.update_kind == "geometry":
            if not isinstance(collection, GeometryParams):
                raise TypeError(
                    "A geometry updater must be bound to a GeometryParams collection."
                )
            interfaces = collection.interfaces.values()
            collection_label = "geometry Part"
        elif updater.update_kind == "materials":
            if not isinstance(collection, MaterialsParams):
                raise TypeError(
                    "A materials updater must be bound to a MaterialsParams collection."
                )
            interfaces = collection.interfaces.values()
            collection_label = "material interface"
        else:
            raise ValueError(
                f"Cannot resolve a target for unknown update kind "
                f"{updater.update_kind!r}."
            )

        expected = updater.target_type

        def is_accepted(interface: BasePart | BaseMaterial) -> bool:
            return expected is None or isinstance(interface, expected)

        name = updater.interface_name
        if name:
            target = next(
                (interface for interface in interfaces if interface.name == name),
                None,
            )
            if target is None:
                available = [interface.name for interface in interfaces]
                raise KeyError(
                    f"{collection_label.capitalize()} {name!r} does not exist; "
                    f"available: {available}."
                )
            if not is_accepted(target):
                expected_name = (
                    expected.__name__ if isinstance(expected, type) else str(expected)
                )
                raise TypeError(
                    f"{collection_label.capitalize()} {name!r} is a "
                    f"{type(target).__name__}; updater "
                    f"{type(updater).__name__} requires {expected_name}."
                )
            return target

        candidates = [interface for interface in interfaces if is_accepted(interface)]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            expected_name = (
                expected.__name__ if isinstance(expected, type) else "matching"
            )
            raise ValueError(
                f"This {collection_label} collection has no {expected_name} "
                f"target for updater {type(updater).__name__}."
            )
        raise ValueError(
            f"This collection has several targets for updater "
            f"{type(updater).__name__}; declare the interface name among "
            f"{[interface.name for interface in candidates]}."
        )

    # -------------------------------------------------------------- lifecycle
    def initialize(self) -> None:
        """Hand every sub-updater its collection, then initialize it.

        The collection is the model's own (``params.geometry`` / ``params.materials``, per the
        ``add_*_updater`` hook the sub-updater was registered in); this manager resolves **its**
        interface by name and type, so an unknown or incompatible target fails here, before the
        optimization loop, and the interface itself is the only model object the sub-updater keeps.
        """
        params = self.params
        if not self._updater_defined:
            self.define_updater()
            self._updater_defined = True
        bound_targets: dict[tuple[str, str], str] = {}
        for name, updater in self.updaters.items():
            accessor = self._KIND_TARGETS.get(updater.update_kind)
            collection = (
                accessor(params)
                if (accessor is not None and params is not None)
                else None
            )
            target = self._resolve_target(updater, collection)
            target_key = (updater.update_kind, target.name)
            previous = bound_targets.get(target_key)
            if previous is not None:
                raise ValueError(
                    f"Target {target.name!r} is already assigned to updater "
                    f"{previous!r}; one target cannot have multiple updaters."
                )
            bound_targets[target_key] = name
            updater.bind_target(target)
            updater.initialize()

    def update(self, gradients: dict[str, torch.Tensor], objective_value: float) -> None:
        """Supply the evaluated objective and each target's native gradient slice.

        Args:
            gradients (dict[str, torch.Tensor]): Unscaled physical gradients keyed by
                model-parameter collection.
            objective_value (float): Evaluated physical objective value for the current outer
                iteration.
        """
        controller = morphopt.controller
        default_device = torch.get_default_device()
        bounds = {
            kind: self._gradient_bounds(kind)
            for kind in {updater.update_kind for updater in self.updaters.values()}
        }

        for name, updater in self.updaters.items():
            start, stop = self._slice_of(updater, bounds[updater.update_kind])
            updater.objective_value = objective_value
            on_updater_device = self._device is not None
            try:
                if on_updater_device:
                    torch.set_default_device(self._device)
                    # Each updater gets an isolated device scope.  Move every
                    # tensor reachable from the runtime graph, including the
                    # live FEA Assembly and this updater's gradient block.
                    controller._change_device_recursive(controller, self._device)
                    controller._change_device_recursive(gradients, self._device)

                updater.reinitialize(
                    gradient=gradients[updater.update_kind][start:stop]
                )
                self._var_updaters[name] = updater.update()
            finally:
                if on_updater_device:
                    controller._change_device_recursive(controller, default_device)
                    controller._change_device_recursive(gradients, default_device)
                    torch.set_default_device(default_device)

    def update_variables(self) -> None:
        """Write the updated design variables back to their targets."""
        for name, updater in self.updaters.items():
            updater.update_variables(dx=self._var_updaters.get(name))

    def history_data(self) -> dict[str, object]:
        """Collect each updater under its registered name for the current row.

        Returns:
            dict[str, object]: Component-owned scalar or nested observations for the current
                iteration.
        """
        return {
            "optimizers": {
                name: updater.history_data() for name, updater in self.updaters.items()
            },
        }

    def save(self, foldpath: str, iteration: int) -> None:
        """Save the state of every sub-updater.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        for updater in self.updaters.values():
            updater.save(foldpath=foldpath, iteration=iteration)
            directory = updater.save_directory(
                foldpath, updater.interface_name or "all"
            )
            updater.constraint_weight_strategy.save(
                foldpath=os.path.join(directory, "constraint_weights"), iteration=iteration,
            )
            for name, objective in updater.obj_funcs.items():
                objective.save(
                    foldpath=os.path.join(directory, "objectives", name),
                    iteration=iteration,
                )

    def load(self, foldpath: str, iteration: int) -> None:
        """Restore the state of every sub-updater.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        for updater in self.updaters.values():
            updater.load(foldpath=foldpath, iteration=iteration)
            directory = updater.save_directory(
                foldpath, updater.interface_name or "all"
            )
            updater.constraint_weight_strategy.load(
                foldpath=os.path.join(directory, "constraint_weights"), iteration=iteration,
            )
            for name, objective in updater.obj_funcs.items():
                objective.load(
                    foldpath=os.path.join(directory, "objectives", name),
                    iteration=iteration,
                )

    def pathlog_required(self) -> list[str]:
        """The log sub-paths every sub-updater needs (deduplicated).

        Returns:
            list[str]: Relative log subdirectory names required before persistence.
        """
        paths: list[str] = []
        for updater in self.updaters.values():
            for path in updater.pathlog_required():
                if path not in paths:
                    paths.append(path)
        return paths
