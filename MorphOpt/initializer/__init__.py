import datetime
import shutil
from .. import GLOBAL
import os
import __main__

def initialize_path(opt_label: str = 'DefaultLabel', result_path: str = None) -> None:
    """
    Initialize the workflow by importing necessary modules and setting up the environment.
    """

    GLOBAL.PATH.opt_Lable = opt_label
    
    GLOBAL.PATH.path_Code = os.getcwd() + '/MorphOpt/'
    GLOBAL.PATH.path_Queue = GLOBAL.PATH.path_Code + '/GenerateModel/_Rhino/TaskQueue/'

    if result_path is None:
        result_path = os.getcwd() + '/Results/'
    
    GLOBAL.PATH.path_Result = result_path + '/T' + datetime.datetime.now().strftime(
        "%Y%m%d%H%M%S") + '_' + opt_label + '/'
        
    # create the result path if it does not exist
    os.makedirs(GLOBAL.PATH.path_Result + '/Cache/')
    
    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Objective')

    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Surfaces/Data')
    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Surfaces/Figures')

    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Loads/Data')
    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Loads/Figures')
    
    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Materials/Data')
    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Materials/Figures')

    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Deformation/Data')
    os.makedirs(GLOBAL.PATH.path_Result + '/Log/Deformation/Figures')

    os.makedirs(GLOBAL.PATH.path_Result + '/FEA')


    def ignore_folder(dir, contents):
        """忽略指定的文件夹"""
        return [item for item in contents if item == ".conda"]  # 替换为你要排除的文件夹名

    shutil.copytree(os.getcwd(), GLOBAL.PATH.path_Result + '/scripts/', ignore=ignore_folder)

    shutil.copy(__main__.__file__, GLOBAL.PATH.path_Result + '/scripts/Jobs/MAIN_SCRIPT_FOR_RESTART.py')

def initialize_history() -> None:
    """
    Initialize the history of the optimization process.
    """
    
    GLOBAL.History.iteration = 0
    GLOBAL.History.history_objective = []
    GLOBAL.History.history_time = []