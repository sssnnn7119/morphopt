import math
import re
import torchfea
import torch
from torchfea import controller
import morphopt

from .baseobject import BaseObject

from typing import Callable

class ObjectiveFunction(BaseObject):
    """
    This class is responsible for computing the objective function value and the design sensitivity variables.
    """

    def __init__(self):
        self.fe: torchfea.FEAController = None
        """
        The FEA solver instance.
        """
        
        self.fe_results: list[torchfea.solver.StaticResult] = None
        """
        The FEA results for each step.
        """

        self.jacobian_needed: list[str] = []
        """
        A list of load parameter names for which the jacobian is needed for sensitivity analysis.
        """

    def get_metrics(self) -> list[float]:
        """
        Get custom metrics for display.
        
        Returns:
            list[float]: A list of metric values.
        """
        return []
    
    def objective_function(self):
        """
        Compute the objective function value.
        
        Returns:
            torch.Tensor: The value of the objective function.
        """
        raise NotImplementedError("The objective_function method should be implemented in subclass.")

    def set_step(self, step: int):
        """
        Set the current step for the objective function. This can be used to update any step-specific parameters or states.

        Args:
            step (int): The current step index.
        """
        self.fe.assembly.set_load_parameters(self.fe_results[step].load_params)

    def compute_multistep_objective(self, fe_results: list[torchfea.solver.StaticResult], assembly: torchfea.Assembly) -> torch.Tensor:
        """
        Compute the total objective from a multistep FE result list.
        """
        self.fe_results = fe_results
        return self.objective_function()
    
    def sensitivity_analysis(self, params: morphopt.Params) -> dict[str, torch.Tensor]:
        """
        Perform sensitivity analysis to compute the design sensitivity variables.

        Args:
            params: The optimization parameters.

        Returns:
            dict[str, torch.Tensor]: A dictionary of design sensitivity variables for each parameter class.
        """

        design_sensitivity_vars_dict = params.obtain_design_sensitivity_vars(assembly=self.fe.assembly)

        design_sensitivity_vars = torch.cat(list(design_sensitivity_vars_dict.values()), dim=0)
        design_sensitivity_vars_interval = [0]
        for key in design_sensitivity_vars_dict.keys():
            design_sensitivity_vars_interval.append(design_sensitivity_vars_interval[-1] + design_sensitivity_vars_dict[key].shape[0])

        design_gradients = torch.zeros_like(design_sensitivity_vars)

        def apply_func(assembly: torchfea.Assembly, design_sensitivity_vars: torch.Tensor):
            params.modify_assembly(
                {key: design_sensitivity_vars[design_sensitivity_vars_interval[i]:design_sensitivity_vars_interval[i+1]] for i, key in enumerate(design_sensitivity_vars_dict.keys())}, 
                assembly)
            
        solver: torchfea.solver.StaticImplicitSolver = self.fe.solver

        design_gradients = solver.get_jacobian_sensitivity_multistep(
            fe_results=self.fe_results,
            design_vars=design_sensitivity_vars,
            load_names=self.jacobian_needed,
            apply_func=apply_func,
            compute_objective_funcs=self.compute_multistep_objective,
        )
        
        # rescale the gradients
        # design_gradients = design_gradients / (design_gradients.abs().max() + 1e-8)
        
        design_gradients_dict = {key: design_gradients[design_sensitivity_vars_interval[i]:design_sensitivity_vars_interval[i+1]] for i, key in enumerate(design_sensitivity_vars_dict.keys())}
        
        
        morphopt.controller._detach_recursive(morphopt.controller)
        return design_gradients_dict

    @property
    def num_tasks(self) -> int:
        """
        Get the number of tasks.
        """
        return len(self.fe_results)
    
    def pathlog_required(self):
        return ['deformation']

    def __str__(self) -> str:

        result = ["FE_result Summary:"]
        
        for i in range(self.num_tasks):
            result.append(f"=================================Task {i+1}=================================")
            
            
            # 格式化位移向量（一维）
            u_vector = self.fe_results[i].GC[-6:].tolist()
            u_str = " ".join([f"{x:.6f}" for x in u_vector])
            result.append(f"  Displacement U: {u_str}")

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
            deformed_nodes = (ins.nodes + self.fe.assembly._GC2RGC(self.fe_results[case].GC.to(ins.nodes.device))[ins._RGC_index]).detach().cpu().numpy()

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

            # Save the deformed mesh as an STL file
            save_filepath = f"{foldpath}/{self.pathlog_required()[0]}/task_{case}_iter_{iteration}.stl"
            mesh.save(save_filepath, binary=True)
            plotter.close()