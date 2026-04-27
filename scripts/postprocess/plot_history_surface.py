
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

        self.colors = [(40.0 / 255, 120.0 / 255, 181.0 / 255)] * self.params.geometry.num_surface
        self.opacity = [1.0] * self.params.geometry.num_surface
        self.opacity[0] = 0.6
        self.boundary: tuple[float, float, float, float, float, float] = None


    def load_parameters(self, iteration: int):
        """
        Load the parameters at a given iteration.
        """
        self.params.geometry.load(foldpath=self.restart_path + '/log/', iteration=iteration)
        self.params.geometry.initialize()

    def plot_surfaces(self, iteration: int, 
                      colors: list[tuple[float, float, float]] | tuple[float, float, float] = None, 
                      opacity: list[float] = None,
                      boundary: tuple[float, float, float, float, float, float] = None,
                      plotter: pv.Plotter = None) -> pv.Plotter:
        """
        Plot the surfaces at a given iteration.
        """

        if colors is None:
            colors = self.colors
        if opacity is None:
            opacity = self.opacity
        if boundary is None:
            boundary = self.boundary

        self.load_parameters(iteration=iteration)
        
        if plotter is None:
            plotter = pv.Plotter()

        for sf in range(self.params.geometry.num_surface):
            if sf == 0:
                alpha = 0.6
            else:
                alpha = 1.0
            if opacity is not None:
                alpha = opacity[sf]
            
            color_to_use = (40.0 / 255, 120.0 / 255, 181.0 / 255)
            if colors is not None and isinstance(colors, list):
                color_to_use = colors[sf]
            elif colors is not None and isinstance(colors, tuple):
                color_to_use = colors
            
            mesh = self.params.geometry.surface_list[sf].get_mesh()
            plotter.add_mesh(mesh, opacity=alpha, color=color_to_use,
                           diffuse=0.8, specular=0.1, ambient=0.4, specular_power=5,
                           smooth_shading=True, show_edges=False)
        
        if boundary is not None:
            pass

        return plotter

    def plot_surface_rotation(self, iteration: int, 
                              colors: tuple[float, float, float] = None, 
                              opacity: list[float] = None,
                              boundary: tuple[float, float, float, float, float, float] = None,
                              n_frames: int = 36,
                              total_time: int = 4000,
                              view: tuple[float, float] = (45, 70),
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
        plotter.camera_position = 'iso'
        
        for i in range(n_frames):
            plotter.write_frame()
            plotter.camera.azimuth += 360 / n_frames
            
        plotter.close()

    def plot_history_surface(self, surface_index: int, history_index: int = 0,
                             colors: tuple[float, float, float] = None,
                             opacity: float = 0.6,
                             boundary: tuple[float, float, float, float, float, float] = None,
                             total_time: int = 4000,
                             output_gif: str = 'history_surface.gif', 
                             output_jpg_foldpath: str = None):
        """
        Plot the history of a surface over iterations and save as a gif.

        Args:
            surface_index (int): The index of the surface to plot.
            history_index (int): The total history index to plot.
            colors (tuple): The RGB color for the surface.
            opacity (float): The opacity for the surface.
            boundary (tuple): The boundary points to plot. Should be in the form (x_min, x_max, y_min, y_max, z_min, z_max).
            total_time (int): The total time for the gif in milliseconds.
            output_gif (str): The output gif file name.
            output_jpg_foldpath (str): The folder path to save individual jpg frames. If None, frames are not saved.

        """
        if colors is None:
            colors = self.colors[surface_index]
        if boundary is None:
            boundary = self.boundary

        plotter = pv.Plotter(off_screen=True, window_size=[2500, 2500])
        plotter.set_background('white')

        plotter.enable_parallel_projection()
        azimuth = 210
        elevation = 20
        plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(elevation))))
        plotter.remove_all_lights()
        plotter.add_light(pv.Light(light_type='headlight', intensity=1.0))  # Mayavi 默认: 跟随相机的头灯
        
        plotter.open_gif(output_gif)

        for iteration in range(history_index + 1):
            self.load_parameters(iteration=iteration)
            plotter.clear()
            
            mesh = self.params.geometry.surface_list[surface_index].get_mesh()
            plotter.add_mesh(mesh, opacity=opacity, color=colors,
                           diffuse=0.8, specular=0.1, ambient=0.4, specular_power=5,
                           smooth_shading=True, show_edges=False)
            
            if boundary is not None:
                pass

            
            plotter.write_frame()
            
            if output_jpg_foldpath is not None:
                plotter.screenshot(f"{output_jpg_foldpath}/iter_{iteration}.jpg")
                
        plotter.close()

    def plot_history_all_surfaces(self, history_index: int = 0,
                                  colors: list[tuple[float, float, float]] = None,
                                  opacity: list[float] = None,
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

        if colors is None:
            colors = self.colors
        if opacity is None:
            opacity = self.opacity
        if boundary is None:
            boundary = self.boundary

        plotter = pv.Plotter(off_screen=True, window_size=[2500, 2500])
        plotter.set_background('white')
        

        plotter.open_gif(output_gif)

        num_frames = 60
        for titer in range(num_frames):
            iteration = 1 + int(history_index * titer / num_frames)
            plotter.clear()
            plotter.remove_all_lights()
            plotter.add_light(pv.Light(light_type='headlight', intensity=1.0))  # Mayavi 默认: 跟随相机的头灯
            self.plot_surfaces(iteration=iteration, colors=colors, opacity=opacity, boundary=boundary, plotter=plotter)

            if titer == 0:
                plotter.enable_parallel_projection()
                azimuth = 90
                elevation = 0
                plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                    math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                    math.sin(math.radians(elevation))))
            
            plotter.write_frame()
            
            if output_jpg_foldpath is not None:
                plotter.screenshot(f"{output_jpg_foldpath}/iter_{titer}.jpg")
                
        plotter.close()

if __name__ == "__main__":
    plotter = SurfacesFigurePlotter(restart_path='A:/MineData/Learning/Publications/TMECH2025Contact/results/Optimization/grasp/result/GRASP_T20260302_163335/')
    # plotter.plot_history_all_surfaces(history_index=294,
    #                                  output_gif='Z:/temp/example_displacement_history.gif',
    #                                  output_jpg_foldpath='Z:/temp/')

    plotter.plot_surface_rotation(iteration=294, output_gif='Z:/temp/example_surface_rotation.gif')

    # pt = pv.Plotter(off_screen=True, window_size=[2500, 2500])
    # pt.set_background('white')
    # plotter.plot_surfaces(iteration=294, plotter=pt)

    # pt.enable_parallel_projection()
    # azimuth = 90
    # elevation = 0
    # pt.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
    #     math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
    #     math.sin(math.radians(elevation))))
    
    # pt.remove_all_lights()
    # pt.add_light(pv.Light(light_type='headlight', intensity=0.8))  # Mayavi 默认: 跟随相机的头灯
    
    # pt.screenshot('Z:/temp/294.png')