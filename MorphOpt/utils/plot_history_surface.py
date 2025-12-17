
import sys
import os

import MorphOpt
def restart_optimization(restart_path, target_iteration=None):
    """
    Restart the optimization process from a specified iteration.

    Parameters:
    - restart_path: Path to the directory containing the previous optimization results.
    - target_iteration: The iteration number to restart from. If None, will restart from the last saved iteration.
    """
    
    params: MorphOpt._Params = MAIN_SCRIPT_FOR_RESTART.Params()

    params.load(filepath=restart_path + '/Log/', iteration=target_iteration)

    return controller