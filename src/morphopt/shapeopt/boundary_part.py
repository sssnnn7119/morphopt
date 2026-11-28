"""Boundary part: the shape-optimization Part described by surfaces.

This is the only part type that has the notion of *surfaces*: it owns an
ordered list of :mod:`~morphopt.shapeopt.surfaces` (index ``0`` = outer
boundary, ``1..n`` = cavities), exports them, meshes them into one volume Part,
and carries their design variables.  The geometry updater binds to this class.

```python
class Boundary(morphopt.BoundaryPart):
    def define_surfaces(self) -> None:
        exterior = self.BSP.initialize_cylinder(r0=8.0, length=80.0)
        exterior.add_constraint(exterior.mirror("xz"))
        self.add_surface_interface(exterior)

    def apply_surface_constraints(self) -> None:
        ...   # optional cross-surface extension; local constraints run first

class GeometryParams(morphopt.GeometryParams):
    def define_interface(self) -> None:
        self.add_interface(self.Boundary(fea_seed_size=1.0, mesh_order=1),
                           name="body")
```
"""

from __future__ import annotations

import os
import random
from collections import defaultdict
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import gmsh
import numpy as np
import pyvista as pv
import torch
import torchfea
from torchfea.cad import CADHistory
from torchfea.cad.builder import OCCBuilder

from ..constants import CONSTANT
from ..optcore.modelparams.parts import BasePart
from ..optcore.modelparams.parts.cad_part import CADMeshingMixin
from ..optcore.protocal import ProtocalUpdatable
from .surfaces import BaseSurface
from .surfaces.base_surface import SurfaceExportFormat

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

__all__ = ["BoundaryPart"]


class BoundaryPart(CADMeshingMixin, BasePart, ProtocalUpdatable):
    """One Part whose boundary is described by parameterised surfaces.

    Parameters
    ----------
    fea_seed_size:
        Target element size handed to the volume mesher.
    mesh_order:
        ``1`` keeps the linear mesh, ``2`` converts it to quadratic elements.
    part_name:
        Name of the Part inside the assembly.
    exterior_surface:
        Surface set drawn by default for mesh and deformation visualization
        (default ``surface_0_All``).
    """

    export_modes = ("all_surfaces",)
    is_variable = True
    from .surfaces import (
        BaseSurface,
        BREPSurface,
        ControlPointSurface,
        MeshSurface,
    )
    from .surfaces.bsp_surface import BspSurface as BSP
    from .surfaces.cpgeo_surface import (
        CPGEOSurface as CPGEO,
    )

    def __init__(
        self,
        fea_seed_size: float = CONSTANT.KERNEL.MESH.DEFAULT_BOUNDARY_SEED_SIZE,
        mesh_order: int = CONSTANT.KERNEL.MESH.DEFAULT_ELEMENT_ORDER,
        part_name: str | None = None,
        exterior_surface: str | None = "surface_0_All",
    ) -> None:
        """Initialize BoundaryPart and its configuration state.

        Args:
            fea_seed_size (float): Target finite-element edge length, independent of surface
                control-point sampling.
            mesh_order (int): Finite-element interpolation order: 1 for linear, 2 for quadratic
                elements.
            part_name (str | None): Registered Part name referenced by instances, loads, or material
                assignments.
            exterior_surface (str | None): Name assigned to the Part's exterior surface selection.
        """
        super().__init__(
            mesh_size=fea_seed_size,
            mesh_order=mesh_order,
            part_name=part_name,
            exterior_surface=exterior_surface,
        )

        self.surfaceinterfaces: list[BaseSurface] = []
        """Boundary surfaces; index 0 is the outer boundary, 1.. are cavities."""

        self._surfaces_defined = False
        """Whether :meth:`define_surfaces` has completed for this Part."""
        self._surface_groups: dict[str, list[int]] = {}

    # --------------------------------------------------------------- surfaces
    def define_surfaces(self) -> None:
        """Register this Part's boundary surfaces.

        Override and call :meth:`add_surface_interface` once per surface, in the order the surfaces
        should be indexed (``0`` = outer boundary, ``1..n`` = cavities).  It is called once by this
        Part's :meth:`initialize` method.  The surface factories (``BSP`` / ``CPGEO`` / ...) come
        with this class.
        """

    def add_surface_interface(self, surface: BaseSurface) -> BoundaryPart:
        """Register one boundary surface and return ``self`` (chainable).

        Call this from :meth:`define_surfaces`; for surfaces that only exist at runtime (the UI
        rebuilding a model) it may be called directly.

        Args:
            surface (BaseSurface): Surface interface to register, evaluate, or constrain.

        Returns:
            BoundaryPart: Register one boundary surface and return ``self`` (chainable).
        """
        surface._flip = bool(self.surfaceinterfaces)
        self.surfaceinterfaces.append(surface)
        self._surfaces_defined = True
        return self

    def surface_interfaces(self) -> list[BaseSurface]:
        """Return the boundary surfaces in registration order.

        Returns:
            list[BaseSurface]: The boundary surfaces in registration order.
        """
        return self.surfaceinterfaces

    @property
    def num_surface_interfaces(self) -> int:
        """Count registered outer and cavity boundary surfaces.

        Returns:
            int: Number of surface interfaces in registration order.
        """
        return len(self.surfaceinterfaces)

    def surface_interface(self, index: int) -> BaseSurface:
        """One boundary surface by index.

        Args:
            index (int): Zero-based position within the relevant collection.

        Returns:
            BaseSurface: One boundary surface by index.
        """
        return self.surfaceinterfaces[index]

    @property
    def surface_set_names(self) -> tuple[str, ...]:
        """Names known from geometry; no FE mesh or element indices are cached.

        Returns:
            tuple[str, ...]: Names known from geometry; no FE mesh or element indices are cached.
        """
        names = ["extern", self.exterior_surface or "extern"]
        names.extend(self._face_names.values())
        for index, surface in enumerate(self.surfaceinterfaces):
            names.append(f"surface_{index}_All")
            if isinstance(surface, self.BREPSurface):
                metadata = surface.metadata()
                names.extend(metadata["face_map"])
                names.extend(
                    f"surface_{index}_{name}"
                    for name in (*metadata["face_map"], *metadata["surface_sets"])
                )
        return tuple(dict.fromkeys(names))

    @property
    def node_set_names(self) -> tuple[str, ...]:
        """Describe geometric selections; their node indices depend on the mesh.

        Returns:
            tuple[str, ...]: Describe geometric selections; their node indices depend on the mesh.
        """
        names = ["all", "surface_all"]
        names.extend(f"{name}_nodes" for name in self._face_names.values())
        for index, surface in enumerate(self.surfaceinterfaces):
            prefix = f"surface_{index}"
            names.append(f"{prefix}_All")
            if isinstance(surface, self.BREPSurface):
                metadata = surface.metadata()
                names.extend(f"{name}_nodes" for name in metadata["face_map"])
                names.extend(
                    f"{prefix}_{name}_nodes"
                    for name in (*metadata["face_map"], *metadata["surface_sets"])
                )
                names.extend(
                    f"{prefix}_{name}"
                    for name in (
                        *metadata["edge_map"],
                        *metadata["vertex_map"],
                        *metadata["node_sets"],
                    )
                )
            names.extend(f"{prefix}_{name}" for name in surface.end_node_set_names)
        return tuple(dict.fromkeys(names))

    @property
    def num_variables(self) -> int:
        """Total number of scalar design variables of all surfaces.

        Returns:
            int: Number of scalar coordinates in this interface's active design vector.
        """
        return sum(surface.num_variables for surface in self.surfaceinterfaces)

    # -------------------------------------------------------------- lifecycle
    def initialize(self, *args: object, **kwargs: object) -> None:
        """Declare and initialize every boundary surface once.

        Args:
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """
        super().initialize(*args, **kwargs)
        if not self._surfaces_defined:
            self.define_surfaces()
            self._surfaces_defined = True
        for index, surface in enumerate(self.surfaceinterfaces):
            surface._flip = index != 0
            surface.initialize(*args, **kwargs)
        self._reinitialize_constraints()
        self._apply_surface_constraints()

    def reinitialize(self, iteration: int, *args: object, **kwargs: object) -> None:
        """Re-initialize every boundary surface (reconstruction / refinement).

        Args:
            iteration (int): Iteration index associated with the saved or current model state.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """
        for index, surface in enumerate(self.surfaceinterfaces):
            surface._flip = index != 0
            surface.reinitialize(iteration, *args, **kwargs)
        self._reinitialize_constraints()
        self._apply_surface_constraints()

    def _reinitialize_constraints(self) -> None:
        """Reinitialize constraints."""
        for surface in self.surfaceinterfaces:
            surface.reinitialize_constraints()

    def _apply_surface_constraints(self) -> None:
        """Apply surface constraints."""
        for surface in self.surfaceinterfaces:
            surface.apply_constraints()
        self.apply_surface_constraints()

    def apply_surface_constraints(self) -> None:
        """Optional Part-level hook after surface constraints have run."""

    # ---------------------------------------------------------------- meshing
    @property
    def fea_seed_size(self) -> float:
        """Boundary terminology for the shared CADPart mesh size.

        Returns:
            float: Boundary terminology for the shared CADPart mesh size.
        """
        return self.mesh_size

    @fea_seed_size.setter
    def fea_seed_size(self, value: float) -> None:
        """Set the target finite-element edge length in model length units.

        Args:
            value (float): New target finite-element edge length in model length units.
        """
        self.mesh_size = float(value)

    def prepare_geometry(
        self,
        path_result: str | None = None,
        pools: Pool | None = None,
    ) -> list[BaseSurface]:
        """Provide closed CAD shells or exported parametric/discrete boundaries.

        Args:
            path_result (str | None): Optimization result directory containing scripts and log
                subdirectories.
            pools (Pool | None): Optional multiprocessing pool for geometry preparation or export.

        Returns:
            list[BaseSurface]: Geometry description consumed by the Part's assembly stage.
        """
        self._face_names.clear()
        directory = self.workdir(path_result)
        for index, surface in enumerate(self.surfaceinterfaces):
            surface.synchronize()
            surface.prepare_geometry(
                path_output=directory,
                name_output=f"__surface-{index}",
                pools=pools,
            )
        return list(self.surfaceinterfaces)

    def assemble_geometry(self, geometry: list[BaseSurface]) -> CADHistory:
        """Declare this Part's exterior/cavity assembly operation.

        Args:
            geometry (list[BaseSurface]): Geometry description or geometry collection processed by
                this interface.

        Returns:
            CADHistory: CAD history describing the final volume to mesh.
        """
        self._surface_groups.clear()
        action = partial(self._assemble_surfaces, surfaces=geometry)
        return CADHistory(
            operations=[self._Operation("boundary", action)],
            mesh_size=self.mesh_size
            * random.uniform(*CONSTANT.KERNEL.MESH.BOUNDARY_SEED_SIZE_VARIATION),
        )

    def _assemble_surfaces(
        self,
        context: OCCBuilder,
        *,
        surfaces: list[BaseSurface],
    ) -> list[tuple[int, int]]:
        """Load closed boundaries and assemble one volume with optional cavities.

        Args:
            context (OCCBuilder): Active Gmsh/OCC builder owned by the caller's serialized geometry
                session.
            surfaces (list[BaseSurface]): Surface interfaces in boundary registration order:
                exterior first, followed by cavities.

        Returns:
            list[tuple[int, int]]: Gmsh dimension/tag pairs identifying the assembled volume after
                cavity construction.
        """
        if not surfaces:
            raise ValueError("A BoundaryPart requires an exterior surface.")
        groups = [surface.load_geometry(self, context) for surface in surfaces]
        kernel = (
            gmsh.model.geo
            if any(surface.is_discrete for surface in surfaces)
            else context.occ
        )
        loops = [kernel.addSurfaceLoop(tags) for tags in groups]
        volume = kernel.addVolume(loops)
        kernel.synchronize()
        used = {tag for tags in groups for tag in tags}
        unused = [
            entity for entity in gmsh.model.getEntities(2) if entity[1] not in used
        ]
        if unused:
            context.occ.remove(unused, recursive=True)
            context.occ.synchronize()
        boundary = {
            tag
            for _, tag in gmsh.model.getBoundary(
                [(3, volume)],
                oriented=False,
                recursive=False,
            )
        }
        if boundary != used:
            raise ValueError("Boundary assembly changed the input face topology.")
        self._surface_groups.update(
            {f"surface_{index}_All": tags for index, tags in enumerate(groups)}
        )
        return [(3, volume)]

    def define_mesh_sets(self, part: torchfea.Part) -> None:
        """Extend geometric face sets with this Part's closed-surface groups.

        Args:
            part (torchfea.Part): Part whose geometry, mesh, or named sets are processed.
        """
        super().define_mesh_sets(part)
        for name, tags in self._surface_groups.items():
            sides = defaultdict(list)
            nodes = []
            for tag in tags:
                face = self._face_names[tag]
                for element_ids, side in part.surfaces[face]:
                    sides[side].append(element_ids)
                nodes.append(part.set_nodes[f"{face}_nodes"])
            part.add_surface_set(
                name,
                [(np.unique(np.concatenate(ids)), side) for side, ids in sides.items()],
            )
            part.add_node_set(name, np.unique(np.concatenate(nodes)))
        for index, surface in enumerate(self.surfaceinterfaces):
            surface.define_mesh_sets(part, f"surface_{index}")
        exterior = self.exterior_surface or "extern"
        if exterior not in part.surfaces:
            part.add_surface_set(exterior, part.surfaces["extern"])
        part.exterior_surface = exterior

    def postprocess_mesh(self, part: torchfea.Part) -> torchfea.Part:
        """Map designable boundary nodes before element and order processing.

        Args:
            part (torchfea.Part): Part whose geometry, mesh, or named sets are processed.

        Returns:
            torchfea.Part: Map designable boundary nodes before element and order processing.
        """
        nodes = part.nodes.detach().cpu().numpy()
        for index, surface in enumerate(self.surfaceinterfaces):
            prefix = f"surface_{index}"
            indices = np.sort(part.set_nodes[f"{prefix}_All"])
            positions = nodes[indices]
            node_uv = None
            if surface.num_variables and not surface.uses_facewise_binding:
                surface.match_coordinates(indices, positions)
                if np.array_equal(surface.surf_node_idx, indices):
                    node_uv = surface.surf_node_uv
                parameters = torch.as_tensor(
                    surface.surf_node_uv, device=part.nodes.device, dtype=part.nodes.dtype
                )
                part.nodes[surface.surf_node_idx] = surface.map(parameters)
                positions = part.nodes[indices].detach().cpu().numpy()
            for name, local in surface.get_node_sets(positions, node_uv=node_uv).items():
                part.add_node_set(f"{prefix}_{name}", indices[local])
        part = super().postprocess_mesh(part)
        for surface in self.surfaceinterfaces:
            surface.bind_mesh(part)
        return part

    def export(
        self, directory: Path, *, mode: str = "all_surfaces",
        surface_formats: Sequence[str] | None = None,
    ) -> None:
        """Write every boundary in registration order.

        Args:
            directory: Destination for surface_0, surface_1, and subsequent files.
            mode: `all_surfaces` uses native defaults. `all_surfaces_step` prefers STEP.
            surface_formats: One file extension per surface, in registration order.
                Explicit selections take precedence over the mode's defaults.
        """
        if mode not in ("all_surfaces", "all_surfaces_step"):
            return super().export(directory, mode=mode)
        if surface_formats is not None and len(surface_formats) != len(self.surfaceinterfaces):
            raise ValueError("Select one format for each boundary surface.")
        directory.mkdir(parents=True, exist_ok=True)
        for index, surface in enumerate(self.surfaceinterfaces):
            formats = surface.export_formats
            if not formats:
                raise ValueError(
                    f"surface_{index} ({type(surface).__name__}) has no export format."
                )
            if surface_formats is not None:
                fmt = surface_formats[index]
            elif mode == "all_surfaces_step" and SurfaceExportFormat.STEP in formats:
                fmt = SurfaceExportFormat.STEP
            else:
                fmt = formats[0]
            surface.write_surface(directory / f"surface_{index}", fmt)

    # -------------------------------------------------------- design variables
    def get_parameters(self) -> list[torch.Tensor]:
        """Control points of every surface, in surface order.

        Returns:
            list[torch.Tensor]: Parameter tensors in the interface's design-variable block order.
        """
        return [
            surface.get_surface_parameters().flatten().detach().clone()
            for surface in self.surfaceinterfaces
        ]

    def set_parameters(self, values: list[torch.Tensor]) -> None:
        """Restore the control points of every surface.

        Args:
            values (list[torch.Tensor]): Values aligned with the parameters or records processed by
                this interface.
        """
        if len(values) != self.num_surface_interfaces:
            raise ValueError("Surface parameter list does not match surfaces.")
        for surface, value in zip(self.surfaceinterfaces, values):
            surface.set_surface_parameters(value.detach().clone())
        self._apply_surface_constraints()

    def update_variables(
        self,
        x_change: torch.Tensor,
        max_step_length: list[torch.Tensor],
    ) -> None:
        """Apply the updater's per-control-point limits through ``atan``.

        The updater supplies one step-length tensor per surface and owns its initialization,
        resizing and adaptation.

        Args:
            x_change (torch.Tensor): Design-variable increment in this interface's flattened
                parameter order.
            max_step_length (list[torch.Tensor]): Updater-owned movement limits in the target's
                parameter-block order.
        """
        x_change = x_change.reshape(-1)
        start = 0
        for surface, step in zip(self.surfaceinterfaces, max_step_length, strict=True):
            size = surface.num_variables
            if not size:
                continue
            delta = x_change[start : start + size].reshape(-1, 3)
            start += size
            if not surface.is_updatable:
                continue
            # atan(r)/r has limit 1 at r=0. Its Taylor branch gives the
            # correct nonzero Jacobian without a random initial perturbation.
            squared_norm = delta.square().sum(dim=1, keepdim=True)
            epsilon = CONSTANT.KERNEL.BOUNDARY_PART.UPDATE_STEP_EPSILON
            safe_norm = squared_norm.clamp_min(epsilon).sqrt()
            factor = torch.where(
                squared_norm > epsilon,
                torch.atan(safe_norm) / safe_norm,
                1 - squared_norm / 3,
            )
            change = (2 / torch.pi) * factor * delta
            change = change * step.reshape(-1, 1)
            surface.update_variables(change)

        self._apply_surface_constraints()

    def get_geometry_values(
        self,
    ) -> tuple[list[torch.Tensor], list[torch.Tensor], list[torch.Tensor]]:
        """``(r, rdu, rdu2)`` evaluated on every surface.

        Returns:
            tuple[list[torch.Tensor], list[torch.Tensor], list[torch.Tensor]]: Per-surface positions
                (n_i, 3), first derivatives (n_i, 3, 2), and second derivatives (n_i, 3, 2, 2), in
                surface registration order.
        """
        values = [surface.get_geometry_values() for surface in self.surfaceinterfaces]
        return (
            [value[0] for value in values],
            [value[1] for value in values],
            [value[2] for value in values],
        )

    def get_control_points_list(self) -> list[torch.Tensor]:
        """Detached control points of every surface.

        Returns:
            list[torch.Tensor]: Detached control points of every surface.
        """
        return [
            surface.control_points.detach().clone()
            if surface.num_variables
            else torch.empty((0, 3))
            for surface in self.surfaceinterfaces
        ]

    def get_points_weight(self) -> list[torch.Tensor]:
        """Integration weights of every surface.

        Returns:
            list[torch.Tensor]: Area integration weights aligned with the surface sampling points.
        """
        return [surface.get_points_weight() for surface in self.surfaceinterfaces]

    # ----------------------------------------------------- adjoint sensitivity
    def obtain_design_sensitivity_vars(
        self, assembly: torchfea.Assembly
    ) -> torch.Tensor:
        """Concatenate the control points of every surface.

        Args:
            assembly (torchfea.Assembly): TorchFEA assembly containing the registered Parts,
                Instances, loads, and reference points.

        Returns:
            torch.Tensor: Concatenate the control points of every surface.
        """
        values = [
            surface.get_surface_parameters().flatten()
            for surface in self.surfaceinterfaces
            if surface.num_variables
        ]
        return torch.cat(values, dim=0).detach() if values else torch.zeros(0)

    def modify_assembly(
        self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly
    ) -> None:
        """Map the design variables onto the mesh nodes of this Part.

        Args:
            design_sensitivity_vars (torch.Tensor): Differentiable design-variable tensor used to
                modify the assembly.
            assembly (torchfea.Assembly): TorchFEA assembly containing the registered Parts,
                Instances, loads, and reference points.
        """
        part = assembly.get_part(self.part_name)
        nodes_new = part.nodes.clone()

        values = torch.as_tensor(design_sensitivity_vars).reshape(-1)
        offset = 0
        facewise: list[BaseSurface] = []
        for surface in self.surfaceinterfaces:
            size = surface.num_variables
            if not size:
                continue
            parameters = values[offset : offset + size]
            offset += size
            if not surface.is_updatable:
                continue
            surface.set_surface_parameters(parameters)
            indices, node_update = surface.map_design_nodes()
            nodes_new[indices] = node_update
            if surface.uses_facewise_binding:
                facewise.append(surface)

        if self.mesh_order == 2:
            nodes_new[part.mid_pt_idxmap_torch[:, 2]] = (
                nodes_new[part.mid_pt_idxmap_torch[:, 0]]
                + nodes_new[part.mid_pt_idxmap_torch[:, 1]]
            ) / 2

        for surface in facewise:
            indices, node_update = surface.map_design_nodes()
            nodes_new[indices] = node_update

        part.nodes = nodes_new

    # ---------------------------------------------------------------- io/plot
    def save(self, foldpath: str, iteration: int) -> None:
        """Save every designable surface under this Part's geometry folder.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        dirpath = self.save_directory(foldpath, self.name or "geometry")
        for index, surface in enumerate(self.surfaceinterfaces):
            if not surface.num_variables:
                continue
            surface.save(
                os.path.join(dirpath, "Surface-%d_iter-%d" % (index, iteration))
            )

    def load(self, foldpath: str, iteration: int) -> None:
        """Load every designable surface saved for this Part.

        Args:
            foldpath (str): Root log directory containing this component's namespaced state files.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        dirpath = self.save_directory(foldpath, self.name or "geometry")
        for index, surface in enumerate(self.surfaceinterfaces):
            if not surface.num_variables:
                continue
            path = os.path.join(dirpath, "Surface-%d_iter-%d" % (index, iteration))
            # Surface implementations append their own storage suffix when
            # saving (BSP/CPGEO currently write ``.npz``).  The public load
            # method receives the same stem that was passed to ``save``.
            if os.path.isfile(path) or os.path.isfile(path + ".npz"):
                surface.load(path)

    def get_meshes(self) -> list[pv.PolyData]:
        """Visualisation mesh of every surface.

        Returns:
            list[pv.PolyData]: Visualization meshes in component registration order.
        """
        return [surface.get_mesh() for surface in self.surfaceinterfaces]

    @staticmethod
    def _default_opacity(index: int) -> float:
        """Default surface opacity: the outer boundary is semi-transparent.

        Args:
            index (int): Zero-based position within the relevant collection.

        Returns:
            float: Default surface opacity: the outer boundary is semi-transparent.
        """
        return (
            CONSTANT.KERNEL.VISUALIZATION.BOUNDARY_OUTER_SURFACE_OPACITY
            if index == 0
            else 1.0
        )

    def plot(
        self,
        plotter: pv.Plotter | None = None,
        meshes: Sequence[pv.DataSet] | None = None,
        opacity: list[float] | None = None,
    ) -> pv.Plotter:
        """Plot every boundary surface of this Part.

        Args:
            plotter (pv.Plotter | None): PyVista plotter receiving the scene; None creates a new
                plotter.
            meshes (Sequence[pv.DataSet] | None): Optional precomputed visualization meshes; None
                obtains meshes from the model.
            opacity (list[float] | None): Surface opacities in boundary registration order; None
                uses the visualization defaults.

        Returns:
            pv.Plotter: Plotter populated with the Part's boundary surfaces and optional control
                nets.
        """
        if plotter is None:
            plotter = pv.Plotter()
        if opacity is None:
            opacity = [
                self._default_opacity(index)
                for index in range(self.num_surface_interfaces)
            ]
        if meshes is None:
            meshes = self.get_meshes()

        for index, mesh in enumerate(meshes):
            plotter.add_mesh(
                mesh,
                name=f"boundary:{id(self)}:surface-{index}",
                opacity=opacity[index] if index < len(opacity) else 1.0,
                color=(40.0 / 255, 120.0 / 255, 181.0 / 255),
                diffuse=CONSTANT.KERNEL.VISUALIZATION.BOUNDARY_DIFFUSE,
                specular=CONSTANT.KERNEL.VISUALIZATION.BOUNDARY_SPECULAR,
                ambient=CONSTANT.KERNEL.VISUALIZATION.BOUNDARY_AMBIENT,
                specular_power=CONSTANT.KERNEL.VISUALIZATION.BOUNDARY_SPECULAR_POWER,
                smooth_shading=True,
                show_edges=False,
            )
        return plotter
