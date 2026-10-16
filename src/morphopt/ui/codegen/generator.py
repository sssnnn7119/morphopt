"""Render a :class:`~morphopt.ui.model.problem.ProblemDefinition` into the
source of a standard morphopt problem module (a top-level ``ThisController``
class), ready for ``morphopt.start_optimization`` / ``restart_optimization``.
"""

from __future__ import annotations

from ..model.node_types.parts import BoundaryPartNode, CADPartNode
from ..i18n import localized_message

import ast
import keyword
from collections.abc import Callable
from dataclasses import fields

from ...optcore.modelparams.materials import MaterialModels
from ..model.modelinfo import PartSummary, TorchFEAModelSummary
from ..model.problem import (
    CADOperationNode,
    INSTANCE_REFERENCE_FIELDS,
    FEAComponentNode,
    Node,
    ObjectiveNode,
    PartNode,
    ProblemDefinition,
    SolverNode,
    StepsNode,
    TEMPLATE_MODEL_DIRECTORY,
    UpdaterNode,
)
from ..model.registry import (
    CAD_OPERATION_TYPES,
    LOAD_TYPES,
    PART_TYPES,
    SURFACE_SYMMETRY_CONSTRAINTS,
    SURFACE_TYPES,
    surface_factory_for_type,
    UPDATER_CATALOG,
)
from ..schemes.base import SchemeTemplate, get_template


CORE_BASES = {
    "controller": "morphopt.Controller",
    "objective": "morphopt.ObjectiveFunction",
    "params": "morphopt.Params",
    "geometry": "morphopt.GeometryParams",
    "fea": "morphopt.FEAParams",
    "materials": "morphopt.MaterialsParams",
    "solver": "morphopt.Solver",
    "updaters": "morphopt.Updaters",
}

GEOMETRY_UPDATER_BASE = "morphopt.UpdaterBoundaryPart"
MATERIAL_UPDATER_BASE = "morphopt.UpdaterSIMPMaterial"
HOMOGENEOUS_MATERIAL_BASE = "morphopt.HomogeneousMaterial"
SIMP_MATERIAL_BASE = "morphopt.SIMP_BSPFieldMaterials"

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _material_parameters_expression(
    model: str,
    parameters: dict[str, object],
    problem: ProblemDefinition | None = None,
) -> str:
    """Render model parameters with their typed parameter constructor."""
    parameter_class = getattr(MaterialModels, f"{model}Params")
    parameter_type = parameter_class.__name__
    values = ", ".join(f"{key}={_render_value(value, problem)}" for key, value in parameters.items())
    return f"self.models.{parameter_type}({values})"


def indent_block(text: str, spaces: int) -> str:
    """Indent every non-empty line of ``text`` by ``spaces``."""
    pad = " " * spaces
    return "\n".join(pad + ln if ln.strip() else ln for ln in text.splitlines())


def _helper_names(problem: ProblemDefinition | None) -> set[str]:
    return {node.name for node in problem.helper_variables} if problem is not None else set()


def _render_value(value: object, problem: ProblemDefinition | None) -> str:
    """Use a helper variable as an expression when a field names it exactly."""
    if isinstance(value, str) and value in _helper_names(problem):
        return value
    if isinstance(value, list):
        return "[" + ", ".join(_render_value(item, problem) for item in value) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(_render_value(item, problem) for item in value) + ("," if len(value) == 1 else "") + ")"
    return repr(value)


# --------------------------------------------------------------------------
# surface / component / keyword rendering
# --------------------------------------------------------------------------


def _surface_factory(surface: Node) -> str:
    return surface.factory


def render_surface_call(surface: Node, problem: ProblemDefinition | None = None) -> str:
    factory = _surface_factory(surface)
    prefix = surface.custom_class or "self.FixedSurface"
    if factory is None:  # fixed_stl
        return f"{prefix}.initialize_from_stl_file({_render_value(surface.path_stl or '', problem)})"
    kwargs = []
    for field in surface.fields:
        key = field.key
        value = surface.get_field(key)
        if value is None:
            continue
        kwargs.append(f"{key}={_render_value(value, problem)}")
    kwargs.append(f"flip={repr(surface.flip)}")
    factory = (surface.custom_class + "." + factory.split(".", 1)[1]) if surface.custom_class else f"self.{factory}"
    return f"{factory}({', '.join(kwargs)})"


def render_cad_operation_call(
    operation: CADOperationNode, problem: ProblemDefinition | None = None
) -> str:
    """Render one structured UI CAD operation as a TorchFEA constructor."""
    operation_type = operation.operation_type
    spec = type(operation)
    if operation_type == "StepImport":
        return (
            "torchfea.cad.StepImport("
            f"{operation.operation_id!r}, "
            f"filename={operation.filename or 'import.step'!r}, "
            f"data={operation.data or ''!r})"
        )

    kwargs = [f"id={operation.operation_id!r}"]
    for field in spec.fields:
        key = field.key
        value = operation.get_field(key)
        if value is not None:
            expression = (
                _render_value(value, problem)
                if field.type == "float"
                else repr(value)
            )
            kwargs.append(f"{key}={expression}")
    return f"torchfea.cad.{operation_type}({', '.join(kwargs)})"


def render_component_call(component: Node, problem: ProblemDefinition | None = None) -> str:
    cls = component.backend_class
    kwargs = []
    for field in component.fields:
        key = field.key
        value = component.get_field(key)
        if value is None:
            continue
        kwargs.append(f"{key}={_render_value(value, problem)}")
    cls = component.custom_class or f"self.{cls}"
    return f"{cls}({', '.join(kwargs)})"


# --------------------------------------------------------------------------
# main generator
# --------------------------------------------------------------------------


def generate_source(problem: ProblemDefinition) -> str:
    """Read a synchronized definition and activate its custom subclasses."""
    source = generate_base_source(problem)
    custom_items = problem.updater and any(
        item.get("custom_class")
        for config in problem.updater.geometry + problem.updater.materials
        for key in ("objective_functions", "constraints")
        for item in config.get(key, [])
    )
    if problem.custom_classes or problem.class_bindings or custom_items or any(node.custom_class for node in problem.root.iter_nodes()):
        from .custom_classes import apply_custom_classes

        source = apply_custom_classes(problem, source)
    helper_blocks = [problem.helper_code]
    seen: set[str] = set()
    for node in [*problem.helper_variables, *problem.helper_functions]:
        if not node.name.isidentifier() or keyword.iskeyword(node.name) or node.name in seen:
            raise ValueError(localized_message("ui.errors.generator.invalid_or_duplicate_helper_name_value", value_0=node.name))
        seen.add(node.name)
        if node.kind == "helper_variable":
            try:
                ast.parse(node.value, mode="eval")
            except SyntaxError as exc:
                raise ValueError(localized_message("ui.errors.generator.invalid_helper_variable_value_value", value_0=node.name, value_1=exc)) from exc
            helper_blocks.append(f"{node.name} = {node.value}")
        else:
            helper_blocks.append(
                f"def {node.name}({node.parameters}):\n{indent_block(node.body or 'pass', 4)}"
            )
    return _insert_helpers(source, "\n\n".join(block for block in helper_blocks if block.strip()))


def _insert_helpers(source: str, helper_source: str) -> str:
    """Place helper definitions before custom classes and ThisController."""
    if not helper_source.strip():
        return source
    try:
        compile(helper_source, "<helper code>", "exec")
    except SyntaxError as exc:
        raise ValueError(localized_message("ui.errors.generator.invalid_helper_code_value", value_0=exc)) from exc

    first_class = next(
        node.lineno - 1 for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef)
    )
    lines = source.splitlines()
    lines[first_class:first_class] = [helper_source.rstrip(), "", ""]
    result = "\n".join(lines) + "\n"
    try:
        compile(result, "<generated model>", "exec")
    except SyntaxError as exc:
        raise ValueError(localized_message("ui.errors.generator.invalid_generated_script_value", value_0=exc)) from exc
    return result


def generate_base_source(problem: ProblemDefinition) -> str:
    """Return the full source of a runnable problem module (always headless).

    Code-launched runs never open an observer window; results are watched by
    the MorphOpt UI's in-window observer (disk polling per iteration).
    """
    template = get_template(problem.scheme)
    L: list[str] = []
    a = L.append

    controller_ref = CORE_BASES["controller"]
    run_dev = problem.device or "cpu"
    upd_dev = problem.updater_device or run_dev
    device = repr(run_dev)  # -> morphopt.start_optimization(device=...)
    upd_device = repr(upd_dev)  # -> Updater(..., device=...) (independent)

    a("import os")
    a('os.environ["MPLBACKEND"] = "Agg"')
    a("import morphopt")
    a("import torchfea")
    a("from typing import Any")
    a("")
    a("")
    a(f"class ThisController({controller_ref}):")
    a("")
    a("    def __init__(self) -> None:")
    a("        super().__init__(")
    a(
        f"            path_result_folder={repr(problem.result_folder)}, opt_label={repr(problem.label)}"
    )
    a("        )")
    a("")

    # -------- ObjectiveFunction ------------------------------------------
    objective = problem.objective or ObjectiveNode()
    jac = [item.name for item in objective.jacobian_needed]
    obj_body = objective._objective_function or template.default_objective_slot()
    met_body = objective._get_metrics or template.default_metrics_slot()

    a(f"    class ObjectiveFunction({CORE_BASES['objective']}):")
    a("")
    a("        def __init__(self) -> None:")
    a("            super().__init__()")
    if jac:
        a(f"            self.jacobian_needed = {jac!r}")
    a("")
    a("        def objective_function(self) -> Any:")
    a(indent_block(obj_body, 12))
    a("")
    a("        def get_metrics(self) -> Any:")
    a(indent_block(met_body, 12))
    a("")

    # -------- Params ------------------------------------------------------
    a(f"    class Params({CORE_BASES['params']}):")
    a("")
    a(f"        class GeometryParams({CORE_BASES['geometry']}):")
    a("")
    local_classes = _emit_part_classes(a, problem)
    a("")
    a("            def define_interface(self) -> None:")
    _emit_part_init(a, problem, local_classes)
    a("")
    a("")
    a(f"        class FEAParams({CORE_BASES['fea']}):")
    a("")
    a("            def __init__(self) -> None:")
    a("                super().__init__()")
    a("")
    a("            def define_interface(self) -> None:")
    _emit_components(a, problem)
    a("")
    a("            def define_steps(self) -> None:")
    _emit_steps(a, problem)
    a("")
    a(f"        class MaterialsParams({CORE_BASES['materials']}):")
    a("")
    _emit_material_init(a, problem, template)
    a("")
    a("        def __init__(self) -> None:")
    a("            super().__init__(")
    a(
        "                geometry=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialsParams()"
    )
    a("            )")
    a("")

    # -------- Solver ------------------------------------------------------
    a(f"    class Solver({CORE_BASES['solver']}):")
    a("")
    a("        def __init__(self, params: Any) -> None:")
    solver = problem.solver or SolverNode()
    np_ = _render_value(solver.num_process, problem)
    gpus = list(solver.gpus)
    tasklist = list(solver.task_index_list)
    args = ["params=params", f"num_process={np_}", f"available_gpus={gpus!r}"]
    if tasklist:
        args.append(f"task_index_list={tasklist!r}")
    a("")
    a("            super().__init__(" + ", ".join(args) + ")")
    a("")

    # -------- Updater -----------------------------------------------------
    _emit_updater(a, problem, template, upd_device)

    # -------- main --------------------------------------------------------
    a("")
    a('if __name__ == "__main__":')
    a(
        f"    morphopt.start_optimization(device={device}, restart_per_iteration={problem.restart_per_iteration})"
    )

    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# per-section emitters
# --------------------------------------------------------------------------

#: Part fields that must always be emitted, even when empty
#: (they are positional requirements of the Part constructor)
_REQUIRED_GEOMETRY_FIELDS = {"model_directory", "mesh_file"}


def _render_part_constructor(
    part: PartNode, class_name: str | None = None,
    problem: ProblemDefinition | None = None,
) -> str:
    """Render ``self.<ClassName>(...)`` for one Part definition.

    ``class_name`` overrides the schema type name, used when the model emits a
    local subclass (the boundary part that carries symmetry constraints).
    """
    type_name = class_name or part.type
    spec = type(part)
    kwargs = []
    for field in spec.fields:
        key = field.key
        value = part.get_field(key)
        if key not in _REQUIRED_GEOMETRY_FIELDS and (
            value is None or value == "" or value == []
        ):
            continue
        if key == "model_directory" and value == TEMPLATE_MODEL_DIRECTORY:
            value_source = (
                'os.path.join(os.path.dirname(morphopt.__file__), '
                '"ui", "templates")'
            )
            kwargs.append(f"{key}={value_source}")
        else:
            kwargs.append(f"{key}={_render_value(value if value is not None else '', problem)}")
    if not kwargs:
        return f"self.{type_name}()"
    inner = ",\n".join("    " + option for option in kwargs)
    return f"self.{type_name}(\n{inner},\n)"


def part_class_names(problem: ProblemDefinition) -> dict[str, str]:
    """Name generated subclasses after their Part type."""
    names = {}
    counts: dict[str, int] = {}
    for part in problem.parts():
        type_name = part.type
        count = counts.get(type_name, 0) + 1
        counts[type_name] = count
        names[part.name] = type_name if count == 1 else f"{type_name}{count}"
    return names


def _emit_part_classes(
    a: Callable[[str], object],
    problem: ProblemDefinition,
) -> dict[str, str]:
    """Emit local Part subclasses carrying surfaces and Instances.

    Every Part gets a local subclass so its ``define_instance`` method can
    declare the UI's complete placement list. Boundary Parts additionally
    declare their surfaces, local symmetry constraints and optional custom
    ``apply_surface_constraints`` hook.
    Returns the mapping from Part-definition names to emitted class names.
    """
    fixed_bases = {
        "BasePart": "morphopt.BasePart",
        "CADPart": "morphopt.CADPart",
        "BoxPart": "morphopt.BoxPart",
        "INPPart": "morphopt.INPPart",
        "TorchFEAPart": "morphopt.TorchFEAPart",
    }
    local_class: dict[str, str] = {}
    class_names = part_class_names(problem)

    for part in problem.parts():
        base = (
            f"morphopt.{part.type}"
            if part.has_surfaces
            else fixed_bases.get(part.type)
        )
        if not base:
            continue
        class_name = class_names[part.name]
        surfaces = part.surfaces if isinstance(part, BoundaryPartNode) else ()
        a("")
        a(f"            class {class_name}({base}):")
        a("")
        if isinstance(part, BoundaryPartNode):
            a("                def define_surfaces(self) -> None:")
            config = _geometry_config_for_part(problem, part)
            constraint_lines, custom_code = _surface_constraints_for_part(
                config, part, problem
            )
            if not surfaces and not constraint_lines:
                a("                    pass")
            for index, surface in enumerate(surfaces):
                a(
                    f"                    surface_{index} = "
                    f"{render_surface_call(surface, problem)}"
                )
                a(f"                    self.add_surface_interface(surface_{index})")
            for line in constraint_lines:
                a(f"                    {line}")
            if custom_code:
                a("")
                a("                def apply_surface_constraints(self) -> None:")
                a(indent_block(custom_code, 20))
        elif isinstance(part, CADPartNode):
            a("                def define_operations(self) -> None:")
            operations = part.operations
            if not operations:
                a("                    pass")
            for operation in operations:
                a(
                    "                    self.add_operation("
                    f"{render_cad_operation_call(operation, problem)})"
                )

        a("")
        a("                def define_instance(self) -> None:")
        instances = part.instances
        if not instances:
            a("                    super().define_instance()")
        for instance in instances:
            a("")
            pose = (
                f"[*{_render_value(instance.translation, problem)}, "
                f"*{_render_value(instance.rotation, problem)}]"
                if isinstance(instance.translation, str) or isinstance(instance.rotation, str)
                else repr(instance.pose)
            )
            a(
                "                    self.add_instance("
                f"{part.assembly_name!r}, "
                f"{instance.name!r}, "
                f"{pose})"
            )
        local_class[part.name] = class_name
    return local_class


def _emit_part_init(
    a: Callable[[str], object],
    problem: ProblemDefinition,
    local_classes: dict[str, str] | None = None,
) -> None:
    """Emit initial-geometry Part registration for the model."""
    parts = problem.parts()
    if not parts:
        a("                pass")
        return

    model = problem.imported_model_summary()
    if model is not None:
        _validate_imported_component_selections(problem, model)

    local_class = dict(local_classes or {})
    prefix = " " * 16
    for index, part in enumerate(parts):
        label = part.type
        variable = f"part_{index}"
        name = part.name or part.assembly_name or f"part{index + 1}"
        constructor = _render_part_constructor(
            part, local_class.get(part.name), problem
        ).replace("\n", "\n" + prefix)

        a("")
        a(f"                # {label}")
        a(f"                {variable} = {constructor}")
        if part.name not in local_class and isinstance(part, BoundaryPartNode):
            # a boundary part declares its surfaces in its own class
            for surface in part.surfaces:
                a(
                    f"                {variable}.add_surface_interface("
                    f"{render_surface_call(surface, problem)})"
                )
        a(f"                self.add_interface({variable}, name={name!r})")


def _validate_imported_component_selections(
    problem: ProblemDefinition,
    model: TorchFEAModelSummary,
) -> None:
    """Validate all Assembly-backed names before emitting runnable source."""
    instances = {item.name: item for item in model.instances}
    parts = {item.name: item for item in model.parts}
    for component in problem.fea_components():
        spec = type(component)
        fields_for_type = {field.key for field in spec.fields}
        boundary_instance = False
        for instance_key in ("instance_name", "instance_name1", "instance_name2"):
            if instance_key not in fields_for_type:
                continue
            target = getattr(component, INSTANCE_REFERENCE_FIELDS[instance_key])
            if target is None:
                raise ValueError(
                    localized_message("ui.errors.generator.component_value_must_select_value", value_0=component.name, value_1=instance_key)
                )
            selected = target.name
            if selected not in instances:
                owner = problem.part_for_instance(selected)
                if owner is not None and owner.has_surfaces:
                    # Boundary Parts create their node/surface sets while
                    # generating the Part.  They are not present in the
                    # imported TorchFEA archive being validated here.
                    boundary_instance = True
                    continue
                raise ValueError(
                    localized_message("ui.errors.generator.component_value_references_unknown_torchfea_instance_value", value_0=component.name, value_1=selected)
                )

        if boundary_instance:
            continue

        selections: tuple[
            tuple[str, str, Callable[[PartSummary], tuple[str, ...]]], ...
        ] = (
            ("set_nodes_name", "instance_name", lambda part: part.node_sets),
            ("surface_name", "instance_name", lambda part: part.surface_sets),
            ("surface_name1", "instance_name1", lambda part: part.surface_sets),
            ("surface_name2", "instance_name2", lambda part: part.surface_sets),
        )
        for key, instance_key, sets_of in selections:
            if key not in fields_for_type:
                continue
            selected = str(component.get_field(key, "") or "").strip()
            target = getattr(component, INSTANCE_REFERENCE_FIELDS[instance_key])
            instance_name = target.name if target is not None else ""
            if not selected:
                raise ValueError(localized_message("ui.errors.generator.component_value_must_select_value", value_0=component.name, value_1=key))
            instance = instances.get(instance_name)
            part = parts.get(instance.part_name) if instance is not None else None
            available = sets_of(part) if part is not None else ()
            if selected not in available:
                raise ValueError(
                    localized_message("ui.errors.generator.component_value_references_unknown_value_value_on_instance_value", value_0=component.name, value_1=key, value_2=selected, value_3=instance_name)
                )

        if "element_name" in fields_for_type:
            element_name = str(component.element_name or "").strip()
            instance_name = component.instance.name if component.instance else ""
            instance = instances.get(instance_name)
            part = parts.get(instance.part_name) if instance is not None else None
            if part is None or element_name not in part.element_types:
                raise ValueError(
                    localized_message("ui.errors.generator.component_value_references_unknown_element_value_on_instance_value", value_0=component.name, value_1=element_name, value_2=instance_name)
                )


def _geometry_config_for_part(
    problem: ProblemDefinition, part: PartNode
) -> dict | None:
    """Return the geometry updater config bound to ``part``, if any."""
    updater = problem.updater
    if updater is None:
        return None
    return next(
        (
            config
            for config in updater.geometry
            if problem.config_part_node(config) is part
        ),
        None,
    )


def _surface_constraints_for_part(
    config: dict | None,
    part: BoundaryPartNode,
    problem: ProblemDefinition,
) -> tuple[list[str], str]:
    """Render surface-owned symmetry hooks and an optional Part code hook."""
    if config is None:
        return [], ""

    surfaces = part.surfaces
    statements: list[str] = []
    custom_bodies: list[str] = []
    for item in config.get("symmetry_constraints", []) or []:
        if not isinstance(item, dict):
            raise ValueError(localized_message("ui.errors.generator.invalid_geometry_symmetry_constraint_value", value_0=item))
        item_type = item.get("type")
        spec = SURFACE_SYMMETRY_CONSTRAINTS.get(item_type)
        if spec is None:
            raise ValueError(localized_message("ui.errors.generator.unknown_geometry_symmetry_constraint_value", value_0=item_type))
        params = item.get("params") or {}
        if item_type == "Custom":
            custom_bodies.append(str(params.get("code") or ""))
            continue

        surface_index = item.get("surface_index")
        if not isinstance(surface_index, int) or not 0 <= surface_index < len(surfaces):
            raise ValueError(
                localized_message("ui.errors.generator.geometry_symmetry_constraint_value_on_part_value_references_invalid_surface", value_0=item_type, value_1=part.name, value_2=surface_index)
            )
        surface = surfaces[surface_index]
        surface_factory = surface_factory_for_type(surface.surface_type)
        if surface_factory != spec.factory:
            raise ValueError(
                localized_message("ui.errors.generator.geometry_symmetry_constraint_value_requires_a_value_surface_surface_value", value_0=item_type, value_1=spec.factory, value_2=surface_index, value_3=part.name, value_4=surface.surface_type)
            )

        method_args = []
        if spec.related_surface:
            related_index = item.get("related_surface_index")
            if not isinstance(related_index, int) or not 0 <= related_index < len(surfaces):
                raise ValueError(
                    localized_message("ui.errors.generator.geometry_symmetry_constraint_value_on_part_value_references_invalid_related", value_0=item_type, value_1=part.name, value_2=related_index)
                )
            related = surfaces[related_index]
            related_factory = surface_factory_for_type(related.surface_type)
            if related_factory != spec.factory:
                raise ValueError(
                    localized_message("ui.errors.generator.geometry_symmetry_constraint_value_requires_both_surfaces_to_use_value", value_0=item_type, value_1=spec.factory)
                )
            method_args.append(f"surface_{related_index}")

        kwargs = []
        for field in spec.fields:
            key = field.key
            value = params.get(key, field.new_default())
            kwargs.append(f"{key}={_render_value(value, problem)}")
        surface_name = f"surface_{surface_index}"
        statements.append(
            f"{surface_name}.add_constraint("
            f"{surface_name}.{spec.method}({', '.join(method_args + kwargs)}))"
        )

    return statements, _clean_body("\n\n".join(custom_bodies))


def _clean_body(code: str) -> str:
    body = str(code or "").strip()
    return "" if not body or body == "pass" else body


def _emit_components(a: Callable[[str], object], problem: ProblemDefinition) -> None:
    components = [it for it in problem.fea_components() if it.type]
    if not components:
        a("                pass")
        return
    for it in components:
        a(
            f"                self.add_interface({render_component_call(it, problem)}, name={it.name!r})"
        )


def _emit_steps(a: Callable[[str], object], problem: ProblemDefinition) -> None:
    steps = problem.steps or StepsNode(
        name="Load steps", params={"num_steps": 1, "step_values": [{}]}
    )
    n = int(steps.num_steps)

    values = list(steps.step_values) or [{} for _ in range(n)]
    while len(values) < n:
        values.append({})

    # every amplitude-bearing load component must be set for every step, so a
    # load that was added but left unset in a step is written explicitly as a
    # zero amplitude (matching the step-matrix UI, where an empty cell is 0).
    amps: dict[FEAComponentNode, int] = {}
    for it in problem.fea_components():
        nv = it.num_values
        if nv and it.name:
            amps[it] = nv

    a(f"                self.set_step_num({n})")
    for s in range(n):
        step_dict = (values[s] if s < len(values) else {}) or {}
        for component, nv in amps.items():
            stored = step_dict.get(component)
            amps_values = stored if stored is not None else [0.0] * nv
            a(
                f"                self.set_step_params({s}, {component.name!r}, "
                f"{_render_value(amps_values, problem)})"
            )


def _emit_material_init(
    a: Callable[[str], object],
    problem: ProblemDefinition,
    template: SchemeTemplate,
) -> None:
    materials = problem.material_nodes()
    if not materials:
        a("            def __init__(self) -> None:")
        a("                super().__init__()")
        a("")
        a("            def define_interface(self) -> None:")
        a("                pass")
        return

    a("            def __init__(self) -> None:")
    a("                super().__init__()")
    a("")
    a("            def define_interface(self) -> None:")
    for index, mat in enumerate(materials):
        mtype = mat.material_type or template.MATERIAL_TYPE
        model = mat.get_field("material_model", "NeoHookeanLnJ")
        parameter_class = getattr(MaterialModels, f"{model}Params")
        model_keys = tuple(field.name for field in fields(parameter_class))

        base = HOMOGENEOUS_MATERIAL_BASE
        if mtype == "SIMP_BSPFieldMaterials":
            base = SIMP_MATERIAL_BASE

        material_class = mat.custom_class or base
        kw = []
        if mtype == "SIMP_BSPFieldMaterials":
            keys = [
                "part_name",
                "elementname",
                "mumax",
                "kappamax",
                "density",
                "simp_ratio_min",
                "initial_ratio",
                "voidpenalfactor",
                "materialpenalty",
                "bounding_box",
                "simp_field_resolution",
                "degree",
            ]
            material_parameters = {key: mat.get_field(key) for key in model_keys}
            if model in ("NeoHookean", "NeoHookeanLnJ"):
                material_parameters = {
                    "mu": mat.get_field("mumax"),
                    "kappa": mat.get_field("kappamax"),
                }
            kw.append(
                "material_parameters="
                + _material_parameters_expression(model, material_parameters, problem)
            )
        else:
            keys = ["part_name", "elementname", "density"]
            material_parameters = {key: mat.get_field(key) for key in model_keys}
            kw.append(
                "material_parameters="
                + _material_parameters_expression(model, material_parameters, problem)
            )
        for key in keys:
            value = mat.get_field(key)
            if value is not None:
                kw.append(f"{key}={_render_value(value, problem)}")

        a("")
        name = mat.name or f"material_{index}"
        a(f"                self.add_interface({material_class}(")
        for option in kw:
            a(f"                    {option},")
        a(f"                ), name={name!r})")


def _resolve_geometry_targets(
    problem: ProblemDefinition, geom_cfgs: list[dict]
) -> list[str]:
    """Validate the Part every geometry sub-updater is bound to.

    Only boundary Parts carry surfaces, so an updater must target one
    of those Part objects.
    """
    if not geom_cfgs:
        return []
    boundary = problem.boundary_part_nodes()
    if not boundary:
        raise ValueError(
            localized_message("ui.errors.generator.a_geometry_optimizer_needs_a_boundary_part_inp_torchfea")
        )
    targets: list[str] = []
    for index, cfg in enumerate(geom_cfgs):
        target = problem.config_part_node(cfg)
        if target is None:
            raise ValueError(
                localized_message("ui.errors.generator.geometry_optimizer_value_has_no_target_boundary_part_choose_one", value_0=index + 1, value_1=[node.name for node in boundary])
            )
        name = target.name
        if name in targets:
            raise ValueError(
                localized_message("ui.errors.generator.two_geometry_optimizers_both_target_value_give_each_one_its", value_0=name)
            )
        targets.append(name)
    return targets


def _resolve_material_targets(
    problem: ProblemDefinition, mat_cfgs: list[dict]
) -> list[str]:
    """Validate the material definition every material sub-updater targets.

    Only design-carrying materials (SIMP density fields) have
    variables, so an updater must target one of those material objects.
    """
    if not mat_cfgs:
        return []
    design = [
        material
        for material in problem.material_nodes()
        if material.name in problem.design_material_names()
    ]
    if not design:
        raise ValueError(
            localized_message("ui.errors.generator.a_material_optimizer_needs_a_design_carrying_material_simp")
        )
    targets: list[str] = []
    for index, cfg in enumerate(mat_cfgs):
        target = problem.config_material_node(cfg)
        if target is None or target not in design:
            raise ValueError(
                localized_message("ui.errors.generator.material_optimizer_value_has_no_target_design_material_choose_one", value_0=index + 1, value_1=[material.name for material in design])
            )
        name = target.name
        if name in targets:
            raise ValueError(
                localized_message("ui.errors.generator.two_material_optimizers_both_target_value_give_each_one_its", value_0=name)
            )
        targets.append(name)
    return targets


def _emit_updater(
    a: Callable[[str], object],
    problem: ProblemDefinition,
    template: SchemeTemplate,
    device: str,
) -> None:
    upd = problem.updater or UpdaterNode()
    geom_cfgs = upd.geometry
    geom_targets = _resolve_geometry_targets(problem, geom_cfgs)
    mat_cfgs = upd.materials
    mat_targets = _resolve_material_targets(problem, mat_cfgs)
    has_geom = bool(geom_cfgs)
    has_mat = bool(mat_cfgs)
    if not has_geom and not has_mat:
        a(f"    class Updater({CORE_BASES['updaters']}):")
        a("")
        a("        def __init__(self, params: Any) -> None:")
        a("            super().__init__(params=params)")
        return

    geometry_classes = [
        "UpdaterBoundaryPart" if index == 0 else f"UpdaterBoundaryPart{index}"
        for index in range(len(geom_cfgs))
    ]
    material_classes = [
        "UpdaterSIMPMaterial" if index == 0 else f"UpdaterSIMPMaterial{index}"
        for index in range(len(mat_cfgs))
    ]

    a(f"    class Updater({CORE_BASES['updaters']}):")
    a("")
    a("        def define_updater(self) -> None:")
    for class_name, target in zip(geometry_classes, geom_targets):
        a(
            f"            self.add_geometry_updater("
            f"self.{class_name}(), name={target!r})"
        )
    for class_name, target in zip(material_classes, mat_targets):
        a(
            f"            self.add_material_updater("
            f"self.{class_name}(), name={target!r})"
        )
    a("")
    a("        def __init__(self, params: Any) -> None:")
    a(f"            super().__init__(params=params, device={device})")
    a("")
    for class_name, config in zip(geometry_classes, geom_cfgs):
        target = problem.config_part_node(config)
        base = (
            "morphopt.UpdaterOffsetBoundaryPart"
            if target.type == "OffsetBoundaryPart"
            else GEOMETRY_UPDATER_BASE
        )
        _emit_nested_updater(a, class_name, base, config, problem)
        a("")
    for class_name, config in zip(material_classes, mat_cfgs):
        _emit_nested_updater(a, class_name, MATERIAL_UPDATER_BASE, config, problem)
        a("")


def _render_updater_item(item: dict, category: str, problem: ProblemDefinition | None = None) -> str:
    """Render one valid structured objective/constraint item into source."""
    if not isinstance(item, dict):
        raise ValueError(localized_message("ui.errors.generator.invalid_updater_item_value", value_0=item))
    if item.get("type") == "Custom" and item.get("custom_class"):
        return f"{item['custom_class']}()"
    cat = UPDATER_CATALOG.get(category, {})
    spec = cat.get(item.get("type", ""))
    if spec is None:
        raise ValueError(localized_message("ui.errors.generator.unknown_updater_value_type_value", value_0=category, value_1=item.get('type')))
    gen = spec.gen
    if not gen:
        raise ValueError(localized_message("ui.errors.generator.missing_generator_for_updater_item_value", value_0=item['type']))
    if item.get("custom_class"):
        gen = item["custom_class"] + gen[gen.index("("):]
    params = dict(item.get("params") or {})
    for f in spec.fields:
        params.setdefault(f.key, f.new_default())
    if (
        item.get("type") == "VolFrac"
        and not str(params.get("elementname") or "").strip()
    ):
        raise ValueError(localized_message("ui.errors.generator.volfrac_requires_an_explicit_elems_name"))
    fmt = {k: _render_value(v, problem) for k, v in params.items()}
    try:
        return gen.format(**fmt)
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(localized_message("ui.errors.generator.invalid_updater_parameters_value", value_0=item['type'])) from exc


def _emit_nested_updater(
    a: Callable[[str], object], cls_name: str, base: str, cfg,
    problem: ProblemDefinition,
) -> None:
    """Emit one sub-updater class.

    The class is **target-free** -- it carries the objectives / constraints of
    one sub-optimizer and nothing else. Which Part or material definition it
    optimizes is stated by the ``name`` of the ``add_*_updater(...)`` call that
    registers it, so the same class can be registered several times for
    different targets.  Objectives are declared in ``define_objective()`` and
    registered once when the updater is added, matching the model-parameter
    registration pattern. The hook must not access the bound target.
    """
    cfg = cfg or {}
    if "code" in cfg:
        raise ValueError(localized_message("ui.errors.generator.raw_updater_code_is_unsupported_use_method_overrides"))
    a(f"        class {cls_name}({base}):")
    a("")
    a("            def __init__(self) -> None:")
    a(f"                super().__init__(max_step_iter={_render_value(cfg.get('max_step_iter', 50), problem)})")

    body: list[str] = []
    # NOTE: the model stores the lists under ``objective_functions`` / ``constraints``
    # while the catalogue (UPDATER_CATALOG) is keyed ``objectives`` / ``constraints``.
    for model_key, catalog_key, call in (
        ("objective_functions", "objectives", "add_objective_function"),
        ("constraints", "constraints", "add_constraints"),
    ):
        for item in cfg.get(model_key, []) or []:
            line = _render_updater_item(item, catalog_key, problem)
            body.append(f"self.{call}({line})")

    if "if_update" in cfg and cfg["if_update"] is not None:
        body.append(f"self.if_update = {cfg['if_update']!r}")

    if not body:
        return
    a("")
    a("            def define_objective(self) -> None:")
    for line in body:
        a(indent_block(line, 16))
