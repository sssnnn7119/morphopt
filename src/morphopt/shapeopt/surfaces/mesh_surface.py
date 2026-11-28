"""Fixed boundaries represented by triangular surface meshes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Self

import numpy as np
import pyvista as pv

from .base_surface import BaseSurface, SurfaceExportFormat

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

    from torchfea.cad.builder import OCCBuilder

    from ...optcore.modelparams.parts.cad_part import CADMeshingMixin


def _save_triangle_stl(vertices: np.ndarray, faces: np.ndarray, path: Path) -> None:
    """Write triangular connectivity in binary STL format, locally or in a pool worker."""
    pv.PolyData.from_regular_faces(vertices, faces).save(path, binary=True)


class MeshSurface(BaseSurface):
    """A boundary represented by a fixed triangular surface mesh."""

    export_formats = (SurfaceExportFormat.STL,)

    is_discrete = True

    def __init__(self, vertices: np.ndarray, faces: np.ndarray) -> None:
        """Store vertex coordinates and triangular face connectivity.

        Args:
            vertices (np.ndarray): Cartesian vertex coordinates with shape (num_vertices, 3).
            faces (np.ndarray): Face selection or mesh connectivity required by the selected surface
                operation.
        """
        super().__init__()

        self._vertices = vertices
        self._faces = faces

    @classmethod
    def initialize_from_stl_file(cls, path_stl: str | Path) -> Self:
        """Read an STL file into triangular mesh coordinates and connectivity.

        Args:
            path_stl (str | Path): Path to the triangulated STL geometry asset.

        Returns:
            Self: MeshSurface initialized from the STL vertices and triangle connectivity.
        """
        mesh = pv.read(path_stl)
        vertices = mesh.points
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        return cls(vertices, faces)

    def write_surface(
        self,
        stem: str | Path,
        fmt: str,
        pools: Pool | None = None,
    ) -> Path:
        """Write the fixed triangles as STL."""
        path = self._surface_path(stem, fmt)
        if pools is None:
            _save_triangle_stl(self._vertices, self._faces, path)
        else:
            pools.apply(_save_triangle_stl, (self._vertices, self._faces, path))
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
            list[int]: Discrete face tags reconstructed from the stored triangulated boundary.
        """
        return part.load_mesh_boundary(self._geometry_path)

    def get_mesh(self) -> pv.PolyData:
        """Return the triangular boundary as a PyVista surface mesh.

        Returns:
            pv.PolyData: The triangular boundary as a PyVista surface mesh.
        """
        return pv.PolyData.from_regular_faces(self._vertices, self._faces)
