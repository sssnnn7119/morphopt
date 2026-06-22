import importlib
from . import Controller

def get_controller(path_result: str, iteration: int = None):
    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)


    ThisController = MAIN_SCRIPT_FOR_RESTART.ThisController

    controller: Controller = ThisController()

    controller._load_history(path_result=path_result, target_iteration=iteration)

    return controller