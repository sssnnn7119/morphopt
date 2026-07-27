from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .. import Params, Solver, Updaters, ObjectiveFunction
from .history import History
import datetime
import importlib
import os
import shutil
import torch
import numpy as np

import time
import gc
import morphopt
import multiprocessing as mp
from multiprocessing import get_context

import logging
logger = logging.getLogger(__name__)

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

        self.solver: Solver
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

        self.dataqueue: Optional[mp.Queue] = None

        self.pools = None
        """
        The multiprocessing pool for parallel computation.
        """

        self.optdevice: str = 'cpu'
        """
        The device to run the optimization on.
        """

        self._debug_mode: bool = False
        """
        Whether to run in debug mode, which may include additional checks and logging.
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

        os.makedirs(self.path_result + '/scripts/', exist_ok=True)
        if main_filepath is not None:
            shutil.copy(main_filepath, self.path_result + '/scripts/MAIN_SCRIPT_FOR_RESTART.py')
        else:
            import __main__
            shutil.copy(__main__.__file__, self.path_result + '/scripts/MAIN_SCRIPT_FOR_RESTART.py')

        vendor_package('torchfea', target_dir=self.path_result + '/scripts/')
        vendor_package('cpgeo', target_dir=self.path_result + '/scripts/')
        vendor_package('morphopt', target_dir=self.path_result + '/scripts/')


    def initialize(self) -> None:
        """
        Initialize the workflow by initializing the Params, Solver, Updaters, and ObjFun classes.
        """
        morphopt.controller = self

        self.params = self.Params()
        self.solver = self.Solver(params=self.params)
        self.updater = self.Updater(params=self.params)
        self.objfun = self.ObjectiveFunction()


        self.params.initialize()
        self.solver.initialize()
        self.updater.initialize()
        self.objfun.initialize()
        self.history.initialize()

        # Use 'spawn' context for the Pool to avoid inheriting CUDA context
        # and Qt/X11 connections from forked subprocesses
        self.pools = get_context('spawn').Pool(processes=self.solver.num_process)

    def start_optimization(self, main_filepath: str = None) -> None:
        
        self.initialize()
        self.initialize_path(main_filepath=main_filepath)
        self.opt_loop()

    def _load_history(self, path_result: str, target_iteration: int = None) -> None:
        self.path_result = path_result
        self.initialize()
        self.history.load(foldpath=self.path_result + '/log/', iteration=target_iteration)

        if target_iteration is None:
            target_iteration = self.history.iteration

        self.params.load(foldpath=self.path_result + '/log/', iteration=target_iteration)
        self.solver.load(foldpath=self.path_result + '/log/', iteration=target_iteration)
        self.updater.load(foldpath=self.path_result + '/log/', iteration=target_iteration)


    def restart_optimization(self, path_result: str, target_iteration: int = None) -> None:

        self._load_history(path_result=path_result, target_iteration=target_iteration)
        self.opt_loop()

    def opt_loop(self) -> None:
        """
        This function runs the optimization loop for a specified number of iterations.
        It calls the opt_step function in each iteration.
        """
        import torchfea
        torchfea.enable_logging(log_file=os.path.join(self.path_result, 'log', 'torchfea.log'), file_log_level=logging.DEBUG if self._debug_mode else logging.DEBUG)
        morphopt.enable_logging(log_file=os.path.join(self.path_result, 'log', 'morphopt.log'), file_log_level=logging.DEBUG if self._debug_mode else logging.DEBUG)

        while True:

            # Explicitly release large objects to ensure they are collected
            self.clear_cache()

            loss, t0, t1, t2, t3, t4 = self.step()

            # Record the history of the optimization process
            self.record_history(loss, t0, t1, t2, t3, t4)

            # Print the information
            self.print_info(t0, t1, t2, t3, t4)

            # Save the current parameters and plot the figures
            self.save()

            # if dataqueue is not None, send the data to the queue
            if self.dataqueue is not None:
                self.dataqueue.put({'iteration': self.history.iteration, 'path_result': self.path_result})
            
            if self.restart_per_iteration > 0 and (self.history.iteration+1) % self.restart_per_iteration == 0:
                self.pools.close()
                self.pools.join()
                return
            
            if self.history.iteration == 2:
                self.pools.close()
                self.pools.join()
                return
            

    def step(self):
        """
        Perform a single optimization step.
        Returns:
            loss (torch.Tensor): The loss value after the optimization step.
            t0 (float): The start time of the optimization step.
            t1 (float): The time after model generation.
            t2 (float): The time after finite element analysis (FEA).
            t3 (float): The time after sensitivity analysis.
            t4 (float): The time after updating the surfaces.

        """
        t0 = time.time()
        if os.path.exists(self.path_result + '/cache/TopOptRun.inp'):
            os.remove(self.path_result + '/cache/TopOptRun.inp')

        logger.info("\n" + "=" * 50 + f"\nStarting optimization step {self.history.iteration}...\n" + "=" * 50)

        # Initialize the workflow
        self.params.reinitialize(iteration = self.history.iteration)
        self.solver.reinitialize(iteration = self.history.iteration)
        self.updater.reinitialize(iteration = self.history.iteration)
        self.objfun.reinitialize(iteration = self.history.iteration)

        # Perform the optimization step
        logger.info(f"Creating FEA model for iteration {self.history.iteration}...")
        self.objfun.fe = self.params.create_feamodel(path_result=self.path_result + '/cache/', pools=self.pools)

        t1 = time.time()

        # Perform finite element analysis (FEA)
        logger.info(f"Performing FEA for iteration {self.history.iteration}...")
        self.objfun.fe_results = self.solver.solve()

        t2 = time.time()

        # sensitivity analysis
        logger.info(f"Performing sensitivity analysis for iteration {self.history.iteration}...")
        gradients = self.objfun.sensitivity_analysis(params=self.params)

        t3 = time.time()

        # Update the surfaces based on the FEA results
        logger.info(f"Updating surfaces for iteration {self.history.iteration}...")
        self.updater.update(gradients=gradients)
        self.updater.update_variables()

        loss = self.objfun.objective_function()

        t4 = time.time()

        return loss, t0, t1, t2, t3, t4

    def record_history(self, loss: torch.Tensor, t0: float, t1: float, t2: float, t3: float, t4: float) -> None:
        """
        Record the history of the optimization process.
        """
        self.history.append('objective', loss.item())
        self.history.append('metrics', self.objfun.get_metrics())
        self.history.append('time', [t1-t0, t2-t1, t3-t2, t4-t3])
        self.history.append('num_elements', sum([elem._elems.shape[0] for elem in self.objfun.fe.assembly.get_instance('final_model').elems.values()]))
        self.history.append('num_nodes', self.objfun.fe.assembly.get_instance('final_model').nodes.shape[0])

    def print_info(self, t0, t1, t2, t3, t4) -> None:
        """
        Print the current information of the optimization process.
        """
        logger.info(f"Iteration: {self.history.iteration}")
        logger.info(f"Loss: {self.history.history_objective[-1]:.6f}")
        logger.info("Time Breakdown:")
        logger.info(f"  Initialization Time: {t1 - t0:.2f} seconds")
        logger.info(f"  FEA Time: {t2 - t1:.2f} seconds")
        logger.info(f"  Sensitivity Time: {t3 - t2:.2f} seconds")
        logger.info(f"  Update Time: {t4 - t3:.2f} seconds")
        logger.info(f"  Total Time: {t4 - t0:.2f} seconds")
        logger.info("-" * 50)

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
        self.objfun.fe = None

        torch.cuda.empty_cache()
        data = gc.collect()
        logger.info(f"Garbage collector: collected {data} objects.")

    def change_device(self, device: torch.device, obj: object = None) -> None:
        """
        Recursively change the device of the finite element model and all nested objects.

        Args:
            device (torch.device): The target device.
            obj (object, optional): The object to change the device for. If None, change the device for the Controller instance itself.

        Returns:
            None
        """
        if obj is not None:
            self._change_device_recursive(obj, device)
        else:
            self._change_device_recursive(self, device)

    def _change_device_recursive(self, obj, device, visited=None):
        """
        Recursively move tensors to the target device.
        """
        if visited is None:
            visited = set()
        
        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)

        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, torch.Tensor):
                    obj[k] = v.to(device)
                else:
                    self._change_device_recursive(v, device, visited)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, torch.Tensor):
                    obj[i] = v.to(device)
                else:
                    self._change_device_recursive(v, device, visited)
        elif isinstance(obj, tuple):
            for v in obj:
                self._change_device_recursive(v, device, visited)
        elif hasattr(obj, '__dict__'):
            for k, v in list(obj.__dict__.items()):
                if isinstance(v, torch.Tensor):
                    setattr(obj, k, v.to(device))
                else:
                    self._change_device_recursive(v, device, visited)

    @classmethod
    def _detach_recursive(cls, obj: object, visited: set=None):
        """
        Recursively detach tensors to clean up the computation graph.
        For mutable containers (list, dict, objects), replaces tensors with detached versions.
        This avoids inplace detach_() errors on views.
        """
        if visited is None:
            visited = set()
        
        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)

        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, torch.Tensor):
                    obj[k] = v.detach()
                else:
                    cls._detach_recursive(v, visited)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, torch.Tensor):
                    obj[i] = v.detach()
                else:
                    cls._detach_recursive(v, visited)
        elif isinstance(obj, tuple):
            for v in obj:
                cls._detach_recursive(v, visited)
        elif hasattr(obj, '__dict__'):
            # Iterate over a copy of items to avoid modification issues
            for k, v in list(obj.__dict__.items()):
                if k.startswith('__'): continue 
                if isinstance(v, torch.Tensor) and v.requires_grad:
                    setattr(obj, k, v.detach())
                else:
                    cls._detach_recursive(v, visited)

    def _change_device_recursive(self, obj, device, visited=None):
        """
        Recursively move tensors to the target device.
        """
        if visited is None:
            visited = set()
        
        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)

        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, torch.Tensor):
                    obj[k] = v.to(device)
                else:
                    self._change_device_recursive(v, device, visited)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, torch.Tensor):
                    obj[i] = v.to(device)
                else:
                    self._change_device_recursive(v, device, visited)
        elif isinstance(obj, tuple):
            for v in obj:
                self._change_device_recursive(v, device, visited)
        elif hasattr(obj, '__dict__'):
            for k, v in list(obj.__dict__.items()):
                if isinstance(v, torch.Tensor):
                    setattr(obj, k, v.to(device))
                else:
                    self._change_device_recursive(v, device, visited)
