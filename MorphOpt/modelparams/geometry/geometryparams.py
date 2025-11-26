
import datetime
from email.policy import default
import os
import shutil
import time
import FEA
import numpy as np
import torch
from .geometrysurface.basesurfaceinterface import BaseInterface
from ..base_params import BaseParams
from ... import GLOBAL


class MeshQualityOptimizer:
    """Simplified optimizer assuming tetra connectivity is already a numpy int array of shape [Ne,4]."""
    def __init__(self, elements: np.ndarray, nodes: np.ndarray):
        self.elements = torch.from_numpy(elements.copy())
        self.nodes = torch.from_numpy(nodes.copy())

    @staticmethod
    def signed_volume(nodes: torch.Tensor, conn: torch.Tensor) -> torch.Tensor:
        tets = nodes[conn]
        v0, v1, v2, v3 = tets[:,0], tets[:,1], tets[:,2], tets[:,3]
        return torch.einsum('ij,ij->i', torch.cross(v2-v0, v3-v0, dim=1), v1-v0)/6.0

    @staticmethod
    def aspect_penalty(nodes: torch.Tensor, conn: torch.Tensor, target: float=3.0) -> torch.Tensor:
        t = nodes[conn]
        edges = [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]
        lens = [ (t[:,a]-t[:,b]).norm(dim=1) for a,b in edges ]
        L = torch.stack(lens, dim=1)
        aspect = L.max(dim=1).values / (L.min(dim=1).values + 1e-12)
        return torch.relu(aspect - target).pow(2).mean()

    def run(self, index_internal: np.ndarray, nodes_new: np.ndarray, iters: int=5, lr: float=0.001,
        w_inv=1., w_boundary=10.0,
        min_vol_ratio=0.001,
        # Augmented Lagrangian parameters (for equality constraint g=0 on boundary)
        al_rho_init: float = 100.0,
        al_rho_max: float = 1e6,
        al_increase: float = 10.0,
        al_tol: float = 1e-8):
        nodes = self.nodes.clone().requires_grad_(True)
        conn = self.elements

        # Target boundary coordinates to match exactly
        nodes_new_boundary = torch.from_numpy(nodes_new[~index_internal]).detach().clone()

        # Use L-BFGS with strong Wolfe line search
        opt = torch.optim.LBFGS(
            [nodes],
            lr=lr,
            max_iter=50,            # inner iterations per step (line-search driven)
            history_size=50,
            tolerance_grad=1e-10,
            tolerance_change=1e-6,
            line_search_fn="strong_wolfe",
        )

        # Augmented Lagrangian state (note: boundary nodes are not optimization variables here).
        # We still keep the AL scaffolding for extensibility; with boundary clamped, g==0 always.
        rho = float(al_rho_init)

        # Outer iterations: augmented Lagrangian updates + early stopping on constraints and volumes
        last_min_vol = None
        last_g_norm = None
        for _ in range(max(1, iters)):
            def closure():
                opt.zero_grad()
                nodes_iter = nodes.clone()

                # Physics/quality term: barrier on inverted/near-inverted tets
                vol = self.signed_volume(nodes_iter, conn)
                loss_inv = torch.exp(-(vol + min_vol_ratio) / 0.01).sum()

                # Augmented Lagrangian term for boundary equality (degenerates to zero due to clamp)
                g = nodes_iter[~index_internal] - nodes_new_boundary  # should be 0
                aug = 0.5 * rho * (g * g).sum()

                loss = w_inv * loss_inv + aug
                loss.backward()
                return loss

            loss_val = opt.step(closure)

            # Check early stopping condition (all tets positive volume)
            with torch.no_grad():
                nodes_iter = nodes.clone()
                vol_now = self.signed_volume(nodes_iter, conn)
                last_min_vol = vol_now.min().item()

                g = nodes_iter[~index_internal] - nodes_new_boundary

                print("  Current min volume: %.6e, Current match residual: %.3e\r" % (
                    last_min_vol, g.abs().max().item()
                ), end='')
                if last_min_vol >= min_vol_ratio:
                    break


        # write back nodes
        print()
        print("Mesh optimization done. Min volume: %.6e" % (
            last_min_vol if last_min_vol is not None else float('nan'),
        ))
        return nodes.detach(), last_min_vol, g.abs().max().item()




class GeometryParams(BaseParams):
    """
    Class to handle the surfaces of the morphable model.
    """
    from .geometrysurface.cssurfaceinterface import CsInterface as CS
    from .geometrysurface.bspsurfaceinterface import BspInterface as BSP
    from .geometrysurface.cpgeosurfaceinterface import CPGEOSurfaceInterface as CPGEO

    def __init__(self, fea_seed_size: float, max_step_length: list[float] = [], fea_mesh_order: int = 1, reinitialize_per_iter: int = 5, *args, **kwargs) -> None:
        """
        Initialize the Surfaces class.

        Parameters:
            thickness (list[float]): The minimum distance between the surfaces.
        """

        self.surface_list: list[BaseInterface] = []
        """
        List of surface objects.
        """
        
        self._max_step_length_max: list[float] = max_step_length
        """
        The maximum step length for each surface in the optimization process.
        """

        self._max_step_length: list[float] = max_step_length
        """
        The current maximum step length for each surface in the optimization process.
        """

        self._step_length_min_ratio: float = 0.02
        """
        The minimum ratio for the step length relative to the maximum step length.
        """

        self._step_length_decay: float = 0.5
        """
        The decay factor for the step length relative to the maximum step length.
        """

        self._step_length_increase: float = 1.2
        """
        The increase factor for the step length relative to the maximum step length.
        """
        
        self.if_update = []
        """
        A list indicating whether each surface needs to be updated.
        True means the surface needs to be updated, False means it does not.
        """

        self.reinitialize_per_iter = reinitialize_per_iter
        """
        The number of iterations after which the surfaces are reinitialized.
        This is useful for ensuring that the surfaces are updated periodically during the optimization process.
        """
        self.fea_seed_size = fea_seed_size
        """
        The seed size for the finite element analysis (FEA).
        """
        
        self.fea_mesh_order = fea_mesh_order
        """
        The mesh order for the finite element analysis (FEA).
        """

        self._surface_node_index: list[np.ndarray] = []
        """
        The indices of the surface nodes.
        """
        
    def initialize(self, iteration: int):
        """
        Initialize the surfaces for the optimization process.
            determine which surfaces need to be updated.
            initialize the surfaces.
        """

        if len(self._max_step_length_max) != self.num_surface:
            self._max_step_length_max = [0.5] * self.num_surface
            self._max_step_length = [0.5] * self.num_surface
        
        self.if_update = [True for _ in range(self.num_surface)]
        if iteration % self.reinitialize_per_iter == 0:
            for i in range(self.num_surface):
                self.surface_list[i].initialize()

        if iteration > 2:
            obj_before = GLOBAL.History.history_objective[iteration - 2]
            obj_now = GLOBAL.History.history_objective[iteration-1]

            if obj_now > obj_before:
                for i in range(len(self._max_step_length)):
                    self._max_step_length[i] = max(
                        self._max_step_length[i] * self._step_length_decay, 
                        self._max_step_length_max[i] * self._step_length_min_ratio)
            else:
                for i in range(len(self._max_step_length)):
                    self._max_step_length[i] = min(
                        self._max_step_length[i] * self._step_length_increase, 
                        self._max_step_length_max[i])


    def add_surface(self, surface_new: BaseInterface) -> None:
        """
        Add a surface object to the list.

        Parameters
        ----------
        surface : Surface
            The surface object to be added.
        """
        self.surface_list.append(surface_new)
        
    @property
    def num_surface(self) -> int:
        """
        Get the number of surfaces.

        Returns:
            length (int) :The number of surfaces.
        """
        return len(self.surface_list)
    
    def get_geometry_values(self) -> list[torch.Tensor]:
        """
        Get the geometry values of the surfaces.

        Returns:
            list[tuple]: A tuple containing the geometry values of the surfaces.
                - r (list[torch.Tensor]): The point coordinates of the surfaces.
                - rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
                - rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
        """
        
        rlist = [self.surface_list[i].get_geometry_values() for i in range(self.num_surface)]
        r = [rlist[i][0] for i in range(self.num_surface)]
        rdu = [rlist[i][1] for i in range(self.num_surface)]
        rdu2 = [rlist[i][2] for i in range(self.num_surface)]
        return r, rdu, rdu2
    
    def get_penalty_fairness(self, weight: list[torch.Tensor], r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor]) -> torch.Tensor:
        """
        Get the penalty fairness of the surfaces.

        Parameters:
            weight (list[torch.Tensor]): The weights for the points in the optimization process.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.

        Returns:
            torch.Tensor: The penalty fairness of the surfaces.
        """
        
        penalty = []
        for i in range(self.num_surface):
            penalty.append(self.surface_list[i].get_penalty_fairness(weight[i], r[i], rdu[i], rdu2[i]))
        
        return penalty
    
    def get_points_weight(self) -> list[torch.Tensor]:
        """
        Get the weights for the points in the optimization process.

        Returns:
            list[torch.Tensor]: The weights for the points in the optimization process.
        """
        
        weight = [self.surface_list[i].get_points_weight() for i in range(self.num_surface)]
        return weight
    
    def get_parameters(self) -> torch.Tensor:
        """
        Get the current variables of the surfaces.

        Returns:
            list[torch.Tensor]: The current variables of the surfaces.
        """
        
        xlist = []
        for i in range(self.num_surface):
            if not self.if_update[i]:
                xlist.append(torch.zeros([0]))
                continue
            xlist.append(self.surface_list[i].get_surface_parameters().flatten().detach().clone())
        return xlist
    
    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the current variables of the surfaces.

        Parameters:
            xlist (list[torch.Tensor]): The new variables for the surfaces.
        """
        for i in range(self.num_surface):
            if not self.if_update[i]:
                continue
            self.surface_list[i].set_surface_parameters(xlist[i].detach().clone())
            
    def get_variables(self) -> torch.Tensor:
        """
        Get the current variables of the surfaces.

        Returns:
            torch.Tensor: The current variables of the surfaces.
        """
        xlist = self.get_parameters()
        x_flatten = torch.cat([torch.randn_like(xlist[i].flatten())*1e-6 for i in range(len(xlist))])
        return x_flatten
    
    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the surfaces with the new variables.

        Parameters:
            xlist_change (torch.Tensor): The change of variables for the surfaces.
        """
        
        x_change_list = []
        start = 0
        for i in range(self.num_surface):
            
            if self.if_update[i]:
                end = start + self.surface_list[i].num_variables
            else:
                end = start + 0
            x_change_list.append(x_change[start:end].reshape([3, -1]))
            start = end

        for i in range(self.num_surface):
            
            if not self.if_update[i]:
                continue
            
            r = x_change_list[i].norm(dim=0)
            
            dx = 2/torch.pi * torch.atan(r) * x_change_list[i] / (r + 1e-15) * self._max_step_length[i]
            
            self.surface_list[i].update_variables(dx)

    def save(self, filepath):
        for i in range(self.num_surface):
            self.surface_list[i].save(filepath + '/Surface-%d_iter-%d' %
                              (i, GLOBAL.History.iteration))

    def load(self, filepath, iteration):
        for i in range(self.num_surface):
            self.surface_list[i].load(filepath + '/Surface-%d_iter-%d' %
                              (i, iteration))
            # self.surface_list[i].initialize()
            
    def plot(self):
        for sf in range(self.num_surface):
            if sf == 0:
                alpha = 0.6
            else:
                alpha = 1
            self.surface_list[sf].plot(alpha=alpha, color=(40.0 / 255, 120.0 / 255, 181.0 / 255))

    def save_figure(self, filepath):
        from mayavi import mlab

        fig = mlab.figure(bgcolor=(1, 1, 1), size=(800, 800))
        fig.scene.parallel_projection = True

        self.plot()
        
        # Get all points to determine bounding box
        all_points = []
        for i in range(self.num_surface):
            r, _, _ = self.surface_list[i].get_geometry_values()
            all_points.append(r)

        all_points = torch.cat(all_points, dim=1)
        x_min, x_max = all_points[0].min().item(), all_points[0].max().item()
        y_min, y_max = all_points[1].min().item(), all_points[1].max().item()
        z_min, z_max = all_points[2].min().item(), all_points[2].max().item()

        # Add some padding to the bounds
        padding = 0.05 * max(x_max-x_min, y_max-y_min, z_max-z_min)
        axes = mlab.axes(xlabel='X', ylabel='Y', zlabel='Z', 
                        color=(0, 0, 0),
                        extent=[x_min-padding, x_max+padding, 
                               y_min-padding, y_max+padding, 
                               z_min-padding, z_max+padding])
        axes.label_text_property.color = (0, 0, 0)  # Set text color to black
        axes.axes.property.color = (0, 0, 0)       # Set axes lines color to black
        
        mlab.view(azimuth=210, elevation=70, distance=300)
        mlab.savefig(filepath + '%d.jpg'%GLOBAL.History.iteration)
        mlab.close()
    
    def generate(self, material_para: list[float] | list[torch.Tensor]) -> None:
        """
        This function generates the geometric model of the soft robot.
        It calls the Rhino application to generate the model and then calls Abaqus for finite element analysis (FEA).
        """

        if GLOBAL.History.iteration % self.reinitialize_per_iter == 0:
            self._regenerate(material_para=material_para)
        else:
            last_min_vol, max_g = self._refinemesh()
            if max_g > 5e-1 or last_min_vol < 0:
                self._regenerate(material_para=material_para)
        
        # for i in range(self.num_surface):
        #     self.surface_list[i].pre_load()

    def _refinemesh(self):
        """
        This function refines the mesh of the geometric model of the soft robot.
        """
        from .utils import mesh

        # update each surface nodes
        inp = GLOBAL.obj_fun.inp
        part = inp.part['final_model']
        nodes_new = part.nodes[:, 1:].copy()
        index_internal = np.ones([part.nodes.shape[0]], dtype=bool)
        for i in range(self.num_surface):
            node_surface = self.surface_list[i].model.map(self.surface_list[i]._coordinates_fea).cpu().numpy().T
            nodes_new[self._surface_node_index[i]] = node_surface
            nodes_new = self.surface_list[i].refine_fea_mesh(part, i, nodes_new)

            index_internal[list(part.sets_nodes['surface_%d_All' % i])] = False

        # optimize internal nodes & fix element orientation
        elements = list(part.elems.values())[0][:, 1:]
        optimizer = MeshQualityOptimizer(elements=elements, nodes=part.nodes[:, 1:])
        nodes_new, last_min_vol, max_g = optimizer.run(index_internal=index_internal, nodes_new=nodes_new, iters=5, lr=0.08)

        part.nodes[:, 1:] = nodes_new.detach().cpu().numpy()

        inp.write_inp('Z:/temp/iter%d_refine.inp' % GLOBAL.History.iteration)

        return last_min_vol, max_g

    def _regenerate(self, material_para: list[float]) -> None:
        """
        This function regenerates the geometric model of the soft robot.
        It calls the Rhino application to generate the model and then calls Abaqus for finite element analysis (FEA).
        """
        path_output = GLOBAL.PATH.path_Result + '/Cache/'
        path_queue = GLOBAL.PATH.path_Queue + '/'

        # export the data
        que_names = self._export_data(path_output, path_queue)
        
        # call Rhino to generate the model
        self._call_rhino(que_Names=que_names)

        # call Abaqus for FEA
        self._call_Abaqus(path_output, material_para, self.fea_seed_size, self.fea_mesh_order)

        # read the inp file
        inp_path = GLOBAL.PATH.path_Result + '/Cache/TopOptRun.inp'
        inp = FEA.FEA_INP()
        inp.read_inp(path=inp_path)

        GLOBAL.obj_fun.inp = inp

        # match the points on the surfaces
        self._match_points_surface()

    def _match_points_surface(self):
        """
        Match the points on the surfaces after FEA meshing.
        """
        inp = GLOBAL.obj_fun.inp
        nodes = inp.part['final_model'].nodes[:, 1:]

        temp = torch.tensor([1.])
        default_device = temp.device

        self._surface_node_index = []
        for i in range(self.num_surface):
            if self.surface_list[i].surf_type == 0:
                surf_set_now = np.unique(np.array(list(inp.part['final_model'].sets_nodes['surface_%d_Lateral' % i])))
            else:
                surf_set_now = np.unique(np.array(list(inp.part['final_model'].sets_nodes['surface_%d_All' % i])))
            self._surface_node_index.append(surf_set_now)
            surf_nodes = torch.from_numpy(nodes[surf_set_now]).T.to(default_device)
            self.surface_list[i].match_points_surface(surf_nodes)

    def _export_data(self, path_output: str, path_queue: str) -> list[str]:
        """
        This function export the data of each surfaces
        """
        
        # export each surface with Rhino
        que_Names = []
        for i in range(self.num_surface):
            surf_name0 = '__surface-%d' % i
            name = self.surface_list[i].output_data(path_output=path_output, name_output=surf_name0, flip=(i!=0))
            
            info = '%d\n%s\n%s' % (self.surface_list[i].surf_type, path_output +
                                name, path_output + surf_name0 + '.stp')
            que_name = 'T' + datetime.datetime.now().strftime(
                "%Y%m%d%H%M%S") + '_%d.txt' % i
            with open(path_queue + que_name, 'w') as f:
                f.write(info.replace('/', '\\\\'))
            que_Names.append(path_queue + que_name)
        for que_file in que_Names:
            while os.path.exists(que_file):
                time.sleep(0.1)    
        return que_Names
    
    def _call_rhino(self, que_Names: list[str]) -> None:
        """
        This function is a placeholder for calling Rhino, a 3D computer graphics and computer-aided design (CAD) application.
        It is currently not implemented.
        """
        for que_file in que_Names:
            while os.path.exists(que_file):
                time.sleep(0.1)

    def _call_Abaqus(self, path_output: str, material_para: list[float], seed_size: float, mesh_order: int) -> None:
        
        current_path = os.getcwd()

        shutil.copy(os.path.dirname(os.path.abspath(__file__)) + '/_Abaqus/GenModel.py', path_output)
        with open(path_output + '__FEM_Para_Base.txt', 'w') as f:

            # surface type
            f.write('Surfaces*\t')
            for sf in self.surface_list:
                f.write('%d\t' % sf.surf_type)
            f.write('\n')

            # materials
            f.write(
                'Material*\t%s\t%e\t%d\t%e\t%e\n' %
                ('Rubber', material_para[0], material_para[1],
                material_para[2], material_para[3]))

            # Seed size
            f.write('SeedSize*\t%e\n' % seed_size)

            # mesh order
            f.write('MeshOrder*\t%d\n' % mesh_order)
        
        os.chdir(path_output)
        os.system('abaqus cae noGUI=' + path_output + '/GenModel.py')
        os.chdir(current_path)