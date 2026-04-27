

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

import tempfile

import morphopt
import torch
import importlib.util
import matplotlib.pyplot as plt

torch.set_default_dtype(torch.float64)
torch.set_default_device('cuda:0')

def readhistoryparams(path_result: str, iteration: int = -1):
    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)


    Controller: morphopt.Controller = MAIN_SCRIPT_FOR_RESTART.ThisController

    controller: morphopt.Controller = Controller()

    controller._load_history(path_result=path_result, target_iteration=iteration)


    with tempfile.TemporaryDirectory(prefix='morphopt_') as tmpdir:
        fe = controller.params.create_feamodel(tmpdir + '/')


    return fe


if __name__ == "__main__":

    fe = readhistoryparams('Z:/Results/EXAMPLE_T20260423_164439/', iteration=1)
    fe.assembly._loads['pressure_1'].pressure = 0.06
    fe.solve()
