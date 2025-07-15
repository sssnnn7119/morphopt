import torch
from ..base_params import BaseParams
import numpy as np
import os
from ... import GLOBAL
from mayavi import mlab

class Materials(BaseParams):
    """
    Class to handle the materials of the morphable model.
    """

    def __init__(self, mu: float, kappa: float, density: float) -> None:
        """
        Initialize the Materials class.

        Args:
            mu (float): The shear modulus of the material.
            kappa (float): The bulk modulus of the material.
        """
        super().__init__()
        self.mu = torch.tensor(mu)
        self.kappa = torch.tensor(kappa)
        self.density = torch.tensor(density)

    def get_modules(self, nodes: torch.Tensor = None) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Get the modules of the materials.

        Args:
            nodes (torch.Tensor): The nodes of the morphable model.

        Returns:
            torch.Tensor: The modules of the materials.
        """
        return self.mu, self.kappa

    def get_density(self, nodes: torch.Tensor = None) -> torch.Tensor:
        """
        Get the density of the materials.

        Args:
            nodes (torch.Tensor): The nodes of the morphable model.
                size: (N, 3) where N is the number of nodes.

        Returns:
            torch.Tensor: The density of the materials.
        """
        return self.density

    def get_ratio(self, nodes: torch.Tensor) -> float:
        """
        Get the ratio of maximum to minimum modulus.
        
        Returns:
            float: The ratio of maximum to minimum modulus.
        """
        return 1.0

class BsplineMaterials(Materials):
    """
    Class to handle the materials of the morphable model with B-spline surfaces.
    """

    def __init__(self,
                 mu: float,
                 kappa: float,
                 min_ratio: float,
                 density: float,
                 boundary: list[list[float]],
                 seed_size: float,
                 max_step_length=0.1,
                 init_density = 0.5) -> None:
        """
        Initialize the BsplineMaterials class.

        Args:
            mu (float): The shear modulus of the material.
            kappa (float): The bulk modulus of the material.
            ratio (float): The ratio of maximum to minimum modulus.
            density (float): The density of the material.
        """
        import sys
        sys.path.append("..")
        sys.path.append('..//Modules/bspline')
        from Bspline.bspline import BSP

        num_U = (boundary[0][1] - boundary[0][0]) // seed_size + 1
        num_V = (boundary[1][1] - boundary[1][0]) // seed_size + 1
        num_W = (boundary[2][1] - boundary[2][0]) // seed_size + 1
        
        num_U = int(num_U)
        num_V = int(num_V)
        num_W = int(num_W)

        P0 = torch.ones([1, num_U, num_V, num_W]) * init_density

        self.bspline = BSP(P0=P0,
                           degree=3,
                           dimension_input=3,
                           dimension_output=1,
                           vector_type=[[0, 0], [0, 0], [0, 0]],
                           domain_zoom=boundary)
        
        """ The B-spline surface for the materials.
        It is a 3D B-spline surface with the control points initialized to 1.
        The control points are the parameters of the materials."""

        super().__init__(mu, kappa, density)
        self.min_ratio = min_ratio
        """ The ratio of maximum to minimum modulus.
        It is used to calculate the modules of the materials based on the B-spline surface."""

        self.boundary = torch.tensor(boundary)

        self.max_step_length = max_step_length
        """
        The maximum step length for the x.
        """

    def get_ratio(self, nodes: torch.Tensor) -> torch.Tensor:
        """
        Get the ratio of maximum to minimum modulus.
        
        Args:
            nodes (torch.Tensor): The nodes of the morphable model.
                size: (N, 3) where N is the number of nodes.
        
        Returns:
            torch.Tensor: The ratio of maximum to minimum modulus.
            The ratio is calculated based on the B-spline surface and the minimum ratio.
        """
        x = self.bspline.map(nodes.reshape([-1, 3]).T)
        return x + (1 - x) * self.min_ratio
        
    def get_density(self, nodes):
        """
        Get the density of the materials.
        
        Args:
            nodes (torch.Tensor): The nodes of the morphable model.

        Returns:
            torch.Tensor: The density of the materials.
        """
        

        size0 = nodes.shape[:-1]
        
        density = self.density * self.get_ratio(nodes)
        density = density.reshape(size0)
        
        return density

    def get_modules(self, nodes):
        """
        Get the modules of the materials.

        Args:
            nodes (torch.Tensor): The nodes of the morphable model.

        Returns:
            torch.Tensor: The modules of the materials.
        """

        size0 = nodes.shape[:-1]
        
        ratio = self.get_ratio(nodes)

        mu = ratio * self.mu
        kappa = ratio * self.kappa

        mu = mu.reshape(size0)
        kappa = kappa.reshape(size0)
        return mu, kappa

    def get_variables(self) -> list[torch.Tensor]:

        return torch.randn_like(self.bspline.control_points.flatten()) * 1e-6

    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the variables of the class.
        
        Args:
            x_change (torch.Tensor): The change in variables.
        """

        dp = 2 / torch.pi * torch.atan(x_change) * self.max_step_length
        self.bspline.control_points = self.bspline.control_points + dp.reshape_as(
            self.bspline.control_points)
        self.bspline.control_points[self.bspline.control_points < 0] = 0
        self.bspline.control_points[self.bspline.control_points > 1] = 1

    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the parameters of the class.
        
        Args:
            xlist (list[torch.Tensor]): The new parameters for the class.
        """
        self.bspline.control_points = xlist[0].reshape(
            self.bspline.control_points.shape).detach().clone()

    def get_parameters(self) -> list[torch.Tensor]:
        """
        Get the parameters of the class.
        
        Returns:
            list[torch.Tensor]: The parameters of the class.
        """
        return [self.bspline.control_points.flatten().detach().clone()]


    def save(self, filepath: str) -> None:
        """
        Save the parameters to a file using numpy.savez.
        
        Args:
            filepath (str): The name of the file to save the parameters to.
        """

        # Save parameters as .npz file
        np.savez(
            filepath + '/MaterialField_%d' % (GLOBAL.History.iteration),
            mu=self.mu.detach().cpu().numpy(),
            kappa=self.kappa.detach().cpu().numpy(),
            density=self.density.detach().cpu().numpy(),
            boundary=self.boundary.detach().cpu().numpy(),
            control_points=self.bspline.control_points.detach().cpu().numpy(),
            max_step_length=np.array(self.max_step_length))

    def load(self, filepath: str, iteration: int) -> None:
        """
        Load the parameters from a file.
        
        Args:
            filepath (str): The name of the file to load the parameters from.
            iteration (int): The iteration number to load.
        """
        
        # Load data from the specified .npz file
        file_path = filepath + f'/MaterialField_{iteration}.npz'
        if not os.path.exists(file_path):
            print(f"Warning: File {file_path} does not exist.")
            return
            
        data = np.load(file_path)
        self.mu = torch.tensor(data['mu'])
        self.kappa = torch.tensor(data['kappa'])
        self.density = torch.tensor(data['density'])
        self.boundary = torch.tensor(data['boundary'])
        self.bspline.control_points = torch.tensor(data['control_points'])
        self.max_step_length = float(data['max_step_length'])
        print(f"Successfully loaded materials from {file_path}")
        
    def plot(self) -> None:
        """
        Plot the parameters of the materials using Mayavi.
        This function visualizes the B-spline control points and the scalar field.
        """
        # 创建立方体的网格数据
        x, y, z = torch.meshgrid(
            torch.linspace(self.boundary[0][0], self.boundary[0][1], self.bspline.control_points.shape[1]),
            torch.linspace(self.boundary[1][0], self.boundary[1][1], self.bspline.control_points.shape[2]),
            torch.linspace(self.boundary[2][0], self.boundary[2][1], self.bspline.control_points.shape[3]),
            indexing='ij'
        )



        # 定义标量场和透明度场
        density = self.bspline.map(torch.stack([x, y, z], dim=-1).reshape(-1, 3).T).reshape(x.shape).cpu().numpy()
        density = density**3

        density[0,0,0] = 0.0  # 确保密度场的最小值为0，避免透明度问题
        density[0,0,-1] = 1  # 确保密度场的最大值为1，避免透明度问题

        x = x.cpu()
        y = y.cpu()
        z = z.cpu()
        
        # 创建标量场 - 注意：不需要转置，保持一致的形状
        src = mlab.pipeline.scalar_field(x, y, z, density)
        
        # 使用体积渲染
        vol = mlab.pipeline.volume(src, vmin=0.1, vmax=0.8)
        # 设置透明度转换函数
        otf = vol._volume_property.get_scalar_opacity()
        otf.remove_all_points()
        otf.add_point(0.1, 0.0)    # 低密度值透明
        otf.add_point(0.3, 0.1)
        otf.add_point(0.4, 0.3)
        otf.add_point(0.6, 0.7)
        otf.add_point(0.8, 0.9)    # 高密度值不透明
        
        # 设置颜色转换函数 - 适配不同版本的Mayavi
        try:
            # 尝试使用color_transfer_function
            ctf = vol._volume_property.get_color_transfer_function()
        except AttributeError:
            try:
                # 尝试使用color_tf (某些版本使用)
                ctf = vol._volume_property.color_tf
            except AttributeError:
                # 尝试使用gray_transfer_function (根据错误提示)
                ctf = vol._volume_property.get_gray_transfer_function()
        
        # 清除现有点并添加新的颜色点
        ctf.remove_all_points()
        try:
            # 尝试使用add_rgb_point
            ctf.add_rgb_point(0.1, 0.7, 0.7, 0.7)   # 低密度灰色
            ctf.add_rgb_point(0.3, 0.5, 0.5, 0.9)   # 中密度蓝色
            ctf.add_rgb_point(0.7, 0.9, 0.2, 0.3)   # 高密度红色
        except AttributeError:
            # 备用方法，如果add_rgb_point不可用
            ctf.add_point(0.1, 0.7, 0.7, 0.7)   # 低密度灰色
            ctf.add_point(0.3, 0.5, 0.5, 0.9)   # 中密度蓝色
            ctf.add_point(0.7, 0.9, 0.2, 0.3)   # 高密度红色

    def save_figure(self, filepath: str) -> None:
        """
        Save the figure of the parameters to a file.
        
        Args:
            filepath (str): The name of the file to save the figure to.
        """
        fig = mlab.figure(bgcolor=(1, 1, 1), size=(800, 800))
        fig.scene.parallel_projection = True


        
        self.plot()
        
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

        mlab.view(azimuth=210, elevation=70, distance=300)
        mlab.savefig(filepath + '%d.jpg'%GLOBAL.History.iteration)
        mlab.close()
