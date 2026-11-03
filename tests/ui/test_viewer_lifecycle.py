"""Qt preview lifecycle tests without creating a native OpenGL context."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.widgets import viewer as viewer_module


def test_viewer_defers_vtk_scene_render_until_the_widget_is_shown(monkeypatch):
    app = QApplication.instance() or QApplication([])
    rendered = []

    class Plotter(QWidget):
        camera_position = ((1.0, 1.0, 1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))

        def show_axes(self):
            pass

        def view_isometric(self):
            pass

        def reset_camera(self):
            pass

    class PlotHost(QWidget):
        viewChanged = Signal()
        def __init__(self, parent=None):
            super().__init__(parent)
            self.plotter = Plotter(self)

    class Renderer:
        section_position = None

        def __init__(self, _plotter, **_kwargs):
            pass

        def draw_scene(self, _scene):
            rendered.append("scene")

        def draw_loads(self, _scene):
            rendered.append("loads")

    class Geometry:
        def build(self, *_args):
            rendered.append("build")
            return object()

    class Loads:
        def build(self, *_args):
            return None

    monkeypatch.setattr(viewer_module, "PlotViewport", PlotHost)
    monkeypatch.setattr(viewer_module, "PreviewRenderer", Renderer)
    widget = viewer_module.PreviewViewer(geometry=Geometry(), loads=Loads())

    widget.set_problem(ProblemLibrary.create_blank())

    assert widget._render_pending
    assert rendered == []

    widget.show()
    app.processEvents()

    assert not widget._render_pending
    assert rendered == ["build", "scene", "loads", "loads"]
    widget.close()


def test_result_viewport_keeps_latest_scene_until_visible_and_redraws_on_return(monkeypatch):
    from morphopt.ui.widgets import viewport as pages
    import pyvista as pv

    app = QApplication.instance() or QApplication([])
    events = []

    class Plotter:
        def __init__(self, parent, *, auto_update):
            assert auto_update is False
            self.interactor = QWidget(parent)
            self.camera = pv.Camera()

        def clear(self):
            events.append("clear")

        def view_isometric(self, *, render):
            events.append("camera")

        def reset_camera_clipping_range(self):
            pass

        def render(self):
            events.append("render")

    monkeypatch.setattr(pages, "QtInteractor", Plotter)
    monkeypatch.setattr(pages, "configure_plotter", lambda *args, **kwargs: None)
    monkeypatch.setattr(pages, "apply_visualization", lambda *args: None)
    widget = pages.PlotViewport()
    widget.rebuild(lambda _: events.append("old run"))
    widget.rebuild(lambda _: events.append("new run: outer + inner"))
    assert not events
    widget.show()
    app.processEvents()
    assert events == ["clear", "new run: outer + inner", "camera", "render"]
    widget.hide()
    app.processEvents()
    widget.show()
    app.processEvents()
    assert events[-1] == "render"
    assert events.count("new run: outer + inner") == 1
    widget.hide()
    widget.rebuild(lambda _: events.append("reset"))
    widget.rebuild(lambda _: events.append("edited run: outer + inner"))
    widget.show()
    app.processEvents()
    assert "reset" not in events
    assert events[-2:] == ["edited run: outer + inner", "render"]
    widget.close()


def test_test_morph_keeps_both_surface_actors_across_result_switches(tmp_path, monkeypatch):
    from pathlib import Path
    import runpy
    from types import SimpleNamespace
    import numpy as np
    import pyvista as pv
    from morphopt.ui.widgets import observation_pages as pages
    from morphopt.ui.visualization.rendering import configure_plotter

    app = QApplication.instance() or QApplication([])
    definition = ProblemLibrary.load(Path(__file__).resolve().parents[2] / "examples/bending_actuator/bending_actuator.morph")
    script = ProblemLibrary.export_python_bundle(definition, tmp_path / "case")
    namespace = runpy.run_path(str(script), run_name="result_surface_regression")

    def result(folder):
        geometry = namespace["ThisController"].Params.GeometryParams()
        geometry.initialize()
        part = next(iter(geometry.interfaces.values()))
        return SimpleNamespace(folder=folder, params=object(),
                               fea_components=lambda: (("Part", part),),
                               load_parameters=lambda iteration: None)

    class Viewport(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.plotter = pv.Plotter(off_screen=True, window_size=(400, 400))

        def rebuild(self, build_scene):
            self.plotter.clear()
            configure_plotter(self.plotter)
            build_scene(self.plotter)

    monkeypatch.setattr(pages, "PlotViewport", Viewport)
    page = pages.UpdatableStructurePage()
    try:
        for folder in ("first", "edited", "first", "edited"):
            page.build(result(folder), 1)
            actors = {name: actor for name, actor in page.viewport.plotter.actors.items()
                      if str(name).startswith("boundary:")}
            assert len(actors) == 2
            assert {str(name).rsplit("surface-", 1)[1] for name in actors} == {"0", "1"}
            assert all(actor.visibility and actor.mapper.dataset.n_points > 0 for actor in actors.values())
            outer = next(actor for name, actor in actors.items() if name.endswith("surface-0"))
            assert 0 < outer.prop.opacity < 1
            assert not page.viewport.plotter.renderer.GetUseDepthPeeling()
            assert page.viewport.plotter.renderer.GetUseOIT()
            page.viewport.plotter.reset_camera()
            both = page.viewport.plotter.screenshot(return_img=True)
            outer.visibility = False
            page.viewport.plotter.render()
            inner_only = page.viewport.plotter.screenshot(return_img=True)
            outer.visibility = True
            page.viewport.plotter.render()
            # Actor presence alone is insufficient: the translucent shell
            # must actually contribute pixels after each result switch.
            assert np.count_nonzero(np.any(both != inner_only, axis=2)) > 100
    finally:
        page.viewport.plotter.close()
        page.close()
