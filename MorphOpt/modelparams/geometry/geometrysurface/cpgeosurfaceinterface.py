import math
import os
from mpmath import fac
import torch
from torch.nn.modules import conv
import vtk
from mayavi import mlab




from .basesurfaceinterface import BaseInterface


import CPGEO
import CPGEO.utils
import CPGEO.utils.mesh
import CPGEO.utils.mlab_visualization as vis

class CPGEOSurfaceInterface(BaseInterface):

    def __init__(self, surface: CPGEO.surface.Sphere, seed_size: float, symmetric = [0], MaxC = 1., flip: bool = False) -> None:

        super().__init__(surface, symmetric)
        self.MaxC = MaxC
        self.model = surface
        self.seed_size = seed_size
        self.flip = flip

    def initialize(self):
        self.model.reconstruction(seed_size=self.seed_size)
        self.model.pre_load(1)
        
    @property
    def surf_type(self) -> int:
        return 1
    
    @property
    def num_variables(self) -> int:
        """
        Get the number of design variables.

        Returns:
            int: The number of design variables.
        """
        return self.model.cp_vertices.numel()

    def output_data(self, path_output, name_output, seed_size=-1, flip=False):

        # if seed_size < 0:
        #     knots = self.model._pre_vertices
        #     Coo = self.model._pre_faces
            
        # else:
        knots, Coo = self.model.uniformly_mesh(seed_size=self.seed_size)
        
        # points3d, coo = self.Sphere_Mesh(5000, 3)
        R = self.model.map(knots)
        Coo = CPGEO.utils.mesh.refine_triangular_mesh(R.T, Coo)

        # record the output knots and coordinates
        self.surface_out_knots = knots
        self.surface_out_coo = Coo

        # Save STP file
        converter = self.MeshSurfaceConverter()
        data = converter.convert_mesh_to_stp(faces=Coo.cpu().numpy(),
                                      vertices=R.cpu().numpy().T,
                                        filename=name_output)
        with open(path_output + name_output + '.stp', 'w') as f:
            f.write(data)

        with open(path_output + '__FEM' + name_output + '.csv', 'w') as f:
            num_points = 10
            info = ''

            points = torch.tensor([[0., 0., 1.], [0., 1., 0.], [1., 0., 0.]]).T
            output = self.model.map(points).transpose(0, 1).tolist()

            for pt in output:
                info += '%e, %e, %e\n' % (pt[0], pt[1], pt[2])

            f.write(info)

        return name_output + '.stl'
    
    def match_points_surface(self, points):
        points_init = self.model.map(self.surface_out_knots).cpu()

        distance_init = (points.reshape([3, 1, -1]).cpu() - points_init.reshape([3, -1, 1]).cpu()).norm(dim=0)
        index_init = torch.argmin(distance_init, dim=0)

        uv_init = self.surface_out_knots.reshape([3, -1])[:, index_init]

        self._coordinates_fea = uv_init.detach().to(points.device)

    def get_surface_parameters(self) -> torch.Tensor:
        """
        Get the design variables of the surface.

        Returns:
            torch.Tensor: The design variables of the surface.
        """
        return self.model.cp_vertices
    
    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """
        Set the design variables of the surface.

        Parameters:
            x (torch.Tensor): The new design variables to be set.
        """
        self.model.cp_vertices = x.reshape(self.model.cp_vertices.shape)
    
    def update_variables(self, x_change):
        """
        Update the design variables of the surface.

        Parameters:
            x_change (torch.Tensor): The change in design variables.
        """
        x = self.model.cp_vertices + x_change.reshape(self.model.cp_vertices.shape)
        self.model.cp_vertices = self.model.cp_vertices + x_change.reshape(self.model.cp_vertices.shape)
    
    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get the geometry values of the surface.

        Returns:
            tuple: A tuple containing the geometry values of the surface.
                - r (torch.Tensor): The point coordinates of the surface.
                - rdu (torch.Tensor): The partial derivatives of the surface.
                - rdu2 (torch.Tensor): The second partial derivatives of the surface.
        """
        result = self.model.map_c(derivative=2)
        r = result[0]
        rdu = result[1]
        rdu2 = result[2]

        if self.flip:
            rdu[:, 0] = -rdu[:, 0]
            rdu2[:, 0, 0] = rdu2[:, 0, 0]
            rdu2[:, 0, 1] = -rdu2[:, 0, 1]
            rdu2[:, 1, 0] = -rdu2[:, 1, 0]
            rdu2[:, 1, 1] = rdu2[:, 1, 1]

        return r, rdu, rdu2
    
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

        # Calculate the principal curvatures
        sqrt_term = torch.sqrt(torch.clamp(H**2 - K, min=0))
        k1 = H + sqrt_term
        k2 = H - sqrt_term

        p=3

        penalty = torch.tensor(0., dtype=torch.float64)

        indexl, l = self.barrier_function(k1, self.MaxC, 0.7, p)
        if len(indexl) > 0:
            penalty += (l * weight[indexl]).sum()

        indexl, l = self.barrier_function(-k2, self.MaxC, 0.7, p)
        if len(indexl) > 0:
            penalty += (l * weight[indexl]).sum()


        return penalty

    def get_points_weight(self):
        
        R0 = self.model.map(derivative=0)
        
        area = torch.cross(R0[:, self.model._pre_faces[:, 1]] -
                            R0[:, self.model._pre_faces[:, 0]],
                            R0[:, self.model._pre_faces[:, 2]] -
                            R0[:, self.model._pre_faces[:, 0]],
                            dim=0).norm(dim=0) / 2
        ratio_now = torch.zeros(self.model._pre_vertices.shape[1])
        ratio_now = ratio_now.scatter_add(0, self.model._pre_faces[:,
                                                                    0],
                                            area / 3)
        ratio_now = ratio_now.scatter_add(0, self.model._pre_faces[:,
                                                                    1],
                                            area / 3)
        ratio_now = ratio_now.scatter_add(0, self.model._pre_faces[:,
                                                                    2],
                                            area / 3)
        return ratio_now
    
    def save(self, filename):
        self.model.save(filename)
    
    def load(self, filename):
        self.model = self.model.load(filename + '.npz')
        self.model.pre_load(1)

    def plot(self, alpha, color):
        """
        Plot the surface using Mayavi.

        Parameters:
            alpha (float): The transparency of the surface.
            color (tuple): The color of the surface in RGB format.
        """

        r = self.model.map(self.model.knots).tolist()
        coo = self.model.cp_elements.tolist()
        mlab.triangular_mesh(r[0], r[1], r[2], coo, color=color, opacity=alpha)

    @classmethod
    def initialize_Sphere(cls, seed_size: float, flip: bool, r0: float, init_location: list[float], symmetric: list[int] = [0], MaxC = 1.) -> 'CPGEOSurfaceInterface':
        """
        Initialize a sphere with a given radius and center.

        Parameters
            seed_size (float): The size of the seed points for the sphere.
            symmetric (list[int]): The symmetry of the sphere.
            flip (bool): Whether to flip the sphere or not.
            r0 (float): The radius of the sphere.
            init_location (list[float]): The initial location of the sphere.

        Returns:
            CPGEO.surface._Surface_base: The initialized closed surface object.

        """

        num_points = 4*math.pi*r0**2 / seed_size**2
        num_points = int(num_points)

        cpgeo = CPGEO.surface.sphere(num_points=num_points, radius=r0)
        cpgeo.cp_vertices = cpgeo.cp_vertices + torch.tensor(init_location).reshape([3, 1])
        cpgeo.k_neighbors=12
        cpgeo.pre_load(1)
        #, surface: CPGEO.surface.Sphere, seed_size: float, symmetric = [0], MaxC = 1., flip: bool = False
        return cls(cpgeo, seed_size, symmetric, MaxC, flip)

    @classmethod
    def initialize_Cylinder(cls, seed_size: float, flip: bool, r0: float, length: float, init_location: list[float], symmetric: list[int] = [0], MaxC = 1.) -> 'CPGEOSurfaceInterface':
        """
        Initialize a cylinder with a given radius and height.

        Parameters
            seed_size (float): The size of the seed points for the cylinder.
            symmetric (list[int]): The symmetry of the cylinder.
            flip (bool): Whether to flip the cylinder or not.
            r0 (float): The radius of the cylinder.
            length (float): The height of the cylinder.
            init_location (list[float]): The initial location of the cylinder.
            MaxC (float): The maximum curvature of the cylinder.

        Returns:
            CPGEO.surface._Surface_base: The initialized closed surface object.
        """

        num_points = round(
            (2 * math.pi * r0 * length + 2 * math.pi * r0**2) /
            (1.732 * seed_size**2) * 2)
        num_points = max(100, num_points)

        threshold = (length / 1.2) / (length + r0 * 2)

        n = torch.arange(num_points) + 1
        phi = (math.sqrt(5) - 1) / 2
        zn = (2 * n - 1) / num_points - 1
        xn = torch.sqrt(1 - zn**2) * torch.cos(2 * torch.pi * n * phi)
        yn = torch.sqrt(1 - zn**2) * torch.sin(2 * torch.pi * n * phi)

        knots = torch.stack([xn, yn, zn], dim=0).T

        phi0 = (torch.acos(knots[:, 2]) - math.pi / 2) / (math.pi / 2)

        index_lateral = (phi0.abs() < threshold)
        index_head = ~index_lateral & (phi0 >= 0)
        index_bottom = ~index_lateral & (phi0 <= 0)

        theta = torch.atan2(knots[index_lateral, 1], knots[index_lateral,
                                                            0])
        phi = phi0[index_lateral]
        phi = phi / phi.abs().max()

        control_points = torch.zeros([3, num_points])
        control_points[0, index_lateral] = r0 * torch.cos(theta)
        control_points[1, index_lateral] = r0 * torch.sin(theta)
        control_points[2, index_lateral] = length * phi / 2

        control_points[0, index_head] = knots[index_head, 0] / math.cos(
            threshold * math.pi / 2) * r0
        control_points[1, index_head] = knots[index_head, 1] / math.cos(
            threshold * math.pi / 2) * r0
        control_points[2, index_head] = length / 2

        control_points[0,
                        index_bottom] = knots[index_bottom, 0] / math.cos(
                            threshold * math.pi / 2) * r0
        control_points[1,
                        index_bottom] = knots[index_bottom, 1] / math.cos(
                            threshold * math.pi / 2) * r0
        control_points[2, index_bottom] = -length / 2

        control_points[0] *= -1

        cpgeo = CPGEO.surface.Sphere()
        cpgeo.cp_vertices = control_points + torch.tensor(init_location).reshape([3, 1])
        cpgeo.cp_elements = CPGEO.surface._mesh_methods.sphere_mesh(knots.T)
        
        normal = torch.cross(knots[cpgeo.cp_elements[:, 1]] - knots[cpgeo.cp_elements[:, 0]],
                            knots[cpgeo.cp_elements[:, 2]] - knots[cpgeo.cp_elements[:, 0]],
                            dim=1).T
        normal_ = torch.cross(cpgeo.cp_vertices.T[cpgeo.cp_elements[:, 1]] - cpgeo.cp_vertices.T[cpgeo.cp_elements[:, 0]],
                            cpgeo.cp_vertices.T[cpgeo.cp_elements[:, 2]] - cpgeo.cp_vertices.T[cpgeo.cp_elements[:, 0]],
                            dim=1).T
        triangularcenter = (knots[cpgeo.cp_elements[:, 0]] + knots[cpgeo.cp_elements[:, 1]] +
                            knots[cpgeo.cp_elements[:, 2]]).T / 3
        triangularcenter_ = (cpgeo.cp_vertices.T[cpgeo.cp_elements[:, 0]] +
                            cpgeo.cp_vertices.T[cpgeo.cp_elements[:, 1]] +
                            cpgeo.cp_vertices.T[cpgeo.cp_elements[:, 2]]).T / 3
        cpgeo.k_neighbors=12
        cpgeo.initialize()
        cpgeo.pre_load(1)
        # cpgeo.reconstruction(seed_size=seed_size)
        return cls(cpgeo, seed_size, symmetric, MaxC, flip)