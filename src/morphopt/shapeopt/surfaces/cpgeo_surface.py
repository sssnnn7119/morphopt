from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile

import cpgeo
import numpy as np
import pyvista as pv
import torch
from scipy.spatial import cKDTree

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
        self._cap_disks: np.ndarray | None = None  # Bottom and head rows: center XYZ, radius.
        self._fixed_indices: torch.Tensor | None = None  # Rows in the current control mesh.
        self._fixed_points: torch.Tensor | None = None  # Reference coordinates, in the same order.

        self._num_knots: int
        """The number of knot points for the CPGEO model."""

        self._is_first_initialize = True
        """Flag to indicate whether it is the first initialization, used for controlling the initial volume calculation."""

        self._output_rsphere: np.ndarray
        """The output spherical parameterization points for visualization or debugging."""

        self._output_cpfaces: np.ndarray
        """The output control point faces for visualization or debugging."""

    def _capture_fixed_controls(self, indices: np.ndarray | None) -> None:
        """Capture end-cap coordinates at first selection or checkpoint load."""
        if indices is None:
            self._fixed_indices = self._fixed_points = None
        else:
            self._fixed_indices = torch.as_tensor(indices, dtype=torch.long, device=self._cps.device)
            self._fixed_points = self._cps.detach().index_select(0, self._fixed_indices)

    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """Project the design tensor onto the initial end-cap coordinates."""
        points = x.reshape_as(self._cps)
        if self._fixed_indices is not None:
            points = points.index_copy(
                0, self._fixed_indices.to(points.device), self._fixed_points.to(points)
            )
        self._cps = points

    @property
    def end_node_set_names(self) -> tuple[str, ...]:
        """Node sets supported by the fixed end disks of this surface."""
        return ("Bottom", "Head") if self._cap_disks is not None else ()

    def _disk_candidates(self, nodes: np.ndarray) -> dict[str, np.ndarray]:
        """Select points within the axial band and radius of each end disk.

        The height band scales with the surface seed size. For short cylinders it
        ends at the midplane, so the two sets always remain disjoint.
        """
        if self._cap_disks is None:
            return {}
        axis = self._cap_disks[1, :3] - self._cap_disks[0, :3]
        length = np.linalg.norm(axis)
        axis = axis / length
        band = min(self.init_size * CONSTANT.KERNEL.SURFACE.CPGEO_CAP_HEIGHT_RATIO, length / 2)
        result = {}
        for name, disk in zip(self.end_node_set_names, self._cap_disks):
            offsets = nodes - disk[:3]
            axial = offsets @ axis
            radial = np.linalg.norm(offsets - axial[:, None] * axis, axis=1)
            in_disk = radial <= disk[3] + CONSTANT.KERNEL.BOUNDARY_PART.NODE_SET_TOLERANCE
            result[name] = np.flatnonzero((np.abs(axial) < band) & in_disk)
        return result

    def get_node_sets(
        self, nodes: np.ndarray, *, node_uv: np.ndarray | None = None
    ) -> dict[str, np.ndarray]:
        """Select FE nodes inside each disk that also belong to its control patch.

        Each query inherits the label of the closest control knot on the reference
        sphere. A folded side wall can enter an end disk in physical space while
        its knots still belong to the side wall.

        Args:
            nodes: Cartesian coordinates of the FE surface nodes.
            node_uv: Matched CPGEO parameters in the same node order, required
                for a cylinder with fixed ends.

        Returns:
            Local node indices for Bottom and Head, or no sets for free ends.
        """
        if self._cap_disks is None:
            return {}
        if node_uv is None or len(node_uv) != len(nodes):
            raise ValueError("CPGEO end sets require one matched UV coordinate per node.")

        # Before the first refinement the control mesh is the initial cylinder.
        # Afterwards only the originally fixed controls can own an end patch.
        if self._fixed_indices is None:
            cap_controls = self._disk_candidates(self.model.control_points)
        else:
            fixed = self._fixed_indices.cpu().numpy()
            cap_controls = {
                name: fixed[local]
                for name, local in self._disk_candidates(self._fixed_points.cpu().numpy()).items()
            }

        knots = cKDTree(self.model._knots)
        sets = self._disk_candidates(nodes)
        for name, local in sets.items():
            reference, = self.model.curvilinear_to_reference(node_uv[local])
            _, nearest = knots.query(reference)
            sets[name] = local[np.isin(nearest, cap_controls[name])]
        return sets

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

    def reinitialize_constraints(self) -> None:
        """Lock the end disks on the first uniformly reconstructed, symmetry-aligned mesh."""
        super().reinitialize_constraints()
        if self._cap_disks is not None and self._fixed_indices is None and not self._is_first_initialize:
            points = self.model.control_points
            ends = self._disk_candidates(points)
            self._capture_fixed_controls(np.concatenate(list(ends.values())))

    def _reinitialize(self):
        """Internal method to reinitialize the CPGEO model without checking."""
        indices = self.model.refine_surface(
            seed_size=self.init_size,
            max_iterations=CONSTANT.KERNEL.SURFACE.CPGEO_INITIAL_REFINEMENT_ITERATIONS,
            fixed_control_indices=self._fixed_indices.cpu().numpy() if self._fixed_indices is not None else None,
        )

        # Load control points into torch tensor
        self._cps = torch.from_numpy(self.model.control_points).to(
            torch.get_default_device()
        )
        if indices is not None:
            self._fixed_indices = torch.as_tensor(indices, dtype=torch.long, device=self._cps.device)

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
        """Sample the current CPGEO surface at its target spacing and write STL."""
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
        # STL sampling redistributes vertices over the whole surface. Only control
        # mesh reconstruction needs to preserve the initial cap control points.
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

    @staticmethod
    def _archive_path(filename: str | Path) -> Path:
        """Accept either the checkpoint stem or the full NPZ filename."""
        path = Path(filename)
        return path if path.suffix == ".npz" else Path(f"{path}.npz")

    def save(self, filename: str | Path) -> None:
        """Save a native CPGEO archive with optional MorphOpt end-cap indices.

        Args:
            filename: Checkpoint stem or NPZ path.
        """
        path = self._archive_path(filename)
        self.synchronize()
        with TemporaryDirectory(dir=path.parent) as directory:
            archive = Path(directory) / path.name
            self.model.save(archive)
            if self._cap_disks is not None:
                with ZipFile(archive, "a", compression=ZIP_DEFLATED) as npz:
                    with npz.open("cap_disks.npy", "w") as entry:
                        np.save(entry, self._cap_disks, allow_pickle=False)
                    if self._fixed_indices is not None:
                        with npz.open("cap_indices.npy", "w") as entry:
                            np.save(entry, self._fixed_indices.cpu().numpy(), allow_pickle=False)
            archive.replace(path)

    def load(self, filename: str | Path) -> None:
        """Load native CPGEO geometry and restore end controls when the archive declares them."""
        with self._archive_path(filename).open("rb") as archive:
            self.model = cpgeo.CPGEO.load(archive)
            archive.seek(0)
            with np.load(archive, allow_pickle=False) as state:
                self._cap_disks = state.get("cap_disks")
                indices = state.get("cap_indices")
        self._cps = torch.as_tensor(self.model.control_points, device=self._cps.device)
        self._capture_fixed_controls(indices)
        if self._cap_disks is None and indices is not None:
            # Earlier archives stored a rim followed by its center for each end.
            self._cap_disks = np.array([
                [*cap[-1], np.linalg.norm(cap[0] - cap[-1])]
                for cap in np.split(self.model.control_points[indices], 2)
            ])
        self._is_first_initialize = True

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
        *,
        init_location=[0.0, 0.0, 0.0],
        perturbation_L: float = -1.0,
        fix_end_caps: bool = True,
    ) -> CPGEOSurface:
        """Initialize the CPGEO surface for cylinder shape optimization.

        Args:
            r0 (float): The radius of the cylinder.
            length (float): The length of the cylinder.
            seed_size (float): Initial control-mesh and surface sampling spacing.
            init_location: The initial location of the surface. Default is [0., 0., 0.].
            perturbation_L: The perturbation length for initial shape. Default is -1. If < 0, no
                perturbation is applied.
            fix_end_caps: Hold both end disks fixed during shape updates and expose their
                Bottom and Head node sets. A free-ended cylinder still forms a closed shell.

        Returns:
            CPGEOSurface: The initialized CPGEO surface object.
        """
        num_segments_circ = max(3, round(2 * np.pi * r0 / seed_size))
        num_segments_axial = max(1, round(length / seed_size))

        # Generate cylinder vertices
        vertices = []
        for i in range(num_segments_axial + 1):
            z = length * i / num_segments_axial
            for j in range(num_segments_circ):
                # Clockwise rings give the CPGEO chart outward normals for flip=False.
                theta = -2 * np.pi * j / num_segments_circ

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

        # The spherical parameterization needs a closed, consistently wound
        # control mesh. Share the end rings with the cap triangles.
        for ring, z in ((0, 0.0), (num_segments_axial, length)):
            center = len(vertices)
            vertices.append([init_location[0], init_location[1], init_location[2] + z])
            start = ring * num_segments_circ
            for j in range(num_segments_circ):
                a = start + j
                b = start + (j + 1) % num_segments_circ
                faces.append([center, b, a] if ring == 0 else [center, a, b])

        # Create CPGEO model
        cpgeo_model = cpgeo.CPGEO(
            control_points=np.array(vertices),
            cp_faces=np.array(faces),
            knot_influence_num=min(CONSTANT.KERNEL.SURFACE.CPGEO_KNOT_INFLUENCE_COUNT, len(vertices) - 1),
        )

        surface = cls(cpgeo_model, init_size=seed_size)
        if fix_end_caps:
            centers = cpgeo_model.control_points[-2:]
            rims = cpgeo_model.control_points[[0, num_segments_axial * num_segments_circ]]
            surface._cap_disks = np.column_stack((centers, np.linalg.norm(rims - centers, axis=1)))
        return surface

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

        # Start each projection at the nearest sampled surface point.
        _, min_dist_uv_idx = cKDTree(r0).query(nodes)

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
