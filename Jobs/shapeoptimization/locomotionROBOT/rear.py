import os
import sys
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import GLOBAL
from MorphOpt.opt_loop import Controller
from MorphOpt.modelparams import Surfaces, Loads, Materials
from MorphOpt import initializer
from MorphOpt import solvers
from MorphOpt.updaters.surface import update_surfaces
from MorphOpt.updaters.updaters import Updaters
from MorphOpt import generatemodel
from MorphOpt.modelparams import Params as _Params


class Params(_Params):
    class SurfaceParams(Surfaces):

        def __init__(self):

            super().__init__(max_step_length=[0.4, 0.4, 0.4, 0.0])

            self.add_surface(
                Surfaces.BSP.initialize_cylinder(r0=21.,
                                                        length=70.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        flip=False, maxR=0.1, maxC=0.8, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=5.,
                                                    length=64.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[-10, -10, 3],
                                                    flip=True, maxR=0.1, maxC=0.8, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=5.,
                                                    length=64.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[-10, 10, 3],
                                                    flip=True, maxR=0.1, maxC=0.8, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=5.,
                                                    length=64.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[10, 10, 3],
                                                    flip=True, maxR=0.1, maxC=0.8, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=5.,
                                                    length=64.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[10, -10, 3],
                                                    flip=True, maxR=0.1, maxC=0.8, maxFF=0.2, perturbation_L=12.))

            
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=3.,
                                                    length=64.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[0, 0, 3],
                                                    flip=True, maxR=0.1, maxC=0.8, maxFF=0.2,))
            
            self.if_update = [True, True, True, False]


        def initialize(self, iteration):
            super().initialize(iteration)
            # self.if_update[0] = False
            control_points_ = self.surface_list[1].model.control_points.clone()

            control_points_[0] *= -1
            control_points_[1] *= -1

            self.surface_list[2].model.control_points = control_points_

            # for the surface 0
            # rotation symmetric
            s1 = int(self.surface_list[0].model.control_points.shape[2] / 4)
            part1 = self.surface_list[0].model.control_points[:, :, 0:s1]
            part2 = self.surface_list[0].model.control_points[:, :, s1:s1*2]
            part3 = self.surface_list[0].model.control_points[:, :, s1*2:s1*3]
            part4 = self.surface_list[0].model.control_points[:, :, s1*3:s1*4]

            part2 = part2.flip(dims = [2])
            part2[0] *= -1
            part3[0] *= -1
            part3[1] *= -1
            part4 = part4.flip(dims = [2])
            part4[1] *= -1

            part1 = (part1 + part2 + part3 + part4) / 4
            part2 = part1.flip(dims = [2])
            part2[0] *= -1
            part3 = part1.clone()
            part3[0] *= -1
            part3[1] *= -1
            part4 = part1.flip(dims = [2])
            part4[1] *= -1

            self.surface_list[0].model.control_points = torch.cat([part1, part2, part3, part4], dim=2)
 

        def get_geometry_values(self):
            r0, r0du, r0du2 = self.surface_list[0].get_geometry_values()

            r1, r1du, r1du2 = self.surface_list[1].get_geometry_values()

            r3, r3du, r3du2 = self.surface_list[3].get_geometry_values()
            
            r2 = r1.clone()
            r2[0] *= -1
            r2[1] *= -1

            r2du = r1du.clone()
            r2du[0] *= -1
            r2du[1] *= -1

            r2du2 = r1du2.clone()
            r2du2[0] *= -1
            r2du2[1] *= -1

            r = [r0, r1, r2, r3]
            rdu = [r0du, r1du, r2du, r3du]
            rdu2 = [r0du2, r1du2, r2du2, r3du2]

            return r, rdu, rdu2

        def get_parameters(self) -> torch.Tensor:
            """
            Get the current variables of the surfaces.

            Returns:
                list[torch.Tensor]: The current variables of the surfaces.
            """

            xlist = [
                self.surface_list[0].get_surface_parameters().flatten().detach(
                ).clone(),
                self.surface_list[1].get_surface_parameters().flatten().detach(
                ).clone(),
            ]
            return xlist

        def set_parameters(self, xlist: list[torch.Tensor]) -> None:
            """
            Set the current variables of the surfaces.

            Parameters:
                xlist (list[torch.Tensor]): The new variables for the surfaces.
            """
            self.surface_list[0].set_surface_parameters(
                    xlist[0].detach().clone())
            self.surface_list[1].set_surface_parameters(
                    xlist[1].detach().clone())

        def update_variables(self, x_change: torch.Tensor) -> None:
            """
            Update the surfaces with the new variables.

            Parameters:
                xlist_change (torch.Tensor): The change of variables for the surfaces.
            """
            
            params = self.get_parameters()

            x_change_list = []
            start = 0
            for i in range(len(params)):
                end = start + params[i].numel()
                x_change_list.append(x_change[start:end].reshape([3, -1]))
                start = end

            x_new = []
            surf_ind = [0, 1]
            for i in range(len(params)):

                r = x_change_list[i].norm(dim=0)

                dx = 2 / torch.pi * torch.atan(r) * x_change_list[i] / (
                    r + 1e-15) * self._max_step_length[i]

                self.surface_list[surf_ind[i]].update_variables(dx)
            

    class LoadParams(Loads):
        class _Pressure(Loads.Pressures):
            def __init__(self):
                super().__init__()
                self.pressure = torch.Tensor([[0.06, 0.0, 0.0]])
        
        def __init__(self):
            self.pressure = self._Pressure()
            
    class MaterialParams(Materials):
        
        def __init__(self):
            super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
    
    def __init__(self):
        super().__init__(surfaces=self.SurfaceParams(), loads=self.LoadParams(), materials=self.MaterialParams())

class Generator(generatemodel.Genetrator):
    def __init__(self, surfaces: Surfaces, path_output: str = None, path_queue: str = None) -> None:
        """
        Initialize the Genetrator class.
        
        Parameters:
            surfaces (Surfaces): The surfaces of the soft robot.
            path_output (str): The path to the output directory.
            path_queue (str): The path to the queue directory.
        """
        super().__init__(seed_size=2.5, surfaces=surfaces, path_output=path_output, path_queue=path_queue)

class Solver(solvers.Morph):
    """
    Solver class for MorphOpt.
    This class is responsible for solving the finite element analysis (FEA) problem.
    """

    def __init__(self, params: Params):

        super().__init__(params=params,
                         num_process=1)

class Updater(Updaters):
    """
    Updater class for MorphOpt.
    This class is responsible for updating the design variables based on the results of the optimization process.
    """

    def __init__(self, params: Params, *args, **kwargs):
        super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                         loads=None, *args, **kwargs)

    @staticmethod
    def objective_function(U: torch.Tensor, Udp: torch.Tensor, *args, **kwargs):
        
        UdF: torch.Tensor = kwargs.get('UdF', torch.zeros([U.shape[0], U.shape[1], U.shape[1]]))
        loss = (U[0, -2]-2.0)**2 - U[0, 0] / 1000 + (UdF**2).sum() / 500

        return loss

    class UpdaterSurfaces(update_surfaces.UpdaterSurfaces):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(
                params=params,
                max_step_iter=100)

            self.add_objective_function(update_surfaces.objectivefuncs.Sensitivity())
            self.add_objective_function(
                update_surfaces.objectivefuncs.Fairness(surfaces=params.surfaces))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Distance(min_distance=
                                                            [[2.0, 3.0, 3.0, 3.0],
                                                             [3.0, 2.0, 3.0, 3.0],
                                                             [3.0, 3.0, 2.0, 3.0],
                                                             [3.0, 3.0, 3.0, 2.0]]))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Boundary.Cylinder(radius=22., height=70., bottom=0.))
    
    
if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')

    path_result = 'Z:/Results'
    opt_label = 'FRONT'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()
    
    generator = Generator(surfaces=params.surfaces,path_output=GLOBAL.PATH.path_Result + '/Cache/', path_queue=GLOBAL.PATH.path_Queue)

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, generator=generator, solver=solvers, updater=updater)
    controller.opt_loop()
