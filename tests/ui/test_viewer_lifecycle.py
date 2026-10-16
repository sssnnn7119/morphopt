"""Qt preview lifecycle tests without creating a native OpenGL context."""

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
        def __init__(self, parent=None):
            super().__init__(parent)
            self.plotter = Plotter(self)

    class Renderer:
        def __init__(self, _plotter):
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

    monkeypatch.setattr(viewer_module, "_PlotHost", PlotHost)
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
