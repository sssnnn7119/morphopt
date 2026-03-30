
import numpy as np
import torch
import copy
import torchfea
import multiprocessing as mp

from .modelparams import Params, FEAParams, Materials

from .baseobject import BaseObject
import morphopt
class MorphSolver(BaseObject):
    """
    This class is responsible for solving the FEA and get the displacement of the soft robot.
    """

    
    def __init__(self, params: Params, num_process: int = 4, available_gpus: list[str] = None, task_index_list: list[list[int]] = None):
        """
        Initialize the Solver class with a list of pressure values.

        Parameters:
            params (Params): 
            num_process (int): The number of processes to use for parallel computation.
        """

        super().__init__()

        self.params: Params = params
        """
        Pressures: An instance of the params of the optimization problem.
        """

        self.num_process = num_process
        """
        int: The number of processes to use for parallel computation.
        """

        if available_gpus is None:
            self.available_gpus = ['cuda:%d' % i for i in range(torch.cuda.device_count())]
        else:
            self.available_gpus = available_gpus

        self.task_index_list = task_index_list
        """
        list[list[int]]: A list of task indices for each process.
        """

    def initialize(self):
        if self.task_index_list is None:
            self.task_index_list = []
            for i in range(morphopt.controller.params.feamodel.num_load_steps):
                self.task_index_list.append([i])

        

    def reinitialize(self, iteration: int) -> None:
        """
        Reinitialize the solver for a new iteration.

        Parameters:
            iteration (int): The current iteration number.
        """
        pass

    def solve(self):
        """
        Solve the optimization problem using the specified solver.

        Returns:
            tuple: the displacement field and its derivatives:
                - fe (torchfea.FEAController): An instance of the FEA_Main class with the given input parameters.
                - GC0 (list[torch.Tensor]): The displacement field at the reference point.
                - Udp0 (list[torch.Tensor]): The displacement field at the reference point with respect to the pressure.
                - GCv (list[torch.Tensor]): The first adjoint displacement field.
                - GCw (list[torch.Tensor]): The second adjoint displacement field.
        """

        # multiprocess FEA

        fe_cpu = copy.deepcopy(morphopt.controller.objfun.fe)
        fe_cpu.change_device(torch.device('cpu'))

        # self._solve_FEA(fe=fe_cpu, 
        #                 feamodel=self.params.feamodel,
        #                 task_index=self.task_index_list[0],
        #                 available_gpus=self.available_gpus)

        pools = morphopt.controller.pools
        result = []
        for i in range(len(self.task_index_list)):
            result.append(
                            pools.apply_async(self._solve_FEA,
                                            kwds={'fe': fe_cpu,
                                                    'feamodel': self.params.feamodel,
                                                    'task_index': self.task_index_list[i],
                                                    'available_gpus': self.available_gpus}))

        # get the result
        results = []
        list_number = []
        for i in range(len(result)):
            results += result[i].get()
            list_number += self.task_index_list[i]
        list_number = np.array(list_number).flatten()
        
        output = []
        for i in range(len(results)):
            output.append(results[list_number[i]])

        del fe_cpu
        return output
        

    @classmethod
    def _solve_FEA(cls, fe: torchfea.FEAController, 
                   feamodel: FEAParams, 
                   task_index: list[int], 
                   available_gpus: list[str], 
                   U_guess: np.ndarray = None):
        import os
        os.environ['KMP_DUPLICATE_LIB_OK']='True'
        import sys
        import torch
        sys.path.append(os.getcwd())
 
        current_process_name = mp.current_process().name
        try:
            pool_id = int(current_process_name[-1])
        except:
            pool_id = 0

        if len(available_gpus) > 0:
            cuda_now = (pool_id+1) % len(available_gpus)
            torch.set_default_device(available_gpus[cuda_now])
            device_now = available_gpus[cuda_now]
            print("Process %s use GPU: %s" % (current_process_name, available_gpus[cuda_now]))
        else:
            torch.set_default_device('cpu')
            device_now = 'cpu'
            print("Process %s use CPU" % (current_process_name))

        # torch.set_default_device(torch.device('cuda:0'))
        torch.set_default_dtype(torch.float64)
        torch.cuda.empty_cache()
        # construct the FEA
        fe.change_device(device_now)

        if U_guess is not None:
            U0 = torch.from_numpy(U_guess).to(torch.float64).to(fe.assembly.device)
        else:
            U0 = fe.assembly.GC.to(torch.get_default_device())

        result_list = []
        for i in range(len(task_index)):
            feamodel.process_fea(fe=fe, step_index=task_index[i])
            result: torchfea.solver.StaticResult = fe.solve(GC0=U0.to(torch.get_default_device()), if_initialize=False)

            result_list.append(result)
        return result_list