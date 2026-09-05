import multiprocessing as mp


class TaskOptimization:
    @classmethod
    def task_optimization(cls, path_result: str = None,
                          main_filepath: str = None,
                          device: str = 'cpu',
                          target_iteration: int = None,
                          restart_per_iteration: int = 20):
        """Restart loop: run ``restart_per_iteration``-iteration chunks, then
        automatically continue from the latest iteration of the same folder.
        """
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)

        path_queue = mp.Queue()
        while True:
            process = mp.Process(target=cls.optmain, kwargs={'device': device,
                                                        'target_iteration': target_iteration,
                                                        'path_result': path_result,
                                                        'restart_per_iteration': restart_per_iteration,
                                                        'main_filepath': main_filepath,
                                                        'pathqueue': path_queue})
            process.start()
            try:
                process.join()  # Wait for process to finish
                if process.exitcode != 0:
                    print(f"Process failed with exit code {process.exitcode}, continuing...")
                    continue
                path_result = path_queue.get()
            except Exception as e:
                print(f"Error in process or queue: {e}, continuing...")
                continue
            target_iteration = None  # after first restart, always continue to the latest iteration

    @classmethod
    def optmain(cls, device='cpu', target_iteration: int = 0, path_result: str = None, restart_per_iteration: int = 20, main_filepath: str = None, pathqueue: mp.Queue = None):
        import os
        os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

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

        Controller: morphopt.Controller = getattr(__import__(filename), 'ThisController')

        controller: morphopt.Controller = Controller()
        controller.restart_per_iteration = restart_per_iteration
        controller.optdevice = device

        if target_iteration == 0 or path_result is None:
            controller.start_optimization(main_filepath=main_filepath)
        else:
            controller.restart_optimization(path_result=path_result, target_iteration=target_iteration)

        if pathqueue is not None:
            pathqueue.put(controller.path_result)
        return controller.path_result
