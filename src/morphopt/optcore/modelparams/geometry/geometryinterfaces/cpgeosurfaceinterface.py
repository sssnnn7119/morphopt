
import os
import sys
import cpgeo.utils
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

    def synchronize(self):
        self.model._control_points = self._cps.detach().cpu().numpy()

    def map(self, uv: torch.Tensor) -> torch.Tensor:
        """Map from UV space to 3D space using the CPGEO model."""
        uv_np = uv.detach().cpu().numpy().reshape(-1, 2)
        indices_cps, indices_pts, w = self.model.get_weights2(uv_np)
        w = torch.from_numpy(w).to(torch.get_default_device()).flatten()
        indices_cps_t = torch.from_numpy(indices_cps).to(torch.get_default_device())
        indices_pts_t = torch.from_numpy(indices_pts).to(torch.get_default_device())

        weights_per_query = indices_pts_t[1:] - indices_pts_t[:-1]
        indices_pts_t = torch.repeat_interleave(
            torch.arange(uv.shape[0], dtype=torch.long,
                         device=torch.get_default_device()),
            weights_per_query)

        indices = torch.stack([indices_pts_t, indices_cps_t], dim=0).reshape(2, -1)
        return self._map(w, indices, num_pts=uv.shape[0])

    def get_normals(self, uv: torch.Tensor) -> torch.Tensor:
        """Compute normals at given UV coordinates using the CPGEO model."""
        uv_np = uv.detach().cpu().numpy().reshape(-1, 2)
        indices_cps, indices_pts, w, wdu = self.model.get_weights2(uv_np, derivative=1)

        wdu = torch.from_numpy(wdu).to(torch.get_default_device())
        indices_cps_t = torch.from_numpy(indices_cps).to(torch.get_default_device())
        indices_pts_t = torch.from_numpy(indices_pts).to(torch.get_default_device())

        weights_per_query = indices_pts_t[1:] - indices_pts_t[:-1]
        indices_pts_t = torch.repeat_interleave(
            torch.arange(uv.shape[0], dtype=torch.long,
                         device=torch.get_default_device()),
            weights_per_query)

        indices = torch.stack([indices_pts_t, indices_cps_t], dim=0).reshape(2, -1)

        rdu = self._map(wdu[0], indices, num_pts=uv.shape[0])
        rdv = self._map(wdu[1], indices, num_pts=uv.shape[0])

        normals = torch.cross(rdv, rdu, dim=1)
        normals = normals / torch.norm(normals, dim=1, keepdim=True)

        return normals * (1 if self.flip else -1)
        

    def initialize(self):
        """Initialize the CPGEO model and preload knot points for evaluation."""
        # # Initialize CPGEO knots and thresholds
        # self.model.initialize()
        
        # self.model.refine_surface(seed_size=self.init_size, max_iterations=4)

        # # Load control points into torch tensor
        # self._cps = torch.from_numpy(self.model.control_points).to(torch.get_default_device())
        
        # # Get knot points from the CPGEO model
        # # For CPGEO, we use knot points as evaluation points (analogous to UV grid for BSP)
        # self._num_knots = self.model._knots.shape[0]

        # Initialize CPGEO knots and thresholds
        self.model.initialize()

    def reinitialize(self):

        
        self.model.refine_surface(seed_size=self.init_size, max_iterations=4)

        # Load control points into torch tensor
        self._cps = torch.from_numpy(self.model.control_points).to(torch.get_default_device())
        
        # Get knot points from the CPGEO model
        # For CPGEO, we use knot points as evaluation points (analogous to UV grid for BSP)
        self._num_knots = self.model._knots.shape[0]

        return self

    def get_preloaddata(self, pre_points: torch.Tensor = None, faces: torch.Tensor = None):

        if pre_points is not None and faces is not None:
            # If external sample points are provided, use them directly.
            preload_uv = pre_points
            input_points = pre_points.detach().cpu().numpy()
            faces_np = faces.detach().cpu().numpy()
        else:
            # Use mesh vertices directly as preload points for CPGEO.
            uv3_0 = self.model._knots
            faces_0 = self.model._cp_faces
            edges = cpgeo.capi.get_mesh_edges(faces_0)

            uv3_extra = (uv3_0[edges[:, 0]] + uv3_0[edges[:, 1]]) / 2
            uv3_extra = uv3_extra / np.linalg.norm(uv3_extra, axis=1, keepdims=True)

            preload_uv3 = np.vstack([uv3_0, uv3_extra])

            preload_uv = torch.from_numpy(self.model.reference_to_curvilinear(preload_uv3)).to(torch.get_default_device())
            input_points = preload_uv.cpu().numpy()


            faces_np = cpgeo.capi.get_sphere_triangulation(preload_uv3)


        # Precompute weights for vertex evaluation points (derivative 0, 1, 2)
        result = self.model.get_weights2(input_points, derivative=2)
        indices_cps, indices_pts, w, wdu, wdu2 = result

        
        indices_cps_t = torch.from_numpy(indices_cps).to(torch.get_default_device())
        indices_pts_t = torch.from_numpy(indices_pts).to(torch.get_default_device())

        weights_per_query = indices_pts_t[1:] - indices_pts_t[:-1]
        indices_pts_t = torch.repeat_interleave(
            torch.arange(preload_uv.shape[0], dtype=torch.long,
                         device=torch.get_default_device()),
            weights_per_query)

        indices = torch.stack([indices_pts_t, indices_cps_t], dim=0).reshape(2, -1)

        preload_data = self.PreLoadData(
            uv=preload_uv,
            cp_weights=torch.from_numpy(w).to(torch.get_default_device()).flatten(),
            cp_weights_du=torch.from_numpy(wdu[0]).to(torch.get_default_device()).flatten(),
            cp_weights_dv=torch.from_numpy(wdu[1]).to(torch.get_default_device()).flatten(),
            cp_weights_du2=torch.from_numpy(wdu2[0, 0]).to(torch.get_default_device()).flatten(),
            cp_weights_dudv=torch.from_numpy(wdu2[0, 1]).to(torch.get_default_device()).flatten(),
            cp_weights_dv2=torch.from_numpy(wdu2[1, 1]).to(torch.get_default_device()).flatten(),
            indices=indices,
            faces=torch.from_numpy(faces_np).to(torch.get_default_device())
        )

        return preload_data

    def get_points_weight(self):
        """Compute vertex-based integration weights for CPGEO preload points.

        Uses vertex barycentric area weighting: each triangle contributes one-third
        of its area to each incident vertex.
        """
        r = self.get_r().detach()
        return self.preload_data.compute_point_weights(r)


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
        cpfaces = cpgeo.capi.optimize_mesh_by_edge_flipping(vertices=r, faces=self.model._cp_faces)
        result = pools.apply_async(self.output_stl_file, args=(
            r,
            cpfaces,
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

    def match_coordinates(self, surf_node_idx: np.ndarray, surf_nodes: np.ndarray, batch_size: int | None = None):
        """
        Find closest (u, v) on CPGEO surface for each 3D point in `nodes` using a memory-efficient approach.

        Args:
            nodes (np.ndarray): Array of shape (N, 3) containing 3D
                coordinates to match on the surface.

        Returns:
            np.ndarray: Array of shape (N, 2) containing the corresponding
                (u, v) parameters on the CPGEO surface for each input node.
        """
        
        nodes = surf_nodes
        self.surf_node_idx = surf_node_idx

        N = nodes.shape[0]

        # evaluate surface at seed points (M x 3)
        preuv = self.model.reference_to_curvilinear(self.model._knots)
        r0 = self.model.map2(preuv)  # (M, 3)

        # --- find nearest seed for each node (memory-efficient) ---
        try:
            # fast & memory-friendly when scipy is available
            import scipy.spatial as sp
            tree = sp.KDTree(r0)
            _, min_dist_uv_idx = tree.query(nodes, k=1)
        except Exception:
            # fallback: chunked search over nodes to avoid creating an MxN matrix
            min_dist_uv_idx = np.empty(N, dtype=int)
            node_chunk = 1024
            for i in range(0, N, node_chunk):
                j = min(N, i + node_chunk)
                nb = nodes[i:j]                                # (B, 3)
                # compute squared distances in a chunk (M, B)
                d2 = np.sum((r0[:, None, :] - nb[None, :, :]) ** 2, axis=2)
                min_dist_uv_idx[i:j] = np.argmin(d2, axis=0)

        min_dist_uv = preuv[min_dist_uv_idx]                  # (N, 2)

        # --- Newton refinement in batches (reduces peak memory) ---
        max_iter = 5
        tol = 1e-6
        
        if batch_size is None:
            batch_size = N if N <= 4096 else 4096

        uv_out = np.empty((N, 2), dtype=float)

        for start in range(0, N, batch_size):
            end = min(N, start + batch_size)
            uv = min_dist_uv[start:end].copy()
            pts = nodes[start:end]

            for it in range(max_iter):
                r, rdot, rdot2 = self.model.map2(uv, derivative=2)

                ru = rdot[:, :, 0]
                rv = rdot[:, :, 1]
                ruu = rdot2[:, :, 0, 0]
                ruv = rdot2[:, :, 0, 1]
                rvv = rdot2[:, :, 1, 1]

                diff = r - pts
                gu = np.einsum('ij,ij->i', diff, ru)
                gv = np.einsum('ij,ij->i', diff, rv)
                gnorm = np.sqrt(gu * gu + gv * gv)

                if np.all(gnorm < tol):
                    break

                A = np.einsum('ij,ij->i', ru, ru) + np.einsum('ij,ij->i', diff, ruu)
                B = np.einsum('ij,ij->i', ru, rv) + np.einsum('ij,ij->i', diff, ruv)
                C = np.einsum('ij,ij->i', rv, rv) + np.einsum('ij,ij->i', diff, rvv)

                det = A * C - B * B
                det_reg = det.copy()
                det_reg[np.abs(det_reg) < 1e-12] = 1e-12

                du = -(C * gu - B * gv) / det_reg
                dv = -(-B * gu + A * gv) / det_reg
                delta = np.stack([du, dv], axis=1)

                f = np.einsum('ij,ij->i', diff, diff)

                uv_new = uv.copy()
                f_best = f.copy()
                accept = np.zeros(f.shape, dtype=bool)

                uv_step = np.clip(uv + delta, 0.0, 1.0)
                r_step = self.model.map2(uv_step)
                f_step = np.einsum('ij,ij->i', (r_step - pts), (r_step - pts))
                improved = f_step < f_best
                if improved.any():
                    uv_new[improved] = uv_step[improved]
                    f_best[improved] = f_step[improved]
                    accept[improved] = True

                if not np.all(accept):
                    remaining = ~accept
                    for k in range(1, 8):
                        alpha = 0.5 ** k
                        uv_try = np.clip(uv + alpha * delta, 0.0, 1.0)
                        r_try = self.model.map2(uv_try)
                        f_try = np.einsum('ij,ij->i', (r_try - pts), (r_try - pts))

                        improved = (f_try < f_best) & remaining
                        if improved.any():
                            uv_new[improved] = uv_try[improved]
                            f_best[improved] = f_try[improved]
                            accept[improved] = True
                            remaining = ~accept

                        if not remaining.any():
                            break

                uv = uv_new.copy()

                # print(f'Batch {start}-{end}, Iter {it}, Mean Residual {np.sqrt(f_best).mean():.3e}, Accept Rate {accept.mean():.2%}')

            uv_out[start:end] = uv
        self.surf_node_uv = uv_out

        return self.model.map2(uv_out)