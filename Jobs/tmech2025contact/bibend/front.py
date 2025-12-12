import os
import sys

import FEA
import numpy as np
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import *

class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self, *args, **kwargs):
        rp_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index
        loss = -self.U[0][self.fe.assembly._GC_list_indexStart[rp_index] + 4]
        return loss
GLOBAL.obj_fun = ObjectiveFunction()

class Params(_Params):
    class SurfaceParams(_GeometryParams):

        def __init__(self):

            super().__init__(max_step_length=[0.4, 0.4, 0.4, 0.4], fea_seed_size=1.2, fea_mesh_order=1)

            self.add_surface(
                self.BSP.initialize_cylinder(r0=21.,
                                                        length=50.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        flip=False, maxR=0.1, maxC=1.2, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
            self.BSP.initialize_cylinder(r0=6.,
                                                    length=44.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[-11, 0, 3],
                                                    flip=True, maxR=0.1, maxC=1.2, maxFF=0.2, perturbation_L=12.))
        
            self.add_surface(
            self.BSP.initialize_cylinder(r0=6.,
                                                    length=44.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[11, 0, 3],
                                                    flip=True, maxR=0.1, maxC=1.2, maxFF=0.2, perturbation_L=12.))
            
            
            self.if_update = [True, True, True]


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


        def apply_surface_constraints(self):
            control_points_ = self.surface_list[1].model.control_points.clone()

            control_points_[0] *= -1
            control_points_[1] *= -1

            self.surface_list[2].model.control_points = control_points_

            self.surface_list[0].model.control_points = self._symmetry(self.surface_list[0].model.control_points)

        def get_geometry_values(self):
            r0, r0du, r0du2 = self.surface_list[0].get_geometry_values()

            r1, r1du, r1du2 = self.surface_list[1].get_geometry_values()

            
            r2 = r1.clone()
            r2[0] *= -1
            r2[1] *= -1

            r2du = r1du.clone()
            r2du[0] *= -1
            r2du[1] *= -1

            r2du2 = r1du2.clone()
            r2du2[0] *= -1
            r2du2[1] *= -1

            r = [r0, r1, r2,]
            rdu = [r0du, r1du, r2du,]
            rdu2 = [r0du2, r1du2, r2du2,]

            return r, rdu, rdu2

            
    class FEAParams(_FEAParams):
        def __init__(self):
            super().__init__()

        def define_interface(self):
            # Common BC / RP / Couple
            self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
            self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 50.]), name='RP_head')
            self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))
            # Define interfaces
            self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'), name='P_s1')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_0_All'), name='CS_s0')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_1_All'), name='CS_s1')
            self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_2_All'), name='CS_s2')

        def define_steps(self):
            # One step amplitudes
            self.set_step_num(1)
            self.set_step_params(0, 'P_s1', [0.06])
            
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
                                                            [[2.5, 2.5, 2.5, 2.5],
                                                             [2.5, 2.5, 2.5, 2.5],
                                                             [2.5, 2.5, 2.5, 2.5],
                                                             [2.5, 2.5, 2.5, 2.5]]))
            self.add_constraints(
                self.objectivefuncs.boundarys.Cylinder(radius=22., height=50., bottom=0.))

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
    torch.set_default_device('cuda')

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
