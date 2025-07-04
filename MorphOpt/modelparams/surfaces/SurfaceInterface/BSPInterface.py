import numpy as np
import torch
from .BaseInterface import BaseInterface
from ..SurfaceModel.bspline.BSP import BSP_Surf
from .... import GLOBAL

class BspInterface(BaseInterface):
    """
    Class to handle the B-spline surface interface.
    """

    def __init__(self, surface: BSP_Surf, init_size: float, symmetric = [0], MaxR = 0.2, MaxFF = 0.1, MaxC = 1.0):
        super().__init__(surface, symmetric)
        self.model = surface
        RRuu, RRuv, RRvu, RRvv = surface.get_surface_value(derivatives=0)[0][-4:]
        
        self.MaxR = MaxR
        self.MaxFF = MaxFF
        self.MaxC = MaxC

        lengthU = (2 * surface.num_points[0] * init_size)**2
        lengthV = (2 * surface.num_points[1] * init_size)**2
        
        self.init_size = init_size

        RRuu /= lengthU
        RRuv /= lengthV
        RRvu /= lengthU
        RRvv /= lengthV

        self.rr_compensation = torch.ones(4, RRuu.shape[0])
        self.rr_compensation[0, RRuu > MaxR *
                                0.2] = MaxR * 0.2 / RRuu[RRuu > MaxR * 0.2]
        self.rr_compensation[0] /= lengthU
        self.rr_compensation[1, RRuv > MaxR *
                                0.2] = MaxR * 0.2 / RRuv[RRuv > MaxR *
                                                        0.2] / lengthV
        self.rr_compensation[1] /= lengthV
        self.rr_compensation[2, RRvu > MaxR *
                                0.2] = MaxR * 0.2 / RRvu[RRvu > MaxR *
                                                        0.2] / lengthU
        self.rr_compensation[2] /= lengthU
        self.rr_compensation[3, RRvv > MaxR *
                                0.2] = MaxR * 0.2 / RRvv[RRvv > MaxR *
                                                        0.2] / lengthV
        self.rr_compensation[3] /= lengthV
    
    def initialize(self):
        self.model.symmetric_reinitialize()
    
    @property
    def surf_type(self) -> int:
        return 0
    
    @property
    def num_variables(self) -> int:
        """
        Get the number of design variables.

        Returns:
            int: The number of design variables.
        """
        return self.model.control_points.numel()

    def output_data(self, path_output, name_output, seed_size=-1, flip=False):
        flip = not flip
        # degree
        info = "%d,%d\n" % (self.model.degree - 1, self.model.degree - 1)
        # uv control points
        info += "%d,%d\n" % (self.model.num_points[-1] + 1, self.model.num_points[-2])

        offset = round(self.model.num_points[0] / 8)

        for i in range(self.model.num_points[1] + 1):
            for j in range(self.model.num_points[0]):
                indexU = (i + offset) % self.model.num_points[1]
                info += "%e,%e,%e\n" % (self.model.control_points[0, j, indexU],
                                        self.model.control_points[1, j, indexU], self.model.control_points[2, j,
                                                                    indexU])

        with open(path_output + name_output + '.csv', 'w') as f:
            f.write(info)

        with open(path_output + '__FEM' + name_output + '.csv', 'w') as f:
            num_points = 10
            length = 0.1
            info = ''

            # for head surface search
            head = self.model.map(torch.tensor([[1, 1], [0.7, 0.2]]))
            vec = self.model.map(torch.tensor([[1, 1], [0.7, 0.2]]),
                        derivative=[0, 1])
            vv = torch.sqrt(torch.sum(vec**2, dim=0))
            vec /= vv
            info += '%e, %e, %e\n' % (head[0, 0] + length * vec[1, 0] *
                                    (1 - 2 * int(flip)),
                                    head[1, 0] - length * vec[0, 0] *
                                    (1 - 2 * int(flip)), head[2, 0])
            info += '%e, %e, %e\n' % (head[0, 1] + length * vec[1, 1] *
                                    (1 - 2 * int(flip)),
                                    head[1, 1] - length * vec[0, 1] *
                                    (1 - 2 * int(flip)), head[2, 1])

            # for bottom surface search
            bottom = self.model.map(torch.tensor([[0, 0], [0.7, 0.2]]))
            vec = self.model.map(torch.tensor([[0, 0], [0.7, 0.2]]),
                        derivative=[0, 1])
            vv = torch.sqrt(torch.sum(vec**2, dim=0))
            vec /= vv
            info += '%e, %e, %e\n' % (bottom[0, 0] + length * vec[1, 0] *
                                    (1 - 2 * int(flip)),
                                    bottom[1, 0] - length * vec[0, 0] *
                                    (1 - 2 * int(flip)), bottom[2, 0])
            info += '%e, %e, %e\n' % (bottom[0, 1] + length * vec[1, 1] *
                                    (1 - 2 * int(flip)),
                                    bottom[1, 1] - length * vec[0, 1] *
                                    (1 - 2 * int(flip)), bottom[2, 1])

            U = torch.arange(num_points) / num_points
            V = 0.5 * torch.ones_like(U)

            lateral = self.model.map((V, U))

            for i in range(num_points):
                info += "%e, %e, %e\n" % tuple(lateral[:, i])

            f.write(info)

        return name_output + '.csv'
    

    
    def get_surface_parameters(self) -> torch.Tensor:
        """
        Get the design variables of the surface.

        Returns:
            torch.Tensor: The design variables of the surface.
        """
        return self.model.control_points
    
    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """
        Set the design variables of the surface.

        Parameters:
            x (torch.Tensor): The new design variables to be set.
        """
        self.model.control_points = x.reshape(self.model.control_points.shape)
        self.model.symmetric_reinitialize()

    def update_variables(self, x_change):
        
        x_change = x_change.reshape_as(self.model.control_points)
        
        x_change[:, 0, :] = 0
        x_change[:, -1, :] = 0
        x_change[2, 1:3, :] = 0
        x_change[2, -3:-1, :] = 0
        
        self.model.control_points = self.model.control_points + x_change.reshape(self.model.control_points.shape)
    
    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get the geometry values of the surface.

        Returns:
            tuple: A tuple containing the geometry values of the surface.
                - r (torch.Tensor): The point coordinates of the surface.
                - rdu (torch.Tensor): The partial derivatives of the surface.
                - rdu2 (torch.Tensor): The second partial derivatives of the surface.
        """
        return self.model._partial_derivative(derivative=2)[0]

    def get_penalty_fairness(self, weight: torch.Tensor, r: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor) -> torch.Tensor:
        
        Normal0 = torch.cross(rdu[:, 1], rdu[:, 0], dim=0)
        Normal = Normal0 / torch.sqrt(torch.sum(Normal0**2, dim=0))

        I = torch.einsum('imp, inp->mnp', rdu, rdu)
        invI = I.permute([2, 0, 1]).inverse().permute([1, 2, 0])
        II = torch.einsum('imnp, ip->mnp', rdu2, Normal)

        detI = I[0, 0] * I[1, 1] - I[0, 1] * I[1, 0]
        detII = II[0, 0] * II[1, 1] - II[0, 1] * II[1, 0]

        H = 0.5 * (invI * II).sum([0, 1])
        K = detII / detI

        C0 = 4 * H**2 - 2 * K
        
        F = I[0, 1]
        E = I[0, 0]
        G = I[1, 1]
        FF0 = I[0, 1] * I[1, 0] / I[1, 1] / I[0, 0]

        Iu = torch.einsum('iuwp, ivp->uvwp', rdu2, rdu) + \
                torch.einsum('iup, ivwp->uvwp', rdu, rdu2)

        RRuu0 = Iu[0, 0, 0]**2 / E**2
        RRuv0 = Iu[0, 0, 1]**2 / E**2
        RRvu0 = Iu[1, 1, 0]**2 / G**2
        RRvv0 = Iu[1, 1, 1]**2 / G**2

        indexC, C = self.barrier_function(C0, self.MaxC, 0.2,
                                                    3)
        
        indexFF, FF = self.barrier_function(
            FF0, self.MaxFF, 0.8, 3)
        indexRRuu, RRuu = (self.barrier_function(
            RRuu0 * self.rr_compensation[0], self.MaxR, 0.8,
            3))
        indexRRuv, RRuv = (self.barrier_function(
            RRuv0 * self.rr_compensation[1], self.MaxR, 0.8,
            3))
        indexRRvu, RRvu = (self.barrier_function(
            RRvu0 * self.rr_compensation[2], self.MaxR, 0.8,
            3))
        indexRRvv, RRvv = (self.barrier_function(
            RRvv0 * self.rr_compensation[3], self.MaxR, 0.8,
            3))

        return (weight[indexC] * C).sum() + \
            (weight[indexFF] * FF).sum() + \
            (weight[indexRRuu] * RRuu).sum() + \
            (weight[indexRRuv] * RRuv).sum() + \
            (weight[indexRRvu] * RRvu).sum() + \
            (weight[indexRRvv] * RRvv).sum()

    def get_points_weight(self):
        
        R0 = self.model._partial_derivative(derivative=0)[0][0]
        
        R_now = R0.reshape([
            3, self.model.coordinates.shape[1],
            self.model.coordinates.shape[2]
        ])
        R_uplus = R_now.roll(-1, dims=2)

        R_vplus = R_now[:, 1:]
        R_now = R_now[:, :-1]
        R_uvplus = R_uplus[:, 1:]
        R_uplus = R_uplus[:, :-1]

        area1 = torch.cross(R_vplus - R_now, R_uplus - R_now,
                            dim=0).norm(dim=0) / 2
        area2 = torch.cross(R_uvplus - R_uplus,
                            R_uvplus - R_vplus,
                            dim=0).norm(dim=0) / 2

        ratio_now = torch.zeros_like(self.model.coordinates[0])

        ratio_now[:-1] += area1 / 3
        ratio_now[1:] += area1 / 3 + area2 / 3
        ratio_now[:-1, (torch.arange(ratio_now.shape[1]) + 1) %
                ratio_now.shape[1]] += area1 / 3 + area2 / 3
        ratio_now[1:, (torch.arange(ratio_now.shape[1]) + 1) %
                ratio_now.shape[1]] += area2 / 3

        return ratio_now.flatten()

    def save(self, filename):
        self.model.save_to_file(filename + '.txt')

    def load(self, filename):
        self.model = self.model.load_from_file(filename + '.txt')
        self.model.pre_load(
            [self.model.num_points[0] * 2, self.model.num_points[1] * 2])

    def plot(self, alpha, color):
        from mayavi import mlab
        u = torch.linspace(0, 1, self.model.num_points[0] * 2)
        v = torch.linspace(0, 1, self.model.num_points[1] * 2)
        [U, V] = torch.meshgrid(u, v, indexing='ij')
        result = self.model.map([U, V]).tolist()
        
        mlab.mesh(result[0], result[1], result[2], color=color, opacity=alpha)




    @classmethod
    def initialize_cylinder(cls, r0: float, length: float, seed_size: float, symmetric: list[int], flip: bool, degree = 4, init_location = [0.,0.,0.], maxR = 0.2, maxC = 1., maxFF = 0.2, perturbation_L = -1.):    
        """
        Initialize the B-spline surface for the optimization process.

        Parameters:
            r0 (float): The radius of the cylinder.
            length (float): The length of the cylinder.
            seed_size (float): The size of the seed for the B-spline surface.
            symmetric (list[int]): The symmetry of the surface.
            flip (bool): Whether to flip the surface or not.
            degree (int, optional): The degree of the B-spline surface. Default is 4.
            init_location (list[float], optional): The initial location of the surface. Default is [0., 0., 0.].
            maxR (float, optional): The maximum radius for the pre-loading. Default is 0.2.
            maxC (float, optional): The maximum curvature for the pre-loading. Default is 1.0.
            maxFF (float, optional): The maximum fairness factor for the pre-loading. Default is 0.2.
            perturbation_L (float, optional): The perturbation length for the surface. Default is -1. If < 0, no perturbation is applied.

        Returns:
            BSP (BSP_Surf): The initialized B-spline surface object.
            surf_type (int): The type of the surface (0 for B-spline surface).
            symmetric (list[int]): The symmetry of the surface.
        """

        numU = round(r0 * 2 * np.pi / seed_size)
        numV = round(length / seed_size)

        numU = round(numU / 12) * 12

        P0 = torch.zeros(3, numV, numU)

        x = torch.linspace(0, 1, numU + 1)[:-1]
        y = torch.linspace(0, 1, numV)

        [y, x] = torch.meshgrid(y, x, indexing='ij')
        theta = 2 * torch.pi * x + (1 / numU) * torch.pi

        if flip != 0:
            theta = -theta

        P0[0] = torch.cos(theta) * r0
        P0[1] = torch.sin(theta) * r0
        P0[2] = length * y

        # Apply perturbation if specified
        if perturbation_L > 0:
            r = torch.sqrt(P0[0]**2 + P0[1]**2)
            r_new = (1 + 0.04*torch.sin(2*(P0[2] / length) * np.pi * (length/perturbation_L))) * r0
            P0[0] *= r_new / r
            P0[1] *= r_new / r

        bsp = BSP_Surf(P0, degree, [[0, 0], [2, 2]])
        

        bsp._symmetric = symmetric
        bsp.control_points += torch.tensor(init_location).reshape([3, 1, 1])

        bsp.symmetric_reinitialize()

        bsp.control_points.data[
            2, 0, :] = init_location[2]
        bsp.control_points.data[2, -1, :] = init_location[2] + length

        bsp.pre_load([bsp.num_points[0] * 2, bsp.num_points[1] * 2],
                    init_size=seed_size)

        return cls(bsp, init_size=seed_size, symmetric=symmetric, MaxR=maxR, MaxC=maxC, MaxFF=maxFF)