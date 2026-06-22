
from calendar import c
import math
import pyvista as pv
import torch
import morphopt

class SurfacesFigurePlotter:

    def __init__(self, restart_path: str):
        import importlib.util
        torch.set_default_dtype(torch.float64)
        torch.set_default_device('cpu')
        spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", restart_path + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
        MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)
        
        params: morphopt.Params = MAIN_SCRIPT_FOR_RESTART.ThisController.Params()

        self.params = params
        self.restart_path = restart_path

        self.boundary: tuple[float, float, float, float, float, float] = None


    def load_parameters(self, iteration: int):
        """
        Load the parameters at a given iteration.
        """
        self.params.load(foldpath=self.restart_path + '/log/', iteration=iteration)
        self.params.initialize()

    def plot_surfaces(self, iteration: int, 
                      plotter: pv.Plotter = None) -> pv.Plotter:
        """
        Plot the surfaces at a given iteration.
        """

        self.load_parameters(iteration=iteration)
        
        if plotter is None:
            plotter = pv.Plotter()

        self.params.plot(plotter=plotter)

        return plotter

    def plot_surface_rotation(self, iteration: int, 
                              colors: tuple[float, float, float] = None, 
                              opacity: list[float] = None,
                              boundary: tuple[float, float, float, float, float, float] = None,
                              n_frames: int = 36,
                              total_time: int = 4000,
                              view: tuple[float, float] = (45, 80),
                              output_gif: str = 'surface_rotation.gif'):
        """
        Plot the surfaces at a given iteration with rotation and save as a gif.

        Args:
            iteration (int): The iteration number to plot.
            colors (tuple): The RGB color for the surfaces.
            opacity (list): The opacity for each surface.
            boundary (tuple): The boundary points to plot. Should be in the form (x_min, x_max, y_min, y_max, z_min, z_max).
            n_frames (int): The number of frames in the rotation.
            delay (int): The delay between frames in milliseconds.
            view (tuple): The (azimuth, elevation) angles for the view.
            output_gif (str): The output gif file name.
        """

        plotter = pv.Plotter(off_screen=True, window_size=[2500, 2500])
        plotter.set_background('white')
        plotter.remove_all_lights()
        plotter.add_light(pv.Light(light_type='headlight', intensity=1.0))  # Mayavi 默认: 跟随相机的头灯


        self.plot_surfaces(iteration=iteration, colors=colors, opacity=opacity, boundary=boundary, plotter=plotter)

        plotter.enable_parallel_projection()
        azimuth = 210
        elevation = 20
        plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(elevation))))

        plotter.open_gif(output_gif)
        # plotter.camera_position = 'iso'
        
        for i in range(n_frames):
            plotter.write_frame()
            plotter.camera.azimuth += 360 / n_frames
            
        plotter.close()

    def plot_history_all_surfaces(self, history_index: int = 0,
                                  boundary: tuple[float, float, float, float, float, float] = None,
                                  total_time: int = 4000,
                                  output_gif: str = 'history_all_surfaces.gif', 
                                  output_jpg_foldpath: str = None):
        """
        Plot the history of all surfaces over iterations and save as a gif.

        Args:
            history_index (int): The total history index to plot.
            colors (list): The list of RGB colors for each surface.
            opacity (list): The list of opacities for each surface.
            boundary (tuple): The boundary points to plot. Should be in the form (x_min, x_max, y_min, y_max, z_min, z_max).
            total_time (int): The total time for the gif in milliseconds.
            output_gif (str): The output gif file name.
            output_jpg_foldpath (str): The folder path to save individual jpg frames. If None, frames are not saved.
        """

        if boundary is None:
            boundary = self.boundary

        plotter = pv.Plotter(off_screen=True, window_size=[2500, 2500])
        plotter.set_background('white')
        

        plotter.open_gif(output_jpg_foldpath + '/' + output_gif)

        self.plot_surfaces(iteration=history_index, plotter=plotter)
        plotter.enable_parallel_projection()
        azimuth = 90
        elevation = 0
        plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(elevation))))

        for titer in range(history_index):
            print(f"Plotting iteration {titer + 1}/{history_index}...")
            iteration = titer + 1
            plotter.clear()
            plotter.remove_all_lights()
            plotter.add_light(pv.Light(light_type='headlight', intensity=1.0))
            self.plot_surfaces(iteration=iteration, plotter=plotter)

            plotter.write_frame()
            
            if output_jpg_foldpath is not None:
                plotter.screenshot(f"{output_jpg_foldpath}/iter_{iteration}.jpg")
                
        plotter.close()

if __name__ == "__main__":
    plotobject = SurfacesFigurePlotter(restart_path='/run/media/song/SS/MineData/Learning/Publications/RAL2026FEA/results/gripper/BeamMinEnergy_T20260615_132949')

    plotobject.plot_history_all_surfaces(history_index=113,
                                         output_gif='history_all_surfaces.gif', 
                                         output_jpg_foldpath='/run/media/song/缓存/cache/')
    # plotter = plotobject.plot_surfaces(iteration=30)
    # plotter.enable_parallel_projection()
    # azimuth = 210
    # elevation = 20
    # plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
    #     math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
    #     math.sin(math.radians(elevation))))
    
    # plotter.show()