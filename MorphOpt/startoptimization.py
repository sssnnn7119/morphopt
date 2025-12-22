
import MorphOpt
import torch

def restart_optimization(restart_path, target_iteration=None, device='cpu'):
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

    controller: MorphOpt.Controller = MAIN_SCRIPT_FOR_RESTART.ThisController()
    
    controller.restart_optimization(restart_path=restart_path,
                                    target_iteration=target_iteration)

def start_optimization(Controller: type, device='cpu'):
    import os
    os.environ['KMP_DUPLICATE_LIB_OK']='True'
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    torch.set_default_dtype(torch.float64)
    torch.set_default_device(device)
    controller: MorphOpt.Controller = Controller()
    controller.start_optimization()

