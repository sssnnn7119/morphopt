

import morphopt
import torch
import importlib.util
torch.set_default_dtype(torch.float64)
torch.set_default_device('cpu')


def readhistoryparams(path_result: str) -> morphopt.Params:
    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)
    
    params: morphopt.Params = MAIN_SCRIPT_FOR_RESTART.ThisController.Params()

    return params

if __name__ == "__main__":


    path_result = 'Z:/Results/FRONT_T20260128_104510/'
    
    params: morphopt.Params = readhistoryparams(path_result)



    raise Exception("For Debugging Only")