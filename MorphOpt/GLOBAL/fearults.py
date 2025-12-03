import FEA
import numpy as np
import torch
import scipy.sparse as sp
import pypardiso

from MorphOpt import GLOBAL
class ObjectiveFunction:
    """
    The objective functions in MorphOpt.
    """

    def __init__(self):
        self.fe: FEA.FEAController = None
        """
        The FEA solver instance.
        """

        self.inp: FEA.FEA_INP = None
        """
        The FEA .inp file.
        """
        
        self.U: torch.Tensor
        """
        The displacement field.
        [shape: (num_tasks, num_dofs)]
        """

        self.ADJu: torch.Tensor
        """
        The first adjoint displacement field.
        [shape: (num_tasks, num_dofs)]
        """

        self.K_sp: list[sp.csr_matrix]
        """
        The sparse stiffness matrices.
        [shape: (num_tasks,)]
        """

        self.K_solver: list[pypardiso.PyPardisoSolver]
        """
        The solvers for the stiffness matrix.
        [shape: (num_tasks,)]
        """

    def get_objective(self, *args, **kwargs) -> torch.Tensor:
        """
        Get the value of the objective function.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            torch.Tensor: The value of the objective function.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def set_results(self, fe: FEA.FEAController,
                    U: torch.Tensor) -> None:
        """
        Update the results of the FEA solver.
        """
        del self.fe
        self.fe = fe
        self.U = U.cpu()
    @property
    def num_tasks(self) -> int:
        """
        Get the number of tasks.
        """
        return self.U.shape[0]

    def calculate_adjoint(self, *args, **kwargs) -> torch.Tensor:
        """
        Calculate the adjoint variables.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def calculate_adjoint_problem(self, *args, **kwargs) -> torch.Tensor:
        """
        Calculate the linear factor of the objective function.
        """

        def closure_JdU(U: torch.Tensor) -> torch.Tensor:
            U0 = self.U
            self.U = U
            obj = self.get_objective()
            self.U = U0
            return obj
        
        ADJFu_now: torch.Tensor = -torch.autograd.functional.jacobian(closure_JdU, self.U.detach().clone())

        ADJu = []
        K_sp_list = []
        K_solver_list = []
        for step_index in range(self.num_tasks):

            # set the loads
            GLOBAL.controller.params.feamodel.process_fea(fe=self.fe, step_index=step_index)
            
            # region get the decomposed stiffness matrix
            K_indices, K_values = self.fe.assembly.assemble_Stiffness_Matrix(GC=self.U[step_index].to(self.fe.assembly.device))[1:]
            K_values = K_values.cpu().numpy()
            K_indices = K_indices.cpu().numpy()
            K_sp = sp.coo_matrix(
                (K_values,
                (K_indices[0], K_indices[1])), dtype=np.float64,
                shape=(self.fe.assembly.GC.shape[0], self.fe.assembly.GC.shape[0])).tocsr()
            K_solver = pypardiso.PyPardisoSolver()
            K_solver.factorize(K_sp)

            K_sp_list.append(K_sp)
            K_solver_list.append(K_solver)

            # endregion

            # region calculate the adjoint variable
            
            ADJu_now = torch.from_numpy(K_solver.solve(K_sp, ADJFu_now[step_index].cpu().numpy())).cpu()
            ADJu.append(ADJu_now)
            # endregion

        self.ADJu = torch.stack(ADJu, dim=0).cpu()
        self.K_sp = K_sp_list
        self.K_solver = K_solver_list

    def __str__(self) -> str:

        result = ["FE_result Summary:"]
        
        for i in range(self.num_tasks):
            result.append(f"=================================Task {i+1}=================================")
            
            
            # 格式化位移向量（一维）
            u_vector = self.U[i][-6:].tolist()
            u_str = " ".join([f"{x:.6f}" for x in u_vector])
            result.append(f"  Displacement U: {u_str}")
            
            # # 格式化Jacobian矩阵（二维）
            # if self.Udp is not None:
            #     matrix = self.Udp[i][:, -6:].T.tolist()  # 二维矩阵
            #     result.append(f"  Jacobian Udp:")
            #     # 格式化并添加矩阵每行
            #     formatted = format_matrix(matrix, indent=4)
            #     result.extend(formatted)
            
            # # 格式化UdF矩阵（二维）
            # if self.UdF is not None:
            #     matrix = self.UdF[i][:, -6:].tolist()  # 二维矩阵
            #     result.append(f"  UdF:")
            #     formatted = format_matrix(matrix, indent=4)
            #     result.extend(formatted)

            result.append(f"============================================================================")
        
        return "\n".join(result)
        
    def __getitem__(self, key):
        """
        Get the attribute with the given key.
        
        Parameters:
            key: The key of the attribute to get.
            
        Returns:
            The attribute value.
            
        Raises:
            KeyError: If the key is not found.
        """
        if hasattr(self, key):
            return getattr(self, key)
        else:
            raise KeyError(f"'{key}' not found in FE_result")

    def save_figure(self, filepath: str, iteration: int, insname: str = 'final_model', surface: str = 'surface_0_All') -> None:
        """
        Save the figures of the FEA results.

        Parameters:
            filepath (str): The path to save the figures.
            iteration (int): The current iteration number.
        """
        ins = self.fe.assembly.get_instance(insname)
        surfaces = [surface]
        surface_elements: list[FEA.elements.BaseSurface] = []
        for i in range(len(surfaces)):
            surface_elements = surface_elements + ins.surfaces.get_elements(surfaces[i])
        
        surface_connections = [surface_elements[i].surf_elems_circ.cpu().numpy() for i in range(len(surface_elements))]

        for case in range(self.num_tasks):
            deformed_nodes = (ins.nodes + self.fe.assembly._GC2RGC(self.U[case].to(ins.nodes.device))[ins._RGC_index]).detach().cpu().numpy()

            from mayavi import mlab
            from matplotlib.tri import Triangulation
            from tvtk.api import tvtk
            from tvtk.common import configure_input_data

            fig = mlab.figure(size=(800, 800), bgcolor=(1, 1, 1))
            fig.scene.parallel_projection = True
            
            # Draw all surface connections using TVTK

            # Create a dataset with points and cells
            points = tvtk.Points()
            points.from_array(deformed_nodes)

            polys = tvtk.CellArray()
            mesh = tvtk.PolyData()
            mesh.points = points

            # Add all surface connections as polygons - optimized version
            # Pre-calculate the total number of cells and points for pre-allocation
            total_cells = sum(len(connection) for connection in surface_connections)
            polys.allocate(total_cells)

            # Process all faces more efficiently
            for connection in surface_connections:
                for face in connection:
                    # Skip if any node is -1 (placeholder)
                    if -1 in face:
                        continue
                    
                    # More efficient cell insertion
                    n_points = len(face)
                    # Convert face to a list/array compatible with VTK
                    polys.insert_next_cell(n_points)
                    for point_idx in face:
                        polys.insert_cell_point(point_idx)

            mesh.polys = polys

            # Create a mapper and actor
            mapper = tvtk.PolyDataMapper()
            configure_input_data(mapper, mesh)
            actor = tvtk.Actor(mapper=mapper)
            actor.property.color = (40.0/255, 120.0/255, 181.0/255)
            actor.property.opacity = 1.0

            # Add the actor to the scene
            fig.scene.add_actor(actor)

            mlab.view(azimuth=210, elevation=70, distance=300)
            mlab.savefig(f"{filepath}/task_{case}_iter_{iteration}.png")
            mlab.close(fig)