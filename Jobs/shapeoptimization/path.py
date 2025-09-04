import os
import sys
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import numpy as np
import torch
from MorphOpt import GLOBAL
from MorphOpt.opt_loop import Controller
from MorphOpt.modelparams import Surfaces, Loads, Materials
from MorphOpt import initializer
from MorphOpt import solvers
from MorphOpt.updaters.surface import update_surfaces
from MorphOpt.updaters.load import update_loads
from MorphOpt.updaters.updaters import Updaters
from MorphOpt import generatemodel
from MorphOpt.modelparams import Params as _Params
from Bspline import BSP_Curve



U_dim = [-6,-5,-4]

sample_point = torch.tensor([0.0397101435024637, 0.1834346424956498, 
                             0.2033335225863733, 0.4744675900836710, 
                             0.5255324099163290, 0.7966664774136267, 
                             0.8165653575043502, 0.9602898564975363])
sample_weight = torch.tensor([0.05061426814518815, 0.11119051722668725, 
                               0.15685332293894365, 0.181341891689181, 
                               0.181341891689181, 0.15685332293894365, 
                               0.11119051722668725, 0.05061426814518815])

# sample_point = torch.tensor([0.03])
# sample_weight = torch.tensor([1.])

class Params(_Params):
    
    class SurfaceParams(Surfaces):

        def __init__(self):

            super().__init__(max_step_length=[0.2, 0.2, 0.2, 0.2])

            self.add_surface(
                Surfaces.BSP.initialize_cylinder(r0=15.,
                                                        length=120.,
                                                        seed_size=1.,
                                                        symmetric=[0],
                                                        flip=False, maxR=0.2, maxC=2., maxFF=0.2))
            # self.add_surface(
            #     Surfaces.CS.initialize_Sphere(seed_size=1.5, flip=True, r0=4., init_location=[8,0,60]))

            # self.add_surface(
            #     Surfaces.CS.initialize_Sphere(seed_size=1.5, flip=True, r0=4., init_location=[-4,7,60]))
            
            # self.add_surface(
            #     Surfaces.CS.initialize_Sphere(seed_size=1.5, flip=True, r0=4., init_location=[-4,-7,60]))
            
            self.add_surface(
                Surfaces.CPGEO.initialize_Cylinder(seed_size=1.5, flip=True, r0=4., length=110., init_location=[8,0,60], symmetric=[0]))
            
            self.add_surface(
                Surfaces.CPGEO.initialize_Cylinder(seed_size=1.5, flip=True, r0=4., length=110., init_location=[-4,7,60], symmetric=[0]))
            
            self.add_surface(
                Surfaces.CPGEO.initialize_Cylinder(seed_size=1.5, flip=True, r0=4., length=110., init_location=[-4,-7,60], symmetric=[0]))

    class LoadParams(Loads):

        class _Pressure(Loads.Pressures):
            def __init__(self):
                super().__init__()

                p0 = torch.linspace(0, 0.06, 10).reshape([1, 10]).repeat([3, 1])
                self._pressure_bsp = BSP_Curve(P0=p0, degree=4,)
                self.max_step_length = 0.002

            def get_pressure(self):
                return self._pressure_bsp.map([sample_point], derivative=[0]).T
            
            def get_pdxi(self):
                return self._pressure_bsp.map([sample_point], derivative=[1]).T
            
            @property
            def num_variables(self) -> int:
                return self._pressure_bsp.control_points.numel()
            
            def get_parameters(self):
                return self._pressure_bsp.control_points.clone()
            
            def set_parameters(self, xlist: torch.Tensor) -> None:
                self._pressure_bsp.control_points = xlist.reshape(self._pressure_bsp.control_points.shape).detach().clone()
                
            def update_variables(self, x_change):
                delta_p = 2/torch.pi * torch.atan(x_change) * self.max_step_length
                self._pressure_bsp.control_points += delta_p.reshape(self._pressure_bsp.control_points.shape)

        def __init__(self):
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
        super().__init__(seed_size=3.5, surfaces=surfaces, path_output=path_output, path_queue=path_queue)

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
                         loads=self.UpdaterLoads(params=params), *args, **kwargs)

        p0 = torch.tensor([[-30,30], [0,0], [5,5]])
        self._target_curve = BSP_Curve(P0=p0, degree=2)
        self._target_U = self._target_curve.map([sample_point]).T
        self._target_Udxi = self._target_curve.map([sample_point], derivative=[1]).T
    

    def objective_function(self, U: torch.Tensor, Udp: torch.Tensor, *args, **kwargs):
        pdxi = self._load.params_update.pressure.get_pdxi()
        Udxi = torch.einsum('tup, tp->tu', Udp, pdxi)
        
        target = ((U-self._target_U)**2 + (Udxi-self._target_Udxi)**2) * Udxi.norm(dim=1, keepdim=True)

        return torch.einsum('tu, t->', target, sample_weight)

    class UpdaterSurfaces(update_surfaces.UpdaterSurfaces):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(
                params=params,
                max_step_iter=200)

            self.add_objective_function(update_surfaces.objectivefuncs.ShapeDerivativePneumatic())
            self.add_objective_function(
                update_surfaces.objectivefuncs.Fairness(surfaces=params.surfaces))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Distance(min_distance=
                                                            [[2.5, 2.5],
                                                             [2.5, 2.5]]))
            self.add_objective_function(
                update_surfaces.objectivefuncs.boundarys.Cylinder(radius=20., height=120., bottom=0.))

        def initialize(self, iter_now, sensitivity, *args, **kwargs):
            if iter_now < 0:
                self.params_update._max_step_length[0] = 0.06
                for i in range(1, len(self.params_update._max_step_length)):
                    self.params_update._max_step_length[i] = 0.8
            else:
                self.params_update._max_step_length[0] = 0.1
                for i in range(1, len(self.params_update._max_step_length)):
                    self.params_update._max_step_length[i] = 0.1

            super().initialize(iter_now=iter_now, sensitivity=sensitivity, *args, **kwargs)

        def _refine_sensitivity(self, iter_now, sensitivity):
            sensitivity = super()._refine_sensitivity(iter_now, sensitivity)
            
            if iter_now % 10 < 0 and iter_now % 500 < 60:
                for ind_surf in range(1, len(sensitivity)):
                    sensitivity[ind_surf] += sensitivity[ind_surf].abs(
                    ).max() * 0.1
            return sensitivity

    class UpdaterLoads(update_loads.UpdaterLoads):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):
            super().__init__(params=params, max_step_iter=50)

            self.add_objective_function(update_loads.objectivefuncs.SensitivityPressure(loads=params.loads))
            
            self.add_objective_function(update_loads.objectivefuncs.BoundaryPressure(loads=params.loads, p_max=0.06, p_min=0.))

if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')
    
    sample_point = sample_point.to('cuda').to(torch.float64)
    sample_weight = sample_weight.to('cuda').to(torch.float64)

    path_result = 'Z:/Results/'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result)
    initializer.initialize_history()

    

    params = Params()

    generator = Generator(surfaces=params.surfaces,path_output=GLOBAL.PATH.path_Result + '/Cache/', path_queue=GLOBAL.PATH.path_Queue)

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, generator=generator, solver=solvers, updater=updater)
    controller.opt_loop()
