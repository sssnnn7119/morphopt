"""Global visualization preferences and the shared viewport controls."""

from dataclasses import replace

import numpy as np
import pyvista as pv
import pytest
from PySide6.QtCore import QSettings
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
