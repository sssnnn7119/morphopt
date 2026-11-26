"""Focused result-view tests for per-surface and control-net rendering."""

import numpy as np
import pyvista as pv
import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from morphopt.postprocess.visualization import (
    add_design_component,
    design_view_options,
)


@pytest.fixture
def log_view(tmp_path):
    from morphopt.ui.application.results import ResultSession
    from morphopt.ui.widgets.observation_pages import LogsPage

    app = QApplication.instance() or QApplication([])
    logs = tmp_path / "log"
    logs.mkdir()
    path = logs / "morphopt.log"
    path.write_text("".join(f"entry {index}: " + "details " * 40 + "\n" for index in range(200)), encoding="utf-8")
    results = ResultSession()
    results.bind(str(tmp_path))
    page = LogsPage()
    page.resize(800, 400)
    page.show()
    page.refresh(results)
    app.processEvents()
    try:
        yield page, path, results
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def append_log(page, path, results, content="new entry\n"):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(content)
    page.refresh(results)


def test_log_auto_scroll_can_be_disabled_for_reading(log_view):
    page, path, results = log_view
    scroll = page.text.verticalScrollBar()
    assert scroll.maximum() > 0
    assert scroll.value() == scroll.maximum()
    page.follow.setChecked(False)
    scroll.setValue(0)
    append_log(page, path, results)
    assert scroll.value() == 0
    assert page.text.toPlainText().endswith("new entry\n")
    page.follow.setChecked(True)
    assert scroll.value() == scroll.maximum()


def test_log_updates_hold_the_reading_position_until_user_returns_to_bottom(log_view):
    page, path, results = log_view
    scroll = page.text.verticalScrollBar()
    scroll.setValue(scroll.maximum() // 2)
    position = scroll.value()
    visible = page.text.firstVisibleBlock().text()
    page.refresh(results)
    assert scroll.value() == position
    for _ in range(3):
        append_log(page, path, results)
        assert page.follow.isChecked()
        assert scroll.value() == position
        assert page.text.firstVisibleBlock().text() == visible
    scroll.setValue(scroll.maximum())
    append_log(page, path, results)
    assert scroll.value() == scroll.maximum()


def test_log_updates_preserve_selection_even_at_the_bottom(log_view):
    page, path, results = log_view
    cursor = QTextCursor(page.text.document().lastBlock().previous())
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    page.text.setTextCursor(cursor)
    selected = page.text.textCursor().selectedText()
    assert selected
    scroll = page.text.verticalScrollBar()
    scroll.setValue(scroll.maximum())
    position = scroll.value()
    append_log(page, path, results)
    assert scroll.value() == position < scroll.maximum()
    assert page.text.textCursor().selectedText() == selected


def test_log_updates_do_not_move_a_dragged_scrollbar(log_view):
    page, path, results = log_view
    scroll = page.text.verticalScrollBar()
    position = scroll.value()
    scroll.setSliderDown(True)
    try:
        append_log(page, path, results)
        assert scroll.value() == position < scroll.maximum()
    finally:
        scroll.setSliderDown(False)


def test_log_trimming_preserves_the_visible_text_and_horizontal_position(log_view):
    page, path, results = log_view
    page.text.setMaximumBlockCount(50)
    scroll = page.text.verticalScrollBar()
    scroll.setValue(scroll.maximum() // 2)
    visible = page.text.firstVisibleBlock().text()
    horizontal = page.text.horizontalScrollBar()
    horizontal.setValue(horizontal.maximum() // 2)
    horizontal_position = horizontal.value()
    assert horizontal_position > 0
    append_log(page, path, results, "new entry\n" * 10)
    assert page.text.blockCount() == 50
    assert page.text.firstVisibleBlock().text() == visible
    assert horizontal.value() == horizontal_position


@pytest.fixture
def saved_boundary(tmp_path):
    from morphopt.postprocess.snapshots import SavedComponent

    files = {}
    for index in range(2):
        for name, mesh in ((f"surface_{index}", pv.Plane()), (f"net_{index}", pv.Line())):
            files[name] = tmp_path / f"{name}.vtp"
            mesh.save(files[name])
    return SavedComponent("Part", "boundary", "BoundaryPart", files)


def test_boundary_view_options_include_each_surface_and_control_net(saved_boundary):
    keys = [view.key for view in design_view_options(saved_boundary)]
    assert keys == [
        "all",
        "surface:0",
        "surface:0:control-net",
        "surface:1",
        "surface:1:control-net",
    ]


def test_control_net_is_rendered_as_overlay_actors(saved_boundary):
    component = saved_boundary
    view = next(view for view in design_view_options(component) if view.control_net)
    plotter = pv.Plotter(off_screen=True, window_size=(300, 300))
    try:
        add_design_component(
            plotter,
            component,
            geometry_color="#3f9fd6",
            ambient=0.2,
            diffuse=0.8,
            specular=0.1,
            specular_power=20.0,
            boundary_shell_opacity=0.35,
            view=view,
        )
        names = {str(name) for name in plotter.actors}
        prefix = f"boundary:{id(component)}:surface-0"
        assert f"{prefix}:control-net" in names
        assert f"{prefix}:control-points" in names
        assert "surface-0" in names
    finally:
        plotter.close()


def test_history_cache_revisits_frames_and_evicts_by_mesh_size(monkeypatch):
    from morphopt.constants import CONSTANT
    from morphopt.ui.widgets.observation_pages import HistorySceneCache

    points = pv.Sphere().points.copy()
    class Viewport:
        def __init__(self):
            self.plotter = pv.Plotter(off_screen=True)

        def rebuild(self, draw):
            self.plotter.clear()
            draw(self.plotter)

    first, second = Viewport(), Viewport()
    loads = []

    def show(viewport, i):
        def draw(scene):
            loads.append(i)
            mesh = pv.Sphere()
            mesh.points = points + i
            mesh.point_data["value"] = mesh.points[:, 0].copy()
            scene.add_mesh(mesh, name="shape", scalars="value")
            return True

        cache.show(viewport, (i,), draw)
        plotter = viewport.plotter
        actor = plotter.actors["shape"]
        assert np.allclose(actor.mapper.dataset.points, points + i)
        assert np.allclose(actor.mapper.dataset["value"], points[:, 0] + i)
        assert actor.mapper.scalar_visibility
        assert any(a.IsA("vtkScalarBarActor") for a in plotter.actors.values())

    try:
        cache = HistorySceneCache()
        show(first, 1)
        monkeypatch.setattr(CONSTANT.UI.OBSERVER, "PREVIEW_CACHE_BYTES", 2 * cache._mesh_bytes)
        show(second, 2)
        show(first, 1)
        show(first, 3)
        show(first, 1)
        show(second, 4)
        show(second, 2)
        assert loads == [1, 2, 3, 4, 2]
        cache.clear(second)
        show(second, 2)
        assert loads[-2:] == [2, 2]
    finally:
        first.plotter.close()
        second.plotter.close()


def test_deformation_history_retries_missing_cases_and_reuses_available_meshes(monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QWidget
    from morphopt.ui.widgets import observation_pages as pages

    app = QApplication.instance() or QApplication([])
    loaded = []

    class Viewport(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.plotter = pv.Plotter(off_screen=True)

        def rebuild(self, draw):
            self.plotter.clear()
            draw(self.plotter)

    def mesh(case, step):
        loaded.append((case, step))
        return pv.Cube(center=(step, 0, 0)) if len(loaded) > 1 else None

    monkeypatch.setattr(pages, "PlotViewport", Viewport)
    results = SimpleNamespace(folder="archive", deformation_mesh=mesh)
    page = pages.DeformationCasePage()
    try:
        for step, case in [(1, "a"), (1, "a"), (1, "b"), (2, "a"), (1, "a")]:
            page.build(results, step, case)
        assert loaded == [("a", 1), ("a", 1), ("b", 1), ("a", 2)]
        assert page.viewport.plotter.actors["deformation-mesh"].mapper.dataset.center[0] == 1
        page.clear_view()
        page.build(results, 1, "a")
        assert len(loaded) == 5
    finally:
        page.viewport.plotter.close()
        page.close()
