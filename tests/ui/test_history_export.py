"""The common history-export lifecycle with real worker subprocesses."""

from pathlib import Path
import sys
import time

import pyvista as pv
import pytest
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from morphopt.postprocess import boundary_surface_options
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


def surface_dialog(archive):
    return history_export.SurfaceExportDialog(
        str(archive.folder), 2, 2, boundary_surface_options(archive.params),
    )


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
    dialog = surface_dialog(design_archive)
    dialog.export.click()
    first_directory = Path(dialog._directory.name)
    wait_for_export(app, dialog)
    assert errors and "export failure" in errors[0]
    assert not first_directory.exists()
    assert dialog.controls.isEnabled() and dialog.export.isEnabled()
    assert not destination.exists()
    monkeypatch.setattr(history_export, "start_worker", start_worker)
    dialog.export.click()
    directory = Path(dialog._directory.name)
    assert directory != first_directory
    wait_for_export(app, dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert len(messages) == 1 and len(errors) == 1
    assert not directory.exists()
    assert {path.name for path in destination.rglob("*.stp")} == {"surface_0.stp", "surface_1.stp"}


def test_gif_export_uses_structured_frame_count(export_ui, design_archive, tmp_path, monkeypatch):
    app, messages, errors = export_ui
    folder = design_archive.log_folder / "deformation"
    folder.mkdir()
    for iteration, radius in ((1, 1), (2, 2)):
        pv.Sphere(radius=radius).triangulate().save(folder / f"task_case_iter_{iteration}.stl")
    output = tmp_path / "history.gif"
    monkeypatch.setattr(
        history_export, "choose_save_file", lambda *args: SaveFileSelection(output, "gif")
    )
    dialog = history_export.HistoryGifExportDialog(
        str(design_archive.folder), 2, "deformation", ("case",), (),
        {"position": [[5, 5, 5], [0, 0, 0], [0, 0, 1]]}, (150, 150),
        {"background": "white", "text_color": "black", "deformation_color": "blue",
         "mesh_ambient": 0.2, "mesh_diffuse": 0.7, "mesh_specular": 0.2, "mesh_specular_power": 30},
    )
    dialog.export.click()
    directory = Path(dialog._directory.name)
    wait_for_export(app, dialog)
    assert not errors, errors
    assert messages == [tr("ui.history_gif.completed", count=2, path=str(output))]
    assert output.read_bytes().startswith(b"GIF")
    assert not directory.exists()


def test_cancelling_gif_removes_partial_file_and_preserves_existing_output(
    export_ui, design_archive, tmp_path, monkeypatch
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
    dialog = history_export.HistoryGifExportDialog(
        str(design_archive.folder), 2, "deformation", ("case",), (), {}, (150, 150), {},
    )
    dialog.export.click()
    directory = Path(dialog._directory.name)
    assert dialog._process.waitForStarted(1000)
    partial.write_bytes(b"incomplete animation")
    dialog.reject()
    app.processEvents()
    assert dialog._process.state() == QProcess.ProcessState.NotRunning
    assert not dialog._active
    assert not directory.exists() and not partial.exists()
    assert output.read_bytes() == b"existing animation"
    assert not messages and not errors
