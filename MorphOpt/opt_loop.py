import dis
import os
import shutil
import torch
import numpy as np
from . import GLOBAL
from . import initializer
from . import solvers
from . import updaters
from .modelparams import Params
import time
import gc

class Controller:

    def __init__(self, params: Params, solver: solvers.BaseSolver,
                updater: updaters.Updaters) -> None:
        """
        Initialize the Controller class.

        This class is responsible for managing the optimization process.
        It initializes the workflow, generates the model, performs finite element analysis (FEA), and updates the surfaces.
        """

        self.params = params
        """
        Params: An instance of the Params class from the ModelParams module.
        """

        self.solver = solver
        """
        Solver: An instance of the Solver class from the Solve module.
        """

        self.updater = updater
        """
        Updaters: An instance of the Updaters class from the Update module.
        """

    def opt_loop(self) -> None:
        """
        This function runs the optimization loop for a specified number of iterations.
        It calls the opt_step function in each iteration.
        """

        GLOBAL.controller = self

        self.params.initialize()
        self.solver.initialize()
        self.updater.initialize()

        while True:
            # Save the current parameters and plot the figures
            self.save()
            self.save_figure()

            # clean the cache
            del GLOBAL.obj_fun.fe
            torch.cuda.empty_cache()
            data = gc.collect()
            print(f"Garbage collector: collected {data} objects.")

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
                    self.params.load(filepath=GLOBAL.PATH.path_Result + '/log/', iteration=GLOBAL.History.iteration)
                    self.params.reinitialize(iteration = 0)
            self.params.geometry.fea_seed_size = seed_size0
            self.params.geometry._max_iter_before_regenerate = max_iter_before_regenerate0

            # Record the history of the optimization process
            self.record_history(loss, t0, t1, t2, t3)
            
            # Print the information
            self.print_info(t0, t1, t2, t3)
            
            GLOBAL.History.iteration += 1
            

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
        if os.path.exists(GLOBAL.PATH.path_Result + '/cache/TopOptRun.inp'):
            os.remove(GLOBAL.PATH.path_Result + '/cache/TopOptRun.inp')

        # Initialize the workflow
        self.params.reinitialize(iteration = GLOBAL.History.iteration)
        self.solver.reinitialize(iteration = GLOBAL.History.iteration)
        self.updater.reinitialize(iteration = GLOBAL.History.iteration)

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

        loss = GLOBAL.obj_fun.get_objective()

        t3 = time.time()

        return loss, t0, t1, t2, t3

    def record_history(self, loss: torch.Tensor, t0: float, t1: float, t2: float, t3: float) -> None:
        """
        Record the history of the optimization process.
        """
        if GLOBAL.obj_fun.fe.assembly._reference_points.get('RP_head') is None:
            displacement = []
        else:
            GC_start_index = GLOBAL.obj_fun.fe.assembly._GC_list_indexStart[GLOBAL.obj_fun.fe.assembly.get_reference_point('RP_head')._RGC_index]
            displacement = [GLOBAL.obj_fun.U[i][GC_start_index:GC_start_index+6].tolist() for i in range(len(GLOBAL.obj_fun.U))]

        GLOBAL.History.history_deformation.append(displacement)
        GLOBAL.History.history_objective.append(loss.item())
        GLOBAL.History.history_time.append([t1-t0, t2-t1, t3-t2])
        GLOBAL.History.history_num_elements.append(GLOBAL.obj_fun.fe.assembly.get_instance('final_model').elems['element-0']._elems.shape[0])
        GLOBAL.History.history_num_nodes.append(GLOBAL.obj_fun.fe.assembly.get_instance('final_model').nodes.shape[0])

    def print_info(self, t0, t1, t2, t3) -> None:
        """
        Print the current information of the optimization process.
        """
        print(f"Iteration: {GLOBAL.History.iteration}")
        print(GLOBAL.obj_fun)
        print(f"Loss: {GLOBAL.History.history_objective[-1]:.6f}")
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
        self.params.save(foldpath=GLOBAL.PATH.path_Result + '/log/')
        self.solver.save(foldpath=GLOBAL.PATH.path_Result + '/log/')
        self.updater.save(foldpath=GLOBAL.PATH.path_Result + '/log/')

        GLOBAL.History.save_csv(path=GLOBAL.PATH.path_Result + '/log/')
        
    def save_figure(self) -> None:
        """
        Save the figures generated during the optimization process.
        """
        self.params.save_figure(filepath=GLOBAL.PATH.path_Result + '/log/')
        if GLOBAL.obj_fun.fe is not None:
            GLOBAL.obj_fun.save_figure(filepath=GLOBAL.PATH.path_Result + '/log/deformation/figures/', iteration=GLOBAL.History.iteration)

