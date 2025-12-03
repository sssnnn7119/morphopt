import datetime
import importlib
import shutil
from .. import GLOBAL
import os
import __main__

def initialize_path_log(name: str):
    os.makedirs(GLOBAL.PATH.path_Result + '/Log/%s/Data'%(name))
    os.makedirs(GLOBAL.PATH.path_Result + '/Log/%s/Figures'%(name))

def initialize_path(opt_label: str = 'DefaultLabel', result_path: str = None) -> None:
    """
    Initialize the workflow by importing necessary modules and setting up the environment.
    """

    GLOBAL.PATH.opt_Lable = opt_label
    
    GLOBAL.PATH.path_Code = os.getcwd() + '/MorphOpt/'
    GLOBAL.PATH.path_Queue = GLOBAL.PATH.path_Code + '/modelparams/geometry/_Rhino/taskqueue/'
    if result_path is None:
        result_path = os.getcwd() + '/Results/'
    
    GLOBAL.PATH.path_Result = result_path + '/' + opt_label + '_' + 'T' + datetime.datetime.now().strftime(
        "%Y%m%d_%H%M%S") + '/'
        
    # create the result path if it does not exist
    os.makedirs(GLOBAL.PATH.path_Result + '/Cache/')

    initialize_path_log('Surfaces')
    initialize_path_log('Loads')
    initialize_path_log('Materials')
    initialize_path_log('Deformation')

    os.makedirs(GLOBAL.PATH.path_Result + '/FEA')

    # copy the scripts to the result path
    def ignore_folder(dir, contents):
        """忽略指定的文件夹"""
        ignore_list = ['.conda', '.git']
        result = []
        for item in contents:
            if item in ignore_list:
                result.append(item)
        return result

    shutil.copytree(os.getcwd(), GLOBAL.PATH.path_Result + '/scripts/', ignore=ignore_folder)

    shutil.copy(__main__.__file__, GLOBAL.PATH.path_Result + '/scripts/Jobs/MAIN_SCRIPT_FOR_RESTART.py')

    vendor_package('FEA', target_dir=GLOBAL.PATH.path_Result + '/scripts/')
    vendor_package('CPGEO', target_dir=GLOBAL.PATH.path_Result + '/scripts/')
    vendor_package('Bspline', target_dir=GLOBAL.PATH.path_Result + '/scripts/')



def initialize_history() -> None:
    """
    Initialize the history of the optimization process.
    """
    
    GLOBAL.History.iteration = 0
    GLOBAL.History.history_objective = []
    GLOBAL.History.history_time = []


def vendor_package(package_name, target_dir='.'):
    """
    将指定的Python包源文件复制到目标目录
    
    参数:
        package_name: 要复制的包名
        target_dir: 目标目录，默认为当前目录
    """
    try:
        # 导入包以获取其安装路径
        module = importlib.import_module(package_name)
        
        # 获取包的安装目录
        package_path = os.path.dirname(module.__file__)
        
        # 构建目标路径
        target_path = os.path.join(target_dir, package_name)
        
        # 如果目标目录已存在，则先删除
        if os.path.exists(target_path):
            if os.path.isfile(target_path):
                os.remove(target_path)
            else:
                shutil.rmtree(target_path)
        
        # 复制包文件
        if os.path.isdir(package_path):
            shutil.copytree(package_path, target_path)
            print(f"成功将包 '{package_name}' 复制到 {target_path}")
        else:
            shutil.copy2(package_path, target_path)
            print(f"成功将模块 '{package_name}' 复制到 {target_path}")
            
        # 检查是否有相关的.pth文件或其他元数据需要处理
        # 对于纯Python包，通常上面的步骤已经足够
        
    except ImportError:
        print(f"错误: 找不到包 '{package_name}'，请先安装它")
    except Exception as e:
        print(f"复制过程中发生错误: {str(e)}")