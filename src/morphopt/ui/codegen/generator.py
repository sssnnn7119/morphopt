"""Render a :class:`~morphopt.ui.model.problem.ProblemDefinition` into the
source of a standard morphopt problem module (a top-level ``ThisController``
class), ready for ``morphopt.start_optimization`` / ``restart_optimization``.
"""

from __future__ import annotations

import ast
import keyword
import math
from collections.abc import Callable
from dataclasses import fields

from ...constants import CONSTANT
from ...optcore.modelparams.materials import MaterialModels
from ..i18n import localized_message
from ..model.node_types.parts import BoundaryPartNode, CADPartNode
from ..model.problem import (
    CADOperationNode,
    Node,
    ObjectiveNode,
    PartNode,
    ProblemDefinition,
    SolverNode,
    UpdaterNode,
)
from ..model.registry import (
    SURFACE_SYMMETRY_CONSTRAINTS,
    UPDATER_CATALOG,
    surface_factory_for_type,
)
from ..schemes.base import SchemeTemplate, get_template
from .assets import collect_python_assets
from .workspace import workspace_integral_body

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
    values = ", ".join(
        f"{key}={_render_value(value, problem)}" for key, value in parameters.items()
    )
    return f"self.models.{parameter_type}({values})"


def indent_block(text: str, spaces: int) -> str:
    """Indent every non-empty line of ``text`` by ``spaces``."""
    pad = " " * spaces
    return "\n".join(pad + ln if ln.strip() else ln for ln in text.splitlines())


def _helper_names(problem: ProblemDefinition | None) -> set[str]:
    return (
        {node.name for node in problem.helper_variables}
        if problem is not None
        else set()
    )


def _render_value(value: object, problem: ProblemDefinition | None) -> str:
    """Use a helper variable as an expression when a field names it exactly."""
    if isinstance(value, str) and value in _helper_names(problem):
        return value
    if isinstance(value, list):
        return "[" + ", ".join(_render_value(item, problem) for item in value) + "]"
    if isinstance(value, tuple):
        return (
            "("
            + ", ".join(_render_value(item, problem) for item in value)
            + ("," if len(value) == 1 else "")
            + ")"
        )
    return repr(value)


# --------------------------------------------------------------------------
# surface / component / keyword rendering
# --------------------------------------------------------------------------


def _asset_path_expression(path: str) -> str:
    """Resolve an exported asset relative to the generated Python module."""
    if not path:
        return repr("")
    return f"os.path.join(os.path.dirname(os.path.abspath(__file__)), {path!r})"


def render_surface_call(
    surface: Node,
    problem: ProblemDefinition | None = None,
    *,
    asset_paths: dict[int, str] | None = None,
) -> str:
    factory = surface.factory
    if surface.type == "brep_surface":
        prefix = surface.custom_class or "self.BREPSurface"
        path_expression = (
            _asset_path_expression(asset_paths[id(surface)])
            if surface.data
            else repr("")
        )
        spacing = _render_value(surface.control_point_spacing, problem)
        return f"{prefix}({path_expression}, control_point_spacing={spacing})"
    prefix = surface.custom_class or "self.MeshSurface"
    if factory is None:  # mesh_surface
        path_expression = (
            _asset_path_expression(asset_paths[id(surface)])
            if surface.path_stl
            else repr("")
        )
        return f"{prefix}.initialize_from_stl_file({path_expression})"
    kwargs = []
    for field in surface.fields:
        key = field.key
        value = surface.get_field(key)
        if value is None:
            continue
        kwargs.append(f"{key}={_render_value(value, problem)}")
    kwargs.append(f"flip={surface.flip!r}")
    factory = (
        (surface.custom_class + "." + factory.split(".", 1)[1])
        if surface.custom_class
        else f"self.{factory}"
    )
    return f"{factory}({', '.join(kwargs)})"


def render_cad_operation_call(
    operation: CADOperationNode,
    problem: ProblemDefinition | None = None,
    *,
    asset_paths: dict[int, str] | None = None,
) -> str:
    """Render one structured UI CAD operation as a TorchFEA constructor."""
    operation_type = operation.operation_type
    spec = type(operation)
    if operation_type == "StepImport":
        return (
            "torchfea.cad.StepImport.from_file("
            f"{operation.operation_id!r}, {_asset_path_expression(asset_paths[id(operation)])})"
        )

    kwargs = [f"id={operation.operation_id!r}"]
    for field in spec.fields:
        key = field.key
        value = operation.get_field(key)
        if value is not None:
            expression = (
                _render_value(value, problem) if field.type == "float" else repr(value)
            )
            kwargs.append(f"{key}={expression}")
    return f"torchfea.cad.{operation_type}({', '.join(kwargs)})"


def render_component_call(
    component: Node, problem: ProblemDefinition | None = None
) -> str:
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


def generate_source(
    problem: ProblemDefinition, *, asset_paths: dict[int, str] | None = None
) -> str:
    """Read a synchronized definition and activate its custom subclasses."""
    source = generate_base_source(problem, asset_paths=asset_paths)
    custom_items = problem.updater and any(
        config.get("custom_class")
        or any(
            item.get("custom_class")
            for key in ("objective_functions", "constraints")
            for item in config.get(key, [])
        )
        for config in problem.updater.geometry + problem.updater.materials
    )
    if (
        problem.custom_classes
        or problem.class_bindings
        or custom_items
        or any(node.custom_class for node in problem.root.iter_nodes())
    ):
        from .custom_classes import apply_custom_classes

        source = apply_custom_classes(problem, source)
    helper_blocks = [problem.helper_code]
    seen: set[str] = set()
    for node in [*problem.helper_variables, *problem.helper_functions]:
        if (
            not node.name.isidentifier()
            or keyword.iskeyword(node.name)
            or node.name in seen
        ):
            raise ValueError(
                localized_message(
                    "ui.errors.generator.invalid_or_duplicate_helper_name_value",
                    value_0=node.name,
                )
            )
        seen.add(node.name)
        if node.kind == "helper_variable":
            try:
                ast.parse(node.value, mode="eval")
            except SyntaxError as exc:
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.invalid_helper_variable_value_value",
                        value_0=node.name,
                        value_1=exc,
                    )
                ) from exc
            helper_blocks.append(f"{node.name} = {node.value}")
        else:
            helper_blocks.append(
                f"def {node.name}({node.parameters}):\n{indent_block(node.body or 'pass', 4)}"
            )
    return _insert_helpers(
        source, "\n\n".join(block for block in helper_blocks if block.strip())
    )


def _insert_helpers(source: str, helper_source: str) -> str:
    """Place helper definitions before custom classes and ThisController."""
    if not helper_source.strip():
        return source
    try:
        compile(helper_source, "<helper code>", "exec")
    except SyntaxError as exc:
        raise ValueError(
            localized_message(
                "ui.errors.generator.invalid_helper_code_value", value_0=exc
            )
        ) from exc

    first_class = next(
        node.lineno - 1
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef)
    )
    lines = source.splitlines()
    lines[first_class:first_class] = [helper_source.rstrip(), "", ""]
    result = "\n".join(lines) + "\n"
    try:
        compile(result, "<generated model>", "exec")
    except SyntaxError as exc:
        raise ValueError(
            localized_message(
                "ui.errors.generator.invalid_generated_script_value", value_0=exc
            )
        ) from exc
    return result


def _objective_function_body(
    objective: ObjectiveNode, problem: ProblemDefinition
) -> str:
    """Generate one local measurement function per ordered objective term."""
    terms = objective.objective_terms
    if not terms:
        return "return 0.0"

    reference_points = {
        component.name
        for component in problem.fea_components()
        if component.type == "ReferencePoint" and component.name
    }
    steps = problem.steps
    component_indices = dict(CONSTANT.UI.OBJECTIVE.DISPLACEMENT_COMPONENTS)
    functions: list[str] = []
    weighted_terms: list[str] = []
    positive_weight = False

    for index, term in enumerate(terms):
        term_type = str(term.get("type") or "")
        try:
            weight = float(term["weight"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.objective_term_has_invalid_values"
                )
            ) from exc
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.objective_term_has_invalid_values"
                )
            )
        positive_weight = positive_weight or weight > 0

        function_name = f"objective_term_{index + 1}"
        if term_type == CONSTANT.UI.OBJECTIVE.TYPE_DISPLACEMENT:
            direction = str(
                term.get("direction", CONSTANT.UI.OBJECTIVE.DEFAULT_DIRECTION)
            )
            if direction not in {
                CONSTANT.UI.OBJECTIVE.DIRECTION_TARGET,
                CONSTANT.UI.OBJECTIVE.DIRECTION_MAXIMIZE,
                CONSTANT.UI.OBJECTIVE.DIRECTION_MINIMIZE,
            }:
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.objective_has_unknown_direction_value",
                        value_0=direction,
                    )
                )
            target = CONSTANT.UI.OBJECTIVE.DEFAULT_TARGET
            if direction == CONSTANT.UI.OBJECTIVE.DIRECTION_TARGET:
                try:
                    target = float(
                        term.get("target", CONSTANT.UI.OBJECTIVE.DEFAULT_TARGET)
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        localized_message(
                            "ui.errors.generator.objective_term_has_invalid_values"
                        )
                    ) from exc
                if not math.isfinite(target):
                    raise ValueError(
                        localized_message(
                            "ui.errors.generator.objective_term_has_invalid_values"
                        )
                    )
            reference_point = str(term.get("reference_point_name") or "").strip()
            component = str(term.get("component") or "")
            step_name = term.get("step_name")
            if reference_point not in reference_points:
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.objective_references_unknown_point_value",
                        value_0=reference_point,
                    )
                )
            if not isinstance(step_name, str) or step_name not in steps.step_values:
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.objective_references_unknown_step_value",
                        value_0=step_name,
                    )
                )
            if component not in component_indices:
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.objective_has_unknown_component_value",
                        value_0=component,
                    )
                )
            functions.extend(
                [
                    f"def {function_name}() -> Any:",
                    f"    self.set_step({step_name!r})",
                    "    assembly = self.fe.assembly",
                    "    state = assembly._GC2RGC(",
                    f"        self.fe_results[{step_name!r}].GC.to(assembly.device)",
                    "    )",
                    f"    reference_point = assembly.get_reference_point({reference_point!r})",
                    "    return state[reference_point._RGC_index].reshape(-1)["
                    f"{component_indices[component]}]",
                ]
            )
            if direction == CONSTANT.UI.OBJECTIVE.DIRECTION_TARGET:
                weighted_terms.append(
                    f"({weight!r}) * ({function_name}() - {target!r}) ** 2"
                )
            elif direction == CONSTANT.UI.OBJECTIVE.DIRECTION_MAXIMIZE:
                weighted_terms.append(f"-({weight!r}) * {function_name}()")
            else:
                weighted_terms.append(f"({weight!r}) * {function_name}()")
        elif term_type == CONSTANT.UI.OBJECTIVE.TYPE_WORKSPACE:
            from ..application.load_cases import workspace_spec

            spec = workspace_spec(term, problem)
            if len(term.get("case_names", [])) != len(spec["points"]) or any(
                name not in steps.step_values for name in term.get("case_names", [])
            ):
                raise ValueError(
                    localized_message("ui.workspace_objective.generate_required")
                )
            scale = float(term.get("normalization", 1.0))
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError("Workspace normalization must be positive.")
            body = workspace_integral_body(
                reference_point_name=term["reference_point_name"],
                axes=spec["axes"],
                load_groups=[
                    [(name, component) for name, component in entry["parameters"]]
                    for entry in term["inputs"]
                ],
                case_names=term["case_names"],
                weights=spec["weights"],
                tangents=spec["tangents"],
                orientations=spec["orientations"],
            )
            functions.extend(
                [
                    f"def {function_name}() -> Any:",
                    indent_block(body, 4),
                ]
            )
            weighted_terms.append(f"-({weight!r}) * {function_name}() / {scale!r}")
        elif term_type == CONSTANT.UI.OBJECTIVE.TYPE_CUSTOM_LOSS:
            body = str(term.get("body") or "").strip()
            if not body:
                raise ValueError(
                    localized_message("ui.errors.generator.objective_term_needs_code")
                )
            try:
                ast.parse("def _objective_term():\n" + indent_block(body, 4) + "\n")
            except SyntaxError as exc:
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.objective_term_has_invalid_code_value",
                        value_0=exc,
                    )
                ) from exc
            functions.extend(
                [
                    f"def {function_name}() -> Any:",
                    indent_block(body, 4),
                ]
            )
            weighted_terms.append(f"({weight!r}) * {function_name}()")
        else:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.objective_has_unknown_term_type_value",
                    value_0=term_type,
                )
            )

    if not positive_weight:
        raise ValueError(
            localized_message("ui.errors.generator.objective_needs_positive_weight")
        )
    return "\n".join([*functions, "return " + " + ".join(weighted_terms)])


def _metrics_function_body(objective: ObjectiveNode, problem: ProblemDefinition) -> str:
    """Generate an ordered list of displacement and custom metric functions."""
    terms = objective.metrics_terms
    reference_points = {
        component.name
        for component in problem.fea_components()
        if component.type == "ReferencePoint" and component.name
    }
    steps = problem.steps
    component_indices = dict(CONSTANT.UI.OBJECTIVE.DISPLACEMENT_COMPONENTS)
    functions: list[str] = []
    values: list[str] = []

    for index, term in enumerate(terms):
        metric_type = str(term.get("type") or "")
        function_name = f"metric_term_{index + 1}"
        if metric_type == CONSTANT.UI.METRIC.TYPE_DISPLACEMENT:
            reference_point = str(term.get("reference_point_name") or "").strip()
            component = str(term.get("component") or "")
            step_name = term.get("step_name")
            if (
                reference_point not in reference_points
                or not isinstance(step_name, str)
                or step_name not in steps.step_values
                or component not in component_indices
            ):
                # Metrics are optional. Ignore incomplete selections while the
                # user is still configuring the objective editor.
                continue
            functions.extend(
                [
                    f"def {function_name}() -> Any:",
                    f"    self.set_step({step_name!r})",
                    "    assembly = self.fe.assembly",
                    "    state = assembly._GC2RGC(",
                    f"        self.fe_results[{step_name!r}].GC.to(assembly.device)",
                    "    )",
                    f"    reference_point = assembly.get_reference_point({reference_point!r})",
                    "    return state[reference_point._RGC_index].reshape(-1)["
                    f"{component_indices[component]}]",
                ]
            )
        elif metric_type == CONSTANT.UI.METRIC.TYPE_CUSTOM:
            body = str(term.get("body") or "").strip()
            if not body:
                raise ValueError(
                    localized_message("ui.errors.generator.metric_term_needs_code")
                )
            try:
                ast.parse("def _metric_term():\n" + indent_block(body, 4) + "\n")
            except SyntaxError as exc:
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.metric_term_has_invalid_code_value",
                        value_0=exc,
                    )
                ) from exc
            functions.extend(
                [
                    f"def {function_name}() -> Any:",
                    indent_block(body, 4),
                ]
            )
        else:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.metric_has_unknown_term_type_value",
                    value_0=metric_type,
                )
            )
        value_name = f"metric_value_{index + 1}"
        values.extend(
            [
                f"{value_name} = {function_name}()",
                f"if isinstance({value_name}, (list, tuple)):",
                f"    metrics.extend({value_name})",
                "else:",
                f"    metrics.append({value_name})",
            ]
        )

    return "\n".join(
        [
            *functions,
            "metrics = []",
            *values,
            "return metrics",
        ]
    )


def generate_base_source(
    problem: ProblemDefinition,
    *,
    for_class_catalog: bool = False,
    asset_paths: dict[int, str] | None = None,
) -> str:
    """Return the full source of a runnable problem module (always headless).

    Code-launched runs never open an observer window; results are watched by
    the MorphOpt UI's in-window observer (disk polling per iteration).
    ``for_class_catalog`` emits inert objective methods and updater classes so
    editor class discovery also works while terms are still being defined.
    """
    if asset_paths is None:
        asset_paths, _ = collect_python_assets(problem)
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
        f"            path_result_folder={problem.result_folder!r}, opt_label={problem.label!r}"
    )
    a("        )")
    a("")

    # -------- ObjectiveFunction ------------------------------------------
    objective = problem.objective or ObjectiveNode()
    jac = list(
        dict.fromkeys(
            [item.name for item in objective.jacobian_needed]
            + [
                name
                for term in objective.objective_terms
                if term.get("type") == CONSTANT.UI.OBJECTIVE.TYPE_WORKSPACE
                for entry in term.get("inputs", [])
                for name, _component in entry["parameters"]
            ]
        )
    )
    if for_class_catalog:
        obj_body = "return 0.0"
        met_body = "return []"
    else:
        obj_body = _objective_function_body(objective, problem)
        met_body = _metrics_function_body(objective, problem)

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
    local_classes = _emit_part_classes(a, problem, asset_paths=asset_paths)
    a("")
    a("            def define_interface(self) -> None:")
    _emit_part_init(a, problem, local_classes, asset_paths=asset_paths)
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
    process_devices = list(solver.process_devices)
    tasklist = list(solver.task_step_list)
    args = [
        "params=params",
        f"num_process={np_}",
        f"process_devices={process_devices!r}",
    ]
    if tasklist:
        args.append(f"task_step_list={tasklist!r}")
    a("")
    a("            super().__init__(" + ", ".join(args) + ")")
    a("")

    # -------- Updater -----------------------------------------------------
    _emit_updater(a, problem, template, upd_device, for_class_catalog=for_class_catalog)

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
_REQUIRED_GEOMETRY_FIELDS = {"mesh_file"}


def _render_part_constructor(
    part: PartNode,
    class_name: str | None = None,
    problem: ProblemDefinition | None = None,
    *,
    asset_paths: dict[int, str] | None = None,
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
        expression = (
            _asset_path_expression(asset_paths[id(part)])
            if key == "mesh_file" and value
            else _render_value(value if value is not None else "", problem)
        )
        kwargs.append(f"{key}={expression}")
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
    *,
    asset_paths: dict[int, str] | None = None,
) -> dict[str, str]:
    """Emit local Part subclasses carrying surfaces and Instances.

    Every Part gets a local subclass so its ``define_instance`` method can
    declare the UI's complete placement list. Boundary Parts additionally
    declare their surfaces, local symmetry constraints and optional custom
    ``apply_surface_constraints`` hook.
    Returns the mapping from Part-definition names to emitted class names.
    """
    class_names = part_class_names(problem)

    for part in problem.parts():
        base = f"morphopt.{part.backend_class}"
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
                    f"{render_surface_call(surface, problem, asset_paths=asset_paths)}"
                )
                if surface.type == "brep_surface" and surface.design_faces:
                    a(
                        f"                    surface_{index}.select_design_faces({list(surface.design_faces)!r})"
                    )
                a(
                    f"                    surface_{index}.is_updatable = {surface.is_updatable!r}"
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
                    f"{render_cad_operation_call(operation, problem, asset_paths=asset_paths)})"
                )

        a("")
        a("                def define_instance(self) -> None:")
        instances = part.instances
        if not instances:
            a("                    pass")
        for instance in instances:
            a("")
            pose = (
                f"[*{_render_value(instance.translation, problem)}, "
                f"*{_render_value(instance.rotation, problem)}]"
                if isinstance(instance.translation, str)
                or isinstance(instance.rotation, str)
                else repr(instance.pose)
            )
            a(
                "                    self.add_instance("
                f"{part.assembly_name!r}, "
                f"{instance.name!r}, "
                f"{pose})"
            )
    return class_names


def _emit_part_init(
    a: Callable[[str], object],
    problem: ProblemDefinition,
    local_classes: dict[str, str],
    *,
    asset_paths: dict[int, str] | None = None,
) -> None:
    """Emit initial-geometry Part registration for the model."""
    parts = problem.parts()
    if not parts:
        a("                pass")
        return

    prefix = " " * 16
    for index, part in enumerate(parts):
        label = part.type
        variable = f"part_{index}"
        name = part.name or part.assembly_name or f"part{index + 1}"
        constructor = _render_part_constructor(
            part, local_classes[part.name], problem, asset_paths=asset_paths
        ).replace("\n", "\n" + prefix)

        a("")
        a(f"                # {label}")
        a(f"                {variable} = {constructor}")
        a(f"                self.add_interface({variable}, name={name!r})")


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
            raise ValueError(
                localized_message(
                    "ui.errors.generator.invalid_geometry_symmetry_constraint_value",
                    value_0=item,
                )
            )
        item_type = item.get("type")
        spec = SURFACE_SYMMETRY_CONSTRAINTS.get(item_type)
        if spec is None:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.unknown_geometry_symmetry_constraint_value",
                    value_0=item_type,
                )
            )
        params = item.get("params") or {}
        if item_type == "Custom":
            custom_bodies.append(str(params.get("code") or ""))
            continue

        surface_index = item.get("surface_index")
        if not isinstance(surface_index, int) or not 0 <= surface_index < len(surfaces):
            raise ValueError(
                localized_message(
                    "ui.errors.generator.geometry_symmetry_constraint_value_on_part_value_references_invalid_surface",
                    value_0=item_type,
                    value_1=part.name,
                    value_2=surface_index,
                )
            )
        surface = surfaces[surface_index]
        surface_factory = surface_factory_for_type(surface.surface_type)
        if surface_factory != spec.factory:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.geometry_symmetry_constraint_value_requires_a_value_surface_surface_value",
                    value_0=item_type,
                    value_1=spec.factory,
                    value_2=surface_index,
                    value_3=part.name,
                    value_4=surface.surface_type,
                )
            )

        method_args = []
        if spec.related_surface:
            related_index = item.get("related_surface_index")
            if not isinstance(related_index, int) or not 0 <= related_index < len(
                surfaces
            ):
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.geometry_symmetry_constraint_value_on_part_value_references_invalid_related",
                        value_0=item_type,
                        value_1=part.name,
                        value_2=related_index,
                    )
                )
            related = surfaces[related_index]
            related_factory = surface_factory_for_type(related.surface_type)
            if related_factory != spec.factory:
                raise ValueError(
                    localized_message(
                        "ui.errors.generator.geometry_symmetry_constraint_value_requires_both_surfaces_to_use_value",
                        value_0=item_type,
                        value_1=spec.factory,
                    )
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
    steps = problem.steps
    values = steps.step_values if steps is not None else {"load_case_1": {}}
    if not values:
        a("                pass")
    for name, amplitudes in values.items():
        a(f"                self.add_step({name!r})")
        for component in problem.amplitude_components():
            stored = amplitudes.get(component, [0.0] * component.num_values)
            a(
                f"                self.set_step_params({name!r}, {component.name!r}, "
                f"{_render_value(stored, problem)})"
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
            localized_message(
                "ui.errors.generator.a_geometry_optimizer_needs_a_boundary_part_inp_torchfea"
            )
        )
    targets: list[str] = []
    for index, cfg in enumerate(geom_cfgs):
        target = problem.config_part_node(cfg)
        if target is None:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.geometry_optimizer_value_has_no_target_boundary_part_choose_one",
                    value_0=index + 1,
                    value_1=[node.name for node in boundary],
                )
            )
        name = target.name
        if name in targets:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.two_geometry_optimizers_both_target_value_give_each_one_its",
                    value_0=name,
                )
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
            localized_message(
                "ui.errors.generator.a_material_optimizer_needs_a_design_carrying_material_simp"
            )
        )
    targets: list[str] = []
    for index, cfg in enumerate(mat_cfgs):
        target = problem.config_material_node(cfg)
        if target is None or target not in design:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.material_optimizer_value_has_no_target_design_material_choose_one",
                    value_0=index + 1,
                    value_1=[material.name for material in design],
                )
            )
        name = target.name
        if name in targets:
            raise ValueError(
                localized_message(
                    "ui.errors.generator.two_material_optimizers_both_target_value_give_each_one_its",
                    value_0=name,
                )
            )
        targets.append(name)
    return targets


def _emit_updater(
    a: Callable[[str], object],
    problem: ProblemDefinition,
    template: SchemeTemplate,
    device: str,
    *,
    for_class_catalog: bool = False,
) -> None:
    from .custom_classes import updater_class_name

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
        updater_class_name("geometry", index) for index in range(len(geom_cfgs))
    ]
    material_classes = [
        updater_class_name("materials", index) for index in range(len(mat_cfgs))
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
        _emit_nested_updater(
            a, class_name, base, config, problem, for_class_catalog=for_class_catalog
        )
        a("")
    for class_name, config in zip(material_classes, mat_cfgs):
        _emit_nested_updater(
            a,
            class_name,
            MATERIAL_UPDATER_BASE,
            config,
            problem,
            for_class_catalog=for_class_catalog,
        )
        a("")


def _render_updater_item(
    item: dict, category: str, problem: ProblemDefinition | None = None
) -> str:
    """Render one valid structured objective/constraint item into source."""
    if not isinstance(item, dict):
        raise ValueError(
            localized_message(
                "ui.errors.generator.invalid_updater_item_value", value_0=item
            )
        )
    if item.get("type") == "Custom" and item.get("custom_class"):
        return f"{item['custom_class']}()"
    cat = UPDATER_CATALOG.get(category, {})
    spec = cat.get(item.get("type", ""))
    if spec is None:
        raise ValueError(
            localized_message(
                "ui.errors.generator.unknown_updater_value_type_value",
                value_0=category,
                value_1=item.get("type"),
            )
        )
    gen = spec.gen
    if not gen:
        raise ValueError(
            localized_message(
                "ui.errors.generator.missing_generator_for_updater_item_value",
                value_0=item["type"],
            )
        )
    if item.get("custom_class"):
        gen = item["custom_class"] + gen[gen.index("(") :]
    params = dict(item.get("params") or {})
    for f in spec.fields:
        params.setdefault(f.key, f.new_default())
    if (
        item.get("type") == "VolFrac"
        and not str(params.get("elementname") or "").strip()
    ):
        raise ValueError(
            localized_message(
                "ui.errors.generator.volfrac_requires_an_explicit_elems_name"
            )
        )
    fmt = {k: _render_value(v, problem) for k, v in params.items()}
    try:
        return gen.format(**fmt)
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(
            localized_message(
                "ui.errors.generator.invalid_updater_parameters_value",
                value_0=item["type"],
            )
        ) from exc


def _emit_nested_updater(
    a: Callable[[str], object],
    cls_name: str,
    base: str,
    cfg,
    problem: ProblemDefinition,
    *,
    for_class_catalog: bool = False,
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
        raise ValueError(
            localized_message(
                "ui.errors.generator.raw_updater_code_is_unsupported_use_method_overrides"
            )
        )
    a(f"        class {cls_name}({base}):")
    a("")
    a("            def __init__(self) -> None:")
    defaults = (
        CONSTANT.KERNEL.SIMP_UPDATE
        if base == MATERIAL_UPDATER_BASE
        else CONSTANT.KERNEL.SHAPE_UPDATE
    )
    a(
        f"                super().__init__(max_step_iter={_render_value(cfg.get('max_step_iter', 50), problem)}, "
        f"max_step_length={_render_value(cfg.get('max_step_length', defaults.MAX_STEP_LENGTH), problem)})"
    )

    if for_class_catalog:
        a("")
        a("            def define_objective(self) -> None:")
        a("                pass")
        return

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

    if base == MATERIAL_UPDATER_BASE and cfg.get("if_update") is not None:
        body.append(f"self.if_update = {cfg['if_update']!r}")

    if not body:
        return
    a("")
    a("            def define_objective(self) -> None:")
    for line in body:
        a(indent_block(line, 16))
