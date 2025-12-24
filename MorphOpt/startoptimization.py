
import time
import MorphOpt
import torch
import multiprocessing
from multiprocessing import Queue

def restart_optimization(restart_path, target_iteration=None, device='cpu', restart_per_iteration: int = 20):
    import os
    os.environ['KMP_DUPLICATE_LIB_OK']='True'
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    torch.set_default_dtype(torch.float64)
    torch.set_default_device(device)

    import importlib.util
    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", restart_path + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)

    Controller: MorphOpt.Controller = MAIN_SCRIPT_FOR_RESTART.ThisController

    process = multiprocessing.Process(target=main, kwargs={'Controller': Controller, 
                                                           'device': device, 
                                                           'target_iteration': target_iteration, 
                                                           'restart_path': restart_path, 
                                                           'restart_per_iteration': restart_per_iteration, 
                                                           'main_filepath': None, 
                                                           'queue': None})
    process.start()
    process.join()

    while True:
        process = multiprocessing.Process(target=main, kwargs={'Controller': Controller, 
                                                               'device': device, 
                                                               'target_iteration': None, 
                                                               'restart_path': restart_path, 
                                                               'restart_per_iteration': restart_per_iteration, 
                                                               'main_filepath': None, 
                                                               'queue': None})
        process.start()
        process.join()


def start_optimization(Controller: type, device='cpu', restart_per_iteration: int = 20):

    import __main__
    main_filepath = __main__.__file__

    queue = Queue()
    process = multiprocessing.Process(target=main, kwargs={'Controller': Controller, 
                                                           'device': device, 
                                                           'target_iteration': None, 
                                                           'restart_path': None, 
                                                           'restart_per_iteration': restart_per_iteration, 
                                                           'main_filepath': main_filepath, 
                                                           'queue': queue})
    process.start()
    process.join()
    path_result = queue.get()

    while True:
        process = multiprocessing.Process(target=main, kwargs={'Controller': Controller, 
                                                               'device': device, 
                                                               'target_iteration': None, 
                                                               'restart_path': path_result, 
                                                               'restart_per_iteration': restart_per_iteration, 
                                                               'main_filepath': None, 
                                                               'queue': None})
        process.start()
        process.join()

def main(Controller: type, device='cpu', target_iteration: int = 0, restart_path: str = None, restart_per_iteration: int = 20, main_filepath: str = None, queue: Queue = None):
    import os
    os.environ['KMP_DUPLICATE_LIB_OK']='True'
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    torch.set_default_dtype(torch.float64)
    torch.set_default_device(device)
    controller: MorphOpt.Controller = Controller()
    controller.restart_per_iteration = restart_per_iteration

    if target_iteration == 0 or restart_path is None:
        controller.start_optimization(main_filepath=main_filepath)
    else: 
        controller.restart_optimization(restart_path=restart_path, target_iteration=target_iteration)

    if queue is not None:
        queue.put(controller.path_result)
    return controller.path_result