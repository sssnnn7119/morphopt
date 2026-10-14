"""Names and summaries shared by navigation and editor cards."""
from __future__ import annotations
from ..i18n import tr
from ..codegen.custom_classes import class_path_for_node
from ..model.problem import Node, InstanceNode, CADOperationNode, ProblemDefinition
from ..model.schemas import SURFACE_TYPES, CAD_OPERATION_TYPES

CONTAINER_TITLE_KEYS = {
    "problem": "ui.widgets.model_tree.container.problem",
    "helper_code": "ui.widgets.model_tree.container.helper_code",
    "helper_code_block": "ui.widgets.model_tree.container.helper_code_block",
    "helper_variables_group": "ui.widgets.model_tree.container.helper_variables_group",
    "helper_functions_group": "ui.widgets.model_tree.container.helper_functions_group",
    "params_class": "ui.widgets.model_tree.container.params_class",
    "geometry": "ui.widgets.model_tree.container.geometry",
    "loads_group": "ui.widgets.model_tree.container.loads_group",
    "loads": "ui.widgets.model_tree.container.loads",
    "steps": "ui.widgets.model_tree.container.steps",
    "materials": "ui.widgets.model_tree.container.materials",
    "objective": "ui.widgets.model_tree.container.objective",
    "solver": "ui.widgets.model_tree.container.solver",
    "updater": "ui.widgets.model_tree.container.updater",
}

CODE_REFERENCES = {
    "problem": "Controller",
    "params_class": "Params",
    "geometry": "GeometryParams",
    "loads_group": "FEAParams",
    "loads": "define_interface",
    "steps": "define_steps",
    "materials": "MaterialsParams",
    "objective": "ObjectiveFunction",
    "solver": "Solver",
    "updater": "Updater",
}


def container_title(kind: str) -> str:
    """Localized title with its generated-code location in brackets."""
    key = CONTAINER_TITLE_KEYS.get(kind)
    label = tr(key) if key else kind
    reference = CODE_REFERENCES.get(kind)
    return f"{label} [{reference}]" if reference else label


def schema_label(spec: dict, key: str) -> str:
    """Localized full label ``解释 (TypeName)`` of a schema entry."""
    return tr(spec.get("label_key", key))


def surface_title_text(srf: Node, index: int) -> str:
    """Surface name followed by its concrete interface class."""
    st = srf.surface_type or "?"
    spec = SURFACE_TYPES.get(st, {})
    factory = spec.get("factory") or "FixedSurface"
    class_name = {"BSP": "BspSurfaceInterface", "CPGEO": "CPGEOSurfaceInterface"}.get(
        factory.split(".")[0], factory.split(".")[0]
    )
    return f"{srf.name or f'surface_{index}'} [{srf.custom_class or class_name}]"


def part_interface_title_text(interface: Node) -> str:
    """Registration name followed by the selected Part interface class."""
    name = interface.name or interface.resolved_part_name()
    return f"{name} [{interface.custom_class or interface.interface_type or '?'}]"


def instance_title_text(instance: InstanceNode) -> str:
    """Instance name followed by its backend class."""
    return f"{instance.name} [Instance]"


def cad_operation_title_text(operation: CADOperationNode) -> str:
    """Operation name and the live features it consumes."""
    spec = CAD_OPERATION_TYPES[operation.operation_type]
    label = tr(spec["label_key"])
    inputs = [operation.object_id, operation.tool_id, operation.input_id]
    inputs = [value for value in inputs if value]
    suffix = f" ← {', '.join(inputs)}" if inputs else ""
    return f"{operation.operation_id} · {label}{suffix}"


def surface_index(problem: ProblemDefinition | None, srf: Node) -> int | None:
    """Return the 0-based position of ``srf`` inside its Part interface."""
    if problem is None:
        return None
    owner = problem.owner_of_surface(srf)
    if owner is None:
        return None
    for i, s in enumerate(owner.surfaces()):
        if s is srf:
            return i
    return None


def interface_title_text(iface: Node) -> str:
    it = iface.interface_type or "?"
    return f"{iface.name or it} [{iface.custom_class or it + 'Interface'}]"


def material_title_text(material: Node) -> str:
    mtype = material.material_type or "?"
    return f"{material.name or mtype} [{material.custom_class or mtype}]"


def updater_title_text(problem: ProblemDefinition | None, node: Node) -> str:
    """Return the localized title for a transient updater tree entry."""
    if node.kind.startswith("updater_"):
        labels = {
            "geometry": "ui.widgets.model_tree.updater.geometry",
            "materials": "ui.widgets.model_tree.updater.materials",
            "geometry_objectives": "ui.widgets.model_tree.updater.objectives",
            "geometry_symmetry": "ui.widgets.model_tree.updater.geometry_symmetry",
            "geometry_penalty": "ui.widgets.model_tree.updater.geometry_penalty",
            "materials_objectives": "ui.widgets.model_tree.updater.objectives",
            "materials_penalty": "ui.widgets.model_tree.updater.materials_penalty",
        }
        if node.group not in labels:
            return container_title("updater")
        label = tr(labels[node.group])
        part = ""
        if node.section_group == "geometry":
            config = node.config() or {}
            target = (
                problem.config_part_node(config)
                if problem is not None
                else None
            )
            if target is not None:
                part = tr('ui.widgets.model_tree.part_value', value_0=target.name)
        elif node.section_group == "materials":
            config = node.config() or {}
            target = (
                problem.config_material_node(config)
                if problem is not None
                else None
            )
            if target is not None:
                part = tr('ui.widgets.model_tree.material_value', value_0=target.name)
            elif len(node.updater_parent.materials) > 1:
                part = f" · {node.config_index}"
        return f"{label}{part} [{node.code_reference}]"
    return container_title("updater")


def display_node_title(problem: ProblemDefinition | None, text: str, node: Node) -> str:
    path = class_path_for_node(node)
    selected = problem.class_bindings.get(path) if problem and path else None
    if selected:
        return f"{text.rsplit(' [', 1)[0]} [{selected}]"
    return text


def quickstart_summary(options) -> str:
    from ..application.quickstart import GOALS
    shape = options.method == "shapeopt"
    mode = tr('ui.widgets.quickstart.shape_optimization') if shape else tr('ui.widgets.quickstart.topology_optimization')
    parts = [f"<h3>{mode}</h3>"]
    if shape:
        parts += [tr(
            'ui.widgets.quickstart.geometry_value_serial_layers_value_cavities_total_length_value_mm',
            value_0=len(options.layers),
            value_1=options.chambers,
            value_2=options.total_length,
        ), tr('ui.widgets.quickstart.fixed_base_freely_moving_tip')]
    else:
        parts += [tr(
            'ui.widgets.quickstart.geometry_value_value_value_mm_material_fraction_value',
            value_0=options.length,
            value_1=options.height,
            value_2=options.depth,
            value_3=100*options.volume_fraction,
        ), tr('ui.widgets.quickstart.left_end_fixed_objective_load_cases_act_along_z')]
    parts.append(tr('ui.widgets.quickstart.objective_terms_and_their_load_cases'))
    for index, objective in enumerate(options.objectives, 1):
        label = tr(GOALS[objective.kind][0])
        if objective.kind.startswith("workspace_"):
            load = tr(
                'ui.widgets.quickstart.boundary_drives_channels_value_max_pressure_value_kpa_value_points_per_f',
                value_0=', '.join(map(str, objective.workspace_channels)),
                value_1=objective.workspace_pressure_kpa,
                value_2=objective.gauss_order,
            )
        elif shape:
            pressures = ", ".join(f"{channel}:{objective.pressures_kpa.get(
                channel,
                0.,
            ):g}" for channel in options.channel_ids)
            target = "" if objective.kind == "stiffness" else tr(
                'ui.quickstart.summary.target',
                value=f"{objective.target:g}",
            )
            load = tr('ui.widgets.quickstart.pressure_case_kpa_value_value', value_0=pressures, value_1=target)
            if objective.kind == "contact":
                load += tr('ui.widgets.quickstart.fixed_cylinder_contact')
        else:
            target = "" if objective.kind == "stiffness" else tr(
                'ui.quickstart.summary.deflection',
                value=f"{objective.target:g}",
            )
            load = tr('ui.widgets.quickstart.tip_load_z_value_n_value', value_0=objective.force_n, value_1=target)
        parts.append(tr(
            'ui.widgets.quickstart.value_value_weight_value_value',
            value_0=index,
            value_1=label,
            value_2=objective.weight,
            value_3=load,
        ))
    parts.append(tr('ui.widgets.quickstart.preview_save_or_run_the_generated_model_or_expand_its_tree_for_further_e'))
    return "<br><br>".join(parts)
