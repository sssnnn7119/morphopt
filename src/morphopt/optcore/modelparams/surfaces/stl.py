"""Fixed triangle-mesh surface loaded from STL or supplied in memory."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista

from morphopt._torch import torch

from .base import BaseSurfaceInterface, SurfaceExportFormat


class STLSurface(BaseSurfaceInterface):
    """Immutable triangular surface with STL import/export support."""

    def __init__(
        self,
        name: str = "",
        *,
        stl_path: str | Path | None = None,
        vertices: np.ndarray | None = None,
        faces: np.ndarray | None = None,
        scale: float = 1.0,
    ) -> None:
        super().__init__(name)
        self._stl_path = Path(stl_path) if stl_path is not None else None
        """Optional source STL path."""
        self._source_vertices = (
            None if vertices is None else np.asarray(vertices, dtype=float).copy()
        )
        """Optional in-memory triangle vertices."""
        self._source_faces = (
            None if faces is None else np.asarray(faces, dtype=np.int64).copy()
        )
        """Optional in-memory triangle connectivity."""
        self._scale = float(scale)
        """Uniform source-mesh scale factor."""
        self._vertices: np.ndarray | None = None
        """Initialized triangle vertices after source normalization."""
        self._faces: np.ndarray | None = None
        """Initialized triangle connectivity."""

    @classmethod
    def from_stl(cls, path: str | Path, *, scale: float = 1.0) -> STLSurface:
        """Create a fixed surface from an STL file."""
        return cls(stl_path=path, scale=scale)

    @classmethod
    def from_mesh(
        cls, vertices: np.ndarray, faces: np.ndarray, *, scale: float = 1.0
    ) -> STLSurface:
        """Create a fixed surface from in-memory triangular data."""
        return cls(vertices=vertices, faces=faces, scale=scale)

    @property
    def stl_path(self) -> Path | None:
        """Return the optional STL source path."""
        return self._stl_path

    @property
    def source_vertices(self) -> np.ndarray | None:
        """Return a copy of the original vertices when available."""
        return None if self._source_vertices is None else self._source_vertices.copy()

    @property
    def source_faces(self) -> np.ndarray | None:
        """Return a copy of the original triangular connectivity."""
        return None if self._source_faces is None else self._source_faces.copy()

    @property
    def scale(self) -> float:
        """Return the uniform source scale."""
        return self._scale

    def get_surface_points(self) -> torch.Tensor:
        """Read initialized STL vertices."""
        if self._vertices is None:
            raise RuntimeError(f"Surface '{self.name}' has not been initialized")
        return torch.as_tensor(self._vertices)

    def compute_normals(self, parameters: torch.Tensor) -> torch.Tensor:
        """Return nearest fixed-mesh vertex normals for coordinate queries."""
        if self._vertices is None or self._faces is None:
            raise RuntimeError(f"Surface '{self.name}' has not been initialized")
        vertices = torch.as_tensor(self._vertices)
        faces = torch.as_tensor(self._faces, dtype=torch.long)
        triangles = vertices[faces]
        face_normals = torch.linalg.cross(
            triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
        )
        vertex_normals = torch.zeros_like(vertices)
        vertex_normals.index_add_(
            0, faces.reshape(-1), face_normals.repeat_interleave(3, dim=0)
        )
        vertex_normals = vertex_normals / torch.clamp(
            torch.linalg.vector_norm(vertex_normals, dim=-1, keepdim=True),
            min=torch.finfo(vertices.dtype).eps,
        )
        query = torch.as_tensor(parameters, dtype=vertices.dtype).reshape(-1, 3)
        nearest = torch.cdist(query, vertices).argmin(dim=1)
        normals = vertex_normals[nearest]
        return -normals if self.get_flip() else normals

    @classmethod
    def supported_export_formats(cls) -> tuple[SurfaceExportFormat, ...]:
        """Return the single STL export format."""
        return ("stl",)

    def _initialize_backend(self) -> None:
        """Load source triangles and normalize their connectivity."""
        if self._source_vertices is None or self._source_faces is None:
            if self._stl_path is None:
                raise ValueError("STLSurface needs an STL path or in-memory mesh")
            mesh = pyvista.read(self._stl_path).triangulate()
            vertices = np.asarray(mesh.points, dtype=float)
            faces = np.asarray(mesh.faces, dtype=np.int64).reshape(-1, 4)[:, 1:]
        else:
            vertices = self._source_vertices
            faces = self._source_faces
        if vertices.ndim != 2 or vertices.shape[1] != 3:
            raise ValueError("STL vertices must have shape (num_vertices, 3)")
        if faces.ndim != 2 or faces.shape[1] != 3:
            raise ValueError("STL faces must have shape (num_faces, 3)")
        self._vertices = vertices * self._scale
        self._faces = faces.astype(np.int64, copy=True)
        self._sample_parameters = torch.as_tensor(self._vertices)

    def _evaluate_raw(
        self, parameters: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Use nearest fixed vertices as the parameterized fixed-surface map."""
        if self._vertices is None:
            raise RuntimeError(f"Surface '{self.name}' has not been initialized")
        vertices = torch.as_tensor(self._vertices, dtype=parameters.dtype)
        query = torch.as_tensor(parameters, dtype=vertices.dtype).reshape(-1, 3)
        nearest = torch.cdist(query, vertices).argmin(dim=1)
        coordinates = vertices[nearest]
        first_derivatives = torch.zeros(
            (coordinates.shape[0], 3, 2),
            dtype=coordinates.dtype,
            device=coordinates.device,
        )
        second_derivatives = torch.zeros(
            (coordinates.shape[0], 3, 2, 2),
            dtype=coordinates.dtype,
            device=coordinates.device,
        )
        return coordinates, first_derivatives, second_derivatives

    def update_geometry(self, parameters: torch.Tensor | None = None) -> None:
        """Cache fixed STL vertices with zero parametric derivatives."""
        del parameters
        if self._vertices is None or self._faces is None:
            raise RuntimeError(f"Surface '{self.name}' has not been initialized")
        coordinates = torch.as_tensor(self._vertices)
        zero_first = torch.zeros(
            (coordinates.shape[0], 3), dtype=coordinates.dtype, device=coordinates.device
        )
        zero_second = torch.zeros_like(zero_first)
        from .base import SurfaceGeometryData

        self._geometry_data = SurfaceGeometryData(
            coordinates=coordinates,
            first_derivative_u=zero_first,
            first_derivative_v=zero_first,
            second_derivative_uu=zero_second,
            second_derivative_uv=zero_second,
            second_derivative_vv=zero_second,
        )
        faces = torch.as_tensor(self._faces, dtype=torch.long)
        self._points_weight = self._triangle_point_weights(coordinates, faces)
        self._preview_meshes = ()

    def _compute_preview_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Build one triangular PyVista mesh for the fixed surface."""
        if self._vertices is None or self._faces is None:
            raise RuntimeError(f"Surface '{self.name}' has not been initialized")
        packed_faces = np.column_stack(
            (np.full(self._faces.shape[0], 3, dtype=np.int64), self._faces)
        ).reshape(-1)
        return (pyvista.PolyData(self._vertices, packed_faces),)

    def _export_surface(self, path: Path, format: SurfaceExportFormat) -> Path:
        """Save the initialized triangle mesh as STL."""
        del format
        mesh = self._compute_preview_meshes()[0]
        mesh.save(path)
        return path

    @staticmethod
    def _triangle_point_weights(
        vertices: torch.Tensor, faces: torch.Tensor
    ) -> torch.Tensor:
        """Accumulate one-third of each triangle area at its vertices."""
        triangles = vertices[faces]
        area = 0.5 * torch.linalg.vector_norm(
            torch.linalg.cross(
                triangles[:, 1] - triangles[:, 0],
                triangles[:, 2] - triangles[:, 0],
            ),
            dim=-1,
        )
        weights = torch.zeros(
            vertices.shape[0], dtype=vertices.dtype, device=vertices.device
        )
        weights.index_add_(0, faces.reshape(-1), area.repeat_interleave(3) / 3.0)
        return weights
