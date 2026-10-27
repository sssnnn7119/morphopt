"""Part set lists select exact FE faces and nodes in the right-hand viewport."""

from pathlib import Path

import numpy as np
import pyvista as pv
import pytest
from PySide6.QtWidgets import QApplication, QWidget

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.part_mesh import build_part_mesh
from morphopt.ui.model.node_types.parts import BoundaryPartNode, BoxPartNode, INPPartNode
from morphopt.ui.model.node_types.surfaces import BREPSurfaceNode
from morphopt.ui.model.problem import CustomClassNode, MethodOverrideNode, PartNode
from morphopt.ui.visualization.geometry import PreviewGeometry


@pytest.fixture
def window(monkeypatch):
    from morphopt.ui import workbench
    from morphopt.ui.widgets import viewer

    app = QApplication.instance() or QApplication([])

    class Host(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.plotter = pv.Plotter(off_screen=True, window_size=(400, 400))

    monkeypatch.setattr(viewer, "_PlotHost", Host)
    problem = ProblemLibrary.create_blank()
    part = BoxPartNode(name="box", length=2, height=2, depth=2, mesh_size=1, mesh_order=1)
    part.instances[0].translation = [10, 20, 30]
    part.instances[0].rotation = [0, 0, np.pi / 2]
    problem.add_part(part)
    window = workbench.Workbench(problem)
    window.geometry_editor.edit_node(None, problem, part)
    yield window, part
    window.viewer.host.plotter.close()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_part_list_highlights_nodes_and_surfaces_without_changing_definition(window):
    window, part = window
    viewer = window.viewer
    tree = window.geometry_editor._part_set_lists[part]
    before = window.problem.to_dict()
    assert viewer.view_combo.currentData() == "assembly"

    def select(kind, name):
        group = tree.topLevelItem(0 if kind == "surfaces" else 1)
        item = next(group.child(i) for i in range(group.childCount()) if group.child(i).text(0) == name)
        tree.setCurrentItem(item)

    select("nodes", "nodes_xmax")
    assert viewer.view_combo.currentData() == "part"
    assert viewer.part_combo.currentData() is part
    assert viewer._set_selection == (part, "nodes", "nodes_xmax")
    camera = viewer.host.plotter.camera_position
    actor = viewer.renderer._set_actors[0]
    assert actor.mapper.dataset.n_points == 9
    assert np.allclose(actor.mapper.dataset.points[:, 0], 2)
    assert "nodes_xmax" in viewer.face_info.text()
    assert not actor.GetPickable()

    model = viewer.geometry._part_cache[id(part)]
    select("surfaces", "surface_xmin")
    assert viewer.geometry._part_cache[id(part)] is model
    assert len(viewer.renderer._set_actors) == 1
    assert np.allclose(viewer.renderer._set_actors[0].mapper.dataset.points[:, 0], 0)
    assert "surface_xmin" in viewer.face_info.text()
    viewer.section_enabled.setChecked(True)
    assert viewer.renderer._set_actors[0].mapper.GetNumberOfClippingPlanes() == 1
    assert viewer._set_selection == (part, "surfaces", "surface_xmin")
    assert viewer.host.plotter.camera_position == camera
    assert window.problem.to_dict() == before

    tree.setCurrentItem(tree.topLevelItem(0))
    assert not viewer.renderer.has_set_selection
    assert all(actor.prop.opacity == 1 for actor in viewer.renderer._geometry_actors)


def test_selection_follows_geometry_edits_and_switching_preview_modes(window):
    window, part = window
    viewer = window.viewer
    viewer.show_part_set(part, "nodes", "nodes_zmax")
    part.depth = 4
    viewer.set_problem(window.problem)
    assert viewer._set_selection == (part, "nodes", "nodes_zmax")
    assert np.allclose(viewer.renderer._set_actors[0].mapper.dataset.points[:, 2], 4)
    viewer.view_combo.setCurrentIndex(viewer.view_combo.findData("assembly"))
    assert viewer._set_selection is None
    assert not viewer.renderer.has_set_selection
    assert all(actor.prop.opacity == 1 for actor in viewer.renderer._geometry_actors)
    viewer.set_problem(window.problem)
    assert not viewer.renderer.has_set_selection
    viewer.view_combo.setCurrentIndex(viewer.view_combo.findData("part"))
    assert not viewer.renderer.has_set_selection
    viewer.show_part_set(part, "nodes", "nodes_zmax")
    assert np.allclose(viewer.renderer._set_actors[0].mapper.dataset.points[:, 2], 4)
    viewer.show_part_set(part, "nodes", "deleted_set")
    assert not viewer.renderer.has_set_selection
    assert viewer._set_selection is None
    assert "deleted_set" in viewer.face_info.text()


def test_selecting_another_parts_set_switches_to_its_local_view(window):
    window, first = window
    viewer = window.viewer
    second = BoxPartNode(name="other", length=6, height=2, depth=2, mesh_size=1, mesh_order=1)
    window.problem.add_part(second)
    viewer.set_problem(window.problem)
    viewer.show_part_set(first, "nodes", "nodes_xmax")
    viewer.show_part_set(second, "nodes", "nodes_xmax")
    assert viewer.view_combo.currentData() == "part"
    assert viewer.part_combo.currentData() is second
    assert viewer._set_selection == (second, "nodes", "nodes_xmax")
    assert np.allclose(viewer.renderer._set_actors[0].mapper.dataset.points[:, 0], 6)


def test_inp_highlight_uses_actual_node_sets():
    problem = ProblemLibrary.create_blank()
    part = INPPartNode(name="imported", mesh_file=str(Path(__file__).resolve().parents[2] / "docs/assets/ui_reference/reference-box.inp"))
    problem.add_part(part)
    geometry = PreviewGeometry()
    geometry.build(problem, "part", part)
    selected = geometry.mesh_for_set(part, "nodes", "nodes_xmin")
    assert selected.n_points == 4
    assert np.allclose(selected.points[:, 0], 0)


def test_brep_selection_mesh_preserves_exact_named_sets(step_factory):
    import base64
    from morphopt.shapeopt.surfaces.brep_surface import BREPSurface

    source = step_factory("box")
    brep = BREPSurface(source)
    metadata = brep.metadata()
    part = BoundaryPartNode(name="boundary", fea_seed_size=2, mesh_order=1)
    import json
    part.add_surface(BREPSurfaceNode(
        name="outer", filename=source.name,
        data=base64.b64encode(source.read_bytes()).decode("ascii"),
        brep_metadata=json.dumps(metadata),
    ))
    problem = ProblemLibrary.create_blank()
    problem.add_part(part)
    mesh = build_part_mesh(part, problem)
    assert "surface_0_All" in mesh.surfaces
    assert "surface_0_All" in mesh.set_nodes
    geometry = PreviewGeometry()
    geometry.build(problem, "part", part)
    face = next(iter(metadata["face_map"]))
    selected = geometry.mesh_for_set(part, "nodes", f"{face}_nodes")
    assert selected.n_points > 0
    assert np.count_nonzero(np.ptp(selected.points, axis=0) < 1e-8) == 1


def test_custom_part_lists_and_highlights_its_kernel_sets():
    from morphopt.ui.application.part_sets import PartSetCatalog

    problem = ProblemLibrary.create_blank()
    custom = CustomClassNode(name="NamedPart", params={"base_class": "morphopt.BasePart"})
    custom.add_child(MethodOverrideNode(name="build_part", params={"body": (
        "mesh = morphopt.BoxPart(length=2, height=2, depth=2, mesh_size=1, mesh_order=1).get_part()\n"
        "mesh.add_node_set('custom_tip', [0])\n"
        "return mesh"
    )}))
    problem.custom_classes.append(custom)
    part = PartNode.create("BasePart", name="custom_body")
    part.custom_class = "NamedPart"
    problem.add_part(part)
    assert "custom_tip" in PartSetCatalog(problem).for_part(part).nodes
    geometry = PreviewGeometry()
    scene = geometry.build(problem, "part", part)
    assert len(scene.base_meshes) == 1
    selected = geometry.mesh_for_set(part, "nodes", "custom_tip")
    assert selected.n_points == 1
