
import numpy as np
import torch
import copy
import torchfea
import multiprocessing as mp

from .. import Solver
import morphopt


class SIMPSolver(Solver):
    """
    This class is responsible for solving the FEA and get the displacement of the soft robot.
    """


    def __init__(self, params, num_process = 4, available_gpus = None, task_index_list = None):
        super().__init__(params, num_process, available_gpus, task_index_list)

        self._GC_pre: list[np.ndarray] = None
        """save the GC of the previous iteration for the initialization of the GC in the current iteration"""

    def solve(self, U_guess: np.ndarray = None):

        if self._GC_pre is not None:
            U_guess = self._GC_pre
        elif morphopt.controller.history.iteration > 0:
            U_guess_list = []
            for taskidx in range(self.params.feamodel.num_load_steps):
                results = torchfea.solver.StaticResult.load(morphopt.controller.path_result + f'/log/femodel&results/result_{taskidx}_iter_{morphopt.controller.history.iteration-1}.npz')
                U_guess_list.append(results.GC.cpu().numpy())
            U_guess = np.stack(U_guess_list)
        output = super().solve(U_guess=U_guess)

        self._GC_pre = []
        for i in range(len(output)):
            self._GC_pre.append(output[i].GC.cpu().numpy())

        return output
    