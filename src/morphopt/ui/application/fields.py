"""Model-backed field selection and choices, independent of Qt widgets."""
from __future__ import annotations

from ..model.fields import FieldSpec
from ..model.material_models import MATERIAL_MODEL_PARAMETERS
from ..model.problem import CADOperationNode, FEAComponentNode, MaterialNode, Node, ProblemDefinition
from .part_sets import PartSetCatalog


def fields_for_node(
    node: Node,
    problem: ProblemDefinition | None = None,
    *,
    sets: PartSetCatalog | None = None,
) -> tuple[list[FieldSpec], dict, dict]:
    fields = [field for field in node.fields if not field.hidden]
    choices: dict[str, list[str]] = {}
    if isinstance(node, CADOperationNode) and problem is not None:
        owner = problem.owner_of_cad_operation(node)
        operations = owner.operations if owner is not None else []
        index = operations.index(node) if node in operations else 0
        prior = owner.live_cad_operations(operations[:index]) if owner is not None else []
        for key in ("object_id", "tool_id", "input_id"):
            if node.has_field(key):
                choices[key] = [operation.operation_id for operation in prior]
    elif isinstance(node, FEAComponentNode) and problem is not None:
        choices = dynamic_choices(problem, node.type, node, sets=sets)
    elif isinstance(node, MaterialNode):
        model = node.material_model
        common = {"part_name", "material_model", "density", "elementname"}
        if node.is_updatable:
            common |= {
                "simp_ratio_min", "bounding_box", "simp_field_resolution", "degree",
                "initial_ratio", "voidpenalfactor", "materialpenalty",
            }
            if model in ("NeoHookean", "NeoHookeanLnJ"):
                common |= {"mumax", "kappamax"}
                model_parameters = set()
            else:
                model_parameters = set(MATERIAL_MODEL_PARAMETERS[model])
        else:
            model_parameters = set(MATERIAL_MODEL_PARAMETERS[model])
        fields = [field for field in fields if field.key in common | model_parameters]
        if problem is not None:
            choices["part_name"] = problem.part_names()
            catalog = sets or PartSetCatalog(problem)
            choices["elementname"] = list(catalog.for_part(node.part).elements)
    return fields, {}, choices


def dynamic_choices(
    problem: ProblemDefinition,
    itype: str,
    component: FEAComponentNode,
    *,
    sets: PartSetCatalog | None = None,
) -> dict[str, list[str]]:
    """Resolve choices against the owning Part, including imported INP meshes."""
    catalog = sets or PartSetCatalog(problem)
    references = {
        "set_nodes_name": (component.instance_name or "", "nodes"),
        "surface_name": (component.instance_name or "", "surfaces"),
        "surface_name1": (component.instance_name1 or "", "surfaces"),
        "surface_name2": (component.instance_name2 or "", "surfaces"),
        "element_name": (component.instance_name or "", "elements"),
    }
    rp_names = [node.name for node in problem.fea_components() if node.type == "ReferencePoint"]
    choices: dict[str, list[str]] = {}
    for field in component.fields:
        key = field.key
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
            "force_loads": lambda: [node.name for node in self.problem.fea_components() if node.type == "ConcentratedForce" and node.name],
            "moment_loads": lambda: [node.name for node in self.problem.fea_components() if node.type == "ConcentratedMoment" and node.name],
            "axis": lambda: list(range(3)),
            "translation_axis": lambda: list(range(3)),
            "rotation_axis": lambda: list(range(3, 6)),
            "six_component": lambda: list(range(6)),
        }
        return providers[source]()

    def jacobian_issue(self, values: dict) -> str | None:
        components = {node.name: node for node in self.problem.fea_components()}
        reference = components.get(str(values.get("reference_point_name", "")).strip())
        force = components.get(str(values.get("force_load_name", "")).strip())
        moment = components.get(str(values.get("moment_load_name", "")).strip())
        if reference is None or reference.type != "ReferencePoint" or force is None or force.type != "ConcentratedForce" or moment is None or moment.type != "ConcentratedMoment":
            return 'ui.widgets.template_insert_dialog.the_jacobian_template_requires_a_reference_point_force_and_moment_that_a'
        if force.reference_point is not reference or moment.reference_point is not reference:
            return 'ui.widgets.template_insert_dialog.the_concentrated_force_concentrated_moment_and_selected_reference_point'
        return None
