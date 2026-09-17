"""Spawn-based task supervision for optimization runs."""

from __future__ import annotations

import multiprocessing as mp
from multiprocessing.queues import Queue
from multiprocessing.sharedctypes import SynchronizedArray
from multiprocessing.synchronize import Event
import queue as queue_module
from pathlib import Path
from typing import Any, Callable

from .logging import get_logger
from .optcore.controller import Controller, RuntimeEvent
from .optcore.protocols import JsonValue

logger = get_logger(__name__)


def _task_process_entry(
    controller_factory: Callable[..., Controller],
    main_file_path: str | None,
    restart_path: str | None,
    target_iteration: int | None,
    event_queue: Queue,
    stop_event: Event,
    worker_restart_interval: int,
    result_path_buffer: SynchronizedArray,
) -> None:
    """Create a controller in a fresh process and execute one chunk.

    The V4 factory receives the queue and stop-event handles explicitly and
    returns a fully initialized Controller configuration object.
    """

    try:
        controller: Controller = controller_factory(data_queue=event_queue, stop_event=stop_event)
        controller._worker_restart_interval = worker_restart_interval
        if restart_path is None:
            controller.start_optimization(main_file_path)
        else:
            controller.restart_optimization(restart_path, target_iteration)
        _write_result_path(result_path_buffer, controller._result_path)
    except Exception as exc:
        event_queue.put(RuntimeEvent("failed", "child", payload={"error": repr(exc)}).to_dict())
        raise


class TaskRunner:
    """Parent-process supervisor that periodically recycles worker processes.

    A child performs one checkpoint chunk.  A ``restart_requested`` event
    causes the supervisor to start a fresh child from that checkpoint, while a
    normal completion or failure is returned to the caller unchanged.
    """

    def __init__(
        self,
        controller_factory: Callable[..., Controller],
        *,
        main_file_path: str | Path | None = None,
        restart_path: str | Path | None = None,
        target_iteration: int | None = None,
        event_queue: Queue | None = None,
        worker_restart_interval: int = 20,
    ) -> None:
        self._controller_factory = controller_factory
        """Factory used inside each spawned worker."""
        self._main_file_path = str(main_file_path) if main_file_path is not None else None
        """Task source snapshot path."""
        self._restart_path = str(restart_path) if restart_path is not None else None
        """Checkpoint used for continuation."""
        self._target_iteration = target_iteration
        """Optional checkpoint iteration to restore."""
        context = mp.get_context("spawn")
        self._event_queue = event_queue if event_queue is not None else context.Queue()
        """Structured worker events."""
        self._worker_restart_interval = int(worker_restart_interval)
        """Iterations per worker chunk."""
        self._process: mp.Process | None = None
        """Supervisor process handle."""
        self._exit_code: int | None = None
        """Last worker/supervisor exit code."""
        self._result_path: Path | None = Path(restart_path) if restart_path is not None else None
        """Active checkpoint path."""
        self._stop_event = context.Event()
        """Cross-process graceful-stop signal."""
        self._result_path_buffer = context.Array("u", 4096)
        """Shared result path written by the worker and read by the parent."""
        self._restart_count = 0
        """Number of recycled worker chunks."""

    @property
    def process(self) -> mp.Process | None:
        return self._process

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    @property
    def result_path(self) -> Path | None:
        return self._result_path

    @property
    def event_queue(self) -> Queue:
        return self._event_queue

    def start(self) -> None:
        """Start the supervisor in a spawn process and return immediately."""
        if self._process is not None and self._process.is_alive():
            raise RuntimeError("TaskRunner is already running")
        self._process = mp.get_context("spawn").Process(target=self._run_supervisor, daemon=False)
        self._process.start()

    def run_debug(self) -> int:
        """Run one task directly in the current process for debugging."""
        try:
            self._configure_child_environment()
            self._run_task()
            self._exit_code = 0
        except Exception as exc:
            self._publish_failure(exc)
            self._exit_code = 1
        return int(self._exit_code or 0)

    def request_stop(self) -> None:
        """Signal the child and wait briefly for graceful termination."""
        self._stop_event.set()
        if self._process is not None and self._process.is_alive():
            self._process.join(timeout=2)

    def wait(self, timeout: float | None = None) -> int | None:
        """Wait for the supervisor and return its exit code when known."""
        if self._process is None:
            return self._exit_code
        self._process.join(timeout)
        if self._process.exitcode is not None:
            self._exit_code = self._process.exitcode
            self._read_shared_result_path()
        return self._exit_code

    def get_result_path(self) -> Path | None:
        """Return the result directory discovered from the run events."""
        self._read_shared_result_path()
        return self._result_path

    def _run_supervisor(self) -> None:
        """Recycle child workers until completion, failure or stop."""
        context = mp.get_context("spawn")
        restart_path = self._restart_path
        target_iteration = self._target_iteration
        while not self._stop_event.is_set():
            worker_event_queue = context.Queue()
            worker = context.Process(
                target=_task_process_entry,
                args=(self._controller_factory, self._main_file_path, restart_path, target_iteration, worker_event_queue, self._stop_event, self._worker_restart_interval, self._result_path_buffer),
                daemon=False,
            )
            worker.start()
            restart_event = self._monitor_worker(worker, worker_event_queue)
            self._exit_code = worker.exitcode
            if self._stop_event.is_set():
                self._exit_code = 2
                break
            if restart_event is not None:
                self._restart_count += 1
                restart_path = str(restart_event.get("result_path")) if restart_event.get("result_path") else restart_path
                target_iteration = int(restart_event.get("iteration", -1))
                continue
            if worker.exitcode == 0:
                self._exit_code = 0
                break
            # A failed chunk is surfaced to the caller.  Checkpoint restart is
            # requested explicitly by Controller through the event stream.
            self._exit_code = 1
            break
        if self._stop_event.is_set() and self._exit_code is None:
            self._exit_code = 2
        # ``multiprocessing.Process`` does not propagate a target return
        # value.  Make the supervisor status the actual child exit code so
        # the parent can distinguish success, stop and worker failure.
        raise SystemExit(int(self._exit_code or 0))

    def _forward_worker_events(self, worker_event_queue: Queue) -> dict[str, JsonValue] | None:
        """Forward worker events to the parent and return a restart payload."""
        restart_payload: dict[str, JsonValue] | None = None
        first = True
        while True:
            try:
                event = worker_event_queue.get(timeout=0.2 if first else 0.02)
            except queue_module.Empty:
                return restart_payload
            first = False
            self._event_queue.put(event)
            if isinstance(event, dict) and event.get("event_type") == "restart_requested":
                restart_payload = dict(event.get("payload", {}))

    def _monitor_worker(self, worker: mp.Process, worker_event_queue: Queue) -> dict[str, JsonValue] | None:
        """Forward events while a worker is running, then drain its tail."""
        restart_payload: dict[str, JsonValue] | None = None
        while worker.is_alive():
            try:
                event = worker_event_queue.get(timeout=0.1)
            except queue_module.Empty:
                continue
            self._event_queue.put(event)
            if isinstance(event, dict) and event.get("event_type") == "restart_requested":
                restart_payload = dict(event.get("payload", {}))
        worker.join()
        tail_payload = self._forward_worker_events(worker_event_queue)
        return tail_payload if tail_payload is not None else restart_payload

    def _run_task(self) -> None:
        """Execute the configured child entry directly."""
        _task_process_entry(self._controller_factory, self._main_file_path, self._restart_path, self._target_iteration, self._event_queue, self._stop_event, self._worker_restart_interval, self._result_path_buffer)
        self._read_shared_result_path()

    def _read_shared_result_path(self) -> None:
        """Read a result path published by a spawned worker."""
        raw = "".join(self._result_path_buffer[:])
        value = raw.split("\0", 1)[0].strip()
        if value:
            self._result_path = Path(value)

    def _publish_failure(self, error: BaseException) -> None:
        """Publish a structured runner-side failure event."""
        self._event_queue.put(RuntimeEvent("failed", "runner", payload={"error": repr(error)}).to_dict())

    def _configure_child_environment(self) -> None:
        """Reserve the hook for thread limits and device affinity."""
        # TODO: Set thread limits/device affinity before importing TorchFEA.
        return None


def start_optimization(controller_factory: Callable[..., Controller], main_file_path: str | Path | None = None, *, debug: bool = False, **kwargs: Any) -> TaskRunner:
    """Create and start a supervised task runner.

    The returned runner remains available to the caller for event polling and
    stop requests.  ``debug=True`` executes the worker in the current process.
    """

    runner = TaskRunner(controller_factory, main_file_path=main_file_path, **kwargs)
    if debug:
        runner.run_debug()
    else:
        runner.start()
    return runner


def _write_result_path(buffer: SynchronizedArray, path: Path) -> None:
    """Write a result path into the fixed-size cross-process character array."""
    value = str(path)
    if len(value) >= len(buffer):
        raise ValueError("Result path exceeds TaskRunner shared path buffer")
    with buffer.get_lock():
        buffer[:] = "\0" * len(buffer)
        buffer[: len(value)] = value


__all__ = ["RuntimeEvent", "TaskRunner", "start_optimization"]
