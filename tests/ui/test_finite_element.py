from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import pytest
import torch
import torchfea

from morphopt.postprocess import (
    FiniteElementResults,
    IterationModel,
    cpu_torch_defaults,
    export_fields,
)
from morphopt.ui.application import OptimizationRunSession, ProblemLibrary
from morphopt.ui.application.finite_element import FiniteElementSession
from morphopt.ui.application.results import ResultSelection


def test_analysis_worker_changes_loads_without_changing_optimization(iteration_model):
    source, _, original_result = iteration_model
    original_hash = hashlib.sha256(source.model_path.read_bytes()).digest()
    session = FiniteElementSession()
    try:
        session.import_iteration(source)
        assert IterationModel.iterations(source.folder) == (3,)
        assert source.cases() == ("0",)
        session.apply_loads({"body_force": (True, [0.004, 0.0, 0.0])})
        request = session.solve_request()
        process = subprocess.run(
            [sys.executable, "-m", "morphopt.ui.worker", str(request)],
            capture_output=True,
            timeout=45,
        )
        assert process.returncode == 0, process.stderr.decode()
        session.accept_solution()
        assert session.result.GC.abs().max() > original_result.GC.abs().max()
        assert hashlib.sha256(source.model_path.read_bytes()).digest() == original_hash
        assert session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(0.004)
        with pytest.raises(ValueError):
            session.apply_loads({"body_force": (False, [float("nan"), 0.0, 0.0])})
        assert session.load_values()[0][3] is True
        destination = session.directory / "chosen_data.npz"
        request = session.export_request(
            str(destination), "npz", ["energy", "stress", "strain"], location="elements"
        )
        process = subprocess.run(
            [sys.executable, "-m", "morphopt.ui.worker", str(request)],
            capture_output=True,
            timeout=45,
        )
        assert process.returncode == 0, process.stderr.decode()
        with np.load(destination, allow_pickle=False) as archive:
            manifest = json.loads(str(archive["__metadata__"]))
            assert archive["S_Mises"].shape == (64,)
        assert len(manifest["fields"]) == 3
        assert manifest["source"]["iteration"] == 3
    finally:
        session.close()


def test_extension_labels_use_field_descriptions_and_format_names():
    from morphopt.ui.presentation.result_fields import export_format_label, field_label

    assert field_label("custom_field", "Custom physical field") == "Custom physical field"
    assert export_format_label("xyz") == "XYZ (*.xyz)"


def test_result_options_keep_sparse_original_cases_and_separate_model_contexts(
    iteration_model, tmp_path
):
    source, _, original_result = iteration_model
    session = FiniteElementSession()
    try:
        with cpu_torch_defaults():
            controller = torchfea.load_model(str(source.model_path))
            controller.assembly._loads["body_force"]._parameters *= 2
            another_case = controller.solve(if_initialize=False)
            assert another_case.converged
            another_case.save(str(source.model_path.parent / "result_7_iter_3.npz"))
        options = session.result_options(source.folder, source.iteration)
        assert [entry.source.case for entry in options] == ["0", "7"]
        session.select_result(options[1])
        assert session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(0.004)
        assert torch.allclose(session.result.GC, another_case.GC)
        session.select_result(options[0])
        assert session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(0.002)
        assert torch.allclose(session.result.GC, original_result.GC)

        shutil.copyfile(source.model_path, session.directory / "solved_model.npz")
        shutil.copyfile(options[0].result_path, session.directory / "result.npz")
        entry = session.accept_solution("first solve log")
        assert session.result_options(source.folder, 3)[-1] == entry
        assert all(
            item.is_original for item in session.result_options(source.folder, 4)
        )
        assert all(
            item.is_original
            for item in session.result_options(str(tmp_path / "other"), 3)
        )
        # An invalid or unconverged worker result must not create a new option.
        with cpu_torch_defaults():
            rejected = torchfea.solver.StaticResult.load(str(entry.result_path))
            rejected.converged = False
            rejected.save(str(session.directory / "result.npz"))
        with pytest.raises(ValueError):
            session.accept_solution()
        assert len(session.result_options(source.folder, 3)) == 3
        session.select_result(entry)
        assert session.result.converged
        assert entry.log_path.read_text() == "first solve log"
        assert torch.allclose(session.result.GC, original_result.GC)
    finally:
        session.close()


def test_staging_another_definition_does_not_stop_or_mutate_active_run(
    monkeypatch, tmp_path
):
    from morphopt.ui import launcher

    original = ProblemLibrary.create_blank("original")
    process = object()
    monkeypatch.setattr(launcher, "run_job", lambda problem: ("job.py", process))
    monkeypatch.setattr(launcher, "run_root_for", lambda problem: str(tmp_path))
    monkeypatch.setattr(
        launcher,
        "stop_job",
        lambda process: pytest.fail("staging stopped an active job"),
    )
    session = OptimizationRunSession()
    session.set_definition(original)
    session.start_definition(session.definition)
    original.label = "edited outside observer"
    session.set_definition(ProblemLibrary.create_blank("next run"))
    assert session.process is process
    assert session.definition.label == "next run"
    assert session._running_definition.label == "original"


def test_fea_widget_solves_and_exports_after_being_hidden(
    iteration_model, monkeypatch, tmp_path
):
    from PySide6.QtWidgets import QApplication, QWidget

    from morphopt.ui.widgets import finite_element

    app = QApplication.instance() or QApplication([])

    class Viewport(QWidget):
        def rebuild(self, build):
            pass

        def apply_theme(self):
            pass

    monkeypatch.setattr(finite_element, "PlotViewport", Viewport)
    source, _, original_result = iteration_model
    page = finite_element.FiniteElementPage()
    try:
        page.import_iteration(source.folder, source.iteration)
        assert page.cases.count() == 1
        original_entry = page.cases.currentData()
        assert original_entry.is_original
        assert page.loads.rowCount() == 1
        assert page.loads.item(0, 2).text() == "body-1 · C3D8"
        page.loads.item(0, 3).setText("0.004, 0, 0")
        assert page.session.result is None
        # Returning from the observer at the same iteration must retain edits.
        edited_model = page.session.controller
        page.synchronize_result(source.folder, source.iteration)
        assert page.session.controller is edited_model
        assert page.loads.item(0, 3).text() == "0.004, 0, 0"
        page.start_analysis()
        page.hide()

        def wait_for_job():
            deadline = time.monotonic() + 45
            while page.is_running() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            app.processEvents()
            assert not page.is_running(), page.output.toPlainText()

        wait_for_job()
        assert page.session.result is not None, page.output.toPlainText()
        assert page.session.result.GC.abs().max() > original_result.GC.abs().max()
        assert page.cases.count() == 2
        first_entry = page.cases.currentData()
        assert first_entry.number == 1
        first_gc = page.session.result.GC.clone()
        assert "FEA completed." in first_entry.log_path.read_text()
        page.synchronize_result(source.folder, source.iteration)
        assert page.cases.currentData() == first_entry
        assert torch.allclose(page.session.result.GC, first_gc)
        page.loads.item(0, 3).setText("0.006, 0, 0")
        page.start_analysis()
        wait_for_job()
        assert page.cases.count() == 3
        second_entry = page.cases.currentData()
        assert second_entry.number == 2
        second_gc = page.session.result.GC.clone()
        assert second_gc.abs().max() > first_gc.abs().max()

        # Selecting a case restores its model, loads, solution, and own solver log.
        page.cases.setCurrentIndex(page._result_index(original_entry))
        assert page.session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(0.002)
        assert torch.allclose(page.session.result.GC, original_result.GC)
        page.cases.setCurrentIndex(page._result_index(first_entry))
        assert page.session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(0.004)
        assert torch.allclose(page.session.result.GC, first_gc)
        assert "FEA completed." in page.output.toPlainText()
        page.apply_language()
        assert page.cases.count() == 3
        assert page.cases.currentData() == first_entry
        assert torch.allclose(page.session.result.GC, first_gc)
        from morphopt.ui.widgets.file_dialogs import SaveFileSelection

        choices = iter(
            [
                SaveFileSelection(tmp_path / "chosen_nodes.csv", "csv"),
                SaveFileSelection(tmp_path / "chosen_elements.npz", "npz"),
            ]
        )
        monkeypatch.setattr(
            finite_element, "choose_save_file", lambda *args: next(choices)
        )
        page.export_fields()
        wait_for_job()
        with (tmp_path / "chosen_nodes.csv").open(encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        exported_max = max(
            abs(float(row[component]))
            for row in rows
            for component in ("U1", "U2", "U3")
        )
        assert exported_max == pytest.approx(float(first_gc.abs().max()))
        assert "S_Mises" not in rows[0]
        page.export_location.setCurrentIndex(page.export_location.findData("elements"))
        for key in ("element_coordinates", "gauss_coordinates", "strain"):
            page.field_checks[key].setChecked(False)
        page.export_fields()
        wait_for_job()
        with np.load(tmp_path / "chosen_elements.npz", allow_pickle=False) as data:
            manifest = json.loads(str(data["__metadata__"]))
            assert data["S_Mises"].shape == (64,)
            assert "U1" not in data and "E11" not in data and "X" not in data
            assert {field["key"] for field in manifest["fields"]} == {
                "energy",
                "stress",
            }
            assert manifest["source"]["analysis_number"] == 1
            assert manifest["source"]["result_id"] == first_entry.key
        assert not list(tmp_path.glob("fea_iter_*"))

        # Native export includes every saved result, independent of the selected
        # case, record location or checked CSV/NPZ columns above.
        native_parent = tmp_path / 'native_exports'
        monkeypatch.setattr(finite_element, 'choose_directory', lambda *args: str(native_parent))
        monkeypatch.setattr(finite_element.QInputDialog, 'getText', lambda *args, **kwargs: ('actuator', True))
        page.native_export_button.click()
        assert not page.native_export_button.isEnabled()
        wait_for_job()
        archive = native_parent / 'actuator'
        native_manifest = json.loads((archive / 'actuator_manifest.json').read_text())
        assert [path.name for path in archive.glob('*_femodel.npz')] == ['actuator_femodel.npz']
        assert {path.name for path in archive.glob('*.npz')} == {
            'actuator_femodel.npz', 'actuator_case0.npz', 'actuator_analysis1.npz', 'actuator_analysis2.npz'}
        assert native_manifest['iteration'] == 3
        assert [entry['key'] for entry in native_manifest['results']] == [
            original_entry.key, first_entry.key, second_entry.key]
        assert page.cases.count() == 3
        assert page.cases.currentData() == first_entry
        expected_results = (original_result.GC, first_gc, second_gc)
        with cpu_torch_defaults():
            for entry, expected in zip(native_manifest['results'], expected_results, strict=True):
                model = torchfea.load_model(str(archive / entry['model']))
                result = torchfea.solver.StaticResult.load(str(archive / entry['result']))
                model.assembly.set_work_conditions(result.work_conditions)
                assert result.model_hash == model.get_model_hash()
                assert torch.allclose(result.GC, expected)
        assert str(archive) in page.output.toPlainText()

        # Editing or restoring an original must not mutate previously completed analyses.
        page.cases.setCurrentIndex(page._result_index(second_entry))
        assert torch.allclose(page.session.result.GC, second_gc)
        page.loads.item(0, 3).setText("0.009, 0, 0")
        assert page.session.result is None
        assert page.native_export_button.isEnabled()
        original_files = {path.name: path.read_bytes() for path in archive.glob('*.npz')}
        page.native_export_button.click()
        wait_for_job()
        second_archive = native_parent / 'actuator_2'
        assert {path.name: path.read_bytes() for path in second_archive.glob('*.npz')} == original_files
        assert {path.name: path.read_bytes() for path in archive.glob('*.npz')} == original_files
        assert page.loads.item(0, 3).text() == '0.009, 0, 0'
        assert page.session.result is None
        page.apply_language()
        assert page.loads.item(0, 3).text() == "0.009, 0, 0"
        assert page.session.result is None
        page.cases.setCurrentIndex(page._result_index(original_entry))
        assert page.cases.currentData().is_original
        assert page.session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(0.002)
        page.cases.setCurrentIndex(page._result_index(second_entry))
        assert page.session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(0.006)
        assert torch.allclose(page.session.result.GC, second_gc)
        page.import_iteration(source.folder, source.iteration)
        assert page.cases.count() == 3
        assert page.cases.currentData() == second_entry
    finally:
        page.close_cleanup()
        page.deleteLater()
        app.processEvents()


def test_reference_point_exports_use_solved_six_dof_state(
    iteration_model, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QApplication, QWidget

    from morphopt.ui.widgets import finite_element
    from morphopt.ui.widgets.file_dialogs import SaveFileSelection

    source, controller, _ = iteration_model
    with cpu_torch_defaults():
        for name, position in [
            ("RP_tip", [1.0, 0.5, 0.5]),
            ("RP_base", [0.0, 0.5, 0.5]),
            ("RP_ignored", [2.0, 0.0, 0.0]),
        ]:
            controller.assembly.add_reference_point(
                torchfea.model.ReferencePoint(node=position), name
            )
        controller.assembly.get_reference_point("RP_ignored").enabled = False
        controller.assembly.add_constraint(
            torchfea.constraints.Couple("body-1", "nodes_xmax", "RP_tip"), "tip_couple"
        )
        controller.assembly.add_boundary(
            torchfea.boundarys.Boundary_Condition_RP("RP_base"), "fixed_rp"
        )
        controller.assembly.add_boundary(
            torchfea.boundarys.Boundary_Condition_RP("RP_ignored"), "fixed_ignored"
        )
        controller.assembly.add_load(
            torchfea.loads.Moment("RP_tip", [0.0, 1e-4, 0.0]), "moment"
        )
        controller.initialize()
        result = controller.solve(if_initialize=False)
        assert result.converged
        controller.save_model(str(source.model_path), if_save_source_code=False)
        result.save(str(source.model_path.parent / "result_0_iter_3.npz"))
        state = controller.GC2RGC(result.GC)
        tip = controller.assembly.get_reference_point("RP_tip")
        tip_dofs = state[tip._RGC_index].detach().cpu().numpy().reshape(-1)
        assert np.linalg.norm(tip_dofs[3:]) > 0
    expected_fields = {
        "rp_coordinates",
        "rp_displacement",
        "rp_rotation",
        "rp_deformed_coordinates",
    }
    assert (
        set(FiniteElementResults(controller, result).available_fields("reference_points")) == expected_fields
    )
    path = export_fields(
        controller,
        result,
        tmp_path / "reference_points.csv",
        location="reference_points",
    )
    with path.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["reference_point"] for row in rows] == ["RP_base", "RP_tip"]
    assert [row["reference_point_id"] for row in rows] == ["1", "3"]
    row = rows[1]
    assert [float(row[key]) for key in ("X", "Y", "Z")] == pytest.approx(
        [1.0, 0.5, 0.5]
    )
    assert [float(row[key]) for key in ("U1", "U2", "U3")] == pytest.approx(
        tip_dofs[:3]
    )
    assert [float(row[key]) for key in ("UR1", "UR2", "UR3")] == pytest.approx(
        tip_dofs[3:]
    )
    assert float(row["UR"]) == pytest.approx(np.linalg.norm(tip_dofs[3:]))
    assert float(row["x"]) == pytest.approx(1.0 + tip_dofs[0])
    assert "integration_point" not in row and "instance" not in row
    selected = export_fields(
        controller,
        result,
        tmp_path / "rotation_only.csv",
        location="reference_points",
        fields=["rp_rotation"],
    )
    with selected.open(encoding="utf-8-sig") as stream:
        assert next(csv.reader(stream)) == [
            "reference_point_id",
            "reference_point",
            "UR1",
            "UR2",
            "UR3",
            "UR",
        ]

    app = QApplication.instance() or QApplication([])

    class Viewport(QWidget):
        def rebuild(self, build):
            pass

        def apply_theme(self):
            pass

    monkeypatch.setattr(finite_element, "PlotViewport", Viewport)
    page = finite_element.FiniteElementPage()
    try:
        page.import_iteration(source.folder, source.iteration)
        page.export_location.setCurrentIndex(
            page.export_location.findData("reference_points")
        )
        assert page.export_button.isEnabled()
        assert page.no_reference_points.isHidden()
        assert {
            key for key, check in page.field_checks.items() if not check.isHidden()
        } == expected_fields
        destination = tmp_path / "chosen_rp.npz"
        monkeypatch.setattr(
            finite_element,
            "choose_save_file",
            lambda *args: SaveFileSelection(destination, "npz"),
        )
        page.export_fields()
        deadline = time.monotonic() + 45
        while page.is_running() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        assert not page.is_running(), page.output.toPlainText()
        assert destination.is_file(), page.output.toPlainText()
        with np.load(destination, allow_pickle=False) as data:
            assert data["reference_point"].tolist() == ["RP_base", "RP_tip"]
            assert data["UR2"][1] == pytest.approx(tip_dofs[4])
            assert data["U1"][1] == pytest.approx(tip_dofs[0])
            assert (
                json.loads(str(data["__metadata__"]))["location"] == "reference_points"
            )
    finally:
        page.close_cleanup()
        page.deleteLater()
        app.processEvents()


def test_model_without_reference_points_disables_rp_export(
    iteration_model, monkeypatch, tmp_path
):
    from PySide6.QtWidgets import QApplication, QWidget

    from morphopt.ui.widgets import finite_element

    source, controller, result = iteration_model
    assert FiniteElementResults(controller, result).available_fields("reference_points") == ()
    with pytest.raises(ValueError, match="no data"):
        export_fields(
            controller,
            result,
            tmp_path / "empty_rp.csv",
            location="reference_points",
            fields=["rp_rotation"],
        )
    assert not (tmp_path / "empty_rp.csv").exists()
    app = QApplication.instance() or QApplication([])

    class Viewport(QWidget):
        def rebuild(self, build):
            pass

        def apply_theme(self):
            pass

    monkeypatch.setattr(finite_element, "PlotViewport", Viewport)
    page = finite_element.FiniteElementPage()
    try:
        page.import_iteration(source.folder, source.iteration)
        page.export_location.setCurrentIndex(
            page.export_location.findData("reference_points")
        )
        assert not page.export_button.isEnabled()
        assert not page.no_reference_points.isHidden()
        page.export_location.setCurrentIndex(page.export_location.findData("nodes"))
        assert page.export_button.isEnabled()
        assert page.no_reference_points.isHidden()
    finally:
        page.close_cleanup()
        page.deleteLater()
        app.processEvents()


def test_analysis_views_share_selection_and_keep_fea_edits_during_navigation(
    iteration_model, monkeypatch
):
    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QWidget

    from morphopt.ui import mainwindow, workbench
    from morphopt.ui.widgets import finite_element, observation_pages

    app = QApplication.instance() or QApplication([])

    class Viewer(QWidget):
        def refresh_ui(self, context): pass
        def apply_language(self): pass
        def apply_theme(self): pass

    class Viewport(QWidget):
        def rebuild(self, build): pass
        def apply_theme(self): pass

    monkeypatch.setattr(workbench, 'PreviewViewer', Viewer)
    monkeypatch.setattr(observation_pages, 'PlotViewport', Viewport)
    monkeypatch.setattr(finite_element, 'PlotViewport', Viewport)
    source, _, _ = iteration_model
    folder = Path(source.folder)
    scripts = folder / 'scripts'
    scripts.mkdir()
    (scripts / 'MAIN_SCRIPT_FOR_RESTART.py').write_text('')
    history = folder / 'log/history_record.csv'
    history.write_text('iteration,objective\n1,3.0\n2,2.0\n3,1.0\n')
    shutil.copyfile(source.model_path, source.model_path.with_name('femodel_2.npz'))
    shutil.copyfile(source.model_path.parent / 'result_0_iter_3.npz',
                    source.model_path.parent / 'result_0_iter_2.npz')
    monkeypatch.setattr(mainwindow, 'choose_directory', lambda *args: source.folder)
    window = mainwindow.MainWindow()
    try:
        window._menu_actions['open_result'].trigger()
        observer = window._observer
        window.analysis_navigation.setCurrentIndex(1)
        page = window._finite_element
        assert page.session.source.iteration == observer.panel.slider.value() == 3
        page.loads.item(0, 3).setText('0.004, 0, 0')
        private_model = page.session.controller
        window.show_definition()
        window.navigation.setCurrentIndex(1)
        assert window.stack.currentWidget() is page
        assert page.session.controller is private_model
        assert page.loads.item(0, 3).text() == '0.004, 0, 0'
        page.iterations.setCurrentIndex(page.iterations.findData(2))
        assert observer.panel.slider.value() == page.session.source.iteration == 2
        assert window._result_selection == ResultSelection(source.folder, 2)

        # A background optimization may finish more steps while an FEA worker
        # uses its pinned copy. Neither navigation nor polling can replace it.
        page._process.start(sys.executable, ['-c', 'import time; time.sleep(5)'])
        page._update_buttons()
        assert not observer.panel.slider.isEnabled()
        history.write_text('iteration,objective\n1,3.0\n2,2.0\n3,1.0\n4,0.5\n')
        observer.panel.show_iteration(source.folder, 4)
        assert observer.panel.slider.maximum() == 4
        assert observer.panel.slider.value() == 2
        assert page.session.source.iteration == 2
        window.show_definition()
        window.navigation.setCurrentIndex(1)
        assert page.is_running()
        assert page.session.source.iteration == 2
    finally:
        if window._finite_element is not None:
            window._finite_element.close_cleanup()
        window.deleteLater()
        app.processEvents()


def test_fea_contours_rebuild_with_axes_and_follow_selected_solution(iteration_model, monkeypatch):
    from PySide6.QtWidgets import QApplication, QWidget

    from morphopt.ui.widgets import finite_element

    app = QApplication.instance() or QApplication([])

    class Plotter:
        def __init__(self):
            self.meshes = []
            self.axes = None

        def add_mesh(self, mesh, **kwargs):
            self.meshes.append((mesh, kwargs))

        def add_axes(self, **kwargs):
            self.axes = kwargs

    class Viewport(QWidget):
        def rebuild(self, build):
            self.plotter = Plotter()
            build(self.plotter)

        def apply_theme(self):
            pass

    monkeypatch.setattr(finite_element, 'PlotViewport', Viewport)
    source, _, _ = iteration_model
    page = finite_element.FiniteElementPage()
    try:
        page.import_iteration(source.folder, source.iteration)
        page.show()
        app.processEvents()
        assert page.display_field.findData('S_Mises') >= 0
        for field in ('U', 'S_Mises', 'S12', 'E33', 'strain_energy_density'):
            page.display_field.setCurrentIndex(page.display_field.findData(field))
            page._render()
            plotter = page.viewport.plotter
            assert plotter.axes['interactive'] is False
            assert plotter.axes['color'] == finite_element.theme_manager.palette.text
            mesh, kwargs = plotter.meshes[0]
            assert kwargs['scalars'] == field
            assert np.isfinite(mesh.point_data[field]).all()
            assert kwargs['scalar_bar_args']['title'] == field
        page.deformed.setChecked(False)
        undeformed_values = page.viewport.plotter.meshes[0][0].point_data[field].copy()
        page.deformed.setChecked(True)
        np.testing.assert_allclose(page.viewport.plotter.meshes[0][0].point_data[field], undeformed_values)
        # Editing invalidates the old result and its cached fields immediately.
        page.loads.item(0, 3).setText('0.004, 0, 0')
        assert page._result_fields is None
        assert not page.display_field.isEnabled()
        assert 'scalars' not in page.viewport.plotter.meshes[0][1]
        assert page.viewport.plotter.axes is not None
        page._load_selected()
        assert page.display_field.isEnabled()
        assert page.display_field.currentData() == field
        assert not page._render_pending, page.output.toPlainText()
        assert 'scalars' in page.viewport.plotter.meshes[0][1]
    finally:
        page.hide()
        page.close_cleanup()
        page.deleteLater()
        app.processEvents()


def test_native_export_keeps_sparse_cases_and_filters_other_iterations(iteration_model, tmp_path):
    from morphopt.postprocess import NativeResultSnapshot, export_native_results

    source, _, result = iteration_model
    # Sparse original case numbers must survive; unrelated iteration 4 is excluded.
    shutil.copyfile(source.model_path.parent / 'result_0_iter_3.npz',
                    source.model_path.parent / 'result_7_iter_3.npz')
    shutil.copyfile(source.model_path, source.model_path.parent / 'femodel_4.npz')
    shutil.copyfile(source.model_path.parent / 'result_0_iter_3.npz',
                    source.model_path.parent / 'result_0_iter_4.npz')
    session = FiniteElementSession()
    try:
        session.import_iteration(source)
        request = json.loads(session.native_export_request(str(tmp_path / 'native'), 'actuator').read_text())
        archive = export_native_results(request['destination'], name=request['name'], iteration=request['iteration'],
            model_path=request['model_path'], source=request['source'],
            results=tuple(NativeResultSnapshot(**entry) for entry in request['results']))
        assert {path.name for path in archive.iterdir()} == {
            'actuator_femodel.npz', 'actuator_case0.npz', 'actuator_case7.npz', 'actuator_manifest.json'}
        manifest = json.loads((archive / 'actuator_manifest.json').read_text())
        assert [entry['case'] for entry in manifest['results']] == ['0', '7']
        with cpu_torch_defaults():
            loaded = torchfea.solver.StaticResult.load(str(archive / 'actuator_case7.npz'))
            assert torch.allclose(loaded.GC, result.GC)
        assert source.model_path.read_bytes() == (archive / 'actuator_femodel.npz').read_bytes()
    finally:
        session.close()


def test_native_export_failure_cleans_new_directory_and_preserves_existing(
    iteration_model, tmp_path, monkeypatch
):
    from morphopt.postprocess import exports

    source, _, _ = iteration_model
    session = FiniteElementSession()
    try:
        session.import_iteration(source)
        request = json.loads(session.native_export_request(str(tmp_path / 'native'), 'actuator').read_text())
        arguments = dict(name=request['name'], iteration=request['iteration'], model_path=request['model_path'],
                         source=request['source'], results=tuple(
                             exports.NativeResultSnapshot(**entry) for entry in request['results']))
        first = exports.export_native_results(request['destination'], **arguments)
        before = {path.name: path.read_bytes() for path in first.iterdir()}
        copyfile = exports.shutil.copyfile

        def fail_after_model(source, target):
            if Path(target).name == 'actuator_case0.npz':
                raise OSError('disk full')
            return copyfile(source, target)

        monkeypatch.setattr(exports.shutil, 'copyfile', fail_after_model)
        with pytest.raises(OSError, match='disk full'):
            exports.export_native_results(request['destination'], **arguments)
        assert {path.name: path.read_bytes() for path in first.iterdir()} == before
        assert sorted(path.name for path in first.parent.iterdir()) == [first.name]
    finally:
        session.close()
