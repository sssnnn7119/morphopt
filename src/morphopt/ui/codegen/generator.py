"""Render a :class:`~morphopt.ui.model.problem.ProblemDefinition` into the
source of a standard morphopt problem module (a top-level ``ThisController``
class), ready for ``morphopt.start_optimization`` / ``restart_optimization``.
"""

from __future__ import annotations

import ast

from ..model.problem import Node, ProblemDefinition
from ..model.schemas import (
    SURFACE_TYPES, INTERFACE_TYPES, UPDATER_CATALOG,
)
from ..schemes.base import get_template


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
    return SURFACE_TYPES[surface.params["type"]]["factory"]


def render_surface_call(surface: Node) -> str:
    factory = _surface_factory(surface)
    if factory is None:  # fixed_stl
        return "self.FixedSurface.initialize_from_stl_file(%s)" % _literal(
            surface.params.get("path_stl", "")
        )
    kwargs = []
    for key, value in surface.params.items():
        if key in ("type", "flip") or value is None:
            continue
        kwargs.append(f"{key}={_literal(value)}")
    flip = surface.params.get("flip", False)
    kwargs.append(f"flip={_literal(flip)}")
    return f"self.{factory}({', '.join(kwargs)})"


def render_interface_call(interface: Node) -> str:
    itype = interface.params["type"]
    cls = f"{itype}Interface"
    kwargs = []
    for key, value in interface.params.items():
        if key == "type" or value is None:
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
    objective = problem.node("objective") or Node("objective", params={})
    jac = list(objective.params.get("jacobian_needed", []) or [])
    obj_body = objective.params.get("_objective_function", template.default_objective_slot())
    met_body = objective.params.get("_get_metrics", template.default_metrics_slot())

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
    solver = problem.node("solver") or Node("solver", params={})
    np_ = int(solver.params.get("num_process", 1))
    gpus = list(solver.params.get("gpus", []) or [])
    tasklist = list(solver.params.get("task_index_list", []) or [])
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
    geo = problem.node("geometry") or Node("geometry", params={})
    geo_fields = {
        "fea_seed_size", "mesh_order", "reinitialize_per_iter",
        "thickness", "num_layers",
    }
    kw = []
    for k, v in geo.params.items():
        if k in geo_fields and v is not None:
            kw.append(f"{k}={_literal(v)}")
    return ", ".join(kw)


def _emit_geometry_init(a, problem: ProblemDefinition, template) -> None:
    surfaces = problem.surfaces()
    if problem.scheme == "simp":
        geo = problem.node("geometry") or Node("geometry", params={})
        a(f"                super().__init__(mesh_file={_literal(geo.params.get('mesh_file', ''))})")
        return
    kw = _geometry_kwargs(problem)
    a(f"                super().__init__({kw})" if kw else "                super().__init__()")
    for i, srf in enumerate(surfaces):
        a("")
        a("                # %s (surface index %d)" % (SURFACE_TYPES[srf.params["type"]]["label_en"], i))
        a(f"                self.add_surface({render_surface_call(srf)})")


def _emit_apply_constraints(a, problem: ProblemDefinition, template) -> None:
    geo = problem.node("geometry") or Node("geometry", params={})
    body = geo.params.get("_apply_surface_constraints") or template.default_apply_surface_constraints()
    body = str(body).strip()
    if not body or body == "pass":
        return
    a("            def apply_surface_constraints(self):")
    a(indent_block(body, 16))
    a("")


def _emit_interfaces(a, problem: ProblemDefinition) -> None:
    interfaces = [n for n in problem.root.iter_nodes()
                  if n.kind == "interface" and n.params.get("type")]
    if not interfaces:
        a("                pass")
        return
    for it in interfaces:
        a(f"                self.add_fea_interface({render_interface_call(it)}, name={it.name!r})")


def _emit_steps(a, problem: ProblemDefinition) -> None:
    steps = problem.node("steps") or Node("steps", params={"num_steps": 1, "step_values": [{}]})
    n = int(steps.params.get("num_steps", 1))
    values = steps.params.get("step_values") or [{} for _ in range(n)]
    while len(values) < n:
        values.append({})
    a(f"                self.set_step_num({n})")
    for s in range(n):
        step_dict = values[s] or {}
        for name, amps in step_dict.items():
            a(f"                self.set_step_params({s}, {name!r}, {amps!r})")


def _emit_material_init(a, problem: ProblemDefinition, template) -> None:
    mat = problem.node("material") or Node("material", params={})
    mtype = mat.params.get("type", template.BASES["material"].rsplit(".", 1)[-1])
    spec = None
    from ..model import schemas as S
    try:
        spec = S.MATERIAL_TYPES[mtype]
        allowed = {f["key"] for f in spec["params"]}
    except KeyError:
        allowed = set(mat.params)
    kw = []
    for k, v in mat.params.items():
        if k in ("type",) or k.startswith("_") or v is None:
            continue
        if k not in allowed:
            continue
        kw.append(f"{k}={_literal(v)}")
    a(f"                super().__init__({', '.join(kw)})" if kw else "                super().__init__()")


def _emit_map_designfield(a, problem: ProblemDefinition, template) -> None:
    mat = problem.node("material") or Node("material", params={})
    body = mat.params.get("_map_bsp_designfield") or template.default_map_bsp_designfield()
    body = str(body).strip()
    if not body or "return nodes" in body:
        return
    a("")
    a("            def _map_bsp_designfield(self, nodes):")
    a(indent_block(body, 16))


def _emit_updater(a, problem: ProblemDefinition, template, device: str) -> None:
    upd = problem.node("updater") or Node("updater", params={})
    geom_cfg = upd.params.get("geometry")
    mat_cfg = upd.params.get("materials")
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
