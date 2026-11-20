"""Global visualization preferences and the shared viewport controls."""

from dataclasses import replace

import numpy as np
import pyvista as pv
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QWidget

from morphopt.ui.theme import visualization as preferences
from morphopt.ui.visualization.rendering import apply_visualization, configure_plotter
from morphopt.ui.widgets import viewport
from morphopt.ui.widgets.visualization_settings import VisualizationSettingsDialog


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_settings(app, monkeypatch, tmp_path):
    store = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(preferences, "QSettings", lambda *args: store)
    manager = preferences.visualization_manager
    previous = manager.settings
    manager.apply(preferences.VisualizationSettings(), persist=False)
    yield manager
    manager.apply(previous, persist=False)


@pytest.fixture
def offscreen_viewports(app, monkeypatch):
    plotters = []

    class OffscreenPlotter(pv.Plotter):
        def __init__(self, parent, *, auto_update):
            self._widget = QWidget(parent)
            super().__init__(off_screen=True, window_size=(300, 250))
            plotters.append(self)

        @property
        def interactor(self):
            return self._widget

    monkeypatch.setattr(viewport, "QtInteractor", OffscreenPlotter)
    yield
    for plotter in plotters:
        plotter.close()


def test_settings_restore_and_light_strength_does_not_accumulate(isolated_settings):
    settings = replace(isolated_settings.settings, light_intensity=1.8, parallel_projection=False)
    isolated_settings.apply(settings)
    restored = preferences.VisualizationManager()
    restored.restore()
    assert restored.settings == settings
    plotter = pv.Plotter(off_screen=True)
    try:
        configure_plotter(plotter, settings=settings)
        intensity = [light.intensity for light in plotter.renderer.lights]
        configure_plotter(plotter, settings=settings)
        np.testing.assert_allclose([light.intensity for light in plotter.renderer.lights], intensity)
        assert not plotter.camera.parallel_projection
    finally:
        plotter.close()


def test_material_preferences_change_render_without_changing_overlays(isolated_settings):
    plotter = pv.Plotter(off_screen=True, window_size=(250, 250))
    try:
        configure_plotter(plotter)
        actor = plotter.add_mesh(pv.Sphere(), scalars=pv.Sphere().points[:, 2])
        overlay = plotter.add_mesh(pv.Cube().outline(), lighting=False, color="red")
        before = plotter.screenshot(return_img=True)
        camera = plotter.camera_position
        settings = replace(isolated_settings.settings, ambient=0, diffuse=0, specular=0,
                           light_intensity=0, smooth_shading=False)
        configure_plotter(plotter, settings=settings)
        apply_visualization(plotter, settings)
        plotter.render()
        after = plotter.screenshot(return_img=True)
        assert actor.prop.ambient == 0
        assert actor.prop.diffuse == 0
        assert actor.prop.GetInterpolation() == 0  # VTK_FLAT
        assert actor.mapper.scalar_visibility
        assert not overlay.prop.lighting
        assert plotter.camera_position == camera
        assert np.count_nonzero(np.any(before != after, axis=2)) > 100
    finally:
        plotter.close()


def test_axis_views_survive_iteration_updates_and_hidden_settings_changes(
    app, isolated_settings, offscreen_viewports
):
    widget = viewport.PlotViewport()
    try:
        widget.rebuild(lambda plotter: plotter.add_mesh(pv.Sphere(), name="geometry"))
        widget.show()
        app.processEvents()
        for name, (vector, up) in viewport.VIEWS.items():
            widget.set_view(name)
            expected = -np.array(vector, dtype=float)
            expected /= np.linalg.norm(expected)
            np.testing.assert_allclose(widget.plotter.camera.direction, expected, atol=1e-7)
        widget.set_view("-x")
        widget.plotter.camera.zoom(1.4)
        camera = widget.plotter.camera_position
        scale = widget.plotter.camera.parallel_scale
        widget.rebuild(lambda plotter: plotter.add_mesh(pv.Cube(), name="geometry"))
        app.processEvents()
        assert widget.plotter.camera_position == camera
        assert widget.plotter.camera.parallel_scale == scale
        widget.hide()
        actor = widget.plotter.actors["geometry"]
        view_changes = []
        widget.viewChanged.connect(lambda: view_changes.append(True))
        isolated_settings.apply(replace(isolated_settings.settings, ambient=0.65,
                                        parallel_projection=False), persist=False)
        widget.show()
        app.processEvents()
        assert widget.plotter.actors["geometry"] is actor
        assert actor.prop.ambient == pytest.approx(0.65)
        assert not widget.plotter.camera.parallel_projection
        assert view_changes == [True]
        widget.fit_button.click()
        np.testing.assert_allclose(widget.plotter.camera.direction, [1, 0, 0], atol=1e-7)
    finally:
        widget.close()


@pytest.mark.parametrize("parallel", [True, False])
@pytest.mark.parametrize("window_size", [(640, 320), (320, 640)])
def test_fit_button_frames_actual_geometry_in_current_projection(
    app, offscreen_viewports, parallel, window_size,
):
    from morphopt.constants import CONSTANT

    widget = viewport.PlotViewport()
    try:
        plotter = widget.plotter
        plotter.window_size = window_size
        # Viewed end-on, the world bounding box of this long cylinder is much
        # larger than its actual outline. Its actor also has a world translation.
        mesh = pv.Cylinder(direction=(1, 1, 1), height=40, radius=2)
        actor = plotter.add_mesh(mesh)
        actor.position = (12, 22, -7)
        plotter.add_mesh(pv.Cube(center=(300, 300, 300))).visibility = False
        plotter.add_text("Iteration 3")
        camera = plotter.camera
        camera.parallel_projection = parallel
        plotter.camera_position = [(200, 200, 200), (0, 0, 0), (0, 0, 1)]
        camera.parallel_scale = 1000
        direction, up = camera.direction, camera.up
        widget.fit_button.click()
        np.testing.assert_allclose(camera.direction, direction)
        np.testing.assert_allclose(camera.up, up)
        assert camera.distance < 100
        if parallel:
            assert camera.parallel_scale < 10

        projection = camera.GetCompositeProjectionTransformMatrix(
            plotter.renderer.GetTiledAspectRatio(), -1, 1,
        )
        world = mesh.points + actor.position
        clip = np.c_[world, np.ones(mesh.n_points)] @ pv.array_from_vtkmatrix(projection).T
        ndc = clip[:, :3] / clip[:, 3:]
        assert np.abs(ndc[:, 2]).max() <= 1
        frame = CONSTANT.UI.CAMERA.FIT_VIEW_FRACTION
        extent = np.ptp(ndc[:, :2], axis=0) / 2
        assert extent.max() == pytest.approx(frame)
        assert np.abs(ndc[:, :2]).max() <= frame + 1e-6
    finally:
        widget.close()


def test_settings_dialog_previews_then_applies_without_closing(
    app, isolated_settings, offscreen_viewports
):
    dialog = VisualizationSettingsDialog()
    original = isolated_settings.settings
    dialog.show()
    app.processEvents()
    dialog.values["ambient"].setValue(0.6)
    dialog.projection.setCurrentIndex(dialog.projection.findData(False))
    app.processEvents()
    assert isolated_settings.settings == original
    assert dialog.preview.settings.ambient == pytest.approx(0.6)
    assert not dialog.preview.plotter.camera.parallel_projection
    dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
    assert dialog.isVisible()
    assert isolated_settings.settings.ambient == pytest.approx(0.6)
    dialog.values["ambient"].setValue(0.2)
    dialog.reject()
    assert isolated_settings.settings.ambient == pytest.approx(0.6)
    confirmed = VisualizationSettingsDialog()
    confirmed.values["specular"].setValue(0.5)
    confirmed.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
    assert isolated_settings.settings.specular == pytest.approx(0.5)


@pytest.mark.parametrize("parallel", [True, False])
def test_flight_opens_an_independent_perspective_snapshot(
    app, isolated_settings, offscreen_viewports, parallel,
):
    isolated_settings.apply(replace(isolated_settings.settings, parallel_projection=parallel), persist=False)
    widget = viewport.PlotViewport()
    try:
        widget.show()
        widget.rebuild(lambda plotter: plotter.add_mesh(pv.Cube(center=(10, 20, 30))))
        app.processEvents()
        # Include a raw VTK overlay as well as geometry.
        widget.plotter.add_mesh(pv.Sphere(), scalars=pv.Sphere().points[:, 2])
        camera = widget.plotter.camera.copy()
        widget.flight_button.click()
        app.processEvents()
        flight = widget._flight_dialog
        assert flight.isVisible()
        assert not flight.viewport.plotter.camera.parallel_projection
        assert not flight.viewport.controls.isVisible()
        assert (flight.viewport.plotter.renderer.GetViewProps().GetNumberOfItems()
                == widget.plotter.renderer.GetViewProps().GetNumberOfItems())
        source_actor = widget.plotter.renderer.GetActors().GetItemAsObject(0)
        flight_actor = flight.viewport.plotter.renderer.GetActors().GetItemAsObject(0)
        assert flight_actor.GetMapper() is not source_actor.GetMapper()
        assert flight_actor.GetMapper().GetInput() is source_actor.GetMapper().GetInput()
        rendered = flight.viewport.plotter.screenshot(return_img=True)
        assert len(np.unique(rendered.reshape(-1, rendered.shape[-1]), axis=0)) > 100
        flight._pressed = {Qt.Key.Key_W}
        flight._advance(0.1)
        assert widget.plotter.camera == camera
        isolated_settings.apply(replace(isolated_settings.settings, parallel_projection=True), persist=False)
        app.processEvents()
        assert not flight.viewport.plotter.camera.parallel_projection
        widget.open_flight()
        assert widget._flight_dialog is flight
        flight.reject()
        app.processEvents()
        assert widget._flight_dialog is None
        widget.open_flight()
        assert widget._flight_dialog is not flight
        widget._flight_dialog.reject()
    finally:
        widget.close()


def test_closing_source_viewport_closes_flight_and_stops_movement(
    app, isolated_settings, offscreen_viewports,
):
    widget = viewport.PlotViewport()
    widget.show()
    widget.plotter.add_mesh(pv.Cube())
    widget.open_flight()
    app.processEvents()
    flight = widget._flight_dialog
    QTest.keyPress(flight._input_widget, Qt.Key.Key_W)
    assert flight._movement.isActive()
    widget.close()
    assert widget._flight_dialog is None
    assert not flight.isVisible()
    assert not flight._movement.isActive()
    assert flight.viewport.plotter._closed


def test_flight_mouse_looks_only_while_held_without_orbit_or_roll(
    app, isolated_settings, offscreen_viewports,
):
    widget = viewport.PlotViewport()
    widget.plotter.add_mesh(pv.Cube())
    flight = viewport.FirstPersonDialog(widget)
    try:
        flight.show()
        app.processEvents()
        target = flight._input_widget
        camera = flight.viewport.plotter.camera
        position = camera.position
        direction = camera.direction

        def move(x, y):
            event = QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y), QPointF(x, y),
                                Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                                Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(target, event)

        move(60, 60)
        np.testing.assert_allclose(camera.direction, direction)
        QTest.mousePress(target, Qt.MouseButton.LeftButton, pos=QPoint(60, 60))
        move(110, 80)
        assert not np.allclose(camera.direction, direction)
        np.testing.assert_allclose(camera.position, position)
        np.testing.assert_allclose(camera.up, [0, 0, 1])
        move(110, 100000)
        assert abs(np.degrees(flight._pitch)) == pytest.approx(89)
        QTest.mouseRelease(target, Qt.MouseButton.LeftButton, pos=QPoint(110, 80))
        direction = camera.direction
        move(180, 120)
        np.testing.assert_allclose(camera.direction, direction)
        QTest.mousePress(target, Qt.MouseButton.RightButton, pos=QPoint(40, 40))
        move(10, 10)
        QTest.mouseRelease(target, Qt.MouseButton.RightButton)
        np.testing.assert_allclose(camera.direction, direction)
    finally:
        flight.reject()
        widget.close()


@pytest.mark.parametrize("pitch", [-89, 0, 89])
def test_flight_keyboard_movement_release_focus_loss_and_reset(
    app, isolated_settings, offscreen_viewports, pitch,
):
    widget = viewport.PlotViewport()
    widget.plotter.add_mesh(pv.Cube())
    flight = viewport.FirstPersonDialog(widget)
    try:
        flight.show()
        app.processEvents()
        target = flight._input_widget
        camera = flight.viewport.plotter.camera
        home = np.array(camera.position)
        forward = flight._forward()
        forward[2] = 0
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0, 0, 1])
        right /= np.linalg.norm(right)
        for key, direction in ((Qt.Key.Key_W, forward), (Qt.Key.Key_S, -forward),
                               (Qt.Key.Key_D, right), (Qt.Key.Key_A, -right),
                               (Qt.Key.Key_E, [0, 0, 1]), (Qt.Key.Key_Q, [0, 0, -1])):
            flight._pitch = np.radians(pitch)
            flight._apply_pose()
            view_direction = camera.direction
            QTest.keyPress(target, key)
            assert flight._movement.isActive()
            flight._advance(0.1)
            np.testing.assert_allclose(camera.position, home + 0.1 * flight._speed * np.array(direction))
            np.testing.assert_allclose(camera.direction, view_direction)
            QTest.keyRelease(target, key)
            assert not flight._movement.isActive()
            position = camera.position
            flight._advance(0.1)
            np.testing.assert_allclose(camera.position, position)
            QTest.keyClick(target, Qt.Key.Key_R)
            np.testing.assert_allclose(camera.position, home)
        QTest.keyPress(target, Qt.Key.Key_Shift)
        QTest.keyPress(target, Qt.Key.Key_W)
        flight._advance(0.1)
        np.testing.assert_allclose(camera.position, home + 0.4 * flight._speed * forward)
        QTest.mousePress(target, Qt.MouseButton.LeftButton)
        QApplication.sendEvent(target, QEvent(QEvent.Type.FocusOut))
        assert not flight._movement.isActive()
        assert not flight._pressed
        assert flight._look_position is None
        QTest.keyClick(target, Qt.Key.Key_Escape)
        assert not flight.isVisible()
    finally:
        widget.close()


@pytest.mark.parametrize("parallel", [True, False])
def test_first_geometry_after_an_empty_scene_is_fitted_and_fully_visible(
    app, isolated_settings, offscreen_viewports, parallel,
):
    from itertools import product
    isolated_settings.apply(replace(isolated_settings.settings, parallel_projection=parallel), persist=False)
    widget = viewport.PlotViewport()
    try:
        widget.show()
        widget.rebuild(lambda plotter: None)
        app.processEvents()
        assert not widget._scene_has_geometry
        mesh = pv.Cylinder(center=(0, 0, 37), direction=(0, 0, 1), radius=4, height=74)
        widget.rebuild(lambda plotter: plotter.add_mesh(mesh))
        app.processEvents()
        assert widget._scene_has_geometry
        np.testing.assert_allclose(widget.plotter.camera.focal_point, mesh.center)
        renderer = widget.plotter.renderer
        projection = widget.plotter.camera.GetCompositeProjectionTransformMatrix(
            renderer.GetTiledAspectRatio(), -1, 1,
        )
        matrix = np.array([[projection.GetElement(i, j) for j in range(4)] for i in range(4)])
        corners = np.array(list(product(*np.array(mesh.bounds).reshape(3, 2))))
        projected = np.c_[corners, np.ones(len(corners))] @ matrix.T
        ndc = projected[:, :3] / projected[:, 3:]
        assert np.abs(ndc).max() <= 1 + 1e-6
        widget.plotter.camera.zoom(1.3)
        camera = widget.plotter.camera_position
        scale = widget.plotter.camera.parallel_scale
        widget.rebuild(lambda plotter: plotter.add_mesh(mesh))
        app.processEvents()
        assert widget.plotter.camera_position == camera
        assert widget.plotter.camera.parallel_scale == scale
    finally:
        widget.close()


def test_definition_preview_fits_the_first_bsp_surface(app, isolated_settings, offscreen_viewports):
    from morphopt.ui.application import ProblemLibrary
    from morphopt.ui.model.node_types.parts import BoundaryPartNode, BoxPartNode
    from morphopt.ui.model.node_types.surfaces import BspCylinderSurfaceNode
    from morphopt.ui.model.node_types.structural import InstanceNode
    from morphopt.ui.widgets.viewer import PreviewViewer

    problem = ProblemLibrary.create_blank()
    part = BoundaryPartNode(name="part1")
    problem.add_part(part)
    widget = PreviewViewer()
    try:
        widget.show()
        widget.set_problem(problem)
        app.processEvents()
        assert not widget.host._scene_has_geometry
        part.add_child(BspCylinderSurfaceNode(name="surface_0", r0=4, length=74, seed_size=1.4))
        widget.set_problem(problem)  # Same definition: no explicit camera reset.
        app.processEvents()
        assert widget.host._scene_has_geometry
        np.testing.assert_allclose(widget.host.plotter.camera.focal_point, [0, 0, 37], atol=1e-5)
        assert widget.host.plotter.camera.parallel_scale > 30
        widget.host.set_view("x")
        widget.host.plotter.camera.zoom(2)
        camera = widget.host.plotter.camera
        camera.position = np.array(camera.position) + [0, 5, 0]
        camera.focal_point = np.array(camera.focal_point) + [0, 5, 0]
        direction = widget.host.plotter.camera.direction
        zoomed_scale = widget.host.plotter.camera.parallel_scale
        # An internal surface leaves the bounds unchanged, but it is still
        # new geometry and must restore the complete model to the viewport.
        part.add_child(BspCylinderSurfaceNode(
            name="surface_1", r0=2, length=60, seed_size=1.4, init_location=[0, 0, 7],
        ))
        widget.set_problem(problem)
        app.processEvents()
        assert widget.host.plotter.camera.parallel_scale > zoomed_scale
        np.testing.assert_allclose(widget.host.plotter.camera.focal_point, [0, 0, 37], atol=1e-5)
        np.testing.assert_allclose(widget.host.plotter.camera.direction, direction)
        instance = InstanceNode(name="part1-2")
        instance.translation = [100, 0, 0]
        part.add_instance(instance)
        widget.set_problem(problem)
        app.processEvents()
        np.testing.assert_allclose(widget.host.plotter.camera.focal_point, [50, 0, 37], atol=1e-5)
        new_part = BoxPartNode(name="second", length=2, height=2, depth=2)
        new_part.instances[0].translation = [200, 0, 0]
        problem.add_part(new_part)
        widget.set_problem(problem)
        app.processEvents()
        np.testing.assert_allclose(widget.host.plotter.camera.focal_point, [99, 0, 37], atol=1e-5)
        widget.host.plotter.camera.zoom(1.3)
        camera = widget.host.plotter.camera_position
        scale = widget.host.plotter.camera.parallel_scale
        widget.set_problem(problem)
        app.processEvents()
        assert widget.host.plotter.camera_position == camera
        assert widget.host.plotter.camera.parallel_scale == scale
    finally:
        widget.host.plotter.close()
        widget.close()


def test_shared_viewport_refits_new_geometry_keys_without_resetting_orientation(
    app, isolated_settings, offscreen_viewports,
):
    widget = viewport.PlotViewport()
    try:
        widget.show()
        widget.rebuild(lambda plotter: plotter.add_mesh(pv.Cube()), geometry_keys=("first",))
        app.processEvents()
        widget.set_view("z")
        widget.plotter.camera.zoom(2)

        def build(plotter):
            plotter.add_mesh(pv.Cube())
            plotter.add_mesh(pv.Cube(center=(20, 0, 0)))

        widget.rebuild(build, geometry_keys=("first", "second"))
        app.processEvents()
        np.testing.assert_allclose(widget.plotter.camera.focal_point, [10, 0, 0])
        np.testing.assert_allclose(widget.plotter.camera.direction, [0, 0, -1])
        widget.plotter.camera.zoom(1.5)
        camera = widget.plotter.camera_position
        scale = widget.plotter.camera.parallel_scale
        widget.rebuild(build, geometry_keys=("first", "second"))
        app.processEvents()
        assert widget.plotter.camera_position == camera
        assert widget.plotter.camera.parallel_scale == scale
    finally:
        widget.close()
