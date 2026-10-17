from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.runs import RunMode, RunSource, RunSourceKind
from morphopt.ui.i18n import tr


def shell(monkeypatch):
    from morphopt.ui import mainwindow, workbench
    from morphopt.ui.widgets import finite_element, observation_pages

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
    return mainwindow.MainWindow()


def test_workspace_switching_keeps_optimization_process_and_polling(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    window.navigation.setCurrentIndex(1)
    observer = window._observer
    observer._run.process = object()
    observer._timer.start()
    window.navigation.setCurrentIndex(2)
    finite_element = window._finite_element
    window.show_definition()
    assert window.stack.currentIndex() == 0
    assert observer.is_running()
    assert observer._timer.isActive()
    window.goto_observer(ProblemLibrary.create_blank('another definition'))
    assert window._observer is observer
    assert observer.is_running()
    assert observer._timer.isActive()
    assert observer._run.definition.label == 'another definition'
    assert observer._run.source is None
    assert window.statusBar().currentMessage() == tr(
        'ui.workspace.definition_staged', label='another definition'
    )
    observer._on_back()
    assert observer.is_running()
    window.navigation.setCurrentIndex(2)
    assert window._finite_element is finite_element
    observer._run.process = None
    observer._timer.stop()
    finite_element.close_cleanup()
    window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('entry', ['source_button', 'analysis_menu'])
def test_import_definition_prepares_and_starts_latest_definition(monkeypatch, entry):
    from PySide6.QtWidgets import QDialog, QPushButton

    from morphopt.ui import launcher, observe_panel

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    window.set_problem(ProblemLibrary.create('shapeopt', label='first definition'))
    window.navigation.setCurrentIndex(1)
    observer = window._observer
    assert observer._run.source is None
    assert not observer.btn_start.isEnabled()

    assert not any(
        button.text() == tr('ui.workspace.import_definition')
        for button in observer.findChildren(QPushButton)
    )

    class DefinitionSourceDialog:
        def __init__(self, has_definition, parent):
            assert has_definition
            assert parent is observer

        def exec(self):
            return QDialog.DialogCode.Accepted

        def chosen(self):
            return RunSourceKind.DEFINITION

    monkeypatch.setattr(observe_panel, 'SourceDialog', DefinitionSourceDialog)
    # The original source button and the menu both prepare the current definition.
    observer._run.select_source(RunSource(RunSourceKind.PYTHON, path='previous.py'))
    import_task = (
        observer.btn_open.click
        if entry == 'source_button'
        else window._send_definition_action.trigger
    )
    import_task()
    assert observer._run.source.kind is RunSourceKind.DEFINITION
    assert observer._run.source.label == 'first definition'
    assert observer.btn_start.isEnabled()
    assert not observer.is_running()
    assert window.statusBar().currentMessage() == tr(
        'ui.workspace.definition_imported', label='first definition'
    )

    # Re-importing picks up the definition page's latest model, not the old copy.
    window.set_problem(ProblemLibrary.create('shapeopt', label='latest definition'))
    import_task()
    assert window.stack.currentIndex() == 1
    assert observer._run.source.label == 'latest definition'
    prepared = observer._run.definition.to_dict()
    assert prepared == window.current_problem().to_dict()
    assert observer._run.definition is not window.current_problem()
    window.current_problem().label = 'subsequent edit'
    assert observer._run.definition.label == 'latest definition'

    # Exercise the actual Start button through the process-launch boundary.
    launched = []
    process = object()
    monkeypatch.setattr(
        launcher, 'run_job',
        lambda problem: (launched.append(problem.to_dict()), process),
    )
    monkeypatch.setattr(observer._run, 'stream_output', lambda _callback: None)
    observer.btn_start.click()
    assert launched == [prepared]
    assert observer._run.process is process
    assert observer._timer.isActive()
    assert not observer.btn_start.isEnabled()
    observer._timer.stop()
    observer._run.process = None
    window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('mode,target', [(RunMode.FRESH, None), (RunMode.CONTINUE, 1)])
def test_stop_keeps_result_and_continue_button_resumes_it(monkeypatch, tmp_path, mode, target):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QDialog

    from morphopt.ui import launcher, observe_panel

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    window.navigation.setCurrentIndex(1)
    observer = window._observer
    result = tmp_path / 'current_task_T1'
    scripts = result / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'MAIN_SCRIPT_FOR_RESTART.py').write_text(
        "device = 'cuda:1'\nrestart_per_iteration = 3\n"
    )
    log = result / 'log'
    log.mkdir()
    (log / 'history_record.csv').write_text('iteration,objective\n1,2.0\n2,1.0\n')
    process = SimpleNamespace(stdout=None)
    observer._run.process = process
    observer._run.mode = mode
    observer._run.folder = str(result)
    observer._run.last_iteration = 1
    observer.panel._results.folder = str(result)
    observer._timer.start()
    observer._update_buttons()
    stopped = []
    monkeypatch.setattr(launcher, 'stop_job', stopped.append)
    monkeypatch.setattr(launcher, 'latest_result_dir', lambda *_args: str(result))
    progress = []
    monkeypatch.setattr(observer, '_show_progress', progress.append)
    monkeypatch.setattr(observer.panel, 'reset', lambda: pytest.fail('stopping reset the result view'))

    observer.btn_stop.click()
    assert stopped == [process]
    assert not observer.is_running()
    assert not observer._timer.isActive()
    assert not observer.btn_stop.isEnabled()
    assert observer.btn_start.isEnabled()
    assert observer.btn_start.text() == tr('ui.observe_panel.1_continue')
    assert observer._run.source == RunSource(
        RunSourceKind.CONTINUE, path=str(result), label=result.name
    )
    assert observer._run.last_iteration == 2
    assert progress[-1].iteration == 2
    assert observer.panel.path_result == str(result)
    assert observer.status.text() == tr('ui.observe_panel.optimization_paused_at_step', iteration=2)
    window.show_definition()
    window.navigation.setCurrentIndex(1)
    assert observer.btn_start.isEnabled()

    class ResumeDialog:
        def __init__(self, max_step, parent):
            assert max_step == 2
            assert parent is observer

        def exec(self):
            return QDialog.DialogCode.Accepted

        def target_iteration(self):
            return target

    monkeypatch.setattr(observe_panel, 'ContinueDialog', ResumeDialog)
    launches = []

    def resume(folder, **options):
        launches.append((folder, options))
        return process

    monkeypatch.setattr(launcher, 'run_continue', resume)
    monkeypatch.setattr(launcher, 'run_job', lambda *_args: pytest.fail('continuation started a fresh task'))
    observer.btn_start.click()
    assert launches == [(str(result), {
        'target_iteration': target, 'device': 'cuda:1', 'restart_per_iteration': 3,
    })]
    assert observer._run.process is process
    assert observer._run.mode is RunMode.CONTINUE
    assert observer.panel.path_result == str(result)
    assert observer._timer.isActive()
    assert observer._run.source is None
    observer.btn_stop.click()
    assert stopped == [process, process]
    assert observer.btn_start.isEnabled()
    assert observer._run.source.kind is RunSourceKind.CONTINUE
    window.deleteLater()
    app.processEvents()


def test_save_remembers_opened_and_saved_definition_path(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    path = tmp_path / 'saved.morph'
    choices = []
    monkeypatch.setattr(window, '_choose_file_path', lambda *args, **kwargs: choices.append(args) or str(path))
    assert window.save_morph()
    assert len(choices) == 1
    window.current_problem().label = 'updated'
    assert window.save_morph()
    assert len(choices) == 1
    assert ProblemLibrary.load(path).label == 'updated'
    window.set_problem(ProblemLibrary.load(path), path=str(path))
    assert window.save_morph()
    assert len(choices) == 1
    assert window._menu_actions['save'].shortcut().toString() == 'Ctrl+S'
    window.deleteLater()
    app.processEvents()


def test_fea_page_constructs_and_can_be_left_during_worker_start(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    window.navigation.setCurrentIndex(2)
    page = window._finite_element
    assert page.loads.columnCount() == 4
    assert all(not page.loads.horizontalHeaderItem(column).text().startswith('ui.') for column in range(4))
    assert page.export_location.currentData() == 'nodes'
    assert set(page.field_checks) == {'coordinates', 'displacement', 'deformed_coordinates', 'rp_coordinates', 'rp_displacement', 'rp_rotation', 'rp_deformed_coordinates', 'element_coordinates', 'gauss_coordinates', 'energy', 'stress', 'strain'}
    # Starting is an active QProcess state even before the child has launched.
    page._process.start('/bin/sleep', ['1'])
    window.navigation.setCurrentIndex(0)
    assert page.is_running()
    page.close_cleanup()
    window.deleteLater()
    app.processEvents()
