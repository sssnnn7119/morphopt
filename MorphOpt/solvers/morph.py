
import torch

import FEA
import multiprocessing as mp

from ..modelparams import Params, LoadsParams
from ..GLOBAL import PATH
from .base_solver import BaseSolver

from MorphOpt import GLOBAL

class MorphSolver(BaseSolver):
    """
    This class is responsible for solving the FEA and get the displacement of the soft robot.
    """

    
    def __init__(self, params: Params, num_process: int = 4):
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


        FE_inp = FEA.FEA_INP()
        FE_inp.read_inp(PATH.path_Result + '/Cache/' + '/TopOptRun.inp')

        fe = self.init_FEA(FE_inp, load_params=self.params.loads)
        fe.initialize()
        

        # multiprocess FEA
        # self._solve_FEA(PATH.path_Result, self.params.loads, 0)
        pools = mp.Pool(processes=self.num_process)
        result = []
        for i in range(self.params.loads.num_load_steps):
            result.append(
                pools.apply_async(self._solve_FEA,
                                args=(PATH.path_Result, self.params.loads, i,)))
        pools.close()
        pools.join()

        # get the result
        U0 = torch.tensor([i.get() for i in result], device='cpu')

        GLOBAL.obj_fun.set_results(fe=fe, U=U0)
        GLOBAL.obj_fun.calculate_adjoint_problem()
    
    @staticmethod
    def init_FEA(inp: FEA.FEA_INP, load_params: LoadsParams) -> FEA.FEAController:
        """
        Initialize the FEA class with the given input parameters.

        Parameters:
            inp (FEA.FEA_INP): The input parameters for the FEA class.

        Returns:
            FEA.FEAController: An instance of the FEA_Main class with the given input parameters.
            
        """
        fe = FEA.from_inp(inp)
        fe.solver = FEA.solver.StaticImplicitSolver()
        ins_name = 'final_model'
        ins = fe.assembly.get_instance(ins_name)
        # convert to the second order elements
        # fe = FEA.elements.convert_to_second_order(fe, ['element-0'])

        # Add loads
        fe.assembly.add_loads(loads_dict=load_params.get_loads_fea())

        # add boundary condition
        bc_dof = inp.part['final_model'].sets_nodes['surface_0_Bottom']
        fe.assembly.add_constraint(FEA.constraints.Boundary_Condition(instance_name=ins_name, index_nodes=bc_dof),
                        name='BC')        # add reference point and constraints
        
        
        rp = FEA.ReferencePoint([0., 0., ins.nodes[:, 2].max()],)
        rp_name = fe.assembly.add_reference_point(rp=rp, name='RP_head')
        indexNodes = inp.part['final_model'].sets_nodes['surface_0_Head']
        fe.assembly.add_constraint(FEA.constraints.Couple(instance_name=ins_name, indexNodes=indexNodes, rp_name=rp_name)
        )
        
        return fe

    @classmethod
    def _solve_FEA(current_class, path_result: str, load_params: LoadsParams, step_index: int):
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

        available_gpus = ['cuda:0']
        if torch.cuda.is_available():
            cuda_now = (pool_id+1) % len(available_gpus)
            torch.set_default_device(available_gpus[cuda_now])
            print("Process %s use GPU: %s" % (current_process_name, available_gpus[cuda_now]))
        else:
            torch.set_default_device('cpu')

        # torch.set_default_device(torch.device('cuda:0'))
        torch.set_default_dtype(torch.float64)
        torch.cuda.empty_cache()
        # construct the FEA
        FE_inp = FEA.FEA_INP()
        FE_inp.read_inp(path_result + '/Cache/' + '/TopOptRun.inp')

        fe = current_class.init_FEA(FE_inp, load_params=load_params)
        load_params.process_fea(fea=fe, step_index=step_index)

        # solve displacement 0
        fe.solver.maximum_iteration = 200
        result = fe.solve(tol_error=1e-4)

        if type(result) == bool:
            raise RuntimeError(
                "FEA solver failed to converge. Please check the input parameters."
            )

        GC0 = fe.solver.GC.clone().detach()

        return GC0.tolist()