
import time
import multiprocessing as mp



def start_optimization(device='cpu', restart_per_iteration: int = 20, path_result: str=None, target_iteration=None, ):
    """
    Start a new optimization process.

    Args:
        Controller (type): The controller class to use for the optimization.
        device (str, optional): The device to use for computation. Defaults to 'cpu'.
        restart_per_iteration (int, optional): The number of iterations between restarts. Defaults to 20.
    """
    dataqueue = mp.Queue()
    process_optimization = mp.Process(target=TaskOptimization.task_optimization, kwargs={'path_result': path_result, 
                                                                                'device': device, 
                                                                                'target_iteration': target_iteration,
                                                                                'restart_per_iteration': restart_per_iteration, 
                                                                                'dataqueue': dataqueue})
    process_optimization.start()

    while True:
        time.sleep(1)
        if not dataqueue.empty():
            data = dataqueue.get()
            print(data)

    process_optimization.join()

def debug_optimization(device='cpu', restart_per_iteration: int = 20, path_result: str=None, target_iteration=None, ):
    """
    Start a new optimization process.

    Args:
        Controller (type): The controller class to use for the optimization.
        device (str, optional): The device to use for computation. Defaults to 'cpu'.
        restart_per_iteration (int, optional): The number of iterations between restarts. Defaults to 20.
    """
    import __main__
    main_filepath = __main__.__file__
    TaskOptimization.optmain(device=device, 
                            path_result=path_result,
                            target_iteration=target_iteration,
                            restart_per_iteration=restart_per_iteration,
                            main_filepath=main_filepath)


class TaskOptimization:
    @classmethod
    def task_optimization(cls, path_result: str = None, 
                            device: str = 'cpu', 
                            target_iteration: int = None,
                            restart_per_iteration: int = 20, 
                            dataqueue: mp.Queue = None):
        

        if path_result is None:
            import __main__
            main_filepath = __main__.__file__
        else:
            main_filepath = path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py'

        path_queue = mp.Queue()
        while True:
            process = mp.Process(target=cls.optmain, kwargs={'device': device, 
                                                        'target_iteration': target_iteration, 
                                                        'path_result': path_result, 
                                                        'restart_per_iteration': restart_per_iteration, 
                                                        'main_filepath': main_filepath, 
                                                        'pathqueue': path_queue,
                                                        'dataqueue': dataqueue})
            process.start()
            process.join()
            path_result = path_queue.get()
            target_iteration = None  # after first restart, always continue to the latest iteration

    @classmethod
    def optmain(cls, device='cpu', target_iteration: int = 0, path_result: str = None, restart_per_iteration: int = 20, main_filepath: str = None, pathqueue: mp.Queue = None, dataqueue: mp.Queue = None):
        import os
        os.environ['KMP_DUPLICATE_LIB_OK']='True'

        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)

        import torch
        torch.set_default_dtype(torch.float64)
        torch.set_default_device(device)

        import MorphOpt

        filename = os.path.splitext(os.path.basename(main_filepath))[0] 
        filepath = os.path.dirname(main_filepath)
        os.chdir(filepath)
        import sys
        sys.path.append(os.getcwd())

        

        Controller: MorphOpt.Controller = getattr(__import__(filename), 'ThisController')

        controller: MorphOpt.Controller = Controller()
        controller.restart_per_iteration = restart_per_iteration

        if target_iteration == 0 or path_result is None:
            controller.start_optimization(main_filepath=main_filepath)
        else: 
            controller.restart_optimization(path_result=path_result, target_iteration=target_iteration)

        if pathqueue is not None:
            pathqueue.put(controller.path_result)
        if dataqueue is not None:
            dataqueue.put(f"Optimization finished at {controller.path_result}")
        return controller.path_result
