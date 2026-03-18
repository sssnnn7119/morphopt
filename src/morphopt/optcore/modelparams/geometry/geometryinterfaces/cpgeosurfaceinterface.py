
import os
import sys
import numpy as np
import torch
import gmsh

import morphopt

from .basesurfaceinterface import CpBasedInterface
import cpgeo

class CPGEOInterface(CpBasedInterface):
    """
    Class to handle the CPGEO surface interface.
    
    CPGEO uses triangular meshes with control points for morphology optimization,
    providing a flexible alternative to B-spline surfaces for complex geometries.
    """

    def __init__(self, surface: cpgeo.CPGEO, init_size: float, symmetric = [0], MaxC = 1.0):
        super().__init__(surface, symmetric)

        self.model = surface
        """The CPGEO surface model."""

        self._cps = torch.from_numpy(self.model.control_points).to(torch.get_default_device())
        
        self.MaxC = MaxC

        self.init_size = init_size
        
        self._num_knots: int
        """The number of knot points for the CPGEO model."""

    def initialize(self):
        """Initialize the CPGEO model and preload knot points for evaluation."""
        
        # Initialize CPGEO knots and thresholds
        self.model.initialize()

        self._preload()

        
    def reinitialize(self):
        
        self.model.refine_surface(seed_size=self.init_size, max_iterations=4)
        
        # Load control points into torch tensor
        self._cps = torch.from_numpy(self.model.control_points).to(torch.get_default_device())
        
        # Get knot points from the CPGEO model
        # For CPGEO, we use knot points as evaluation points (analogous to UV grid for BSP)
        self._num_knots = self.model._knots.shape[0]

        self._preload()

        return self

    def _preload(self):
        # Precompute Gaussian quadrature points (Dunavant 6-point rule) per triangular face
        knots = self.model._knots
        faces = self.model._cp_faces
        v0 = knots[faces[:, 0]]
        v1 = knots[faces[:, 1]]
        v2 = knots[faces[:, 2]]

        # Dunavant 6-point rule: two 3-point orbits (barycentric coordinates)
        # orbit 1: alpha1=0.816847572980459, beta1=0.091576213509771
        # orbit 2: alpha2=0.108103018168070, beta2=0.445948490915965
        a1 = 0.816847572980459
        b1 = 0.091576213509771
        a2 = 0.108103018168070
        b2 = 0.445948490915965

        gauss_points = np.stack([
            a1 * v0 + b1 * v1 + b1 * v2,
            b1 * v0 + a1 * v1 + b1 * v2,
            b1 * v0 + b1 * v1 + a1 * v2,
            a2 * v0 + b2 * v1 + b2 * v2,
            b2 * v0 + a2 * v1 + b2 * v2,
            b2 * v0 + b2 * v1 + a2 * v2,
        ], axis=1).reshape(-1, 3)

        gauss_points = gauss_points / np.linalg.norm(gauss_points, axis=1, keepdims=True)  # Normalize for spherical surfaces

        self._preload_uv = torch.from_numpy(gauss_points).to(torch.get_default_device()).to(self._cps.dtype)

        # Precompute weights for Gaussian points (derivative 0, 1, 2)
        # get_weights3 returns: (indices_cps, indices_pts, w) for derivative=0
        #                       (indices_cps, indices_pts, w), (indices_cps, indices_pts, wdu) for derivative=1
        #                       (indices_cps, indices_pts, w), (indices_cps, indices_pts, wdu), (indices_cps, indices_pts, wdu2) for derivative=2
        result = self.model.get_weights3(gauss_points, derivative=2)
        indices_cps, indices_pts, w, wdu, wdu2 = result

        
        indices_cps_t = torch.from_numpy(indices_cps).to(torch.get_default_device())
        indices_pts_t = torch.from_numpy(indices_pts).to(torch.get_default_device())

        weights_per_query = indices_pts_t[1:] - indices_pts_t[:-1]
        # 使用repeat_interleave创建查询点索引
        indices_pts_t = torch.repeat_interleave(torch.arange(self._preload_uv.shape[0], dtype=torch.long), weights_per_query)
        
        # Convert to torch tensors and flatten for compatibility with base class _map method
        self._indices = torch.stack([indices_pts_t, indices_cps_t], dim=0).reshape(2, -1)
        
        self._weights = torch.from_numpy(w).to(torch.get_default_device()).flatten()

        self._weights_du = torch.from_numpy(wdu[0]).to(torch.get_default_device()).flatten()
        self._weights_dv = torch.from_numpy(wdu[1]).to(torch.get_default_device()).flatten()
        self._weights_du2 = torch.from_numpy(wdu2[0, 0]).to(torch.get_default_device()).flatten()
        self._weights_dv2 = torch.from_numpy(wdu2[1, 1]).to(torch.get_default_device()).flatten()
        self._weights_dudv = torch.from_numpy(wdu2[0, 1]).to(torch.get_default_device()).flatten()

    def get_points_weight(self):
        """Compute area-based weights for each Gaussian preload point.
        
        For each triangular face we use a 6-point Gaussian quadrature. Each
        Gaussian point receives weight = triangle_area / 6.

        Returns:
            torch.Tensor: Weights for each preload point (shape: num_faces * 6)
        """
        # Use control-point coordinates to compute triangle areas
        cps = self._cps.detach()
        faces = torch.from_numpy(self.model._cp_faces).to(cps.device)

        v0 = cps[faces[:, 0]]
        v1 = cps[faces[:, 1]]
        v2 = cps[faces[:, 2]]

        # Triangle area = 0.5 * ||cross product||
        areas = torch.cross(v1 - v0, v2 - v0, dim=1).norm(dim=1) / 2.0

        # Dunavant 6-point rule uses two orbits with different weights.
        # Reference triangle (area = 1/2) weights for the two orbits are:
        #   wA = 0.054975871827661  (for the three points of orbit A)
        #   wB = 0.1116907948390055 (for the three points of orbit B)
        # They sum to 1/2. Convert to fractions (sum to 1) by dividing by 1/2.
        f1 = 0.054975871827661 / 0.5
        f2 = 0.1116907948390055 / 0.5

        # Per-triangle weights: for each face, six points have weights [f1,f1,f1,f2,f2,f2]*area
        fractions = torch.tensor([f1, f1, f1, f2, f2, f2], device=cps.device, dtype=self._cps.dtype)
        weights = (areas.unsqueeze(1) * fractions.unsqueeze(0)).reshape(-1)

        # Ensure same dtype/device as other tensors
        return weights.to(cps.device).to(self._cps.dtype)


    @staticmethod
    def output_stl_file(vertices, faces, path_output, name_output):
        """Output CPGEO mesh as STL file.
        
        Args:
            vertices (np.ndarray): Vertex coordinates, shape (N, 3)
            faces (np.ndarray): Face connectivity, shape (F, 3)
            path_output (str): Output directory path
            name_output (str): Output file name (without extension)
        """
        import pyvista as pv
        
        # Create PyVista mesh
        faces_with_count = np.hstack([np.full((faces.shape[0], 1), 3), faces])
        mesh = pv.PolyData(vertices, faces_with_count)
        
        # Output STL file
        output_file = path_output + name_output + '.stl'
        mesh.save(output_file)
        
        return output_file

    def output_data(self, path_output, name_output, seed_size=-1, flip=False):
        """Output CPGEO mesh data to STL file.
        
        Args:
            path_output (str): Output directory path
            name_output (str): Output file name
            seed_size (float): Optional seed size (unused for CPGEO)
            flip (bool): Optional flip flag (unused for CPGEO)
        
        Returns:
            str: Output filename with extension
        """
        
        pools = morphopt.controller.pools
        r = self.model.map3(self.model._knots)
        result = pools.apply_async(self.output_stl_file, args=(
            r,
            self.model._cp_faces,
            path_output,
            name_output))
        result.get()

        return name_output + '.stl'

    def _geofair_data(self, r: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor):
        """
        To compute the geometric fairness data.

        Parameters:
            r (torch.Tensor): The surface points.
            rdu (torch.Tensor): The first derivatives of the surface points.
            rdu2 (torch.Tensor): The second derivatives of the surface points.

        Returns:
            C0 (torch.Tensor): The curvature-based fairness measure.
            FF0 (torch.Tensor): The first fundamental form-based fairness measure.
            RRuu0 (torch.Tensor): The second derivative in u direction-based fairness measure.
            RRuv0 (torch.Tensor): The mixed second derivative-based fairness measure.
            RRvu0 (torch.Tensor): The mixed second derivative-based fairness measure.
            RRvv0 (torch.Tensor): The second derivative in v direction-based fairness measure.
        """
        Normal0 = torch.cross(rdu[:, :, 1], rdu[:, :, 0], dim=1)
        Normal = Normal0 / torch.sqrt(torch.sum(Normal0**2, dim=1, keepdim=True))

        I = torch.einsum('pim, pin->pmn', rdu, rdu)
        invI = I.inverse()
        II = torch.einsum('pimn, pi->pmn', rdu2, Normal)

        detI = I[:, 0, 0] * I[:, 1, 1] - I[:, 0, 1] * I[:, 1, 0]
        detII = II[:, 0, 0] * II[:, 1, 1] - II[:, 0, 1] * II[:, 1, 0]

        H = 0.5 * (invI * II).sum([1, 2])
        K = detII / detI

        C0 = 4 * H**2 - 2 * K

        return C0

    def get_penalty_fairness(self, weight: torch.Tensor, r: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor) -> torch.Tensor:
    
        C0 = self._geofair_data(r, rdu, rdu2)

        indexC, C = self.barrier_function(C0, self.MaxC, 0.8,
                                                    5)

        return (weight[indexC] * C).sum()


    def save(self, filename):
        """Save CPGEO model to file."""
        self.model.control_points = self._cps.detach().cpu().numpy()
        self.model.save(filename)

    def load(self, filename):
        """Load CPGEO model from file."""
        self.model = cpgeo.CPGEO.load(filename + '.npz')
        self._cps = torch.from_numpy(self.model.control_points).to(torch.get_default_device())
        self.initialize()


    def get_mesh(self):
        """Get PyVista mesh from CPGEO model.
        
        Returns:
            pv.PolyData: PyVista mesh with current control point positions
        """
        import pyvista as pv
        
        # Get current control point positions
        vertices = r = self.model.map3(self.model._knots)
        faces = self.model._cp_faces
        
        # Create PyVista mesh (prepend face count for each triangle)
        faces_with_count = np.hstack([np.full((faces.shape[0], 1), 3), faces])
        mesh = pv.PolyData(vertices, faces_with_count)
        mesh.compute_normals(inplace=True)
        
        return mesh


    @classmethod
    def initialize_cylinder(cls, r0: float, length: float, seed_size: float, flip: bool, 
                          num_U_ratio: int = 1, num_V_ratio: int = 1, symmetric: list[int] = [0], 
                          degree = 3, init_location = [0.,0.,0.], maxR = 0.2, maxC = 1., maxFF = 0.2, 
                          perturbation_L = -1.):
        """
        Initialize the CPGEO surface for cylinder shape optimization.

        Parameters:
            r0 (float): The radius of the cylinder.
            length (float): The length of the cylinder.
            seed_size (float): The size of the mesh seed.
            flip (bool): Whether to flip the surface normal or not.
            num_U_ratio (int, optional): The ratio for mesh density in circumferential direction. Default is 1.
            num_V_ratio (int, optional): The ratio for mesh density in axial direction. Default is 1.
            symmetric (list[int]): The symmetry of the surface.
            degree (int, optional): Unused for CPGEO. Default is 3.
            init_location (list[float], optional): The initial location of the surface. Default is [0., 0., 0.].
            maxR (float, optional): The maximum curvature derivative constraint. Default is 0.2.
            maxC (float, optional): The maximum curvature constraint. Default is 1.0.
            maxFF (float, optional): The maximum fairness factor. Default is 0.2.
            perturbation_L (float, optional): The perturbation length for initial shape. Default is -1. If < 0, no perturbation is applied.

        Returns:
            CPGEOInterface: The initialized CPGEO surface object.
        """
        import trimesh
        
        # Create cylindrical mesh using trimesh
        # Estimate number of segments based on seed size
        num_segments_circ = max(12, round(r0 * 2 * np.pi / seed_size))
        num_segments_circ = round(num_segments_circ / 12) * 12  # Make it divisible by 12
        num_segments_circ = round(num_segments_circ / num_U_ratio) * num_U_ratio
        
        num_segments_axial = max(2, round(length / seed_size))
        num_segments_axial = round(num_segments_axial / num_V_ratio) * num_V_ratio
        
        # Generate cylinder vertices
        vertices = []
        for i in range(num_segments_axial + 1):
            z = length * i / num_segments_axial
            for j in range(num_segments_circ):
                theta = 2 * np.pi * j / num_segments_circ
                if flip:
                    theta = -theta
                
                # Base radius
                r_val = r0
                
                # Apply perturbation if specified
                if perturbation_L > 0:
                    r_val = r0 * (1 + 0.04 * np.cos(2 * (z / length) * np.pi * (length / perturbation_L)))
                
                x = r_val * np.cos(theta) + init_location[0]
                y = r_val * np.sin(theta) + init_location[1]
                z_final = z + init_location[2]
                
                vertices.append([x, y, z_final])
        
        vertices = np.array(vertices)
        
        # Generate faces (triangulate the cylinder surface)
        faces = []
        for i in range(num_segments_axial):
            for j in range(num_segments_circ):
                # Current ring
                v00 = i * num_segments_circ + j
                v01 = i * num_segments_circ + (j + 1) % num_segments_circ
                # Next ring
                v10 = (i + 1) * num_segments_circ + j
                v11 = (i + 1) * num_segments_circ + (j + 1) % num_segments_circ
                
                # Two triangles per quad
                if flip:
                    faces.append([v00, v10, v01])
                    faces.append([v01, v10, v11])
                else:
                    faces.append([v00, v01, v10])
                    faces.append([v01, v11, v10])
        
        faces = np.array(faces)
        
        # Create CPGEO model
        cpgeo_model = cpgeo.CPGEO(
            control_points=vertices,
            cp_faces=faces,
            knot_influence_num=20
        )
        
        # Create interface
        output = cls(cpgeo_model, init_size=seed_size, symmetric=symmetric, 
                    MaxR=maxR, MaxC=maxC, MaxFF=maxFF)
        output.flip = flip

        return output
    
    @classmethod
    def initialize_Sphere(cls, r0: float, seed_size: float, flip: bool, symmetric: list[int] = [0], init_location = [0.,0.,0.], 
                          MaxC = 1.0):
        """
        Initialize the CPGEO surface for sphere shape optimization.

        Parameters:
            r0 (float): The radius of the sphere.
            seed_size (float): The size of the mesh seed.
            flip (bool): Whether to flip the surface normal or not.
            symmetric (list[int]): The symmetry of the surface.
            init_location (list[float], optional): The initial location of the surface. Default is [0., 0., 0.].
            MaxC (float, optional): The maximum curvature constraint. Default is 1.0
        Returns:
            CPGEOInterface: The initialized CPGEO surface object.
            
        """
        import cpgeo.capi

        # Estimate number of points based on surface area and seed size
        area = 4 * np.pi * r0**2
        num_points = int(area / (seed_size**2))
        
        # Generate points using Fibonacci Lattice for uniform spherical distribution
        indices = np.arange(0, num_points, dtype=float) + 0.5
        phi = np.arccos(1 - 2*indices/num_points) + 1e-9  # small offset to avoid north pole singularity
        theta = np.pi * (1 + 5**0.5) * indices

        x = r0 * np.cos(theta) * np.sin(phi) + init_location[0]
        y = r0 * np.sin(theta) * np.sin(phi) + init_location[1]
        z = r0 * np.cos(phi) + init_location[2]

        vertices = np.stack((x, y, z), axis=-1)
        
        # Get triangulation from CAPI
        # We pass coordinates relative to the center, as spherical triangulation 
        # typically operates on directions or convex hull of points
        vertices_relative = (vertices - np.array(init_location)) / r0
        faces = cpgeo.capi.get_sphere_triangulation(vertices_relative.flatten())

        # Create CPGEO model
        cpgeo_model = cpgeo.CPGEO(
            control_points=vertices,
            cp_faces=faces,
            knot_influence_num=20
        )
        
        # Create interface
        output = cls(cpgeo_model, init_size=seed_size, symmetric=symmetric, MaxC=MaxC)
        output.flip = flip

        return output

        