


def start_optimization(device='cpu', restart_per_iteration: int = 20, path_result: str=None, target_iteration=None, ):
    """
    Start a new optimization process.

    Args:
        Controller (type): The controller class to use for the optimization.
        device (str, optional): The device to use for computation. Defaults to 'cpu'.
        restart_per_iteration (int, optional): The number of iterations between restarts. Defaults to 20.
    """
    if path_result is None:
        import __main__
        main_filepath = __main__.__file__
    else:
        main_filepath = path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py'

    import time
    import multiprocessing as mp
    from .taskoptmization import TaskOptimization
    from .taskui import run_ui


    dataqueue = mp.Queue()
    process_optimization = mp.Process(target=TaskOptimization.task_optimization, kwargs={'path_result': path_result, 
                                                                                'main_filepath': main_filepath,
                                                                                'device': device, 
                                                                                'target_iteration': target_iteration,
                                                                                'restart_per_iteration': restart_per_iteration, 
                                                                                'dataqueue': dataqueue})
    process_optimization.start()

    process_ui = mp.Process(target=run_ui, args=(dataqueue, main_filepath))
    process_ui.start()

    process_optimization.join()
    process_ui.join()

def debug_optimization(device='cpu', restart_per_iteration: int = 20, path_result: str=None, target_iteration=None, ):
    """
    Start a new optimization process.

    Args:
        Controller (type): The controller class to use for the optimization.
        device (str, optional): The device to use for computation. Defaults to 'cpu'.
        restart_per_iteration (int, optional): The number of iterations between restarts. Defaults to 20.
    """
    import __main__
    from .taskoptmization import TaskOptimization
    main_filepath = __main__.__file__
    TaskOptimization.optmain(device=device, 
                            path_result=path_result,
                            target_iteration=target_iteration,
                            restart_per_iteration=restart_per_iteration,
                            main_filepath=main_filepath)




