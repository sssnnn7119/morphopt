from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import cpgeo
import numpy as np
import pyvista as pv
import torch

from ...constants import CONSTANT
from .base_surface import ControlPointSurface, SurfaceExportFormat
from .cpgeo_constraints import (
    CPGEOMirrorConstraint,
    CPGEORotationalSymmetryConstraint,
    CPGEOSurfaceRelationConstraint,
)
from .mesh_surface import _save_triangle_stl

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

    from torchfea.cad.builder import OCCBuilder

    from ...optcore.modelparams.parts.cad_part import CADMeshingMixin


class CPGEOSurface(ControlPointSurface):
    """Represent a closed CPGEO surface with a triangular control mesh.

    The PyTorch control-point tensor carries design-variable gradients. The CPGEO backend
    supplies basis coefficients, reconstruction, and STL export. Call synchronize() before
    operations that read backend geometry after changing live control points.
    """

    export_format = SurfaceExportFormat.STL

    is_discrete = True
    mirror: type[CPGEOMirrorConstraint] = CPGEOMirrorConstraint
    rotate: type[CPGEORotationalSymmetryConstraint] = CPGEORotationalSymmetryConstraint
    relate: type[CPGEOSurfaceRelationConstraint] = CPGEOSurfaceRelationConstraint

    def __init__(
        self,
        surface: cpgeo.CPGEO,
        init_size: float,
    ):
        """Initialize CPGEOSurface and its configuration state.

        Args:
            surface (cpgeo.CPGEO): Surface interface to register, evaluate, or constrain.
            init_size (float): Target CPGEO reconstruction spacing in model length units.
        """
        super().__init__()
        self.is_updatable = True

        self.model: cpgeo.CPGEO = surface
        """The CPGEO surface model."""

        self._cps = torch.from_numpy(self.model.control_points).to(
            torch.get_default_device()
        )

        self.init_size = init_size

        self._num_knots: int
        """The number of knot points for the CPGEO model."""

        self._is_first_initialize = True
        """Flag to indicate whether it is the first initialization, used for controlling the initial volume calculation."""

        self._output_rsphere: np.ndarray
        """The output spherical parameterization points for visualization or debugging."""

        self._output_cpfaces: np.ndarray
        """The output control point faces for visualization or debugging."""

    def synchronize(self):
        """Copy live geometric parameters to the external geometry representation."""
        self.model._control_points = self._cps.detach().cpu().numpy()

    def map(self, uv: torch.Tensor) -> torch.Tensor:
        """Map from UV space to 3D space using the CPGEO model.

        Args:
            uv (torch.Tensor): Surface parameter coordinates with shape (num_queries, 2).

        Returns:
            torch.Tensor: Evaluated Cartesian positions with shape (num_queries, 3), retaining
                control-point gradients.
        """
        uv_np = uv.detach().cpu().numpy().reshape(-1, 2)
        indices_cps, indices_pts, w = self.model.get_weights2(uv_np)
        w = torch.from_numpy(w).to(torch.get_default_device()).flatten()
        indices_cps_t = torch.from_numpy(indices_cps).to(torch.get_default_device())
        indices_pts_t = torch.from_numpy(indices_pts).to(torch.get_default_device())

        weights_per_query = indices_pts_t[1:] - indices_pts_t[:-1]
        indices_pts_t = torch.repeat_interleave(
            torch.arange(
                uv.shape[0], dtype=torch.long, device=torch.get_default_device()
            ),
            weights_per_query,
        )

        indices = torch.stack([indices_pts_t, indices_cps_t], dim=0).reshape(2, -1)
        return self._map(w, indices, num_pts=uv.shape[0])

    def get_normals(self, uv: torch.Tensor) -> torch.Tensor:
        """Compute normals at given UV coordinates using the CPGEO model.

        Args:
            uv (torch.Tensor): Surface parameter coordinates with shape (num_queries, 2).

        Returns:
            torch.Tensor: Oriented unit normals with shape (num_queries, 3).
        """
        uv_np = uv.detach().cpu().numpy().reshape(-1, 2)
        indices_cps, indices_pts, _, wdu = self.model.get_weights2(uv_np, derivative=1)

        wdu = torch.from_numpy(wdu).to(torch.get_default_device())
        indices_cps_t = torch.from_numpy(indices_cps).to(torch.get_default_device())
        indices_pts_t = torch.from_numpy(indices_pts).to(torch.get_default_device())

        weights_per_query = indices_pts_t[1:] - indices_pts_t[:-1]
        indices_pts_t = torch.repeat_interleave(
            torch.arange(
                uv.shape[0], dtype=torch.long, device=torch.get_default_device()
            ),
            weights_per_query,
        )

        indices = torch.stack([indices_pts_t, indices_cps_t], dim=0).reshape(2, -1)

        rdu = self._map(wdu[0], indices, num_pts=uv.shape[0])
        rdv = self._map(wdu[1], indices, num_pts=uv.shape[0])

        normals = torch.cross(rdv, rdu, dim=1)
        normals = normals / torch.norm(normals, dim=1, keepdim=True)

        return normals * (1 if self.flip else -1)

    def initialize(self):
        """Initialize the CPGEO model and preload knot points for evaluation."""
        self.model.initialize()

        self._is_first_initialize = True

    def _reconstruction_check(self):
        """Compare the largest and smallest control-point influence areas.

        Returns:
            bool: True when the influence-area ratio exceeds the configured reconstruction
                threshold.
        """

        # calculate the gaussian determinant of the first fundamental form
        gaussian_points = self.model._knots[self.model._cp_faces].mean(axis=1)
        gaussian_points = gaussian_points / np.linalg.norm(
            gaussian_points, axis=1, keepdims=True
        )

        indices_cps, indices_pts = self.model.get_weights3(gaussian_points)[:2]
        indices_cps_t = torch.from_numpy(indices_cps).to(torch.get_default_device())
        indices_pts_t = torch.from_numpy(indices_pts).to(torch.get_default_device())

        weights_per_query = indices_pts_t[1:] - indices_pts_t[:-1]
        indices_pts_t = torch.repeat_interleave(
            torch.arange(
                gaussian_points.shape[0],
                dtype=torch.long,
                device=torch.get_default_device(),
            ),
            weights_per_query,
        )

        # the triangular areas for each face
        r = self.model.map3(self.model._knots)
        area = 0.5 * np.linalg.norm(
            np.cross(
                r[self.model._cp_faces][:, 1] - r[self.model._cp_faces][:, 0],
                r[self.model._cp_faces][:, 2] - r[self.model._cp_faces][:, 0],
            ),
            axis=1,
        )

        # influence of control points
        area_g = torch.zeros(
            self.model.control_points.shape[0], device=torch.get_default_device()
        )
        area_g.index_add_(
            0,
            indices_cps_t,
            torch.from_numpy(area)
            .to(torch.get_default_device())
            .flatten()[indices_pts_t],
        )

        return (
            area_g.max() / area_g.min()
            > CONSTANT.KERNEL.SURFACE.CPGEO_AREA_IMBALANCE_THRESHOLD
        )

    def reinitialize(self, iteration: int, *args: object, **kwargs: object) -> None:
        """Reconstruct the CPGEO control mesh when its sampling-area distribution becomes unbalanced.

        The first call also performs reconstruction. Rebuilding can change the number of control
        points, so basis and geometry caches are refreshed before the next subproblem.

        Args:
            iteration (int): Iteration index associated with the saved or current model state.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """

        if_reconstruct = self._reconstruction_check()

        if if_reconstruct or self._is_first_initialize:
            self._reinitialize()
            self._is_first_initialize = False

    def _reinitialize(self):
        """Internal method to reinitialize the CPGEO model without checking."""
        self.model.refine_surface(
            seed_size=self.init_size,
            max_iterations=CONSTANT.KERNEL.SURFACE.CPGEO_INITIAL_REFINEMENT_ITERATIONS,
        )

        # Load control points into torch tensor
        self._cps = torch.from_numpy(self.model.control_points).to(
            torch.get_default_device()
        )

        # Get knot points from the CPGEO model
        # For CPGEO, we use knot points as evaluation points (analogous to UV grid for BSP)
        self._num_knots = self.model._knots.shape[0]

        self.pre_load()

    def get_preloaddata(
        self, pre_points: torch.Tensor = None, faces: torch.Tensor = None
    ):
        """Precompute sparse CPGEO basis stencils for surface integration and differentiation.

        Args:
            pre_points (torch.Tensor): Optional curvilinear parameter samples with shape
                (num_points, 2). Supply together with triangular faces; otherwise use refined
                reference-sphere samples.
            faces (torch.Tensor): Optional triangular connectivity indexing pre_points.

        Returns:
            ControlPointSurface.PreLoadData: Parameters, triangle connectivity, and sparse basis
                coefficients through second derivatives.
        """
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

            preload_uv = torch.from_numpy(
                self.model.reference_to_curvilinear(preload_uv3)
            ).to(torch.get_default_device())
            input_points = preload_uv.cpu().numpy()

            faces_np = cpgeo.capi.get_sphere_triangulation(preload_uv3)

        # Precompute weights for vertex evaluation points (derivative 0, 1, 2)
        result = self.model.get_weights2(input_points, derivative=2)
        indices_cps, indices_pts, w, wdu, wdu2 = result

        indices_cps_t = torch.from_numpy(indices_cps).to(torch.get_default_device())
        indices_pts_t = torch.from_numpy(indices_pts).to(torch.get_default_device())

        weights_per_query = indices_pts_t[1:] - indices_pts_t[:-1]
        indices_pts_t = torch.repeat_interleave(
            torch.arange(
                preload_uv.shape[0], dtype=torch.long, device=torch.get_default_device()
            ),
            weights_per_query,
        )

        indices = torch.stack([indices_pts_t, indices_cps_t], dim=0).reshape(2, -1)

        preload_data = self.PreLoadData(
            uv=preload_uv,
            cp_weights=torch.from_numpy(w).to(torch.get_default_device()).flatten(),
            cp_weights_du=torch.from_numpy(wdu[0])
            .to(torch.get_default_device())
            .flatten(),
            cp_weights_dv=torch.from_numpy(wdu[1])
            .to(torch.get_default_device())
            .flatten(),
            cp_weights_du2=torch.from_numpy(wdu2[0, 0])
            .to(torch.get_default_device())
            .flatten(),
            cp_weights_dudv=torch.from_numpy(wdu2[0, 1])
            .to(torch.get_default_device())
            .flatten(),
            cp_weights_dv2=torch.from_numpy(wdu2[1, 1])
            .to(torch.get_default_device())
            .flatten(),
            indices=indices,
            faces=torch.from_numpy(faces_np).to(torch.get_default_device()),
        )

        return preload_data

    def get_points_weight(self):
        """Compute vertex-based integration weights for CPGEO preload points.

        Uses vertex barycentric area weighting: each triangle contributes one-third of its area to
        each incident vertex.

        Returns:
            torch.Tensor: Reference surface-area quadrature weights aligned with the preloaded
                sample points.
        """
        r = self.get_r().detach()
        return self.preload_data.compute_point_weights(r)

    def write_surface(
        self,
        stem: str | Path,
        fmt: str,
        pools: Pool | None = None,
    ) -> Path:
        """Reconstruct the current CPGEO surface at its sampling spacing and write STL."""
        path = self._surface_path(stem, fmt)
        self.synchronize()
        # The native spherical remesher requires a closed control mesh.
        control_mesh = pv.PolyData.from_regular_faces(
            self.model.control_points, self.model._cp_faces
        )
        if control_mesh.n_open_edges:
            raise ValueError(
                "CPGEO STL export requires a closed control mesh. Check the end caps and shared edges."
            )
        r_sphere, cpfaces = self.model.uniformly_mesh(
            seed_size=self.init_size,
            max_iterations=CONSTANT.KERNEL.SURFACE.CPGEO_OUTPUT_REFINEMENT_ITERATIONS,
        )
        r = self.model.map3(r_sphere)

        self._output_rsphere = r_sphere
        self._output_cpfaces = cpfaces

        if pools is None:
            _save_triangle_stl(r, cpfaces, path)
        else:
            pools.apply(_save_triangle_stl, (r, cpfaces, path))
        return path

    def load_geometry(
        self,
        part: CADMeshingMixin,
        context: OCCBuilder,
    ) -> list[int]:
        """Load geometry.

        Args:
            part (CADMeshingMixin): Part whose geometry, mesh, or named sets are processed.
            context (OCCBuilder): Active Gmsh/OCC builder owned by the caller's serialized geometry
                session.

        Returns:
            list[int]: Discrete face tags of the CPGEO boundary in the active assembly session.
        """
        return part.load_mesh_boundary(self._geometry_path)

    def save(self, filename):
        """Save CPGEO model to file.

        Args:
            filename: State-file path or filename prefix accepted by this component's save/load
                pair.
        """
        self.model.control_points = self._cps.detach().cpu().numpy()
        self.model.save(filename)

    def load(self, filename):
        """Load CPGEO model from file.

        Args:
            filename: State-file path or filename prefix accepted by this component's save/load
                pair.
        """
        self.model = cpgeo.CPGEO.load(filename + ".npz")
        self._cps = torch.from_numpy(self.model.control_points).to(
            torch.get_default_device()
        )
        self.initialize()

    def get_mesh(self):
        """Get the PyVista mesh from the synchronized CPGEO model.

        Returns:
            pv.PolyData: Triangular surface mesh with computed normals.

        Notes:
            The backend model supplies the coordinates. Call synchronize() first if the live PyTorch
            control points have changed since the last synchronization.
        """
        # Get current control point positions
        vertices = self.model.map3(self.model._knots)
        faces = self.model._cp_faces

        # Create PyVista mesh (prepend face count for each triangle)
        faces_with_count = np.hstack([np.full((faces.shape[0], 1), 3), faces])
        mesh = pv.PolyData(vertices, faces_with_count)
        mesh.compute_normals(inplace=True)

        return mesh

    @classmethod
    def initialize_cylinder(
        cls,
        r0: float,
        length: float,
        seed_size: float,
        num_U_ratio: int = 1,
        num_V_ratio: int = 1,
        init_location=[0.0, 0.0, 0.0],
        perturbation_L=-1.0,
    ):
        """Initialize the CPGEO surface for cylinder shape optimization.

        Args:
            r0 (float): The radius of the cylinder.
            length (float): The length of the cylinder.
            seed_size (float): Initial control-mesh and surface sampling spacing.
            num_U_ratio (int): Circumferential segment-count alignment factor, combined with 12 by
                LCM.
            num_V_ratio (int): Axial segment-count rounding factor; the final count is even.
            init_location: The initial location of the surface. Default is [0., 0., 0.].
            perturbation_L: The perturbation length for initial shape. Default is -1. If < 0, no
                perturbation is applied.

        Returns:
            CPGEOSurface: The initialized CPGEO surface object.
        """
        # Estimate number of segments based on seed size
        base_segments = CONSTANT.KERNEL.SURFACE.CYLINDER_CIRCUMFERENTIAL_BASE_SEGMENTS
        num_segments_circ = max(base_segments, round(r0 * 2 * np.pi / seed_size))
        circ_ratio = int(np.lcm(base_segments, num_U_ratio))
        num_segments_circ = max(
            circ_ratio, round(num_segments_circ / circ_ratio) * circ_ratio
        )

        num_segments_axial = max(2, round(length / seed_size))
        num_segments_axial = round(num_segments_axial / num_V_ratio) * num_V_ratio
        if num_segments_axial % 2:
            num_segments_axial += 1

        # Generate cylinder vertices
        vertices = []
        for i in range(num_segments_axial + 1):
            z = length * i / num_segments_axial
            for j in range(num_segments_circ):
                theta = 2 * np.pi * j / num_segments_circ

                # Base radius
                r_val = r0

                # Apply perturbation if specified
                if perturbation_L > 0:
                    r_val = r0 * (
                        1
                        + CONSTANT.KERNEL.SURFACE.CYLINDER_INITIAL_PERTURBATION_RATIO
                        * np.cos(2 * (z / length) * np.pi * (length / perturbation_L))
                    )

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
                faces.append([v00, v01, v10])
                faces.append([v01, v11, v10])

        faces = np.array(faces)

        # Create CPGEO model
        cpgeo_model = cpgeo.CPGEO(
            control_points=vertices, cp_faces=faces, knot_influence_num=20
        )

        # Create interface
        return cls(cpgeo_model, init_size=seed_size)

    @classmethod
    def initialize_Sphere(
        cls,
        r0: float,
        seed_size: float,
        init_location=[0.0, 0.0, 0.0],
    ):
        """Initialize the CPGEO surface for sphere shape optimization.

        Args:
            r0 (float): The radius of the sphere.
            seed_size (float): The size of the mesh seed.
            init_location: The initial location of the surface. Default is [0., 0., 0.].

        Returns:
            CPGEOSurface: The initialized CPGEO surface object.
        """
        import cpgeo.capi

        # Estimate number of points based on surface area and seed size
        area = 4 * np.pi * r0**2
        num_points = int(area / (seed_size**2))

        # Generate points using Fibonacci Lattice for uniform spherical distribution
        indices = np.arange(0, num_points, dtype=float) + 0.5
        phi = (
            np.arccos(1 - 2 * indices / num_points)
            + CONSTANT.KERNEL.SURFACE.SPHERE_POLE_OFFSET
        )  # avoid the pole singularity
        theta = np.pi * (1 + 5**0.5) * indices

        x = -r0 * np.cos(theta) * np.sin(phi) + init_location[0]
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
            control_points=vertices, cp_faces=faces, knot_influence_num=20
        )

        # Create interface
        return cls(cpgeo_model, init_size=seed_size)

    def match_coordinates(
        self,
        surf_node_idx: np.ndarray,
        surf_nodes: np.ndarray,
        batch_size: int | None = None,
    ):
        """Project finite-element surface nodes onto the synchronized CPGEO geometry.

        Matched parameters and global node indices are retained for subsequent differentiable
        geometry updates.

        Args:
            surf_node_idx (np.ndarray): Global FE node indices corresponding to surf_nodes.
            surf_nodes (np.ndarray): Cartesian coordinates of assigned surface nodes, shape
                (num_nodes, 3).
            batch_size (int | None): Maximum number of points processed together during coordinate
                matching.

        Returns:
            np.ndarray: Projected Cartesian positions with shape (num_nodes, 3), in input-node
                order. The matched (u, v) parameters are stored separately in surf_node_uv.
        """

        nodes = surf_nodes
        self.surf_node_idx = surf_node_idx

        N = nodes.shape[0]

        # evaluate surface at seed points (M x 3)
        preuv = self.model.reference_to_curvilinear(self._output_rsphere)

        r0 = self.model.map2(preuv)  # (M, 3)

        # --- find nearest seed for each node (memory-efficient) ---
        try:
            # fast & memory-friendly when scipy is available
            import scipy.spatial as sp

            tree = sp.KDTree(r0)
            _, min_dist_uv_idx = tree.query(nodes, k=1)
        except ImportError:
            # fallback: chunked search over nodes to avoid creating an MxN matrix
            min_dist_uv_idx = np.empty(N, dtype=int)
            node_chunk = CONSTANT.KERNEL.SURFACE.PROJECTION_NODE_CHUNK_SIZE
            for i in range(0, N, node_chunk):
                j = min(N, i + node_chunk)
                nb = nodes[i:j]  # (B, 3)
                # compute squared distances in a chunk (M, B)
                d2 = np.sum((r0[:, None, :] - nb[None, :, :]) ** 2, axis=2)
                min_dist_uv_idx[i:j] = np.argmin(d2, axis=0)

        min_dist_uv = preuv[min_dist_uv_idx]  # (N, 2)

        # --- Newton refinement in batches (reduces peak memory) ---
        max_iter = CONSTANT.KERNEL.SURFACE.PROJECTION_ITERATIONS_CPGEO
        tol = CONSTANT.KERNEL.SURFACE.PROJECTION_TOLERANCE

        if batch_size is None:
            batch_limit = CONSTANT.KERNEL.SURFACE.PROJECTION_BATCH_SIZE_CPGEO
            batch_size = min(N, batch_limit)

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
                gu = np.einsum("ij,ij->i", diff, ru)
                gv = np.einsum("ij,ij->i", diff, rv)
                gnorm = np.sqrt(gu * gu + gv * gv)

                if np.all(gnorm < tol):
                    break

                A = np.einsum("ij,ij->i", ru, ru) + np.einsum("ij,ij->i", diff, ruu)
                B = np.einsum("ij,ij->i", ru, rv) + np.einsum("ij,ij->i", diff, ruv)
                C = np.einsum("ij,ij->i", rv, rv) + np.einsum("ij,ij->i", diff, rvv)

                det = A * C - B * B
                det_reg = det.copy()
                regularization = (
                    CONSTANT.KERNEL.SURFACE.PROJECTION_REGULARIZATION_TOLERANCE
                )
                det_reg[np.abs(det_reg) < regularization] = regularization

                du = -(C * gu - B * gv) / det_reg
                dv = -(-B * gu + A * gv) / det_reg
                delta = np.stack([du, dv], axis=1)

                f = np.einsum("ij,ij->i", diff, diff)

                uv_new = uv.copy()
                f_best = f.copy()
                accept = np.zeros(f.shape, dtype=bool)

                uv_step = np.clip(uv + delta, 0.0, 1.0)
                r_step = self.model.map2(uv_step)
                f_step = np.einsum("ij,ij->i", (r_step - pts), (r_step - pts))
                improved = f_step < f_best
                if improved.any():
                    uv_new[improved] = uv_step[improved]
                    f_best[improved] = f_step[improved]
                    accept[improved] = True

                if not np.all(accept):
                    remaining = ~accept
                    for k in range(
                        1, CONSTANT.KERNEL.SURFACE.PROJECTION_LINE_SEARCH_STEPS + 1
                    ):
                        alpha = CONSTANT.KERNEL.SURFACE.PROJECTION_LINE_SEARCH_DECAY**k
                        uv_try = np.clip(uv + alpha * delta, 0.0, 1.0)
                        r_try = self.model.map2(uv_try)
                        f_try = np.einsum("ij,ij->i", (r_try - pts), (r_try - pts))

                        improved = (f_try < f_best) & remaining
                        if improved.any():
                            uv_new[improved] = uv_try[improved]
                            f_best[improved] = f_try[improved]
                            accept[improved] = True
                            remaining = ~accept

                        if not remaining.any():
                            break

                uv = uv_new.copy()

            uv_out[start:end] = uv
        self.surf_node_uv = uv_out

        return self.model.map2(uv_out)
