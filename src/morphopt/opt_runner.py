"""Optimization entry points, worker execution and checkpoint restart loop."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
from multiprocessing.queues import Queue

logger = logging.getLogger(__name__)


def _main_script(path_result: str | None) -> str:
    """Locate the initial task or the archived script of a resumed run."""
    if path_result is None:
        import __main__

        return __main__.__file__
    return os.path.join(path_result, "scripts", "MAIN_SCRIPT_FOR_RESTART.py")


def start_optimization(
    device: str = "cpu",
    restart_per_iteration: int = 20,
    path_result: str | None = None,
    target_iteration: int | None = None,
) -> None:
    """Run optimization in spawned processes and resume each completed segment.

    ``path_result`` selects an existing run; otherwise the task in ``__main__``
    starts a new run. ``target_iteration=None`` resumes its latest checkpoint.
    """
    mp.set_start_method("spawn", force=True)
    process = mp.Process(
        target=_run_task,
        kwargs={
            "path_result": path_result,
            "main_filepath": _main_script(path_result),
            "device": device,
            "target_iteration": target_iteration,
            "restart_per_iteration": restart_per_iteration,
        },
    )
    process.start()
    process.join()
    exitcode = process.exitcode
    process.close()
    if exitcode != 0:
        raise ChildProcessError(f"Optimization task failed with exit code {exitcode}.")


def debug_optimization(
    device: str = "cpu",
    restart_per_iteration: int = 20,
    path_result: str | None = None,
    target_iteration: int | None = None,
) -> None:
    """Run the task in the current process with serial, debugger-friendly FEA."""
    mp.set_start_method("spawn", force=True)
    _run_worker(
        device=device,
        path_result=path_result,
        target_iteration=target_iteration,
        restart_per_iteration=restart_per_iteration,
        main_filepath=_main_script(path_result),
        debug=True,
    )


def _run_task(
    path_result: str | None,
    main_filepath: str,
    device: str = "cpu",
    target_iteration: int | None = None,
    restart_per_iteration: int = 20,
) -> None:
    """Continue worker segments from the latest completed checkpoint."""
    import warnings
    from queue import Empty

    from .optcore.history import History

    warnings.filterwarnings("ignore", category=UserWarning)
    completed = 0
    if path_result is not None:
        history = History()
        history.load(foldpath=path_result + "/log/", iteration=target_iteration)
        completed = history.iteration
    path_queue = mp.Queue()
    try:
        while True:
            process = mp.Process(
                target=_run_worker,
                kwargs={
                    "device": device,
                    "target_iteration": target_iteration,
                    "path_result": path_result,
                    "restart_per_iteration": restart_per_iteration,
                    "main_filepath": main_filepath,
                    "pathqueue": path_queue,
                },
            )
            process.start()
            # Drain checkpoints while the worker is alive so its queue feeder
            # cannot block shutdown while the supervisor waits for completion.
            while True:
                try:
                    progress = path_queue.get(timeout=0.1)
                except Empty:
                    if process.is_alive():
                        continue
                    break
                path_result = progress["path_result"]
                completed = progress["iteration"]
            process.join()
            exitcode = process.exitcode
            process.close()
            if exitcode != 0:
                if completed == 0:
                    raise ChildProcessError(
                        "Optimization failed before the first completed iteration "
                        f"(exit code {exitcode}). See the worker traceback."
                    )
                print(f"Process failed with exit code {exitcode}, continuing...")
            target_iteration = None
    finally:
        path_queue.close()
        path_queue.join_thread()


def _run_worker(
    main_filepath: str,
    device: str = "cpu",
    target_iteration: int | None = None,
    path_result: str | None = None,
    restart_per_iteration: int = 20,
    pathqueue: Queue | None = None,
    debug: bool = False,
) -> str:
    """Load one task and run a new or restored controller in this process."""
    os.environ["KMP_DUPLICATE_LIB_OK"] = "True"
    import sys
    import warnings

    import torch

    import morphopt

    warnings.filterwarnings("ignore", category=UserWarning)
    torch.set_default_dtype(torch.float64)
    torch.set_default_device(device)
    filename = os.path.splitext(os.path.basename(main_filepath))[0]
    os.chdir(os.path.dirname(main_filepath))
    sys.path.append(os.getcwd())
    controller_class = __import__(filename).ThisController
    controller: morphopt.Controller = controller_class()
    controller.restart_per_iteration = restart_per_iteration
    controller.optdevice = device
    controller.dataqueue = pathqueue
    controller._debug_mode = debug
    try:
        if target_iteration == 0 or path_result is None:
            controller.start_optimization(main_filepath=main_filepath)
        else:
            controller.restart_optimization(
                path_result=path_result, target_iteration=target_iteration
            )
    except Exception:
        logger.exception(
            "Optimization worker failed; result folder: %s", controller.path_result
        )
        raise
    return controller.path_result
