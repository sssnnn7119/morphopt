import sys
import os
import importlib.util
import numpy as np
from sympy.polys.subresultants_qq_zz import res
from traits.adaptation.tests.benchmark import target

# Add the path to your MorphOpt module
sys.path.append(os.getcwd())



import runpy
from MorphOpt import GLOBAL

import torch
torch.set_default_dtype(torch.float64)
torch.set_default_device('cpu')
os.environ['CUDA_LAUNCH_BLOCKING'] = '1'

def restart_optimization(restart_path, target_iteration=None):
    """
    Restart the optimization process from a specified iteration.

    Parameters:
    - restart_path: Path to the directory containing the previous optimization results.
    - target_iteration: The iteration number to restart from. If None, will restart from the last saved iteration.
    """

    GLOBAL.PATH.path_Code = os.getcwd() + '/MorphOpt/'
    GLOBAL.PATH.path_Queue = GLOBAL.PATH.path_Code + '/GenerateModel/_Rhino/TaskQueue/'
    GLOBAL.PATH.path_Result = restart_path

    GLOBAL.History.load(restart_path + '/log/')
    if target_iteration is None:
        target_iteration = GLOBAL.History.iteration
    GLOBAL.History.iteration = target_iteration
    GLOBAL.History.history_objective = GLOBAL.History.history_objective[:target_iteration]
    GLOBAL.History.history_time = GLOBAL.History.history_time[:target_iteration]
    
    sys.path.append(restart_path + '/scripts/Jobs/')
    import MAIN_SCRIPT_FOR_RESTART as MAIN_SCRIPT_FOR_RESTART
    
    params = MAIN_SCRIPT_FOR_RESTART.Params()

    params.load(filepath=restart_path + '/Log/', iteration=target_iteration)

    return params

if __name__ == "__main__":
    # Read the parameters from the restart path
    restart_path = "Z:/Results/T20250702202809_DefaultLabel/"
    target_iteration = None

    restart_optimization(restart_path = restart_path, 
                         target_iteration = target_iteration)