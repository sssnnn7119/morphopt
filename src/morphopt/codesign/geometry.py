
from .. import GeometryParams
import numpy as np
import torch
import torchfea

class CodesignGeometry(GeometryParams):

    def __init__(self, 
                 fea_seed_size: float,
                 mesh_order: int = 1,
                 reinitialize_per_iter: int = 5,
                 thickness=1.0,
                 num_layers=1,
                 **kwargs):
        super().__init__(
            fea_seed_size=fea_seed_size,
            mesh_order=mesh_order,
            reinitialize_per_iter=reinitialize_per_iter,
            **kwargs,
        )
        self.shell_thickness: float = float(thickness)
        """
        The thickness of the shell elements.
        """

        self.num_layers: int = max(1, int(num_layers))
        """
        The number of layers for the shell elements. This is used to control the number of integration points through the thickness of the shell elements.
        """

        self._node_idx: list[np.ndarray] = []
        """
        The list of node indices for the offseted nodes of the shell elements. `_node_idx[i]` is the `i-th` layer of the shell elements.
        
        `0-th` layer corresponds to the original surface mesh, and the `i-th` layer corresponds to the offseted nodes by `i*thickness` along the normal direction. This is used to update the nodal coordinates of the shell elements in the assembly modification step.
        """

        self._tri_local: np.ndarray | None = None
        """
        Triangle connectivity on the base layer, stored as local node indices.
        """

        self._shell_second_order_node_map: torch.Tensor | None = None
        """[N,3] int64 tensor (i,j,mid) for shell mid-edge nodes."""

        self._shell_elem_offset: int | None = None
        """Element-id offset for the shell block (0-based)."""

        self._reinit_opt_steps: int = 100
        self._reinit_opt_lr: float = 5e-3
        self._reinit_opt_curvature_weight: float = 1e2
        self._reinit_opt_shape_weight: float = 1e2
        self._reinit_opt_curvature_margin_ratio: float = 0.25
        self._reinit_opt_inward_sign: float = 1.0
        self._reinit_opt_accept_only_improve: bool = True

    def reinitialize(self, iteration):
        super().reinitialize(iteration)
        self._optimize_after_reinitialize()

    @staticmethod
    def _principal_curvatures(rdu: torch.Tensor, rdu2: torch.Tensor, eps: float = 1e-12) -> tuple[torch.Tensor, torch.Tensor]:
        normal0 = torch.cross(rdu[:, :, 1], rdu[:, :, 0], dim=1)
        normal = normal0 / (normal0.norm(dim=1, keepdim=True) + eps)

        I = torch.einsum("pim,pin->pmn", rdu, rdu)
        eye2 = torch.eye(2, dtype=I.dtype, device=I.device).unsqueeze(0)
        I = I + eps * eye2

        II = torch.einsum("pimn,pi->pmn", rdu2, normal)
        S = torch.linalg.solve(I, II)

        tr = S[:, 0, 0] + S[:, 1, 1]
        det = S[:, 0, 0] * S[:, 1, 1] - S[:, 0, 1] * S[:, 1, 0]
        disc = (tr * tr - 4.0 * det).clamp(min=0.0)
        root = torch.sqrt(disc)

        k1 = 0.5 * (tr + root)
        k2 = 0.5 * (tr - root)
        return k1, k2

    def _optimize_after_reinitialize(self) -> None:
        if self._reinit_opt_steps <= 0:
            return

        thickness = float(self.shell_thickness)
        if thickness <= 0:
            return

        k_limit = 1.0 / max(thickness * (1.0 + self._reinit_opt_curvature_margin_ratio), 1e-12)

        def _surrogate_loss(surf_now: GeometryParams.CpBasedInterface, cp_ref_now: torch.Tensor):
            _, rdu_now, rdu2_now = surf_now.get_geometry_values()
            k1_now, k2_now = self._principal_curvatures(rdu_now, rdu2_now)

            k1_in_now = torch.relu(self._reinit_opt_inward_sign * k1_now)
            k2_in_now = torch.relu(self._reinit_opt_inward_sign * k2_now)
            k_in_now = torch.maximum(k1_in_now, k2_in_now)

            viol_now = torch.relu(k_in_now - k_limit)
            loss_curv_now = ((viol_now)**2).sum()
            loss_shape_now = ((surf_now._cps - cp_ref_now) ** 2).mean()
            return self._reinit_opt_curvature_weight * loss_curv_now + self._reinit_opt_shape_weight * loss_shape_now

        for sfidx in range(1, self.num_surface):
            surf = self.surface_list[sfidx]
            surf.pre_load()
            if not hasattr(surf, "_cps"):
                continue

            cp_ref = surf._cps.detach().clone()
            surf._cps = surf._cps.detach().clone().requires_grad_(True)
            optimizer = torch.optim.Adam([surf._cps], lr=self._reinit_opt_lr)

            with torch.no_grad():
                best_loss = _surrogate_loss(surf, cp_ref).detach()
            best_cps = surf._cps.detach().clone()
            
            total_iter = 0
            while True:
                optimizer.zero_grad()

                loss = _surrogate_loss(surf, cp_ref)

                loss.backward()

                if loss == 0:
                    break
                if _surrogate_loss(surf, surf._cps.detach()) < 1e-3:
                    break

                optimizer.step()

                with torch.no_grad():
                    loss_now = _surrogate_loss(surf, cp_ref)
                    if loss_now < best_loss:
                        best_loss = loss_now.detach()
                        best_cps = surf._cps.detach().clone()

                total_iter += 1
                if total_iter >= self._reinit_opt_steps:
                    break

            if self._reinit_opt_accept_only_improve:
                surf._cps = best_cps
            else:
                surf._cps = surf._cps.detach()

        

        

    def _compute_normals(self, base_nodes: torch.Tensor, tri_local: np.ndarray) -> torch.Tensor:
        """
        Compute vertex normals from current base-layer nodes with autograd support.
        """
        # tri = torch.as_tensor(tri_local, dtype=torch.long, device=base_nodes.device)
        # v0 = base_nodes[tri[:, 0]]
        # v1 = base_nodes[tri[:, 1]]
        # v2 = base_nodes[tri[:, 2]]
        # face_normals = torch.cross(v1 - v0, v2 - v0, dim=1)

        # vert_normals = torch.zeros_like(base_nodes)
        # vert_normals.index_add_(0, tri[:, 0], face_normals)
        # vert_normals.index_add_(0, tri[:, 1], face_normals)
        # vert_normals.index_add_(0, tri[:, 2], face_normals)

        # vert_normals = vert_normals / (vert_normals.norm(dim=1, keepdim=True) + 1e-14)

        normal_list = []
        for sfidx in range(1, self.num_surface):
            
            normal_list.append(self.surface_list[sfidx].get_normals(torch.from_numpy(self.surface_list[sfidx].surf_node_uv).to(torch.get_default_device())))

        normals = torch.cat(normal_list, dim=0)

        return normals

    def _compute_offset_targets(self, base_nodes: torch.Tensor, tri_local: np.ndarray) -> torch.Tensor:
        direction = self._compute_normals(base_nodes, tri_local)

        total_thickness = float(self.shell_thickness)
        return base_nodes + total_thickness * direction



    def _build_shell_c3d6(self, part: torchfea.Part) -> torchfea.Part:
        thickness = float(self.shell_thickness)
        if thickness <= 0:
            return part
        if self.num_layers <= 0:
            return part

        # Ensure surface elements exist so we can query triangle meshes.
        try:
            part.surfaces.initialize(part)
        except Exception:
            pass

        tri_by_surface: dict[int, np.ndarray] = {}
        tri_local_by_surface: dict[int, np.ndarray] = {}
        base_ids_blocks: list[np.ndarray] = []
        cavity_order: list[int] = []

        for sidx in range(1, int(self.num_surface)):
            surf_name = f"surface_{sidx}_All"
            tri = part.surfaces.get_trimesh(surf_name).detach().cpu().numpy().astype(int)
            cavity_order.append(sidx)
            tri_by_surface[sidx] = tri
            base_ids_blocks.append(np.sort(np.asarray(part.set_nodes[surf_name], dtype=int)))

        if len(tri_by_surface) == 0:
            raise KeyError("No cavity surfaces found in surface_1_All ... surface_n_All")

        # Merge base-layer node indices (keep deterministic order).
        base_ids = np.concatenate(base_ids_blocks, axis=0)
        self._node_idx = [base_ids]

        local_map = -np.ones((int(part.nodes.shape[0]),), dtype=int)
        local_map[base_ids] = np.arange(base_ids.shape[0], dtype=int)

        tri_local_all = []
        for sidx in cavity_order:
            tri_global = tri_by_surface[sidx]
            tri_local = local_map[tri_global]
            if np.any(tri_local < 0):
                raise ValueError(f"Failed to map cavity triangles for surface_{sidx}_All")
            tri_local = tri_local.astype(int)
            tri_local_by_surface[sidx] = tri_local
            tri_local_all.append(tri_local)
        self._tri_local = np.concatenate(tri_local_all, axis=0).astype(int)

        device = part.nodes.device
        base_ids_t = torch.as_tensor(base_ids, dtype=torch.long, device=device)

        with torch.no_grad():
            base_nodes = part.nodes[base_ids_t]
            target_nodes = self._compute_offset_targets(base_nodes, self._tri_local)
            disp = target_nodes - base_nodes

            nodes_all = part.nodes
            num_base = int(base_nodes.shape[0])
            for layer in range(1, self.num_layers + 1):
                alpha = float(layer) / float(self.num_layers)
                new_xyz = base_nodes + alpha * disp
                start_idx = int(nodes_all.shape[0])
                nodes_all = torch.cat([nodes_all, new_xyz], dim=0)
                self._node_idx.append(np.arange(start_idx, start_idx + num_base, dtype=int))
            part.nodes = nodes_all

        # Determine next element id (0-based, consistent with torchfea export).
        existing_max = -1
        for e in part.elems.values():
            if getattr(e, "_elems_index", None) is None:
                continue
            if e._elems_index.numel() == 0:
                continue
            existing_max = max(existing_max, int(e._elems_index.max().item()))
        elem_offset = int(existing_max + 1)
        self._shell_elem_offset = elem_offset

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

                elem_ids_now = np.arange(elem_cursor, elem_cursor + wedge6.shape[0], dtype=int)
                elem_cursor += wedge6.shape[0]
                if layer == self.num_layers - 1:
                    elem_ids_top_by_surface[sidx] = elem_ids_now

        wedge6_np = np.concatenate(wedge6_blocks, axis=0).astype(int)
        elem_index = torch.arange(elem_offset, elem_offset + wedge6_np.shape[0], dtype=torch.long, device=device)


        self._shell_second_order_node_map = None
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
            part.add_surface_set(surf_name_offset, [(np.asarray(elem_ids_s_top, dtype=int), 1)])

            # Also provide a node set for convenience (include mid-edge nodes for quadratic).
            row = (np.asarray(elem_ids_s_top, dtype=int) - elem_offset).astype(int)
            if row.size > 0:
                conn = wedge6_np[row][:, shell_top_face_cols]
                part.set_nodes[surf_name_offset] = np.unique(conn.reshape(-1)).astype(int)

        # Refresh surfaces cache to include the newly-added offset surfaces.
        try:
            part.surfaces.initialize(part)
        except Exception:
            pass

        return part

    def _regenerate(self, path_result: str, pools=None):

        part = super()._regenerate(path_result=path_result, pools=pools)
        part = self._build_shell_c3d6(part)
        return part


    def modify_assembly(self, design_sensitivity_vars, assembly):
        super().modify_assembly(design_sensitivity_vars, assembly)

        if len(self._node_idx) == 0 or self._tri_local is None:
            return
        
        part = assembly.get_part('final_model')

        nodes = part.nodes.clone()
        base_ids_t = torch.as_tensor(self._node_idx[0], dtype=torch.long, device=nodes.device)
        base_nodes = nodes[base_ids_t]
        target_nodes = self._compute_offset_targets(base_nodes, self._tri_local)
        disp = target_nodes - base_nodes

        for layer in range(1, self.num_layers + 1):
            layer_ids_t = torch.as_tensor(self._node_idx[layer], dtype=torch.long, device=nodes.device)
            alpha = float(layer) / float(self.num_layers)
            nodes[layer_ids_t] = base_nodes + alpha * disp

        # Keep quadratic mid-edge nodes consistent (and differentiable).
        if self._mesh_order == 2:
            nodes[part.mid_pt_idxmap_torch[:, 2]] = (nodes[part.mid_pt_idxmap_torch[:, 0]] + nodes[part.mid_pt_idxmap_torch[:, 1]]) / 2

        part.nodes = nodes