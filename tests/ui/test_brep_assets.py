"""BREP topology survives UI persistence and portable script export."""

from __future__ import annotations

from collections.abc import Callable
import base64
import json
from pathlib import Path
import runpy
import shutil

import numpy as np
import pytest

from morphopt.shapeopt.surfaces.brep_surface import BREPSurface
from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.part_sets import PartSetCatalog
from morphopt.ui.codegen.assets import collect_python_assets
from morphopt.ui.model.node_types.parts import BoundaryPartNode
from morphopt.ui.model.node_types.surfaces import BREPSurfaceNode


@pytest.fixture
def brep_node(step_factory: Callable[[str], Path], tmp_path: Path) -> BREPSurfaceNode:
    source = BREPSurface(step_factory("hole"))
    face = next(name for name, face in source.faces.items() if len(face.loops) == 2)
    edge = source.faces[face].loops[1][0]
    source.add_surface_set("loaded", face)
    source.add_node_set("rim", edge)
    source.convert_faces_to_nurbs(face)
    asset = source.export_step(tmp_path / "source" / "body.stp")
    return BREPSurfaceNode(
        name="outer", filename=asset.name,
        data=base64.b64encode(asset.read_bytes()).decode("ascii"),
        face_map=asset.with_suffix(".faces.json").read_text(),
        brep_metadata=asset.with_suffix(".brep.json").read_text(),
    )


def test_morph_and_moved_script_restore_topology_sets_and_mesh(
    brep_node: BREPSurfaceNode, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    problem = ProblemLibrary.create_blank()
    part = BoundaryPartNode(name="body", fea_seed_size=1.2, mesh_order=1)
    part.add_surface(brep_node)
    problem.add_part(part)
    definition = problem.to_dict()
    morph = Path(ProblemLibrary.save(problem, tmp_path / "case.morph"))
    restored = ProblemLibrary.load(morph)
    assert restored.to_dict() == definition
    surface = restored.parts()[0].surfaces[0]
    assert surface.brep_metadata == brep_node.brep_metadata
    assert brep_node.data in morph.read_text()

    catalog = PartSetCatalog(restored).for_part(restored.parts()[0])
    metadata = json.loads(surface.brep_metadata)
    assert "surface_0_loaded" in catalog.surfaces
    assert "surface_0_loaded_nodes" in catalog.nodes
    assert "surface_0_rim" in catalog.nodes
    assert {f"surface_0_{name}" for name in metadata["edge_map"]} <= set(catalog.nodes)
    assert {f"surface_0_{name}" for name in metadata["vertex_map"]} <= set(catalog.nodes)

    script = Path(ProblemLibrary.export_python_bundle(restored, tmp_path / "bundle"))
    assert brep_node.data not in script.read_text()
    moved = tmp_path / "moved"
    shutil.move(script.parent, moved)
    shutil.rmtree(tmp_path / "source")
    (tmp_path / "hole.step").unlink()
    cwd = tmp_path / "different_cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    namespace = runpy.run_path(str(moved / script.name), run_name="test_brep_bundle")
    geometry = namespace["ThisController"].Params.GeometryParams()
    geometry.initialize()
    boundary = geometry.interface("body")
    brep = boundary.surface_interface(0)
    assert brep.surface_sets == {"loaded": tuple(metadata["surface_sets"]["loaded"])}
    assert brep.node_sets == {"rim": tuple(metadata["node_sets"]["rim"])}
    assert set(brep.faces) == set(json.loads(surface.face_map))
    assert all(brep.faces[name].is_nurbs for name in metadata["nurbs_faces"])
    mesh = boundary.build_part(str(tmp_path / "mesh"))
    np.testing.assert_array_equal(mesh.set_nodes["surface_0_loaded_nodes"],
                                 mesh.set_nodes[f"{metadata['surface_sets']['loaded'][0]}_nodes"])
    assert len(mesh.set_nodes["surface_0_rim"]) > 2
    assert set(catalog.surfaces) <= set(mesh.surfaces.keys())
    assert set(catalog.nodes) <= set(mesh.set_nodes)
    assert problem.to_dict() == definition


def test_same_step_with_distinct_sets_exports_distinct_sidecars(
    brep_node: BREPSurfaceNode, tmp_path: Path,
) -> None:
    problem = ProblemLibrary.create_blank()
    original = json.loads(brep_node.brep_metadata)
    for name in ("first", "second"):
        metadata = {**original, "surface_sets": {name: original["surface_sets"]["loaded"]}}
        part = BoundaryPartNode(name=name)
        part.add_surface(BREPSurfaceNode(
            name="outer", filename=brep_node.filename, data=brep_node.data,
            face_map=brep_node.face_map, brep_metadata=json.dumps(metadata),
        ))
        problem.add_part(part)
    _, assets = collect_python_assets(problem)
    steps = [asset for asset in assets.values() if asset.format == "step"]
    assert len(steps) == 2
    assert steps[0].name != steps[1].name
    assert steps[0].content == steps[1].content
    script = Path(ProblemLibrary.export_python_bundle(problem, tmp_path / "bundle"))
    for step, name in zip(steps, ("first", "second"), strict=True):
        asset = script.parent / step.relative_path
        metadata = json.loads(asset.with_suffix(".brep.json").read_text())
        assert set(metadata["surface_sets"]) == {name}
        assert json.loads(asset.with_suffix(".faces.json").read_text()) == json.loads(brep_node.face_map)
