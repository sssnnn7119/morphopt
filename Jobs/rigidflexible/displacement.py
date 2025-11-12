import os
import sys
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

from tkinter.tix import Tree
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import *


class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self):

        rp_head_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index

        GC_start = self.fe.assembly._GC_list_indexStart[rp_head_index]

        loss1 = 0*torch.clamp(1.2-self.U[0][GC_start + 4], min=0)**3
        loss11 = self.U[5][GC_start + 4]
        loss2 = self.U[1][GC_start + 3]
        loss3 = -self.U[2][GC_start + 3]
        loss4 = self.U[3][GC_start + 5]
        loss5 = -self.U[4][GC_start + 5]
        return loss1 + loss2 + loss3 + loss4 + loss5 + loss11
GLOBAL.obj_fun = ObjectiveFunction()

class Params(_Params):
    class SurfaceParams(_GeometryParams):

        def __init__(self):

            super().__init__(max_step_length=[0.4, 0.4, 0.4, 0.4], reinitialize_per_iter=3, fea_seed_size=1.5, fea_mesh_order=1)

            self.add_surface(
                self.BSP.initialize_cylinder(r0=10.,
                                                        length=80.,
                                                        seed_size=0.8,
                                                        symmetric=[0, [1]],
                                                        flip=False, maxR=0.1, maxC=2.0, maxFF=0.2, perturbation_L=12.))
            
            # self.add_surface(
            #     self.CPGEO.initialize_Sphere(seed_size=0.8,
            #                                  flip=True,
            #                                  r0=5.,
            #                                  init_location=[0,0,40.],
            #                                  MaxC=0.8))
            
            self.add_surface(
                self.CPGEO.initialize_Sphere(seed_size=0.8,
                                             flip=True,
                                             r0=5.,
                                             init_location=[0,0,20.],
                                             MaxC=0.8))
            
            self.add_surface(
                self.CPGEO.initialize_Sphere(seed_size=0.8,
                                             flip=True,
                                             r0=5.,
                                             init_location=[0,0,60.],
                                             MaxC=0.8))
            
            self.if_update = [False, True, True]


    class FEAParams(_FEAParams):

        def __init__(self):
            super().__init__()

        def define_interface(self):
            # Common BC / RP / Couple
            self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
            self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
            self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

            self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 20.]), name='RP_Rigid2')
            self.add_fea_interface(self.CoupleInterface(rp_name='RP_Rigid2', instance_name='final_model', set_nodes_name='surface_1_All'))

            self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 60.]), name='RP_Rigid3')
            self.add_fea_interface(self.CoupleInterface(rp_name='RP_Rigid3', instance_name='final_model', set_nodes_name='surface_2_All'))

            # self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'),
            #                         name='pressure_1')
            self.add_fea_interface(self.ConcentratedMomentInterface(rp_name='RP_head'),
                                    name='moment_1')

        def define_steps(self):
            self.set_step_num(6)
            # self.set_step_params(0, "pressure_1", [0.0])
            self.set_step_params(0, "moment_1", [0.0, 0.0, 0.0])

            # self.set_step_params(1, "pressure_1", [0.0])
            self.set_step_params(1, "moment_1", [40., 0.0, 0.0])
            
            # self.set_step_params(2, "pressure_1", [0.0])
            self.set_step_params(2, "moment_1", [-40., 0.0, 0.0])

            # self.set_step_params(3, "pressure_1", [0.0])
            self.set_step_params(3, "moment_1", [0.0, 0.0, 40.])
            
            # self.set_step_params(4, "pressure_1", [0.0])
            self.set_step_params(4, "moment_1", [0.0, 0.0, -40.])

            # self.set_step_params(5, "pressure_1", [0.0])
            self.set_step_params(5, "moment_1", [0.0, -40.0, 0.0])

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

            shape_derivative = self.objectivefuncs.ShapeDerivativeDirect(reset_per_iter=5)
            self.add_objective_function(shape_derivative)
            self.add_objective_function(
                self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
            self.add_objective_function(
                self.objectivefuncs.Distance(min_distance=
                                                            [[2.5, 2.5, 1.5, 1.5],
                                                             [2.5, 2.5, 1.5, 1.5],
                                                             [1.5, 1.5, 1.5, 1.5],
                                                             [1.5, 1.5, 1.5, 1.5]]))
            self.add_objective_function(
                self.objectivefuncs.boundarys.Cylinder(radius=12., height=80., bottom=0.))
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
    opt_label = 'EXAMPLE'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, solver=solvers, updater=updater)
    controller.opt_loop()
