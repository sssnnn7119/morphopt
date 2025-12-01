
import os
import sys


import numpy as np
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())
import FEA
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import *

class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self, *args, **kwargs):
        loss1 = torch.exp(1 - self.U[0, -2]/2.0)
        loss2 = torch.exp(1 - (self.U[1, -4] - self.U[2, -4])/21)
        loss3 = self.U[3, -2]
        return loss1 + loss2 + loss3
GLOBAL.obj_fun = ObjectiveFunction()

class Params(_Params):
    class SurfaceParams(_GeometryParams):

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

            super().__init__(max_step_length=[0.2, 0.2, 0.2, 0.2,0.2], reinitialize_per_iter=4, fea_seed_size=1.5, fea_mesh_order=1)

            self.add_surface(
                self.BSP.initialize_cylinder(r0=21.,
                                                 length=70.,
                                                 seed_size=1.0,
                                                 flip=False,
                                                 maxR=0.2,
                                                 maxC=2.0,
                                                 maxFF=0.2, perturbation_L=14))
            self.add_surface(
                self.BSP.initialize_cylinder(seed_size=1.0,
                                                 flip=True,
                                                 r0=5.,
                                                 length=64.,
                                                 maxR=0.2,
                                                 maxC=2.0,
                                                 init_location=[12, 0, 3], perturbation_L=14))

            self.add_surface(
                self.BSP.initialize_cylinder(seed_size=1.0,
                                                 flip=True,
                                                 r0=5.,
                                                 length=64.,
                                                 maxR=0.2,
                                                 maxC=2.0,
                                                 init_location=[-6, 10.5, 3], perturbation_L=14))

            self.add_surface(
                self.BSP.initialize_cylinder(seed_size=1.0,
                                                 flip=True,
                                                 r0=5.,
                                                 length=64.,
                                                 maxR=0.2,
                                                 maxC=2.0,
                                                 init_location=[-6, -10.5, 3], perturbation_L=14))

            self.add_surface(
                self.BSP.initialize_cylinder(seed_size=1.0,
                                                 flip=True,
                                                 r0=3.,
                                                 length=64.,
                                                maxR=0.2,
                                                maxC=2.0,
                                                 init_location=[0, 0, 3], perturbation_L=14))
            

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
            r0 = self.surface_list[0].model.control_points.clone()
            self.surface_list[0].model.control_points[0] = (r0[0] + r0.flip(dims=[2])[0]) / 2
            self.surface_list[0].model.control_points[1] = (r0[1] - r0.flip(dims=[2])[1]) / 2

            # rotate the bottom surface
            r1 = self.surface_list[1].model.control_points.clone()
            self.surface_list[1].model.control_points[0] = (r1[0] + r1.flip(dims=[2])[0]) / 2
            self.surface_list[1].model.control_points[1] = (r1[1] - r1.flip(dims=[2])[1]) / 2
            r1 = self.surface_list[1].model.control_points

            r1_120, r1_240 = self.__rotate120_240(r1)
            self.surface_list[2].model.control_points = r1_120
            self.surface_list[2].initialize()

            self.surface_list[3].model.control_points = r1_240
            self.surface_list[3].initialize()

            # rotate the exterior surface
            num_points = self.surface_list[4].model.control_points.shape[2] / 3
            num_points = int(num_points)
            r0 = self.surface_list[4].model.control_points[:, :, :num_points]
            r0_120, r0_240 = self.__rotate120_240(r0)
            self.surface_list[4].model.control_points[:, :,
                                                    num_points:num_points *
                                                    2] = r0_240
            self.surface_list[4].model.control_points[:, :,
                                                    num_points * 2:] = r0_120
            r0 = self.surface_list[4].model.control_points.clone()
            self.surface_list[4].model.control_points[0] = (r0[0] + r0.flip(dims=[2])[0]) / 2
            self.surface_list[4].model.control_points[1] = (r0[1] - r0.flip(dims=[2])[1]) / 2

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

            r = [r0, r1, r2, r3, r4]
            rdu = [r0du, r1du, r2du, r3du, r4du]
            rdu2 = [r0du2, r1du2, r2du2, r3du2, r4du2]

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
                
                if surf_ind[i] == 0:
                    num_points = self.surface_list[surf_ind[i]].model.control_points.shape[2] / 3
                    num_points = int(num_points)
                    dx = dx.reshape_as(self.surface_list[surf_ind[i]].model.control_points)
                    r0 = dx[:, :, :num_points]
                    r0_120, r0_240 = self.__rotate120_240(r0)
                    dx[:, :,num_points:num_points * 2] = r0_120
                    dx[:, :,num_points * 2:] = r0_240
                    r0 = dx.clone()
                    dx[0] = (r0[0] + r0.flip(dims=[2])[0]) / 2
                    dx[1] = (r0[1] - r0.flip(dims=[2])[1]) / 2
                    dx = dx.reshape([3, -1])

                if surf_ind[i] == 4:
                    num_points = self.surface_list[surf_ind[i]].model.control_points.shape[2] / 3
                    num_points = int(num_points)
                    dx = dx.reshape_as(self.surface_list[surf_ind[i]].model.control_points)
                    r0 = dx[:, :, :num_points]
                    r0_120, r0_240 = self.__rotate120_240(r0)
                    dx[:, :,num_points:num_points * 2] = r0_240
                    dx[:, :,num_points * 2:] = r0_120
                    r0 = dx.clone()
                    dx[0] = (r0[0] + r0.flip(dims=[2])[0]) / 2
                    dx[1] = (r0[1] - r0.flip(dims=[2])[1]) / 2
                    dx = dx.reshape([3, -1])
                    
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
            
            weight = [w0, w1, w1, w1, w4]
            return weight
          
    class FEAParams(_FEAParams):
        def __init__(self):
            super().__init__()

        def define_interface(self):
            # Common BC / RP / Couple
            self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
            self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 70.]), name='RP_head')
            self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))
            # Define all load interfaces once
            self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'), name='P_s1')
            self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_2_All'), name='P_s2')
            self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_3_All'), name='P_s3')
            self.add_fea_interface(self.ConcentratedMomentInterface(rp_name='RP_head'), name='M_head')
            # Contact self (no amplitude, but needs to exist in FEA)
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_0_All'), name='CS_s0')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_1_All'), name='CS_s1')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_2_All'), name='CS_s2')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_3_All'), name='CS_s3')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_4_All'), name='CS_s4')

        def define_steps(self):
            # Define step amplitudes
            self.set_step_num(4)
            self.set_step_params(0, 'P_s1', [-0.06])
            self.set_step_params(0, 'P_s2', [0.12])
            self.set_step_params(0, 'P_s3', [0.12])
            self.set_step_params(0, 'M_head', [0.0, 0.0, 0.0])

            self.set_step_params(1, 'P_s1', [0.12])
            self.set_step_params(1, 'P_s2', [0.12])
            self.set_step_params(1, 'P_s3', [0.12])
            self.set_step_params(1, 'M_head', [0.0, 0.0, 0.0])

            self.set_step_params(2, 'P_s1', [-0.06])
            self.set_step_params(2, 'P_s2', [-0.06])
            self.set_step_params(2, 'P_s3', [-0.06])
            self.set_step_params(2, 'M_head', [0.0, 0.0, 0.0])

            self.set_step_params(3, 'P_s1', [-0.06])
            self.set_step_params(3, 'P_s2', [-0.06])
            self.set_step_params(3, 'P_s3', [-0.06])
            self.set_step_params(3, 'M_head', [0.0, -60.0, 0.0])
            
    class MaterialParams(_Materials):
        
        def __init__(self):
            super().__init__(mu=0.7, kappa=7.0, density=1.08e-9,)
    
    def __init__(self):
        super().__init__(surfaces=self.SurfaceParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())


class Solver(_MorphSolver):
    """
    Solver class for MorphOpt.
    This class is responsible for solving the finite element analysis (FEA) problem.
    """

    def __init__(self, params: Params):
        super().__init__(params=params,
                         num_process=1)
   
    
class Updater(_Updaters):
    """
    Updater class for MorphOpt.
    This class is responsible for updating the design variables based on the results of the optimization process.
    """

    def __init__(self, params: Params, *args, **kwargs):
        super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                         loads=None, *args, **kwargs)

    class UpdaterSurfaces(_UpdaterSurfaces):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(
                params=params,
                max_step_iter=100)

            shape_derivative = self.objectivefuncs.ShapeDerivativeDisplacement()
            self.add_objective_function(shape_derivative)
            self.add_constraints(
                self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
            self.add_constraints(
                self.objectivefuncs.Distance(min_distance=
                                                            [[2.5, 2.5, 2.5, 2.5, 2.5],
                                                             [2.5, 2.5, 2.5, 2.5, 2.5],
                                                             [2.5, 2.5, 2.5, 2.5, 2.5],
                                                             [2.5, 2.5, 2.5, 2.5, 2.5],
                                                             [2.5, 2.5, 2.5, 2.5, 2.5]]))
            self.add_constraints(
                self.objectivefuncs.boundarys.Cylinder(radius=22.5, height=70., bottom=0.))
            self.add_constraints(
                self.objectivefuncs.boundarys.MinRadius(radius=2.9))


class Controller(_Controller):
    def save(self):
        super().save()
        import shutil
        try:
            shutil.copyfile(GLOBAL.PATH.path_Result + '/Cache/TopOptRun.inp',
                            GLOBAL.PATH.path_Result + '/Log/Deformation/Data/TopOptRun_%d.inp' % (GLOBAL.History.iteration-1))
        except:
            pass
    
if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cpu')

    path_result = 'Z:/Results'
    opt_label = 'FRONT'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()

    solver = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, solver=solver, updater=updater)
    controller.opt_loop()
