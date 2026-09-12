"""Render a :class:`~morphopt.ui.model.problem.ProblemDefinition` into the
source of a standard morphopt problem module (a top-level ``ThisController``
class), ready for ``morphopt.start_optimization`` / ``restart_optimization``.
"""

from __future__ import annotations

import ast

from ..model.problem import (
    Node, ProblemDefinition,
    GeometryNode, StepsNode, MaterialNode, ObjectiveNode, SolverNode,
    UpdaterNode,
)
from ..model.schemas import (
    SURFACE_TYPES, INTERFACE_TYPES, UPDATER_CATALOG,
)
from ..schemes.base import get_template
from ...optcore.modelparams.geometry import inspect_model


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _literal(value):
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
            surface.path_stl or "")
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


def _drop_empty(items):
    return [it for it in items if it]


# --------------------------------------------------------------------------
# main generator
# --------------------------------------------------------------------------

def generate_source(problem: ProblemDefinition) -> str:
    """Return the full source of a runnable problem module (always headless).

    Code-launched runs never open an observer window; results are watched by
    the MorphOpt UI's in-window observer (disk polling per iteration).
    """
    template = get_template(problem.scheme)
    B = template.BASES
    L: list[str] = []
    a = L.append

    controller_ref = B["controller"]  # morphopt.Controller
    run_dev = problem.device or "cpu"
    upd_dev = problem.updater_device or run_dev
    device = repr(run_dev)      # -> morphopt.start_optimization(device=...)
    upd_device = repr(upd_dev)  # -> Updater(..., device=...) (independent)

    a("import morphopt")
    a("")
    a("")
    a(f"class ThisController({controller_ref}):")
    a("")
    a("    def __init__(self):")
    a("        super().__init__(")
    a(f"            path_result_folder={_literal(problem.result_folder)}, opt_label={_literal(problem.label)}")
    a("        )")
    a("")

    # -------- ObjectiveFunction ------------------------------------------
    objective = problem.objective or ObjectiveNode()
    jac = list(objective.jacobian_needed)
    obj_body = objective._objective_function or template.default_objective_slot()
    met_body = objective._get_metrics or template.default_metrics_slot()

    a(f"    class ObjectiveFunction({B['objective']}):")
    a("")
    a("        def __init__(self):")
    a("            super().__init__()")
    if jac:
        a(f"            self.jacobian_needed = {jac!r}")
    a("")
    a("        def objective_function(self):")
    a(indent_block(obj_body, 12))
    a("")
    a("        def get_metrics(self):")
    a(indent_block(met_body, 12))
    a("")

    # -------- Params ------------------------------------------------------
    a(f"    class Params({B['params']}):")
    a("")
    a(f"        class GeometryParams({B['geometry']}):")
    a("")
    a("            def __init__(self):")
    _emit_geometry_init(a, problem, template)
    a("")
    if problem.scheme == "simp":
        # fixed mesh -> no re-mesh, nothing more to generate for geometry
        pass
    else:
        _emit_apply_constraints(a, problem, template)
    a("")
    a(f"        class FEAParams({B['fea']}):")
    a("")
    a("            def __init__(self):")
    a("                super().__init__()")
    a("")
    a("            def define_interface(self):")
    _emit_interfaces(a, problem)
    a("")
    a("            def define_steps(self):")
    _emit_steps(a, problem)
    a("")
    a(f"        class MaterialParams({B['material']}):")
    a("")
    a("            def __init__(self):")
    _emit_material_init(a, problem, template)
    if problem.scheme in ("simp", "codesign"):
        _emit_map_designfield(a, problem, template)
    a("")
    a("        def __init__(self):")
    a("            super().__init__(")
    a("                surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams()")
    a("            )")
    a("")

    # -------- Solver ------------------------------------------------------
    a(f"    class Solver({B['solver']}):")
    a("")
    a("        def __init__(self, params):")
    solver = problem.solver or SolverNode()
    np_ = int(solver.num_process)
    gpus = list(solver.gpus)
    tasklist = list(solver.task_index_list)
    args = [f"params=params", f"num_process={np_}"]
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
    a(f"    morphopt.start_optimization(device={device}, restart_per_iteration={problem.restart_per_iteration})")

    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# per-section emitters
# --------------------------------------------------------------------------

def _geometry_kwargs(problem: ProblemDefinition) -> str:
    geo = problem.geometry or GeometryNode()
    geo_fields = ("fea_seed_size", "mesh_order", "reinitialize_per_iter",
                  "thickness", "num_layers")
    kw = []
    for key in geo_fields:
        value = geo.get_field(key)
        if value is not None:
            kw.append(f"{key}={_literal(value)}")
    return ", ".join(kw)


def _emit_geometry_init(a, problem: ProblemDefinition, template) -> None:
    surfaces = problem.surfaces()
    if problem.scheme == "simp":
        geo = problem.geometry or GeometryNode()
        if geo.model_directory and geo.model_filename:
            model = inspect_model(geo.model_directory, geo.model_filename)
            _validate_simp_interface_selections(problem, model)
            material = problem.material
            if material is not None:
                parts = {item.name: item for item in model.parts}
                part_name = str(material.part_name or "").strip()
                if part_name not in parts:
                    raise ValueError("Select an imported Part for the SIMP material.")
                if material.elementname not in parts[part_name].element_types:
                    raise ValueError(
                        f"Element {material.elementname!r} does not exist on imported "
                        f"Part {part_name!r}.")
        a("                super().__init__(")
        a(f"                    model_directory={_literal(geo.model_directory)},")
        a(f"                    model_filename={_literal(geo.model_filename)},")
        a("                )")
        return
    kw = _geometry_kwargs(problem)
    a(f"                super().__init__({kw})" if kw else "                super().__init__()")
    for i, srf in enumerate(surfaces):
        a("")
        a("                # %s (surface index %d)" % (SURFACE_TYPES[srf.surface_type]["label_en"], i))
        a(f"                self.add_surface({render_surface_call(srf)})")


def _validate_simp_interface_selections(problem: ProblemDefinition, model) -> None:
    """Validate all Assembly-backed names before emitting runnable source."""
    instances = {item.name: item for item in model.instances}
    parts = {item.name: item for item in model.parts}
    for interface in problem.interfaces():
        spec = INTERFACE_TYPES.get(interface.interface_type, {})
        fields_for_type = {field["key"] for field in spec.get("params", [])}
        for instance_key in ("instance_name", "instance_name1", "instance_name2"):
            if instance_key not in fields_for_type:
                continue
            selected = str(interface.get_field(instance_key, "") or "").strip()
            if not selected:
                raise ValueError(
                    f"Interface {interface.name!r} must select {instance_key}.")
            if selected not in instances:
                raise ValueError(
                    f"Interface {interface.name!r} references unknown TorchFEA "
                    f"Instance {selected!r}.")

        selections = (
            ("set_nodes_name", "instance_name", "node_sets"),
            ("surface_name", "instance_name", "surface_sets"),
            ("surface_name1", "instance_name1", "surface_sets"),
            ("surface_name2", "instance_name2", "surface_sets"),
        )
        for key, instance_key, set_attribute in selections:
            if key not in fields_for_type:
                continue
            selected = str(interface.get_field(key, "") or "").strip()
            instance_name = str(interface.get_field(instance_key, "") or "").strip()
            if not selected:
                raise ValueError(f"Interface {interface.name!r} must select {key}.")
            instance = instances.get(instance_name)
            part = parts.get(instance.part_name) if instance is not None else None
            available = getattr(part, set_attribute, ()) if part is not None else ()
            if selected not in available:
                raise ValueError(
                    f"Interface {interface.name!r} references unknown {key} "
                    f"{selected!r} on Instance {instance_name!r}.")

        if "element_name" in fields_for_type:
            element_name = str(interface.element_name or "").strip()
            instance = instances.get(str(interface.instance_name or "").strip())
            part = parts.get(instance.part_name) if instance is not None else None
            if part is None or element_name not in part.element_types:
                raise ValueError(
                    f"Interface {interface.name!r} references unknown element "
                    f"{element_name!r} on Instance {interface.instance_name!r}.")


def _emit_apply_constraints(a, problem: ProblemDefinition, template) -> None:
    geo = problem.geometry or GeometryNode()
    updater = problem.updater
    geometry_config = updater.geometry_config() if updater is not None else None
    body = None
    if geometry_config is not None:
        # Equality constraints are kept separate from penalty constraints in
        # the model tree.  Their implementation is still emitted on
        # GeometryParams because that is where the backend invokes
        # ``apply_surface_constraints()`` after every variable update.
        equality_items = geometry_config.get("equality_constraints")
        found_equality = False
        equality_bodies = []
        for item in equality_items or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") not in {"MirrorSymmetry", "SurfaceEquality"}:
                continue
            found_equality = True
            equality_bodies.append((item.get("params") or {}).get("code", ""))

        # Definitions written before equality_constraints was introduced may
        # still contain the item in the penalty list.  Read it once so old
        # files keep generating the same source; the UI migrates it on edit.
        if not found_equality:
            for item in geometry_config.get("constraints", []) or []:
                if (isinstance(item, dict)
                        and item.get("type") in {"MirrorSymmetry", "SurfaceEquality"}):
                    found_equality = True
                    equality_bodies.append(
                        (item.get("params") or {}).get("code", ""))

        if found_equality:
            # The backend exposes one hook, so several UI templates are
            # composed in their tree order into that hook.
            body = "\n\n".join(str(part).strip()
                                  for part in equality_bodies if str(part).strip())

        if not found_equality:
            # Legacy definitions stored this body directly on GeometryNode.
            # Do not inject a template default here: an explicitly empty
            # equality list means the user removed the constraint.
            body = geo._apply_surface_constraints
            if not body and "equality_constraints" not in geometry_config:
                # Very old updater configs had no equality list at all and
                # relied on the scheme template's default hook.
                body = template.default_apply_surface_constraints()
    else:
        body = geo._apply_surface_constraints or template.default_apply_surface_constraints()
    body = str(body).strip()
    if not body or body == "pass":
        return
    a("            def apply_surface_constraints(self):")
    a(indent_block(body, 16))
    a("")


def _emit_interfaces(a, problem: ProblemDefinition) -> None:
    interfaces = [it for it in problem.interfaces() if it.interface_type]
    if not interfaces:
        a("                pass")
        return
    for it in interfaces:
        a(f"                self.add_fea_interface({render_interface_call(it)}, name={it.name!r})")


def _emit_steps(a, problem: ProblemDefinition) -> None:
    steps = problem.steps or StepsNode(name="Load steps",
                                       params={"num_steps": 1, "step_values": [{}]})
    n = int(steps.num_steps)

    values = list(steps.step_values) or [{} for _ in range(n)]
    while len(values) < n:
        values.append({})

    # every amplitude-bearing load interface must be set for every step, so a
    # load that was added but left unset in a step is written explicitly as a
    # zero amplitude (matching the step-matrix UI, where an empty cell is 0).
    amps: dict[str, int] = {}
    for it in problem.interfaces():
        nv = INTERFACE_TYPES.get(it.interface_type, {}).get("num_values", 0)
        if nv and it.name:
            amps[it.name] = nv

    a(f"                self.set_step_num({n})")
    for s in range(n):
        step_dict = (values[s] if s < len(values) else {}) or {}
        for name, nv in amps.items():
            stored = step_dict.get(name)
            amps_values = stored if stored is not None else [0.0] * nv
            a(f"                self.set_step_params({s}, {name!r}, {amps_values!r})")


def _emit_material_init(a, problem: ProblemDefinition, template) -> None:
    mat = problem.material or MaterialNode()
    mtype = mat.material_type or template.BASES["material"].rsplit(".", 1)[-1]
    from ..model import schemas as S
    try:
        spec = S.MATERIAL_TYPES[mtype]
        keys = [f["key"] for f in spec["params"]]
    except KeyError:
        keys = list(mat.field_names())
    kw = []
    for key in keys:
        value = mat.get_field(key)
        if value is None:
            continue
        kw.append(f"{key}={_literal(value)}")
    a(f"                super().__init__({', '.join(kw)})" if kw else "                super().__init__()")


def _emit_map_designfield(a, problem: ProblemDefinition, template) -> None:
    mat = problem.material or MaterialNode()
    body = mat._map_bsp_designfield or template.default_map_bsp_designfield()
    body = str(body).strip()
    if not body or "return nodes" in body:
        return
    a("")
    a("            def _map_bsp_designfield(self, nodes):")
    a(indent_block(body, 16))


def _emit_updater(a, problem: ProblemDefinition, template, device: str) -> None:
    upd = problem.updater or UpdaterNode()
    geom_cfg = upd.geometry_config()
    mat_cfg = upd.materials_config()
    has_geom = bool(geom_cfg)
    has_mat = bool(mat_cfg)
    if not has_geom and not has_mat:
        a(f"    class Updater({template.BASES['updaters']}):")
        a("")
        a("        def __init__(self, params, *args, **kwargs):")
        a("            super().__init__(*args, **kwargs)")
        return

    updater_base = template.BASES["updaters"]
    parts = []
    if has_geom:
        parts.append(f"surfaces=self.UpdaterGeometries(params=params)")
    if has_mat:
        parts.append(f"materials=self.UpdaterMaterials(params=params)")
    a(f"    class Updater({updater_base}):")
    a("")
    a("        def __init__(self, params, *args, **kwargs):")
    a(f"            super().__init__({', '.join(parts)}, device={device}, *args, **kwargs)")
    a("")
    if has_geom:
        _emit_nested_updater(a, "UpdaterGeometries", template.BASES.get("updater_geom"), geom_cfg)
        a("")
    if has_mat:
        _emit_nested_updater(a, "UpdaterMaterials", template.BASES.get("updater_mat"), mat_cfg)


def _render_updater_item(item: dict, category: str):
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
    fmt = {k: _literal(v) for k, v in params.items()}
    try:
        return gen.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return None


def _emit_nested_updater(a, cls_name: str, base: str, cfg) -> None:
    cfg = cfg or {}
    a(f"        class {cls_name}({base}):")
    a("")
    a("            def __init__(self, params):")
    a(f"                super().__init__(params=params, max_step_iter={int(cfg.get('max_step_iter', 50))})")

    # NOTE: the model stores the lists under ``objective_functions`` / ``constraints``
    # while the catalogue (UPDATER_CATALOG) is keyed ``objectives`` / ``constraints``.
    for model_key, catalog_key, call in (
            ("objective_functions", "objectives", "add_objective_function"),
            ("constraints", "constraints", "add_constraints")):
        for item in cfg.get(model_key, []) or []:
            line = _render_updater_item(item, catalog_key)
            if line is None:
                continue
            a(f"                self.{call}({line})")

    # raw-code fallback / escape hatch (kept for imported job scripts)
    code = (cfg.get("code") or "").strip()
    if code:
        a(indent_block(code, 16))

    if "if_update" in cfg and cfg["if_update"] is not None:
        a(f"                self.if_update = {cfg['if_update']!r}")
