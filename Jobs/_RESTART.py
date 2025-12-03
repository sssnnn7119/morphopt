import sys
import os
import importlib.util
import numpy as np

# Add the path to your MorphOpt module
sys.path.append(os.getcwd())



import runpy
from MorphOpt import GLOBAL

import torch

os.environ['CUDA_LAUNCH_BLOCKING'] = '1'

def restart_optimization(restart_path, target_iteration=None):
    """
    Restart the optimization process from a specified iteration.

    Parameters:
    - restart_path: Path to the directory containing the previous optimization results.
    - target_iteration: The iteration number to restart from. If None, will restart from the last saved iteration.
    """

    GLOBAL.PATH.path_Code = os.getcwd() + '/MorphOpt/'
    GLOBAL.PATH.path_Queue = GLOBAL.PATH.path_Code + '/modelparams/geometry/_Rhino/taskqueue/'
    GLOBAL.PATH.path_Result = restart_path

    GLOBAL.History.load_csv(restart_path + '/log/')
    if target_iteration is None:
        target_iteration = GLOBAL.History.iteration
    GLOBAL.History.iteration = target_iteration
    GLOBAL.History.history_num_nodes = GLOBAL.History.history_num_nodes[:target_iteration]
    GLOBAL.History.history_num_elements = GLOBAL.History.history_num_elements[:target_iteration]
    GLOBAL.History.history_objective = GLOBAL.History.history_objective[:target_iteration]
    GLOBAL.History.history_time = GLOBAL.History.history_time[:target_iteration]
    GLOBAL.History.history_deformation = GLOBAL.History.history_deformation[:target_iteration]
    
    sys.path.append(restart_path + '/scripts/Jobs/')
    import MAIN_SCRIPT_FOR_RESTART as MAIN_SCRIPT_FOR_RESTART # type: ignore
    
    params = MAIN_SCRIPT_FOR_RESTART.Params()
    solver = MAIN_SCRIPT_FOR_RESTART.Solver(params=params)
    updater = MAIN_SCRIPT_FOR_RESTART.Updater(params=params)
    controller = MAIN_SCRIPT_FOR_RESTART.Controller(params=params, 
                                                    solver=solver, 
                                                    updater=updater)
    params.initialize(0)
    params.load(filepath=restart_path + '/Log/', iteration=target_iteration)
    controller.opt_loop()

if __name__ == "__main__":
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')
    restart_optimization(restart_path = "Z:/Results/JUMP_T2025-12-02_14-17-23/", 
                         target_iteration = None)  
