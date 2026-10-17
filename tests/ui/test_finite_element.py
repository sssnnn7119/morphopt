from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time

import numpy as np
import pytest
import torch
import torchfea

from morphopt import BoxPart
from morphopt.postprocess import available_fields, export_results
from morphopt.ui.application import OptimizationRunSession, ProblemLibrary
from morphopt.ui.application.finite_element import FiniteElementSession, IterationModel
from morphopt.ui.application.results import _cpu_torch_defaults


@pytest.fixture
def iteration_model(tmp_path):
    folder = tmp_path / 'optimization'
    saved = folder / 'log' / 'femodel&results'
    saved.mkdir(parents=True)
    with _cpu_torch_defaults():
        part = BoxPart(length=1, height=1, depth=1, mesh_size=1, mesh_order=1).build_part()
        part.elems['design'].set_materials(torchfea.materials.NeoHookean(mu=1., kappa=10.))
        controller = torchfea.FEAController()
        controller.assembly = torchfea.Assembly()
        controller.assembly.add_part(part, 'body')
        controller.assembly.add_instance(torchfea.Instance('body'), 'body-1')
        controller.assembly.add_boundary(torchfea.boundarys.Boundary_Condition('body-1', 'nodes_xmin'), 'fixed')
        controller.assembly.add_load(torchfea.loads.BodyForce('body-1', 'design', [.002, 0., 0.]), 'body_force')
        controller.solver = torchfea.solver.StaticImplicitSolver(tol_error=1e-8)
        controller.initialize()
        result = controller.solve(if_initialize=False)
        assert result.converged
        controller.save_model(str(saved / 'femodel_3.npz'), if_save_source_code=False)
        result.save(str(saved / 'result_0_iter_3.npz'))
    return IterationModel(str(folder), 3, 0), controller, result


def test_analysis_worker_changes_loads_without_changing_optimization(iteration_model):
    source, _, original_result = iteration_model
    original_hash = hashlib.sha256(source.model_path.read_bytes()).digest()
    session = FiniteElementSession()
    try:
        session.import_iteration(source)
        assert IterationModel.iterations(source.folder) == (3,)
        assert source.cases() == (0,)
        session.apply_loads({'body_force': (True, [.004, 0., 0.])})
        request = session.solve_request()
        process = subprocess.run([sys.executable, '-m', 'morphopt.ui.fea_worker', str(request)], capture_output=True, timeout=45)
        assert process.returncode == 0, process.stderr.decode()
        session.accept_solution()
        assert session.result.GC.abs().max() > original_result.GC.abs().max()
        assert hashlib.sha256(source.model_path.read_bytes()).digest() == original_hash
        assert session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(.004)
        with pytest.raises(ValueError):
            session.apply_loads({'body_force': (False, [float('nan'), 0., 0.])})
        assert session.load_values()[0][3] is True
        destination = session.directory / 'chosen_data.npz'
        request = session.export_request(str(destination), 'npz', ['energy', 'stress', 'strain'], location='elements')
        process = subprocess.run([sys.executable, '-m', 'morphopt.ui.fea_worker', str(request)], capture_output=True, timeout=45)
        assert process.returncode == 0, process.stderr.decode()
        with np.load(destination, allow_pickle=False) as archive:
            manifest = json.loads(str(archive['__metadata__']))
            assert archive['S_Mises'].shape == (64,)
        assert len(manifest['fields']) == 3
        assert manifest['source']['iteration'] == 3
    finally:
        session.close()


def test_exports_merge_selected_quantities_into_one_file(iteration_model, tmp_path):
    _, controller, result = iteration_model
    previous_dtype = torch.get_default_dtype()
    node_path = export_results(controller, result, tmp_path / 'my_nodes.csv')
    element_path = export_results(controller, result, tmp_path / 'my_elements.csv', location='elements')
    export_results(controller, result, tmp_path / 'my_elements.npz', location='elements')
    assert torch.get_default_dtype() is previous_dtype
    with node_path.open(encoding='utf-8-sig') as stream:
        nodes = list(csv.DictReader(stream))
    assert len(nodes) == 27
    assert set(nodes[0]) == {'instance', 'node_id', 'X', 'Y', 'Z', 'U1', 'U2', 'U3', 'U', 'x', 'y', 'z'}
    for node in nodes:
        assert float(node['x']) - float(node['X']) == pytest.approx(float(node['U1']), abs=1e-12)
    with element_path.open(encoding='utf-8-sig') as stream:
        points = list(csv.DictReader(stream))
    assert len(points) == 64
    assert len({(row['instance'], row['element_block'], row['element_id'], row['integration_point']) for row in points}) == 64
    assert sum(float(point['reference_volume']) for point in points) == pytest.approx(1.)
    assert sum(float(point['strain_energy']) for point in points) > 0
    assert 'S_Mises' in points[0] and 'E11' in points[0]
    for point in points:
        assert float(point['strain_energy']) == pytest.approx(float(point['strain_energy_density']) * float(point['reference_volume']))
    with np.load(tmp_path / 'my_elements.npz', allow_pickle=False) as data:
        assert data['S_Mises'].shape == (64,)
        assert np.isfinite(data['S_Mises']).all()
        assert data['strain_energy'].sum() == pytest.approx(sum(float(row['strain_energy']) for row in points))
        assert json.loads(str(data['__metadata__']))['location'] == 'elements'
    assert not (tmp_path / 'manifest.json').exists()
    before = node_path.read_bytes()
    with pytest.raises(FileExistsError):
        export_results(controller, result, node_path)
    assert node_path.read_bytes() == before
    export_results(controller, result, node_path, fields=['displacement'], overwrite=True)
    with node_path.open(encoding='utf-8-sig') as stream:
        assert next(csv.reader(stream)) == ['instance', 'node_id', 'U1', 'U2', 'U3', 'U']
    with pytest.raises(ValueError, match='one result location'):
        export_results(controller, result, tmp_path / 'mixed.csv', fields=['coordinates', 'stress'])
    assert not (tmp_path / 'mixed.csv').exists()


def test_elements_without_gauss_points_export_only_element_data(iteration_model, tmp_path, monkeypatch):
    _, controller, result = iteration_model
    element = controller.assembly._instances['body-1'].part.elems['design']
    def no_gauss(_self, _nodes):
        raise NotImplementedError
    monkeypatch.setattr(type(element), 'get_gaussian_points', no_gauss)
    assert available_fields(controller, result, 'elements') == ('element_coordinates',)
    path = export_results(controller, result, tmp_path / 'elements.csv', location='elements',
                          fields=['element_coordinates', 'gauss_coordinates', 'energy', 'stress', 'strain'])
    with path.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8
    assert set(rows[0]) == {'instance', 'element_block', 'element_id', 'CX', 'CY', 'CZ'}
    assert all(row['CX'] for row in rows)
    with pytest.raises(ValueError, match='no data'):
        export_results(controller, result, tmp_path / 'no_gauss.csv', location='elements', fields=['stress'])
    assert not (tmp_path / 'no_gauss.csv').exists()


def test_result_options_keep_sparse_original_cases_and_separate_model_contexts(iteration_model, tmp_path):
    source, _, original_result = iteration_model
    session = FiniteElementSession()
    try:
        with _cpu_torch_defaults():
            controller = torchfea.load_model(str(source.model_path))
            controller.assembly._loads['body_force']._parameters *= 2
            another_case = controller.solve(if_initialize=False)
            assert another_case.converged
            another_case.save(str(source.model_path.parent / 'result_7_iter_3.npz'))
        options = session.result_options(source.folder, source.iteration)
        assert [entry.source.case for entry in options] == [0, 7]
        session.select_result(options[1])
        assert session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(.004)
        assert torch.allclose(session.result.GC, another_case.GC)
        session.select_result(options[0])
        assert session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(.002)
        assert torch.allclose(session.result.GC, original_result.GC)

        shutil.copyfile(source.model_path, session.directory / 'solved_model.npz')
        shutil.copyfile(options[0].result_path, session.directory / 'result.npz')
        entry = session.accept_solution('first solve log')
        assert session.result_options(source.folder, 3)[-1] == entry
        assert all(item.is_original for item in session.result_options(source.folder, 4))
        assert all(item.is_original for item in session.result_options(str(tmp_path / 'other'), 3))
        # An invalid or unconverged worker result must not create a new option.
        with _cpu_torch_defaults():
            rejected = torchfea.solver.StaticResult.load(str(entry.result_path))
            rejected.converged = False
            rejected.save(str(session.directory / 'result.npz'))
        with pytest.raises(ValueError):
            session.accept_solution()
        assert len(session.result_options(source.folder, 3)) == 3
        session.select_result(entry)
        assert session.result.converged
        assert entry.log_path.read_text() == 'first solve log'
        assert torch.allclose(session.result.GC, original_result.GC)
    finally:
        session.close()


def test_staging_another_definition_does_not_stop_or_mutate_active_run(monkeypatch, tmp_path):
    from morphopt.ui import launcher
    original = ProblemLibrary.create_blank('original')
    process = object()
    monkeypatch.setattr(launcher, 'run_job', lambda problem: ('job.py', process))
    monkeypatch.setattr(launcher, 'run_root_for', lambda problem: str(tmp_path))
    monkeypatch.setattr(launcher, 'stop_job', lambda process: pytest.fail('staging stopped an active job'))
    session = OptimizationRunSession()
    session.set_definition(original)
    session.start_definition(session.definition)
    original.label = 'edited outside observer'
    session.set_definition(ProblemLibrary.create_blank('next run'))
    assert session.process is process
    assert session.definition.label == 'next run'
    assert session._running_definition.label == 'original'


def test_gauss_strain_uses_global_axes_for_rotated_instances(iteration_model, tmp_path):
    _, controller, _ = iteration_model
    extension = .01
    with _cpu_torch_defaults():
        instance = torchfea.Instance('body', translation=[2., 3., 4.], rotation=[0., 0., math.pi / 2])
        controller.assembly._instances['body-1'] = instance
        controller.initialize()
        rgc = controller.GC2RGC(torch.zeros_like(controller.assembly._GC))
        local = torch.zeros_like(instance.part.nodes)
        local[:, 0] = instance.part.nodes[:, 0] * extension
        rgc[instance._RGC_index] = local @ instance.rotation_matrix.T
        result = torchfea.solver.StaticResult(
            GC=controller.RGC2GC(rgc), work_conditions=controller.assembly.get_work_conditions(),
            model_hash=controller.get_model_hash(), converged=True)
        output = export_results(controller, result, tmp_path / 'rotated_strain.csv', location='elements', fields=['strain'])
        export_results(controller, result, tmp_path / 'rotated_nodes.csv', fields=['coordinates'])
    with output.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 64
    for row in rows:
        assert float(row['E22']) == pytest.approx(((1 + extension) ** 2 - 1) / 2)
        assert float(row['E11']) == pytest.approx(0, abs=1e-12)
    with (tmp_path / 'rotated_nodes.csv').open(encoding='utf-8-sig') as stream:
        first = next(csv.DictReader(stream))
    assert [float(first[key]) for key in ('X', 'Y', 'Z')] == pytest.approx([2., 3., 4.])


def test_fea_widget_solves_and_exports_after_being_hidden(iteration_model, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication, QWidget
    from morphopt.ui.widgets import finite_element

    app = QApplication.instance() or QApplication([])
    class Viewport(QWidget):
        def rebuild(self, build): pass
        def apply_theme(self): pass
    monkeypatch.setattr(finite_element, 'PlotViewport', Viewport)
    source, _, original_result = iteration_model
    page = finite_element.FiniteElementPage()
    try:
        page.import_iteration(source.folder, source.iteration)
        assert page.cases.count() == 1
        original_entry = page.cases.currentData()
        assert original_entry.is_original
        assert page.loads.rowCount() == 1
        assert page.loads.item(0, 2).text() == 'body-1 · design'
        page.loads.item(0, 3).setText('0.004, 0, 0')
        assert page.session.result is None
        page.start_analysis()
        page.hide()
        def wait_for_job():
            deadline = time.monotonic() + 45
            while page.is_running() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            app.processEvents()
            assert not page.is_running(), page.output.toPlainText()
        wait_for_job()
        assert page.session.result is not None, page.output.toPlainText()
        assert page.session.result.GC.abs().max() > original_result.GC.abs().max()
        assert page.cases.count() == 2
        first_entry = page.cases.currentData()
        assert first_entry.number == 1
        first_gc = page.session.result.GC.clone()
        assert 'FEA completed.' in first_entry.log_path.read_text()
        page.loads.item(0, 3).setText('0.006, 0, 0')
        page.start_analysis()
        wait_for_job()
        assert page.cases.count() == 3
        second_entry = page.cases.currentData()
        assert second_entry.number == 2
        second_gc = page.session.result.GC.clone()
        assert second_gc.abs().max() > first_gc.abs().max()

        # Selecting a case restores its model, loads, solution, and own solver log.
        page.cases.setCurrentIndex(page._result_index(original_entry))
        assert page.session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(.002)
        assert torch.allclose(page.session.result.GC, original_result.GC)
        page.cases.setCurrentIndex(page._result_index(first_entry))
        assert page.session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(.004)
        assert torch.allclose(page.session.result.GC, first_gc)
        assert 'FEA completed.' in page.output.toPlainText()
        page.apply_language()
        assert page.cases.count() == 3
        assert page.cases.currentData() == first_entry
        assert torch.allclose(page.session.result.GC, first_gc)
        from morphopt.ui.widgets.file_dialogs import SaveFileSelection
        choices = iter([
            SaveFileSelection(tmp_path / 'chosen_nodes.csv', 'csv'),
            SaveFileSelection(tmp_path / 'chosen_elements.npz', 'npz'),
        ])
        monkeypatch.setattr(finite_element, 'choose_save_file', lambda *args: next(choices))
        page.export_results()
        wait_for_job()
        with (tmp_path / 'chosen_nodes.csv').open(encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        exported_max = max(abs(float(row[component])) for row in rows for component in ('U1', 'U2', 'U3'))
        assert exported_max == pytest.approx(float(first_gc.abs().max()))
        assert 'S_Mises' not in rows[0]
        page.export_location.setCurrentIndex(page.export_location.findData('elements'))
        for key in ('element_coordinates', 'gauss_coordinates', 'strain'):
            page.field_checks[key].setChecked(False)
        page.export_results()
        wait_for_job()
        with np.load(tmp_path / 'chosen_elements.npz', allow_pickle=False) as data:
            manifest = json.loads(str(data['__metadata__']))
            assert data['S_Mises'].shape == (64,)
            assert 'U1' not in data and 'E11' not in data and 'X' not in data
            assert {field['key'] for field in manifest['fields']} == {'energy', 'stress'}
            assert manifest['source']['analysis_number'] == 1
            assert manifest['source']['result_id'] == first_entry.key
        assert not list(tmp_path.glob('fea_iter_*'))

        # Editing or restoring an original must not mutate previously completed analyses.
        page.cases.setCurrentIndex(page._result_index(second_entry))
        assert torch.allclose(page.session.result.GC, second_gc)
        page.loads.item(0, 3).setText('0.009, 0, 0')
        assert page.session.result is None
        page.apply_language()
        assert page.loads.item(0, 3).text() == '0.009, 0, 0'
        assert page.session.result is None
        page.cases.setCurrentIndex(page._result_index(original_entry))
        assert page.cases.currentData().is_original
        assert page.session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(.002)
        page.cases.setCurrentIndex(page._result_index(second_entry))
        assert page.session.load_values()[0][-1].reshape(-1)[0] == pytest.approx(.006)
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
            return torch.full((1, 1), 2.)

    nodes = torch.tensor([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.]])
    instance = SimpleNamespace(enabled=True, nodes=nodes, _RGC_index=slice(0, 9), rotation_matrix=None,
        part=SimpleNamespace(elems={'solid': IntegratedElement(), 'plain': PlainElement()}))
    controller = SimpleNamespace(assembly=SimpleNamespace(_instances={'part': instance}),
        GC2RGC=lambda values: values, get_model_hash=lambda: 'mixed model')
    result = SimpleNamespace(GC=torch.zeros(9), converged=True, model_hash='mixed model')
    path = export_results(controller, result, tmp_path / 'mixed.csv', location='elements',
        fields=['element_coordinates', 'gauss_coordinates', 'energy'])
    with path.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert rows[0]['integration_point'] == '1'
    assert rows[0]['strain_energy_density'] == '2.0'
    assert rows[1]['integration_point'] == ''
    assert rows[1]['strain_energy_density'] == ''
    assert rows[1]['X'] == ''
    assert float(rows[1]['CY']) == pytest.approx(.5)
    export_results(controller, result, tmp_path / 'mixed.npz', location='elements',
        fields=['element_coordinates', 'energy'])
    with np.load(tmp_path / 'mixed.npz', allow_pickle=False) as data:
        assert np.isnan(data['integration_point'][1])
        assert np.isnan(data['strain_energy_density'][1])
        assert all(data[key].dtype != object for key in data.files)


def test_failed_export_preserves_existing_file_and_cleans_temporary_files(iteration_model, tmp_path, monkeypatch):
    from morphopt.postprocess import RESULT_FIELDS, ResultField, ResultLocation, ResultTable
    _, controller, result = iteration_model
    def broken_rows():
        yield 'body-1', 1, 0.
        raise ValueError('field evaluation failed')
    monkeypatch.setitem(RESULT_FIELDS, 'broken', ResultField('broken', 'unused', 'Test provider',
        ResultLocation.NODES, lambda context: ResultTable('broken', ('instance', 'node_id', 'bad'), broken_rows())))
    path = tmp_path / 'user_data.csv'
    path.write_text('original data')
    with pytest.raises(ValueError, match='field evaluation failed'):
        export_results(controller, result, path, fields=['broken'], overwrite=True)
    assert path.read_text() == 'original data'
    assert not list(tmp_path.glob('.user_data.csv.*'))
    new_path = tmp_path / 'incomplete.csv'
    with pytest.raises(ValueError, match='field evaluation failed'):
        export_results(controller, result, new_path, fields=['broken'])
    assert not new_path.exists()
    assert not list(tmp_path.glob('.incomplete.csv.*'))


def test_reference_point_exports_use_solved_six_dof_state(iteration_model, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QWidget
    from morphopt.ui.widgets import finite_element
    from morphopt.ui.widgets.file_dialogs import SaveFileSelection

    source, controller, _ = iteration_model
    with _cpu_torch_defaults():
        for name, position in [('RP_tip', [1., .5, .5]), ('RP_base', [0., .5, .5]), ('RP_ignored', [2., 0., 0.])]:
            controller.assembly.add_reference_point(torchfea.model.ReferencePoint(node=position), name)
        controller.assembly.get_reference_point('RP_ignored').enabled = False
        controller.assembly.add_constraint(torchfea.constraints.Couple('body-1', 'nodes_xmax', 'RP_tip'), 'tip_couple')
        controller.assembly.add_boundary(torchfea.boundarys.Boundary_Condition_RP('RP_base'), 'fixed_rp')
        controller.assembly.add_boundary(torchfea.boundarys.Boundary_Condition_RP('RP_ignored'), 'fixed_ignored')
        controller.assembly.add_load(torchfea.loads.Moment('RP_tip', [0., 1e-4, 0.]), 'moment')
        controller.initialize()
        result = controller.solve(if_initialize=False)
        assert result.converged
        controller.save_model(str(source.model_path), if_save_source_code=False)
        result.save(str(source.model_path.parent / 'result_0_iter_3.npz'))
        state = controller.GC2RGC(result.GC)
        tip = controller.assembly.get_reference_point('RP_tip')
        tip_dofs = state[tip._RGC_index].detach().cpu().numpy().reshape(-1)
        assert np.linalg.norm(tip_dofs[3:]) > 0
    expected_fields = {'rp_coordinates', 'rp_displacement', 'rp_rotation', 'rp_deformed_coordinates'}
    assert set(available_fields(controller, result, 'reference_points')) == expected_fields
    path = export_results(controller, result, tmp_path / 'reference_points.csv', location='reference_points')
    with path.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    assert [row['reference_point'] for row in rows] == ['RP_base', 'RP_tip']
    assert [row['reference_point_id'] for row in rows] == ['1', '3']
    row = rows[1]
    assert [float(row[key]) for key in ('X', 'Y', 'Z')] == pytest.approx([1., .5, .5])
    assert [float(row[key]) for key in ('U1', 'U2', 'U3')] == pytest.approx(tip_dofs[:3])
    assert [float(row[key]) for key in ('UR1', 'UR2', 'UR3')] == pytest.approx(tip_dofs[3:])
    assert float(row['UR']) == pytest.approx(np.linalg.norm(tip_dofs[3:]))
    assert float(row['x']) == pytest.approx(1. + tip_dofs[0])
    assert 'integration_point' not in row and 'instance' not in row
    selected = export_results(controller, result, tmp_path / 'rotation_only.csv', location='reference_points', fields=['rp_rotation'])
    with selected.open(encoding='utf-8-sig') as stream:
        assert next(csv.reader(stream)) == ['reference_point_id', 'reference_point', 'UR1', 'UR2', 'UR3', 'UR']

    app = QApplication.instance() or QApplication([])
    class Viewport(QWidget):
        def rebuild(self, build): pass
        def apply_theme(self): pass
    monkeypatch.setattr(finite_element, 'PlotViewport', Viewport)
    page = finite_element.FiniteElementPage()
    try:
        page.import_iteration(source.folder, source.iteration)
        page.export_location.setCurrentIndex(page.export_location.findData('reference_points'))
        assert page.export_button.isEnabled()
        assert page.no_reference_points.isHidden()
        assert {key for key, check in page.field_checks.items() if not check.isHidden()} == expected_fields
        destination = tmp_path / 'chosen_rp.npz'
        monkeypatch.setattr(finite_element, 'choose_save_file', lambda *args: SaveFileSelection(destination, 'npz'))
        page.export_results()
        deadline = time.monotonic() + 45
        while page.is_running() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        app.processEvents()
        assert not page.is_running(), page.output.toPlainText()
        assert destination.is_file(), page.output.toPlainText()
        with np.load(destination, allow_pickle=False) as data:
            assert data['reference_point'].tolist() == ['RP_base', 'RP_tip']
            assert data['UR2'][1] == pytest.approx(tip_dofs[4])
            assert data['U1'][1] == pytest.approx(tip_dofs[0])
            assert json.loads(str(data['__metadata__']))['location'] == 'reference_points'
    finally:
        page.close_cleanup()
        page.deleteLater()
        app.processEvents()


def test_model_without_reference_points_disables_rp_export(iteration_model, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication, QWidget
    from morphopt.ui.widgets import finite_element
    source, controller, result = iteration_model
    assert available_fields(controller, result, 'reference_points') == ()
    with pytest.raises(ValueError, match='no data'):
        export_results(controller, result, tmp_path / 'empty_rp.csv', location='reference_points', fields=['rp_rotation'])
    assert not (tmp_path / 'empty_rp.csv').exists()
    app = QApplication.instance() or QApplication([])
    class Viewport(QWidget):
        def rebuild(self, build): pass
        def apply_theme(self): pass
    monkeypatch.setattr(finite_element, 'PlotViewport', Viewport)
    page = finite_element.FiniteElementPage()
    try:
        page.import_iteration(source.folder, source.iteration)
        page.export_location.setCurrentIndex(page.export_location.findData('reference_points'))
        assert not page.export_button.isEnabled()
        assert not page.no_reference_points.isHidden()
        page.export_location.setCurrentIndex(page.export_location.findData('nodes'))
        assert page.export_button.isEnabled()
        assert page.no_reference_points.isHidden()
    finally:
        page.close_cleanup()
        page.deleteLater()
        app.processEvents()
