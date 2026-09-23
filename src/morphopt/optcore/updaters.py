import os
from collections.abc import Callable
from typing import TypeAlias

import torch

import morphopt

from .modelparams import GeometryParams, MaterialsParams, Params
from .modelparams.materialinterface.basematerialinterface import BaseMaterialInterface
from .modelparams.partinterface.basepartinterface import BasePartInterface
from .protocal import ProtocalInitializable, ProtocalSavable

UpdaterCollection: TypeAlias = GeometryParams | MaterialsParams
"""Collections from which :class:`Updaters` resolves a target."""

UpdaterTarget: TypeAlias = BasePartInterface | BaseMaterialInterface
"""Objects that a :class:`BaseUpdater` can own after binding."""

UpdaterTargetType: TypeAlias = type[UpdaterTarget] | tuple[type[UpdaterTarget], ...]
"""Accepted class specification for an updater target."""


class BaseUpdater(ProtocalInitializable, ProtocalSavable):
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
    class Updater(morphopt.shapeopt.Updaters):
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
    handled separately after the target has been resolved.
    """

    update_kind: str = ""
    """Kind of collection this updater updates (``geometry`` / ``materials``)."""

    target_type: UpdaterTargetType | None = None
    """Interface type accepted by this updater, or ``None`` for any target."""

    @property
    def interface_name(self) -> str:
        """Name of the interface this updater owns inside its collection."""
        return self._interface_name

    @interface_name.setter
    def interface_name(self, value: str) -> None:
        new_name = str(value).strip() if value else ""
        if new_name != self._interface_name:
            self._target = None
        self._interface_name = new_name

    @property
    def target(self) -> UpdaterTarget:
        """The model interface resolved for this updater."""
        if self._target is None:
            raise ValueError(
                f"{type(self).__name__} has no target yet; the updater manager "
                "binds it during initialization."
            )
        return self._target

    def bind_target(self, target: UpdaterTarget | None = None) -> UpdaterTarget:
        """Store the already-resolved model target.

        Target lookup and type validation are centralized in :class:`Updaters`;
        subclasses only expose a domain-specific property such as ``part`` or
        ``material``.
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
        """Return the namespaced state-file path for this updater."""
        directory = self.save_directory(foldpath, self.interface_name or "all")
        return os.path.join(directory, f"step_length_{iteration}.npz")

    class Optimizer:
        class BaseOpt:
            def __init__(self, closure: Callable[[torch.Tensor], float]):
                self.closure = closure
                """
                the objective function to be optimized, which should return the objective value
                """

                self.grad = torch.func.jacrev(self.closure)
                """        the gradient of the objective function, which should return the gradient vector
                """

                # params for line search
                self._c1 = 1e-4
                self._rou1 = 0.2

            def set_line_search_params(self, c1: float = None, rou1: float = None):
                """
                Set the parameters for the line search method.

                Parameters:
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
                """
                Backtracking line search to find the step length for the optimization process.

                Parameters:
                    x0 (torch.Tensor): The current point in the optimization process.
                    dx (torch.Tensor): The gradient vector at the current point.
                    direction (torch.Tensor): The search direction.
                    alpha0 (float): The initial step length.
                    c1 (float): The parameter for the Wolfe condition.
                    rou1 (float): The parameter for the backtracking line search.
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
                    if (alpha * direction).abs().max() < 1e-14:
                        return 0.0, obj0

        class LBFGS(BaseOpt):
            def __init__(
                self,
                closure: Callable[[torch.Tensor], float],
                num_limit: int = 10,
                tol_error: float = 1e-10,
            ) -> None:
                super().__init__(closure=closure)
                self.SK = []
                self.YK = []
                self.rhok = []

                self.num_limit = num_limit
                """
                the number of pairs of Hessian and gradient stored in the memory
                """

                self.tol_error = tol_error
                """
                the tolerance for the convergence of the optimization process
                """

            def Hg_loop(self, dv: torch.Tensor) -> torch.Tensor:
                """
                Compute the product of the inverse Hessian matrix and the gradient vector.
                This is done using the BFGS update formula.

                Parameters:
                    dv (torch.Tensor): The gradient vector.

                Returns:
                    torch.Tensor: The product of the inverse Hessian matrix and the gradient vector.
                """

                q = dv.clone()
                alpha = torch.zeros(len(self.SK))
                for i in range(len(self.SK) - 1, -1, -1):
                    alpha[i] = self.rhok[i] * self.SK[i].dot(q)
                    q = q - alpha[i] * self.YK[i]

                y = q / (self.rhok[-1] * self.YK[-1].dot(self.YK[-1]))

                for i in range(len(self.SK)):
                    beta = self.rhok[i] * self.YK[i].dot(y)
                    y = y + (alpha[i] - beta) * self.SK[i]

                return y

            def step(self, x_now: torch.Tensor, gk_now: torch.Tensor = None):

                obj_now = self.closure(x_now)
                if gk_now is None:
                    gk_now: torch.Tensor = self.grad(x_now).flatten()

                gk_now.view(-1)[gk_now.view(-1).isnan()] = 0

                # if the first iteration, use steepest descent direction
                if len(self.SK) == 0:
                    dk = -gk_now
                else:
                    dk = self.Hg_loop(-gk_now)
                if dk.view(-1).isnan().any():
                    dk = -gk_now
                    self.SK = []
                    self.YK = []
                    self.rhok = []

                # if the gradient is not positive, use steepest descent direction
                if (dk * gk_now).sum() > 0:
                    dk = -dk

                # line search
                alpha, obj_new = self._LineSearchBacktracking(
                    x0=x_now, dx=gk_now, direction=dk, alpha0=1.0, obj0=obj_now
                )

                # if the step length is too small, stop the iteration
                if abs(alpha) <= self.tol_error:
                    self.SK = []
                    self.YK = []
                    self.rhok = []

                x_new = x_now + alpha * dk

                if obj_new > obj_now:
                    self.SK = []
                    self.YK = []
                    self.rhok = []
                    return 0.0, torch.zeros_like(x_now), gk_now

                gk_new: torch.Tensor = self.grad(x_new).flatten()

                yk = gk_new.flatten() - gk_now.flatten()
                sk = alpha * dk.flatten()

                # BFGS method
                if yk.norm() > 1e-14 and sk.norm() > 1e-14:
                    self.SK.append(sk)
                    self.YK.append(yk)
                    self.rhok.append(1 / yk.dot(sk))

                    if len(self.SK) > self.num_limit:
                        self.SK = self.SK[1:]
                        self.YK = self.YK[1:]
                        self.rhok = self.rhok[1:]

                return alpha, dk, gk_new

    def __init__(self, interface_name: str | None = None) -> None:
        """
        Initialize the BaseUpdater.

        Only the name of the interface it owns is kept: the updater manager
        resolves and hands over the interface while initializing.
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

        self.optimizer: BaseUpdater.Optimizer.BaseOpt = None
        """The optimization algorithm used to update the design variables.
        This should be set to an instance of a subclass of Optimizer.BaseOpt.
        """

    def define_objective(self) -> None:
        """Register this updater's objective functions and constraints.

        Scheme-specific updaters override this hook and call
        :meth:`add_objective_function` / :meth:`add_constraints`.  It is
        called once by :meth:`Updaters.add_updater`, so this hook should only
        declare the updater's functions and constraints and must not depend on
        a bound target.
        """

    @staticmethod
    def _add_named_function(
        functions: dict[str, object], function: object, name: str | None = None
    ) -> None:
        """Add a function under the existing ``name_0``, ``name_1`` policy."""
        base_name = type(function).__name__ if name is None else name
        index = 0
        final_name = f"{base_name}_{index}"
        while final_name in functions:
            index += 1
            final_name = f"{base_name}_{index}"
        functions[final_name] = function

    def add_objective_function(self, obj_func: object, name: str | None = None) -> None:
        """Register one objective function for this updater."""
        self._add_named_function(self.obj_funcs, obj_func, name)

    def add_constraints(self, obj_func: object, name: str | None = None) -> None:
        """Register one constraint function for this updater."""
        self._add_named_function(self.constraints_funcs, obj_func, name)

    def reinitialize(self, gradient: torch.Tensor) -> None:
        """Rebuild the updater's subproblem from one gradient slice."""
        raise NotImplementedError("This method should be overridden by subclasses.")

    def initialize(self) -> None:
        """
        Initialize the updater.

        Called by :class:`Updaters` right after :meth:`bind_target`, with the
        updater's own interface already bound.  A subclass implements its
        runtime initialization here; objective functions and constraints were
        already registered by :meth:`Updaters.add_updater`.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")

    def closure(self, x: torch.Tensor, return_list: bool = False) -> torch.Tensor:
        """
        This method is called to update the design variables based on the optimization algorithm used.

        Parameters:
            x (torch.Tensor): The current design variables.
            return_list (bool): If True, returns a list of objective function values; otherwise, returns their sum.

        Returns:
            torch.Tensor: The objective function value(s).
        """
        raise NotImplementedError("This method should be overridden by subclasses.")

    def update_variables(self, dx: torch.Tensor) -> None:
        """Write one updater's result back to its bound target."""
        raise NotImplementedError

    def update(self) -> torch.Tensor:
        """
        Update the parameters of the optimization process.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")


class Updaters(ProtocalInitializable, ProtocalSavable):
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
    class Updater(morphopt.shapeopt.Updaters):
        def define_updater(self) -> None:
            self.add_geometry_updater(self.Shape(), name="body")
            self.add_material_updater(self.Solid(), name="solid")

        class Shape(morphopt.shapeopt.UpdaterBoundaryPart):
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
        """
        Initialize the updater collection.

        Args:
            params (Params, optional): The model parameters shared by the
                sub-updaters; they resolve their targets from it.
            updaters (dict | list, optional): sub-updaters to register before
                ``define_updater()`` runs.  A dict is used as is (name ->
                updater), a list gets default names.
            device (str, optional): The device used for the objective function
                and the sensitivity analysis.  Defaults to the current one.
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

        The **adder** says what each sub-updater updates -- geometry or
        materials -- so the kind is unambiguous and the target is the ``name``:

        ```python
        def define_updater(self) -> None:
            self.add_geometry_updater(self.Shape(), name="body")
            self.add_material_updater(self.Solid(), name="solid")
        ```
        """

    def add_geometry_updater(
        self, updater: BaseUpdater, name: str | None = None
    ) -> str:
        """Register a sub-updater that owns a Part of ``params.geometry``."""
        return self.add_updater(updater, name=name, kind="geometry")

    def add_material_updater(
        self, updater: BaseUpdater, name: str | None = None
    ) -> str:
        """Register a sub-updater that owns a material interface."""
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

        ``name`` names the sub-updater *and* is the interface it owns (a Part
        name for geometry, a material interface name for materials), unless the
        constructor already got an explicit ``interface_name=``.  Nothing is
        resolved here: the target object itself is looked up in
        :meth:`initialize`.  The updater's :meth:`BaseUpdater.define_objective`
        hook is called here, once, after registration validation succeeds.
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

        The design gradient of a kind is ordered like its collection: target by
        target, so a sub-updater takes the block of the target it owns.
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
        """Slice of one target inside already computed bounds."""
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

        Geometry and material collections expose different collection methods,
        but the selection policy is identical: an explicit name wins; without
        one, exactly one interface of the updater's declared ``target_type``
        must exist.
        Keeping this policy here prevents every concrete updater from growing
        its own copy of the same lookup and ambiguity checks.
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

        def is_accepted(interface: BasePartInterface | BaseMaterialInterface) -> bool:
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

        The collection is the model's own (``params.geometry`` /
        ``params.materials``, per the ``add_*_updater``
        hook the sub-updater was registered in); this manager resolves **its**
        interface by name and type, so an unknown or incompatible target fails
        here, before the optimization loop, and the interface itself is the
        only model object the sub-updater keeps.
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

    def update(self, gradients: dict[str, torch.Tensor]) -> None:
        """Update every sub-updater from its own slice of the gradient."""
        controller = morphopt.controller
        default_device = torch.get_default_device()
        bounds = {
            kind: self._gradient_bounds(kind)
            for kind in {updater.update_kind for updater in self.updaters.values()}
        }

        for name, updater in self.updaters.items():
            start, stop = self._slice_of(updater, bounds[updater.update_kind])
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

    def save(self, foldpath: str, iteration: int) -> None:
        """Save the state of every sub-updater."""
        for updater in self.updaters.values():
            updater.save(foldpath=foldpath, iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        """Restore the state of every sub-updater."""
        for updater in self.updaters.values():
            updater.load(foldpath=foldpath, iteration=iteration)

    def pathlog_required(self) -> list[str]:
        """The log sub-paths every sub-updater needs (deduplicated)."""
        paths: list[str] = []
        for updater in self.updaters.values():
            for path in updater.pathlog_required():
                if path not in paths:
                    paths.append(path)
        return paths
