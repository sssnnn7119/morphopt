import os
import sys
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

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

            super().__init__(max_step_length=[0.2, 0.2])

            self.add_surface(
                Surfaces.BSP.initialize_cylinder(r0=14.,
                                                        length=70.,
                                                        seed_size=1.,
                                                        symmetric=[0],
                                                        flip=False, maxR=0.2, maxC=1.5, maxFF=0.2))


            self.add_surface(Surfaces.CS.initialize_Cylinder(seed_size=1., 
                                                                flip=True, 
                                                                r0=4, 
                                                                length=64, 
                                                                init_location=[0,6,35],
                                                                symmetric=[1, [1]], 
                                                                MaxC=1.5))

            self.add_surface(Surfaces.CS.initialize_Cylinder(seed_size=1., 
                                                                flip=True, 
                                                                r0=4, 
                                                                length=64, 
                                                                init_location=[0,-6,35],
                                                                symmetric=[1, [1]], 
                                                                MaxC=1.5))
            
        def initialize(self, iteration):
            super().initialize(iteration)
            # self.if_update[0] = False
            

    class LoadParams(Loads):
        class _Pressure(Loads.Pressures):
            def __init__(self):
                super().__init__()
                self.pressure = torch.Tensor([[0.04]])
        
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
        super().__init__(seed_size=1.5, surfaces=surfaces, path_output=path_output, path_queue=path_queue)

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

        

        return 

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
                                                            [[3.0, 3.0],
                                                             [3.0, 3.0]]))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Boundary.Cylinder(radius=15., height=70., bottom=0.))
    
    
if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')

    path_result = 'Z:/Results'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result)
    initializer.initialize_history()

    params = Params()
    
    generator = Generator(surfaces=params.surfaces,path_output=GLOBAL.PATH.path_Result + '/Cache/', path_queue=GLOBAL.PATH.path_Queue)

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, generator=generator, solver=solvers, updater=updater)
    controller.opt_loop()
