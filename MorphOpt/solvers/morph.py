
from scipy.signal import step
import torch

import FEA
import multiprocessing as mp

from ..modelparams import Params, FEAParams
from ..GLOBAL import PATH
from .base_solver import BaseSolver

from MorphOpt import GLOBAL

class MorphSolver(BaseSolver):
    """
    This class is responsible for solving the FEA and get the displacement of the soft robot.
    """

    
    def __init__(self, params: Params, num_process: int = 4, available_gpus: list[str] = None):
        """
        Initialize the Solver class with a list of pressure values.

        Parameters:
            pressure_list (list[list[float]]): A list of pressure values for the optimization problem.
            U_dim (list[int]): The dimensions of the interest for the optimization problem.
            p_dim (list[int]): The dimensions of the pressure for the optimization problem.
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

        
    def solve(self):
        """
        Solve the optimization problem using the specified solver.

        Returns:
            tuple: the displacement field and its derivatives:
                - fe (FEA.FEAController): An instance of the FEA_Main class with the given input parameters.
                - GC0 (list[torch.Tensor]): The displacement field at the reference point.
                - Udp0 (list[torch.Tensor]): The displacement field at the reference point with respect to the pressure.
                - GCv (list[torch.Tensor]): The first adjoint displacement field.
                - GCw (list[torch.Tensor]): The second adjoint displacement field.
        """
        
        fe = self.params.feamodel.create_fea(inp=GLOBAL.obj_fun.inp)
        fe.initialize()

        # multiprocess FEA
        # self._solve_FEA(GLOBAL.obj_fun.inp, self.params.loads, 0, self.available_gpus)
        pools = mp.Pool(processes=self.num_process)
        result = []
        for i in range(self.params.feamodel.num_load_steps):
            result.append(
                pools.apply_async(self._solve_FEA,
                                args=(GLOBAL.obj_fun.inp, self.params.feamodel, i, self.available_gpus)))
        pools.close()
        pools.join()

        # get the result
        U0 = torch.tensor([i.get() for i in result], device='cpu')

        GLOBAL.obj_fun.set_results(fe=fe, U=U0)
        GLOBAL.obj_fun.calculate_adjoint_problem()

    @classmethod
    def _solve_FEA(current_class, inp: FEA.FEA_INP, feamodel: FEAParams, step_index: int, available_gpus):
        import os
        os.environ['KMP_DUPLICATE_LIB_OK']='True'
        import sys
        import torch
        sys.path.append(os.getcwd())
        import FEA

        current_process_name = mp.current_process().name
        try:
            pool_id = int(current_process_name.split("-")[-1])
        except:
            pool_id = 0

        if len(available_gpus) > 0:
            cuda_now = (pool_id+1) % len(available_gpus)
            torch.set_default_device(available_gpus[cuda_now])
            print("Process %s use GPU: %s" % (current_process_name, available_gpus[cuda_now]))
        else:
            torch.set_default_device('cpu')
            print("Process %s use CPU" % (current_process_name))

        # torch.set_default_device(torch.device('cuda:0'))
        torch.set_default_dtype(torch.float64)
        torch.cuda.empty_cache()
        # construct the FEA
        fe = feamodel.create_fea(inp)
        feamodel.process_fea(fe=fe, step_index=step_index)

        # solve displacement 0
        fe.solver.maximum_iteration = 200
        result = fe.solve(tol_error=1e-3)

        if type(result) == bool:
            raise RuntimeError(
                "FEA solver failed to converge. Please check the input parameters."
            )

        GC0 = fe.solver.GC.clone().detach()

        return GC0.tolist()