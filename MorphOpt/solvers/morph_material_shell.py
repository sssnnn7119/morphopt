import os
import sys
from webbrowser import get

from CPGEO import surface
from FEA.loads import pressure
from FEA.obj_base import Optional
from matplotlib.pyplot import cla
from mayavi.mlab import surf
from networkx import nodes
import numpy as np
import torch


import FEA
import multiprocessing as mp

from ..modelparams.surfaces.SurfaceInterface import CPGEOSphereInterface

from ..modelparams import Params
from ..modelparams.surfaces.Surfaces_offset import Surfaces_offset
from ..GLOBAL import PATH, History
from .base_solver import BaseSolver
from .FE_result import FE_result
from FEA.elements import materials
from CPGEO.utils import mlab_visualization as vis

class MorphMaterialShell(BaseSolver):
    """
    This class is responsible for solving the FEA and get the displacement of the soft robot.
    """

    num_thick_element = 4
    """the number of thick elements in the shell"""

    def __init__(self,
                 params: Params,
                 shell_mu: float,
                 shell_kappa: float,
                 shell_density: float,
                 U_dim: list[int] = [-6, -5, -4, -3, -2, -1],
                 num_process: int = 4):
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
        
        self.surface_params: Surfaces_offset = self.params.surfaces
        """
        Surfaces_offset: An instance of the surfaces parameters of the optimization problem.
        """

        self.num_process = num_process
        """
        int: The number of processes to use for parallel computation.
        """

        self.U_dim: list[int] = U_dim
        """
        list[int]: The dimensions of the interest for the optimization problem.
        """

        self.shell_mu = shell_mu
        """
        float: The shear modulus of the shell material.
        """

        self.shell_kappa = shell_kappa
        """
        float: The bulk modulus of the shell material.
        """

        self.shell_density = shell_density
        """
        float: The density of the shell material.
        """

    def solve(self):
        """
        Solve the optimization problem using the specified solver.

        Returns:
            tuple: the displacement field and its derivatives:
                - fe (FEA.Main.FEA_Main): An instance of the FEA_Main class with the given input parameters.
                - GC0 (list[torch.Tensor]): The displacement field at the reference point.
                - Udp0 (list[torch.Tensor]): The displacement field at the reference point with respect to the pressure.
                - UdF0 (list[torch.Tensor]): The derivative of the displacement field with respect to the external force on the end-effector.
                - GCv (list[torch.Tensor]): The first adjoint displacement field.
                - GCw (list[torch.Tensor]): The second adjoint displacement field.
                - ADJudf (list[torch.Tensor]): The adjoint displacement field with respect to the external force on the end-effector.
        """

        pressure_list = self.params.loads.pressure.get_pressure().tolist()

        fe, mu, kappa, density, surface_names, offseted_shell_nodes = self._initialize()

        fe.export_to_inp(
            PATH.path_Result + '/Log/Deformation/Data/%d.inp'% History.iteration)

        # multiprocess FEA

        # self._solve_FEA(
        #     PATH.path_Result,
        #     pressure_list[0],
        #     self.surface_params.thickness,
        #     self.shell_mu,
        #     self.shell_kappa,
        #     self.shell_density,
        #     surface_names,
        #     offseted_shell_nodes,
        #     mu,
        #     kappa,
        #     density,
        #     self.U_dim,
        # )
        pools = mp.Pool(processes=self.num_process)
        result = []
        for i in range(len(pressure_list)):
            result.append(
                pools.apply_async(self._solve_FEA,
                                  args=(
                                      PATH.path_Result,
                                      pressure_list[i],
                                      self.shell_mu,
                                      self.shell_kappa,
                                      self.shell_density,
                                      surface_names,
                                      offseted_shell_nodes,
                                      mu,
                                      kappa,
                                      density,
                                      self.U_dim,
                                  )))
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

    def _initialize(self):
        FE_inp = FEA.FEA_INP()
        FE_inp.Read_INP(PATH.path_Result + '/Cache/' + '/TopOptRun.inp')

        surface_names = []
        for i in range(self.params.surfaces.num_surface - 1):
            surface_names.append('surface_%d_All' % (i + 1))

        fe = FEA.from_inp(FE_inp)
        offseted_shell_nodes = self.calculate_offseted_shell_nodes(fe, surface_names)

        fe: FEA.FEA_Main = self.init_FEA(FE_inp,
                           shell_mu=self.shell_mu,
                           shell_kappa=self.shell_kappa,
                           shell_density=self.shell_density,
                           offseted_shell_nodes=offseted_shell_nodes,
                           surface_names=surface_names)
        fe.initialize()

        mu = {}
        kappa = {}
        density = {}
        for i in range(len(fe.elems)):
            str_now = 'element-%d' % i
            if str_now not in fe.elems.keys():
                continue
            gaussian_points = fe.elems[str_now].get_gaussian_points(fe.nodes)
            density_now = self.params.materials.get_density(
                gaussian_points).cpu().numpy()
            module = self.params.materials.get_modules(gaussian_points)
            mu_now = module[0].cpu().numpy()
            kappa_now = module[1].cpu().numpy()
            mu[str_now] = mu_now
            kappa[str_now] = kappa_now
            density[str_now] = density_now

            materials_now = materials.NeoHookean(
                mu=torch.from_numpy(mu[str_now]).to(fe.nodes.device).to(
                    fe.nodes.dtype),
                kappa=torch.from_numpy(kappa[str_now]).to(fe.nodes.device).to(
                    fe.nodes.dtype),
            )

            fe.elems[str_now].set_density(
                torch.from_numpy(density[str_now]).to(fe.nodes.device).to(
                    fe.nodes.dtype))
            fe.elems[str_now].set_materials(materials_now)



        return fe, mu, kappa, density, surface_names, offseted_shell_nodes

    def calculate_offseted_shell_nodes(self, fe: FEA.FEA_Main, surface_names: list[str]) -> torch.Tensor:
        """
        Offset unique nodes in surface_elems along CP-surface normals (from params.surfaces.surf_list[1..n]).
        Normals are computed using the CP surface model as in the test (map_c derivative -> cross -> normalize).
        The normal at each FE node is taken from the nearest sampled CP-surface point.

        Returns:
            list[list[np.ndarray]]: The offset shell nodes for each surface
        """
        device = fe.nodes.device
        dtype = fe.nodes.dtype
        eps = torch.tensor(1e-12, device=device, dtype=dtype)

        def get_offseted_points(surface: CPGEOSphereInterface.CPGEOSurfaceInterface, coordinates: torch.Tensor, thickness: float):
            r, rdu = surface.model.map_c(points=coordinates, derivative=1)
            normal = torch.cross(rdu[:, 0, :], rdu[:, 1, :], dim=0)
            normal = normal / torch.norm(normal, dim=0)
            return r + thickness * normal
        
        def get_triangle_normals(points: torch.Tensor, connection: torch.Tensor):
            # Calculate normals for each triangle in the mesh
            p0 = points[:, connection[:, 0]]
            p1 = points[:, connection[:, 1]]
            p2 = points[:, connection[:, 2]]
            v1 = p1 - p0
            v2 = p2 - p0
            normals = torch.cross(v1, v2, dim=0)
            normals_length = torch.norm(normals, dim=0)
            normals = normals / normals_length
            return normals
        offseted_shell_nodes: list[list[np.ndarray]] = []
        for surface_index in range(len(surface_names)):

            # the reference nodes of surface
            surfinterface: CPGEOSphereInterface.CPGEOSurfaceInterface = self.surface_params.surface_list[surface_index+1]
            surfmodel = surfinterface.model
            knots0 = surfmodel.reference_to_curvilinear(surfinterface.surface_out_knots)
            coo0 = surfinterface.surface_out_coo
            edges0 = CPGEOSphereInterface.CPGEO.utils.mesh.get_edges(coo0)
            offseted_points_init = get_offseted_points(surfinterface, knots0, thickness=self.surface_params.thickness)
            normal_tri_0 = get_triangle_normals(offseted_points_init, coo0)

            # optimize the offseted points
            knots_change = (torch.randn_like(knots0) * 1e-10).requires_grad_(True)
            opt = torch.optim.LBFGS(
                params=[knots_change], max_iter=40, line_search_fn='strong_wolfe'
            )
            def closure():
                opt.zero_grad()
                points_offset = get_offseted_points(surfinterface, knots0 + knots_change, thickness=self.surface_params.thickness)
                alpha = 0.1

                loss_distance = alpha *((points_offset - offseted_points_init)**2).sum() + \
                        ((points_offset[:, edges0[:, 0]] - points_offset[:, edges0[:, 1]])**2).sum()

                normal_tri = get_triangle_normals(points_offset, coo0)
                loss_normal = -((normal_tri * normal_tri_0).sum(dim=0)).sum()
                loss = loss_distance + loss_normal * 0

                loss.backward()
                return loss

            for i in range(3):
                opt.step(closure)

            nodes_new = get_offseted_points(surfinterface, knots0 + knots_change.detach(), thickness=self.surface_params.thickness).T

            # link the fea nodes to the surface model coordinates
            surface_elems = fe.get_surface_elements(surface_names[surface_index])[0]._elems
            unique_nodes = torch.unique(surface_elems)
            nodes_fea = fe.nodes[unique_nodes]
            nodes_surface = surfmodel.map_c(knots0).T

            distance_mat = torch.norm(nodes_fea[:, None, :] - nodes_surface[None, :, :], dim=-1)
            index_map = distance_mat.argmin(dim=-1)
        
            nodes_new = nodes_new[index_map]

            # insert the offseted shell nodes for each layer
            offseted_shell_nodes_now = []
            for layer in range(self.num_thick_element):
                # 0-1 mapping from original nodes to new nodes
                ratio = (layer + 1) / self.num_thick_element
                offseted_shell_nodes_now.append((nodes_new * ratio + nodes_fea * (1 - ratio)).cpu().numpy())
            offseted_shell_nodes.append(offseted_shell_nodes_now)

        return offseted_shell_nodes

    @classmethod
    def generate_shell_from_surface(cls, 
            fe: FEA.Main.FEA_Main, surface_names: str, offseted_shell_nodes: np.ndarray, surface_new_name: Optional[str] = None) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, dict]:
        """
        Generate shell elements (C3D6) from triangular surface meshes.
        
        This function takes one or more surfaces (identified by their names in the FEA model),
        and generates wedge elements (C3D6) by extruding the triangular faces
        along their averaged normal directions by a specified thickness.
        
        Args:
            fe (FEA.Main.FEA_Main): The FEA model instance containing the surfaces
            surface_names (str): Name(s) of the surfaces to extrude (e.g., 'surface_1_All' 
                                    or ['surface_1_All', 'surface_2_All'])
            offseted_shell_nodes (np.ndarray): The offset shell nodes to use for the extrusion
            surface_new_name (str, optional): New names for the offset surfaces.
        Returns:
            tuple: A tuple containing:
                - nodes_new (torch.Tensor): Combined node coordinates (original + new nodes)
                - elems_c3d6 (torch.Tensor): Element connectivity for the new C3D6 elements
                - c3d6_indices (torch.Tensor): Indices for the new C3D6 elements
                - offset_surface_sets (dict): Dictionary mapping surface names to offset surface sets
        """

        # Get and combine the triangular elements of all surfaces
        surface_elems = fe.get_surface_elements(surface_names)[0]._elems

        # Get the unique node indices from the triangular elements
        surface_node_indices = torch.unique(
            surface_elems
        )  # Calculate triangle normals for each triangle in the surface using vectorized operations

        # Create a tensor for mapping from global node indices to local indices
        max_node_idx = torch.max(surface_elems).item()
        node_idx_map = torch.full((max_node_idx + 1, ),
                                -1,
                                device=fe.nodes.device,
                                dtype=torch.int64)
        node_idx_map[surface_node_indices] = torch.arange(
            surface_node_indices.shape[0], device=fe.nodes.device)

        # Calculate new nodes by offsetting the original nodes in the normal direction
        new_nodes = torch.tensor(offseted_shell_nodes, device=fe.nodes.device, dtype=fe.nodes.dtype)
        
        # Create C3D6 (wedge) elements
        # Each triangle in the surface becomes a C3D6 element
        # C3D6 connectivity: [bottom_triangle_node0, bottom_triangle_node1, bottom_triangle_node2,
        #                    top_triangle_node0, top_triangle_node1, top_triangle_node2]
        c3d6_elements = torch.zeros(
            (surface_elems.shape[0], 6), device=fe.nodes.device,
            dtype=torch.int64)  # Create the C3D6 elements (vectorized)
        # Original triangle nodes form the base (first 3 columns)
        c3d6_elements[:, 0] = surface_elems[:, 0]
        c3d6_elements[:, 1] = surface_elems[:, 1]
        c3d6_elements[:, 2] = surface_elems[:, 2]

        # New nodes form the top (last 3 columns)
        # Use the same node_idx_map from earlier for mapping node indices
        c3d6_elements[:, 3] = fe.nodes.shape[0] + node_idx_map[surface_elems[:, 0]]
        c3d6_elements[:, 4] = fe.nodes.shape[0] + node_idx_map[surface_elems[:, 1]]
        c3d6_elements[:, 5] = fe.nodes.shape[0] + node_idx_map[surface_elems[:, 2]]

        # Element indices for the new C3D6 elements - find the largest existing element index
        max_elem_index = max([(torch.max(elem_group._elems_index).item()
                            if hasattr(elem_group, '_elems_index')
                            and elem_group._elems_index.numel() > 0 else 0)
                            for elem_group in fe.elems.values()],
                            default=0)

        c3d6_indices = torch.arange(max_elem_index + 1,
                                    max_elem_index + 1 + surface_elems.shape[0],
                                    device=fe.nodes.device,
                                    dtype=torch.int64)    # Combine the original nodes with the new nodes
        nodes_new = torch.cat([fe.nodes, new_nodes], dim=0)

        # Create a dictionary to store the offset surface sets
        # For each original surface name, we'll create a set for the top face (Surface 1) of the wedge elements
        offset_surface_sets = {}

        # Track which wedge elements correspond to each original surface
        start_idx = 0
        
        # Count triangles in this surface
        num_triangles = surface_elems.shape[0]

        # Create surface set for the offset surface (face index 1 - top triangular face)
        # The format needed is a list of [element_index, surface_index] pairs
        offset_surface = []
        for j in range(num_triangles):
            elem_index = c3d6_indices[start_idx + j].item()
            # Surface index 1 corresponds to the top triangular face (nodes 3, 4, 5) in C3D6
            surf_index = 1
            offset_surface.append(elem_index)
        
        # Store the offset surface set
        if offset_surface:
            if surface_new_name is not None:
                offset_name = surface_new_name
            else:
                offset_name = f"{surface_names}_offset"

            offset_surface_sets[offset_name] = [(np.array(offset_surface), 1)]
        
        # Update the starting index for the next surface
        start_idx += num_triangles

        return nodes_new, c3d6_elements.cpu(), c3d6_indices.cpu(), offset_surface_sets

    @classmethod
    def add_shell_elements_to_model(cls, fe: FEA.Main.FEA_Main, nodes_new: torch.Tensor,
                                    c3d6_elements: torch.Tensor,
                                    c3d6_indices: torch.Tensor,
                                    name_new_elements: str = "shell_elements",
                                    offset_surface_sets: dict = None):
        """
        Add the generated shell elements to the FEA model.
        
        Args:
            fe (FEA.Main.FEA_Main): The FEA model instance
            nodes_new (torch.Tensor): Combined node coordinates (original + new nodes)
            c3d6_elements (torch.Tensor): Element connectivity for the new C3D6 elements
            c3d6_indices (torch.Tensor): Indices for the new C3D6 elements
            offset_surface_sets (dict, optional): Dictionary mapping surface names to offset surface sets
            
        Returns:
            FEA.Main.FEA_Main: Updated FEA model with the shell elements added
        """
        import FEA
        # Create a new FEA_Main instance with the updated nodes
        new_fe = FEA.Main.FEA_Main(nodes_new)

        # Copy all the original elements from the old model
        for elem_name, elem_obj in fe.elems.items():
            new_fe.elems[elem_name] = elem_obj

        # Create new C3D6 elements and add them to the model
        new_fe.add_element(FEA.elements.C3.C3D6(elems=c3d6_elements,
                                                elems_index=c3d6_indices),
                        name=name_new_elements)    # Copy node sets, element sets, and surface sets
        for name, node_set in fe.node_sets.items():
            new_fe.add_node_set(name, node_set)

        for name, elem_set in fe.element_sets.items():
            new_fe.add_element_set(name, elem_set)

        for name, surf_set in fe.surface_sets.items():
            new_fe.add_surface_set(name, surf_set)
            
        # Add the offset surface sets if provided
        if offset_surface_sets:
            for name, surf_set in offset_surface_sets.items():
                new_fe.add_surface_set(name, surf_set)

        # Copy reference points
        for rp_name, rp in fe.reference_points.items():
            new_rp = FEA.ReferencePoint(rp.node)
            new_fe.add_reference_point(new_rp, name=rp_name)

        # Copy loads
        for load_name, load_obj in fe.loads.items():
            new_fe.loads[load_name] = load_obj

        # Copy constraints
        for const_name, const_obj in fe.constraints.items():
            new_fe.constraints[const_name] = const_obj

        return new_fe

    
    @classmethod
    def init_FEA(cls, inp: FEA.FEA_INP,
                 shell_mu: float,
                 shell_kappa: float,
                 shell_density: float,
                 offseted_shell_nodes: list[list[np.ndarray]],
                 surface_names: list[str],
                 mu: dict[str, np.ndarray] = None,
                 kappa: dict[str, np.ndarray] = None,
                 density: dict[str, np.ndarray] = None) -> FEA.Main.FEA_Main:
        """
        Initialize the FEA class with the given input parameters.

        Parameters:
            inp (FEA.FEA_INP): The input parameters for the FEA class.

        Returns:
            FEA.Main.FEA_Main: An instance of the FEA_Main class with the given input parameters.
            
        """
        fe = FEA.from_inp(inp)

        fe.maximum_iteration = 100

        surface_names_list = [surface_names]
        for i in range(cls.num_thick_element):
            if i < cls.num_thick_element - 1:
                surface_new_name = [surface_names[k] + ('_offset%d'%i) for k in range(len(surface_names))]
            else:
                surface_new_name = [surface_names[k] + '_offset' for k in range(len(surface_names))]
            surface_names_list.append(surface_new_name)

        for i in range(cls.num_thick_element):

            nodes_new = []
            c3d6_elements = []
            c3d6_indices = []
            offset_surface_sets = {}

            for k in range(len(surface_names_list[i])):
                nodes_new, c3d6_elements_now, c3d6_indices_now, offset_surface_sets_now = cls.generate_shell_from_surface(
                    fe=fe, surface_names=surface_names_list[i][k], offseted_shell_nodes=offseted_shell_nodes[k][i], surface_new_name=surface_names_list[i+1][k])

                # update the indices
                if k > 0:
                    elems_offset = (- c3d6_indices_now.min() + c3d6_indices[-1].max() + 1).item()
                    c3d6_indices_now = c3d6_indices_now + elems_offset
                    surf_ind = offset_surface_sets_now[surface_names_list[i+1][k]][0][1]
                    surf_elem = offset_surface_sets_now[surface_names_list[i+1][k]][0][0] + elems_offset
                    offset_surface_sets_now[surface_names_list[i+1][k]][0] = (surf_elem, surf_ind)

                fe.nodes = nodes_new
                c3d6_elements.append(c3d6_elements_now)
                c3d6_indices.append(c3d6_indices_now)
                offset_surface_sets.update(offset_surface_sets_now)

            c3d6_elements = torch.cat(c3d6_elements, dim=0)  # Combine all new elements
            c3d6_indices = torch.cat(c3d6_indices, dim=0)  # Combine all new indices

            # Add the shell elements to create a new model
            fe = FEA.elements.add_shell_elements_to_model(
                fe=fe, nodes_new=nodes_new, c3d6_elements=c3d6_elements,c3d6_indices= c3d6_indices, name_new_elements='shell_elements%d'%i, offset_surface_sets=offset_surface_sets)

        if cls.num_thick_element > 2:
            fe.merge_elements(element_name_list=['shell_elements%d'%i for i in range(cls.num_thick_element-1)], element_name_new='shell_elements')
        else:
            fe.elems['shell_elements'] = fe.elems['shell_elements0']
            del fe.elems['shell_elements0']


        
        # fe.elems['shell_elements'] = fe.elems['shell_elements0']
        # del fe.elems['shell_elements0']
        fe.elems['pressure_elements'] = fe.elems['shell_elements%d' % (cls.num_thick_element - 1)]
        del fe.elems['shell_elements%d' % (cls.num_thick_element - 1)]


        # convert the elements to C3D10 and C3D15
        # element_names_to_convert = list(fe.elems.keys())
        # fe = FEA.elements.convert_to_second_order(fe,
        #                                  element_names_to_convert)

        
        fe = FEA.elements.convert_to_second_order(
            fe, element_names=['pressure_elements'])
        elem_pressure: FEA.elements.C3D15 = fe.elems['pressure_elements']
        elem_pressure.surf_order = torch.tensor([1, 0, 0, 0, 0], device='cpu').reshape([1, -1]).repeat([elem_pressure._elems.shape[0], 1])

        # assign the materials to the elements
        if mu is not None and kappa is not None and density is not None:
            for str_now in mu.keys():
                materials_now = materials.NeoHookean(
                    mu=torch.from_numpy(mu[str_now]).to(fe.nodes.device).to(
                        fe.nodes.dtype),
                    kappa=torch.from_numpy(kappa[str_now]).to(
                        fe.nodes.device).to(fe.nodes.dtype),
                )

                fe.elems[str_now].set_density(
                    torch.from_numpy(density[str_now]).to(fe.nodes.device).to(
                        fe.nodes.dtype))
                fe.elems[str_now].set_materials(materials_now)

        # assign the shell material to the elements
        materials_shell = materials.NeoHookean(
            mu=torch.tensor(shell_mu,
                            dtype=torch.float64,
                            device=fe.nodes.device),
            kappa=torch.tensor(shell_kappa,
                               dtype=torch.float64,
                               device=fe.nodes.device),
        )
        fe.elems['shell_elements'].set_density(
            torch.tensor(shell_density,
                         dtype=torch.float64,
                         device=fe.nodes.device))
        fe.elems['shell_elements'].set_materials(materials_shell)

        fe.elems['pressure_elements'].set_density(
            torch.tensor(shell_density,
                         dtype=torch.float64,
                         device=fe.nodes.device))
        fe.elems['pressure_elements'].set_materials(materials_shell)
        
        # add loads
        i = 0
        while True:
            if 'surface_%d_All_offset' % (i + 1) not in fe.surface_sets.keys():
                break
            fe.add_load(FEA.loads.Pressure(
                surface_set='surface_%d_All_offset' % (i + 1), pressure=0.),
                        name='Pressure_%d' % i)
            i += 1

        # add boundary condition
        bc_dof = np.where((abs(fe.nodes[:, 2] - 0)
                                < 0.1).cpu().numpy())[0] * 3
        bc_dof = np.concatenate([bc_dof, bc_dof + 1, bc_dof + 2])
        fe.add_constraint(FEA.constraints.Boundary_Condition(indexDOF=bc_dof,
                                                             dispValue=0.),
                          name='BC')

        # add reference point and constraints
        rp = FEA.ReferencePoint([0., 0., fe.nodes[:, 2].max()], )
        rp_name = fe.add_reference_point(rp=rp)
        indexNodes = np.where((abs(fe.nodes[:, 2] - rp.node[2])
                               < 0.1).cpu().numpy())[0]
        fe.add_constraint(
            FEA.constraints.Couple(indexNodes=indexNodes, rp_name=rp_name))

        mid_nodes_index = fe.elems['element-0'].get_2nd_order_point_index()
        fe.nodes[mid_nodes_index[:,
                                 0]] = (fe.nodes[mid_nodes_index[:, 1]] +
                                        fe.nodes[mid_nodes_index[:, 2]]) / 2.0

        return fe

    @classmethod
    def _solve_FEA(current_class, path_result: str,
                   pressure_list: list[float], shell_mu: float, shell_kappa: float, shell_density: float,
                   surface_names: list[str], offseted_shell_nodes: list[list[np.ndarray]], mu: np.ndarray, kappa: np.ndarray,
                   density: np.ndarray, U_dim: list[int]):
        import os
        os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
        import sys
        import torch
        sys.path.append(os.getcwd())
        import FEA
        import pypardiso
        import scipy.sparse as sp

        current_process_name = mp.current_process().name
        try:
            pool_id = int(current_process_name.split("-")[-1]) % 4
        except:
            pool_id = 0

        if torch.cuda.is_available():

            cuda_now = (pool_id - 1) % torch.cuda.device_count()
            torch.set_default_device('cuda:%d' % cuda_now)
        else:
            torch.set_default_device('cpu')

        # torch.set_default_device(torch.device('cuda:0'))
        torch.set_default_dtype(torch.float64)
        torch.cuda.empty_cache()
        # construct the FEA
        FE_inp = FEA.FEA_INP()
        FE_inp.Read_INP(path_result + '/Cache/' + '/TopOptRun.inp')

        fe = current_class.init_FEA(FE_inp,
                                    shell_mu=shell_mu,
                                    shell_kappa=shell_kappa,
                                    shell_density=shell_density,
                                    surface_names=surface_names,
                                    offseted_shell_nodes=offseted_shell_nodes,
                                    mu=mu,
                                    kappa=kappa,
                                    density=density)

        num_pressure = len(pressure_list)
        num_surface = num_pressure + 1

        # change the load
        for j in range(len(pressure_list)):
            fe.loads['Pressure_%d' % j].pressure = pressure_list[j]

        # solve displacement 0

        result = fe.solve(tol_error=1e-6)
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

        def get_Rdp(dim_now: int):
            def function_p0dot(p):
                p0 = fe.loads['Pressure_%d' % dim_now].pressure
                fe.loads['Pressure_%d' % dim_now].pressure = p
                result = fe._assemble_Stiffness_Matrix(fe._GC2RGC(fe.GC))[0]
                fe.loads['Pressure_%d' % dim_now].pressure = p0
                return result
            _, Rdp = torch.autograd.functional.jvp(
                function_p0dot,
                torch.tensor([pressure_list[dim_now]], dtype=torch.float64),
                torch.ones([1]))
            return Rdp
        

        Rdp = torch.zeros([num_pressure, fe.GC.shape[0]])
        for p in range(num_pressure):
            Rdp[p] = get_Rdp(p)
        Udp0 = -K_solver.solve(K_sp, Rdp.T.cpu().numpy())
        Udp0 = torch.from_numpy(Udp0).to(Rdp.device).to(Rdp.dtype).T
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
                GCudf[u_ind,f_ind] = torch.from_numpy(GCudf_now).to(R0.device).to(R0.dtype).flatten()

        # endregion

        return GC0.tolist(), Udp0.tolist(), UdF.tolist(), GCv.tolist(), GCw.tolist(), GCudf.tolist()
