"""Render a :class:`~morphopt.ui.model.problem.ProblemDefinition` into the
source of a standard morphopt problem module (a top-level ``ThisController``
class), ready for ``morphopt.start_optimization`` / ``restart_optimization``.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import fields

from ...optcore.modelparams.materialinterface import MaterialModels
from ..model.modelinfo import PartSummary, TorchFEAModelSummary
from ..model.problem import (
    INSTANCE_REFERENCE_FIELDS,
    InterfaceNode,
    Node,
    ObjectiveNode,
    PartInterfaceNode,
    ProblemDefinition,
    SolverNode,
    StepsNode,
    TEMPLATE_MODEL_DIRECTORY,
    UpdaterNode,
)
from ..model.schemas import (
    INTERFACE_TYPES,
    PART_INTERFACE_TYPES,
    SURFACE_TYPES,
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

BOUNDARY_PART_BASE = "morphopt.BoundaryPartInterface"
GEOMETRY_UPDATER_BASE = "morphopt.UpdaterBoundaryPart"
MATERIAL_UPDATER_BASE = "morphopt.UpdaterSIMPMaterial"
HOMOGENEOUS_MATERIAL_BASE = "morphopt.HomogeneousMaterial"
SIMP_MATERIAL_BASE = "morphopt.SIMP_BSPFieldMaterials"

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _literal(value: object) -> str:
    """Turn a stored field value into valid Python source.

    Strings that *look* like numbers / lists (common when a text field is
    used instead of a typed widget) are normalised with ``ast.literal_eval``.
    """
    if isinstance(value, str):
        try:
            return repr(ast.literal_eval(value))
        except (ValueError, SyntaxError):
            return repr(value)
    return repr(value)


def _material_parameters_expression(
    model: str,
    parameters: dict[str, object],
) -> str:
    """Render model parameters with their typed parameter constructor."""
    parameter_class = getattr(MaterialModels, f"{model}Params")
    parameter_type = parameter_class.__name__
    values = ", ".join(f"{key}={_literal(value)}" for key, value in parameters.items())
    return f"self.materialmodels.{parameter_type}({values})"


def indent_block(text: str, spaces: int) -> str:
    """Indent every non-empty line of ``text`` by ``spaces``."""
    pad = " " * spaces
    return "\n".join(pad + ln if ln.strip() else ln for ln in text.splitlines())


# --------------------------------------------------------------------------
# surface / interface / keyword rendering
# --------------------------------------------------------------------------


def _surface_factory(surface: Node) -> str:
    return SURFACE_TYPES[surface.surface_type]["factory"]


def render_surface_call(surface: Node) -> str:
    factory = _surface_factory(surface)
    if factory is None:  # fixed_stl
        return "self.FixedSurface.initialize_from_stl_file(%s)" % _literal(
            surface.path_stl or ""
        )
    kwargs = []
    for field in SURFACE_TYPES[surface.surface_type]["params"]:
        key = field["key"]
        value = surface.get_field(key)
        if value is None:
            continue
        kwargs.append(f"{key}={_literal(value)}")
    kwargs.append(f"flip={_literal(surface.flip)}")
    return f"self.{factory}({', '.join(kwargs)})"


def render_interface_call(interface: Node) -> str:
    cls = f"{interface.interface_type}Interface"
    kwargs = []
    for field in INTERFACE_TYPES[interface.interface_type]["params"]:
        key = field["key"]
        value = interface.get_field(key)
        if value is None:
            continue
        kwargs.append(f"{key}={_literal(value)}")
    return f"self.{cls}({', '.join(kwargs)})"


# --------------------------------------------------------------------------
# main generator
# --------------------------------------------------------------------------


def generate_source(problem: ProblemDefinition) -> str:
    """Return the full source of a runnable problem module (always headless).

    Code-launched runs never open an observer window; results are watched by
    the MorphOpt UI's in-window observer (disk polling per iteration).
    """
    problem.resolve_references()
    template = get_template(problem.scheme)
    L: list[str] = []
    a = L.append

    controller_ref = CORE_BASES["controller"]
    run_dev = problem.device or "cpu"
    upd_dev = problem.updater_device or run_dev
    device = repr(run_dev)  # -> morphopt.start_optimization(device=...)
    upd_device = repr(upd_dev)  # -> Updater(..., device=...) (independent)

    a("import os")
    a("import morphopt")
    a("from typing import Any")
    a("")
    a("")
    a(f"class ThisController({controller_ref}):")
    a("")
    a("    def __init__(self) -> None:")
    a("        super().__init__(")
    a(
        f"            path_result_folder={_literal(problem.result_folder)}, opt_label={_literal(problem.label)}"
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
    _emit_interfaces(a, problem)
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
    np_ = int(solver.num_process)
    gpus = list(solver.gpus)
    tasklist = list(solver.task_index_list)
    args = ["params=params", f"num_process={np_}"]
    if gpus:
        args.append(f"available_gpus={gpus!r}")
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

#: geometry-interface fields that must always be emitted, even when empty
#: (they are positional requirements of the interface constructor)
_REQUIRED_GEOMETRY_FIELDS = {"model_directory", "mesh_file"}


def _render_part_constructor(
    interface: PartInterfaceNode, class_name: str | None = None
) -> str:
    """Render ``self.<ClassName>(...)`` for one part interface.

    ``class_name`` overrides the schema type name, used when the model emits a
    local subclass (the boundary part that carries the equality constraints).
    """
    type_name = class_name or interface.interface_type
    spec = PART_INTERFACE_TYPES.get(interface.interface_type, {})
    kwargs = []
    for field in spec.get("params", []):
        key = field["key"]
        value = interface.get_field(key)
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
            kwargs.append(f"{key}={_literal(value if value is not None else '')}")
    if not kwargs:
        return f"self.{type_name}()"
    inner = ",\n".join("    " + option for option in kwargs)
    return f"self.{type_name}(\n{inner},\n)"


def _emit_part_classes(
    a: Callable[[str], object],
    problem: ProblemDefinition,
) -> dict[str, str]:
    """Emit local Part subclasses carrying surfaces and Instances.

    Every Part gets a local subclass so its ``define_instance`` method can
    declare the UI's complete placement list. Boundary Parts additionally
    declare their surfaces and optional equality constraints.
    Returns the mapping interface name -> emitted class name.
    """
    fixed_bases = {
        "INPPartInterface": "morphopt.INPPartInterface",
        "TorchFEAPartInterface": "morphopt.TorchFEAPartInterface",
    }
    local_class: dict[str, str] = {}

    constraints = _surface_constraints_bodies(problem)
    for index, interface in enumerate(problem.part_interfaces()):
        base = BOUNDARY_PART_BASE if interface.has_surfaces else fixed_bases.get(
            interface.interface_type
        )
        if not base:
            continue
        class_name = (
            f"BoundaryPart{index}" if interface.has_surfaces else f"PartInterface{index}"
        )
        surfaces = interface.surfaces()
        a("")
        a(f"            class {class_name}({base}):")
        a("")
        if interface.has_surfaces:
            a("                def define_surfaces(self) -> None:")
            if not surfaces:
                a("                    pass")
            for surface in surfaces:
                a(
                    "                    self.add_surface_interface("
                    f"{render_surface_call(surface)})"
                )
            code = constraints.get(interface.name)
            if code:
                a("")
                a("                def apply_surface_constraints(self) -> None:")
                a(indent_block(code, 20))

        a("")
        a("                def define_instance(self) -> None:")
        instances = interface.instances()
        if not instances:
            a("                    super().define_instance()")
        for instance in instances:
            a("")
            a(
                "                    self.add_instance("
                f"{interface.resolved_part_name()!r}, "
                f"{instance.name!r}, "
                f"{instance.pose!r})"
            )
        local_class[interface.name] = class_name
    return local_class


def _emit_part_init(
    a: Callable[[str], object],
    problem: ProblemDefinition,
    local_classes: dict[str, str] | None = None,
) -> None:
    """Emit the ``GeometryParams.define_interface`` body of the model."""
    parts = problem.part_interfaces()
    if not parts:
        a("                pass")
        return

    model = problem.imported_model_summary()
    if model is not None:
        _validate_imported_interface_selections(problem, model)

    local_class = dict(local_classes or {})
    prefix = " " * 16
    for index, interface in enumerate(parts):
        spec = PART_INTERFACE_TYPES.get(interface.interface_type, {})
        label = spec.get("label_en") or interface.interface_type
        variable = f"part_{index}"
        name = interface.name or interface.resolved_part_name() or f"part{index + 1}"
        constructor = _render_part_constructor(
            interface, local_class.get(interface.name)
        ).replace("\n", "\n" + prefix)

        a("")
        a(f"                # {label}")
        a(f"                {variable} = {constructor}")
        if interface.name not in local_class:
            # a boundary part declares its surfaces in its own class
            for surface in interface.surfaces():
                a(
                    f"                {variable}.add_surface_interface("
                    f"{render_surface_call(surface)})"
                )
        a(f"                self.add_interface({variable}, name={name!r})")


def _validate_imported_interface_selections(
    problem: ProblemDefinition,
    model: TorchFEAModelSummary,
) -> None:
    """Validate all Assembly-backed names before emitting runnable source."""
    instances = {item.name: item for item in model.instances}
    parts = {item.name: item for item in model.parts}
    for interface in problem.interfaces():
        spec = INTERFACE_TYPES.get(interface.interface_type, {})
        fields_for_type = {field["key"] for field in spec.get("params", [])}
        boundary_instance = False
        for instance_key in ("instance_name", "instance_name1", "instance_name2"):
            if instance_key not in fields_for_type:
                continue
            target = getattr(interface, INSTANCE_REFERENCE_FIELDS[instance_key])
            if target is None:
                raise ValueError(
                    f"Interface {interface.name!r} must select {instance_key}."
                )
            selected = target.name
            if selected not in instances:
                owner = problem.part_interface_for_instance(selected)
                if owner is not None and owner.has_surfaces:
                    # Boundary Parts create their node/surface sets while
                    # generating the Part.  They are not present in the
                    # imported TorchFEA archive being validated here.
                    boundary_instance = True
                    continue
                raise ValueError(
                    f"Interface {interface.name!r} references unknown TorchFEA "
                    f"Instance {selected!r}."
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
            selected = str(interface.get_field(key, "") or "").strip()
            target = getattr(interface, INSTANCE_REFERENCE_FIELDS[instance_key])
            instance_name = target.name if target is not None else ""
            if not selected:
                raise ValueError(f"Interface {interface.name!r} must select {key}.")
            instance = instances.get(instance_name)
            part = parts.get(instance.part_name) if instance is not None else None
            available = sets_of(part) if part is not None else ()
            if selected not in available:
                raise ValueError(
                    f"Interface {interface.name!r} references unknown {key} "
                    f"{selected!r} on Instance {instance_name!r}."
                )

        if "element_name" in fields_for_type:
            element_name = str(interface.element_name or "").strip()
            instance_name = interface.instance.name if interface.instance else ""
            instance = instances.get(instance_name)
            part = parts.get(instance.part_name) if instance is not None else None
            if part is None or element_name not in part.element_types:
                raise ValueError(
                    f"Interface {interface.name!r} references unknown element "
                    f"{element_name!r} on Instance {instance_name!r}."
                )


def _surface_constraints_bodies(problem: ProblemDefinition) -> dict[str, str]:
    """Equality-constraint body per boundary part (only non-empty bodies).

    Every geometry sub-optimizer owns one Part, so its equality code is emitted
    on the Part subclass it constrains.
    """
    updater = problem.updater
    configs = updater.geometry if updater is not None else []
    bodies: dict[str, str] = {}

    for config in configs:
        node = problem.config_part_node(config)
        if node is None:
            continue
        body = _constraint_body_of(config)
        if body:
            bodies[node.name] = body

    return bodies


def _constraint_body_of(config: dict) -> str:
    """Equality-constraint body of one geometry sub-optimizer config."""
    # Equality constraints are kept separate from penalty constraints in the
    # model tree.
    equality_items = config.get("equality_constraints")
    equality_bodies = []
    for item in equality_items or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"MirrorSymmetry", "SurfaceEquality"}:
            continue
        equality_bodies.append((item.get("params") or {}).get("code", ""))
    return _clean_body("\n\n".join(equality_bodies))


def _clean_body(code: str) -> str:
    body = str(code or "").strip()
    return "" if not body or body == "pass" else body


def _emit_interfaces(a: Callable[[str], object], problem: ProblemDefinition) -> None:
    interfaces = [it for it in problem.interfaces() if it.interface_type]
    if not interfaces:
        a("                pass")
        return
    for it in interfaces:
        a(
            f"                self.add_interface({render_interface_call(it)}, name={it.name!r})"
        )


def _emit_steps(a: Callable[[str], object], problem: ProblemDefinition) -> None:
    steps = problem.steps or StepsNode(
        name="Load steps", params={"num_steps": 1, "step_values": [{}]}
    )
    n = int(steps.num_steps)

    values = list(steps.step_values) or [{} for _ in range(n)]
    while len(values) < n:
        values.append({})

    # every amplitude-bearing load interface must be set for every step, so a
    # load that was added but left unset in a step is written explicitly as a
    # zero amplitude (matching the step-matrix UI, where an empty cell is 0).
    amps: dict[InterfaceNode, int] = {}
    for it in problem.interfaces():
        nv = INTERFACE_TYPES.get(it.interface_type, {}).get("num_values", 0)
        if nv and it.name:
            amps[it] = nv

    a(f"                self.set_step_num({n})")
    for s in range(n):
        step_dict = (values[s] if s < len(values) else {}) or {}
        for interface, nv in amps.items():
            stored = step_dict.get(interface)
            amps_values = stored if stored is not None else [0.0] * nv
            a(
                f"                self.set_step_params({s}, {interface.name!r}, "
                f"{amps_values!r})"
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

        interface_class = base
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
                + _material_parameters_expression(model, material_parameters)
            )
        else:
            keys = ["part_name", "elementname", "density"]
            material_parameters = {key: mat.get_field(key) for key in model_keys}
            kw.append(
                "material_parameters="
                + _material_parameters_expression(model, material_parameters)
            )
        for key in keys:
            value = mat.get_field(key)
            if value is not None:
                kw.append(f"{key}={_literal(value)}")

        a("")
        name = mat.name or f"material_{index}"
        a(f"                self.add_interface({interface_class}(")
        for option in kw:
            a(f"                    {option},")
        a(f"                ), name={name!r})")


def _resolve_geometry_targets(
    problem: ProblemDefinition, geom_cfgs: list[dict]
) -> list[str]:
    """Validate the Part every geometry sub-updater is bound to.

    Only boundary part interfaces carry surfaces, so an updater must target one
    of those Part objects.
    """
    if not geom_cfgs:
        return []
    boundary = problem.boundary_part_nodes()
    if not boundary:
        raise ValueError(
            "A geometry optimizer needs a boundary part interface; INP / TorchFEA "
            "parts have no design surfaces."
        )
    targets: list[str] = []
    for index, cfg in enumerate(geom_cfgs):
        target = problem.config_part_node(cfg)
        if target is None:
            raise ValueError(
                f"Geometry optimizer {index + 1} has no target boundary Part; choose "
                f"one of {[node.name for node in boundary]}."
            )
        name = target.name
        if name in targets:
            raise ValueError(
                f"Two geometry optimizers both target {name!r}; give each one its "
                "own Part."
            )
        targets.append(name)
    return targets


def _resolve_material_targets(
    problem: ProblemDefinition, mat_cfgs: list[dict]
) -> list[str]:
    """Validate the material interface every material sub-updater is bound to.

    Only design-carrying material interfaces (SIMP density fields) have
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
            "A material optimizer needs a design-carrying material interface "
            "(SIMP density field); homogeneous materials have no variables."
        )
    targets: list[str] = []
    for index, cfg in enumerate(mat_cfgs):
        target = problem.config_material_node(cfg)
        if target is None or target not in design:
            raise ValueError(
                f"Material optimizer {index + 1} has no target design material; "
                f"choose one of {[material.name for material in design]}."
            )
        name = target.name
        if name in targets:
            raise ValueError(
                f"Two material optimizers both target {name!r}; give each one its "
                "own interface."
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
        _emit_nested_updater(a, class_name, GEOMETRY_UPDATER_BASE, config)
        a("")
    for class_name, config in zip(material_classes, mat_cfgs):
        _emit_nested_updater(a, class_name, MATERIAL_UPDATER_BASE, config)
        a("")


def _render_updater_item(item: dict, category: str) -> str | None:
    """Render one structured objective/constraint item into source (or None)."""
    if not isinstance(item, dict):
        return None
    cat = UPDATER_CATALOG.get(category, {})
    spec = cat.get(item.get("type", ""))
    if spec is None:
        return None
    gen = spec.get("gen", "")
    if not gen:
        return None
    params = dict(item.get("params") or {})
    for f in spec.get("params", []):
        params.setdefault(f["key"], f["default"])
    if (
        item.get("type") == "VolFrac"
        and not str(params.get("elementname") or "").strip()
    ):
        raise ValueError("VolFrac requires an explicit elems name.")
    fmt = {k: _literal(v) for k, v in params.items()}
    try:
        return gen.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return None


def _emit_nested_updater(a: Callable[[str], object], cls_name: str, base: str, cfg) -> None:
    """Emit one sub-updater class.

    The class is **target-free** -- it carries the objectives / constraints of
    one sub-optimizer and nothing else.  Which Part / material interface it
    optimizes is stated by the ``name`` of the ``add_*_updater(...)`` call that
    registers it, so the same class can be registered several times for
    different targets.  Objectives are declared in ``define_objective()`` and
    registered once when the updater is added, mirroring ``define_interface()``
    of the params collections.  The hook must not access the bound target.
    """
    cfg = cfg or {}
    a(f"        class {cls_name}({base}):")
    a("")
    a("            def __init__(self) -> None:")
    a(f"                super().__init__(max_step_iter={int(cfg.get('max_step_iter', 50))})")

    body: list[str] = []
    # NOTE: the model stores the lists under ``objective_functions`` / ``constraints``
    # while the catalogue (UPDATER_CATALOG) is keyed ``objectives`` / ``constraints``.
    for model_key, catalog_key, call in (
        ("objective_functions", "objectives", "add_objective_function"),
        ("constraints", "constraints", "add_constraints"),
    ):
        for item in cfg.get(model_key, []) or []:
            line = _render_updater_item(item, catalog_key)
            if line is None:
                continue
            body.append(f"self.{call}({line})")

    # raw-code fallback / escape hatch (kept for imported job scripts)
    code = (cfg.get("code") or "").strip()
    if code:
        body.append(code)

    if "if_update" in cfg and cfg["if_update"] is not None:
        body.append(f"self.if_update = {cfg['if_update']!r}")

    if not body:
        return
    a("")
    a("            def define_objective(self) -> None:")
    for line in body:
        a(indent_block(line, 16))
