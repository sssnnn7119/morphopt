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
from pathlib import Path

from .model.problem import ProblemDefinition
from .codegen.generator import generate_source

#: where UI-launched runs are written by default (job cwd)
UI_RUN_DIR = os.path.join(os.getcwd(), "ui_runs")


def export_to_py(problem: ProblemDefinition, path) -> str:
    """Write the problem definition to a runnable ``ThisController`` module."""
    src = generate_source(problem)
    Path(path).write_text(src, encoding="utf-8")
    return path


def _sanitize(name: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name)
    return out or "problem"


def run_root_for(problem: ProblemDefinition, base: str | None = None) -> str:
    """Absolute directory that will contain ``<label>_T<timestamp>/`` folders."""
    if base is None:
        base = UI_RUN_DIR
    os.makedirs(base, exist_ok=True)
    rf = problem.result_folder or ".results/"
    if not os.path.isabs(rf):
        rf = os.path.join(base, rf)
    return rf


def run_job(problem: ProblemDefinition, workdir: str | None = None) -> tuple[str, subprocess.Popen]:
    """Launch the problem headless in a subprocess.

    Nothing is written into the project/``workdir``: the only generated module
    file is a tiny launch stub placed in the *system* temporary directory
    (spawn workers must import a real module file to obtain ``ThisController``,
    while the timestamped result folder does not exist yet).  Once the run's
    result folder appears, the controller writes the canonical runnable script
    ``<result>/scripts/MAIN_SCRIPT_FOR_RESTART.py`` and the observer adds the
    definition ``<result>/scripts/MAIN_SCRIPT_FOR_RESTART.morph`` beside it.

    Returns ``(staging_job_path, process)``.  The process (and its mp-spawned
    children) run in their own process group so the whole tree can be stopped
    at once.
    """
    if workdir is None:
        base = UI_RUN_DIR
    else:
        base = workdir
    os.makedirs(base, exist_ok=True)
    # ensure the run root is absolute so the observer can discover folders
    run_root = run_root_for(problem, base)
    problem.result_folder = run_root

    # system temp launch module (unique, import-safe stem) -- never in base
    stem = re.sub(r"[^A-Za-z0-9_]", "_", _sanitize(problem.label))
    job_path = os.path.join(tempfile.gettempdir(), f"{stem}_{os.getpid()}.py")
    export_to_py(problem, job_path)

    env = dict(os.environ)
    env.setdefault("PYVISTA_QT_BINDING", "pyside6")
    proc = subprocess.Popen([sys.executable, job_path], cwd=base, env=env,
                            start_new_session=True)
    return job_path, proc


def run_continue(path_result: str, target_iteration: int | None = None,
                 device: str = "cpu", restart_per_iteration: int = 10,
                 workdir: str | None = None) -> subprocess.Popen:
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
    env = dict(os.environ)
    env.setdefault("PYVISTA_QT_BINDING", "pyside6")
    return subprocess.Popen([sys.executable, "-c", code], cwd=workdir, env=env,
                            start_new_session=True)


def stop_job(proc: subprocess.Popen | None) -> None:
    """Terminate a launched job and its whole process group (best effort)."""
    if proc is None or proc.poll() is not None:
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


def latest_result_dir(run_root: str, label: str) -> str | None:
    """Newest ``<run_root>/<label>_T*`` folder (for auto-discovering a run)."""
    if not run_root or not label:
        return None
    matches = sorted(glob_dirs(os.path.join(run_root, label + "_T*")))
    return matches[-1] if matches else None


def glob_dirs(pattern: str):
    import glob
    out = []
    for p in glob.glob(pattern):
        if os.path.isdir(p):
            out.append(p)
    return out


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
