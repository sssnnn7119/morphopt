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


class BspSurface:
    def __init__(self):
        self.control_points = np.array(
            [[x, y, 0.0] for y in range(2) for x in range(3)], dtype=float
        )
        self.model = type("BspModel", (), {"size": (2, 3)})()

    def get_mesh(self):
        return pv.Plane(i_resolution=4, j_resolution=2)


class BoundaryPart:
    def __init__(self):
        self.surfaceinterfaces = [BspSurface(), BspSurface()]
        self.name = "boundary"

    @property
    def num_surface_interfaces(self):
        return len(self.surfaceinterfaces)

    def plot(self, plotter):
        for index, surface in enumerate(self.surfaceinterfaces):
            plotter.add_mesh(
                surface.get_mesh(),
                name=f"boundary:{id(self)}:surface-{index}",
                color="#3f9fd6",
            )


def test_boundary_view_options_include_each_surface_and_control_net():
    keys = [view.key for view in design_view_options(BoundaryPart())]
    assert keys == [
        "all",
        "surface:0",
        "surface:0:control-net",
        "surface:1",
        "surface:1:control-net",
    ]


def test_control_net_is_rendered_as_overlay_actors():
    component = BoundaryPart()
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
        assert f"{prefix}" in names
    finally:
        plotter.close()
