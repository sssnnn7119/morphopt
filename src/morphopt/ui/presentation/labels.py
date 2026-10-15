"""Shared naming for navigation, editor cards, menus and object selectors."""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ..codegen.custom_classes import class_path_for_node
from ..i18n import tr
from ..model.problem import (
    CADOperationNode,
    CustomClassNode,
    InstanceNode,
    FEAComponentNode,
    MaterialNode,
    Node,
    PartNode,
    ProblemDefinition,
    SurfaceNode,
)
from ..model.schemas import (
    CAD_OPERATION_TYPES,
    INTERFACE_TYPES,
    MATERIAL_TYPES,
    SURFACE_TYPES,
    UPDATER_CATALOG,
    SURFACE_SYMMETRY_CONSTRAINTS,
)

if TYPE_CHECKING:
    from .navigation import UpdaterItemTreeNode, UpdaterTreeNode


CONTAINER_TITLE_KEYS = {
    "problem": "ui.widgets.model_tree.container.problem",
    "helper_code": "ui.widgets.model_tree.container.helper_code",
    "helper_code_block": "ui.widgets.model_tree.container.helper_code_block",
    "helper_variables_group": "ui.widgets.model_tree.container.helper_variables_group",
    "helper_functions_group": "ui.widgets.model_tree.container.helper_functions_group",
    "custom_classes": "ui.widgets.model_tree.container.custom_classes",
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

CONTAINER_CLASSES = {
    "problem": "Controller",
    "params_class": "Params",
    "geometry": "GeometryParams",
    "loads_group": "FEAParams",
    "materials": "MaterialsParams",
    "objective": "ObjectiveFunction",
    "solver": "Solver",
    "updater": "Updaters",
}

UPDATER_TITLE_KEYS = {
    "geometry": "ui.widgets.model_tree.updater.geometry",
    "materials": "ui.widgets.model_tree.updater.materials",
    "geometry_objectives": "ui.widgets.model_tree.updater.objectives",
    "geometry_symmetry": "ui.widgets.model_tree.updater.geometry_symmetry",
    "geometry_penalty": "ui.widgets.model_tree.updater.geometry_penalty",
    "materials_objectives": "ui.widgets.model_tree.updater.objectives",
    "materials_penalty": "ui.widgets.model_tree.updater.materials_penalty",
}


def typed_title(name: str, class_name: str | None) -> str:
    """Use ``name [ClassName]`` for objects; plain names for groups and hooks."""
    return tr("ui.naming.object_title", name=name, class_name=class_name) if class_name else name


def container_title(kind: str, class_name: str | None = None) -> str:
    key = CONTAINER_TITLE_KEYS.get(kind)
    label = tr(key) if key else kind
    return typed_title(label, class_name or CONTAINER_CLASSES.get(kind))


def schema_label(spec: dict, key: str) -> str:
    """Localized type description with the catalog's Python class name."""
    label = tr(spec["label_key"]) if spec.get("label_key") else key
    title = typed_title(label, spec.get("class_name"))
    return tr("ui.naming.updatable_title", title=title) if spec.get("design") else title


def surface_title_text(surface: SurfaceNode, index: int) -> str:
    spec = SURFACE_TYPES.get(surface.surface_type, {})
    return typed_title(
        surface.name or f"surface_{index}",
        surface.custom_class or spec.get("class_name"),
    )


def part_interface_title_text(part: PartNode) -> str:
    title = typed_title(
        part.name or part.resolved_part_name(),
        part.custom_class or part.interface_type,
    )
    return tr("ui.naming.updatable_title", title=title) if part.is_updatable else title


def instance_title_text(instance: InstanceNode) -> str:
    return typed_title(instance.name, "Instance")


def cad_operation_title_text(operation: CADOperationNode) -> str:
    return typed_title(
        operation.operation_id,
        CAD_OPERATION_TYPES[operation.operation_type]["class_name"],
    )


def cad_operation_summary_text(operation: CADOperationNode) -> str:
    """Keep CAD dependencies available without extending every tree title."""
    title = schema_label(CAD_OPERATION_TYPES[operation.operation_type], operation.operation_type)
    inputs = [
        value for value in (operation.object_id, operation.tool_id, operation.input_id)
        if value
    ]
    if inputs:
        return title + "\n" + tr("ui.naming.cad_inputs", inputs=", ".join(inputs))
    return title


def surface_index(problem: ProblemDefinition | None, surface: SurfaceNode) -> int | None:
    owner = problem.owner_of_surface(surface) if problem is not None else None
    return owner.surfaces().index(surface) if owner is not None else None


def interface_title_text(interface: FEAComponentNode) -> str:
    spec = INTERFACE_TYPES.get(interface.interface_type, {})
    return typed_title(
        interface.name or interface.interface_type,
        interface.custom_class or spec.get("class_name"),
    )


def material_title_text(material: MaterialNode) -> str:
    spec = MATERIAL_TYPES.get(material.material_type, {})
    title = typed_title(
        material.name or material.material_type,
        material.custom_class or spec.get("class_name"),
    )
    return tr("ui.naming.updatable_title", title=title) if material.is_updatable else title


def component_update_description(component: PartNode | MaterialNode) -> str:
    """Describe the component's existing design capability; it is not a toggle."""
    if isinstance(component, PartNode):
        key = "ui.component.geometry_updatable" if component.is_updatable else "ui.component.geometry_fixed"
    else:
        key = "ui.component.material_updatable" if component.is_updatable else "ui.component.material_fixed"
    return tr(key)


def updater_group_title(group: str) -> str:
    return tr(UPDATER_TITLE_KEYS[group])


def updater_section_title_text(problem: ProblemDefinition, group: str, config: dict) -> str:
    """Describe the target and the actual optimizer class in both tree and page."""
    if group == "geometry":
        target = problem.config_part_node(config)
        class_name = (
            "UpdaterOffsetBoundaryPart"
            if target is not None and target.interface_type == "OffsetBoundaryPart"
            else "UpdaterBoundaryPart"
        )
    else:
        target = problem.config_material_node(config)
        class_name = "UpdaterSIMPMaterial"
    label = updater_group_title(group)
    if target is not None:
        label = tr("ui.naming.optimizer_for_target", target=target.name)
    return typed_title(label, class_name)


def updater_title_text(problem: ProblemDefinition | None, node: UpdaterTreeNode) -> str:
    if node.kind == "updater_item":
        item = cast("UpdaterItemTreeNode", node).item
        category = "objectives" if node.group.endswith("objectives") else "constraints"
        catalog = SURFACE_SYMMETRY_CONSTRAINTS if node.group.endswith("symmetry") else UPDATER_CATALOG[category]
        return updater_item_title_text(item, catalog.get(item["type"], {}))
    if node.group in {"geometry", "materials"} and problem is not None:
        config = node.config()
        if config is not None:
            return updater_section_title_text(problem, node.group, config)
    return updater_group_title(node.group)


def updater_item_title_text(item: dict, spec: dict) -> str:
    if spec:
        label = tr(spec["label_key"])
    else:
        label = tr("ui.naming.custom") if item["type"] == "Custom" else item["type"]
    return typed_title(label, item.get("custom_class") or spec.get("class_name"))


def node_title(problem: ProblemDefinition | None, node: Node) -> str:
    """Canonical object title, including the selected custom class."""
    if isinstance(node, PartNode):
        return part_interface_title_text(node)
    if isinstance(node, InstanceNode):
        return instance_title_text(node)
    if isinstance(node, CADOperationNode):
        return cad_operation_title_text(node)
    if isinstance(node, FEAComponentNode):
        return interface_title_text(node)
    if isinstance(node, MaterialNode):
        return material_title_text(node)
    if isinstance(node, SurfaceNode):
        return surface_title_text(node, surface_index(problem, node) or 0)
    if node.kind.startswith("updater_"):
        return updater_title_text(problem, cast("UpdaterTreeNode", node))
    if node.kind in {"helper_variable", "helper_function"}:
        return node.name + ("()" if node.kind == "helper_function" else "")
    if isinstance(node, CustomClassNode):
        return typed_title(node.name, node.base_class.rsplit(".", 1)[-1])
    if node.kind == "method_override":
        return node.name + "()"
    path = class_path_for_node(node)
    selected = problem.class_bindings.get(path) if problem is not None and path else None
    return container_title(node.kind, selected or node.custom_class or None)


def reference_choice_title(problem: ProblemDefinition | None, key: str, name: object) -> str | None:
    """Decorate object names for display while selectors retain raw values."""
    if problem is None or not name:
        return None
    if key in {"instance_name", "instance_name1", "instance_name2"}:
        return typed_title(str(name), "Instance")
    if key in {
        "rp_name", "rp_name1", "rp_name2",
        "force_load_name", "moment_load_name", "reference_point_name",
    }:
        interface = next((node for node in problem.interfaces() if node.name == name), None)
        return interface_title_text(interface) if interface is not None else None
    if key == "part_name":
        part = next(
            (node for node in problem.part_interfaces() if node.resolved_part_name() == name),
            None,
        )
        if part is not None:
            return typed_title(str(name), part.custom_class or part.interface_type)
    return None


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
