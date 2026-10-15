"""Co-design boundary part: cavity surfaces with an offset shell.

The co-design (``codesign``) scheme extends the shape-optimization boundary
description with a solid shell: every cavity surface (index ``1..n``) is offset
along its normal and the resulting layer is filled with ``C3D6`` wedge
elements.  The shell therefore belongs to the same Part as the solid volume and
follows the same design variables.
"""

from __future__ import annotations

import numpy as np
import torch
import torchfea

from ..shapeopt.boundary_part import BoundaryPart

__all__ = ["OffsetBoundaryPart"]


class OffsetBoundaryPart(BoundaryPart):
    """Boundary-surface geometry whose cavity surfaces carry a solid shell.

    Parameters
    ----------
    shell_thickness:
        Total thickness of the offset shell added on the cavity surfaces.
    num_layers:
        Number of wedge layers through the shell thickness (1 = single layer).
    """

    def __init__(
        self,
        shell_thickness: float = 1.0,
        num_layers: int = 1,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)

        self.shell_thickness: float = float(shell_thickness)
        """Total thickness of the offset shell on the cavity surfaces."""

        self.num_layers: int = int(num_layers)
        """Number of wedge layers through the shell thickness."""

        self._node_idx: list[np.ndarray] = []
        """Node indices of each offset layer (0 = base surface mesh)."""

        if self.shell_thickness <= 0:
            raise ValueError("shell_thickness must be positive.")
        if self.num_layers < 1:
            raise ValueError("num_layers must be at least one.")

    # ------------------------------------------------------------- shell mesh
    def _compute_normals(self, base_nodes: torch.Tensor) -> torch.Tensor:
        """Cavity-surface normals evaluated on the current control points."""
        normals = []
        for index in range(1, self.num_surface_interfaces):
            surface = self.surfaceinterfaces[index]
            normals.append(
                surface.get_normals(
                    torch.as_tensor(
                        surface.surf_node_uv, device=base_nodes.device,
                        dtype=base_nodes.dtype,
                    )
                )
            )
        return torch.cat(normals, dim=0)

    def _compute_offset_targets(self, base_nodes: torch.Tensor) -> torch.Tensor:
        """Offset the base nodes by ``shell_thickness`` along the normals."""
        direction = self._compute_normals(base_nodes)
        return base_nodes + float(self.shell_thickness) * direction

    def _postprocess_part(self, part: torchfea.Part) -> torchfea.Part:
        """Add the offset shell wedge elements to the meshed Part."""
        return self._build_shell_c3d6(part)

    def build_part(self, path_result=None, pools=None) -> torchfea.Part:
        """Build and validate the offset wedges, including quadratic conversion."""
        part = super().build_part(path_result=path_result, pools=pools)
        shell = part.elems["C3D6"]
        shell.initialize(nodes=part.nodes)
        weights = shell.gaussian_weight
        if not torch.isfinite(weights).all() or (weights <= 0).any():
            raise ValueError(f"Invalid offset shell mesh on Part {self.part_name!r}.")
        return part

    def _build_shell_c3d6(self, part: torchfea.Part) -> torchfea.Part:
        # Ensure surface elements exist so we can query triangle meshes.
        part.surfaces.initialize(part)

        tri_by_surface: dict[int, np.ndarray] = {}
        tri_local_by_surface: dict[int, np.ndarray] = {}
        base_ids_blocks: list[np.ndarray] = []
        cavity_order: list[int] = []

        for sidx in range(1, self.num_surface_interfaces):
            surf_name = f"surface_{sidx}_All"
            tri = (
                part.surfaces.get_trimesh(surf_name).detach().cpu().numpy().astype(int)
            )
            cavity_order.append(sidx)
            tri_by_surface[sidx] = tri
            base_ids_blocks.append(
                np.asarray(self.surfaceinterfaces[sidx].surf_node_idx, dtype=int)
            )

        if len(tri_by_surface) == 0:
            raise KeyError(
                "No cavity surfaces found in surface_1_All ... surface_n_All"
            )

        # Merge base-layer node indices (keep deterministic order).
        base_ids = np.concatenate(base_ids_blocks, axis=0)
        self._node_idx = [base_ids]

        local_map = -np.ones((int(part.nodes.shape[0]),), dtype=int)
        local_map[base_ids] = np.arange(base_ids.shape[0], dtype=int)

        for sidx in cavity_order:
            tri_global = tri_by_surface[sidx]
            tri_local = local_map[tri_global]
            if np.any(tri_local < 0):
                raise ValueError(
                    f"Failed to map cavity triangles for surface_{sidx}_All"
                )
            tri_local = tri_local.astype(int)
            tri_local_by_surface[sidx] = tri_local

        device = part.nodes.device
        base_ids_t = torch.as_tensor(base_ids, dtype=torch.long, device=device)

        with torch.no_grad():
            base_nodes = part.nodes[base_ids_t]
            target_nodes = self._compute_offset_targets(base_nodes)
            disp = target_nodes - base_nodes

            nodes_all = part.nodes
            num_base = int(base_nodes.shape[0])
            for layer in range(1, self.num_layers + 1):
                alpha = float(layer) / float(self.num_layers)
                new_xyz = base_nodes + alpha * disp
                start_idx = int(nodes_all.shape[0])
                nodes_all = torch.cat([nodes_all, new_xyz], dim=0)
                self._node_idx.append(
                    np.arange(start_idx, start_idx + num_base, dtype=int)
                )
            part.nodes = nodes_all

        # Determine the next element id (0-based, consistent with torchfea export).
        existing_max = -1
        for element in part.elems.values():
            if element._elems_index.numel() == 0:
                continue
            existing_max = max(existing_max, int(element._elems_index.max().item()))
        elem_offset = int(existing_max + 1)

        # Build linear wedge connectivity (C3D6) for all layers.
        wedge6_blocks = []
        elem_ids_top_by_surface: dict[int, np.ndarray] = {}

        elem_cursor = elem_offset
        for layer in range(self.num_layers):
            low_ids = self._node_idx[layer]
            up_ids = self._node_idx[layer + 1]

            for sidx in cavity_order:
                tri_local = tri_local_by_surface[sidx]
                n0 = low_ids[tri_local[:, 0]]
                n1 = low_ids[tri_local[:, 1]]
                n2 = low_ids[tri_local[:, 2]]
                n3 = up_ids[tri_local[:, 0]]
                n4 = up_ids[tri_local[:, 1]]
                n5 = up_ids[tri_local[:, 2]]

                wedge6 = np.stack([n0, n1, n2, n3, n4, n5], axis=1).astype(int)
                wedge6_blocks.append(wedge6)

                elem_ids_now = np.arange(
                    elem_cursor, elem_cursor + wedge6.shape[0], dtype=int
                )
                elem_cursor += wedge6.shape[0]
                if layer == self.num_layers - 1:
                    elem_ids_top_by_surface[sidx] = elem_ids_now

        wedge6_np = np.concatenate(wedge6_blocks, axis=0).astype(int)
        elem_index = torch.arange(
            elem_offset,
            elem_offset + wedge6_np.shape[0],
            dtype=torch.long,
            device=device,
        )

        element = torchfea.elements.initialize_element(
            element_type="C3D6",
            elems_index=elem_index,
            elems=torch.from_numpy(wedge6_np).to(device=device, dtype=torch.long),
            part=part,
        )
        part.add_element(element, name="C3D6")
        shell_top_face_cols = [3, 4, 5]

        # Define offset surfaces at the outermost layer, per cavity.
        for sidx, elem_ids_s_top in elem_ids_top_by_surface.items():
            surf_name_offset = f"surface_{sidx}_offset"
            part.add_surface_set(
                surf_name_offset, [(np.asarray(elem_ids_s_top, dtype=int), 1)]
            )

            row = (np.asarray(elem_ids_s_top, dtype=int) - elem_offset).astype(int)
            if row.size > 0:
                conn = wedge6_np[row][:, shell_top_face_cols]
                part.set_nodes[surf_name_offset] = np.unique(conn.reshape(-1)).astype(
                    int
                )

        # Refresh the surfaces cache to include the newly added offset surfaces.
        part.surfaces.initialize(part)

        return part

    # ------------------------------------------------------------ variables
    def modify_assembly(
        self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly
    ) -> None:
        """Update the Part nodes and keep the offset layers consistent."""
        super().modify_assembly(design_sensitivity_vars, assembly)

        part = assembly.get_part(self.part_name)
        nodes = part.nodes.clone()

        base_ids_t = torch.as_tensor(
            self._node_idx[0], dtype=torch.long, device=nodes.device
        )
        base_nodes = nodes[base_ids_t]
        target_nodes = self._compute_offset_targets(base_nodes)
        disp = target_nodes - base_nodes

        for layer in range(1, self.num_layers + 1):
            layer_ids_t = torch.as_tensor(
                self._node_idx[layer], dtype=torch.long, device=nodes.device
            )
            alpha = float(layer) / float(self.num_layers)
            nodes[layer_ids_t] = base_nodes + alpha * disp

        if self.mesh_order == 2:
            nodes[part.mid_pt_idxmap_torch[:, 2]] = (
                nodes[part.mid_pt_idxmap_torch[:, 0]]
                + nodes[part.mid_pt_idxmap_torch[:, 1]]
            ) / 2

        part.nodes = nodes

    @staticmethod
    def _default_opacity(index: int) -> float:
        """The solid volume is hidden so the shell stays visible."""
        return 0.0 if index == 0 else 1.0
