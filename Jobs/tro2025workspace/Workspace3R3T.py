import os
import sys

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import numpy as np
import torch
from MorphOpt import GLOBAL
from MorphOpt.opt_loop import _Controller
from MorphOpt.modelparams import Surfaces, Loads, Materials
from MorphOpt import initializer
from MorphOpt import solvers
from MorphOpt.updaters.surface import update_surfaces
from MorphOpt.updaters.updaters import Updaters
from MorphOpt import generatemodel
from MorphOpt.modelparams import Params as _Params


class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self, U: torch.Tensor, Udp: torch.Tensor, UdF: torch.Tensor, *args, **kwargs):
        objective = torch.tensor(0.).cpu()

        normal_list = []
        Udp_loss_list = []  
        for i in range(U.shape[0]):

            ratio = ((i // 32) % 2) == 0
            ratio = -1 if ratio else 1

            U_now = U[i].clone()

            U1 = U_now.clone() / 3
            U1[3] = (-1 / 36 * U_now[3]**3)
            U1[4] = (-1 / 36 * U_now[4]**3)
            U1[5] = (-1 / 36 * U_now[5]**3)

            Udp_now = Udp[i].clone()

            if i < 64:
                Udp_left = Udp_now[1:]
                Udp_loss = Udp_now[0]
            else:
                ratio *= -1
                Udp_left = Udp_now[[4, 5, 0, 1, 2]]
                Udp_loss = Udp_now[3]

            normal = torch.zeros(6, device='cpu')
            normal[0] = torch.det(Udp_left[:, 1:])
            normal[1] = torch.det(Udp_left[:, [0, 2, 3, 4, 5]]) * -1
            normal[2] = torch.det(Udp_left[:, [0, 1, 3, 4, 5]])
            normal[3] = torch.det(Udp_left[:, [0, 1, 2, 4, 5]]) * -1
            normal[4] = torch.det(Udp_left[:, [0, 1, 2, 3, 5]])
            normal[5] = torch.det(Udp_left[:, :-1]) * -1
            normal *= ratio

            print(i, (normal.cpu() * Udp_loss).sum().item())
            normal_list.append(normal)
            Udp_loss_list.append(Udp_loss)

            objective += (normal.cpu() * U1).sum()

        if objective > 0:
            objective *= -1
        return objective

    
    
GLOBAL.obj_fun = ObjectiveFunction()


class Params(_Params):

    class SurfaceParams(Surfaces):

        def __rotate120_240(self, r0):
            r0_120 = torch.zeros_like(r0)
            r0_120[0] = r0[0] * np.cos(2 * np.pi / 3) - r0[1] * np.sin(
                2 * np.pi / 3)
            r0_120[1] = r0[0] * np.sin(2 * np.pi / 3) + r0[1] * np.cos(
                2 * np.pi / 3)
            r0_120[2] = r0[2]

            r0_240 = torch.zeros_like(r0)
            r0_240[0] = r0[0] * np.cos(4 * np.pi / 3) - r0[1] * np.sin(
                4 * np.pi / 3)
            r0_240[1] = r0[0] * np.sin(4 * np.pi / 3) + r0[1] * np.cos(
                4 * np.pi / 3)
            r0_240[2] = r0[2]

            return r0_120, r0_240

        def __init__(self):

            super().__init__(max_step_length=[0.2, 0.2,0.2, 0.2,0.2, 0.2,0.2], reinitialize_per_iter=4)

            self.add_surface(
                Surfaces.BSP.initialize_cylinder(r0=15.,
                                                 length=150.,
                                                 seed_size=1.0,
                                                 symmetric=[0],
                                                 flip=False,
                                                 maxR=0.2,
                                                 maxC=0.8,
                                                 maxFF=0.2))
            self.add_surface(
                Surfaces.CPGEO.initialize_Sphere(seed_size=1.0,
                                                 flip=True,
                                                 r0=4.,
                                                 init_location=[8, 0, 50], MaxC=2.0))

            self.add_surface(
                Surfaces.CPGEO.initialize_Sphere(seed_size=1.0,
                                                 flip=True,
                                                 r0=4.,
                                                 init_location=[-4, 7, 50], MaxC=2.0))

            self.add_surface(
                Surfaces.CPGEO.initialize_Sphere(seed_size=1.0,
                                                 flip=True,
                                                 r0=4.,
                                                 init_location=[-4, -7, 50], MaxC=2.0))

            self.add_surface(
                Surfaces.CPGEO.initialize_Sphere(seed_size=1.0,
                                                 flip=True,
                                                 r0=4.,
                                                 init_location=[8, 0, 100], MaxC=2.0))

            self.add_surface(
                Surfaces.CPGEO.initialize_Sphere(seed_size=1.0,
                                                 flip=True,
                                                 r0=4.,
                                                 init_location=[-4, 7, 100], MaxC=2.0))

            self.add_surface(
                Surfaces.CPGEO.initialize_Sphere(seed_size=1.0,
                                                 flip=True,
                                                 r0=4.,
                                                 init_location=[-4, -7, 100], MaxC=2.0))

        def initialize(self, iteration: int):

            if iteration % self.reinitialize_per_iter == 0:
                self.surface_list[0].initialize()
                self.surface_list[1].initialize()
                self.surface_list[4].initialize()

            # rotate the exterior surface
            num_points = self.surface_list[0].model.control_points.shape[2] / 3
            num_points = int(num_points)
            r0 = self.surface_list[0].model.control_points[:, :, :num_points]
            r0_120, r0_240 = self.__rotate120_240(r0)
            self.surface_list[0].model.control_points[:, :,
                                                    num_points:num_points *
                                                    2] = r0_120
            self.surface_list[0].model.control_points[:, :,
                                                    num_points * 2:] = r0_240

            # rotate the bottom surface
            r1 = self.surface_list[1].model.cp_vertices
            r1_120, r1_240 = self.__rotate120_240(r1)
            self.surface_list[2].model.cp_vertices = r1_120
            self.surface_list[2].model.cp_elements = self.surface_list[1].model.cp_elements
            self.surface_list[2].model.initialize()
            self.surface_list[2].model.pre_load(1)

            self.surface_list[3].model.cp_vertices = r1_240
            self.surface_list[3].model.cp_elements = self.surface_list[1].model.cp_elements
            self.surface_list[3].model.initialize()
            self.surface_list[3].model.pre_load(1)


            # rotate the top surface
            r4 = self.surface_list[4].model.cp_vertices
            r4_120, r4_240 = self.__rotate120_240(r4)
            self.surface_list[5].model.cp_vertices = r4_120
            self.surface_list[5].model.cp_elements = self.surface_list[4].model.cp_elements
            self.surface_list[5].model.initialize()
            self.surface_list[5].model.pre_load(1)

            self.surface_list[6].model.cp_vertices = r4_240
            self.surface_list[6].model.cp_elements = self.surface_list[4].model.cp_elements
            self.surface_list[6].model.initialize()
            self.surface_list[6].model.pre_load(1)

        def get_geometry_values(self):
            r0, r0du, r0du2 = self.surface_list[0].get_geometry_values()

            r1, r1du, r1du2 = self.surface_list[1].get_geometry_values()
            r2, r3 = self.__rotate120_240(r1)
            r2du, r3du = self.__rotate120_240(r1du.reshape([3, -1]))
            r2du = r2du.reshape_as(r1du)
            r3du = r3du.reshape_as(r1du)
            r2du2, r3du2 = self.__rotate120_240(r1du2.reshape([3, -1]))
            r2du2 = r2du2.reshape_as(r1du2)
            r3du2 = r3du2.reshape_as(r1du2)

            r4, r4du, r4du2 = self.surface_list[4].get_geometry_values()
            r5, r6 = self.__rotate120_240(r4)
            r5du, r6du = self.__rotate120_240(r4du.reshape([3, -1]))
            r5du = r5du.reshape_as(r4du)
            r6du = r6du.reshape_as(r4du)
            r5du2, r6du2 = self.__rotate120_240(r4du2.reshape([3, -1]))
            r5du2 = r5du2.reshape_as(r4du2)
            r6du2 = r6du2.reshape_as(r4du2)

            r = [r0, r1, r2, r3, r4, r5, r6]
            rdu = [r0du, r1du, r2du, r3du, r4du, r5du, r6du]
            rdu2 = [r0du2, r1du2, r2du2, r3du2, r4du2, r5du2, r6du2]

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
                self.surface_list[4].get_surface_parameters().flatten().detach(
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
            self.surface_list[4].set_surface_parameters(
                    xlist[2].detach().clone())

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
            surf_ind = [0, 1, 4]
            for i in range(len(params)):

                r = x_change_list[i].norm(dim=0)

                dx = 2 / torch.pi * torch.atan(r) * x_change_list[i] / (
                    r + 1e-15) * self._max_step_length[i]

                self.surface_list[surf_ind[i]].update_variables(dx)

        def get_points_weight(self) -> list[torch.Tensor]:
            """
            Get the weights for the points in the optimization process.

            Returns:
                list[torch.Tensor]: The weights for the points in the optimization process.
            """

            w0 = self.surface_list[0].get_points_weight()
            w1 = self.surface_list[1].get_points_weight()
            w4 = self.surface_list[4].get_points_weight()
            
            weight = [w0, w1, w1, w1, w4, w4, w4]
            return weight



    class LoadParams(Loads):

        class _Pressure(Loads.Pressures):

            def __init__(self):
                super().__init__()
                p_max = 0.06
                guassian_points = (np.array([-1 / np.sqrt(3), 1 / np.sqrt(3)])
                                   + 1) / 2 * p_max

                self.pressure = torch.zeros([2, 2, 4, 8, 2, 3])
                # [下面or上面， 最小or最大， 下面其他or上面其他， 其他， 下面气压or上面气压】
                self.pressure[0, 0, :, :, 0, 0] = 0.
                self.pressure[0, 1, :, :, 0, 0] = p_max
                self.pressure[1, 0, :, :, 1, 0] = 0.
                self.pressure[1, 1, :, :, 1, 0] = p_max

                for p1 in range(2):
                    for p2 in range(2):
                        for P1 in range(2):
                            for P2 in range(2):
                                for P3 in range(2):
                                    self.pressure[0, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 0,
                                                  1] = guassian_points[p1]
                                    self.pressure[0, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 0,
                                                  2] = guassian_points[p2]
                                    self.pressure[0, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 1,
                                                  0] = guassian_points[P1]
                                    self.pressure[0, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 1,
                                                  1] = guassian_points[P2]
                                    self.pressure[0, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 1,
                                                  2] = guassian_points[P3]

                                    self.pressure[1, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 1,
                                                  1] = guassian_points[p1]
                                    self.pressure[1, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 1,
                                                  2] = guassian_points[p2]
                                    self.pressure[1, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 0,
                                                  0] = guassian_points[P1]
                                    self.pressure[1, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 0,
                                                  1] = guassian_points[P2]
                                    self.pressure[1, :, p1 * 2 + p2,
                                                  P1 * 4 + P2 * 2 + P3, 0,
                                                  2] = guassian_points[P3]

                self.pressure = self.pressure.reshape([-1, 6])
                print(self.pressure.shape)

        def __init__(self):
            self.pressure = self._Pressure()

    class MaterialParams(Materials):

        def __init__(self):
            super().__init__(
                mu=0.482,
                kappa=48.,
                density=1.08e-9,
            )

    def __init__(self):
        super().__init__(surfaces=self.SurfaceParams(),
                         loads=self.LoadParams(),
                         materials=self.MaterialParams())


class Generator(generatemodel.Generator):

    def __init__(self,
                 surfaces: Surfaces,
                 path_output: str = None,
                 path_queue: str = None) -> None:
        """
        Initialize the Genetrator class.
        
        Parameters:
            surfaces (Surfaces): The surfaces of the soft robot.
            path_output (str): The path to the output directory.
            path_queue (str): The path to the queue directory.
        """
        super().__init__(seed_size=4.5,
                         surfaces=surfaces,
                         path_output=path_output,
                         path_queue=path_queue)


class Solver(solvers.Morph):
    """
    Solver class for MorphOpt.
    This class is responsible for solving the finite element analysis (FEA) problem.
    """

    def __init__(self, params: Params):

        super().__init__(params=params,
                         num_process=5)


class Updater(Updaters):
    """
    Updater class for MorphOpt.
    This class is responsible for updating the design variables based on the results of the optimization process.
    """

    def __init__(self, params: Params, *args, **kwargs):
        super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                         loads=None,
                         *args,
                         **kwargs)

    class UpdaterSurfaces(update_surfaces.UpdaterSurfaces):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(params=params,
                             max_step_iter=300)

            self.add_objective_function(
                update_surfaces.objectivefuncs.ShapeDerivativeContinuation())
            self.add_objective_function(
                update_surfaces.objectivefuncs.Fairness(surfaces=params.surfaces))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Distance(min_distance=np.ones([params.surfaces.num_surface, params.surfaces.num_surface]) * 2.5))
            self.add_objective_function(
                update_surfaces.objectivefuncs.boundarys.Cylinder(radius=20.,
                                                               height=150.,
                                                               bottom=0.))

        def initialize(self, iter_now, sensitivity, *args, **kwargs):
            if iter_now < 60:
                self.params_update._max_step_length[0] = 0.06
                for i in range(1, len(self.params_update._max_step_length)):
                    self.params_update._max_step_length[i] = 0.8
            else:
                self.params_update._max_step_length[0] = 0.2
                for i in range(1, len(self.params_update._max_step_length)):
                    self.params_update._max_step_length[i] = 0.2

            super().initialize(iter_now=iter_now, sensitivity=sensitivity, *args, **kwargs)

        def _refine_sensitivity(self, iter_now, sensitivity):
            sensitivity = super()._refine_sensitivity(iter_now, sensitivity)
            
            if iter_now % 10 < 60 and iter_now % 500 < 60:
                for ind_surf in range(1, len(sensitivity)):
                    sensitivity[ind_surf] += sensitivity[ind_surf].abs(
                    ).max() * 0.1
            return sensitivity

if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')

    path_result = 'D:/Songzenan/Results'
    opt_label = '6A3R3T'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()

    generator = Generator(surfaces=params.surfaces,
                          path_output=GLOBAL.PATH.path_Result + '/Cache/',
                          path_queue=GLOBAL.PATH.path_Queue)

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = _Controller(params=params,
                            generator=generator,
                            solver=solvers,
                            updater=updater)
    controller.opt_loop()
