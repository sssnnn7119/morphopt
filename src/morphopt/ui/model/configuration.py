"""Construct mutable optimizer configurations from registered node defaults."""
from .registry import SURFACE_SYMMETRY_CONSTRAINTS, UPDATER_CATALOG, UPDATER_OBJECTIVES, UPDATER_CONSTRAINTS

def symmetry_constraint_defaults(item_type: str) -> dict:
    """Return defaults for one geometry-symmetry constraint."""
    return SURFACE_SYMMETRY_CONSTRAINTS[item_type].default_parameters()


def symmetry_constraint(item_type: str, **overrides) -> dict:
    """Build one geometry-symmetry constraint from its node defaults."""
    params = symmetry_constraint_defaults(item_type)
    params.update(overrides)
    item = {"type": item_type, "params": params}
    if item_type != "Custom":
        item["surface_index"] = None
    return item



def updater_item_defaults(item_type: str, category: str) -> dict:
    return UPDATER_CATALOG[category][item_type].default_parameters()


# --------------------------------------------------------------------------
# updater term / section factories
#
# These build the plain config dicts that live on the ``UpdaterNode`` from
# the catalogued defaults, so scheme templates declare only the *deviations*
# (``Distance(min_distance=...)`` instead of a full hand-written dict).  The
# code generator keeps reading the very same ``{"type", "params"}`` layout.
# --------------------------------------------------------------------------


def updater_objective(item_type: str, **overrides) -> dict:
    """One objective term: node defaults + ``overrides`` for item ``type``."""
    spec = UPDATER_OBJECTIVES[item_type]
    params = spec.default_parameters()
    params.update(overrides)
    return {"type": item_type, "params": params}


def updater_constraint(item_type: str, **overrides) -> dict:
    """One constraint term: node defaults + ``overrides`` for item ``type``."""
    spec = UPDATER_CONSTRAINTS[item_type]
    params = spec.default_parameters()
    params.update(overrides)
    return {"type": item_type, "params": params}


def geometry_updater_config(
    part_name: str = "",
    max_step_iter: int = 50,
    objective_functions: tuple | None = None,
    constraints: tuple | None = None,
    symmetry_constraints: tuple = (),
) -> dict:
    """Config of one geometry sub-optimizer.

    ``part_name`` is the boundary part component it updates; an empty name
    means "the only boundary part of the model".
    New configs include ShapeDerivative and Fairness, Distance, Cylinder
    penalties. Explicitly empty collections remain empty.
    """
    return {
        "part_name": str(part_name or ""),
        "max_step_iter": int(max_step_iter),
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
    if_update: bool | list[bool] = True,
    objective_functions: tuple = (),
    constraints: tuple = (),
) -> dict:
    """Config of one material sub-optimizer.

    ``material_name`` is the material definition it updates; an empty name
    means "the only design-carrying material in the model".
    """
    return {
        "material_name": str(material_name or ""),
        "max_step_iter": int(max_step_iter),
        "if_update": if_update,
        "objective_functions": list(objective_functions),
        "constraints": list(constraints),
    }


