"""Capture actual archive views and a second finite-element solve."""

import csv
import multiprocessing
import sys
import time
from pathlib import Path

from morphopt.ui.application import ProblemLibrary


def demo_archive(directory: Path, definition: Path) -> None:
    """Run one restart segment before either language starts its Qt session."""
    from morphopt.opt_runner import _run_worker

    problem = ProblemLibrary.load(definition, issues=[])
    problem.device = problem.updater_device = "cpu"
    problem.solver.process_devices = ["cpu"]
    problem.result_folder = str(directory / "results")
    script = directory / "task.py"
    ProblemLibrary.export_python(problem, script)
    _run_worker(str(script), device="cpu", restart_per_iteration=3)


def wait_for(predicate, settle, description, seconds=120):
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for " + description)
        settle()


def capture_simp(window, directory, save, settle):
    """Observe a live CPU topology job and open its material-specific OBJ settings."""
    from morphopt.ui.application.quickstart import QuickstartOptions, build_quickstart

    options = QuickstartOptions.for_method("simp")
    options.label = "SIMP"
    options.mesh_size = 4
    problem = build_quickstart(options)
    problem.device = problem.updater_device = "cpu"
    problem.solver.process_devices = ["cpu"]
    problem.result_folder = ".results"
    directory.mkdir()
    script = directory / "simp.py"
    ProblemLibrary.export_python(problem, script)
    window._ensure_observer()
    observer = window._observer
    if not observer.start_python(str(script)):
        raise RuntimeError("Could not start the documentation SIMP job")
    try:
        window._show_analysis()
        wait_for(lambda: observer.panel.iteration >= 1 or not observer.is_running(),
                 settle, "first SIMP checkpoint", 600)
        if observer.panel.iteration < 1:
            raise RuntimeError(observer.output_view.toPlainText())
        save("ui-quickstart/optimization/live-progress.png", "Live SIMP optimization with its first checkpoint")
    finally:
        if observer.is_running():
            observer.btn_stop.click()
    observer.panel.options.setCurrentRow(2)
    save("ui-quickstart/optimization/simp-density.png", "Optimized material density field")
    dialog = observer.panel.history_export_dialog()
    dialog.tabs.setCurrentIndex(1)
    dialog.show()
    save("ui-quickstart/optimization/export-simp-field.png", "SIMP density field export", dialog)
    dialog.component_mode.setCurrentIndex(dialog.component_mode.findData("voxel_obj"))
    if not dialog.voxel_threshold.isVisible():
        raise RuntimeError("SIMP voxel export is unavailable")
    save("ui-quickstart/optimization/export-simp-obj.png", "OBJ voxel size and retention threshold", dialog)
    dialog.reject()


def capture_result(window, folder, save, settle):
    from morphopt.ui.widgets.run_dialogs import ContinueDialog

    window._ensure_observer()
    observer = window._observer
    observer.open_result(str(folder))
    window._show_analysis()
    panel = observer.panel
    with (folder / "log/history_record.csv").open(encoding="utf-8") as stream:
        count = len(list(csv.DictReader(stream)))
    if count < 2:
        raise ValueError("Screenshot archive must contain at least two completed iterations")

    def shot(name, caption, widget=None):
        save("ui-quickstart/optimization/" + name + ".png", caption, widget)

    panel.options.setCurrentRow(0)
    shot("history-and-metrics", "Objective, metrics and iteration history")
    panel.options.setCurrentRow(1)
    shot("optimization-log", "Optimization log")
    panel.options.setCurrentRow(2)
    panel.select_iteration(1)
    shot("initial-design", "First archived design")
    panel.select_iteration(count)
    shot("saved-design", "Last archived design")
    selector = panel._updatable_structure_page.view_selector
    index = next(i for i in range(selector.count()) if "control" in str(selector.itemData(i)))
    selector.setCurrentIndex(index)
    shot("surface-control-net", "Surface and control net")
    dialog = panel.history_export_dialog()
    dialog.show()
    try:
        settle()
        dialog.gif.options()  # Flush the interactive scene and surface any archive error.
        shot("export-history-gif", "GIF settings and final frame", dialog)
        dialog.tabs.setCurrentIndex(1)
        shot("export-current-surfaces", "Export all boundary surfaces", dialog)
        dialog.tabs.setCurrentIndex(2)
        shot("export-abaqus-inp", "Abaqus input deck", dialog)
    finally:
        dialog.reject()
    panel.options.setCurrentRow(panel.options.count() - 1)
    shot("load-case-deformation", "Deformed mesh of the archived load case")
    resume = ContinueDialog(count, window)
    resume.show()
    shot("continue-dialog", "Choose a saved iteration to resume", resume)
    resume.reject()

    window.show_finite_element()
    fe = window._finite_element
    if fe is None or fe.session.result is None:
        raise RuntimeError("Could not load the archived finite-element solution")

    def fe_shot(name, caption, widget=None):
        save("ui-quickstart/finite-element/" + name + ".png", caption, widget)

    def menu(combo, name):
        combo.showPopup()
        fe_shot(name, name, combo.view().window())
        combo.hidePopup()

    def choose(combo, key):
        index = combo.findData(key)
        if index < 0:
            raise ValueError(f"Missing finite-element option: {key}")
        combo.setCurrentIndex(index)

    fe_shot("displacement", "Displacement magnitude on the deformed model")
    menu(fe.iterations, "design-iteration-menu")
    menu(fe.display_field, "field-menu")
    fe.deformed.setChecked(False)
    fe_shot("undeformed-configuration", "Displacement on the undeformed model")
    fe.deformed.setChecked(True)
    choose(fe.display_field, "S_Mises")
    fe_shot("mises-stress", "Mises stress")
    menu(fe.export_location, "export-location-menu")
    for location, name in [("elements", "gauss-point-export"), ("reference_points", "reference-point-export")]:
        choose(fe.export_location, location)
        fe_shot(name, "Export " + location)

    pressure_row = next(i for i in range(fe.loads.rowCount()) if fe.loads.item(i, 0).text() == "pressure_1")
    field = fe.loads.cellWidget(pressure_row, 3)
    field.edits[0].setText("0.04")
    field.edits[0].editingFinished.emit()
    fe_shot("modified-pressure", "Pressure changed to 0.04 in the working model")
    fe.start_analysis()
    fe_shot("solver-running", "Recomputing the modified load case")
    wait_for(lambda: not fe.is_running(), settle, "finite-element solve", 600)
    if fe.session.selected_result.is_original or fe.session.result is None:
        raise RuntimeError("Finite-element recomputation failed: " + fe.output.toPlainText())
    fe.display_field.setCurrentIndex(0)
    fe_shot("recomputed-displacement", "Displacement after recomputing pressure 0.04")
    menu(fe.cases, "analysis-result-menu")
    return count


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    demo_archive(Path.cwd(), Path(sys.argv[1]))
