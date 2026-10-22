"""Every structured UI field must reach a real backend parameter."""
from __future__ import annotations
from morphopt.ui.model.fields import field_defaults
from morphopt.ui.model.material_models import MATERIAL_MODEL_CHOICES
from morphopt.ui.model.configuration import symmetry_constraint

import ast
import base64
import inspect
import os
from textwrap import dedent
from types import SimpleNamespace

import numpy as np
import pytest
import torch
import torchfea

import morphopt
from morphopt.ui.application import ProblemLibrary, ProblemSession
from morphopt.ui.application.fields import fields_for_node
from morphopt.ui.codegen.generator import (
    _emit_material_init,
    _render_part_constructor,
    _render_updater_item,
    _surface_constraints_for_part,
    render_cad_operation_call,
    render_component_call,
    render_surface_call,
)
from morphopt.ui.i18n import LocalizationManager
from morphopt.ui.model import registry as R
from morphopt.ui.model.problem import (
    CADOperationNode, HelperVariableNode, FEAComponentNode,
    PartNode, SurfaceNode,
)
from morphopt.ui.schemes.base import get_template


def literal_call(expression):
    call = ast.parse(expression, mode="eval").body
    assert isinstance(call, ast.Call)
    return (
        [ast.literal_eval(arg) for arg in call.args],
        {keyword.arg: ast.literal_eval(keyword.value) for keyword in call.keywords},
    )


def backend_surface_factory(spec):
    if spec.backend_class == "BREPSurface":
        return morphopt.BoundaryPart.BREPSurface
    if spec.factory is None:
        return morphopt.BoundaryPart.MeshSurface.initialize_from_stl_file
    family, method = spec.factory.split(".")
    return getattr(getattr(morphopt.BoundaryPart, family), method)


@pytest.mark.parametrize("kind,spec", R.SURFACE_TYPES.items())
def test_surface_fields_reach_factory(kind, spec):
    surface = SurfaceNode.create(kind)
    args, kwargs = literal_call(render_surface_call(surface))
    bound = inspect.signature(backend_surface_factory(spec)).bind(*args, **kwargs)
    if kind == "brep_surface":
        assert bound.arguments["path_step"] == ""
        assert surface.filename == ""
        assert surface.data == ""
        assert surface.face_map == "{}"
        return
    for field in spec.fields:
        assert bound.arguments[field.key] == surface.get_field(field.key)


@pytest.mark.parametrize("kind", ["bsp_cylinder", "cpgeo_cylinder", "cpgeo_sphere"])
def test_surface_factories_construct_with_ui_parameters(kind):
    spec = R.SURFACE_TYPES[kind]
    params = field_defaults(spec.fields)
    params.update(r0=2.0, seed_size=1.5, init_location=[1.0, 2.0, 3.0])
    if kind.endswith("cylinder"):
        params.update(length=12.0, maxC=0.6)
    else:
        params["MaxC"] = 0.6
    surface = backend_surface_factory(spec)(**params, flip=True)
    assert surface.is_updatable is True
    assert surface.MaxC == 0.6
    assert surface.init_size == 1.5
    assert surface.flip is True
    assert surface.control_points.shape[1] == 3
    assert np.isfinite(surface.control_points.cpu().numpy()).all()
    if kind == "bsp_cylinder":
        assert surface.MaxR == params["maxR"]
        assert surface.MaxFF == params["maxFF"]


@pytest.mark.parametrize("key,index", [("maxC", 0), ("maxFF", 1), ("maxR", 2)])
def test_bsp_fairness_thresholds_control_penalties(key, index, monkeypatch):
    params = field_defaults(R.SURFACE_TYPES["bsp_cylinder"].fields)
    params.update(r0=2.0, length=12.0, seed_size=1.5, maxC=1.0, maxR=1.0, maxFF=1.0)
    surface = backend_surface_factory(R.SURFACE_TYPES["bsp_cylinder"])(**params, flip=False)
    measures = [torch.zeros(1) for _ in range(6)]
    measures[index] = torch.tensor([0.9])
    surface.rr_compensation = torch.ones((4, 1))
    monkeypatch.setattr(surface, "_geofair_data", lambda *args: measures)
    points = surface.control_points.clone()
    penalty = surface.get_penalty_fairness(torch.ones(1), None, None, None)
    assert penalty.item() == pytest.approx(0.125)
    setattr(surface, {"maxC": "MaxC", "maxR": "MaxR", "maxFF": "MaxFF"}[key], 2.0)
    assert surface.get_penalty_fairness(torch.ones(1), None, None, None).item() == 0.0
    assert torch.equal(surface.control_points, points)


@pytest.mark.parametrize("kind,spec", R.PART_TYPES.items())
def test_part_fields_reach_constructor_or_explicit_base_parameter(kind, spec, tmp_path):
    part = PartNode.create(kind, name="body")
    # Empty import paths are deliberate unfinished definitions, so use actual
    # values to check every field rather than have codegen omit optional ones.
    for field in spec.fields:
        if part.get_field(field.key) == "":
            part.set_field(field.key, "selected")
    rendered = _render_part_constructor(
        part, asset_paths={id(part): "morphopt_assets/selected.inp"}
    )
    kwargs = eval(rendered, {
        "self": SimpleNamespace(**{kind: lambda **values: values}),
        "os": os, "__file__": str(tmp_path / "model.py"),
    })
    cls = getattr(morphopt, kind)
    inspect.signature(cls).bind(**kwargs)
    declared = {
        name for base in cls.__mro__ for name, parameter
        in inspect.signature(base.__init__).parameters.items()
        if parameter.kind not in (parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL)
    }
    for field in spec.fields:
        key = field.key
        assert key in declared, (kind, key)
        expected = (
            str(tmp_path / "morphopt_assets" / "selected.inp")
            if key == "mesh_file" else part.get_field(key)
        )
        assert kwargs[key] == expected


@pytest.mark.parametrize("kind,spec", R.LOAD_TYPES.items())
def test_load_fields_and_amplitude_counts_match_backend(kind, spec):
    component = FEAComponentNode.create(kind)
    for field in spec.fields:
        if field.type == "combo" and component.get_field(field.key) in (None, ""):
            component.set_field(field.key, "selected")
    args, kwargs = literal_call(render_component_call(component))
    cls = getattr(morphopt.FEAParams, spec.backend_class)
    inspect.signature(cls).bind(*args, **kwargs)
    assert set(kwargs) == {field.key for field in spec.fields}
    assert kwargs == {field.key: component.get_field(field.key) for field in spec.fields}
    assert cls(*args, **kwargs).num_values == spec.num_values


@pytest.mark.parametrize("kind", next(
    field.choices for field in R.LOAD_TYPES["PenaltyDoF"].fields
    if field.key == "obj_type"
))
def test_penalty_object_type_choices_are_supported_by_assembly(kind):
    assembly = torchfea.Assembly()
    containers = {
        "auto": assembly._instances, "instance": assembly._instances,
        "rp": assembly._reference_points, "load": assembly._loads,
        "constraint": assembly._constraints, "boundary": assembly._boundarys,
    }
    marker = object()
    containers[kind]["selected"] = marker
    assert assembly.get_object("selected", kind) is marker


@pytest.mark.parametrize("kind,spec", R.CAD_OPERATION_TYPES.items())
def test_cad_fields_reach_native_operation(kind, spec, tmp_path):
    from morphopt.ui.application.cad import cad_operation_from_node

    operation = CADOperationNode.create(kind, operation_id="feature")
    for field in spec.fields:
        if field.type in {"combo", "str"}:
            operation.set_field(field.key, f"selected_{field.key}")
    if kind == "StepImport":
        content = b"STEP payload"
        operation.data = base64.b64encode(content).decode("ascii")
        relative = "morphopt_assets/" + operation.filename
        asset = tmp_path / relative
        asset.parent.mkdir()
        asset.write_bytes(content)
        rendered = render_cad_operation_call(operation, asset_paths={id(operation): relative})
        exported = eval(rendered, {
            "torchfea": torchfea, "os": os, "__file__": str(tmp_path / "model.py"),
        })
        preview = cad_operation_from_node(operation)
        assert (exported.id, exported.filename, exported.data) == (
            preview.id, preview.filename, preview.data,
        )
        return
    rendered = render_cad_operation_call(operation)
    args, kwargs = literal_call(rendered)
    cls = getattr(torchfea.cad, kind)
    bound = inspect.signature(cls).bind(*args, **kwargs)
    assert bound.arguments["id"] == "feature"
    for field in spec.fields:
        assert bound.arguments[field.key] == operation.get_field(field.key)
    # Preview and exported scripts must construct the same native CAD data.
    preview = cad_operation_from_node(operation)
    exported = cls(*args, **kwargs)
    for key in bound.arguments:
        assert getattr(preview, key) == getattr(exported, key)


UPDATER_ITEMS = [
    (category, kind, spec)
    for category, catalog in R.UPDATER_CATALOG.items()
    for kind, spec in catalog.items()
]


@pytest.mark.parametrize("category,kind,spec", UPDATER_ITEMS)
def test_updater_term_fields_reach_backend(category, kind, spec):
    params = field_defaults(spec.fields)
    if kind == "VolFrac":
        params["elementname"] = "design"
    expression = _render_updater_item({"type": kind, "params": params}, category)
    root = (morphopt.UpdaterBoundaryPart if spec.group == "geometry"
            else morphopt.UpdaterSIMPMaterial)
    target = eval(expression.split("(", 1)[0], {"self": root, "morphopt": morphopt})
    args, kwargs = literal_call(expression)
    inspect.signature(target).bind(*args, **kwargs)
    assert kwargs == params


@pytest.mark.parametrize("kind,spec", [
    (kind, spec) for kind, spec in R.SURFACE_SYMMETRY_CONSTRAINTS.items()
    if spec.factory is not None
])
def test_symmetry_fields_reach_surface_owned_constraint(kind, spec):
    problem = ProblemLibrary.create("shapeopt")
    part = problem.parts()[0]
    surface_kind = "bsp_cylinder" if spec.factory == "BSP" else "cpgeo_cylinder"
    part.surfaces.clear()
    for index in range(2):
        part.add_surface(SurfaceNode.create(surface_kind, index=index))
    item = symmetry_constraint(kind)
    item["surface_index"] = 0
    if spec.related_surface:
        item["related_surface_index"] = 1
    statements, body = _surface_constraints_for_part(
        {"symmetry_constraints": [item]}, part, problem,
    )
    assert not body
    outer = ast.parse(statements[0], mode="eval").body
    call = outer.args[0]
    kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
    surface_cls = getattr(morphopt.BoundaryPart, spec.factory)
    constraint_cls = getattr(surface_cls, spec.method)
    args = [object()] if spec.related_surface else []
    inspect.signature(constraint_cls).bind(*args, **kwargs)
    assert kwargs == field_defaults(spec.fields)


@pytest.mark.parametrize("material_type", R.MATERIAL_TYPES)
@pytest.mark.parametrize("model", MATERIAL_MODEL_CHOICES)
def test_every_visible_material_field_reaches_its_constructor(material_type, model):
    problem = ProblemLibrary.create("simp")
    original = problem.material_nodes()[0]
    material = R.MATERIAL_TYPES[material_type](name=original.name)
    material.set_part(original.part)
    problem.materials.assignments[0] = material
    material.material_model = model
    visible, _, _ = fields_for_node(material, problem)
    visible_keys = {field.key for field in visible}
    if material_type == "SIMP_BSPFieldMaterials":
        assert {"bounding_box", "simp_field_resolution", "degree", "initial_ratio",
                "simp_ratio_min", "voidpenalfactor", "materialpenalty"} <= visible_keys
        if model in ("NeoHookean", "NeoHookeanLnJ"):
            assert {"mumax", "kappamax"} <= visible_keys
            assert not {"mu", "kappa"} & visible_keys
    lines = []
    _emit_material_init(lines.append, problem, get_template(problem.scheme))
    tree = ast.parse(dedent("\n".join(lines)))
    ctor = next(call for call in ast.walk(tree) if isinstance(call, ast.Call)
                and ast.unparse(call.func) == f"morphopt.{material_type}")
    kwargs = {kw.arg: kw.value for kw in ctor.keywords}
    parameter_call = kwargs.pop("material_parameters")
    assert ast.unparse(parameter_call.func) == f"self.models.{model}Params"
    material_parameters = {kw.arg: ast.literal_eval(kw.value) for kw in parameter_call.keywords}
    constructor_params = {key: ast.literal_eval(value) for key, value in kwargs.items()}
    typed = getattr(morphopt.MaterialsParams.models, f"{model}Params")
    parameter_values = typed(**material_parameters)
    inspect.signature(getattr(morphopt, material_type)).bind(
        **constructor_params, material_parameters=parameter_values,
    )
    for field in visible:
        key = field.key
        if key != "material_model":
            actual = constructor_params[key] if key in constructor_params else material_parameters[key]
            assert actual == material.get_field(key), (material_type, model, key)
    if material_type == "SIMP_BSPFieldMaterials" and model in ("NeoHookean", "NeoHookeanLnJ"):
        assert material_parameters == {"mu": material.mumax, "kappa": material.kappamax}


@pytest.mark.parametrize("gpus", [[], ["cuda:1"]])
def test_solver_device_selection_and_task_groups_reach_backend(gpus, monkeypatch):
    problem = ProblemLibrary.create("shapeopt")
    problem.solver.gpus = gpus
    problem.solver.num_process = 3
    problem.solver.task_index_list = [[0, 1], [2]]
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 8)
    namespace = {"__name__": "parameter_contract"}
    exec(ProblemSession(problem).source(), namespace)
    solver = namespace["ThisController"].Solver(None)
    assert solver.available_gpus == gpus
    assert solver.num_process == 3
    assert solver.task_index_list == [[0, 1], [2]]


def test_surface_helper_variable_is_emitted_as_an_expression():
    problem = ProblemLibrary.create("shapeopt")
    problem.helper_variables.append(HelperVariableNode(name="curvature_limit", params={"value": "0.25"}))
    surface = SurfaceNode.create("bsp_cylinder", maxC="curvature_limit")
    call = ast.parse(render_surface_call(surface, problem), mode="eval").body
    value = next(keyword.value for keyword in call.keywords if keyword.arg == "maxC")
    assert isinstance(value, ast.Name) and value.id == "curvature_limit"


def test_parameter_form_shows_code_field_and_fairness_help():
    from PySide6.QtWidgets import QApplication, QLabel
    from morphopt.ui.widgets.param_form import ParamForm

    app = QApplication.instance() or QApplication([])
    fields = R.SURFACE_TYPES["bsp_cylinder"].fields
    form = ParamForm(field_defaults(fields), fields)
    for key in ("maxR", "maxC", "maxFF"):
        tooltip = form.controls[key].toolTip()
        assert key in tooltip
        assert "Fairness" in tooltip
        assert any(label.toolTip() == tooltip for label in form.findChildren(QLabel))
    form.close()
    app.processEvents()


def test_fairness_threshold_labels_and_help_are_defined_in_each_locale():
    manager = LocalizationManager()
    for locale in ("zh-CN", "en-US"):
        table = manager.load_locale(locale)
        for catalog in (R.SURFACE_TYPES, R.PART_TYPES, R.LOAD_TYPES,
                        R.MATERIAL_TYPES, R.CAD_OPERATION_TYPES,
                        R.SURFACE_SYMMETRY_CONSTRAINTS, R.UPDATER_OBJECTIVES, R.UPDATER_CONSTRAINTS):
            for spec in catalog.values():
                assert spec.label_key in table
                for field in spec.fields:
                    assert field.label_key in table
                    if field.doc_key:
                        assert field.doc_key in table
        for key in ("maxR", "maxC", "maxFF"):
            field = next(f for f in R.SURFACE_TYPES["bsp_cylinder"].fields if f.key == key)
            assert "Fairness" in table[field.doc_key]
        assert not any("每次迭代允许的最大" in value for key, value in table.items()
                       if key.startswith("ui.schema.fields.max"))
