import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

import numpy as np
from torchfea import inp

import morphopt
import torch
import importlib.util
import matplotlib.pyplot as plt

torch.set_default_dtype(torch.float64)
torch.set_default_device('cpu')


def readhistoryparams(path_result: str, iteration: int = -1) -> morphopt.Params:
    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)


    Controller: morphopt.Controller = MAIN_SCRIPT_FOR_RESTART.ThisController

    controller: morphopt.Controller = Controller()

    controller._load_history(path_result=path_result, target_iteration=iteration)


    return controller

if __name__ == "__main__":


    path_result = 'Z:/Results/Twist_Energy_T20260512_141203/'
    
    controller: morphopt.Controller = readhistoryparams(path_result, 216)

    fe = controller.params.create_feamodel()

    mat: morphopt.SIMPMaterials = controller.params.materials
    
    plotter = mat.plot()

    controller.params.geometry.plot(plotter=plotter, opacity=[0.0, 1.0])

    plotter.show()

