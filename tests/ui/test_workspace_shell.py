from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.results import ResultSelection
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


def test_analysis_is_unavailable_until_a_task_is_opened(monkeypatch):
    from morphopt.ui import mainwindow

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    assert window.navigation.count() == 2
    assert not window.navigation.isTabEnabled(1)
    assert window._observer is None
    assert window._finite_element is None
    assert 'export_fea' not in window._menu_actions
    assert not hasattr(window, 'export_finite_element')
    window.navigation.setCurrentIndex(1)
    assert window.stack.currentIndex() == 0
    monkeypatch.setattr(window, '_choose_file_path', lambda *args, **kwargs: '')
    window._menu_actions['open_python'].trigger()
    monkeypatch.setattr(mainwindow, 'choose_directory', lambda *args: '')
    window._menu_actions['open_result'].trigger()
    assert not window.navigation.isTabEnabled(1)
    assert window._observer is None
    window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('entry', ['definition_button', 'analysis_menu'])
def test_definition_entry_starts_latest_snapshot_and_preserves_it_across_navigation(monkeypatch, entry):
    from morphopt.ui import launcher

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    window.set_problem(ProblemLibrary.create('shapeopt', label='latest definition'))
    window._ensure_observer()
    observer = window._observer
    launched = []
    process = object()
    monkeypatch.setattr(launcher, 'run_job', lambda problem: (launched.append(problem.to_dict()), process))
    monkeypatch.setattr(observer._run, 'stream_output', lambda _callback: None)
    start = (window.start_button.click if entry == 'definition_button'
             else window._start_optimization_action.trigger)
    start()
    assert window.stack.currentWidget() is observer
    assert window.navigation.isTabEnabled(1)
    assert observer.is_running()
    assert observer._timer.isActive()
    assert launched == [window.current_problem().to_dict()]
    assert observer.task_controls.parentWidget() is window.analysis_header
    assert observer.btn_start.isHidden()
    assert not observer.btn_stop.isHidden()
    assert observer._run.definition is not window.current_problem()
    assert not hasattr(observer, 'btn_open')
    assert not window._menu_actions['open_python'].isEnabled()
    assert not window._menu_actions['open_result'].isEnabled()

    window.show_definition()
    window.current_problem().label = 'subsequent edit'
    assert observer._run.definition.label == 'latest definition'
    assert observer.is_running()
    assert observer._timer.isActive()
    assert not window.start_button.isEnabled()
    window.navigation.setCurrentIndex(1)
    assert window.stack.currentWidget() is observer
    assert window._observer is observer
    assert observer._run.process is process
    observer._timer.stop()
    observer._run.process = None
    window.deleteLater()
    app.processEvents()


def test_file_menu_starts_python_without_replacing_the_definition(monkeypatch, tmp_path):
    from morphopt.ui import launcher

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    definition = window.current_problem()
    path = str(tmp_path / 'another.py')
    monkeypatch.setattr(window, '_choose_file_path', lambda *args, **kwargs: path)
    window._ensure_observer()
    observer = window._observer
    process = object()
    paths = []
    monkeypatch.setattr(launcher, 'run_py_definition', lambda path: (paths.append(path) or str(tmp_path), 'another', process))
    monkeypatch.setattr(observer._run, 'stream_output', lambda _callback: None)
    window._menu_actions['open_python'].trigger()
    assert paths == [path]
    assert observer.is_running()
    assert observer._timer.isActive()
    assert window.stack.currentWidget() is observer
    assert window.current_problem() is definition
    assert observer.task_label == 'another.py'
    assert 'another.py' in window.windowTitle()
    observer._timer.stop()
    observer._run.process = None
    window.deleteLater()
    app.processEvents()


def saved_result(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'MAIN_SCRIPT_FOR_RESTART.py').write_text('')
    log = tmp_path / 'log'
    log.mkdir()
    (log / 'history_record.csv').write_text('iteration,objective\n1,2.0\n2,1.0\n')
    models = log / 'femodel&results'
    models.mkdir()
    for iteration in (1, 2):
        (models / f'femodel_{iteration}.npz').touch()
    return str(tmp_path.resolve())


def test_result_menu_shares_folder_and_iteration_with_fea_without_launching(monkeypatch, tmp_path):
    from morphopt.ui import launcher, mainwindow

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    folder = saved_result(tmp_path)
    monkeypatch.setattr(mainwindow, 'choose_directory', lambda *args: folder)
    monkeypatch.setattr(launcher, 'run_continue', lambda *args, **kwargs: pytest.fail('opening a result launched a worker'))
    window._menu_actions['open_result'].trigger()
    observer = window._observer
    assert window.stack.currentWidget() is observer
    assert window._result_selection == ResultSelection(folder, 2)
    assert observer.btn_start.isEnabled()
    assert not observer.is_running()
    assert window.analysis_navigation.isTabEnabled(1)
    assert window.result_context.folder == folder
    assert window.result_context.toolTip() == folder
    assert not hasattr(window, 'result_path')
    clipboard = app.clipboard()
    previous_clipboard = clipboard.text()
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        window.show()
        app.processEvents()
        QTest.mouseClick(window.result_context, Qt.MouseButton.LeftButton)
        assert clipboard.text() == folder
        assert window.statusBar().currentMessage() == tr('ui.workspace.result_path_copied')
        clipboard.setText('before keyboard activation')
        QTest.keyClick(window.result_context, Qt.Key.Key_Return)
        assert clipboard.text() == folder
    finally:
        clipboard.setText(previous_clipboard)

    window._ensure_finite_element()
    page = window._finite_element
    imports = []
    monkeypatch.setattr(page, 'synchronize_result', lambda *selection: imports.append(selection))
    window.analysis_navigation.setCurrentIndex(1)
    assert imports[-1] == (folder, 2)
    assert window.stack.currentWidget() is page
    assert not observer.panel.chk_follow.isChecked()
    page.selectionChanged.emit(folder, 1)
    assert observer.panel.slider.value() == 1
    assert window._result_selection == ResultSelection(folder, 1)
    window.analysis_navigation.setCurrentIndex(0)
    observer.panel.slider.setValue(2)
    assert window._result_selection == ResultSelection(folder, 2)
    window.analysis_navigation.setCurrentIndex(1)
    assert imports[-1] == (folder, 2)
    window.show_definition()
    window.navigation.setCurrentIndex(1)
    assert window.stack.currentWidget() is page
    assert window._finite_element is page
    assert window.result_context.toolTip() == folder
    page.close_cleanup()
    window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('existing_result', [False, True])
def test_invalid_result_and_failed_launch_keep_current_workspace(monkeypatch, tmp_path, existing_result):
    from morphopt.ui import launcher, mainwindow

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    warnings = []
    monkeypatch.setattr(mainwindow, 'choose_directory', lambda *args: str(tmp_path))
    monkeypatch.setattr(mainwindow.QMessageBox, 'warning', lambda *args: warnings.append(args))
    window._menu_actions['open_result'].trigger()
    assert warnings
    assert window._observer is None
    assert not window.navigation.isTabEnabled(1)
    if existing_result:
        saved_result(tmp_path)
        window._menu_actions['open_result'].trigger()
        selection = window._result_selection
    monkeypatch.setattr(window, '_choose_file_path', lambda *args, **kwargs: str(tmp_path / 'bad.py'))
    def fail(_path):
        raise ValueError('invalid script')
    monkeypatch.setattr(launcher, 'run_py_definition', fail)
    window._menu_actions['open_python'].trigger()
    assert window.stack.currentIndex() == (1 if existing_result else 0)
    assert window.navigation.isTabEnabled(1) == existing_result
    assert not window._observer.is_running()
    assert window._menu_actions['open_python'].isEnabled()
    if existing_result:
        assert window._result_selection == selection
        assert window._observer._run.folder == str(tmp_path)
        assert window._observer._run.source.kind is RunSourceKind.CONTINUE
        assert window._observer.btn_start.text() == tr('ui.observe_panel.continue')
        assert window.result_context.folder == str(tmp_path)
    window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('mode,target', [(RunMode.FRESH, None), (RunMode.CONTINUE, 1)])
def test_stop_keeps_result_and_continue_button_resumes_it(monkeypatch, tmp_path, mode, target):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QDialog

    from morphopt.ui import launcher, observe_panel

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    window._ensure_observer()
    window._show_analysis()
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
    assert observer.btn_stop.isHidden()
    assert not observer.btn_start.isHidden()
    assert observer.btn_start.isEnabled()
    assert observer.btn_start.text() == tr('ui.observe_panel.continue')
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


@pytest.mark.parametrize('missing', ['folder', 'history', 'restart_script'])
def test_stop_keeps_continue_visible_when_no_restart_is_available(monkeypatch, tmp_path, missing):
    from morphopt.ui import launcher

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    window._ensure_observer()
    window._show_analysis()
    observer = window._observer
    observer._run.process = object()
    if missing != 'folder':
        observer._run.folder = str(tmp_path)
        if missing == 'history':
            scripts = tmp_path / 'scripts'
            scripts.mkdir()
            (scripts / 'MAIN_SCRIPT_FOR_RESTART.py').touch()
        else:
            log = tmp_path / 'log'
            log.mkdir()
            (log / 'history_record.csv').write_text('iteration,objective\n1,1.0\n')
    monkeypatch.setattr(launcher, 'stop_job', lambda _process: None)
    monkeypatch.setattr(observer, '_show_progress', lambda _progress: None)
    monkeypatch.setattr(launcher, 'run_continue', lambda *args, **kwargs: pytest.fail('resumed without a saved restart'))
    observer._update_buttons()
    observer.btn_stop.click()
    assert not observer.is_running()
    assert observer.btn_stop.isHidden()
    assert not observer.btn_start.isHidden()
    assert not observer.btn_start.isEnabled()
    assert observer.btn_start.text() == tr('ui.observe_panel.continue')
    assert observer.btn_start.toolTip() == tr('ui.observe_panel.continue_unavailable_hint')
    observer.btn_start.click()
    window.show_definition()
    window.navigation.setCurrentIndex(1)
    assert not observer.btn_start.isHidden()
    assert not observer.btn_start.isEnabled()
    window.deleteLater()
    app.processEvents()


def test_result_path_updates_before_first_iteration_and_resets_for_a_new_task(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from morphopt.ui import launcher
    from morphopt.ui.application.runs import RunProgress

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    window._ensure_observer()
    window._show_analysis()
    observer = window._observer
    assert window.result_context.toolTip() == tr('ui.workspace.result_path_pending')
    folder = tmp_path / 'new_result'
    folder.mkdir()
    observer._run.folder = str(folder)
    observer._run.process = SimpleNamespace(stdout=None)
    observer._show_progress(RunProgress(str(folder), 0, True))
    assert window.result_context.folder == str(folder)
    assert window.result_context.toolTip() == str(folder)
    assert window._result_selection is None
    monkeypatch.setattr(launcher, 'stop_job', lambda _process: None)
    observer._update_buttons()
    observer.btn_stop.click()
    assert window.result_context.folder == str(folder)
    assert window.result_context.toolTip() == str(folder)

    monkeypatch.setattr(window, '_choose_file_path', lambda *args, **kwargs: str(tmp_path / 'another.py'))
    monkeypatch.setattr(launcher, 'run_py_definition', lambda _path: (str(tmp_path), 'another', SimpleNamespace(stdout=None)))
    window.open_python_optimization()
    assert observer.is_running()
    assert window.result_context.folder is None
    assert window.result_context.toolTip() == tr('ui.workspace.result_path_pending')
    observer._timer.stop()
    observer._run.process = None
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
    window._ensure_observer()
    window._show_analysis()
    window._ensure_finite_element()
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


def test_natural_completion_keeps_the_result_available_for_continuation(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from morphopt.ui import mainwindow

    app = QApplication.instance() or QApplication([])
    window = shell(monkeypatch)
    folder = saved_result(tmp_path)
    monkeypatch.setattr(mainwindow, 'choose_directory', lambda *args: folder)
    window._menu_actions['open_result'].trigger()
    observer = window._observer
    observer._run.process = SimpleNamespace(poll=lambda: 0)
    observer._run.mode = RunMode.CONTINUE
    observer._run.source = None
    observer._timer.start()
    observer._poll_once()
    assert not observer.is_running()
    assert not observer._timer.isActive()
    assert observer._run.source == RunSource(RunSourceKind.CONTINUE, path=folder, label=tmp_path.name)
    assert observer.btn_start.isEnabled()
    assert observer._run.last_iteration == 2
    assert window._menu_actions['open_result'].isEnabled()
    window.deleteLater()
    app.processEvents()
