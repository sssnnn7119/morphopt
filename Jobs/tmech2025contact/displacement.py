import os
import sys

import FEA
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import *
import multiprocessing as mp

class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self):
        
        device0 = torch.tensor(1).device

        rp_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index
        RGC0 = self.fe.assembly._GC2RGC(self.U[0].to(device0))
        U0 = RGC0[rp_index]

        RGC1 = self.fe.assembly._GC2RGC(self.U[1].to(device0))
        U1 = RGC1[rp_index]

        loss0 = torch.exp((U0[2]+20)/5)/5
        loss1 = U1[5]

        return loss0 + loss1
GLOBAL.obj_fun = ObjectiveFunction()

class Params(_Params):
    class SurfaceParams(_GeometryParams):

        def __init__(self):

            super().__init__(fea_seed_size=1.4, fea_mesh_order=1)

            self.add_surface(
                self.BSP.initialize_cylinder(r0=12.,
                                                        length=50.,
                                                        seed_size=0.8,
                                                        symmetric=[0, [1]],
                                                        flip=False, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=50/4))
            
            self.add_surface(
                self.BSP.initialize_cylinder(r0=8.,
                                                    length=44.,
                                                    seed_size=0.8,
                                                    symmetric=[0, [1]],
                                                    init_location=[0, 0, 3],
                                                    flip=True, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=50/4))

        def _get_all_r(self, rinit: torch.Tensor):
            rout = rinit.clone()

            num_points = rinit.shape[2] / 4
            num_points = int(num_points)
            r0 = rinit[:, :, :num_points]
            r1 = r0.clone()
            r1[0] *= -1
            rout[:, :, num_points:num_points*2] = r1.flip(dims=[2])
            r2 = r0.clone()
            r2[0] *= -1
            r2[1] *= -1
            rout[:, :, num_points*2:num_points*3] = r2
            r3 = r0.clone()
            r3[1] *= -1
            rout[:, :, num_points*3:num_points*4] = r3.flip(dims=[2])

            return rout

        def initialize(self, iteration: int):

            super().initialize(iteration=iteration)

            # rotate the exterior surface
            self.surface_list[0].model.control_points = self._get_all_r(self.surface_list[0].model.control_points)

            # rotate the bottom surface
            self.surface_list[1].model.control_points = self._get_all_r(self.surface_list[1].model.control_points)


        def get_geometry_values(self):
            
            # rotate the exterior surface
            self.surface_list[0].model.control_points = self._get_all_r(self.surface_list[0].model.control_points)

            # rotate the bottom surface
            self.surface_list[1].model.control_points = self._get_all_r(self.surface_list[1].model.control_points)

            return super().get_geometry_values()

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

            x_change_list: list[torch.Tensor] = []
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

                num_points = self.surface_list[surf_ind[i]].model.control_points.shape[2] / 3
                num_points = int(num_points)
                dx = dx.reshape_as(self.surface_list[surf_ind[i]].model.control_points)
                dx = self._get_all_r(dx)

                self.surface_list[surf_ind[i]].update_variables(dx)

        def get_points_weight(self) -> list[torch.Tensor]:
            """
            Get the weights for the points in the optimization process.

            Returns:
                list[torch.Tensor]: The weights for the points in the optimization process.
            """

            w0 = self.surface_list[0].get_points_weight()
            w1 = self.surface_list[1].get_points_weight()
            
            weight = [w0, w1]
            return weight


    class FEAParams(_FEAParams):

        def __init__(self):
            super().__init__()

        def define_interface(self):
            # Common BC / RP / Couple
            self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
            self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 50.]), name='RP_head')
            self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

            self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'),
                                    name='pressure_1')
            self.add_fea_interface(self.ConcentratedMomentInterface(rp_name='RP_head'),
                                   name='moment_1')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_0_All',),
                                    name='contact_0')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_1_All',),
                                    name='contact_1') 
            

        def define_steps(self):
            self.set_step_num(2)

            self.set_step_params(0, "pressure_1", [-0.05])
            self.set_step_params(0, "moment_1", [0.0, 0.0, 0.0])

            self.set_step_params(1, "pressure_1", [-0.05])
            self.set_step_params(1, "moment_1", [0.0, 0.0, 100.0])


    class MaterialParams(_Materials):
        
        def __init__(self):
            super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
    
    def __init__(self):
        super().__init__(surfaces=self.SurfaceParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())


class Solver(_MorphSolver):
    """
    Solver class for MorphOpt.
    This class is responsible for solving the finite element analysis (FEA) problem.
    """

    def __init__(self, params: Params):

        super().__init__(params=params,
                         task_index_list=[[0, 1]],
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
                max_step_iter=50)

            shape_derivative = self.objectivefuncs.ShapeDerivativeDisplacement(reset_per_iter=5)
            self.add_objective_function(shape_derivative)
            self.add_constraints(
                self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
            self.add_constraints(
                self.objectivefuncs.Distance(min_distance=
                                                            [[1.0, 2.5],
                                                             [2.5, 2.0]]))
            self.add_constraints(
                self.objectivefuncs.boundarys.Cylinder(radius=15., height=50., bottom=0.))


class Controller(_Controller):
    def save(self):
        super().save()
        try:
            GLOBAL.obj_fun.inp.write_inp(GLOBAL.PATH.path_Result + '/Log/Deformation/Data/TopOptRun_%d.inp' % (GLOBAL.History.iteration-1))
        except:
            pass

    
if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')

    path_result = 'Z:/Results'
    opt_label = 'JUMP'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, solver=solvers, updater=updater)
    controller.opt_loop()
