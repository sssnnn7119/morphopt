"""Editable boundary Part generated from ordered parametric surfaces."""

from __future__ import annotations

from multiprocessing.pool import Pool
from pathlib import Path
from typing import cast

import numpy as np
import pyvista
from morphopt._torch import torch
import torchfea

from .base import BasePartDefinition
from .mesh import MeshBuilder
from ..surfaces.base import BaseSurfaceInterface, SurfaceExportFormat


class BoundaryPart(BasePartDefinition):
    """Generate an editable solid Part from its ordered boundary surfaces.

    Surface zero defines the exterior envelope.  Subsequent surfaces define
    internal cavities, receive a reversed v-parameter orientation, and share
    the same control-point update lifecycle as the exterior surface.
    """

    def __init__(
        self,
        part_name: str = "final_model",
        *,
        element_name: str = "solid",
        fea_seed_size: float | None = None,
        mesh_order: int = 1,
        exterior_surface: str = "extern",
    ) -> None:
        super().__init__(
            part_name,
            element_names=(str(element_name),),
            exterior_surface=exterior_surface,
        )
        self._element_name = str(element_name)
        """Name assigned to the generated finite-element family."""
        self._fea_seed_size = fea_seed_size
        """Optional target size supplied to Gmsh for volume meshing."""
        self._mesh_order = int(mesh_order)
        """Requested finite-element interpolation order, one or two."""
        self._surfaces: list[BaseSurfaceInterface] = []
        """Ordered surface definitions used to generate this solid."""
        self._control_point_shapes: tuple[torch.Size, ...] = ()
        """Shapes used to split the flattened geometry design vector."""
        self._design_delta: torch.Tensor = torch.zeros(0, dtype=torch.float32)
        """Current local design delta supplied by the DesignRegistry."""
        self._surface_node_index: tuple[np.ndarray, ...] = ()
        """Per-surface TorchFEA node indices built after volume meshing."""
        self._surface_node_parameters: tuple[np.ndarray, ...] = ()
        """Per-surface parametric coordinates associated with mesh nodes."""

    @property
    def surfaces(self) -> tuple[BaseSurfaceInterface, ...]:
        """Return surface definitions in their stable orientation order."""
        return tuple(self._surfaces)

    @property
    def element_name(self) -> str:
        """Return the generated finite-element family name."""
        return self._element_name

    @property
    def fea_seed_size(self) -> float | None:
        """Return the requested Gmsh volume mesh size."""
        return self._fea_seed_size

    @property
    def mesh_order(self) -> int:
        """Return the requested finite-element interpolation order."""
        return self._mesh_order

    def define_surfaces(self) -> None:
        """Register ordered surfaces through :meth:`add_surface`.

        Geometry task classes override this hook.  The first registered
        surface must be the external closed envelope.
        """
        return None

    def add_surface(self, surface: BaseSurfaceInterface) -> BaseSurfaceInterface:
        """Append one surface to the ordered boundary definition."""
        self._surfaces.append(surface)
        return surface

    def get_geometry_values(
        self,
    ) -> tuple[tuple[torch.Tensor, ...], tuple[torch.Tensor, ...], tuple[torch.Tensor, ...]]:
        """Return cached position and derivative values for every surface."""
        values = tuple(surface.get_geometry_values() for surface in self._surfaces)
        return (
            tuple(value[0] for value in values),
            tuple(value[1] for value in values),
            tuple(value[2] for value in values),
        )

    def get_control_points_list(self) -> tuple[torch.Tensor, ...]:
        """Return detached control-point tensors in surface order."""
        return tuple(
            surface.get_surface_parameters().detach().clone()
            for surface in self._surfaces
        )

    def get_points_weight(self) -> tuple[torch.Tensor, ...]:
        """Return cached integration weights in surface order."""
        return tuple(surface.get_points_weight() for surface in self._surfaces)

    def export_model(self, path: str | Path, format: str) -> Path:
        """Export every current boundary surface below one model directory."""
        directory = Path(path)
        if directory.suffix:
            directory = directory.parent / directory.stem
        directory.mkdir(parents=True, exist_ok=True)
        normalized_format = format.lower().lstrip(".")
        for index, surface in enumerate(self._surfaces):
            surface.export_surface(
                directory / f"surface_{index}", cast(SurfaceExportFormat, normalized_format)
            )
        return directory

    def build_part(
        self,
        path_result: Path | None = None,
        pools: Pool | None = None,
    ) -> None:
        """Export surfaces, mesh a volume and cache the imported TorchFEA Part."""
        del pools
        if not self._surfaces:
            raise RuntimeError(f"BoundaryPart {self._part_name!r} defines no surfaces")
        if self._mesh_order not in {1, 2}:
            raise ValueError("mesh_order must be one or two")
        directory = Path(path_result) if path_result is not None else Path.cwd()
        directory.mkdir(parents=True, exist_ok=True)
        export_format = self._select_export_format()
        surface_paths = tuple(
            surface.export_surface(
                directory / f"__surface-{index}", export_format
            )
            for index, surface in enumerate(self._surfaces)
        )
        builder = MeshBuilder(
            minimum_size=(0.5 * self._fea_seed_size if self._fea_seed_size else None),
            maximum_size=self._fea_seed_size,
            mesh_order=self._mesh_order,
        )
        try:
            builder.set_surface_paths(surface_paths)
            builder.build_volume()
            builder.build_mesh()
            inp_path = builder.export_inp(
                directory / f"{self._part_name}.inp", part_name=self._part_name
            )
        finally:
            builder.finalize()
        self._torchfea_Part = MeshBuilder.read_inp_part(inp_path, self._part_name)
        self._rename_element_families()
        if self._mesh_order == 2:
            self._convert_to_quadratic_elements()
        self._torchfea_Part.exterior_surface = self._exterior_surface
        self._register_surface_sets()
        self._match_surface_nodes()

    def get_parameters(self) -> torch.Tensor:
        """Return the flattened committed surface parameters without recomputation."""
        parameters = [
            surface.get_surface_parameters().reshape(-1)
            for surface in self._surfaces
            if surface.get_surface_parameters().numel()
        ]
        if not parameters:
            return torch.zeros(0, dtype=torch.float32)
        return torch.cat(parameters).detach().clone()

    def set_parameters(self, parameters: torch.Tensor) -> None:
        """Split flattened values and commit them to editable surfaces."""
        values = torch.as_tensor(parameters).detach().clone().reshape(-1)
        expected = sum(int(np.prod(shape)) for shape in self._control_point_shapes)
        if values.numel() != expected:
            raise ValueError(
                f"Part {self._part_name!r} expects {expected} parameters, got {values.numel()}"
            )
        offset = 0
        for surface, shape in zip(self._surfaces, self._control_point_shapes, strict=True):
            size = int(np.prod(shape))
            if size:
                surface.set_surface_parameters(values[offset : offset + size].reshape(shape))
                surface.update_geometry()
            offset += size

    def build_design_delta(self) -> None:
        """Create an all-zero local vector matching committed parameters."""
        self._design_delta = torch.zeros_like(self.get_parameters())

    def get_design_delta(self) -> torch.Tensor:
        """Return the already-built local trial vector."""
        return self._design_delta

    def set_design_delta(self, design_delta: torch.Tensor) -> None:
        """Store the registry-owned local trial vector."""
        self._design_delta = torch.as_tensor(design_delta)

    def update_assembly(self, design_delta: torch.Tensor) -> None:
        """Map a trial control-point delta onto cached Part nodes with autograd."""
        part = self.get_part()
        trial = self.get_parameters() + torch.as_tensor(design_delta).reshape(-1)
        offset = 0
        updated_nodes = part.nodes.clone()
        for surface, shape, node_index, node_parameters in zip(
            self._surfaces,
            self._control_point_shapes,
            self._surface_node_index,
            self._surface_node_parameters,
            strict=True,
        ):
            size = int(np.prod(shape))
            if size and node_index.size:
                surface.update_geometry(trial[offset : offset + size].reshape(shape))
                values = surface.map(torch.as_tensor(node_parameters, dtype=part.nodes.dtype))
                updated_nodes[torch.as_tensor(node_index, dtype=torch.long)] = values
            offset += size
        part.nodes = updated_nodes
        self._design_delta = torch.as_tensor(design_delta)

    def apply_design_delta(self, changes: torch.Tensor) -> None:
        """Commit a validated local update to every editable surface."""
        self.set_parameters(self.get_parameters() + torch.as_tensor(changes).reshape(-1))
        self._design_delta = torch.zeros_like(self.get_parameters())

    def initialize(self) -> None:
        """Create ordered surfaces and establish their geometry caches."""
        super().initialize()
        self._surfaces.clear()
        self.define_surfaces()
        if not self._surfaces:
            raise RuntimeError(f"BoundaryPart {self._part_name!r} defines no surfaces")
        shapes: list[torch.Size] = []
        for index, surface in enumerate(self._surfaces):
            surface._set_name(f"surface_{index}")
            surface._set_flip(index > 0)
            surface.initialize()
            shapes.append(surface.get_surface_parameters().shape)
        self._control_point_shapes = tuple(shapes)
        self.build_design_delta()

    def reinitialize(self, iteration: int) -> None:
        """Discard last mesh mappings and refresh committed surface caches."""
        super().reinitialize(iteration)
        self._surface_node_index = ()
        self._surface_node_parameters = ()
        for surface in self._surfaces:
            surface.reinitialize(iteration)

    def build_meshes(self) -> None:
        """Build current visualization meshes for every boundary surface."""
        meshes: list[pyvista.DataSet] = []
        for surface in self._surfaces:
            surface.build_meshes()
            meshes.extend(surface.get_meshes())
        self._meshes = tuple(meshes)

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist each surface's parameters and mesh-node parameter mapping."""
        folder = Path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
        for surface in self._surfaces:
            surface.save(folder, iteration)

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Restore each surface's persisted parameters and geometry cache."""
        folder = Path(folder_path)
        for surface in self._surfaces:
            surface.load(folder, iteration)

    def _select_export_format(self) -> str:
        """Return the common backend format supported by every surface."""
        supported = set(self._surfaces[0].get_export_formats())
        for surface in self._surfaces[1:]:
            supported.intersection_update(surface.get_export_formats())
        if not supported:
            raise ValueError("BoundaryPart surfaces need one common STP or STL format")
        return "stp" if "stp" in supported else "stl"

    def _rename_element_families(self) -> None:
        """Rename imported element families to the declared output name."""
        part = self.get_part()
        source_names = tuple(part.elems)
        if len(source_names) != 1:
            raise ValueError(
                f"Generated Part {self._part_name!r} has {len(source_names)} element families"
            )
        part.elems = {self._element_name: part.elems[source_names[0]]}

    def _convert_to_quadratic_elements(self) -> None:
        """Convert all generated linear families in one TorchFEA operation."""
        part = self.get_part()
        source_names = list(part.elems)
        target_names = [f"{name}_quadratic" for name in source_names]
        part.convert_linear_to_quadratic_elements(source_names, target_names)
        self._element_name = target_names[0]
        self._element_names = tuple(target_names)

    def _register_surface_sets(self) -> None:
        """Ensure a stable exterior surface set exists after INP import."""
        part = self.get_part()
        surface_names = [f"surface_{index}_all" for index in range(len(self._surfaces))]
        existing = set(part.surfaces.keys())
        source_sets = [name for name in surface_names if name in existing]
        if not source_sets:
            return
        combined: list[tuple[np.ndarray, int]] = []
        for surface_name in source_sets:
            combined.extend(part.surfaces[surface_name])
        if self._exterior_surface not in existing:
            part.add_surface_set(self._exterior_surface, combined)

    def _match_surface_nodes(self) -> None:
        """Associate every meshed node with its nearest ordered surface sample."""
        part = self.get_part()
        nodes = part.nodes.detach().cpu().numpy()
        samples = [
            surface.get_geometry_values()[0].detach().cpu().numpy()
            for surface in self._surfaces
        ]
        distance = np.stack(
            [
                np.square(nodes[:, None, :] - coordinates[None, :, :]).sum(axis=-1).min(axis=1)
                for coordinates in samples
            ],
            axis=1,
        )
        owners = distance.argmin(axis=1)
        node_indices: list[np.ndarray] = []
        node_parameters: list[np.ndarray] = []
        for index, surface in enumerate(self._surfaces):
            indices = np.flatnonzero(owners == index)
            parameters = surface.match_coordinates(indices, nodes[indices])
            node_indices.append(indices)
            node_parameters.append(parameters)
        self._surface_node_index = tuple(node_indices)
        self._surface_node_parameters = tuple(node_parameters)
