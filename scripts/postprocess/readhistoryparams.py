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


    path_result = 'Z:/Results/EXAMPLE_T20260420_190258'
    
    controller: morphopt.Controller = readhistoryparams(path_result, 55)

    mat: morphopt.codesign.CodesignMaterials = controller.params.materials

    quiry_points = np.meshgrid(np.linspace(-20, 20, 50), np.linspace(-20, 20, 50), np.linspace(0, 50, 50))

    quiry_points = np.stack(quiry_points, axis=-1).reshape(-1, 3)

    cps = mat.get_ratio(torch.from_numpy(quiry_points))

    mask = quiry_points[:, 0]**2 + quiry_points[:, 1]**2 < 20**2
    cps = cps[mask] * mat._mumax

    plt.figure()
    plt.hist(cps, bins=50, color='tab:blue', edgecolor='black', density=True)
    plt.title('CPS Distribution Histogram')
    plt.xlabel('CPS value')
    plt.ylabel('Frequency')
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.show()

    raise Exception("For Debugging Only")