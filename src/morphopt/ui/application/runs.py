"""Optimization-process lifecycle independent from observer widgets."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .. import launcher
from ..i18n import localized_message
from ..model.problem import ProblemDefinition
from ...postprocess import last_completed_iteration
from .definitions import ProblemLibrary


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
        self.definition: ProblemDefinition | None = None
        self._running_definition: ProblemDefinition | None = None
        self.source: RunSource | None = None
        self.last_iteration = 0
        self._save_definition = True
        self._saved_folders: set[str] = set()
        self.output_id = 0
        self.log = RunLog()

    @property
    def active(self) -> bool:
        """Whether the observer still owns a process awaiting final polling."""
        return self.process is not None

    def set_definition(self, problem: ProblemDefinition) -> None:
        """Stage an independent definition for the next run without stopping this one."""
        self.definition = ProblemDefinition.from_dict(problem.to_dict())
        if not self.active:
            self.source = None

    def select_source(self, source: RunSource) -> None:
        self._ensure_idle()
        if source.kind is RunSourceKind.CONTINUE:
            if not self.is_result_folder(source.path):
                raise ValueError(localized_message("ui.errors.runs.missing_scripts_main_script_for_restart_py_in_the_selected"))
            self.adopt(source.path)
        else:
            self.clear_result()
            self._save_definition = source.kind is RunSourceKind.DEFINITION
        self.source = source

    def start_selected(self, target_iteration: int | None = None) -> subprocess.Popen:
        source = self.source
        if source is None:
            raise ValueError(localized_message("ui.errors.runs.select_a_task_source_first"))
        if source.kind is RunSourceKind.DEFINITION:
            if self.definition is None:
                raise ValueError(localized_message("ui.errors.runs.no_definition_is_bound_to_this_run"))
            process = self.start_definition(self.definition)
        elif source.kind is RunSourceKind.PYTHON:
            process = self.start_python(source.path)
        else:
            process = self.start_continue(source.path, target_iteration)
        self.last_iteration = (target_iteration or 0) if source.kind is RunSourceKind.CONTINUE else 0
        self.source = None
        return process

    def poll(self) -> RunProgress:
        previous = self.folder
        if self.mode is RunMode.FRESH:
            self.discover_folder()
        if self.active and self.folder and self._save_definition and self._running_definition is not None and self.folder not in self._saved_folders:
            try:
                ProblemLibrary.save_result_copy(self._running_definition, self.folder)
            except (OSError, ValueError, TypeError) as exc:
                import logging
                logging.getLogger(__name__).warning("Cannot save the result definition: %s", exc)
            else:
                self._saved_folders.add(self.folder)
        iteration = last_completed_iteration(self.folder) if self.folder else 0
        changed = previous != self.folder or iteration != self.last_iteration
        self.last_iteration = iteration
        exit_code = self.process.poll() if self.process is not None else None
        finished = exit_code is not None
        if finished:
            self.release_finished()
        return RunProgress(self.folder, iteration, changed, finished, exit_code)

    def stream_output(self, callback) -> None:
        """Read the worker pipe off the UI thread; callback receives run id and text."""
        import threading
        self.output_id += 1
        self.log.clear()
        process, output_id = self.process, self.output_id
        if process is None or process.stdout is None:
            return
        stream = process.stdout
        def read() -> None:
            try:
                for raw in iter(stream.readline, b""):
                    callback(output_id, raw.decode("utf-8", errors="replace"))
            finally:
                stream.close()
        threading.Thread(target=read, name="morphopt-ui-output-reader", daemon=True).start()

    def consume_output(self, output_id: int, text: str) -> str | None:
        return self.log.consume(text) if output_id == self.output_id else None

    def adopt(self, folder: str) -> None:
        self._ensure_idle()
        self.folder = str(Path(folder).resolve())
        self.last_iteration = 0
        self.process = None
        self.mode = None

    def clear_result(self) -> None:
        """Forget the browsed result before selecting a fresh task source."""
        self._ensure_idle()
        self.folder = None
        self.fresh_root = ""
        self.fresh_label = ""
        self.started_at = 0.0
        self.last_iteration = 0

    def start_definition(self, problem: ProblemDefinition) -> subprocess.Popen:
        self._ensure_idle()
        definition = ProblemDefinition.from_dict(problem.to_dict())
        started_at = time.time()
        _job, process = launcher.run_job(definition)
        self._save_definition = True
        self.definition = definition
        self._running_definition = definition
        self._saved_folders.clear()
        self.source = None
        self.last_iteration = 0
        self.process = process
        self.mode = RunMode.FRESH
        self.folder = None
        self.fresh_root = launcher.run_root_for(problem)
        self.fresh_label = launcher.sanitize_name(problem.label)
        self.started_at = started_at
        return process

    def start_python(self, path: str) -> subprocess.Popen:
        self._ensure_idle()
        started_at = time.time()
        root, label, process = launcher.run_py_definition(path)
        self._save_definition = False
        self._running_definition = None
        self.source = None
        self.last_iteration = 0
        self.process = process
        self.mode = RunMode.FRESH
        self.folder = None
        self.fresh_root = root
        self.fresh_label = label
        self.started_at = started_at
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
        self._save_definition = False
        self._running_definition = None
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
        """Stop the worker and retain its last saved result as a resumable task."""
        if not self.active:
            return
        if self.mode is RunMode.FRESH:
            self.discover_folder()
        launcher.stop_job(self.process)
        # A fresh worker may create its result folder while it is stopping.
        if self.mode is RunMode.FRESH:
            self.discover_folder()
        self.process = None
        self.mode = None
        self.last_iteration = last_completed_iteration(self.folder) if self.folder else 0
        if self.folder and self.is_result_folder(self.folder) and self.last_iteration > 0:
            # Selecting via adopt() would reset progress for the displayed result.
            self.source = RunSource(
                RunSourceKind.CONTINUE,
                path=self.folder,
                label=Path(self.folder).name,
            )
        else:
            self.source = None

    def _ensure_idle(self) -> None:
        if self.active:
            raise RuntimeError(localized_message("ui.errors.runs.an_optimization_process_is_already_active"))


@dataclass(frozen=True)
class RunProgress:
    folder: str | None
    iteration: int
    changed: bool
    finished: bool = False
    exit_code: int | None = None


class RunLog:
    """Normalize terminal redraws into a text log with stable table headers."""
    def __init__(self):
        self.headers: set[str] = set()

    def clear(self) -> None:
        self.headers.clear()

    def consume(self, text: str) -> str | None:
        import re
        redraw = bool(re.search(r"\x1b\[[0-9;]*[ABEFG]", text))
        line = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[@-_])", "", text).replace("\r\n", "\n")
        line = line.rsplit("\r", 1)[-1].rstrip("\n")
        if not line:
            return None
        words = line.strip().lower().split()
        if len(words) >= 3 and words[0] == "iter" and "total" in words:
            key = " ".join(line.split())
            if redraw and key in self.headers:
                return None
            self.headers.add(key)
        return line
