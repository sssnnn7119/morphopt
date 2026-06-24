def get_controller(path_result: str, iteration: int = None):
    """
    Load the controller from a specified result folder and iteration.

    Args:
        path_result (str): The folder path of the optimization result.
        iteration (int, optional): The iteration number to load. If None, the latest iteration will be loaded.

    Returns:
        ThisController: The controller instance loaded from the specified result folder and iteration.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)


    ThisController = MAIN_SCRIPT_FOR_RESTART.ThisController

    controller = ThisController()

    controller._load_history(path_result=path_result, target_iteration=iteration)

    return controller