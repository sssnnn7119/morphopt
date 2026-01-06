import math
import torchfea
import numpy as np
import torch
import scipy.sparse as sp
import pypardiso
import morphopt

from .baseobject import BaseObject

class ObjectiveFunction(BaseObject):
    """
    The objective functions in morphopt.
    """

    def __init__(self):
        self.fe: torchfea.FEAController = None
        """
        The FEA solver instance.
        """

        self.inp: torchfea.FEA_INP = None
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
    
    def set_results(self, fe: torchfea.FEAController,
                    U: torch.Tensor) -> None:
        """
        Update the results of the FEA solver.
        """
        self.fe = fe
        self.U = U.cpu()
    @property
    def num_tasks(self) -> int:
        """
        Get the number of tasks.
        """
        return self.U.shape[0]
    
    def pathlog_required(self):
        return ['deformation']

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
            morphopt.controller.params.feamodel.process_fea(fe=self.fe, step_index=step_index)
            
            # region get the decomposed stiffness matrix
            R, K_indices, K_values = self.fe.assembly.assemble_Stiffness_Matrix(GC=self.U[step_index].to(self.fe.assembly.device))
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

    def save(self, foldpath: str, iteration: int, insname: str = 'final_model', surface: str = 'surface_0_All') -> None:
        """
        Save the figures of the FEA results.

        Parameters:
            foldpath (str): The path to save the figures.
            iteration (int): The current iteration number.
        """
        ins = self.fe.assembly.get_instance(insname)
        surfaces = [surface]
        surface_elements: list[torchfea.elements.BaseSurface] = []
        for i in range(len(surfaces)):
            surface_elements = surface_elements + ins.surfaces.get_elements(surfaces[i])
        
        surface_connections = [surface_elements[i].surf_elems_circ.cpu().numpy() for i in range(len(surface_elements))]

        for case in range(self.num_tasks):
            deformed_nodes = (ins.nodes + self.fe.assembly._GC2RGC(self.U[case].to(ins.nodes.device))[ins._RGC_index]).detach().cpu().numpy()

            import pyvista as pv

            plotter = pv.Plotter(off_screen=True, window_size=(1200, 1200))

            # Create faces list for pyvista
            faces = []
            for connection in surface_connections:
                for face in connection:
                    if -1 not in face:
                        faces.append([len(face)] + list(face))

            # Create pyvista mesh
            mesh = pv.PolyData(deformed_nodes, faces)
            plotter.add_mesh(mesh, color=(40.0/255, 120.0/255, 181.0/255), opacity=1.0)

            x_min, x_max = deformed_nodes[:,0].min().item(), deformed_nodes[:,0].max().item()
            y_min, y_max = deformed_nodes[:,1].min().item(), deformed_nodes[:,1].max().item()
            z_min, z_max = deformed_nodes[:,2].min().item(), deformed_nodes[:,2].max().item()

            # Add some padding to the bounds
            padding = 0.05 * max(x_max-x_min, y_max-y_min, z_max-z_min)
            
            plotter.show_bounds(xtitle='X', ytitle='Y', ztitle='Z', color='black',
                                bounds=[x_min-padding, x_max+padding, 
                                        y_min-padding, y_max+padding, 
                                        z_min-padding, z_max+padding])
            
            # Approximate view
            plotter.set_background('white')
            plotter.enable_parallel_projection()
            azimuth = 210
            elevation = 20
            plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                math.sin(math.radians(elevation))))

            # Save the figure as a PNG file
            plotter.screenshot(f"{foldpath}/{self.pathlog_required()[0]}/task_{case}_iter_{iteration}.png")

            # Save the deformed mesh as an OBJ file
            obj_filepath = f"{foldpath}/{self.pathlog_required()[0]}/task_{case}_iter_{iteration}.obj"
            mesh.save(obj_filepath)
            plotter.close()