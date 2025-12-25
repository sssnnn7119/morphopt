from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from . import Params, MorphSolver, Updaters, ObjectiveFunction
from .history import History
import datetime
import importlib
import os
import shutil
import torch
import numpy as np

import time
import gc
import MorphOpt

class Controller:

    class Params:
        pass

    class Solver:
        pass

    class Updater:
        pass

    class ObjectiveFunction:
        pass

    def __init__(self, path_result_folder: str, opt_label: str = 'DefaultLabel') -> None:
        """
        Initialize the Controller class.

        This class is responsible for managing the optimization process.
        It initializes the workflow, generates the model, performs finite element analysis (FEA), and updates the surfaces.
        """

        self.params: Params 
        """
        Params: An instance of the Params class from the ModelParams module.
        """

        self.solver: MorphSolver
        """
        Solver: An instance of the Solver class from the Solve module.
        """

        self.updater: Updaters
        """
        Updaters: An instance of the Updaters class from the Update module.
        """

        self.objfun: ObjectiveFunction
        """
        ObjFun: An instance of the ObjectiveFunction class from the ObjFunc module.
        """

        self.opt_label: str = opt_label
        """
        The name of the optimization.
        """

        self.path_result_folder: str = path_result_folder
        """
        The foldpath to the result directory.
        """

        self.path_result: str = None
        """
        The path to the result directory.
        """

        self.history = History()
        """
        History: An instance of the History class from the History module to record the optimization history.
        """

        self.restart_per_iteration: int = 20
        """
        The frequency of restarting the optimization process.
        """

    def initialize_path(self, main_filepath: str = None) -> None:
        """
        Initialize the workflow by importing necessary modules and setting up the environment.
        """

        def vendor_package(package_name, target_dir='.'):
            """
            copy the specified package to the target directory.
            
            Args:
                package_name: The name of the package to copy.
                target_dir: The target directory, default is the current directory.
            """
            try:
                # import the package
                module = importlib.import_module(package_name)
                
                # get the package path
                package_path = os.path.dirname(module.__file__)
                
                # construct the target path
                target_path = os.path.join(target_dir, package_name)
                
                # if the target directory exists, remove it first
                if os.path.exists(target_path):
                    if os.path.isfile(target_path):
                        os.remove(target_path)
                    else:
                        shutil.rmtree(target_path)
                
                # copy the package files
                if os.path.isdir(package_path):
                    shutil.copytree(package_path, target_path)
                    print(f"successfully copied package '{package_name}' to {target_path}")
                else:
                    shutil.copy2(package_path, target_path)
                    print(f"successfully copied module '{package_name}' to {target_path}")
                    
                # Check if there are related .pth files or other metadata that need to be handled
                # For pure Python packages, the above steps are usually sufficient
                
            except ImportError:
                print(f"Error: Package '{package_name}' not found. Please install it first.")
            except Exception as e:
                print(f"Error occurred during copying: {str(e)}")
        
        self.path_result = self.path_result_folder + '/' + self.opt_label + '_' + 'T' + datetime.datetime.now().strftime(
            "%Y%m%d_%H%M%S") + '/'
            
        # create the result path if it does not exist
        os.makedirs(self.path_result + '/cache/')
        pathlog_list = []
        pathlog_list += self.params.pathlog_required()
        pathlog_list += self.solver.pathlog_required()
        pathlog_list += self.updater.pathlog_required()
        pathlog_list += self.objfun.pathlog_required()
        for pathlog in pathlog_list:
            os.makedirs(self.path_result + '/log/' + pathlog)

        os.makedirs(self.path_result + '/fea')

        # copy the scripts to the result path
        def ignore_folder(dir, contents):
            """忽略指定的文件夹"""
            ignore_list = ['.conda', '.git']
            result = []
            for item in contents:
                if item in ignore_list:
                    result.append(item)
            return result

        shutil.copytree(os.getcwd(), self.path_result + '/scripts/', ignore=ignore_folder)

        if main_filepath is not None:
            shutil.copy(main_filepath, self.path_result + '/scripts/MAIN_SCRIPT_FOR_RESTART.py')
        else:
            import __main__
            shutil.copy(__main__.__file__, self.path_result + '/scripts/MAIN_SCRIPT_FOR_RESTART.py')

        vendor_package('FEA', target_dir=self.path_result + '/scripts/')
        vendor_package('CPGEO', target_dir=self.path_result + '/scripts/')
        vendor_package('Bspline', target_dir=self.path_result + '/scripts/')


    def initialize(self) -> None:
        """
        Initialize the workflow by initializing the Params, Solver, Updaters, and ObjFun classes.
        """
        MorphOpt.controller = self

        self.params = self.Params()
        self.solver = self.Solver(params=self.params)
        self.updater = self.Updater(params=self.params)
        self.objfun = self.ObjectiveFunction()


        self.params.initialize()
        self.solver.initialize()
        self.updater.initialize()
        self.objfun.initialize()
        self.history.initialize()

    def start_optimization(self, main_filepath: str = None) -> None:
        
        self.initialize()
        self.initialize_path(main_filepath=main_filepath)
        self.opt_loop()

    def restart_optimization(self, restart_path: str, target_iteration: int = None) -> None:

        self.path_result = restart_path
        self.initialize()
        self.history.load(foldpath=self.path_result + '/log/', iteration=target_iteration)

        if target_iteration is None:
            target_iteration = self.history.iteration

        self.params.load(foldpath=self.path_result + '/log/', iteration=target_iteration)
        self.solver.load(foldpath=self.path_result + '/log/', iteration=target_iteration)
        self.updater.load(foldpath=self.path_result + '/log/', iteration=target_iteration)

        self.history.iteration += 1

        self.opt_loop()

    def opt_loop(self) -> None:
        """
        This function runs the optimization loop for a specified number of iterations.
        It calls the opt_step function in each iteration.
        """
        
        while True:

            # Explicitly release large objects to ensure they are collected
            self.clear_cache()

            seed_size0 = self.params.geometry.fea_seed_size
            max_iter_before_regenerate0 = self.params.geometry._max_iter_before_regenerate
            
            while True:
                try:
                    loss, t0, t1, t2, t3 = self.step()
                    break
                except Exception as e:
                    print('Error occurred during optimization step: %s' % str(e))
                    self.params.geometry.fea_seed_size = seed_size0 * np.random.uniform(0.9, 1.2)
                    self.params.geometry._max_iter_before_regenerate = 1
                    self.params.load(foldpath=self.path_result + '/log/', iteration=self.history.iteration)
                    self.params.reinitialize(iteration = 0)
            self.params.geometry.fea_seed_size = seed_size0
            self.params.geometry._max_iter_before_regenerate = max_iter_before_regenerate0

            # Record the history of the optimization process
            self.record_history(loss, t0, t1, t2, t3)
            
            # Print the information
            self.print_info(t0, t1, t2, t3)

            # Save the current parameters and plot the figures
            self.save()
            
            if self.restart_per_iteration > 0 and (self.history.iteration+1) % self.restart_per_iteration == 0:
                print(f"Restarting optimization at iteration {self.history.iteration} to free up resources.")
                return
            
            self.history.iteration += 1
            

    def step(self):
        """
        Perform a single optimization step.
        Returns:
            loss (torch.Tensor): The loss value after the optimization step.
            t0 (float): The start time of the optimization step.
            t1 (float): The time after model generation.
            t2 (float): The time after finite element analysis (FEA).
            t3 (float): The time after updating the surfaces.
        """
        t0 = time.time()
        if os.path.exists(self.path_result + '/cache/TopOptRun.inp'):
            os.remove(self.path_result + '/cache/TopOptRun.inp')

        # Initialize the workflow
        self.params.reinitialize(iteration = self.history.iteration)
        self.solver.reinitialize(iteration = self.history.iteration)
        self.updater.reinitialize(iteration = self.history.iteration)
        self.objfun.reinitialize(iteration = self.history.iteration)

        # Perform the optimization step
        # Generate the model
        self.params.geometry.generate(material_para=[self.params.materials.density, 1, 
                                                self.params.materials.mu, 
                                                self.params.materials.kappa])

        t1 = time.time()

        # Perform finite element analysis (FEA)
        self.solver.solve()

        t2 = time.time()

        # Update the surfaces based on the FEA results
        self.updater.update()
        self.updater.update_variables()

        loss = self.objfun.get_objective()

        t3 = time.time()

        return loss, t0, t1, t2, t3

    def record_history(self, loss: torch.Tensor, t0: float, t1: float, t2: float, t3: float) -> None:
        """
        Record the history of the optimization process.
        """
        if self.objfun.fe.assembly._reference_points.get('RP_head') is None:
            displacement = []
        else:
            GC_start_index = self.objfun.fe.assembly._GC_list_indexStart[self.objfun.fe.assembly.get_reference_point('RP_head')._RGC_index]
            displacement = [self.objfun.U[i][GC_start_index:GC_start_index+6].tolist() for i in range(len(self.objfun.U))]
        self.history.history_deformation.append(displacement)
        self.history.history_objective.append(loss.item())
        self.history.history_time.append([t1-t0, t2-t1, t3-t2])
        self.history.history_num_elements.append(self.objfun.fe.assembly.get_instance('final_model').elems['element-0']._elems.shape[0])
        self.history.history_num_nodes.append(self.objfun.fe.assembly.get_instance('final_model').nodes.shape[0])

    def print_info(self, t0, t1, t2, t3) -> None:
        """
        Print the current information of the optimization process.
        """
        print(f"Iteration: {self.history.iteration}")
        print(self.objfun)
        print(f"Loss: {self.history.history_objective[-1]:.6f}")
        print("Time Breakdown:")
        print(f"  Initialization Time: {t1 - t0:.2f} seconds")
        print(f"  FEA Time: {t2 - t1:.2f} seconds")
        print(f"  Update Time: {t3 - t2:.2f} seconds")
        print(f"  Total Time: {t3 - t0:.2f} seconds")
        print("-" * 50)

    def save(self) -> None:
        """
        Save the current state of the optimization process.
        """
        self.params.save(foldpath=self.path_result + '/log/', iteration=self.history.iteration)
        self.solver.save(foldpath=self.path_result + '/log/', iteration=self.history.iteration)
        self.updater.save(foldpath=self.path_result + '/log/', iteration=self.history.iteration)
        self.history.save(foldpath=self.path_result + '/log/', iteration=self.history.iteration)
        self.objfun.save(foldpath=self.path_result + '/log/', iteration=self.history.iteration)

    def clear_cache(self) -> None:
        """
        Clear the cache directory.
        """
        self.objfun.K_sp = []
        self.objfun.K_solver = []
        self.objfun.U = None
        self.objfun.ADJu = None
        self.objfun.fe = None

        torch.cuda.empty_cache()
        data = gc.collect()
        print(f"Garbage collector: collected {data} objects.")