import os
import sys
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import *


class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self):
        loss1 = -self.U[0][-2]
        return loss1
GLOBAL.obj_fun = ObjectiveFunction()

class Params(_Params):
    class SurfaceParams(_SurfacesParams):

        def __init__(self):

            super().__init__(max_step_length=[0.4, 0.4])

            self.add_surface(
                self.BSP.initialize_cylinder(r0=8.,
                                                        length=80.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        flip=False, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
                self.BSP.initialize_cylinder(r0=4.,
                                                    length=74.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[0, 0, 3],
                                                    flip=True, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=12.))


    class LoadParams(_LoadsParams):

        def __init__(self):
            super().__init__()

            self.add_load_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'),
                                    name='pressure_1')
    
            self.set_step_num(1)

            self.set_step_params(0, "pressure_1", [0.06])
            

    class MaterialParams(_Materials):
        
        def __init__(self):
            super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
    
    def __init__(self):
        super().__init__(surfaces=self.SurfaceParams(), loads=self.LoadParams(), materials=self.MaterialParams())

class Generator(_Generator):
    def __init__(self, surfaces: Params.SurfaceParams, path_output: str = None, path_queue: str = None) -> None:
        """
        Initialize the Genetrator class.
        
        Parameters:
            surfaces (Surfaces): The surfaces of the soft robot.
            path_output (str): The path to the output directory.
            path_queue (str): The path to the queue directory.
        """
        super().__init__(seed_size=1.5, surfaces=surfaces, path_output=path_output, path_queue=path_queue)

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
                self.objectivefuncs.Fairness(surfaces=params.surfaces, sensitivity=shape_derivative))
            self.add_objective_function(
                self.objectivefuncs.Distance(min_distance=
                                                            [[2.5, 2.5],
                                                             [2.5, 2.5]]))
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
    
    generator = Generator(surfaces=params.surfaces,path_output=GLOBAL.PATH.path_Result + '/Cache/', path_queue=GLOBAL.PATH.path_Queue)

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, generator=generator, solver=solvers, updater=updater)
    controller.opt_loop()
