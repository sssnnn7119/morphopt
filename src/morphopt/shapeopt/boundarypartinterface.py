"""Boundary part interface: the shape-optimization Part described by surfaces.

This is the only part interface that has the notion of *surfaces*: it owns an
ordered list of :mod:`~morphopt.shapeopt.surfaceinterfaces` (index ``0`` = outer
boundary, ``1..n`` = cavities), exports them, meshes them into one volume Part,
and carries their design variables.  The geometry updater binds to this class.

```python
class Boundary(morphopt.BoundaryPartInterface):
    def define_surfaces(self) -> None:
        self.add_surface_interface(self.BSP.initialize_cylinder(r0=8.0, length=80.0))

    def apply_surface_constraints(self) -> None:
        ...   # equality constraints on self.surface_interfaces()[...]

class GeometryParams(morphopt.GeometryParams):
    def define_interface(self) -> None:
        self.add_interface(self.Boundary(fea_seed_size=1.0, mesh_order=1),
                           name="body")
```
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np
import pyvista as pv
import torch
import torchfea

from ..optcore.modelparams.partinterface import BasePartInterface
from ..optcore.protocal import ProtocalUpdatable
from .meshgenerator import MeshGenerator
from .surfaceinterfaces import (
    BaseSurfaceInterface,
)

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

__all__ = ["BoundaryPartInterface"]


class BoundaryPartInterface(BasePartInterface, ProtocalUpdatable):
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
        Surface set used as the Part exterior surface (default ``surface_0_All``).
    """

    from .surfaceinterfaces import (
        BaseSurfaceInterface,
        CpBasedSurfaceInterface,
        FixedSurface,
    )
    from .surfaceinterfaces.bspsurfaceinterface import BspSurfaceInterface as BSP
    from .surfaceinterfaces.cpgeosurfaceinterface import (
        CPGEOSurfaceInterface as CPGEO,
    )

    def __init__(
        self,
        fea_seed_size: float = 1.0,
        mesh_order: int = 1,
        part_name: str | None = None,
        exterior_surface: str | None = "surface_0_All",
    ) -> None:
        super().__init__(
            part_name=part_name,
            exterior_surface=exterior_surface,
        )

        self.fea_seed_size: float = float(fea_seed_size)
        """Target element size handed to the volume mesher."""

        self.mesh_order: int = int(mesh_order)
        """Mesh order used for the finite element model (1 or 2)."""

        self.surfaceinterfaces: list[BaseSurfaceInterface] = []
        """Boundary surfaces; index 0 is the outer boundary, 1.. are cavities."""

        self._surfaces_defined = False
        """Whether :meth:`define_surfaces` has completed for this Part."""

    # --------------------------------------------------------------- surfaces
    def define_surfaces(self) -> None:
        """Register this Part's boundary surfaces.

        Override and call :meth:`add_surface_interface` once per surface, in
        the order the surfaces should be indexed (``0`` = outer boundary,
        ``1..n`` = cavities).  It is called once by this Part's
        :meth:`initialize` method.  The surface factories (``BSP`` / ``CPGEO``
        / ...) come with this class.
        """

    def add_surface_interface(
        self, surface: BaseSurfaceInterface
    ) -> BoundaryPartInterface:
        """Register one boundary surface and return ``self`` (chainable).

        Call this from :meth:`define_surfaces`; for surfaces that only exist at
        runtime (the UI rebuilding a model) it may be called directly.
        """
        self.surfaceinterfaces.append(surface)
        self._surfaces_defined = True
        return self

    def surface_interfaces(self) -> list[BaseSurfaceInterface]:
        """Return the boundary surfaces in registration order."""
        return self.surfaceinterfaces

    @property
    def num_surface_interfaces(self) -> int:
        return len(self.surfaceinterfaces)

    def surface_interface(self, index: int) -> BaseSurfaceInterface:
        """One boundary surface by index."""
        return self.surfaceinterfaces[index]

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

    def reinitialize(self, iteration: int, *args: object, **kwargs: object) -> None:
        """Re-initialize every boundary surface (reconstruction / refinement)."""
        for surface in self.surfaceinterfaces:
            surface.reinitialize(iteration, *args, **kwargs)
        self.apply_surface_constraints()

    def apply_surface_constraints(self) -> None:
        """Hook applied after every design update (equality constraints)."""

    # ---------------------------------------------------------------- meshing
    def build_part(
        self, path_result: str | None = None, pools: Pool | None = None
    ) -> torchfea.Part:
        """Regenerate the volume mesh of this Part from its surfaces."""
        part = self._mesh_part(path_result=path_result, pools=pools)
        part = self._postprocess_part(part)
        if self.mesh_order == 2:
            part.convert_linear_to_quadratic_elements(
                list(part.elems.keys()), list(part.elems.keys())
            )
        return part

    def _postprocess_part(self, part: torchfea.Part) -> torchfea.Part:
        """Hook to add element families to the freshly meshed Part."""
        return part

    def _mesh_part(
        self, path_result: str | None = None, pools: Pool | None = None
    ) -> torchfea.Part:
        """Export the surfaces, run Gmsh, and map them onto the mesh nodes."""
        path_output = self.workdir(path_result)

        # synchronize the surfaces so their exported files are up to date
        for surface in self.surfaceinterfaces:
            surface.synchronize()

        self.export_data(path_output)

        # mesh the exported surfaces into an Abaqus part
        inp_path = os.path.join(path_output, "TopOptRun.inp")
        if os.path.exists(inp_path):
            os.remove(inp_path)

        if pools is None:
            pools_now = mp.Pool(1)
        else:
            pools_now = pools

        pool_owned = pools is None
        try:
            try:
                if sys.platform.startswith("win") and not pool_owned:
                    pools_now.apply_async(
                        MeshGenerator.run,
                        kwds={
                            "seed_size": self.fea_seed_size,
                            "output_file": inp_path,
                            "directory": path_output,
                            "part_name": self.part_name,
                        },
                    ).get()
                else:
                    MeshGenerator.run(
                        seed_size=self.fea_seed_size,
                        output_file=inp_path,
                        directory=path_output,
                        part_name=self.part_name,
                    )
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to mesh boundary Part {self.name!r} "
                    f"({self.part_name!r})."
                ) from exc
        finally:
            if pool_owned:
                pools_now.close()
                pools_now.join()

        if not os.path.isfile(inp_path):
            raise RuntimeError(
                f"Mesh generator did not create the expected Abaqus file: "
                f"{inp_path}"
            )

        # read the inp file and create the Part
        inp = torchfea.FEA_INP()
        inp.read_inp(path=inp_path)
        nodes = inp.part[self.part_name].nodes[:, 1:]
        part = torchfea.Part(
            torch.from_numpy(nodes)
            .to(torch.get_default_device())
            .to(torch.get_default_dtype())
        )
        for surface_name, surface in inp.part[self.part_name].surfaces.items():
            part.add_surface_set(
                surface_name, [(entry[0], entry[1]) for entry in surface]
            )

        for set_name, node_indices in inp.part[self.part_name].sets_nodes.items():
            part.set_nodes[set_name] = np.unique(np.array(list(node_indices)))

        index_bottom = np.where(np.abs(nodes[:, 2] - 0) < 1e-3)[0]
        part.set_nodes["surface_0_Bottom"] = index_bottom
        index_head = np.where(np.abs(nodes[:, 2] - np.max(nodes[:, 2])) < 1e-3)[0]
        part.set_nodes["surface_0_Head"] = index_head

        for key in inp.part[self.part_name].elems.keys():
            elems = inp.part[self.part_name].elems[key][:, 1:]
            elems_index = inp.part[self.part_name].elems[key][:, 0]
            element = torchfea.elements.initialize_element(
                element_type=key,
                elems_index=torch.from_numpy(elems_index).to(
                    torch.get_default_device()
                ),
                elems=torch.from_numpy(elems).to(torch.get_default_device()),
                part=part,
            )
            part.add_element(element, name=key)

        surf_node_idx_list_order0 = [
            np.sort(part.set_nodes[f"surface_{index}_All"])
            for index in range(self.num_surface_interfaces)
        ]

        # match the mesh nodes of every surface with its parameterisation
        for surface_index in range(self.num_surface_interfaces):
            surf_node_idx = surf_node_idx_list_order0[surface_index]
            surf_nodes = part.nodes[surf_node_idx].cpu().numpy()
            surface_now = self.surfaceinterfaces[surface_index]
            surface_now.match_coordinates(surf_node_idx, surf_nodes)

            nodes_new = surface_now.map(torch.from_numpy(surface_now.surf_node_uv))
            part.nodes[surface_now.surf_node_idx] = nodes_new

        return part

    def export_data(self, dirpath: str) -> None:
        """Export every surface to ``__surface-<index>.stp|stl``."""
        os.makedirs(dirpath, exist_ok=True)
        for index, surface in enumerate(self.surfaceinterfaces):
            surface.output_data(
                path_output=dirpath,
                name_output="__surface-%d" % index,
                flip=(index != 0),
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
            norm = delta.norm(dim=1, keepdim=True)
            change = 2 / torch.pi * torch.atan(norm) * delta / (norm + 1e-15)
            if step is not None:
                change = change * step
            surface.update_variables(change)
            start += size

        self.apply_surface_constraints()

    @staticmethod
    def _surface_step_lengths(
        max_step_length: list[torch.Tensor | None] | None,
        surfaces: Sequence[BaseSurfaceInterface],
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
        values = [surface._cps.flatten() for surface in self.surfaceinterfaces]
        return torch.cat(values, dim=0).detach() if values else torch.zeros(0)

    def modify_assembly(
        self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly
    ) -> None:
        """Map the design variables onto the mesh nodes of this Part."""
        part = assembly.get_part(self.part_name)
        nodes_new = part.nodes.clone()

        values = torch.as_tensor(design_sensitivity_vars).reshape(-1)
        offset = 0
        for surface in self.surfaceinterfaces:
            size = surface.num_variables
            surface._cps = values[offset : offset + size].reshape_as(surface._cps)
            offset += size

            node_update = surface.map(torch.from_numpy(surface.surf_node_uv))
            nodes_new[surface.surf_node_idx] = node_update

        if self.mesh_order == 2:
            nodes_new[part.mid_pt_idxmap_torch[:, 2]] = (
                nodes_new[part.mid_pt_idxmap_torch[:, 0]]
                + nodes_new[part.mid_pt_idxmap_torch[:, 1]]
            ) / 2

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
        return 0.6 if index == 0 else 1.0

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
                opacity=opacity[index] if index < len(opacity) else 1.0,
                color=(40.0 / 255, 120.0 / 255, 181.0 / 255),
                diffuse=0.8,
                specular=0.2,
                ambient=0.3,
                specular_power=10,
                smooth_shading=True,
                show_edges=False,
            )
        return plotter
