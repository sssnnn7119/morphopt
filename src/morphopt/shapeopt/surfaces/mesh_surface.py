"""Fixed boundaries represented by triangular surface meshes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Self

import numpy as np
import pyvista as pv

from .base_surface import BaseSurface

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

    from torchfea.cad.builder import OCCBuilder

    from ...optcore.modelparams.parts.cad_part import CADMeshingMixin


class MeshSurface(BaseSurface):
    """A boundary represented by a fixed triangular surface mesh."""

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

    @staticmethod
    def output_stl_file(
        vertices: np.ndarray,
        faces: np.ndarray,
        path_output: str | Path,
        name_output: str,
    ) -> str:
        """Write the triangular surface mesh to an STL file.

        Args:
            vertices (np.ndarray): Cartesian vertex coordinates with shape (num_vertices, 3).
            faces (np.ndarray): Face selection or mesh connectivity required by the selected surface
                operation.
            path_output (str | Path): Directory in which geometry files are written.
            name_output (str): Output geometry filename stem, without the generated format suffix.

        Returns:
            str: Written STL path, including its format suffix.
        """
        faces_with_count = np.hstack([np.full((faces.shape[0], 1), 3), faces])
        mesh = pv.PolyData(vertices, faces_with_count)

        output_file = Path(path_output) / f"{name_output}.stl"
        mesh.save(output_file)
        return str(output_file)

    def output_data(
        self,
        path_output: str | Path,
        name_output: str,
        seed_size: float = -1,
        pools: Pool | None = None,
    ) -> str:
        """Export the mesh as STL and return its filename.

        Args:
            path_output (str | Path): Directory in which geometry files are written.
            name_output (str): Output geometry filename stem, without the generated format suffix.
            seed_size (float): Geometry sampling or meshing spacing in model length units.
            pools (Pool | None): Optional multiprocessing pool for geometry preparation or export.

        Returns:
            str: Geometry filename relative to path_output, including its format suffix.
        """
        arguments = (self._vertices, self._faces, path_output, name_output)
        if pools is None:
            self.output_stl_file(*arguments)
        else:
            pools.apply_async(self.output_stl_file, args=arguments).get()

        return name_output + ".stl"

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
        faces = np.asarray(self._faces, dtype=np.int64)
        faces_with_count = np.column_stack(
            [np.full(faces.shape[0], 3, dtype=np.int64), faces]
        )
        return pv.PolyData(np.asarray(self._vertices), faces_with_count)
