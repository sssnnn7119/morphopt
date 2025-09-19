import os
import sys
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

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



U_dim=[-6, -4]

class Params(_Params):
    class SurfaceParams(Surfaces):

        def __init__(self):

            super().__init__(max_step_length=[0.1, 0.1])

            self.add_surface(
                Surfaces.BSP.initialize_cylinder(r0=8.,
                                                        length=80,
                                                        seed_size=1.,
                                                        symmetric=[1, [1]],
                                                        flip=False, maxR=0.2, maxC=2., maxFF=0.4))
            self.add_surface(
                Surfaces.BSP.initialize_cylinder(
                    r0=4.,
                    length=74.,
                    seed_size=1.,
                    symmetric=[1, [1]],
                    flip=True,
                    init_location=[0., 0., 3.], maxR=0.2, maxC=2., maxFF=0.4))

            
        def initialize(self, iteration):
            super().initialize(iteration)
            

    class LoadParams(Loads):
        class _Pressure(Loads.Pressures):
            def __init__(self) -> None:
                super().__init__()
                self.pressure = torch.Tensor([[0.05], [0.09]])
        
        def __init__(self) -> None:
            self.pressure = self._Pressure()
            
    class MaterialParams(Materials):
        
        def __init__(self):
            super().__init__(mu=0.482, kappa=48., density=1.08e-9,)
    
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

class Solver(solvers.morph):
    """
    Solver class for MorphOpt.
    This class is responsible for solving the finite element analysis (FEA) problem.
    """

    def __init__(self, params: Params):

        super().__init__(params=params, U_dim=U_dim,
                         num_process=1)

class Updater(Updaters):
    """
    Updater class for MorphOpt.
    This class is responsible for updating the design variables based on the results of the optimization process.
    """

    def __init__(self, params: Params, *args, **kwargs):
        super().__init__(U_dim=U_dim,
                         surfaces=self.UpdaterSurfaces(params=params),
                         loads=None, *args, **kwargs)
    extra_target = False
    @staticmethod
    def objective_function(U: torch.Tensor, Udp: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        

        target = (U[0, 1] + 10)**2 + (U[0, 0] - 30)**2

        if target < 20 or Updater.extra_target:
            Updater.extra_target = True
            target += (U[1, 1] - 10)**2
        return target

    class UpdaterSurfaces(update_surfaces.UpdaterSurfaces):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(
                params=params,
                max_step_iter=100)

            self.add_objective_function(update_surfaces.objectivefuncs.ShapeDerivativeContinuation())
            self.add_objective_function(
                update_surfaces.objectivefuncs.Fairness(surfaces=params.surfaces))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Distance(min_distance=np.ones([params.surfaces.num_surface, params.surfaces.num_surface]) * 2.5))
            self.add_objective_function(
                update_surfaces.objectivefuncs.boundarys.Cylinder(radius=12., height=80., bottom=0.))
            
        
        def initialize(self, iter_now: int, sensitivity: list[torch.Tensor], *args,
                    **kwargs) -> None:
            """
            Initialize the parameters of the optimization process.

            Parameters:
                iter_now (int): The current iteration number.
            """

            # reset the scaler
            if iter_now % 1 == 0 or self.scaler is None:
                # get the maximum sensitivity value
                max_sensitivity = 0
                for sensitivity_surf in sensitivity:
                    max_sensitivity = max(max_sensitivity,
                                        sensitivity_surf.abs().max())
                self.scaler = 10 / max_sensitivity
            sensitivity = [
                sensitivity_surf * self.scaler for sensitivity_surf in sensitivity
            ]

            super().initialize(iter_now=iter_now, sensitivity=sensitivity, *args, **kwargs)
    
if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')

    path_result = 'Z:/Results'
    opt_label = 'youqingPath'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()
    
    generator = Generator(surfaces=params.surfaces,path_output=GLOBAL.PATH.path_Result + '/Cache/', path_queue=GLOBAL.PATH.path_Queue)

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = _Controller(params=params, generator=generator, solver=solvers, updater=updater)
    controller.opt_loop()
