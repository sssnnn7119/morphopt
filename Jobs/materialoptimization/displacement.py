import os
import re
import sys


os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
sys.path.append(os.getcwd())


import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import GLOBAL
from MorphOpt.opt_loop import Controller
from MorphOpt.modelparams import Surfaces_offset, Loads, BsplineMaterials
from MorphOpt import initializer
from MorphOpt import solvers
from MorphOpt.updaters.surface import update_surfaces_Shell
from MorphOpt.updaters.material import update_materials
from MorphOpt.updaters.updaters import Updaters
from MorphOpt import generatemodel
from MorphOpt.modelparams import Params as _Params

U_dim = [-6,-5,-4,-3,-2,-1]
 
class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self, U, Udp, UdF, *args, **kwargs):
        return -U[0, 5]+ (UdF**2).sum() / 10
GLOBAL.OBJFUN = ObjectiveFunction()


class Params(_Params):

    class SurfaceParams(Surfaces_offset):

        def __init__(self):

            super().__init__(thickness=1.5, max_step_length=[0.4, 0.4], reinitialize_per_iter=5)

            self.add_surface(
                Surfaces_offset.BSP.initialize_cylinder(r0=20.,
                                                 length=40.,
                                                 seed_size=2.,
                                                 symmetric=[0],
                                                 flip=False,
                                                 maxR=0.2,
                                                 maxC=2.5,
                                                 maxFF=0.2))
            # self.add_surface(
            #     Surfaces_offset.BSP.initialize_cylinder(r0=4.,
            #                                      length=14.,
            #                                      seed_size=1.,
            #                                      symmetric=[0],
            #                                      flip=True,
            #                                      init_location=[0., 0., 3.],
            #                                      maxR=0.2,
            #                                      maxC=2.,
            #                                      maxFF=0.2))

            # self.add_surface(Surfaces_offset.CPGEO.initialize_Cylinder(seed_size=1.,
            #                                                     flip=True,
            #                                                     r0=4,
            #                                                     length=14,
            #                                                     init_location=[0,0,10],
            #                                                     symmetric=[0],
            #                                                     MaxC=1.))

            # self.add_surface(
            #     Surfaces_offset.CPGEO.initialize_Cylinder(
            #         seed_size=1.2,
            #         flip=True,
            #         r0=10,
            #         length=74,
            #         init_location=[0, 0, 40],
            #         MaxC=2.5
            #     ))

            self.add_surface(
                Surfaces_offset.CPGEO.initialize_Sphere(
                    seed_size=1.0,
                    flip=True,
                    r0=10,
                    init_location=[0, 0, 20],
                    MaxC=1.5
                ))

            
        def initialize(self, iteration):
            super().initialize(iteration)
            self.if_update[0] = False
            
    class LoadParams(Loads):

        class _Pressure(Loads.Pressures):

            def __init__(self):
                super().__init__()
                self.pressure = torch.Tensor([[0.06]])

        def __init__(self):
            self.pressure = self._Pressure()

    class MaterialParams(BsplineMaterials):

        def __init__(self):
            super().__init__(mu=1.22,
                             kappa=12.20,
                             min_ratio=1e-6,
                             density=1.08e-9,
                             boundary=[[-25, 25], [-25, 25], [-5, 45]],
                             seed_size=1.0, 
                             max_step_length=0.05,
                             init_density=0.5)

    def __init__(self):
        super().__init__(surfaces=self.SurfaceParams(),
                         loads=self.LoadParams(),
                         materials=self.MaterialParams())
        self.surfaces: Surfaces_offset = self.surfaces

    def save_figure(self, filepath: str) -> None:
        """
        Save the figures of the parameters to a file.
        
        Args:
            filepath (str): The path to save the figures.
        """
        super().save_figure(filepath=filepath)

        # plot the morphology
        from mayavi import mlab

        fig = mlab.figure(bgcolor=(1, 1, 1), size=(800, 800))
        fig.scene.parallel_projection = True

        self.materials.plot()
        for sf in range(1, self.surfaces.num_surface):
            if sf == 0:
                alpha = 0.6
            else:
                alpha = 1
            self.surfaces.surface_list[sf].plot(alpha=alpha, color=(40.0 / 255, 120.0 / 255, 181.0 / 255))
        
        self.materials.plot()



        # 添加轮廓和坐标轴
        mlab.outline()
        axes = mlab.axes(xlabel='X', ylabel='Y', zlabel='Z')
        axes.label_text_property.color = (0, 0, 0)  # Set text color to black
        axes.axes.property.color = (0, 0, 0)       # Set axes lines color to black

        # colorbar
        colorbar = mlab.colorbar(orientation='vertical', title='Density', label_fmt='%.2f',
                  nb_labels=5)
        # Make colorbar text color black
        colorbar.label_text_property.color = (0, 0, 0)
        colorbar.title_text_property.color = (0, 0, 0)

        if not os.path.exists(filepath + 'Morph'):
            initializer.initialize_path_log('Morph')

        mlab.view(azimuth=210, elevation=70, distance=300)
        mlab.savefig(filepath + '/Morph/' + '%d.jpg'%GLOBAL.History.iteration)
        mlab.close()

class Generator(generatemodel.Genetrator):

    def __init__(self,
                 surfaces: Surfaces_offset,
                 path_output: str = None,
                 path_queue: str = None) -> None:
        """
        Initialize the Genetrator class.
        
        Parameters:
            surfaces (Surfaces): The surfaces of the soft robot.
            path_output (str): The path to the output directory.
            path_queue (str): The path to the queue directory.
        """
        super().__init__(seed_size=1.2,
                         surfaces=surfaces,
                         path_output=path_output,
                         path_queue=path_queue)


class Solver(solvers.MorphMaterialShell):
    """
    Solver class for MorphOpt.
    This class is responsible for solving the finite element analysis (FEA) problem.
    """

    def __init__(self, params: Params):

        super().__init__(
            params=params,
            U_dim=U_dim,
            num_process=1,
            shell_mu=0.48,
            shell_kappa=4.8,
            shell_density=1.08e-9,
        )

class Updater(Updaters):
    """
    Updater class for MorphOpt.
    This class is responsible for updating the design variables based on the results of the optimization process.
    """

    def __init__(self, params: Params, *args, **kwargs):
        super().__init__(U_dim=U_dim,
                         surfaces=self.UpdaterSurfaces(params=params),
                         loads=None,
                         materials=self.UpdaterMaterials(params=params),
                         *args,
                         **kwargs)
        # self.if_update_surface = False
        # self.if_update_material = False



    class UpdaterMaterials(update_materials.UpdaterMaterials):
        """
        Updater class for MorphOpt materials.
        This class is responsible for updating the material properties based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(params=params, max_step_iter=50)
            self.add_objective_function(
                update_materials.objectivefuncs.Sensitivity(
                    materials=params.materials))
            self.add_objective_function(
                update_materials.objectivefuncs.VolumePanelty(
                    materials=params.materials, factor=1e-16))
            

    class UpdaterSurfaces(update_surfaces_Shell.UpdaterSurface_Shell):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(params=params, max_step_iter=100, reset_per_iter=3)

            self.add_objective_function(
                update_surfaces_Shell.objectivefuncs.Sensitivity())
            self.add_objective_function(
                update_surfaces_Shell.objectivefuncs.Fairness(
                    surfaces=params.surfaces))
            self.add_objective_function(
                update_surfaces_Shell.objectivefuncs.ShellOffsetCurvature(
                    shell_thickness=params.surfaces.thickness, surf_index=[1]))
            self.add_objective_function(
                update_surfaces_Shell.objectivefuncs.DistanceShell(min_distance=
                                                            [[0., 5., 5.],
                                                             [5., 2., 2.],
                                                             [5., 2., 2.]], shell_thickness=params.surfaces.thickness))
            self.add_objective_function(
                update_surfaces_Shell.objectivefuncs.Boundary.Cylinder(radius=100.,
                                                               height=37.,
                                                               bottom=3.))


if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')

    path_result = 'Z:/Results'
    opt_label = 'MaterialShell'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()

    generator = Generator(surfaces=params.surfaces,
                          path_output=GLOBAL.PATH.path_Result + '/Cache/',
                          path_queue=GLOBAL.PATH.path_Queue)

    solvers = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params,
                            generator=generator,
                            solver=solvers,
                            updater=updater)
    # params.materials.plot()
    controller.opt_loop()
