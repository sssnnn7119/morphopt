"""Launch helpers: export the problem to .py and run / continue it.

The generated script is a standard morphopt job module; running it spawns the
optimization worker in a child process, exactly like the canonical
``examples/*.py`` flow.  Runs are always headless (no observer window from the
job): the MorphOpt UI's in-window observer launches the job and polls the
result folder on disk.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .model.problem import ProblemDefinition
from ..paths import sanitize_name
from .worker_environment import worker_environment

#: where UI-launched runs are written by default (job cwd)
UI_RUN_DIR = os.path.join(os.getcwd(), "ui_runs")


def _start_headless_process(
    command: Sequence[str], working_directory: str
) -> subprocess.Popen:
    """Start one UI-managed job in its own process group.

    All launch paths use this helper so Stop can reliably terminate spawned
    worker children and PyVista consistently selects PySide6 when a job
    imports visualization-adjacent dependencies.  The job's combined output
    is piped back to :class:`ObserverControls` for display in the UI.
    """
    environment = worker_environment()
    process_options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt" else {"start_new_session": True}
    )
    return subprocess.Popen(
        list(command),
        cwd=working_directory,
        env=environment,
        **process_options,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )


def run_root_for(problem: ProblemDefinition, base: str | None = None) -> str:
    """Absolute directory that will contain ``<label>_T<timestamp>/`` folders."""
    if base is None:
        base = UI_RUN_DIR
    os.makedirs(base, exist_ok=True)
    rf = problem.result_folder or ".results/"
    if not os.path.isabs(rf):
        rf = os.path.join(base, rf)
    return rf


def run_job(
    problem: ProblemDefinition, workdir: str | None = None
) -> tuple[str, subprocess.Popen]:
    """Export a private temporary script bundle and launch it headless.

    The controller copies the bundle into the result's scripts directory.
    Returns the staging script path and the process owning the worker tree.
    """
    from .application.definitions import ProblemLibrary

    base = UI_RUN_DIR if workdir is None else workdir
    problem.result_folder = run_root_for(problem, base)
    job_path = ProblemLibrary.export_python_bundle(
        problem, tempfile.mkdtemp(prefix="morphopt_")
    )

    proc = _start_headless_process([sys.executable, job_path], base)
    return job_path, proc


def run_continue(
    path_result: str,
    target_iteration: int | None = None,
    device: str = "cpu",
    restart_per_iteration: int = 10,
    workdir: str | None = None,
) -> subprocess.Popen:
    """Continue an existing result folder (last step or a chosen step)."""
    if workdir is None:
        workdir = UI_RUN_DIR
    os.makedirs(workdir, exist_ok=True)
    code = (
        "import morphopt; "
        "morphopt.start_optimization(path_result=%r, target_iteration=%r, "
        "device=%r, restart_per_iteration=%r)"
        % (path_result, target_iteration, device, restart_per_iteration)
    )
    return _start_headless_process([sys.executable, "-c", code], workdir)


def parse_job_location(py_path: str) -> tuple[str, str]:
    """Read where a definition script writes its results.

    A runnable definition declares ``opt_label`` and ``path_result_folder`` in
    ``Controller.__init__``; results go to ``<path_result_folder>/<opt_label>_T*``
    relative to the script's directory.  Falls back to ``.results/`` + script
    stem when the file does not carry them.
    """
    label = os.path.splitext(os.path.basename(py_path))[0]
    folder = ".results/"
    try:
        text = Path(py_path).read_text(encoding="utf-8")
    except OSError:
        text = ""
    m = re.search(r"\bopt_label\s*=\s*(['\"])(.*?)\1", text)
    if m:
        label = m.group(2)
    m = re.search(r"\bpath_result_folder\s*=\s*(['\"])(.*?)\1", text)
    if m:
        folder = m.group(2)
    py_dir = os.path.dirname(os.path.abspath(py_path))
    if not os.path.isabs(folder):
        folder = os.path.join(py_dir, folder)
    return os.path.normpath(folder), sanitize_name(label)


def run_py_definition(
    py_path: str, workdir: str | None = None
) -> tuple[str, str, subprocess.Popen]:
    """Run an existing definition ``.py`` from scratch (headless job).

    The script keeps its own result location (``opt_label`` +
    ``path_result_folder``), so the caller can discover the fresh result with
    :func:`latest_result_dir`.  Returns ``(root, label, process)``.
    """
    if workdir is None:
        workdir = os.path.dirname(os.path.abspath(py_path))
    os.makedirs(workdir, exist_ok=True)
    root, label = parse_job_location(py_path)
    proc = _start_headless_process([sys.executable, os.path.abspath(py_path)], workdir)
    return root, label, proc


def stop_job(proc: subprocess.Popen | None) -> None:
    """Terminate the launched task's process tree using the platform API."""
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True, text=True, errors="replace", timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode and proc.poll() is None:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        proc.wait(timeout=3)
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    # give it a moment, then force kill if it is still alive
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.wait(timeout=3)


def latest_result_dir(run_root: str, label: str) -> str | None:
    """Newest ``<run_root>/<label>_T*`` folder (for auto-discovering a run)."""
    if not run_root or not label or not Path(run_root).is_dir():
        return None
    matches = sorted(
        str(path) for path in Path(run_root).iterdir()
        if path.is_dir() and path.name.startswith(label + "_T")
    )
    return matches[-1] if matches else None


def parse_run_options(scripts_main: str) -> tuple[str, int]:
    """Read device + restart_per_iteration from a job's restart main script."""
    device, restart = "cpu", 10
    try:
        text = Path(scripts_main).read_text(encoding="utf-8")
    except OSError:
        return device, restart
    m = re.search(r"device\s*=\s*['\"]([^'\"]+)['\"]", text)
    if m:
        device = m.group(1)
    m = re.search(r"restart_per_iteration\s*=\s*(\d+)", text)
    if m:
        restart = int(m.group(1))
    return device, restart
