"""Refresh ordering and real VTK actors across load edits and deletion."""

from __future__ import annotations

import pyvista as pv
import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QWidget

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.refresh import RefreshContext, RefreshCoordinator
from morphopt.ui.visualization.scene import ArrowLoad, CouplingLoad, MarkerLoad


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_refresh_coalesces_changes_without_losing_an_unknown_source(app):
    problem = ProblemLibrary.create_blank()
    prepared = []
    received = []

    def prepare(changes):
        prepared.append(changes)
        return RefreshContext(
            problem, changed_nodes=tuple(n for n in changes if n is not None),
            full=None in changes,
        )

    class Component:
        def __init__(self, name):
            self.name = name

        def refresh_ui(self, context):
            received.append((self.name, context))

    coordinator = RefreshCoordinator(prepare)
    coordinator.set_components([Component("tree"), Component("editor"), Component("preview")])
    coordinator.request(problem.steps)
    coordinator.request()
    coordinator.request(problem.loads)
    coordinator.flush()

    assert len(prepared) == 1
    assert prepared[0] == (problem.steps, None, problem.loads)
    assert [name for name, _ in received] == ["tree", "editor", "preview"]
    assert all(context is received[0][1] for _, context in received)
    assert received[0][1].geometry_changed
    coordinator.flush()
    assert len(prepared) == 1


def test_refresh_reports_failure_and_still_updates_other_components(app, caplog):
    problem = ProblemLibrary.create_blank()
    visited = []
    failed = []

    class BrokenComponent:
        def refresh_ui(self, context):
            raise ValueError("invalid legend location")

    class OtherComponent:
        def refresh_ui(self, context):
            visited.append(context.problem)

    coordinator = RefreshCoordinator(lambda changes: RefreshContext(problem))
    coordinator.set_components([BrokenComponent(), OtherComponent()])
    coordinator.failed.connect(lambda component, error: failed.append(error))
    coordinator.refresh_now()

    assert visited == [problem]
    assert len(failed) == 1
    assert "invalid legend location" in caplog.text


def test_source_generation_does_not_rebind_a_synchronized_model(monkeypatch):
    from morphopt.ui.codegen.generator import generate_source

    problem = ProblemLibrary.create("shapeopt")

    def forbid_rebinding():
        raise AssertionError("A refresh component must only read the synchronized model")

    monkeypatch.setattr(problem, "resolve_references", forbid_rebinding)
    source = generate_source(problem)
    compile(source, "<read-only source refresh>", "exec")


@pytest.fixture
def workbench_with_vtk(app, monkeypatch):
    from morphopt.ui import workbench
    from morphopt.ui.widgets import viewer

    class OffscreenHost(QWidget):
        """Use real PyVista actors without requiring a Qt OpenGL widget."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.plotter = pv.Plotter(off_screen=True, window_size=(400, 400))

    monkeypatch.setattr(viewer, "_PlotHost", OffscreenHost)
    problem = ProblemLibrary.create("shapeopt")
    window = workbench.Workbench(problem)
    failures = []
    window.refresh_coordinator.failed.connect(lambda component, error: failures.append(error))
    yield window, failures
    window.viewer.host.plotter.close()
    window.close()


def test_deleting_couple_preserves_other_loads_step_and_camera(workbench_with_vtk, monkeypatch):
    window, failures = workbench_with_vtk
    problem, viewer = window.problem, window.viewer
    pressure = next(n for n in problem.interfaces() if n.interface_type == "Pressure")
    couple = next(n for n in problem.interfaces() if n.interface_type == "Couple")
    problem.steps.num_steps = 2
    problem.steps.step_values.append({pressure: [0.04]})
    window.refresh_coordinator.refresh_now(problem.steps)
    viewer.step_combo.setCurrentIndex(viewer.step_combo.findData(1))
    viewer.host.plotter.camera_position = [(150, -100, 80), (0, 0, 35), (0, 0, 1)]
    camera = viewer.host.plotter.camera_position
    base_actors = {
        item.options["name"]: viewer.host.plotter.renderer.actors[item.options["name"]]
        for _, _, item in viewer.geometry.scene.base_meshes
    }
    assert viewer.renderer._overlay_actors
    assert any(isinstance(item, CouplingLoad) for item in viewer.loads.build(viewer.geometry, 1).items)
    rendered = []
    draw_loads = viewer.renderer.draw_loads

    def record_loads(scene):
        rendered.append(scene)
        draw_loads(scene)

    monkeypatch.setattr(viewer.renderer, "draw_loads", record_loads)
    window._on_node_selected(couple)
    window.actions.remove_interface(couple)
    window.refresh_coordinator.flush()

    assert not failures
    assert couple not in problem.interfaces()
    assert pressure in problem.steps.step_values[0]
    assert pressure in problem.steps.step_values[1]
    assert viewer.step_combo.currentData() == 1
    assert viewer.host.plotter.camera_position == camera
    assert all(viewer.host.plotter.renderer.actors[name] is actor for name, actor in base_actors.items())
    items = rendered[-1].items
    assert not any(isinstance(item, CouplingLoad) for item in items)
    assert any(isinstance(item, ArrowLoad) and pressure.name in item.label for item in items)
    assert any(isinstance(item, MarkerLoad) and item.is_reference_point for item in items)
    assert all(actor in viewer.host.plotter.renderer.actors.values() for actor in viewer.renderer._overlay_actors)
    assert set(window.loads_editor._node_editors) == set(problem.interfaces())

    # Exercise a full scene rebuild too: a bad legend location used to raise
    # after drawing geometry and prevent every load from being drawn.
    window.refresh_coordinator.refresh_now()
    assert not failures
    assert viewer.step_combo.currentData() == 1
    assert viewer.host.plotter.camera_position == camera
    assert any(isinstance(item, ArrowLoad) for item in rendered[-1].items)
    assert viewer.renderer._overlay_actors
    assert all(actor in viewer.host.plotter.renderer.actors.values() for actor in viewer.renderer._overlay_actors)


def test_load_edit_preserves_editor_and_tree_state(workbench_with_vtk):
    window, failures = workbench_with_vtk
    problem = window.problem
    pressure = next(n for n in problem.interfaces() if n.interface_type == "Pressure")
    window._on_node_selected(problem.loads)
    editor = window.loads_editor._node_editors[pressure][0]
    geometry_item = window.tree._node_item[problem.geometry]
    geometry_item.setExpanded(False)
    window.loads_editor._on_node_changed(pressure)
    window.refresh_coordinator.flush()

    assert not failures
    assert window.loads_editor._node_editors[pressure][0] is editor
    assert window.tree._item_node[window.tree.currentItem()] is pressure
    assert not window.tree._node_item[problem.geometry].isExpanded()
    assert set(window.loads_editor._node_editors) == set(problem.interfaces())

    # A canonical reference can change while the list of choices stays the
    # same. Refresh the selection too, without writing it back to the model.
    changed = QSignalSpy(window.loads_editor.changed)
    control = editor._controls["instance_name"]
    assert problem.set_interface_reference(pressure, "instance_name", None)
    window.refresh_coordinator.refresh_now(pressure)
    assert control.currentData() == ""
    assert changed.count() == 0
