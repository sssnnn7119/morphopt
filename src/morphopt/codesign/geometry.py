
from .. import GeometryParams
import numpy as np
import torch
import torchfea

class CodesignGeometry(GeometryParams):

    def __init__(self, 
                 fea_seed_size: float,
                 fea_mesh_order: int = 1,
                 reinitialize_per_iter: int = 5,
                 thickness=1.0,
                 num_layers=1,
                 **kwargs):
        super().__init__(
            fea_seed_size=fea_seed_size,
            fea_mesh_order=fea_mesh_order,
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

        self._reinit_opt_steps: int = 100
        self._reinit_opt_lr: float = 5e-3
        self._reinit_opt_curvature_weight: float = 1e2
        self._reinit_opt_shape_weight: float = 1e2
        self._reinit_opt_curvature_margin_ratio: float = 0.15
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



    def _build_shell_c3d6(self, inp: torchfea.FEA_INP):
        part = inp.part['final_model']
        nodes_all = part.nodes

        existing_elem_max_id = -1
        if hasattr(part, 'elems') and part.elems is not None:
            for elem_block in part.elems.values():
                if elem_block is not None and elem_block.size > 0:
                    existing_elem_max_id = max(existing_elem_max_id, int(np.max(elem_block[:, 0])))

        # Step 1: collect all cavity surfaces (surface_1_All ... surface_n_All),
        # merge their nodes and triangle mesh into a single base set.
        tri_blocks = []
        tri_blocks_by_surface: dict[int, np.ndarray] = {}
        cavity_order: list[int] = []
        for name, tri in part.surfaces_tri.items():
            if not (name.startswith('surface_') and name.endswith('_All')):
                continue
            try:
                sidx = int(name.split('_')[1])
            except Exception:
                continue
            if sidx >= 1 and tri.size > 0:
                tri_now = tri.astype(int)
                tri_blocks.append(tri_now)
                tri_blocks_by_surface[sidx] = tri_now
                cavity_order.append(sidx)

        if len(tri_blocks) == 0:
            raise KeyError("No cavity surface triangles found in surface_1_All ... surface_n_All.")

        tri_all = np.concatenate(tri_blocks, axis=0)
        base_ids = np.unique(tri_all.reshape(-1)).astype(int)
        self._node_idx = [base_ids]

        local_map = -np.ones(nodes_all.shape[0], dtype=int)
        local_map[base_ids] = np.arange(base_ids.shape[0], dtype=int)

        tri_local = local_map[tri_all]
        if np.any(tri_local < 0):
            raise ValueError("Failed to map merged cavity triangles to local node indices.")
        self._tri_local = tri_local.astype(int)

        # Step 2: compute smoothed offset target points on merged triangle mesh.
        base_xyz = nodes_all[base_ids, 1:4].copy()
        target_xyz = self._compute_offset_targets(torch.from_numpy(base_xyz).to(torch.get_default_device()), self._tri_local).cpu().numpy()
        disp_xyz = target_xyz - base_xyz

        # Step 3: insert layered nodes by linear interpolation from base to offset target.
        next_node_id = int(nodes_all[:, 0].max()) + 1
        for i in range(1, self.num_layers + 1):
            alpha = float(i) / float(self.num_layers)
            xyz = base_xyz + alpha * disp_xyz
            node_ids = np.arange(next_node_id, next_node_id + xyz.shape[0], dtype=nodes_all.dtype)
            next_node_id += xyz.shape[0]

            block = np.zeros((xyz.shape[0], 4), dtype=nodes_all.dtype)
            block[:, 0] = node_ids
            block[:, 1:4] = xyz
            nodes_all = np.concatenate([nodes_all, block], axis=0)

            self._node_idx.append(node_ids.astype(int))

        # Build C3D6 elements between consecutive layers.
        c3d6_rows = []
        next_elem_id = existing_elem_max_id + 1
        elem_id_of_tri_layer0: list[int] = []
        elem_id_of_tri_by_layer: list[list[int]] = [[] for _ in range(self.num_layers)]

        # Step 4: construct C3D6 from merged tri mesh and layer node indices.
        for layer in range(self.num_layers):
            low_ids = self._node_idx[layer]
            up_ids = self._node_idx[layer + 1]

            for tri in self._tri_local:
                a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
                n0, n1, n2 = int(low_ids[a]), int(low_ids[b]), int(low_ids[c])
                n3, n4, n5 = int(up_ids[a]), int(up_ids[b]), int(up_ids[c])

                c3d6_rows.append([next_elem_id, n0, n1, n2, n3, n4, n5])
                elem_id_of_tri_by_layer[layer].append(next_elem_id)
                if layer == 0:
                    elem_id_of_tri_layer0.append(next_elem_id)
                next_elem_id += 1

        part.nodes = nodes_all
        c3d6_new = np.asarray(c3d6_rows, dtype=int)
        if not hasattr(part, 'elems') or part.elems is None:
            part.elems = {'C3D6': c3d6_new}
        elif 'C3D6' in part.elems and part.elems['C3D6'] is not None and part.elems['C3D6'].size > 0:
            part.elems['C3D6'] = np.concatenate([part.elems['C3D6'], c3d6_new], axis=0)
        else:
            part.elems['C3D6'] = c3d6_new

        # Keep INP part bookkeeping coherent with FEA_INP flow.
        if hasattr(part, 'num_elems_3D'):
            part.num_elems_3D = sum(
                elem_data.shape[0]
                for elem_data in part.elems.values()
                if elem_data is not None and elem_data.size > 0 and elem_data.shape[1] >= 4
            )
        if hasattr(part, 'num_elems_2D'):
            part.num_elems_2D = 0

        # Surface definitions for cavity pressure/BC: use layer-0 triangular face of C3D6 (face index 0).
        part.surfaces = {} if not hasattr(part, 'surfaces') or part.surfaces is None else part.surfaces
        part.sets_nodes = {} if not hasattr(part, 'sets_nodes') or part.sets_nodes is None else part.sets_nodes

        # Define offset surfaces by cavity index: surface_%d_offset.
        # Use the outermost inserted layer (k=num_layers).
        tri_cursor = 0
        top_layer_ids = self._node_idx[self.num_layers]
        for sidx in cavity_order:
            tri_s = tri_blocks_by_surface[sidx]
            ntri = tri_s.shape[0]

            # Element ids for this cavity at topmost wedge layer.
            elem_ids_s_top = np.asarray(
                elem_id_of_tri_by_layer[self.num_layers - 1][tri_cursor:tri_cursor + ntri],
                dtype=int,
            )
            tri_cursor += ntri

            surf_name_offset = f'surface_{sidx}_offset'
            # C3D6 top triangular face index is 1.
            part.surfaces[surf_name_offset] = [(elem_ids_s_top, 1)]

            tri_local_s = local_map[tri_s]
            tri_layer_s = top_layer_ids[tri_local_s]
            part.surfaces_tri[surf_name_offset] = tri_layer_s.astype(int)
            part.sets_nodes[surf_name_offset] = set(np.unique(tri_layer_s.reshape(-1)).astype(int).tolist())

        # Rebuild element sets for section assignment consistency.
        new_elem_ids = set(c3d6_new[:, 0].astype(int).tolist())
        if hasattr(part, 'sets_elems') and part.sets_elems is not None:
            for set_name in list(part.sets_elems.keys()):
                old_set = part.sets_elems[set_name] if part.sets_elems[set_name] is not None else set()
                part.sets_elems[set_name] = set(old_set).union(new_elem_ids)

        # Rebuild material table shape/indexes expected by FEA_INP (index, density, type, p0, p1).
        old_em = part.elems_material if hasattr(part, 'elems_material') else None
        density = 0.0
        mat_type = 1.0
        p0 = 1.0
        p1 = 1.0
        if old_em is not None and old_em.size > 0:
            valid = np.where((old_em[:, 0] >= 0) & np.isin(old_em[:, 2].astype(int), [1, 2]))[0]
            if valid.size > 0:
                src = old_em[valid[0]]
                density = float(src[1])
                mat_type = float(src[2])
                p0 = float(src[3])
                p1 = float(src[4])

        p0 = 0.
        p1 = 0.

        all_elem_ids = np.concatenate(
            [blk[:, 0].astype(int) for blk in part.elems.values() if blk is not None and blk.size > 0],
            axis=0,
        )
        mat_size = int(all_elem_ids.max()) + 1 if all_elem_ids.size > 0 else 0
        new_em = -np.ones((mat_size, 5), dtype=float)
        if old_em is not None and old_em.size > 0:
            copy_len = min(old_em.shape[0], mat_size)
            new_em[:copy_len] = old_em[:copy_len]

        new_em[c3d6_new[:, 0].astype(int), 0] = c3d6_new[:, 0].astype(float)
        new_em[c3d6_new[:, 0].astype(int), 1] = density
        new_em[c3d6_new[:, 0].astype(int), 2] = mat_type
        new_em[c3d6_new[:, 0].astype(int), 3] = p0
        new_em[c3d6_new[:, 0].astype(int), 4] = p1

        missing_ids = all_elem_ids[new_em[all_elem_ids, 2] < 0]
        if missing_ids.size > 0:
            new_em[missing_ids, 0] = missing_ids.astype(float)
            new_em[missing_ids, 1] = density
            new_em[missing_ids, 2] = mat_type
            new_em[missing_ids, 3] = p0
            new_em[missing_ids, 4] = p1

        part.elems_material = new_em

        return inp

    def _regenerate(self, path_result: str, pools=None):

        # get the input data
        inp = super()._regenerate(path_result=path_result, pools=pools)
        inp = self._build_shell_c3d6(inp)
        return inp


    def modify_assembly(self, design_sensitivity_vars, assembly):
        super().modify_assembly(design_sensitivity_vars, assembly)

        if len(self._node_idx) == 0 or self._tri_local is None:
            return

        nodes = assembly.get_part('final_model').nodes.clone()
        base_ids = self._node_idx[0]
        base_nodes = nodes[base_ids]
        target_nodes = self._compute_offset_targets(base_nodes, self._tri_local)
        disp = target_nodes - base_nodes

        for layer in range(1, self.num_layers + 1):
            layer_ids = self._node_idx[layer]
            alpha = float(layer) / float(self.num_layers)
            nodes[layer_ids] = base_nodes + alpha * disp

        assembly.get_part('final_model').nodes = nodes