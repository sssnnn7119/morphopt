import os
import shutil
import torch
import numpy as np
from . import GLOBAL
from . import initializer
from .generatemodel import Genetrator
from . import solvers
from . import updaters
from .modelparams import Params
import time


class Controller:

    def __init__(self, params: Params, generator: Genetrator, solver: solvers.BaseSolver,
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

        self.generator = generator
        """
        Genetrator: An instance of the Genetrator class from the GenerateModel module.
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

        while True:
            # Save the current parameters and plot the figures
            self.save()
            self.save_figure()

            # clean the cache
            torch.cuda.empty_cache()

            seed_size0 = self.generator.seed_size
            
            
            while True:
                # try:
                    t0 = time.time()
                    
                    # clean the .inp files
                    if os.path.exists(GLOBAL.PATH.path_Result + '/Cache/TopOptRun.inp'):
                        os.remove(GLOBAL.PATH.path_Result + '/Cache/TopOptRun.inp')

                    # Initialize the workflow
                    self.params.initialize(iteration = GLOBAL.History.iteration)
                    self.generator.initialize(iteration = GLOBAL.History.iteration)
                    self.solver.initialize(iteration = GLOBAL.History.iteration)
                    self.updater.initialize(iteration = GLOBAL.History.iteration)

                    # Perform the optimization step
                    # Generate the model
                    self.generator.generate(material_para=[self.params.materials.density, 1, 
                                                           self.params.materials.mu, 
                                                           self.params.materials.kappa])

                    t1 = time.time()

                    # Perform finite element analysis (FEA)
                    self.solver.solve()

                    t2 = time.time()

                    # Update the surfaces based on the FEA results
                    loss = self.updater.update(self.solver.fe_result).item()
                    self.updater.update_variables()

                    t3 = time.time()
                    
                    break
                # except Exception as e:
                #     print('Error occurred during optimization step: %s' % str(e))
                #     self.generator.seed_size = seed_size0 * np.random.uniform(0.9, 1.2)
                #     self.params.load(filepath=GLOBAL.PATH.path_Result + '/Log/', iteration=GLOBAL.History.iteration)
                #     self.params.initialize(iteration = 0)

            GLOBAL.History.history_deformation.append([self.solver.fe_result.U[i][-6:].tolist() for i in range(len(self.solver.fe_result.U))])
            GLOBAL.History.history_objective.append(loss)
            GLOBAL.History.history_time.append([t1-t0, t2-t1, t3-t2])
            self.generator.seed_size = seed_size0
            
            # Print the information
            print(f"Iteration: {GLOBAL.History.iteration}")
            print(self.solver.fe_result)
            print(f"Loss: {loss:.6f}")
            print("Time Breakdown:")
            print(f"  Initialization Time: {t1 - t0:.2f} seconds")
            print(f"  FEA Time: {t2 - t1:.2f} seconds")
            print(f"  Update Time: {t3 - t2:.2f} seconds")
            print(f"  Total Time: {t3 - t0:.2f} seconds")
            print("-" * 50)
            
            GLOBAL.History.iteration += 1
            

    def save(self) -> None:
        """
        Save the current state of the optimization process.
        """
        self.params.save(filepath=GLOBAL.PATH.path_Result + '/Log/')

        # try:
        #     shutil.copyfile(GLOBAL.PATH.path_Result + '/Cache/TopAbqLS.cae',
        #                     GLOBAL.PATH.path_Result + '/Log/Deformation/Data/TopAbqLS_%d.cae' % (GLOBAL.History.iteration-1))
        # except:
        #     pass
        GLOBAL.History.save_csv(path=GLOBAL.PATH.path_Result + '/Log/')
        
    def save_figure(self) -> None:
        """
        Save the figures generated during the optimization process.
        """
        self.params.save_figure(filepath=GLOBAL.PATH.path_Result + '/Log/')
        if self.solver.fe_result is not None:
            self.solver.fe_result.save_figure(filepath=GLOBAL.PATH.path_Result + '/Log/Deformation/Figures/', iteration=GLOBAL.History.iteration)

