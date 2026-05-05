


def start_optimization(device='cpu', restart_per_iteration: int = 20, path_result: str=None, target_iteration=None, no_gui: bool=False):
    """
    Start a new optimization process.

    Args:
        Controller (type): The controller class to use for the optimization.
        device (str, optional): The device to use for computation. Defaults to 'cpu'.
        restart_per_iteration (int, optional): The number of iterations between restarts. Defaults to 20.
    """

    import multiprocessing as mp

    if path_result is None:
        import __main__
        main_filepath = __main__.__file__
    else:
        main_filepath = path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py'

    import time
    from .taskoptmization import TaskOptimization

    dataqueue = mp.Queue()
    process_optimization = mp.Process(target=TaskOptimization.task_optimization, kwargs={'path_result': path_result, 
                                                                                'main_filepath': main_filepath,
                                                                                'device': device, 
                                                                                'target_iteration': target_iteration,
                                                                                'restart_per_iteration': restart_per_iteration, 
                                                                                'dataqueue': dataqueue})
    process_optimization.start()

    if no_gui:
        process_optimization.join()
        return
    
    # Defer PyQt6 import until after the optimization process is forked/spawned
    # to avoid inheriting Qt/X11 connections in subprocesses
    from .taskui import run_ui
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
    import os
    import morphopt

    if path_result is None:
        import __main__
        main_filepath = __main__.__file__
    else:
        main_filepath = path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py'

    filename = os.path.splitext(os.path.basename(main_filepath))[0] 
    filepath = os.path.dirname(main_filepath)
    os.chdir(filepath)
    import sys
    sys.path.append(os.getcwd())

    Controller: morphopt.Controller = getattr(__import__(filename), 'ThisController')

    controller: morphopt.Controller = Controller()
    controller.restart_per_iteration = restart_per_iteration
    controller.optdevice = device

    TaskOptimization.optmain(device=device, 
                            path_result=path_result,
                            target_iteration=target_iteration,
                            restart_per_iteration=restart_per_iteration,
                            main_filepath=main_filepath)




