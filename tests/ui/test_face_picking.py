"""Surface identity and VTK picking on merged Part previews."""

from pathlib import Path

import numpy as np
import pyvista as pv
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.model.node_types.parts import (
    BoundaryPartNode, BoxPartNode, CADPartNode, INPPartNode, OffsetBoundaryPartNode,
)
from morphopt.ui.model.node_types.surfaces import CPGEOCylinderSurfaceNode
from morphopt.ui.visualization.geometry import PreviewGeometry
from morphopt.ui.visualization.scene import LabelItem, PreviewScene
from morphopt.ui.widgets.preview_renderer import PreviewRenderer, _SOURCE_CELL_ID
from morphopt.ui.widgets.viewer import _FaceClickFilter


def scene_for(part, *, mode="part", geometry=None):
    problem = ProblemLibrary.create_blank()
    problem.add_part(part)
    geometry = geometry or PreviewGeometry()
    return geometry.build(problem, mode, part)


def test_box_faces_keep_local_names_after_instance_rotation():
    part = BoxPartNode(name="body", length=4, height=6, depth=8)
    instance = part.instances[0]
    instance.rotation = [0, 0, np.pi / 2]
    instance.translation = [10, 20, 30]
    scene = scene_for(part, mode="assembly")
    _, mesh, item = scene.base_meshes[0]
    info = item.faces
    assert info.part_name == "body"
    assert info.instance_name == instance.name
    names = [info.group_names[group][0] for group in info.cell_groups]
    assert set(names) == {f"surface_{axis}{side}" for axis in "xyz" for side in ("min", "max")}
    top = names.index("surface_zmax")
    assert mesh.cell_centers().points[top] == pytest.approx([7, 22, 38])


@pytest.mark.parametrize("part_type", [BoundaryPartNode, OffsetBoundaryPartNode])
def test_boundary_faces_distinguish_wall_and_caps(part_type):
    part = part_type(name="tube")
    part.add_surface(CPGEOCylinderSurfaceNode(name="outer", r0=2, length=10))
    scene = scene_for(part)
    _, mesh, item = scene.base_meshes[0]
    names = [item.faces.group_names[group][0] for group in item.faces.cell_groups]
    assert set(names) == {"surface_0_All", "surface_0_Bottom", "surface_0_Head"}
    centers = mesh.cell_centers().points
    assert np.allclose(centers[np.array(names) == "surface_0_Bottom", 2], 0)
    assert np.allclose(centers[np.array(names) == "surface_0_Head", 2], 10)


def test_cad_remains_merged_without_static_face_labels(monkeypatch):
    import morphopt.ui.visualization.geometry as geometry_module

    points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.]])
    records = [
        {"points": points, "triangles": [[0, 1, 2]],
         "edge_lines": [{"edge_tag": 1, "lines": [[0, 1]]}]},
        {"points": points, "triangles": [[1, 3, 2]],
         "edge_lines": [{"edge_tag": 1, "lines": [[0, 1]]}]},
    ]
    monkeypatch.setattr(geometry_module, "cad_brep_records_from_node", lambda *_: records)
    geometry = PreviewGeometry()
    part = CADPartNode(name="housing")
    scene = scene_for(part, geometry=geometry)
    assert len(scene.items) == 2
    assert not any(isinstance(item, LabelItem) for item in scene.items)
    _, mesh, item = scene.base_meshes[0]
    assert item.faces.group_names == (("face_0",), ("face_1",))
    assert list(item.faces.cell_groups) == [0, 1]
    assert geometry.cad_face_mesh(part, "face_1").n_cells == 1

    plotter = pv.Plotter(off_screen=True, window_size=(400, 400))
    monkeypatch.setattr(plotter, "render", lambda: None)
    renderer = PreviewRenderer(plotter)
    try:
        renderer.draw_scene(scene)
        plotter.camera_position = [(0.5, 0.5, 4), (0.5, 0.5, 0), (0, 1, 0)]
        plotter.reset_camera()
        plotter.renderer.SetWorldPoint(0.8, 0.8, 0, 1)
        plotter.renderer.WorldToDisplay()
        x, y, _ = plotter.renderer.GetDisplayPoint()
        hit = renderer.pick_face(round(x), round(y))
        assert hit.surface_names == ("face_1",)
        assert renderer._selection_actor.mapper.dataset.n_cells == 1
    finally:
        plotter.close()


def test_inp_face_names_come_from_original_surface_sets():
    source = Path(__file__).resolve().parents[2] / "docs/examples/reference-box.inp"
    part = INPPartNode(name="imported", mesh_file=str(source))
    scene = scene_for(part)
    assert len(scene.base_meshes) == 1
    _, mesh, item = scene.base_meshes[0]
    assert mesh.n_cells > 0
    assert len(item.faces.cell_groups) == mesh.n_cells
    assert item.faces.group_names == (("extern",),)


def test_picker_selects_merged_face_and_ignores_overlays_and_empty_space(monkeypatch):
    # Cell picking is geometric; no native GL window or raster rendering is
    # required to exercise the actual VTK ray intersection and cell identity.
    plotter = pv.Plotter(off_screen=True, window_size=(400, 400))
    monkeypatch.setattr(plotter, "render", lambda: None)
    selections = []
    renderer = PreviewRenderer(plotter, on_face_picked=selections.append)
    try:
        scene = scene_for(BoxPartNode(name="body", length=2, height=2, depth=2))
        renderer.draw_scene(scene)
        plotter.camera_position = [(1, 1, 8), (1, 1, 1), (0, 1, 0)]
        plotter.reset_camera()
        # A foreground load glyph must not hide the Part from the picker.
        plotter.add_mesh(pv.Plane(center=(1, 1, 4), i_size=1, j_size=1), color="red")
        hit = renderer.pick_face(200, 200)
        assert hit.part_name == "body"
        assert hit.surface_names == ("surface_zmax",)
        assert renderer._selection_actor.mapper.dataset.n_cells == 1
        first_actor = renderer._selection_actor
        assert renderer.pick_face(200, 200) == hit
        assert first_actor not in plotter.renderer.actors.values()
        assert renderer.pick_face(0, 0) is None
        assert renderer._selection_actor is None
        assert selections[-1] is None
        renderer.draw_scene(PreviewScene())
        assert renderer.pick_face(200, 200) is None
    finally:
        plotter.close()


def test_dragging_the_view_does_not_select_a_face(monkeypatch):
    plotter = pv.Plotter(off_screen=True)
    monkeypatch.setattr(plotter, "render", lambda: None)
    renderer = PreviewRenderer(plotter)
    picked = []
    monkeypatch.setattr(renderer, "pick_face", lambda *xy: picked.append(xy))
    positions = iter([(10, 10), (30, 30), (10, 10)])
    monkeypatch.setattr(plotter.iren, "get_event_position", lambda: next(positions))
    try:
        renderer._face_press()
        renderer._face_move()
        renderer._face_release()
        assert picked == []
    finally:
        plotter.close()


def test_section_clips_picking_and_highlight_without_rebuilding_geometry(monkeypatch):
    plotter = pv.Plotter(off_screen=True, window_size=(400, 400))
    monkeypatch.setattr(plotter, "render", lambda: None)
    renderer = PreviewRenderer(plotter)
    try:
        scene = scene_for(BoxPartNode(name="body", length=2, height=2, depth=2))
        renderer.draw_scene(scene)
        plotter.camera_position = [(1, 1, 8), (1, 1, 1), (0, 1, 0)]
        plotter.reset_camera()
        actor = renderer._geometry_actors[0]
        camera = plotter.camera_position
        assert renderer.pick_face(200, 200).surface_names == ("surface_zmax",)
        renderer.set_section(True, 2, 0.5, reverse=True)
        assert renderer.section_position == pytest.approx(1)
        assert renderer._geometry_actors[0] is actor
        assert actor.mapper.GetNumberOfClippingPlanes() == 1
        assert renderer.pick_face(200, 200).surface_names == ("surface_zmin",)
        assert renderer._selection_actor.mapper.GetNumberOfClippingPlanes() == 1
        renderer.set_section(True, 2, 0.7, reverse=True)
        assert renderer.section_position == pytest.approx(1.4)
        assert renderer._geometry_actors[0] is actor
        assert renderer._selection_actor is None
        assert plotter.camera_position == camera
        # Rebuilding after a model edit retains the section settings.
        renderer.draw_scene(scene)
        assert renderer.section_position == pytest.approx(1.4)
        assert renderer._geometry_actors[0].mapper.GetNumberOfClippingPlanes() == 1
        renderer.set_section(False, 2, 0.7)
        assert renderer._geometry_actors[0].mapper.GetNumberOfClippingPlanes() == 0
        assert renderer.pick_face(200, 200).surface_names == ("surface_zmax",)
    finally:
        plotter.close()


@pytest.mark.parametrize("scale", [1, 1.5, 2])
def test_qt_click_maps_to_render_pixels_at_display_scale(monkeypatch, scale):
    app = QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.resize(400, 300)
    render_size = (round(400 * scale), round(300 * scale))
    plotter = pv.Plotter(off_screen=True, window_size=render_size)
    monkeypatch.setattr(plotter, "render", lambda: None)
    selected = []
    renderer = PreviewRenderer(plotter, on_face_picked=selected.append, track_mouse_events=False)
    mouse_filter = _FaceClickFilter(widget, plotter, renderer)
    try:
        renderer.draw_scene(scene_for(BoxPartNode(name="body", length=2, height=2, depth=2)))
        plotter.camera_position = [(1, 1, 8), (1, 1, 1), (0, 1, 0)]
        plotter.reset_camera()
        plotter.renderer.SetWorldPoint(1.5, 1.5, 2, 1)
        plotter.renderer.WorldToDisplay()
        x, y, _ = plotter.renderer.GetDisplayPoint()
        local = QPointF(x / scale, (render_size[1] - 1 - y) / scale)
        for event_type, buttons in (
            (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
        ):
            event = QMouseEvent(event_type, local, local, Qt.MouseButton.LeftButton,
                                buttons, Qt.KeyboardModifier.NoModifier)
            assert not mouse_filter.eventFilter(widget, event)
        app.processEvents()
        assert selected[-1].surface_names == ("surface_zmax",)
        assert renderer._face_picker.GetPickPosition() == pytest.approx((1.5, 1.5, 2), abs=0.02)
    finally:
        plotter.close()
        widget.close()


def test_mapper_cell_ids_are_resolved_to_source_faces(monkeypatch):
    plotter = pv.Plotter(off_screen=True, window_size=(400, 400))
    monkeypatch.setattr(plotter, "render", lambda: None)
    renderer = PreviewRenderer(plotter)
    try:
        renderer.draw_scene(scene_for(BoxPartNode(name="body", length=2, height=2, depth=2)))
        actor = renderer._geometry_actors[0]
        # Model the cell reordering caused by a surface/triangulation filter.
        displayed = actor.mapper.dataset
        order = np.arange(displayed.n_cells)[::-1]
        reordered = pv.PolyData(displayed.points, displayed.faces.reshape(-1, 5)[order].ravel())
        reordered.cell_data[_SOURCE_CELL_ID] = displayed.cell_data[_SOURCE_CELL_ID][order]
        assert list(reordered.cell_data[_SOURCE_CELL_ID]) == list(order)
        actor.mapper.dataset = reordered
        plotter.camera_position = [(1, 1, 8), (1, 1, 1), (0, 1, 0)]
        plotter.reset_camera()
        assert renderer.pick_face(200, 200).surface_names == ("surface_zmax",)
    finally:
        plotter.close()
