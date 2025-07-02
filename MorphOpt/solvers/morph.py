import os
import sys

import numpy as np
import torch

import FEA
import multiprocessing as mp

from ..modelparams import Params
from ..GLOBAL import PATH
from .base_solver import BaseSolver
from .FE_result import FE_result
from FEA.elements import materials

class Morph(BaseSolver):
    """
    This class is responsible for solving the FEA and get the displacement of the soft robot.
    """

    
    def __init__(self, params: Params, U_dim: list[int] = [-6, -5, -4, -3, -2, -1], num_process: int = 4):
        """
        Initialize the Solver class with a list of pressure values.

        Parameters:
            pressure_list (list[list[float]]): A list of pressure values for the optimization problem.
            U_dim (list[int]): The dimensions of the interest for the optimization problem.
            p_dim (list[int]): The dimensions of the pressure for the optimization problem.
            num_process (int): The number of processes to use for parallel computation.
        """
        
        self.params: Params = params
        """
        Pressures: An instance of the params of the optimization problem.
        """

        self.num_process = num_process
        """
        int: The number of processes to use for parallel computation.
        """
        
        self.U_dim: list[int] = U_dim
        """
        list[int]: The dimensions of the interest for the optimization problem.
        """
        
    def solve(self) -> FE_result:
        """
        Solve the optimization problem using the specified solver.

        Returns:
            tuple: the displacement field and its derivatives:
                - fe (FEA.Main.FEA_Main): An instance of the FEA_Main class with the given input parameters.
                - GC0 (list[torch.Tensor]): The displacement field at the reference point.
                - Udp0 (list[torch.Tensor]): The displacement field at the reference point with respect to the pressure.
                - GCv (list[torch.Tensor]): The first adjoint displacement field.
                - GCw (list[torch.Tensor]): The second adjoint displacement field.
        """

        pressure_list = self.params.loads.pressure.get_pressure().tolist()
                
        FE_inp = FEA.FEA_INP()
        FE_inp.Read_INP(PATH.path_Result + '/Cache/' + '/TopOptRun.inp')

        fe = self.init_FEA(FE_inp)
        fe.initialize()
        
        mu = {}
        kappa = {}
        density = {}
        for i in range(len(fe.elems)):
            str_now = 'element-%d' % i
            if str_now not in fe.elems.keys():
                continue
            gaussian_points = fe.elems[str_now].get_gaussian_points(fe.nodes)
            density_now = self.params.materials.get_density(gaussian_points).cpu().numpy()
            module = self.params.materials.get_modules(gaussian_points)
            mu_now = module[0].cpu().numpy()
            kappa_now = module[1].cpu().numpy()
            mu[str_now] = mu_now
            kappa[str_now] = kappa_now
            density[str_now] = density_now
        
            materials_now = materials.NeoHookean(mu=torch.from_numpy(mu[str_now]).to(fe.nodes.device).to(fe.nodes.dtype),
                                                    kappa=torch.from_numpy(kappa[str_now]).to(fe.nodes.device).to(fe.nodes.dtype),)

            fe.elems[str_now].set_density(torch.from_numpy(density[str_now]).to(fe.nodes.device).to(fe.nodes.dtype))
            fe.elems[str_now].set_materials(materials_now)

        # multiprocess FEA
        # self.__class__._solve_FEA(self.__class__, PATH.path_Result, pressure_list[0], 
        #                            mu, kappa, density, self.U_dim,)
        pools = mp.Pool(processes=self.num_process)
        result = []
        for i in range(len(pressure_list)):
            result.append(
                pools.apply_async(self.__class__._solve_FEA,
                                args=(self.__class__, PATH.path_Result, pressure_list[i], 
                                       mu, kappa, density, self.U_dim,)))
        pools.close()
        pools.join()

        # get the result
        GC0 = torch.tensor([i.get()[0] for i in result], device='cpu')
        Udp0 = torch.tensor([i.get()[1] for i in result], device='cpu')
        UdF0 = torch.tensor([i.get()[2] for i in result], device='cpu')
        GCv = torch.tensor([i.get()[3] for i in result], device='cpu')
        GCw = torch.tensor([i.get()[4] for i in result], device='cpu')
        GCudf = torch.tensor([i.get()[5] for i in result], device='cpu')

        fe_result = FE_result(fe=fe,
                              pressure_list=torch.tensor(pressure_list,
                                                         device='cpu'),
                              U=GC0,
                              Udp=Udp0,
                              UdF=UdF0,
                              GCv=GCv,
                              GCw=GCw, GCudf=GCudf)

        return fe_result
    
    @staticmethod
    def init_FEA(inp: FEA.FEA_INP, mu: dict[str,np.ndarray]=None, kappa: dict[str,np.ndarray]=None, density: dict[str,np.ndarray]=None) -> FEA.Main.FEA_Main:
        """
        Initialize the FEA class with the given input parameters.

        Parameters:
            inp (FEA.FEA_INP): The input parameters for the FEA class.

        Returns:
            FEA.Main.FEA_Main: An instance of the FEA_Main class with the given input parameters.
            
        """
        fe = FEA.from_inp(inp)
        
        # assign the materials
        if mu is not None and kappa is not None and density is not None:
            for str_now in mu.keys():
                materials_now = materials.NeoHookean(mu=torch.from_numpy(mu[str_now]).to(fe.nodes.device).to(fe.nodes.dtype),
                                                        kappa=torch.from_numpy(kappa[str_now]).to(fe.nodes.device).to(fe.nodes.dtype),)

                fe.elems[str_now].set_density(torch.from_numpy(density[str_now]).to(fe.nodes.device).to(fe.nodes.dtype))
                fe.elems[str_now].set_materials(materials_now)        # convert the C3D4 elements to C3D10 elements
        ## find all edges of the elements
        str_now = 'element-0'
        nodes_now = fe.nodes.clone()
        # nodes_new, elems_new = fe.elems[str_now].to_C3D10(nodes_now=nodes_now)
        
        # Update the element in FEA
        # fe.elems[str_now] = elems_new
        # fe.nodes = nodes_new
        
        # add loads
        i=0
        while True:
            if 'surface_%d_All' % (i + 1) not in fe.surface_sets.keys():
                break
            fe.add_load(FEA.loads.Pressure(surface_set='surface_%d_All' % (i + 1), pressure=0.),
                        name='Pressure_%d' % i)
            i += 1

        # add boundary condition
        bc_dof = np.where((abs(fe.nodes[:, 2] - 0)
                                < 0.1).cpu().numpy())[0] * 3
        bc_dof = np.concatenate([bc_dof, bc_dof + 1, bc_dof + 2])
        fe.add_constraint(FEA.constraints.Boundary_Condition(indexDOF=bc_dof, dispValue=0.),
                        name='BC')        # add reference point and constraints
        
        
        rp = FEA.ReferencePoint([0., 0., fe.nodes[:, 2].max()],)
        rp_name = fe.add_reference_point(rp=rp)
        indexNodes = np.where((abs(fe.nodes[:, 2] - rp.node[2])
                                < 0.1).cpu().numpy())[0]
        fe.add_constraint(FEA.constraints.Couple(indexNodes=indexNodes, rp_name=rp_name)
        )

        return fe

    @staticmethod
    def _solve_FEA(current_class: 'Morph', path_result, pressure_list: list[float], mu: np.ndarray, kappa: np.ndarray, density: np.ndarray, U_dim: list[int]) -> tuple[list, list, list, list]:
        import os
        os.environ['KMP_DUPLICATE_LIB_OK']='True'
        import sys
        import torch
        sys.path.append(os.getcwd())
        sys.path.append('..//Modules/FEA')
        import FEA
        import pypardiso
        import scipy.sparse as sp

        current_process_name = mp.current_process().name
        try:
            pool_id = int(current_process_name.split("-")[-1]) % 4
        except:
            pool_id = 0

        if torch.cuda.is_available():
            
            cuda_now = (pool_id-1) % torch.cuda.device_count()
            torch.set_default_device('cuda:%d' % cuda_now)
        else:
            torch.set_default_device('cpu')

        # torch.set_default_device(torch.device('cuda:0'))
        torch.set_default_dtype(torch.float64)
        torch.cuda.empty_cache()
        # construct the FEA
        FE_inp = FEA.FEA_INP()
        FE_inp.Read_INP(path_result + '/Cache/' + '/TopOptRun.inp')

        fe = current_class.init_FEA(FE_inp, mu=mu, kappa=kappa, density=density)

        num_pressure = len(pressure_list)
        num_surface = num_pressure + 1

        # change the load
        for j in range(len(pressure_list)):
            fe.loads['Pressure_%d' % j].pressure = pressure_list[j]

        # solve displacement 0

        # fe.elems['element-0'].set_order(1)
        result = fe.solve(tol_error=1e-6)

        # fe.elems['element-0'].set_order(2)
        # fe.refine_RGC()

        
        # result = fe.solve(tol_error=1e-3)

        if not result:
            raise RuntimeError(
                "FEA solver failed to converge. Please check the input parameters."
            )

        GC0 = fe.GC.clone().detach()
        RGC0 = fe._GC2RGC(GC0)

        # region get the decomposed stiffness matrix
        K_indices, K_values = fe._assemble_Stiffness_Matrix(
            RGC=RGC0)[1:]

        K_sp = sp.coo_matrix(
            (K_values.cpu().numpy(),
             (K_indices[0].cpu().numpy(), K_indices[1].cpu().numpy())),
            shape=(fe.GC.shape[0], fe.GC.shape[0])).tocsr()
        K_solver = pypardiso.PyPardisoSolver()
        K_solver.factorize(K_sp)
        # endregion

        # region for Udp calculate the jacobian
        R = torch.zeros([num_pressure, fe.RGC_list_indexStart[-1]])
        for p in range(num_pressure):
            F = torch.zeros([R.shape[1]])
            F_indice, F_values = fe.loads['Pressure_%d' % p]._get_K0_F0(
                fe._GC2RGC(GC0)[0])[:2]
            F.scatter_add_(0, F_indice, F_values)
            R[p, :F.numel()] = F.view([-1])
        R0 = fe.assemble_force(force=R, GC0=GC0)
        Udp0 = K_solver.solve(K_sp, R0.T.cpu().numpy())
        Udp0 = torch.from_numpy(Udp0).to(R.device).to(R.dtype).T
        # Udp0 = fe.solve_linear_perturbation(GC0=GC0, R0=R)
        # endregion


        # region for GCu define the adjoint problem
        R = torch.zeros([len(U_dim), fe.RGC_list_indexStart[-1]])
        for i in range(len(U_dim)):
            R[i, U_dim[i]] = 1

        # solve adjoint problem with displacement 0
        R0 = fe.assemble_force(force=R, GC0=GC0)
        GCv = K_solver.solve(K_sp, -R0.T.cpu().numpy())
        GCv = torch.from_numpy(GCv).to(R.device).to(R.dtype).T
        # GCv = fe.solve_linear_perturbation(GC0=GC0, R0=-R)
        # endregion

        # get the derivative of the stiffness matrix with respect to the pressure
        # region for GCudp

        Kdp_indices = fe._assemble_Stiffness_Matrix(fe._GC2RGC(GC0))[1]

        function_udot = lambda u: fe._assemble_Stiffness_Matrix(fe._GC2RGC(u))[
            2]

        def get_Kdp(dim_now: int):

            def function_p0dot(p):
                p0 = fe.loads['Pressure_%d' % dim_now].pressure
                fe.loads['Pressure_%d' % dim_now].pressure = p
                result = fe._assemble_Stiffness_Matrix(fe._GC2RGC(fe.GC))[2]
                fe.loads['Pressure_%d' % dim_now].pressure = p0
                return result

            # \partial K / \partial u \cdot \partial u / \partial p
            K0_values, Kdp1_values = torch.autograd.functional.jvp(
                function_udot, GC0, Udp0[dim_now])

            # \partial K / \partial p
            _, Kdp2_values = torch.autograd.functional.jvp(
                function_p0dot,
                torch.tensor([pressure_list[dim_now]], dtype=torch.float64),
                torch.ones([1]))

            Kdp0_values = Kdp1_values + Kdp2_values
            Kdp0 = torch.sparse_coo_tensor(Kdp_indices, Kdp0_values).coalesce()
            return Kdp0

        Kdp = []
        for i in range(len(pressure_list)):
            Kdp.append(get_Kdp(i))

        # combine the results
        adjForce = torch.zeros(
            [len(U_dim),
             len(pressure_list), fe.RGC_list_indexStart[-1]])
        for i in range(len(U_dim)):
            for j in range(len(pressure_list)):
                adjForce[i, j, fe.RGC_remain_index_flatten] = Kdp[j] @ GCv[i]

        # solve the second adjoint problem
        for i in range(len(pressure_list)):
            fe.loads['Pressure_%d' % i].pressure = pressure_list[i]
        f = -adjForce.reshape([len(U_dim) * len(pressure_list), -1])

        R0 = fe.assemble_force(force=f, GC0=GC0)
        GCw = K_solver.solve(K_sp, R0.T.cpu().numpy())
        GCw = torch.from_numpy(GCw).to(f.device).to(f.dtype).T
        # GCw = fe.solve_linear_perturbation(GC0=GC0, R0=f)
        GCw = GCw.reshape([len(U_dim), len(pressure_list), -1])  # u,p
        # endregion


        # region for the UdF

        R_F = torch.zeros([len(U_dim), GC0.shape[0]])
        for i in range(len(U_dim)):
            R_F[i, U_dim[i]] = 1
        UdF = K_solver.solve(K_sp, R_F.T.cpu().numpy())
        UdF = torch.from_numpy(UdF).to(R_F.device).to(R_F.dtype).T

        # endregion

        # region for the GCudf

        # calculate the KdF
        function_udot = lambda u: fe._assemble_Stiffness_Matrix(fe._GC2RGC(u))[
            2]

        GCudf = torch.zeros([len(U_dim), len(U_dim), GC0.shape[0]])

        for f_ind in range(len(U_dim)):
            _, KdF1_values = torch.autograd.functional.jvp(
                    function_udot, GC0, UdF[f_ind])
            KdF1_indices = fe._assemble_Stiffness_Matrix(RGC0)[1]

            KdF_values = KdF1_values
            KdF_indices = KdF1_indices
            KdF = torch.sparse_coo_tensor(KdF_indices, KdF_values).coalesce()
            
            for u_ind in range(len(U_dim)):
                # calculate the GCudf
                adjForceW = torch.zeros([fe.RGC_list_indexStart[-1]])
                adjForceW[fe.RGC_remain_index_flatten] = -KdF @ GCv[u_ind]
                R0 = fe.assemble_force(force=adjForceW, GC0=GC0)
                GCudf_now = K_solver.solve(K_sp, R0.T.cpu().numpy())
                GCudf[i,j] = torch.from_numpy(GCudf_now).to(R0.device).to(R0.dtype).flatten()

        # endregion

        return GC0.tolist(), Udp0.tolist(), UdF.tolist(), GCv.tolist(), GCw.tolist(), GCudf.tolist()