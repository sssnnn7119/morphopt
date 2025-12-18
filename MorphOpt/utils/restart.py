
import sys
from .. import GLOBAL
import os
from ..opt_loop import Controller
import MorphOpt
def restart_optimization(restart_path, target_iteration=None) -> Controller:
    """
    Restart the optimization process from a specified iteration.

    Parameters:
    - restart_path: Path to the directory containing the previous optimization results.
    - target_iteration: The iteration number to restart from. If None, will restart from the last saved iteration.
    """

    GLOBAL.PATH.path_Code = os.getcwd() + '/MorphOpt/'
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
    
    params: MorphOpt._Params = MAIN_SCRIPT_FOR_RESTART.Params()
    solver: MorphOpt._MorphSolver = MAIN_SCRIPT_FOR_RESTART.Solver(params=params)
    updater: MorphOpt._Updaters = MAIN_SCRIPT_FOR_RESTART.Updater(params=params)
    controller: MorphOpt._Controller = MAIN_SCRIPT_FOR_RESTART.Controller(params=params, 
                                                    solver=solver, 
                                                    updater=updater)
    params.reinitialize(0)
    params.load(filepath=restart_path + '/Log/', iteration=target_iteration)

    return controller