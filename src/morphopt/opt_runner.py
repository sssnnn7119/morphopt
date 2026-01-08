


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

def view_optimization_result(path_result: str = None):
    """
    View the result of an optimization process.

    Args:
        path_result (str): The folder path of the optimization result.
    """
    import os
    import multiprocessing as mp
    from .taskui import run_ui
    from .optcore.history import History

    if path_result is None or not os.path.exists(path_result):
        # Use file dialog to select directory if path is not provided
        # We need a temporary app to show the dialog
        from PyQt6.QtWidgets import QApplication, QFileDialog
        import sys
        
        # Check if an app instance already exists
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        
        path_result = QFileDialog.getExistingDirectory(None, "Select Optimization Result Folder", os.getcwd())
        if not path_result:
            return

    main_filepath = os.path.join(path_result, 'scripts', 'MAIN_SCRIPT_FOR_RESTART.py')
    if not os.path.exists(main_filepath):
        print(f"Error: {main_filepath} not found.")
        return

    # Determine the last iteration
    history = History()
    try:
        history.load(foldpath=os.path.join(path_result, 'log'))
        last_iteration = history.iteration
    except:
        last_iteration = 0

    dataqueue = mp.Queue()
    # Send the initial data to load the result
    dataqueue.put({'iteration': last_iteration, 'path_result': path_result})

    run_ui(dataqueue, main_filepath)

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




