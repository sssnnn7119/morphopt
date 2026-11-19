"""Construct mutable optimizer configurations from registered node defaults."""
from ...constants import CONSTANT
from .registry import SURFACE_SYMMETRY_CONSTRAINTS, UPDATER_CATALOG, UPDATER_OBJECTIVES, UPDATER_CONSTRAINTS
from .strategies import strategy_config

def symmetry_constraint_defaults(item_type: str) -> dict:
    """Return defaults for one geometry-symmetry constraint.

    Args:
        item_type (str): Registered interface type used to create a new collection item.

    Returns:
        dict: Defaults for one geometry-symmetry constraint.
    """
    return SURFACE_SYMMETRY_CONSTRAINTS[item_type].default_parameters()


def symmetry_constraint(item_type: str, **overrides) -> dict:
    """Build one geometry-symmetry constraint from its node defaults.

    Args:
        item_type (str): Registered interface type used to create a new collection item.
        **overrides: Additional keyword arguments accepted by the shared interface.

    Returns:
        dict: Build one geometry-symmetry constraint from its node defaults.
    """
    params = symmetry_constraint_defaults(item_type)
    params.update(overrides)
    item = {"type": item_type, "params": params}
    if item_type != "Custom":
        item["surface_index"] = None
    return item



def updater_item_defaults(item_type: str, category: str) -> dict:
    """Return updater item defaults.

    Args:
        item_type (str): Registered interface type used to create a new collection item.
        category (str): Interface or asset category used to select compatible editors or
            renderers.

    Returns:
        dict: Updater item defaults.
    """
    return UPDATER_CATALOG[category][item_type].default_parameters()


# --------------------------------------------------------------------------
# updater term / section factories
#
# These build the plain config dicts that live on the ``UpdaterNode`` from
# the catalogued defaults, so Quickstart declares only the *deviations*
# (``Distance(min_distance=...)`` instead of a full hand-written dict).  The
# code generator keeps reading the very same ``{"type", "params"}`` layout.
# --------------------------------------------------------------------------


def updater_objective(item_type: str, **overrides) -> dict:
    """One objective term: node defaults + ``overrides`` for item ``type``.

    Args:
        item_type (str): Registered interface type used to create a new collection item.
        **overrides: Additional keyword arguments accepted by the shared interface.

    Returns:
        dict: One objective term: node defaults + ``overrides`` for item ``type``.
    """
    spec = UPDATER_OBJECTIVES[item_type]
    params = spec.default_parameters()
    params.update(overrides)
    return {"type": item_type, "params": params}


def updater_constraint(item_type: str, **overrides) -> dict:
    """One constraint term: node defaults + ``overrides`` for item ``type``.

    Args:
        item_type (str): Registered interface type used to create a new collection item.
        **overrides: Additional keyword arguments accepted by the shared interface.

    Returns:
        dict: One constraint term: node defaults + ``overrides`` for item ``type``.
    """
    spec = UPDATER_CONSTRAINTS[item_type]
    params = spec.default_parameters()
    params.update(overrides)
    return {"type": item_type, "params": params}


def geometry_updater_config(
    part_name: str = "",
    max_step_iter: int = 50,
    max_step_length: float = CONSTANT.KERNEL.SHAPE_UPDATE.MAX_STEP_LENGTH,
    objective_functions: tuple | None = None,
    constraints: tuple | None = None,
    symmetry_constraints: tuple = (),
) -> dict:
    """Config of one geometry sub-optimizer.

    ``part_name`` is the boundary part component it updates; an empty name means "the only
    boundary part of the model". New configs include ShapeDerivative and Fairness, Distance,
    Cylinder penalties. Explicitly empty collections remain empty.

    Args:
        part_name (str): Registered Part name referenced by instances, loads, or material
            assignments.
        max_step_iter (int): Maximum optimizer steps per subproblem solve.
        max_step_length (float): Updater-owned movement limits in the target's parameter-block
            order.
        objective_functions (tuple | None): Registered differentiable subproblem objective
            declarations.
        constraints (tuple | None): Registered penalty or hard-projection declarations.
        symmetry_constraints (tuple): Hard surface-projection configurations in application
            order.

    Returns:
        dict: Config of one geometry sub-optimizer.
    """
    return {
        "part_name": str(part_name or ""),
        "max_step_iter": int(max_step_iter),
        "max_step_length": float(max_step_length),
        "update_strategy": strategy_config("geometry"),
        "objective_functions": list(objective_functions) if objective_functions is not None else [
            updater_objective("ShapeDerivative"),
        ],
        "constraints": list(constraints) if constraints is not None else [
            updater_constraint("Fairness"),
            updater_constraint("Distance"),
            updater_constraint("Cylinder"),
        ],
        "symmetry_constraints": list(symmetry_constraints),
    }


def materials_updater_config(
    material_name: str = "",
    max_step_iter: int = 50,
    max_step_length: float = CONSTANT.KERNEL.SIMP_UPDATE.MAX_STEP_LENGTH,
    if_update: bool | list[bool] = True,
    objective_functions: tuple | None = None,
    constraints: tuple | None = None,
) -> dict:
    """Config of one material sub-optimizer.

    ``material_name`` is the material definition it updates; an empty name means "the only
    design-carrying material in the model". New configs include sensitivity, variable bounds and
    volume fraction. Explicitly empty collections remain empty.

    Args:
        material_name (str): Registered material-interface name selected as the updater target.
        max_step_iter (int): Maximum optimizer steps per subproblem solve.
        max_step_length (float): Updater-owned movement limits in the target's parameter-block
            order.
        if_update (bool | list[bool]): Enable the selected interface's design update when True.
        objective_functions (tuple | None): Registered differentiable subproblem objective
            declarations.
        constraints (tuple | None): Registered penalty or hard-projection declarations.

    Returns:
        dict: Config of one material sub-optimizer.
    """
    return {
        "material_name": str(material_name or ""),
        "max_step_iter": int(max_step_iter),
        "max_step_length": float(max_step_length),
        "update_strategy": strategy_config("materials"),
        "if_update": if_update,
        "objective_functions": list(objective_functions) if objective_functions is not None else [
            updater_objective("Sensitivity"),
        ],
        "constraints": list(constraints) if constraints is not None else [
            updater_constraint("MinValue"),
            updater_constraint("MaxValue"),
            updater_constraint("VolFrac"),
        ],
    }




def objective_term_config(term_type: str) -> dict:
    """Defaults shared by the objective editor and file import.

    Args:
        term_type (str): Registered physical-objective expression type.

    Returns:
        dict: Defaults shared by the objective editor and file import.
    """
    objective = CONSTANT.UI.OBJECTIVE
    term = {"type": term_type, "weight": objective.DEFAULT_WEIGHT}
    if term_type == objective.TYPE_DISPLACEMENT:
        term.update(
            reference_point_name="", step_name=None, component="",
            direction=objective.DEFAULT_DIRECTION, target=objective.DEFAULT_TARGET,
        )
    elif term_type == objective.TYPE_WORKSPACE:
        term.update(
            kind=objective.DEFAULT_WORKSPACE_KIND, reference_point_name="", inputs=[],
            gauss_order=objective.DEFAULT_WORKSPACE_GAUSS_ORDER,
            normalization=objective.DEFAULT_WORKSPACE_NORMALIZATION, case_names=[],
        )
    elif term_type == objective.TYPE_CUSTOM_LOSS:
        term["body"] = ""
    else:
        raise ValueError(f"Unknown objective type: {term_type}")
    return term


def metric_term_config(metric_type: str) -> dict:
    """Defaults shared by the metric editor and file import.

    Args:
        metric_type (str): Registered metric expression type.

    Returns:
        dict: Defaults shared by the metric editor and file import.
    """
    if metric_type == CONSTANT.UI.METRIC.TYPE_DISPLACEMENT:
        return {"type": metric_type, "reference_point_name": "", "step_name": None, "component": ""}
    if metric_type == CONSTANT.UI.METRIC.TYPE_CUSTOM:
        return {"type": metric_type, "body": ""}
    raise ValueError(f"Unknown metric type: {metric_type}")
