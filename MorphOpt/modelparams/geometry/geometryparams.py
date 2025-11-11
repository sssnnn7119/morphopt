
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

class SurfacesParams(BaseParams):
    """
    Class to handle the surfaces of the morphable model.
    """
    from .geometrysurface.cssurfaceinterface import CsInterface as CS
    from .geometrysurface.bspsurfaceinterface import BspInterface as BSP
    from .geometrysurface.cpgeosurfaceinterface import CPGEOSurfaceInterface as CPGEO

    def __init__(self, max_step_length: list[float], fea_seed_size: float, fea_mesh_order: int = 1, reinitialize_per_iter: int = 5, *args, **kwargs) -> None:
        """
        Initialize the Surfaces class.

        Parameters:
            thickness (list[float]): The minimum distance between the surfaces.
        """

        self.surface_list: list[BaseInterface] = []
        """
        List of surface objects.
        """
        
        self._max_step_length: list[float] = max_step_length
        """
        The maximum step length for each surface in the optimization process.
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
        
        self.if_update = [True for _ in range(self.num_surface)]
        if iteration % self.reinitialize_per_iter == 0:
            for i in range(self.num_surface):
                self.surface_list[i].initialize()

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
            self._refinemesh()

    def _refinemesh(self):
        """
        This function refines the mesh of the geometric model of the soft robot.
        """
        inp = GLOBAL.obj_fun.inp
        part = inp.part['final_model']
        for i in range(self.num_surface):
            node_surface = self.surface_list[i].model.map(self.surface_list[i]._coordinates_fea).cpu().numpy().T
            part.nodes[self._surface_node_index[i], 1:] = node_surface

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