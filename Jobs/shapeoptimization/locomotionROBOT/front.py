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

class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self, U, Udp, UdF, *args, **kwargs):
        loss1 = (U[0, -2]-1.8)**2
        loss2 = (U[1, 2] - 16)**2 / 1000
        loss3 = (UdF**2).sum() / 200000
        return loss1 + loss2 + loss3
GLOBAL.OBJFUN = ObjectiveFunction()

class Params(_Params):
    class SurfaceParams(Surfaces):

        def __init__(self):

            super().__init__(max_step_length=[0.4, 0.4, 0.4, 0.4])

            self.add_surface(
                Surfaces.BSP.initialize_cylinder(r0=21.,
                                                        length=70.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        flip=False, maxR=0.1, maxC=0.8, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=6.,
                                                    length=64.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[-11, 0, 3],
                                                    flip=True, maxR=0.1, maxC=0.8, maxFF=0.2, perturbation_L=12.))
        
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=6.,
                                                    length=64.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[11, 0, 3],
                                                    flip=True, maxR=0.1, maxC=0.8, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=2.,
                                                    length=64.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[0, 0, 3],
                                                    flip=True, maxR=0.1, maxC=0.8, maxFF=0.2,))
            
            self.if_update = [True, True, True, True]


        def _symmetry(self, control_points: torch.Tensor):
            # for the surface 0
            # rotation symmetric
            s1 = int(control_points.shape[2] / 4)
            part1 = control_points[:, :, 0:s1].clone()
            part2 = control_points[:, :, s1:s1*2].clone()
            part3 = control_points[:, :, s1*2:s1*3].clone()
            part4 = control_points[:, :, s1*3:s1*4].clone()

            part2_flipped = part2.flip(dims=[2]).clone()
            part2_flipped = torch.cat([part2_flipped[0:1] * -1, part2_flipped[1:]], dim=0)
            
            part3_mod = part3.clone()
            part3_mod = torch.cat([part3_mod[0:1] * -1, part3_mod[1:2] * -1, part3_mod[2:]], dim=0)
            
            part4_flipped = part4.flip(dims=[2]).clone()
            part4_flipped = torch.cat([part4_flipped[0:1], part4_flipped[1:2] * -1, part4_flipped[2:]], dim=0)

            part1_avg = (part1 + part2_flipped + part3_mod + part4_flipped) / 4
            
            part2_result = part1_avg.flip(dims=[2]).clone()
            part2_result = torch.cat([part2_result[0:1] * -1, part2_result[1:]], dim=0)
            
            part3_result = part1_avg.clone()
            part3_result = torch.cat([part3_result[0:1] * -1, part3_result[1:2] * -1, part3_result[2:]], dim=0)
            
            part4_result = part1_avg.flip(dims=[2]).clone()
            part4_result = torch.cat([part4_result[0:1], part4_result[1:2] * -1, part4_result[2:]], dim=0)

            return torch.cat([part1_avg, part2_result, part3_result, part4_result], dim=2)

        def initialize(self, iteration):
            super().initialize(iteration)
            # self.if_update[0] = False
            control_points_ = self.surface_list[1].model.control_points.clone()

            control_points_[0] *= -1
            control_points_[1] *= -1

            self.surface_list[2].model.control_points = control_points_


            self.surface_list[0].model.control_points = self._symmetry(self.surface_list[0].model.control_points)
            self.surface_list[3].model.control_points = self._symmetry(self.surface_list[3].model.control_points)
 

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
                self.surface_list[3].get_surface_parameters().flatten().detach(
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
            self.surface_list[3].set_surface_parameters(
                    xlist[2].detach().clone())

        def update_variables(self, x_change: torch.Tensor) -> None:
            """
            Update the surfaces with the new variables.

            Parameters:
                xlist_change (torch.Tensor): The change of variables for the surfaces.
            """
            
            params = self.get_parameters()

            x_change_list: list[torch.Tensor] = []
            start = 0
            for i in range(len(params)):
                end = start + params[i].numel()
                x_change_list.append(x_change[start:end].reshape([3, -1]))
                start = end

            x_change_list[0] = self._symmetry(x_change_list[0].reshape_as(self.surface_list[0].model.control_points)).reshape([3, -1])
            x_change_list[2] = self._symmetry(x_change_list[2].reshape_as(self.surface_list[3].model.control_points)).reshape([3, -1])

            x_new = []
            surf_ind = [0, 1]
            for i in range(len(surf_ind)):

                r = x_change_list[i].norm(dim=0)

                dx = 2 / torch.pi * torch.atan(r) * x_change_list[i] / (
                    r + 1e-15) * self._max_step_length[i]

                self.surface_list[surf_ind[i]].update_variables(dx)

            r = x_change_list[2].norm(dim=0)

            dx = 2 / torch.pi * torch.atan(r) * x_change_list[2] / (
                r + 1e-15) * self._max_step_length[3]

            self.surface_list[3].update_variables(dx)
            

    class LoadParams(Loads):
        class _Pressure(Loads.Pressures):
            def __init__(self):
                super().__init__()
                self.pressure = torch.Tensor([[0.06, 0.0, 0.0], [0.06, 0.06, 0.0]])
        
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
                                                            [[2.0, 2.0, 2.0, 2.0],
                                                             [2.0, 2.0, 2.0, 2.0],
                                                             [2.0, 2.0, 2.0, 2.0],
                                                             [2.0, 2.0, 2.0, 2.0]]))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Boundary.Cylinder(radius=22., height=70., bottom=0.))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Boundary.MinRadius(radius=1.9))
    
    
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
