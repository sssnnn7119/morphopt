import multiprocessing as mp


class TaskOptimization:
    @classmethod
    def task_optimization(
        cls,
        path_result: str = None,
        main_filepath: str = None,
        device: str = "cpu",
        target_iteration: int = None,
        restart_per_iteration: int = 20,
    ):
        """Restart loop: run ``restart_per_iteration``-iteration chunks, then
        automatically continue from the latest iteration of the same folder.
        """
        import warnings

        warnings.filterwarnings("ignore", category=UserWarning)

        from queue import Empty
        from .optcore.history import History

        completed = 0
        if path_result is not None:
            history = History()
            history.load(foldpath=path_result + "/log/", iteration=target_iteration)
            completed = history.iteration
        path_queue = mp.Queue()
        try:
            while True:
                process = mp.Process(
                    target=cls.optmain,
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
                # Drain completed-checkpoint notifications while the worker is
                # alive, so its queue feeder cannot block process shutdown.
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
                            f"Optimization failed before the first completed iteration "
                            f"(exit code {exitcode}). See the worker traceback."
                        )
                    print(f"Process failed with exit code {exitcode}, continuing...")
                target_iteration = None
        finally:
            path_queue.close()
            path_queue.join_thread()

    @classmethod
    def optmain(
        cls,
        device="cpu",
        target_iteration: int = 0,
        path_result: str = None,
        restart_per_iteration: int = 20,
        main_filepath: str = None,
        pathqueue: mp.Queue = None,
    ):
        import os

        os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

        import warnings

        warnings.filterwarnings("ignore", category=UserWarning)

        import torch

        torch.set_default_dtype(torch.float64)
        torch.set_default_device(device)

        import morphopt

        filename = os.path.splitext(os.path.basename(main_filepath))[0]
        filepath = os.path.dirname(main_filepath)
        os.chdir(filepath)
        import sys

        sys.path.append(os.getcwd())

        Controller: morphopt.Controller = __import__(filename).ThisController

        controller: morphopt.Controller = Controller()
        controller.restart_per_iteration = restart_per_iteration
        controller.optdevice = device
        controller.dataqueue = pathqueue

        if target_iteration == 0 or path_result is None:
            controller.start_optimization(main_filepath=main_filepath)
        else:
            controller.restart_optimization(
                path_result=path_result, target_iteration=target_iteration
            )

        return controller.path_result
