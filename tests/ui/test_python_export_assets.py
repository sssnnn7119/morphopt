from __future__ import annotations

import base64
import ast
import importlib
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from morphopt.optcore.controller import Controller
from morphopt.ui import launcher
from morphopt.ui.application import ProblemLibrary
from morphopt.ui.codegen.assets import PYTHON_ASSET_DIRECTORY
from morphopt.ui.codegen.generator import generate_source
from morphopt.ui.model.node_types.parts import (
    BoundaryPartNode,
    CADPartNode,
    INPPartNode,
)
from morphopt.ui.model.node_types.surfaces import MeshSurfaceNode
from morphopt.ui.model.problem import CADOperationNode


def test_python_export_copies_stl_inp_and_step_assets_without_changing_morph_data(tmp_path):
    stl_source = tmp_path / "shape.stl"
    inp_source = tmp_path / "mesh.inp"
    step_content = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
    stl_content = b"solid shape\nendsolid shape\n"
    inp_content = b"*Part, name=mesh\n*End Part\n"
    stl_source.write_bytes(stl_content)
    inp_source.write_bytes(inp_content)

    problem = ProblemLibrary.create_blank()
    boundary = BoundaryPartNode(name="boundary")
    stl_surface = MeshSurfaceNode(name="stl_surface", path_stl=str(stl_source))
    boundary.add_surface(stl_surface)
    problem.add_part(boundary)

    inp_part = INPPartNode(
        name="inp_part", mesh_file=str(inp_source), inp_part_name="mesh"
    )
    problem.add_part(inp_part)

    cad_part = CADPartNode(name="cad_part")
    problem.add_part(cad_part)
    step = CADOperationNode.create("StepImport", operation_id="step_import")
    step.filename = "model.step"
    step.data = base64.b64encode(step_content).decode("ascii")
    problem.add_cad_operation(cad_part, step)

    original_morph = problem.to_dict()
    output = tmp_path / "export" / "model.py"
    ProblemLibrary.export_python(problem, output)

    asset_directory = output.parent / PYTHON_ASSET_DIRECTORY
    assets = list(asset_directory.iterdir())
    contents = {path.read_bytes() for path in assets}
    assert contents == {stl_content, inp_content, step_content}
    assert {path.name for path in assets} == {"shape.stl", "mesh.inp", "model.step"}

    source = output.read_text(encoding="utf-8")
    compile(source, str(output), "exec")
    assert "StepImport.from_file(" in source
    preview = generate_source(problem)
    assert preview == source
    assert "data=" not in preview
    assert "initialize_from_stl_file(os.path.join(" in source
    assert "mesh_file=os.path.join(" in source
    assert str(stl_source) not in source
    assert str(inp_source) not in source
    assert problem.to_dict() == original_morph


def test_controller_copies_script_assets_into_restart_directory(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    script = source_dir / "job.py"
    script.write_text("# generated job\n", encoding="utf-8")
    source_assets = source_dir / "morphopt_assets"
    source_assets.mkdir()
    (source_assets / "mesh_abcd.inp").write_bytes(b"mesh")

    controller = Controller.__new__(Controller)
    controller.path_result_folder = str(tmp_path / "results")
    controller.opt_label = "job"
    controller.params = SimpleNamespace(pathlog_required=lambda: [])
    controller.solver = SimpleNamespace(pathlog_required=lambda: [])
    controller.updater = SimpleNamespace(pathlog_required=lambda: [])
    controller.objfun = SimpleNamespace(pathlog_required=lambda: [])

    monkeypatch.setattr(importlib, "import_module", lambda _name: (_ for _ in ()).throw(ImportError()))
    controller.initialize_path(str(script))

    copied_script_dir = Path(controller.path_result) / "scripts"
    assert (copied_script_dir / "MAIN_SCRIPT_FOR_RESTART.py").read_text(encoding="utf-8") == "# generated job\n"
    assert (copied_script_dir / "morphopt_assets" / "mesh_abcd.inp").read_bytes() == b"mesh"


def test_python_export_bundle_uses_folder_name_for_script_and_assets(tmp_path):
    source = tmp_path / "input.step"
    content = b"ISO-10303-21;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
    source.write_bytes(content)

    problem = ProblemLibrary.create_blank()
    cad_part = CADPartNode(name="cad_part")
    problem.add_part(cad_part)
    step = CADOperationNode.create("StepImport", operation_id="step_import")
    step.filename = source.name
    step.data = base64.b64encode(content).decode("ascii")
    problem.add_cad_operation(cad_part, step)

    folder = tmp_path / "Bracket Study"
    script = Path(ProblemLibrary.export_python_bundle(problem, folder))

    assert script == folder / "Bracket Study.py"
    assert script.is_file()
    assert (folder / PYTHON_ASSET_DIRECTORY / source.name).read_bytes() == content


def test_reexported_bundle_preserves_distinct_same_name_assets_and_can_be_moved(tmp_path):
    first = tmp_path / "first" / "mesh.inp"
    second = tmp_path / "second" / "mesh.inp"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first mesh")
    second.write_bytes(b"second mesh")
    problem = ProblemLibrary.create_blank()
    for name, path in (("first", first), ("second", second)):
        problem.add_part(INPPartNode(name=name, mesh_file=str(path)))

    folder = tmp_path / "bundle"
    script = Path(ProblemLibrary.export_python_bundle(problem, folder))
    first.write_bytes(b"updated first mesh")
    ProblemLibrary.export_python_bundle(problem, folder)
    source = script.read_text()
    assert source == generate_source(problem)

    relocated = tmp_path / "relocated"
    shutil.move(folder, relocated)
    first.unlink()
    second.unlink()
    contents = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == "mesh_file":
            path = eval(compile(ast.Expression(node.value), "<mesh path>", "eval"), {
                "os": os, "__file__": str(relocated / script.name),
            })
            contents.add(Path(path).read_bytes())
    assert contents == {b"updated first mesh", b"second mesh"}


def test_ui_launch_uses_independent_script_bundles_and_rejects_invalid_code(tmp_path, monkeypatch):
    make_temp = launcher.tempfile.mkdtemp
    monkeypatch.setattr(launcher.tempfile, "mkdtemp", lambda **kwargs: make_temp(dir=tmp_path, **kwargs))
    launches = []
    process = object()
    monkeypatch.setattr(
        launcher, "_start_headless_process",
        lambda command, directory: launches.append(command) or process,
    )
    source = tmp_path / "mesh.inp"
    problem = ProblemLibrary.create_blank()
    problem.add_part(INPPartNode(name="mesh", mesh_file=str(source)))
    source.write_bytes(b"first mesh")
    first, _ = launcher.run_job(problem, str(tmp_path / "results"))
    source.write_bytes(b"second mesh")
    second, _ = launcher.run_job(problem, str(tmp_path / "results"))
    assert Path(first).parent != Path(second).parent
    assert (Path(first).parent / PYTHON_ASSET_DIRECTORY / source.name).read_bytes() == b"first mesh"
    assert (Path(second).parent / PYTHON_ASSET_DIRECTORY / source.name).read_bytes() == b"second mesh"

    problem.helper_code = "def broken("
    with pytest.raises(ValueError):
        launcher.run_job(problem, str(tmp_path / "results"))
    assert len(launches) == 2
