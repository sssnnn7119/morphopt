
import torch
from mayavi import mlab
from .basesurfaceinterface import BaseInterface
from ..geometricmodel.closedsurfacemodel.CS import ClosedSurface
class CsInterface(BaseInterface):

    def __init__(self, surface: ClosedSurface, symmetric = [0], MaxC = 1.):
        super().__init__(surface, symmetric)
        self.MaxC = MaxC
        self.model = surface

    def reinitialize(self):
        self.model.refine_surface()

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
        return self.model.control_points.numel()

    def output_data(self, path_output, name_output, seed_size=-1, flip=False):

        if seed_size<0:
            knots = self.model.pre_nodes
            coo = self.model.pre_elements.cpu().numpy()
        else:
            knots = self.model.knots.T
            coo = self.model.knots_element.cpu().numpy()

        # points3d, coo = self.Sphere_Mesh(5000, 3)
        R = self.model.map(knots)
        r = R.cpu().numpy()

        # record the output knots and coordinates
        self.surface_out_knots = knots
        self.surface_out_coo = coo

        # Save STP file
        converter = self.MeshSurfaceConverter()
        data = converter.convert_mesh_to_stp(faces=coo,
                                      vertices=r.T,
                                        filename=name_output)
        with open(path_output + name_output + '.stp', 'w') as f:
            f.write(data)

        with open(path_output + '__FEM' + name_output + '.csv', 'w') as f:
            num_points = 10
            info = ''

            points = self.model.fibonacci_grid(num_points, dimen=3)
            output = self.model.map(points).transpose(0, 1).tolist()

            for pt in output:
                info += '%e, %e, %e\n' % (pt[0], pt[1], pt[2])

            f.write(info)

        return name_output + '.stp'
    
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
    
    def update_variables(self, x_change):
        """
        Update the design variables of the surface.

        Parameters:
            x_change (torch.Tensor): The change in design variables.
        """
        x = self.model.control_points + x_change.reshape(self.model.control_points.shape)
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

        indexC, C = self.barrier_function(C0, self.MaxC, 0.8,
                                                    1)

        return (weight[indexC] * C).sum()

    def get_points_weight(self):
        
        R0 = self.model._partial_derivative(derivative=0)[0][0]
        
        area = torch.cross(R0[:, self.model.pre_elements[:, 1]] -
                            R0[:, self.model.pre_elements[:, 0]],
                            R0[:, self.model.pre_elements[:, 2]] -
                            R0[:, self.model.pre_elements[:, 0]],
                            dim=0).norm(dim=0) / 2
        ratio_now = torch.zeros(self.model.pre_nodes.shape[1])
        ratio_now = ratio_now.scatter_add(0, self.model.pre_elements[:,
                                                                    0],
                                            area / 3)
        ratio_now = ratio_now.scatter_add(0, self.model.pre_elements[:,
                                                                    1],
                                            area / 3)
        ratio_now = ratio_now.scatter_add(0, self.model.pre_elements[:,
                                                                    2],
                                            area / 3)
        return ratio_now
    
    def save(self, filename):
        self.model.save_to_file(filename + '.txt')
    
    def load(self, filename):
        self.model = self.model.load_from_file(filename + '.txt')
        self.model.pre_load(1)

    def plot(self, alpha, color):
        """
        Plot the surface using Mayavi.

        Parameters:
            alpha (float): The transparency of the surface.
            color (tuple): The color of the surface in RGB format.
        """
        knots = self.model.symmetrize_knots_CPs()[1]
        r = self.model.map(knots.T).tolist()
        coo = self.model.knots_element.tolist()
        mlab.triangular_mesh(r[0], r[1], r[2], coo, color=color, opacity=alpha)

    @classmethod
    def initialize_Sphere(cls, seed_size: float, flip: bool, r0: float, init_location: list[float], symmetric: list[int] = [0]) -> 'CsInterface':
        """
        Initialize a sphere with a given radius and center.

        Parameters
            seed_size (float): The size of the seed points for the sphere.
            symmetric (list[int]): The symmetry of the sphere.
            flip (bool): Whether to flip the sphere or not.
            r0 (float): The radius of the sphere.
            init_location (list[float]): The initial location of the sphere.

        Returns:
            ClosedSurface (ClosedSurface): The initialized closed surface object.
            surf_type (int): The type of the surface (1 for closed surface).
            symmetric (list[int]): The symmetry of the surface.

        """

        CS = ClosedSurface(seed_size=seed_size, symmetric=symmetric, init_location=torch.tensor(init_location), flip=flip)

        CS.initialize(lambda:CS._initial_surface.sphere(radius=r0, seed_size=seed_size, flip=flip))

        CS.pre_load()

        return cls(CS, symmetric)

    @classmethod
    def initialize_Cylinder(cls, seed_size: float, flip: bool, r0: float, length: float, init_location: list[float], symmetric: list[int] = [0], MaxC: float = 1.) -> 'CsInterface':
        """
        Initialize a cylinder with a given radius and height.

        Parameters
            seed_size (float): The size of the seed points for the cylinder.
            symmetric (list[int]): The symmetry of the cylinder.
            flip (bool): Whether to flip the cylinder or not.
            r0 (float): The radius of the cylinder.
            length (float): The height of the cylinder.
            init_location (list[float]): The initial location of the cylinder.

        Returns:
            ClosedSurface (ClosedSurface): The initialized closed surface object.
            surf_type (int): The type of the surface (1 for closed surface).
            symmetric (list[int]): The symmetry of the surface.
        """

        CS = ClosedSurface(seed_size=seed_size, symmetric=symmetric, init_location=torch.tensor(init_location), flip=flip)

        CS.initialize(lambda:CS._initial_surface.cylinder(radius=r0, height=length, seed_size=seed_size, flip=flip))
        
        CS.pre_load()
        return cls(CS, symmetric, MaxC=MaxC)