"""Optimization-process lifecycle independent from observer widgets."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .. import launcher
from ..model.problem import ProblemDefinition


class RunMode(str, Enum):
    FRESH = "fresh"
    CONTINUE = "continue"


class RunSourceKind(str, Enum):
    DEFINITION = "definition"
    PYTHON = "py"
    CONTINUE = "continue"


@dataclass(frozen=True)
class RunSource:
    """Typed source selected for the next optimization run."""

    kind: RunSourceKind
    path: str = ""
    label: str = ""


class OptimizationRunSession:
    """Own one UI-launched process and its result-discovery state."""

    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.mode: RunMode | None = None
        self.folder: str | None = None
        self.fresh_root = ""
        self.fresh_label = ""
        self.started_at = 0.0

    @property
    def active(self) -> bool:
        """Whether the observer still owns a process awaiting final polling."""
        return self.process is not None

    def adopt(self, folder: str) -> None:
        self._ensure_idle()
        self.folder = str(Path(folder).resolve())
        self.process = None
        self.mode = None

    def clear_result(self) -> None:
        """Forget the browsed result before selecting a fresh task source."""
        self._ensure_idle()
        self.folder = None
        self.fresh_root = ""
        self.fresh_label = ""
        self.started_at = 0.0

    def start_definition(self, problem: ProblemDefinition) -> subprocess.Popen:
        self._ensure_idle()
        _job, process = launcher.run_job(problem)
        self.process = process
        self.mode = RunMode.FRESH
        self.folder = None
        self.fresh_root = launcher.run_root_for(problem)
        self.fresh_label = launcher.sanitize_name(problem.label)
        self.started_at = time.time()
        return process

    def start_python(self, path: str) -> subprocess.Popen:
        self._ensure_idle()
        root, label, process = launcher.run_py_definition(path)
        self.process = process
        self.mode = RunMode.FRESH
        self.folder = None
        self.fresh_root = root
        self.fresh_label = label
        self.started_at = time.time()
        return process

    def start_continue(
        self,
        folder: str,
        target_iteration: int | None,
    ) -> subprocess.Popen:
        self._ensure_idle()
        scripts = Path(folder) / "scripts" / "MAIN_SCRIPT_FOR_RESTART.py"
        device, restart_per_iteration = launcher.parse_run_options(str(scripts))
        process = launcher.run_continue(
            folder,
            target_iteration=target_iteration,
            device=device,
            restart_per_iteration=restart_per_iteration,
        )
        self.process = process
        self.mode = RunMode.CONTINUE
        self.folder = str(Path(folder).resolve())
        self.started_at = time.time()
        return process

    @staticmethod
    def is_result_folder(folder: str) -> bool:
        return (Path(folder) / "scripts" / "MAIN_SCRIPT_FOR_RESTART.py").is_file()

    def discover_folder(self) -> str | None:
        """Resolve the timestamped result folder of a fresh process."""
        if self.mode is not RunMode.FRESH:
            return self.folder
        candidate = launcher.latest_result_dir(self.fresh_root, self.fresh_label)
        if candidate is None:
            return None
        if Path(candidate).stat().st_mtime < self.started_at - 2:
            return None
        self.folder = str(Path(candidate).resolve())
        return self.folder

    def has_exited(self) -> bool:
        return self.process is not None and self.process.poll() is not None

    def release_finished(self) -> None:
        if self.has_exited():
            self.process = None
            self.mode = None

    def stop(self) -> None:
        launcher.stop_job(self.process)
        self.process = None
        self.mode = None

    def _ensure_idle(self) -> None:
        if self.active:
            raise RuntimeError("An optimization process is already active")
