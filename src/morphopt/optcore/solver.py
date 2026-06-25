
import numpy as np
import torch
import copy
import torchfea
import multiprocessing as mp

from .modelparams import Params, FEAParams

from .baseobject import BaseObject
import morphopt
class Solver(BaseObject):
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

    def solve(self, U_guess: np.ndarray = None):
        """
        Solve the optimization problem using the specified solver.

        Returns:
            The result of the optimization problem.
        """

        # multiprocess FEA

        fe_cpu = copy.deepcopy(morphopt.controller.objfun.fe)
        fe_cpu.change_device(torch.device('cpu'))
        
        if morphopt.controller._debug_mode:
            self._solve_FEA(fe=fe_cpu, 
                            feamodel=self.params.feamodel,
                            task_index=self.task_index_list[0],
                            available_gpus=self.available_gpus)

        pools = morphopt.controller.pools
        # pools.close()
        # pools.join()
        # pools = mp.Pool(processes=self.num_process)
        # morphopt.controller.pools = pools
        result = []
        for i in range(len(self.task_index_list)):
            result.append(
                            pools.apply_async(self._solve_FEA,
                                            kwds={'fe': fe_cpu,
                                                    'feamodel': self.params.feamodel,
                                                    'task_index': self.task_index_list[i],
                                                    'available_gpus': self.available_gpus,
                                                    'U_guess': U_guess[self.task_index_list[i][0]] if U_guess is not None else None,
                                                    'path_result': morphopt.controller.path_result}
                                            )
                        )

        # get the result
        results = []
        list_number = []
        for i in range(len(result)):
            results += result[i].get()
            list_number += self.task_index_list[i]
        list_number = np.array(list_number).flatten()
        
        output: list[torchfea.solver.StaticResult] = []
        for i in range(len(results)):
            output.append(results[list_number[i]])
            morphopt.controller.objfun.fe._change_device_recursive(output[i], torch.get_default_device())

        # check if convergence is achieved
        for tidx in range(len(output)):
            if output[tidx].converged == False:
                raise ValueError("FEA did not converge for load step %d" % list_number[tidx])

        del fe_cpu
        return output
        

    @classmethod
    def _solve_FEA(cls, fe: torchfea.FEAController, 
                   feamodel: FEAParams, 
                   task_index: list[int], 
                   available_gpus: list[str], 
                   U_guess: np.ndarray = None,
                   path_result: str = None):
        import os
        os.environ['KMP_DUPLICATE_LIB_OK']='True'
        import sys
        import torch
        sys.path.append(os.getcwd())

        import torchfea
        torchfea.enable_logging(log_file=os.path.join(path_result, 'log', 'torchfea.log'))
 
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
            U0 = torch.from_numpy(U_guess).to(torch.float64).to(torch.get_default_device())
        else:
            U0 = fe.assembly._GC.to(torch.get_default_device())

        result_list = []
        for i in range(len(task_index)):
            feamodel.process_fea(fe=fe, step_index=task_index[i])
            result: torchfea.solver.StaticResult = fe.solve(GC0=U0.to(torch.get_default_device()), if_initialize=False)

            result_list.append(result)
            fe._change_device_recursive(result, torch.device('cpu'))
            U0 = result.GC.detach().clone()

        del fe
        torch.cuda.empty_cache()
        return result_list