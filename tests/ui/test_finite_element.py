from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import pytest
import torch
import torchfea

from morphopt import BoxPart
from morphopt.postprocess import (
    IterationModel,
    available_fields,
    cpu_torch_defaults,
    export_results,
    export_saved_results,
)
from morphopt.ui.application import OptimizationRunSession, ProblemLibrary
from morphopt.ui.application.finite_element import FiniteElementSession
from morphopt.ui.application.results import ResultSelection


@pytest.fixture
def iteration_model(tmp_path):
    folder = tmp_path / "optimization"
    saved = folder / "log" / "femodel&results"
    saved.mkdir(parents=True)
    with cpu_torch_defaults():
        part = BoxPart(
            length=1, height=1, depth=1, mesh_size=1, mesh_order=1
        ).build_part()
        part.elems["C3D8"].set_materials(
            torchfea.materials.NeoHookean(mu=1.0, kappa=10.0)
        )
        controller = torchfea.FEAController()
        controller.assembly = torchfea.Assembly()
        controller.assembly.add_part(part, "body")
        controller.assembly.add_instance(torchfea.Instance("body"), "body-1")
        controller.assembly.add_boundary(
            torchfea.boundarys.Boundary_Condition("body-1", "nodes_xmin"), "fixed"
        )
        controller.assembly.add_load(
            torchfea.loads.BodyForce("body-1", "C3D8", [0.002, 0.0, 0.0]),
            "body_force",
        )
        controller.solver = torchfea.solver.StaticImplicitSolver(tol_error=1e-8)
        controller.initialize()
        result = controller.solve(if_initialize=False)
        assert result.converged
        controller.save_model(str(saved / "femodel_3.npz"), if_save_source_code=False)
        result.save(str(saved / "result_0_iter_3.npz"))
    (saved / "load_cases.json").write_text(json.dumps(["0", "7"]), encoding="utf-8")
    return IterationModel(str(folder), 3, "0"), controller, result


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
            [sys.executable, "-m", "morphopt.ui.fea_worker", str(request)],
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
            [sys.executable, "-m", "morphopt.ui.fea_worker", str(request)],
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


def test_exports_merge_selected_quantities_into_one_file(iteration_model, tmp_path):
    _, controller, result = iteration_model
    previous_dtype = torch.get_default_dtype()
    node_path = export_results(controller, result, tmp_path / "my_nodes.csv")
    element_path = export_results(
        controller, result, tmp_path / "my_elements.csv", location="elements"
    )
    export_results(
        controller, result, tmp_path / "my_elements.npz", location="elements"
    )
    assert torch.get_default_dtype() is previous_dtype
    with node_path.open(encoding="utf-8-sig") as stream:
        nodes = list(csv.DictReader(stream))
    assert len(nodes) == 27
    assert set(nodes[0]) == {
        "instance",
        "node_id",
        "X",
        "Y",
        "Z",
        "U1",
        "U2",
        "U3",
        "U",
        "x",
        "y",
        "z",
    }
    for node in nodes:
        assert float(node["x"]) - float(node["X"]) == pytest.approx(
            float(node["U1"]), abs=1e-12
        )
    with element_path.open(encoding="utf-8-sig") as stream:
        points = list(csv.DictReader(stream))
    assert len(points) == 64
    assert (
        len(
            {
                (
                    row["instance"],
                    row["element_block"],
                    row["element_id"],
                    row["integration_point"],
                )
                for row in points
            }
        )
        == 64
    )
    assert sum(float(point["reference_volume"]) for point in points) == pytest.approx(
        1.0
    )
    assert sum(float(point["strain_energy"]) for point in points) > 0
    assert "S_Mises" in points[0] and "E11" in points[0]
    for point in points:
        assert float(point["strain_energy"]) == pytest.approx(
            float(point["strain_energy_density"]) * float(point["reference_volume"])
        )
    with np.load(tmp_path / "my_elements.npz", allow_pickle=False) as data:
        assert data["S_Mises"].shape == (64,)
        assert np.isfinite(data["S_Mises"]).all()
        assert data["strain_energy"].sum() == pytest.approx(
            sum(float(row["strain_energy"]) for row in points)
        )
        assert json.loads(str(data["__metadata__"]))["location"] == "elements"
    assert not (tmp_path / "manifest.json").exists()
    before = node_path.read_bytes()
    with pytest.raises(FileExistsError):
        export_results(controller, result, node_path)
    assert node_path.read_bytes() == before
    export_results(
        controller, result, node_path, fields=["displacement"], overwrite=True
    )
    with node_path.open(encoding="utf-8-sig") as stream:
        assert next(csv.reader(stream)) == [
            "instance",
            "node_id",
            "U1",
            "U2",
            "U3",
            "U",
        ]
    with pytest.raises(ValueError, match="one result location"):
        export_results(
            controller, result, tmp_path / "mixed.csv", fields=["coordinates", "stress"]
        )
    assert not (tmp_path / "mixed.csv").exists()


def test_saved_result_export_restores_its_load_case(iteration_model, tmp_path):
    source, _, _ = iteration_model
    with cpu_torch_defaults():
        controller = torchfea.load_model(str(source.model_path))
        controller.assembly._loads["body_force"]._parameters *= 2
        result = controller.solve(if_initialize=False)
        result_path = tmp_path / "different_case.npz"
        result.save(str(result_path))
        instance = controller.assembly._instances["body-1"]
        expected = controller.GC2RGC(result.GC)[instance._RGC_index].detach().cpu().numpy()

    output = export_saved_results(
        source.model_path, result_path, tmp_path / "fields.npz",
        location="nodes", fields=["displacement"],
    )
    with np.load(output) as data:
        np.testing.assert_allclose(data["U1"], expected[:, 0])


def test_extension_labels_use_field_descriptions_and_format_names():
    from morphopt.ui.presentation.result_fields import export_format_label, field_label

    assert field_label("custom_field", "Custom physical field") == "Custom physical field"
    assert export_format_label("xyz") == "XYZ (*.xyz)"


def test_elements_without_gauss_points_export_only_element_data(
    iteration_model, tmp_path, monkeypatch
):
    _, controller, result = iteration_model
    element = controller.assembly._instances["body-1"].part.elems["C3D8"]

    def no_gauss(_self, _nodes):
        raise NotImplementedError

    monkeypatch.setattr(type(element), "get_gaussian_points", no_gauss)
    assert available_fields(controller, result, "elements") == ("element_coordinates",)
    from morphopt.postprocess import ResultContours

    assert {field.key for field in ResultContours(controller, result).fields} == {
        "U", "U1", "U2", "U3"
    }
    path = export_results(
        controller,
        result,
        tmp_path / "elements.csv",
        location="elements",
        fields=[
            "element_coordinates",
            "gauss_coordinates",
            "energy",
            "stress",
            "strain",
        ],
    )
    with path.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8
    assert set(rows[0]) == {"instance", "element_block", "element_id", "CX", "CY", "CZ"}
    assert all(row["CX"] for row in rows)
    with pytest.raises(ValueError, match="no data"):
        export_results(
            controller,
            result,
            tmp_path / "no_gauss.csv",
            location="elements",
            fields=["stress"],
        )
    assert not (tmp_path / "no_gauss.csv").exists()


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


def test_gauss_strain_uses_global_axes_for_rotated_instances(iteration_model, tmp_path):
    _, controller, _ = iteration_model
    extension = 0.01
    with cpu_torch_defaults():
        instance = torchfea.Instance(
            "body", translation=[2.0, 3.0, 4.0], rotation=[0.0, 0.0, math.pi / 2]
        )
        controller.assembly._instances["body-1"] = instance
        controller.initialize()
        rgc = controller.GC2RGC(torch.zeros_like(controller.assembly._GC))
        local = torch.zeros_like(instance.part.nodes)
        local[:, 0] = instance.part.nodes[:, 0] * extension
        rgc[instance._RGC_index] = local @ instance.rotation_matrix.T
        result = torchfea.solver.StaticResult(
            GC=controller.RGC2GC(rgc),
            work_conditions=controller.assembly.get_work_conditions(),
            model_hash=controller.get_model_hash(),
            converged=True,
        )
        output = export_results(
            controller,
            result,
            tmp_path / "rotated_strain.csv",
            location="elements",
            fields=["strain"],
        )
        export_results(
            controller, result, tmp_path / "rotated_nodes.csv", fields=["coordinates"]
        )
    with output.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 64
    for row in rows:
        assert float(row["E22"]) == pytest.approx(((1 + extension) ** 2 - 1) / 2)
        assert float(row["E11"]) == pytest.approx(0, abs=1e-12)
    with (tmp_path / "rotated_nodes.csv").open(encoding="utf-8-sig") as stream:
        first = next(csv.DictReader(stream))
    assert [float(first[key]) for key in ("X", "Y", "Z")] == pytest.approx(
        [2.0, 3.0, 4.0]
    )


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
        page.export_results()
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
        page.export_results()
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


def test_mixed_elements_do_not_invent_gauss_points(tmp_path):
    from types import SimpleNamespace

    class PlainElement:
        _elems = torch.tensor([[1, 2]])
        _elems_index = torch.tensor([1])

        def get_gaussian_points(self, nodes):
            raise NotImplementedError

    class IntegratedElement:
        _elems = torch.tensor([[0, 1]])
        _elems_index = torch.tensor([0])
        gaussian_weight = torch.ones((1, 1))

        def get_gaussian_points(self, nodes):
            return nodes[self._elems].mean(dim=1)[None, ...]

        def get_potential_energy_density(self, local):
            return torch.full((1, 1), 2.0)

    nodes = torch.tensor([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]])
    instance = SimpleNamespace(
        enabled=True,
        nodes=nodes,
        _RGC_index=slice(0, 9),
        rotation_matrix=None,
        part=SimpleNamespace(
            elems={"solid": IntegratedElement(), "plain": PlainElement()}
        ),
    )
    controller = SimpleNamespace(
        assembly=SimpleNamespace(_instances={"part": instance}),
        GC2RGC=lambda values: values,
        get_model_hash=lambda: "mixed model",
    )
    result = SimpleNamespace(
        GC=torch.zeros(9), converged=True, model_hash="mixed model"
    )
    path = export_results(
        controller,
        result,
        tmp_path / "mixed.csv",
        location="elements",
        fields=["element_coordinates", "gauss_coordinates", "energy"],
    )
    with path.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert rows[0]["integration_point"] == "1"
    assert rows[0]["strain_energy_density"] == "2.0"
    assert rows[1]["integration_point"] == ""
    assert rows[1]["strain_energy_density"] == ""
    assert rows[1]["X"] == ""
    assert float(rows[1]["CY"]) == pytest.approx(0.5)
    export_results(
        controller,
        result,
        tmp_path / "mixed.npz",
        location="elements",
        fields=["element_coordinates", "energy"],
    )
    with np.load(tmp_path / "mixed.npz", allow_pickle=False) as data:
        assert np.isnan(data["integration_point"][1])
        assert np.isnan(data["strain_energy_density"][1])
        assert all(data[key].dtype != object for key in data.files)


def test_failed_export_preserves_existing_file_and_cleans_temporary_files(
    iteration_model, tmp_path, monkeypatch
):
    from morphopt.postprocess import (
        RESULT_FIELDS,
        ResultField,
        ResultLocation,
        ResultTable,
    )

    _, controller, result = iteration_model

    def broken_rows():
        yield "body-1", 1, 0.0
        raise ValueError("field evaluation failed")

    monkeypatch.setitem(
        RESULT_FIELDS,
        "broken",
        ResultField(
            "broken",
            "Test provider",
            ResultLocation.NODES,
            lambda context: ResultTable(
                "broken", ("instance", "node_id", "bad"), broken_rows()
            ),
        ),
    )
    path = tmp_path / "user_data.csv"
    path.write_text("original data")
    with pytest.raises(ValueError, match="field evaluation failed"):
        export_results(controller, result, path, fields=["broken"], overwrite=True)
    assert path.read_text() == "original data"
    assert not list(tmp_path.glob(".user_data.csv.*"))
    new_path = tmp_path / "incomplete.csv"
    with pytest.raises(ValueError, match="field evaluation failed"):
        export_results(controller, result, new_path, fields=["broken"])
    assert not new_path.exists()
    assert not list(tmp_path.glob(".incomplete.csv.*"))


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
        set(available_fields(controller, result, "reference_points")) == expected_fields
    )
    path = export_results(
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
    selected = export_results(
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
        page.export_results()
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
    assert available_fields(controller, result, "reference_points") == ()
    with pytest.raises(ValueError, match="no data"):
        export_results(
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


def test_contours_match_exported_gauss_fields_and_cache_by_group(iteration_model, tmp_path):
    from morphopt.postprocess import ResultContours

    _, controller, result = iteration_model
    path = export_results(controller, result, tmp_path / 'contours.npz',
                          location='elements', fields=['energy', 'stress', 'strain'])
    instance = controller.assembly._instances['body-1']
    contours = ResultContours(controller, result)
    previous_dtype = torch.get_default_dtype()
    with np.load(path) as exported:
        for field in contours.fields:
            actual = contours.values(field)['body-1']
            if field.source == 'displacement':
                displacement = controller.GC2RGC(result.GC)[instance._RGC_index].detach().cpu().numpy()
                expected = (np.linalg.norm(displacement, axis=1) if field.key == 'U'
                            else displacement[:, int(field.key[1]) - 1])
            else:
                sums = np.zeros(len(instance.nodes))
                counts = np.zeros(len(instance.nodes))
                for block, element in instance.part.elems.items():
                    for local_index, element_id in enumerate(element._elems_index.tolist()):
                        selection = ((exported['element_block'] == block)
                                     & (exported['element_id'] == element_id + 1))
                        mean = np.average(exported[field.key][selection],
                                          weights=exported['reference_volume'][selection])
                        nodes = element._elems[local_index].cpu().numpy()
                        sums[nodes] += mean
                        counts[nodes] += 1
                expected = sums / counts
            np.testing.assert_allclose(actual, expected, atol=1e-12)
        field = next(field for field in contours.fields if field.key == 'S11')
        assert np.shares_memory(contours.values(field)['body-1'], contours.values(field)['body-1'])
    assert torch.get_default_dtype() is previous_dtype


def test_contour_strain_rotates_into_global_axes(iteration_model):
    from morphopt.postprocess import ResultContours

    _, controller, _ = iteration_model
    with cpu_torch_defaults():
        instance = torchfea.Instance('body', rotation=[0., 0., math.pi / 2])
        controller.assembly._instances['body-1'] = instance
        controller.initialize()
        extension = 0.1
        rgc = controller.GC2RGC(torch.zeros_like(controller.assembly._GC))
        local = torch.zeros_like(instance.part.nodes)
        local[:, 0] = extension * instance.part.nodes[:, 0]
        rgc[instance._RGC_index] = local @ instance.rotation_matrix.T
        result = torchfea.solver.StaticResult(GC=controller.RGC2GC(rgc), converged=True,
                                            work_conditions=controller.assembly.get_work_conditions())
        contours = ResultContours(controller, result)
        for field in contours.fields:
            if field.source == 'strain':
                expected = ((1 + extension) ** 2 - 1) / 2 if field.key == 'E22' else 0.
                np.testing.assert_allclose(contours.values(field)['body-1'], expected, atol=1e-12)


def test_contour_average_handles_weights_missing_nodes_and_sparse_element_ids():
    from types import SimpleNamespace

    from morphopt.postprocess import ResultContours

    class IntegratedElement:
        _elems = torch.tensor([[0, 1], [1, 2]])
        _elems_index = torch.tensor([8, 3])
        gaussian_weight = torch.tensor([[1., 3.], [3., 1.]])

        def get_gaussian_points(self, nodes):
            return nodes[self._elems].mean(dim=1)[None].expand(2, -1, -1)

        def get_potential_energy_density(self, local):
            return torch.tensor([[0., 8.], [4., 0.]])

    class PlainElement:
        _elems = torch.tensor([[2, 3]])
        _elems_index = torch.tensor([2])

    instance = SimpleNamespace(enabled=True, nodes=torch.zeros(4, 3),
        _RGC_index=slice(0, 12), rotation_matrix=None,
        part=SimpleNamespace(elems={'solid': IntegratedElement(), 'plain': PlainElement()}))
    controller = SimpleNamespace(assembly=SimpleNamespace(_instances={'body': instance}),
                                 GC2RGC=lambda values: values)
    result = SimpleNamespace(GC=torch.zeros(12))
    contours = ResultContours(controller, result)
    assert not any(field.source in ('stress', 'strain') for field in contours.fields)
    field = next(field for field in contours.fields if field.source == 'energy')
    np.testing.assert_allclose(contours.values(field)['body'], [3., 4.5, 6., np.nan])


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
        assert page._contours is None
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
    from morphopt.postprocess import native

    source, _, _ = iteration_model
    session = FiniteElementSession()
    try:
        session.import_iteration(source)
        request = json.loads(session.native_export_request(str(tmp_path / 'native'), 'actuator').read_text())
        arguments = dict(name=request['name'], iteration=request['iteration'], model_path=request['model_path'],
                         source=request['source'], results=tuple(
                             native.NativeResultSnapshot(**entry) for entry in request['results']))
        first = native.export_native_results(request['destination'], **arguments)
        before = {path.name: path.read_bytes() for path in first.iterdir()}
        copyfile = native.shutil.copyfile

        def fail_after_model(source, target):
            if Path(target).name == 'actuator_case0.npz':
                raise OSError('disk full')
            return copyfile(source, target)

        monkeypatch.setattr(native.shutil, 'copyfile', fail_after_model)
        with pytest.raises(OSError, match='disk full'):
            native.export_native_results(request['destination'], **arguments)
        assert {path.name: path.read_bytes() for path in first.iterdir()} == before
        assert sorted(path.name for path in first.parent.iterdir()) == [first.name]
    finally:
        session.close()
