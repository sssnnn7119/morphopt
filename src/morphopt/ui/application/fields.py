"""Field selection and model-backed choices, independent of Qt editors."""
from __future__ import annotations

from ..model.problem import CADOperationNode, InterfaceNode, Node, ProblemDefinition
from ..model.schemas import (
    CAD_OPERATION_TYPES,
    INTERFACE_TYPES,
    MATERIAL_MODEL_PARAMETERS,
    MATERIAL_TYPES,
    PART_INTERFACE_TYPES,
    SOLVER_FIELDS,
    SURFACE_TYPES,
    fld,
)
from .part_sets import PartSetCatalog


def fields_for_node(
    node: Node,
    problem: ProblemDefinition | None = None,
    *,
    sets: PartSetCatalog | None = None,
) -> tuple[list[dict], dict, dict]:
    """Return (param_fields, code_slots, extra_choices) for ``node``."""
    kind = node.kind
    if isinstance(node, CADOperationNode):
        spec = CAD_OPERATION_TYPES[node.operation_type]
        choices: dict[str, list[str]] = {}
        if problem is not None:
            owner = problem.owner_of_cad_operation(node)
            operations = owner.cad_operations() if owner is not None else []
            current_index = operations.index(node) if node in operations else 0
            live_operations = (
                owner.live_cad_operations(operations[:current_index])
                if owner is not None
                else []
            )
            prior_ids = [op.operation_id for op in live_operations]
            for key in ("object_id", "tool_id", "input_id"):
                if any(field["key"] == key for field in spec["params"]):
                    choices[key] = prior_ids
        fields = [field for field in spec["params"] if not field.get("hidden")]
        return fields, {}, choices
    if kind == "surface":
        st = node.get_field("type", "bsp_cylinder")
        spec = SURFACE_TYPES.get(st, {})
        return list(spec.get("params", [])), {}, {}
    if kind == "interface":
        it = node.get_field("type", "Pressure")
        spec = INTERFACE_TYPES.get(it, {})
        choices: dict[str, list[str]] = {}
        if problem is not None:
            # dynamic choices: surfaces sets + rp names
            choices = dynamic_choices(problem, it, node, sets=sets)
        return list(spec.get("params", [])), {}, choices
    if kind == "material":
        mt = node.get_field("type", "")
        spec = MATERIAL_TYPES.get(mt, {})
        model = node.get_field("material_model", "NeoHookeanLnJ")
        fields = list(spec.get("params", []))
        if mt in ("HomogeneousMaterial", "SIMP_BSPFieldMaterials"):
            common = {"part_name", "material_model", "density", "elementname"}
            if mt == "SIMP_BSPFieldMaterials":
                # Neo-Hookean SIMP uses its maximum moduli as the model
                # parameters.  Other models expose their own TorchFEA
                # parameters; mumax/kappamax remain internal plotting
                # defaults and are not shown as a second parameter set.
                if model in ("NeoHookean", "NeoHookeanLnJ"):
                    common |= {"mumax", "kappamax"}
                    model_parameters = {"mu", "kappa"}
                else:
                    model_parameters = set(MATERIAL_MODEL_PARAMETERS.get(model, ()))
                allowed = common | model_parameters
            else:
                allowed = common | set(MATERIAL_MODEL_PARAMETERS.get(model, ()))
            fields = [field for field in fields if field["key"] in allowed]
        code_slots = {}
        choices = {}
        if problem is not None and mt in (
            "SIMP_BSPFieldMaterials",
            "HomogeneousMaterial",
        ):
            part_names = problem.part_names()
            choices["part_name"] = part_names
            choices["elementname"] = problem.element_names(node.part_name)
        return fields, code_slots, choices
    if kind == "geometry":
        # the Geometry section is a container: its Parts are separate nodes
        return [], {}, {}
    if kind == "part_interface":
        itype = node.get_field("type", "")
        spec = PART_INTERFACE_TYPES.get(itype, {})
        choices: dict[str, list[str]] = {}
        if problem is not None:
            summary = problem.imported_model_summary()
            choices["model_part_name"] = (
                [item.name for item in summary.parts] if summary is not None else []
            )
        return list(spec.get("params", [])), {}, choices
    if kind == "instance":
        return [
            fld(
                "translation",
                "Translation",
                "vec3",
                [0.0, 0.0, 0.0],
                "Translation [tx, ty, tz] of this Instance.",
            ),
            fld(
                "rotation",
                "Rotation exponential coordinates",
                "vec3",
                [0.0, 0.0, 0.0],
                "Rotation exponential coordinates [rx, ry, rz].",
            ),
        ], {}, {}
    if kind == "solver":
        return list(SOLVER_FIELDS), {}, {}
    if kind == "objective":
        return [], {}, {}
    if kind == "updater":
        return [], {}, {}
    return [], {}, {}


def dynamic_choices(
    problem: ProblemDefinition,
    itype: str,
    iface: InterfaceNode,
    *,
    sets: PartSetCatalog | None = None,
) -> dict[str, list[str]]:
    """Resolve choices against the owning Part, including mixed local/imported models."""
    catalog = sets or PartSetCatalog(problem)
    references = {
        "set_nodes_name": (iface.instance_name or "", "nodes"),
        "surface_name": (iface.instance_name or "", "surfaces"),
        "surface_name1": (iface.instance_name1 or "", "surfaces"),
        "surface_name2": (iface.instance_name2 or "", "surfaces"),
        "element_name": (iface.instance_name or "", "elements"),
    }
    rp_names = [node.name for node in problem.interfaces() if node.interface_type == "ReferencePoint"]
    choices: dict[str, list[str]] = {}
    for field in INTERFACE_TYPES.get(itype, {}).get("params", []):
        key = field["key"]
        if key in ("instance_name", "instance_name1", "instance_name2"):
            choices[key] = problem.instance_names()
        elif key in references:
            name, kind = references[key]
            part_sets = catalog.for_instance(name)
            choices[key] = list(getattr(part_sets, kind))
        elif key in ("rp_name", "rp_name1", "rp_name2"):
            choices[key] = rp_names
    return choices


class SnippetInputs:
    """Model-backed snippet options and reference consistency policy."""
    editable = frozenset({"instances", "reference_points", "elements", "force_loads", "moment_loads"})

    def __init__(self, problem: ProblemDefinition):
        self.problem = problem

    def values(self, source: str) -> list:
        providers = {
            "load_steps": lambda: list(range(self.problem.steps.num_steps if self.problem.steps else 1)),
            "instances": self.problem.instance_names,
            "reference_points": self.problem.reference_point_names,
            "elements": self.problem.element_names,
            "force_loads": lambda: [node.name for node in self.problem.interfaces() if node.interface_type == "ConcentratedForce" and node.name],
            "moment_loads": lambda: [node.name for node in self.problem.interfaces() if node.interface_type == "ConcentratedMoment" and node.name],
            "axis": lambda: list(range(3)),
            "translation_axis": lambda: list(range(3)),
            "rotation_axis": lambda: list(range(3, 6)),
            "six_component": lambda: list(range(6)),
        }
        return providers[source]()

    def jacobian_issue(self, values: dict) -> str | None:
        interfaces = {node.name: node for node in self.problem.interfaces()}
        reference = interfaces.get(str(values.get("reference_point_name", "")).strip())
        force = interfaces.get(str(values.get("force_load_name", "")).strip())
        moment = interfaces.get(str(values.get("moment_load_name", "")).strip())
        if reference is None or reference.interface_type != "ReferencePoint" or force is None or force.interface_type != "ConcentratedForce" or moment is None or moment.interface_type != "ConcentratedMoment":
            return 'ui.widgets.template_insert_dialog.the_jacobian_template_requires_a_reference_point_force_and_moment_that_a'
        if force.reference_point is not reference or moment.reference_point is not reference:
            return 'ui.widgets.template_insert_dialog.the_concentrated_force_concentrated_moment_and_selected_reference_point'
        return None
