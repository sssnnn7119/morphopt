"""CPGEO control-mesh surfaces and standard primitive definitions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista
import trimesh
import gmsh

from morphopt._torch import torch

import cpgeo

from .base import SurfaceExportFormat
from .cpbased import CpBasedSurface
from .fairness import CPGEOFairnessEvaluator


class CPGEOSurface(CpBasedSurface):
    """Editable triangular CPGEO surface exported as STL."""

    def __init__(
        self,
        name: str = "",
        *,
        cpgeo_model: cpgeo.CPGEO | None = None,
        control_points: torch.Tensor | None = None,
        control_faces: np.ndarray | None = None,
    ) -> None:
        super().__init__(name, control_points)
        self._cpgeo_model = cpgeo_model
        """CPGEO backend holding control topology and interpolation state."""
        self._control_faces = (
            None
            if control_faces is None
            else np.asarray(control_faces, dtype=np.int64).copy()
        )
        """Triangular control-mesh connectivity."""
        self._fairness_evaluator = CPGEOFairnessEvaluator()
        """Fairness evaluator owned by this editable CPGEO surface."""

    @property
    def fairness_evaluator(self) -> CPGEOFairnessEvaluator:
        """Return the evaluator dedicated to this CPGEO surface."""
        return self._fairness_evaluator

    @classmethod
    def supported_export_formats(cls) -> tuple[SurfaceExportFormat, ...]:
        """Return STL as the CPGEO surface export format."""
        return ("stl",)

    def _initialize_backend(self) -> None:
        """Create/initialize the CPGEO model and identity preload cache."""
        if self._cpgeo_model is None:
            if self._control_faces is None or self._control_points.numel() == 0:
                raise RuntimeError(f"Surface '{self.name}' has no CPGEO control mesh")
            self._cpgeo_model = cpgeo.CPGEO(
                control_points=self._control_points.detach().cpu().numpy(),
                cp_faces=self._control_faces,
                knot_influence_num=20,
            )
        if self._control_faces is None:
            self._control_faces = np.asarray(self._cpgeo_model._cp_faces, dtype=np.int64)
        if self._control_points.numel() == 0:
            self._control_points = torch.as_tensor(
                self._cpgeo_model.control_points
            ).detach().clone()
        self._cpgeo_model.initialize()
        self.build_preload(
            torch.as_tensor(self._control_points.detach().cpu()),
            torch.as_tensor(self._control_faces, dtype=torch.long),
        )

    def update_backend(self) -> None:
        """Synchronize committed control points into the CPGEO backend."""
        if self._cpgeo_model is not None:
            self._cpgeo_model.control_points = self._control_points.detach().cpu().numpy()

    def compute_normals(self, parameters: torch.Tensor) -> torch.Tensor:
        """Return nearest control-mesh vertex normals for query coordinates."""
        if self._control_faces is None:
            raise RuntimeError(f"Surface '{self.name}' has not been initialized")
        vertices = self._control_points
        faces = torch.as_tensor(self._control_faces, dtype=torch.long, device=vertices.device)
        triangles = vertices[faces]
        face_normals = torch.linalg.cross(
            triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
        )
        vertex_normals = torch.zeros_like(vertices)
        vertex_normals.index_add_(0, faces.reshape(-1), face_normals.repeat_interleave(3, dim=0))
        vertex_normals = vertex_normals / torch.clamp(
            torch.linalg.vector_norm(vertex_normals, dim=-1, keepdim=True),
            min=torch.finfo(vertices.dtype).eps,
        )
        query = torch.as_tensor(parameters, dtype=vertices.dtype, device=vertices.device).reshape(-1, 3)
        nearest = torch.cdist(query, vertices).argmin(dim=1)
        normals = vertex_normals[nearest]
        return -normals if self.get_flip() else normals

    def _compute_preview_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Build one current triangular control-mesh preview."""
        if self._control_faces is None:
            raise RuntimeError(f"Surface '{self.name}' has not been initialized")
        coordinates, _, _ = self.get_geometry_values()
        return (
            self._create_poly_data(
                coordinates, torch.as_tensor(self._control_faces, dtype=torch.long)
            ),
        )

    def _export_surface(self, path: Path, format: SurfaceExportFormat) -> Path:
        """Export the current control mesh as STL."""
        del format
        self._compute_preview_meshes()[0].save(path)
        return path


class CPGEOCylinderSurface(CPGEOSurface):
    """Triangular CPGEO cylinder surface definition."""

    def __init__(
        self,
        radius: float,
        length: float,
        seed_size: float,
        *,
        name: str = "",
        num_u_ratio: int = 1,
        num_v_ratio: int = 1,
        init_location: tuple[float, float, float] = (0.0, 0.0, 0.0),
        perturbation_length: float | None = None,
    ) -> None:
        super().__init__(name)
        self._radius = float(radius)
        """Cylinder radius."""
        self._length = float(length)
        """Cylinder axial length."""
        self._seed_size = float(seed_size)
        """Target control-mesh spacing."""
        self._num_u_ratio = int(num_u_ratio)
        """Circumferential density ratio."""
        self._num_v_ratio = int(num_v_ratio)
        """Axial density ratio."""
        self._init_location = tuple(float(value) for value in init_location)
        """Cylinder origin."""
        self._perturbation_length = perturbation_length
        """Optional initial radial perturbation wavelength."""

    @property
    def radius(self) -> float:
        """Return the cylinder radius."""
        return self._radius

    @property
    def length(self) -> float:
        """Return the cylinder axial length."""
        return self._length

    @property
    def seed_size(self) -> float:
        """Return the requested triangular surface size."""
        return self._seed_size

    @property
    def num_u_ratio(self) -> int:
        """Return the circumferential refinement ratio."""
        return self._num_u_ratio

    @property
    def num_v_ratio(self) -> int:
        """Return the axial refinement ratio."""
        return self._num_v_ratio

    @property
    def init_location(self) -> tuple[float, float, float]:
        """Return the cylinder base-center location."""
        return self._init_location

    @property
    def perturbation_length(self) -> float | None:
        """Return the optional radial perturbation wavelength."""
        return self._perturbation_length

    def _initialize_backend(self) -> None:
        """Create the cylinder control mesh before base CPGEO initialization."""
        if self._cpgeo_model is None:
            vertices, faces = self._create_cylinder_mesh()
            self._control_points = torch.as_tensor(vertices)
            self._control_faces = faces
        super()._initialize_backend()

    def _create_cylinder_mesh(self) -> tuple[np.ndarray, np.ndarray]:
        """Generate a quality triangular closed cylinder surface with Gmsh."""
        if self._radius <= 0.0 or self._length <= 0.0 or self._seed_size <= 0.0:
            raise ValueError("radius, length and seed_size must be positive")
        density_ratio = max(1, self._num_u_ratio, self._num_v_ratio)
        mesh_size = min(
            self._seed_size,
            min(self._radius, self._length) / 4.0,
        ) / density_ratio
        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Verbosity", 0)
            gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size)
            gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size)
            gmsh.option.setNumber("Mesh.RecombineAll", 0)
            gmsh.model.add(self.name or "cpgeo_cylinder")
            gmsh.model.occ.addCylinder(
                *self._init_location, 0.0, 0.0, self._length, self._radius
            )
            gmsh.model.occ.synchronize()
            gmsh.model.mesh.generate(2)
            node_tags, coordinates, _ = gmsh.model.mesh.getNodes()
            vertices = np.asarray(coordinates, dtype=float).reshape(-1, 3)
            node_index = {
                int(node_tag): index for index, node_tag in enumerate(node_tags)
            }
            faces: list[np.ndarray] = []
            for _, surface_tag in gmsh.model.getEntities(2):
                element_types, _, element_nodes = gmsh.model.mesh.getElements(
                    2, surface_tag
                )
                for element_type, nodes in zip(
                    element_types, element_nodes, strict=True
                ):
                    if element_type != 2:
                        continue
                    triangles = np.asarray(nodes, dtype=np.int64).reshape(-1, 3)
                    faces.append(
                        np.asarray(
                            [[node_index[int(node)] for node in triangle] for triangle in triangles],
                            dtype=np.int64,
                        )
                    )
        finally:
            gmsh.finalize()
        control_faces = np.concatenate(faces, axis=0)
        if self._perturbation_length is not None and self._perturbation_length > 0.0:
            relative = vertices[:, :2] - np.asarray(self._init_location[:2])
            radius = np.linalg.norm(relative, axis=1)
            amplitude = 1.0 + 0.04 * np.cos(
                2.0 * np.pi * (vertices[:, 2] - self._init_location[2])
                / self._perturbation_length
            )
            vertices[:, :2] = (
                np.asarray(self._init_location[:2])
                + relative * (self._radius * amplitude / np.maximum(radius, 1e-12))[:, None]
            )
        return vertices, control_faces


class CPGEOSphereSurface(CPGEOSurface):
    """Triangular CPGEO sphere surface definition."""

    def __init__(
        self,
        radius: float,
        seed_size: float,
        *,
        name: str = "",
        init_location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        super().__init__(name)
        self._radius = float(radius)
        """Sphere radius."""
        self._seed_size = float(seed_size)
        """Target control-mesh spacing."""
        self._init_location = tuple(float(value) for value in init_location)
        """Sphere center."""

    def _initialize_backend(self) -> None:
        """Create the sphere control mesh before base CPGEO initialization."""
        if self._cpgeo_model is None:
            vertices, faces = self._create_sphere_mesh()
            self._control_points = torch.as_tensor(vertices)
            self._control_faces = faces
        super()._initialize_backend()

    def _create_sphere_mesh(self) -> tuple[np.ndarray, np.ndarray]:
        """Create an icosphere with a density derived from seed size."""
        subdivisions = max(
            2,
            int(
                np.ceil(
                    np.log2(max(1.0, 2.0 * np.pi * self._radius / self._seed_size))
                )
            )
            - 2,
        )
        mesh = trimesh.creation.icosphere(subdivisions=subdivisions, radius=self._radius)
        vertices = np.asarray(mesh.vertices, dtype=float)
        vertices += np.asarray(self._init_location, dtype=float)
        return vertices, np.asarray(mesh.faces, dtype=np.int64)
