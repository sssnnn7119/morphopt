"""The common history-export lifecycle with real worker subprocesses."""

from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image
import pytest
from PySide6.QtGui import QColor
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from morphopt.ui.i18n import tr
from morphopt.ui.widgets import history_export
from morphopt.ui.widgets.file_dialogs import SaveFileSelection


@pytest.fixture
def export_ui(monkeypatch):
    app = QApplication.instance() or QApplication([])
    messages, errors = [], []
    monkeypatch.setattr(
        QMessageBox, "information", lambda parent, title, message: messages.append(message)
    )
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: errors.append(dialog.detailedText()))
    return app, messages, errors


def wait_for_export(app, dialog):
    deadline = time.monotonic() + 45
    while dialog._active and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert not dialog._active
    assert dialog._process.state() == QProcess.ProcessState.NotRunning


def export_dialog(archive, target=None):
    from morphopt.ui.application.results import ResultSession

    session = ResultSession()
    session.load_iteration(str(archive.folder), 2)
    return history_export.HistoryExportDialog(
        session, 2, {}, (150, 150),
        {"background": "white", "deformation_color": "blue",
         "geometry_color": "blue", "boundary_shell_opacity": 0.4,
         "mesh_ambient": 0.2, "mesh_diffuse": 0.7, "mesh_specular": 0.2, "mesh_specular_power": 30},
        initial_target=target,
    )


def test_component_owned_format_reaches_ui_and_archive(export_ui, design_archive, tmp_path, monkeypatch):
    geometry = design_archive.controller_class.Params.GeometryParams

    class ReportPart(geometry.BoundaryPart):
        export_modes = (*geometry.BoundaryPart.export_modes, "report")

        def export(self, directory, *, mode="all_surfaces"):
            if mode == "report":
                (directory / "summary.txt").write_text(self.name, encoding="utf-8")
            else:
                super().export(directory, mode=mode)

    monkeypatch.setattr(geometry, "BoundaryPart", ReportPart)
    dialog = export_dialog(design_archive)
    dialog.tabs.setCurrentIndex(1)
    dialog.component_mode.setCurrentIndex(dialog.component_mode.findData("report"))
    monkeypatch.setattr(history_export, "choose_save_directory", lambda *args: str(tmp_path / "report"))
    captured = {}
    monkeypatch.setattr(dialog, "_start", lambda request, destination: captured.update(request))
    dialog.export.click()
    from morphopt.postprocess import export_design_components
    paths = export_design_components(str(design_archive.folder), 2, str(tmp_path), captured["selections"])
    assert paths == [tmp_path / "body" / "summary.txt"]
    assert paths[0].read_text(encoding="utf-8") == "body"
    dialog.reject()


def test_simp_voxel_settings_reach_archived_obj(export_ui, tmp_path, monkeypatch):
    import shutil
    import pyvista as pv
    import torch
    from morphopt.optcore.history import History
    from morphopt.postprocess import OptimizationArchive, cpu_torch_defaults

    app, _, errors = export_ui
    archive = OptimizationArchive(tmp_path / "run")
    scripts = archive.folder / "scripts"
    scripts.mkdir(parents=True)
    example = Path(__file__).resolve().parents[2] / "examples/simp_gripper/simp_gripper.py"
    shutil.copyfile(example, scripts / "MAIN_SCRIPT_FOR_RESTART.py")
    with cpu_torch_defaults():
        material = archive.initialize_params().materials.interface("body")
        controls = material.get_parameters()[0].reshape(material.simp_field.size)
        controls.fill_(0.4)
        controls[:controls.shape[0] // 2] = 2.0
        material.set_parameters([controls])
        material.save(str(archive.log_folder), 2)
    history = History()
    history.append(objective=1.0)
    history.append(objective=0.9)
    history.save(foldpath=str(archive.log_folder))

    destination = tmp_path / "export"
    monkeypatch.setattr(history_export, "choose_save_directory", lambda *args: str(destination))
    dialog = export_dialog(archive)
    dialog.tabs.setCurrentIndex(1)
    assert not dialog.component_form.isRowVisible(dialog.voxel_size)
    dialog.component_mode.setCurrentIndex(dialog.component_mode.findData("voxel_obj"))
    assert dialog.component_form.isRowVisible(dialog.voxel_threshold)
    dialog.voxel_size.setValue(2.0)
    dialog.voxel_threshold.setValue(0.7)
    dialog.export.click()
    wait_for_export(app, dialog)
    assert not errors, errors
    mesh = pv.read(destination / "body" / "voxels.obj")
    # Only the high-density half of the 80-unit gripper remains, on a 2-unit X grid.
    x = np.unique(mesh.points[:, 0])
    assert 38 <= x[-1] <= 42
    np.testing.assert_array_equal(np.diff(x), 2)


def test_mixed_boundary_writes_step_and_stl_together(export_ui, design_archive, tmp_path, monkeypatch):
    import gmsh
    import pyvista as pv
    from torchfea import cad
    from morphopt.postprocess import OptimizationArchive, cpu_torch_defaults, export_design_components

    geometry = design_archive.controller_class.Params.GeometryParams

    class MixedPart(geometry.BoundaryPart):
        def define_surfaces(self):
            super().define_surfaces()
            mesh = pv.Tetrahedron()
            self.add_surface_interface(self.MeshSurface(mesh.points, mesh.regular_faces))
            for _ in range(2):
                self.add_surface_interface(self.CPGEO.initialize_cylinder(2, 4, 1))

    monkeypatch.setattr(geometry, "BoundaryPart", MixedPart)
    with cpu_torch_defaults():
        part = OptimizationArchive(design_archive.folder).initialize_params().geometry.interface("body")
        for index in (3, 4):
            cpgeo = part.surface_interface(index)
            offset = cpgeo.control_points.new_tensor([index, 0, 0])
            cpgeo.set_surface_parameters(cpgeo.control_points + offset)
            cpgeo.save(design_archive.log_folder / part.pathlog_required()[0] / "body" / f"Surface-{index}_iter-1")

    dialog = export_dialog(design_archive)
    dialog.tabs.setCurrentIndex(1)
    choices = dialog.surface_choices
    assert [c.currentData() for c in choices] == ["stp", "stp", "stl", "stl", "stl"]
    assert [c.count() for c in choices] == [2, 1, 1, 2, 2]
    choices[0].setCurrentIndex(choices[0].findData("stl"))
    choices[4].setCurrentIndex(choices[4].findData("stp"))
    request = {}
    destination = tmp_path / "mixed"
    monkeypatch.setattr(dialog, "_start", lambda data, destination: request.update(data))
    monkeypatch.setattr(history_export, "choose_save_directory", lambda *args: str(destination))
    dialog.export.click()
    paths = export_design_components(
        str(design_archive.folder), request["iteration"], str(destination), request["selections"]
    )
    assert {path.name for path in paths} == {
        "surface_0.stl", "surface_1.stp", "surface_2.stl", "surface_3.stl", "surface_4.stp",
    }
    assert pv.read(destination / "body" / "surface_0.stl").n_cells > 0
    assert pv.read(destination / "body" / "surface_2.stl").n_cells == 4
    mesh = pv.read(destination / "body" / "surface_3.stl")
    assert mesh.n_open_edges == 0 and mesh.n_cells > 0
    assert mesh.center[0] == pytest.approx(3, abs=0.2)
    with cad.occ_session("import_cpgeo_step") as context:
        (volume,) = context.occ.importShapes(str(destination / "body" / "surface_4.stp"))
        context.occ.synchronize()
        assert volume[0] == 3 and len(gmsh.model.getBoundary([volume])) == 6
        assert context.occ.getCenterOfMass(*volume)[0] == pytest.approx(4, abs=0.2)
    dialog.reject()


def test_surface_export_retries_after_worker_failure_and_cleans_requests(
    export_ui, design_archive, tmp_path, monkeypatch
):
    app, messages, errors = export_ui
    destination = tmp_path / "surfaces"
    monkeypatch.setattr(history_export, "choose_save_directory", lambda *args: str(destination))
    start_worker = history_export.start_worker

    def fail(process, request):
        process.start(sys.executable, ["-c", "import sys; print('export failure'); sys.exit(2)"])

    monkeypatch.setattr(history_export, "start_worker", fail)
    dialog = export_dialog(design_archive)
    dialog.tabs.setCurrentIndex(1)
    dialog.export.click()
    first_directory = dialog._directory
    wait_for_export(app, dialog)
    assert errors and "export failure" in errors[0]
    assert first_directory.exists()
    assert dialog.tabs.isEnabled() and dialog.export.isEnabled()
    assert not destination.exists()
    monkeypatch.setattr(history_export, "start_worker", start_worker)
    dialog.export.click()
    directory = dialog._directory
    assert directory == first_directory
    wait_for_export(app, dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert len(messages) == 1 and len(errors) == 1
    assert not directory.exists()
    assert {path.name for path in destination.rglob("*.stp")} == {"surface_0.stp", "surface_1.stp"}


@pytest.mark.parametrize("pitch", [30, 90, -90])
def test_gif_pose_editor(export_ui, deformation_archive, pitch):
    app, _, _ = export_ui
    dialog = export_dialog(deformation_archive, {"case": "case"})
    dialog.show()
    app.processEvents()
    gif = dialog.gif
    try:
        camera = gif.viewport.plotter.camera
        distance = camera.distance
        for field, value in zip(gif.position, (12, -5, 7)):
            assert field.isVisible() and not field.prefix() and not field.suffix()
            field.setValue(value)
        for field, value in zip(gif.angles, (90, pitch, 90)):
            assert field.isVisible() and not field.prefix() and not field.suffix()
            field.setValue(value)
        app.processEvents()
        np.testing.assert_allclose(camera.position, (12, -5, 7))
        np.testing.assert_allclose(camera.direction, (0, np.cos(np.radians(pitch)), np.sin(np.radians(pitch))), atol=1e-12)
        np.testing.assert_allclose(camera.up, (1, 0, 0), atol=1e-12)
        np.testing.assert_allclose([field.value() for field in gif.angles], (90, pitch, 90))
        assert camera.distance == pytest.approx(distance)
        for parallel in (True, False):
            gif.projection.setCurrentIndex(gif.projection.findData(parallel))
            options = gif.options()["camera"]
            assert options["parallel_projection"] is parallel
            np.testing.assert_allclose(options["position"][0], (12, -5, 7))
    finally:
        dialog.reject()


def test_gif_preview_matches_export(export_ui, deformation_archive, tmp_path, monkeypatch):
    app, messages, errors = export_ui
    output = tmp_path / "history.gif"
    monkeypatch.setattr(
        history_export, "choose_save_file", lambda *args: SaveFileSelection(output, "gif")
    )
    dialog = export_dialog(deformation_archive, {"case": "case"})
    dialog.show()

    app.processEvents()
    gif = dialog.gif
    plotter = gif.viewport.plotter
    assert gif.error.isHidden(), gif.error.text()
    assert plotter.renderer.axes_widget is not None
    if plotter.iren is not None:
        assert plotter.renderer.axes_enabled
    assert not any(actor.IsA("vtkCornerAnnotation") or actor.IsA("vtkTextActor")
                   for actor in plotter.renderer.GetActors2D())
    gif.resolution_preset.setCurrentIndex(gif.resolution_preset.count() - 1)
    assert gif.pixel_width.isVisible() and gif.pixel_height.isVisible()
    gif.pixel_width.setValue(120)
    gif.pixel_height.setValue(180)
    assert gif.options()["window_size"] == (120, 180)
    app.processEvents()
    assert abs(gif.viewport.width() - gif.viewport.height() * 2 / 3) <= 1

    assert not gif.view_height.isVisible()
    gif.projection.setCurrentIndex(gif.projection.findData(True))
    app.processEvents()
    assert gif.view_height.isVisible()
    gif.view_height.setValue(30)
    assert gif.options()["camera"]["parallel_scale"] == 15
    direction = plotter.camera.direction
    gif.fit_button.click()
    app.processEvents()
    assert 0 < gif.view_height.value() < 30
    assert gif.view_height.value() == pytest.approx(2 * plotter.camera.parallel_scale)
    np.testing.assert_allclose(plotter.camera.direction, direction)
    last_points = plotter.actors["deformation-mesh"].mapper.dataset.points.copy()
    initial_pose = gif.options()["camera"]["position"]
    initial_angles = [field.value() for field in gif.angles]
    if plotter.iren is None:  # Offscreen VTK has no mouse interactor.
        plotter.camera.azimuth = 43
    else:
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        center = plotter.rect().center()
        end = center + QPoint(49, 22)
        QTest.mousePress(plotter, Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(plotter, end, delay=20)
        app.processEvents()
        assert [field.value() for field in gif.angles] != initial_angles
        np.testing.assert_allclose([field.value() for field in gif.position], plotter.camera.position, atol=1e-6)
        QTest.mouseRelease(plotter, Qt.MouseButton.LeftButton, pos=end)
    assert gif.options()["camera"]["position"] != initial_pose
    plotter.camera.zoom(1.2)
    camera = gif.options()["camera"]
    gif.last.setValue(1)
    app.processEvents()
    assert not np.array_equal(plotter.actors["deformation-mesh"].mapper.dataset.points, last_points)
    for key, value in gif.options()["camera"].items():
        np.testing.assert_allclose(value, camera[key])
    gif.last.setValue(2)
    monkeypatch.setattr(history_export.QColorDialog, "getColor", lambda *args: QColor("#e6c888"))
    gif.background.click()
    app.processEvents()
    for key, value in gif.options()["camera"].items():
        np.testing.assert_allclose(value, camera[key])
    from morphopt.postprocess.visualization import history_frames
    frames = history_frames(gif.archive, range(2, 3), mode="deformation", target={"case": "case"},
                            camera=camera, window_size=(120, 180), style=gif.style)
    last_preview, = frames
    np.testing.assert_array_equal(last_preview[-1, 0], [230, 200, 136])
    dialog.export.click()
    directory = dialog._directory
    wait_for_export(app, dialog)
    assert not errors, errors
    assert messages == [tr("ui.history_export.completed", path=str(output))]
    with Image.open(output) as animation:
        assert animation.size == (120, 180)
        assert animation.n_frames == 2
        for index in range(animation.n_frames):
            animation.seek(index)
            frame = np.asarray(animation.convert("RGB"), dtype=float)
            np.testing.assert_allclose(frame[-1, 0], last_preview[-1, 0], atol=2)
        assert np.abs(frame - last_preview).mean() < 2
    assert not directory.exists()


def test_cancelling_gif_removes_partial_file_and_preserves_existing_output(
    export_ui, deformation_archive, tmp_path, monkeypatch
):
    app, messages, errors = export_ui
    output = tmp_path / "history.gif"
    output.write_bytes(b"existing animation")
    partial = output.with_name(".history.partial.gif")
    monkeypatch.setattr(
        history_export, "choose_save_file", lambda *args: SaveFileSelection(output, "gif")
    )
    monkeypatch.setattr(
        history_export, "start_worker",
        lambda process, request: process.start(sys.executable, ["-c", "import time; time.sleep(30)"]),
    )
    dialog = export_dialog(deformation_archive)
    dialog.export.click()
    directory = dialog._directory
    assert dialog._process.waitForStarted(1000)
    partial.write_bytes(b"incomplete animation")
    dialog.reject()
    app.processEvents()
    assert dialog._process.state() == QProcess.ProcessState.NotRunning
    assert not dialog._active
    assert not directory.exists() and not partial.exists()
    assert output.read_bytes() == b"existing animation"
    assert not messages and not errors


def test_abaqus_export_uses_selected_iteration_and_case(export_ui, deformation_archive, tmp_path, monkeypatch):
    app, messages, errors = export_ui
    output = tmp_path / "case.inp"
    monkeypatch.setattr(history_export, "choose_save_file", lambda *args: SaveFileSelection(output, "inp"))
    dialog = export_dialog(deformation_archive)
    dialog.tabs.setCurrentIndex(2)
    assert dialog.inp_case.currentText() == "case"
    dialog.inp_step.setCurrentIndex(0)
    dialog.nlgeom.setChecked(False)
    dialog.export.click()
    wait_for_export(app, dialog)
    assert not errors, errors
    deck = output.read_text().lower()
    assert "*node" in deck and "*element" in deck and "*static" in deck
    assert "*end step" in deck and "nlgeom=yes" not in deck


def test_mesh_export_without_case_result(export_ui, deformation_archive, tmp_path, monkeypatch):
    app, _, errors = export_ui
    deformation_archive.fea_result_path("case", 2).unlink()
    output = tmp_path / "mesh.inp"
    monkeypatch.setattr(history_export, "choose_save_file", lambda *args: SaveFileSelection(output, "inp"))
    dialog = export_dialog(deformation_archive)
    dialog.tabs.setCurrentIndex(2)
    assert not dialog.export.isEnabled()
    dialog.inp_kind.setCurrentIndex(dialog.inp_kind.findData("parts"))
    assert dialog.export.isEnabled()
    assert not dialog.inp_form.isRowVisible(dialog.inp_case)
    dialog.export.click()
    wait_for_export(app, dialog)
    assert not errors, errors
    deck = output.read_text().lower()
    assert "*part" in deck and "*node" in deck and "*element" in deck and "*end part" in deck
    assert "*step" not in deck
