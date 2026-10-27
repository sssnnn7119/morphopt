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
from collections import defaultdict
from collections.abc import Sequence
from functools import partial
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

        Override and call :meth:`add_surface_interface` once per surface, in
        the order the surfaces should be indexed (``0`` = outer boundary,
        ``1..n`` = cavities).  It is called once by this Part's
        :meth:`initialize` method.  The surface factories (``BSP`` / ``CPGEO``
        / ...) come with this class.
        """

    def add_surface_interface(self, surface: BaseSurface) -> BoundaryPart:
        """Register one boundary surface and return ``self`` (chainable).

        Call this from :meth:`define_surfaces`; for surfaces that only exist at
        runtime (the UI rebuilding a model) it may be called directly.
        """
        self.surfaceinterfaces.append(surface)
        self._surfaces_defined = True
        return self

    def surface_interfaces(self) -> list[BaseSurface]:
        """Return the boundary surfaces in registration order."""
        return self.surfaceinterfaces

    @property
    def num_surface_interfaces(self) -> int:
        return len(self.surfaceinterfaces)

    def surface_interface(self, index: int) -> BaseSurface:
        """One boundary surface by index."""
        return self.surfaceinterfaces[index]

    @property
    def surface_set_names(self) -> tuple[str, ...]:
        """Names known from geometry; no FE mesh or element indices are cached."""
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
        """Describe geometric selections; their node indices depend on the mesh."""
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
                    for name in (*metadata["edge_map"], *metadata["vertex_map"], *metadata["node_sets"])
                )
            elif index == 0 and isinstance(surface, self.BSP):
                names.extend((f"{prefix}_Bottom", f"{prefix}_Head"))
        return tuple(dict.fromkeys(names))

    @property
    def num_variables(self) -> int:
        """Total number of scalar design variables of all surfaces."""
        return sum(surface.num_variables for surface in self.surfaceinterfaces)

    # -------------------------------------------------------------- lifecycle
    def initialize(self, *args: object, **kwargs: object) -> None:
        """Declare and initialize every boundary surface once."""
        super().initialize(*args, **kwargs)
        if not self._surfaces_defined:
            self.define_surfaces()
            self._surfaces_defined = True
        for surface in self.surfaceinterfaces:
            surface.initialize(*args, **kwargs)
        self._reinitialize_constraints()
        self._apply_surface_constraints()

    def reinitialize(self, iteration: int, *args: object, **kwargs: object) -> None:
        """Re-initialize every boundary surface (reconstruction / refinement)."""
        for surface in self.surfaceinterfaces:
            surface.reinitialize(iteration, *args, **kwargs)
        self._reinitialize_constraints()
        self._apply_surface_constraints()

    def _reinitialize_constraints(self) -> None:
        for surface in self.surfaceinterfaces:
            surface.reinitialize_constraints()

    def _apply_surface_constraints(self) -> None:
        for surface in self.surfaceinterfaces:
            surface.apply_constraints()
        self.apply_surface_constraints()

    def apply_surface_constraints(self) -> None:
        """Optional Part-level hook after surface constraints have run."""

    # ---------------------------------------------------------------- meshing
    @property
    def fea_seed_size(self) -> float:
        """Boundary terminology for the shared CADPart mesh size."""
        return self.mesh_size

    @fea_seed_size.setter
    def fea_seed_size(self, value: float) -> None:
        self.mesh_size = float(value)

    def prepare_geometry(
        self,
        path_result: str | None = None,
        pools: Pool | None = None,
    ) -> list[BaseSurface]:
        """Provide closed CAD shells or exported parametric/discrete boundaries."""
        self._face_names.clear()
        directory = self.workdir(path_result)
        for index, surface in enumerate(self.surfaceinterfaces):
            surface.synchronize()
            surface.prepare_geometry(
                path_output=directory,
                name_output=f"__surface-{index}",
                flip=index != 0,
                pools=pools,
            )
        return list(self.surfaceinterfaces)

    def assemble_geometry(self, geometry: list[BaseSurface]) -> CADHistory:
        """Declare this Part's exterior/cavity assembly operation."""
        self._surface_groups.clear()
        action = partial(self._assemble_surfaces, surfaces=geometry)
        return CADHistory(
            operations=[self._Operation("boundary", action)],
            mesh_size=self.mesh_size,
        )

    def _assemble_surfaces(
        self,
        context: OCCBuilder,
        *,
        surfaces: list[BaseSurface],
    ) -> list[tuple[int, int]]:
        """Load closed boundaries and assemble one volume with optional cavities."""
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
        """Extend geometric face sets with this Part's closed-surface groups."""
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
        """Map designable boundary nodes before element and order processing."""
        nodes = part.nodes.detach().cpu().numpy()
        outer_nodes = part.set_nodes["surface_0_All"]
        for name, indices in self.surfaceinterfaces[0].get_node_sets(nodes[outer_nodes]).items():
            part.add_node_set(f"surface_0_{name}", outer_nodes[indices])
        for index, surface in enumerate(self.surfaceinterfaces):
            if not surface.num_variables or surface.uses_facewise_binding:
                continue
            indices = np.sort(part.set_nodes[f"surface_{index}_All"])
            surface.match_coordinates(indices, nodes[indices])
            uv = torch.as_tensor(
                surface.surf_node_uv,
                device=part.nodes.device,
                dtype=part.nodes.dtype,
            )
            part.nodes[surface.surf_node_idx] = surface.map(uv)
        part = super().postprocess_mesh(part)
        for surface in self.surfaceinterfaces:
            surface.bind_mesh(part)
        return part

    def export_data(self, dirpath: str, pools: Pool | None = None) -> None:
        """Export every surface to ``__surface-<index>.stp|stl``."""
        os.makedirs(dirpath, exist_ok=True)
        for index, surface in enumerate(self.surfaceinterfaces):
            surface.output_data(
                path_output=dirpath,
                name_output="__surface-%d" % index,
                flip=(index != 0),
                pools=pools,
            )

    # -------------------------------------------------------- design variables
    def get_parameters(self) -> list[torch.Tensor]:
        """Control points of every surface, in surface order."""
        return [
            surface.get_surface_parameters().flatten().detach().clone()
            for surface in self.surfaceinterfaces
        ]

    def set_parameters(self, values: list[torch.Tensor]) -> None:
        """Restore the control points of every surface."""
        if len(values) != self.num_surface_interfaces:
            raise ValueError("Surface parameter list does not match surfaces.")
        for surface, value in zip(self.surfaceinterfaces, values):
            surface.set_surface_parameters(value.detach().clone())
        self.apply_surface_constraints()

    def update_variables(
        self,
        x_change: torch.Tensor,
        max_step_length: list[torch.Tensor | None] | None = None,
    ) -> None:
        """Apply one shape update with the ``atan`` step-length limiter.

        ``max_step_length`` is ``None`` (no limiting) or **one tensor per
        surface**, holding the step length of each control point (that is the
        form :class:`~morphopt.UpdaterBoundaryPart` keeps per iteration).
        """
        x_change = torch.as_tensor(x_change).reshape(-1)
        surfaces = self.surfaceinterfaces
        steps = self._surface_step_lengths(max_step_length, surfaces)

        start = 0
        for surface, step in zip(surfaces, steps):
            size = surface.num_variables
            if not size:
                continue
            delta = x_change[start : start + size].reshape(-1, 3)
            start += size
            if not surface.is_updatable:
                continue
            norm = delta.norm(dim=1, keepdim=True)
            change = (
                2
                / torch.pi
                * torch.atan(norm)
                * delta
                / (norm + CONSTANT.KERNEL.BOUNDARY_PART.UPDATE_STEP_EPSILON)
            )
            if step is not None:
                change = change * step
            surface.update_variables(change)

        self.apply_surface_constraints()

    @staticmethod
    def _surface_step_lengths(
        max_step_length: list[torch.Tensor | None] | None,
        surfaces: Sequence[BaseSurface],
    ) -> list[torch.Tensor | None]:
        """One ``[num_points, 1]`` step-length column per surface (or ``None``)."""
        if max_step_length is None:
            return [None] * len(surfaces)
        if isinstance(max_step_length, torch.Tensor):
            raise TypeError(
                "max_step_length must be one tensor per surface (per control "
                "point), not a single tensor."
            )
        steps = list(max_step_length)
        if len(steps) != len(surfaces):
            raise ValueError(
                f"Expected {len(surfaces)} per-surface step lengths, got {len(steps)}."
            )
        normalised: list[torch.Tensor | None] = []
        for surface, step in zip(surfaces, steps):
            if step is None:
                normalised.append(None)
                continue
            column = torch.as_tensor(step).reshape(-1, 1)
            num_points = surface.num_variables // 3
            if column.shape[0] != num_points:
                # the surface changed size since the step length was built
                column = column.mean().repeat(num_points, 1)
            normalised.append(column)
        return normalised

    def get_geometry_values(
        self,
    ) -> tuple[list[torch.Tensor], list[torch.Tensor], list[torch.Tensor]]:
        """``(r, rdu, rdu2)`` evaluated on every surface."""
        values = [surface.get_geometry_values() for surface in self.surfaceinterfaces]
        return (
            [value[0] for value in values],
            [value[1] for value in values],
            [value[2] for value in values],
        )

    def get_control_points_list(self) -> list[torch.Tensor]:
        """Detached control points of every surface."""
        return [
            surface.control_points.detach().clone()
            if surface.num_variables
            else torch.empty((0, 3))
            for surface in self.surfaceinterfaces
        ]

    def get_penalty_fairness(
        self,
        weight: list[torch.Tensor],
        r: list[torch.Tensor],
        rdu: list[torch.Tensor],
        rdu2: list[torch.Tensor],
    ) -> list[torch.Tensor]:
        """Fairness penalty of every surface."""
        return [
            surface.get_penalty_fairness(
                weight[index], r[index], rdu[index], rdu2[index]
            )
            for index, surface in enumerate(self.surfaceinterfaces)
        ]

    def get_points_weight(self) -> list[torch.Tensor]:
        """Integration weights of every surface."""
        return [surface.get_points_weight() for surface in self.surfaceinterfaces]

    # ----------------------------------------------------- adjoint sensitivity
    def obtain_design_sensitivity_vars(
        self, assembly: torchfea.Assembly
    ) -> torch.Tensor:
        """Concatenate the control points of every surface."""
        values = [
            surface.get_surface_parameters().flatten()
            for surface in self.surfaceinterfaces
            if surface.num_variables
        ]
        return torch.cat(values, dim=0).detach() if values else torch.zeros(0)

    def modify_assembly(
        self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly
    ) -> None:
        """Map the design variables onto the mesh nodes of this Part."""
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
        """Save every designable surface under this Part's geometry folder."""
        dirpath = self.save_directory(foldpath, self.name or "geometry")
        for index, surface in enumerate(self.surfaceinterfaces):
            if not surface.num_variables:
                continue
            surface.save(
                os.path.join(dirpath, "Surface-%d_iter-%d" % (index, iteration))
            )

    def load(self, foldpath: str, iteration: int) -> None:
        """Load every designable surface saved for this Part."""
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
        """Visualisation mesh of every surface."""
        return [surface.get_mesh() for surface in self.surfaceinterfaces]

    @staticmethod
    def _default_opacity(index: int) -> float:
        """Default surface opacity: the outer boundary is semi-transparent."""
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
        """Plot every boundary surface of this Part."""
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
