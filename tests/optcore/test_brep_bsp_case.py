"""Portable mixed BREP/BSP geometry and fixed-boundary regression checks."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import torch

from morphopt.shapeopt.objectivefuncs.shapederivative import ShapeDerivative
from morphopt.shapeopt.boundary_part import BoundaryPart
from morphopt.ui.application import ProblemLibrary
from morphopt.ui.codegen.assets import collect_python_assets

CASE = Path(__file__).resolve().parents[2] / "docs/examples/brep-bsp-cylinder.morph"


@pytest.fixture
def boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryPart]:
    previous_dtype = torch.get_default_dtype()
    torch.set_default_dtype(torch.float64)
    problem = ProblemLibrary.load(CASE)
    script = Path(ProblemLibrary.export_python_bundle(problem, tmp_path / "brep_bsp"))
    spec = importlib.util.spec_from_file_location("brep_bsp", script)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "brep_bsp", module)
    spec.loader.exec_module(module)
    geometry = module.ThisController.Params.GeometryParams()
    geometry.initialize()
    try:
        yield geometry.interface("body")
    finally:
        torch.set_default_dtype(previous_dtype)


def test_case_embeds_assets_and_roundtrips(tmp_path: Path) -> None:
    problem = ProblemLibrary.load(CASE)
    part = problem.parts()[0]
    assert [surface.type for surface in part.surfaces] == ["brep_surface", "bsp_cylinder"]
    assert [surface.is_updatable for surface in part.surfaces] == [False, True]
    assert "if_update" not in problem.updater.geometry[0]
    assert problem.device == "cpu"
    assert problem.solver.num_process == 1
    assert problem.solver.gpus == []
    _, assets = collect_python_assets(problem)
    assert {asset.format for asset in assets.values()} == {"step", "json"}
    path = Path(ProblemLibrary.save(problem, tmp_path / "copy.morph"))
    assert ProblemLibrary.load(path).to_dict() == problem.to_dict()
    text = path.read_text(encoding="utf-8")
    assert "/home/" not in text
    assert "/run/media/" not in text
    script = Path(ProblemLibrary.export_python_bundle(problem, tmp_path / "export"))
    source = script.read_text(encoding="utf-8")
    assert "self.BREPSurface(os.path.join(" in source
    assert part.surfaces[0].data not in source


def test_mixed_boundaries_mesh_and_preserve_sets(boundary: BoundaryPart, tmp_path: Path) -> None:
    mesh = boundary.build_part(str(tmp_path))
    assert len(mesh.nodes) > 0
    assert len(mesh.elems["C3D4"]._elems) > 0
    for name in ("surface_0_All", "surface_1_All"):
        assert mesh.surfaces[name]
        assert len(mesh.set_nodes[name])
    for name in boundary.surface_interface(0).face_names:
        assert name in mesh.surfaces
        assert f"{name}_nodes" in mesh.set_nodes
        assert len(mesh.set_nodes[f"{name}_nodes"])
    assert not any(name.startswith("gmsh_surface_") for name in mesh.surfaces.keys())
    assert "surface_0_Bottom" not in mesh.set_nodes
    assert "surface_0_Head" not in mesh.set_nodes


def test_fixed_boundary_sampling_and_shape_derivative(boundary: BoundaryPart) -> None:
    outer, inner = boundary.surface_interfaces()
    r, rdu, rdu2 = boundary.get_geometry_values()
    weights = boundary.get_points_weight()
    assert outer.num_variables == 0
    assert inner.num_variables > 0
    assert r[0].shape[0] > 0
    assert rdu[0].shape == (len(r[0]), 3, 2)
    assert rdu2[0].shape == (len(r[0]), 3, 2, 2)
    assert weights[0].shape == (len(r[0]),)
    assert (weights[0] > 0).all()
    assert float(weights[0].sum()) == pytest.approx(160 * torch.pi, rel=0.05)
    side = (r[0][:, 2] > 0.1) & (r[0][:, 2] < 15.9)
    normals = torch.linalg.cross(rdu[0][:, :, 1], rdu[0][:, :, 0], dim=1)
    assert ((normals[side, :2] * r[0][side, :2]).sum(dim=1) < 0).all()
    objective = ShapeDerivative()
    objective.initialize(
        gradient=torch.ones(boundary.num_variables), r0=r,
        surfaces=boundary.surface_interfaces(),
    )
    assert objective._cp0[0].shape == (0, 3)
    assert objective.gradient[0].shape == (0, 3)
    before = boundary.get_parameters()
    inner.is_updatable = False
    inner.update_variables(torch.full_like(inner.control_points, 0.001))
    boundary.update_variables(torch.ones(boundary.num_variables))
    assert torch.equal(inner.get_surface_parameters(), before[1])
    inner.is_updatable = True
    inner.update_variables(torch.full_like(inner.control_points, 0.001))
    updated = boundary.get_geometry_values()[0]
    assert float(objective(r=updated)) > 0.0
    boundary.set_parameters(before)
