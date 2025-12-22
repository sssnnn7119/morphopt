
from calendar import c
from mayavi import mlab
import torch
import MorphOpt

class SurfacesFigurePlotter:

    def __init__(self, restart_path: str):
        import importlib.util
        torch.set_default_dtype(torch.float64)
        torch.set_default_device('cpu')
        spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", restart_path + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
        MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)
        
        params: MorphOpt.Params = MAIN_SCRIPT_FOR_RESTART.ThisController.Params()

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
        self.params.geometry.load(foldpath=self.restart_path + '/log/surfaces/data/', iteration=iteration)

    def plot_surfaces(self, iteration: int, 
                      colors: list[tuple[float, float, float]] | tuple[float, float, float] = None, 
                      opacity: list[float] = None,
                      boundary: tuple[float, float, float, float, float, float] = None):
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

        for sf in range(self.params.geometry.num_surface):
            if sf == 0:
                alpha = 0.6
            else:
                alpha = 1.0
            if opacity is not None:
                alpha = opacity[sf]
            if colors is not None and isinstance(colors, list):
                self.params.geometry.surface_list[sf].plot(alpha=alpha, color=colors[sf])
            elif colors is not None and isinstance(colors, tuple):
                self.params.geometry.surface_list[sf].plot(alpha=alpha, color=colors)
            else:
                self.params.geometry.surface_list[sf].plot(alpha=alpha, color=(40.0 / 255, 120.0 / 255, 181.0 / 255))
        
        if boundary is not None:
            mlab.points3d(boundary[0], boundary[2], boundary[4], scale_factor=0.01, color=(1,0,0), opacity = 0.0)
            mlab.points3d(boundary[1], boundary[3], boundary[5], scale_factor=0.01, color=(0,1,0), opacity = 0.0)

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

        fig = mlab.figure(size=(2500, 2500), bgcolor=(1, 1, 1))
        fig.scene.parallel_projection = True

        self.plot_surfaces(iteration=iteration, colors=colors, opacity=opacity, boundary=boundary)

        import imageio
        frames = []
        for i in range(n_frames):
            mlab.view(azimuth=i * (360 / n_frames), elevation=view[1])
            mlab.savefig('temp.png')
            frames.append(imageio.v2.imread('temp.png'))
        imageio.mimsave(output_gif, frames, fps=n_frames / (total_time / 1000), loop=0)
        import os
        os.remove('temp.png')

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
            colors = self.colors
        if boundary is None:
            boundary = self.boundary

        fig = mlab.figure(size=(2500, 2500), bgcolor=(1, 1, 1))
        fig.scene.parallel_projection = True

        import imageio
        frames = []
        for iteration in range(history_index + 1):
            self.load_parameters(iteration=iteration)
            mlab.clf()
            self.params.geometry.surface_list[surface_index].plot(alpha=opacity, color=colors)
            if boundary is not None:
                mlab.points3d(boundary[0], boundary[2], boundary[4], scale_factor=0.01, color=(1,0,0), opacity = 0.0)
                mlab.points3d(boundary[1], boundary[3], boundary[5], scale_factor=0.01, color=(0,1,0), opacity = 0.0)
            mlab.view(azimuth=45, elevation=70)
            if output_jpg_foldpath is not None:
                figpath = output_jpg_foldpath + f'/iteration_{iteration:04d}.jpg'
            else:
                figpath = 'temp.jpg'
            mlab.savefig(figpath)
            frames.append(imageio.v2.imread(figpath))
        imageio.mimsave(output_gif, frames, fps=(history_index + 1) / (total_time / 1000), loop=0)
        import os
        if output_jpg_foldpath is None:
            os.remove('temp.jpg')

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

        fig = mlab.figure(size=(2500, 2500), bgcolor=(1, 1, 1))
        fig.scene.parallel_projection = True

        import imageio
        frames = []
        for iteration in range(history_index + 1):
            mlab.clf()
            if boundary is not None:
                mlab.points3d(boundary[0], boundary[2], boundary[4], scale_factor=0.01, color=(1,0,0), opacity = 0.0)
                mlab.points3d(boundary[1], boundary[3], boundary[5], scale_factor=0.01, color=(0,1,0), opacity = 0.0)
            self.plot_surfaces(iteration=iteration, colors=colors, opacity=opacity, boundary=boundary)
            mlab.view(azimuth=45, elevation=70)
            if output_jpg_foldpath is not None:
                figpath = output_jpg_foldpath + f'/iteration_{iteration:04d}.jpg'
            else:
                figpath = 'temp.jpg'
            mlab.savefig(figpath)
            frames.append(imageio.v2.imread(figpath))
        imageio.mimsave(output_gif, frames, fps=(history_index + 1) / (total_time / 1000), loop=0)
        import os
        if output_jpg_foldpath is None:
            os.remove('temp.jpg')

if __name__ == "__main__":
    plotter = SurfacesFigurePlotter(restart_path='Z:/Results/EXAMPLE_T20251219_172355/')
    plotter.plot_history_all_surfaces(history_index=50,
                                     output_gif='Z:/temp/example_displacement_history.gif',
                                     output_jpg_foldpath='Z:/temp/')