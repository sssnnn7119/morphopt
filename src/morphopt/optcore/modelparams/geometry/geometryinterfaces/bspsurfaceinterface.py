
import os
import sys
import numpy as np
import torch
import gmsh

import morphopt

from .basesurfaceinterface import BaseInterface
from ..geometricmodel.bspline.BSP import BSP_Surf


class BSplineSolidGenerator:
    def __init__(self, P0, degree_u=3, degree_v=3):
        """
        初始化 B-Spline 实体生成器 (使用 Gmsh)
        
        参数:
            P0: numpy array, shape (3, numV, numU). 
                代表控制点 (Poles). 
                注意: U方向应为非重复的唯一控制点 (Periodic).
            degree_u: U方向阶数
            degree_v: V方向阶数
        """
        self.P0 = P0
        self.degree_u = degree_u
        self.degree_v = degree_v
        self.volume_tag = None
        
    def build(self):
        """
        构建版本 - 改用 addBSplineSurface + Symmetric Wrapping + Trim
        通过上下游双重延伸(Padding)确保接缝处C2连续性
        """
        self.volume_tag = None
        
        # 初始化 Gmsh
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0) # Suppress Gmsh output
        gmsh.option.setNumber("General.Verbosity", 0)
        gmsh.model.add("bspline_solid")
        
        # 获取维度
        num_poles_v = self.P0.shape[1]
        num_poles_u_raw = self.P0.shape[2]
        du = self.degree_u
        dv = self.degree_v
        
        # ----------------------------------------------------
        # 0. Sanitize Input (Check for explicit closure)
        # ----------------------------------------------------
        # 用户可能传入了闭合的控制点序列 (P_start == P_end)
        # B-Spline 周期性数学构造需要唯一控制点序列。
        # 如果发现首尾重合，去掉最后一个。
        
        # 检查第一行即可
        p_start = self.P0[:, 0, 0]
        p_end = self.P0[:, 0, -1]
        dist = np.linalg.norm(p_start - p_end)
        
        if dist < 1e-6:
            # print("Detecting closed input poles (Start == End). Removing last pole for periodic construction.")
            poles_to_use = self.P0[:, :, :-1]
        else:
            poles_to_use = self.P0
            
        num_poles_u = poles_to_use.shape[2]
        # print(f"Effective Unique Poles U: {num_poles_u}")


        # ----------------------------------------------------
        # 1. Prepare Control Points (Periodic Extension)
        # ----------------------------------------------------
        # B-Spline Periodicity Implementation:
        # 1. Unique Poles: P[0] ... P[n-1]  (Count = n)
        # 2. Extended Poles: P[0]...P[n-1] + P[0]...P[d-1] (Count = n + d)
        # 3. Knots: Uniform. Count = (n+d) + d + 1 = n + 2d + 1
        # 4. Valid Period Range: [d, n+d] (Length = n)
        
        # Create Point Entities
        point_tags_map = np.zeros((num_poles_v, num_poles_u), dtype=int)
        for j in range(num_poles_v):
            for i in range(num_poles_u):
                pt = poles_to_use[:, j, i]
                t = gmsh.model.occ.addPoint(pt[0], pt[1], pt[2])
                point_tags_map[j, i] = t

        # Build Extended List (Row by Row)
        # Flattened list for addBSplineSurface
        side_point_tags = []
        
        for j in range(num_poles_v):
            # Original: indices 0 ... num_poles_u - 1
            for i in range(num_poles_u):
                side_point_tags.append(point_tags_map[j, i])
            # Wrap Extension: indices 0 ... du - 1
            for k in range(du):
                side_point_tags.append(point_tags_map[j, k])

        # ----------------------------------------------------
        # 2. Setup Knots (Uniform)
        # ----------------------------------------------------
        num_extended_poles_u = num_poles_u + du
        num_knots_u = num_extended_poles_u + du + 1
        
        # Uniform Knots: 0, 1, 2, ...
        # Range of full surface support: [0, num_knots_u - 1] because degree=d
        # Standard domain of B-Spline starts at knot[d] = d
        # Ends at knot[len - 1 - d] = (n+2d) - d = n+d
        # So valid parameter range is [d, n+d]. Length = n. Correct.
        knots_u = [float(i) for i in range(num_knots_u)]
        mults_u = [1] * len(knots_u)
        
        # V: Clamped (Standard)
        num_knots_v = num_poles_v - dv + 1
        knots_v = []
        mults_v = []
        for i in range(num_knots_v):
            knots_v.append(float(i))
            if i == 0 or i == num_knots_v - 1:
                mults_v.append(dv + 1)
            else:
                mults_v.append(1)
                
        # ----------------------------------------------------
        # 3. Create Base Surface
        # ----------------------------------------------------
        try:
            raw_surface = gmsh.model.occ.addBSplineSurface(
                side_point_tags, num_extended_poles_u, -1, du, dv, 
                [], knots_u, knots_v, mults_u, mults_v
            )
        except Exception as e:
            # print(f"BSpline fail: {e}")
            raise e
            
        # ----------------------------------------------------
        # 4. Trim Surface (One Period)
        # ----------------------------------------------------
        # Trim range: [du, du + num_poles_u]
        u_min = float(du)
        u_max = float(du + num_poles_u)
        v_min = knots_v[0]
        v_max = knots_v[-1]
        
        # Create UV bounding box loop
        p1 = gmsh.model.occ.addPoint(u_min, v_min, 0)
        p2 = gmsh.model.occ.addPoint(u_max, v_min, 0)
        p3 = gmsh.model.occ.addPoint(u_max, v_max, 0)
        p4 = gmsh.model.occ.addPoint(u_min, v_max, 0)
        
        l1 = gmsh.model.occ.addLine(p1, p2)
        l2 = gmsh.model.occ.addLine(p2, p3)
        l3 = gmsh.model.occ.addLine(p3, p4)
        l4 = gmsh.model.occ.addLine(p4, p1)
        
        loop = gmsh.model.occ.addCurveLoop([l1, l2, l3, l4])
        
        side_surface = gmsh.model.occ.addTrimmedSurface(raw_surface, [loop], wire3D=False)
        
        gmsh.model.occ.synchronize()
        
        # ----------------------------------------------------
        # 5. Create Caps using Common Topology
        # ----------------------------------------------------
        # 直接获取 Trimmed Surface 的边界
        boundaries = gmsh.model.getBoundary([(2, side_surface)], recursive=False)
        
        cap_faces = []
        
        for dim, tag in boundaries:
            # 检查是否闭合 (Caps)
            status, nodes = gmsh.model.getAdjacencies(1, tag)
            
            is_closed_loop = False
            if len(nodes) >= 2:
                # 几何检查
                c1 = gmsh.model.getValue(0, nodes[0], [])
                c2 = gmsh.model.getValue(0, nodes[-1], [])
                dist = np.linalg.norm(np.array(c1)-np.array(c2))
                if dist < 1e-5:
                    is_closed_loop = True
            
            if is_closed_loop:
                # Cap Face
                w = gmsh.model.occ.addWire([tag])
                try:
                    f = gmsh.model.occ.addPlaneSurface([w])
                    cap_faces.append(f)
                except:
                    try:
                        f = gmsh.model.occ.addSurfaceFilling(w)
                        cap_faces.append(f)
                    except:
                        pass


        # ----------------------------------------------------
        # 6. Build Solid
        # ----------------------------------------------------
        surface_tags = [side_surface] + cap_faces
        
        # print("Sewing and Healing...")
        
        # 尝试直接通过 SurfaceLoop 创建
        try:
            shell_tag = gmsh.model.occ.addSurfaceLoop(surface_tags)
            self.volume_tag = gmsh.model.occ.addVolume([shell_tag])
            # print(f"Created solid via SurfaceLoop: {self.volume_tag}")
        except Exception as e:
            # print(f"Direct SurfaceLoop failed: {e}")
            # 使用 healShapes，重点是 sewFaces=True
            try:
                healed = gmsh.model.occ.healShapes([(2, t) for t in surface_tags], 
                                                 tolerance=1e-1,
                                                 fixDegenerated=True, 
                                                 fixSmallEdges=False,
                                                 fixSmallFaces=False,
                                                 sewFaces=True, 
                                                 makeSolids=True)
                
                for dim, tag in healed:
                    if dim == 3:
                        self.volume_tag = tag
                        # print(f"Healed Solid Created: {tag}")
                        break
            except Exception as he:
                pass
                # print(f"Heal error: {he}")

        gmsh.model.occ.synchronize()
        
        if self.volume_tag:
            # ----------------------------------------------------
            # 7. Cleanup (Nuclear Option: BRep Isolation)
            # ----------------------------------------------------
            # To ensure ABSOLUTELY NO extra lines, points, or invisible shells
            # are exported, we will:
            # 1. Isolate the Solid in the current model.
            # 2. Write it to a temporary BRep (native OCC format).
            # 3. CLEARS the Gmsh model.
            # 4. Import the BRep back.
            # 5. This guarantees fresh indexing and zero "history".
            
            # print("Starting Nuclear Cleanup (BRep Isolation)...")
            
            # Remove everything else first (Standard cleanup) to minimize BRep size
            gmsh.model.occ.synchronize()
            keep_entities = {(3, self.volume_tag)}
            all_entities = gmsh.model.getEntities()
            to_remove = [e for e in all_entities if e not in keep_entities and e[0] <= 2] # Remove only < Dim 3 first
            if to_remove:
                gmsh.model.occ.remove(to_remove, recursive=False)
            gmsh.model.occ.synchronize()

            # Export BRep
            temp_brep = "temp_clean.brep"
            gmsh.write(temp_brep)
            
            # RESET GMSH
            # Note: gmsh.clear() clears the current model data but keeps the session
            gmsh.clear() 
            
            # Re-import
            # print("Reloading clean BRep...")
            gmsh.model.occ.importShapes(temp_brep)
            gmsh.model.occ.synchronize()
            
            # Cleanup temp file
            if os.path.exists(temp_brep):
                os.remove(temp_brep)

            # Get the new volume tag (should be 1)
            vols = gmsh.model.getEntities(3)
            if len(vols) == 1:
                self.volume_tag = vols[0][1]
                # print(f"BRep Isolation Successful. New Volume Tag: {self.volume_tag}")
                
                 # ----------------------------------------------------
                # Heal AGAIN after re-import to merge tolerances
                # ----------------------------------------------------
                # print("Running Post-Import Heal and Topology Simplification...")
                
                # 1. Remove Duplicates (Geometry Level)
                gmsh.model.occ.removeAllDuplicates()
                gmsh.model.occ.synchronize()

                # 2. Heal
                try:
                    healed = gmsh.model.occ.healShapes([(3, self.volume_tag)],
                                                        tolerance=1e-5, # Tighter tolerance
                                                        fixDegenerated=True,
                                                        fixSmallEdges=True,
                                                        fixSmallFaces=True,
                                                        # fixOrientation=True, # Error: Not supported in Python API wrapper?
                                                        sewFaces=True,
                                                        makeSolids=True)
                    if healed and healed[0][0] == 3:
                        self.volume_tag = healed[0][1]
                        # print(f"Post-Import Heal Successful. Tag: {self.volume_tag}")
                except Exception as e:
                    pass
                    # print(f"Post-Import Heal warning: {e}")
                
                gmsh.model.occ.synchronize()

                # Check Mass
                mass = gmsh.model.occ.getMass(3, self.volume_tag)
                # print(f"Volume Mass: {mass}")
                
                # Check Topology
                # Note: getBoundary with recursive=True returns (Dim, Tag) tuples.
                boundaries = gmsh.model.getBoundary([(3, self.volume_tag)], recursive=True)
                edge_tags = [e[1] for e in boundaries if e[0] == 1]
                # print(f"Topology Check: Solid has {len(edge_tags)} edges.")
                if len(edge_tags) > 3:
                    pass
                    # print("Warning: More than 3 edges (Top, Bottom, Seam). Topology might be split.")

                # ----------------------------------------------------
                # FINAL CLEANUP: Purge residue from Healing
                # ----------------------------------------------------
                # Healing might create new faces and leave old ones as orphans.
                # We identify ONLY the current solid and its children, delete rest.
                
                keep_set = set()
                keep_set.add((3, self.volume_tag))
                
                # Recursive descendants (Faces, Edges, Vertices)
                sub_shapes = gmsh.model.getBoundary([(3, self.volume_tag)], recursive=True)
                for dim, tag in sub_shapes:
                    keep_set.add((dim, tag))
                    
                # Get all entities
                candidates = gmsh.model.getEntities()
                
                to_delete = []
                for dim, tag in candidates:
                    if (dim, tag) not in keep_set:
                        to_delete.append((dim, tag))
                
                if to_delete:
                    # print(f"Post-Heal Cleanup: Removing {len(to_delete)} orphan entities.")
                    gmsh.model.occ.remove(to_delete, recursive=False)
                    gmsh.model.occ.synchronize()
                
                # [REMOVED] Physical Group
                # We do NOT add PhysicalGroup. 
                # Experience shows Abaqus treats PhysicalGroups as Sets/Surfaces rather than the native Part.
                # ptag = gmsh.model.addPhysicalGroup(3, [self.volume_tag])
                # gmsh.model.setPhysicalName(3, ptag, "BSplineSolid")
                
            else:
                # print(f"Error: Reloaded BRep contains {len(vols)} volumes!")
                self.volume_tag = vols[0][1] if vols else None

            # Final Sanity Check LOG
            # print("--- Post-Isolation Entity Check ---")
            # for dim in range(4):
            #     ents = gmsh.model.getEntities(dim)
            #     print(f"Dim {dim}: {len(ents)} entities -> {[e[1] for e in ents]}")
                
            return self.volume_tag

        if self.volume_tag is None:
             print("Warning: Failed to create solid. Returning surface elements.")
             return side_surface # Fallback
    
    def export_step(self, filename):
        """导出 STEP 文件"""
        try:
            gmsh.write(filename)
            print(f"Successfully exported to {filename}")
            return True
        except Exception as e:
            print(f"Export failed: {e}")
            return False
    
    def finalize(self):
        """清理 Gmsh 资源"""
        gmsh.finalize()
    
    def visualize(self):
        """启动 Gmsh GUI 进行可视化（可选）"""
        gmsh.fltk.run()



class BspInterface(BaseInterface):
    """
    Class to handle the B-spline surface interface.
    """

    def __init__(self, surface: BSP_Surf, init_size: float, symmetric = [0], MaxR = 0.2, MaxFF = 0.1, MaxC = 1.0):
        super().__init__(surface, symmetric)
        self.model = surface
        RRuu, RRuv, RRvu, RRvv = surface.get_surface_value(derivatives=0)[0][-4:]
        
        self.MaxR = MaxR
        self.MaxFF = MaxFF
        self.MaxC = MaxC

        lengthU = (2 * surface.num_points[0] * init_size)**2
        lengthV = (2 * surface.num_points[1] * init_size)**2
        
        self.init_size = init_size

        RRuu /= lengthU
        RRuv /= lengthV
        RRvu /= lengthU
        RRvv /= lengthV

        self.rr_compensation = torch.ones(4, RRuu.shape[0])
        self.rr_compensation[0, RRuu > MaxR *
                                0.2] = MaxR * 0.2 / RRuu[RRuu > MaxR * 0.2]
        self.rr_compensation[0] /= lengthU
        self.rr_compensation[1, RRuv > MaxR *
                                0.2] = MaxR * 0.2 / RRuv[RRuv > MaxR *
                                                        0.2] / lengthV
        self.rr_compensation[1] /= lengthV
        self.rr_compensation[2, RRvu > MaxR *
                                0.2] = MaxR * 0.2 / RRvu[RRvu > MaxR *
                                                        0.2] / lengthU
        self.rr_compensation[2] /= lengthU
        self.rr_compensation[3, RRvv > MaxR *
                                0.2] = MaxR * 0.2 / RRvv[RRvv > MaxR *
                                                        0.2] / lengthV
        self.rr_compensation[3] /= lengthV

        self.flip: bool = False
    
    def reinitialize(self):
        self.model.symmetric_reinitialize()
    
    @property
    def surf_type(self) -> int:
        return 0
    
    @property
    def num_variables(self) -> int:
        """
        Get the number of design variables.

        Returns:
            int: The number of design variables.
        """
        return self.model.control_points.numel()

    @property
    def control_points(self) -> torch.Tensor:
        """
        Get the control points of the B-spline surface.

        Returns:
            torch.Tensor: The control points of the B-spline surface.
        """
        return self.model.control_points
    
    @control_points.setter
    def control_points(self, x: torch.Tensor) -> None:
        """
        Set the control points of the B-spline surface.

        Parameters:
            x (torch.Tensor): The new control points to be set.
        """
        self.model.control_points = x.reshape(self.model.control_points.shape)
    
    @staticmethod
    def output_stp_file(control_points, degree_u, degree_v, path_output, name_output):
        generator = BSplineSolidGenerator(P0=control_points, degree_u=degree_u, degree_v=degree_v)
        generator.build()
        output_file = path_output + name_output + '.stp'
        generator.export_step(output_file)
        generator.finalize()

    def output_data(self, path_output, name_output, seed_size=-1, flip=False):
        flip = not flip

        
        pools = morphopt.controller.pools
        result = pools.apply_async(self.output_stp_file, args=(self.model.control_points.detach().cpu().numpy(),
                                                  self.model.degree,
                                                    self.model.degree,
                                                    path_output,
                                                    name_output))
        result.get()

        with open(path_output + '__FEM' + name_output + '.csv', 'w') as f:
            num_points = 10
            length = 0.1
            info = ''

            # for head surface search
            head = self.model.map(torch.tensor([[1, 1], [0.7, 0.2]]))
            vec = self.model.map(torch.tensor([[1, 1], [0.7, 0.2]]),
                        derivative=[0, 1])
            vv = torch.sqrt(torch.sum(vec**2, dim=0))
            vec /= vv
            info += '%e, %e, %e\n' % (head[0, 0] + length * vec[1, 0] *
                                    (1 - 2 * int(flip)),
                                    head[1, 0] - length * vec[0, 0] *
                                    (1 - 2 * int(flip)), head[2, 0])
            info += '%e, %e, %e\n' % (head[0, 1] + length * vec[1, 1] *
                                    (1 - 2 * int(flip)),
                                    head[1, 1] - length * vec[0, 1] *
                                    (1 - 2 * int(flip)), head[2, 1])

            # for bottom surface search
            bottom = self.model.map(torch.tensor([[0, 0], [0.7, 0.2]]))
            vec = self.model.map(torch.tensor([[0, 0], [0.7, 0.2]]),
                        derivative=[0, 1])
            vv = torch.sqrt(torch.sum(vec**2, dim=0))
            vec /= vv
            info += '%e, %e, %e\n' % (bottom[0, 0] + length * vec[1, 0] *
                                    (1 - 2 * int(flip)),
                                    bottom[1, 0] - length * vec[0, 0] *
                                    (1 - 2 * int(flip)), bottom[2, 0])
            info += '%e, %e, %e\n' % (bottom[0, 1] + length * vec[1, 1] *
                                    (1 - 2 * int(flip)),
                                    bottom[1, 1] - length * vec[0, 1] *
                                    (1 - 2 * int(flip)), bottom[2, 1])

            U = torch.arange(num_points) / num_points
            V = 0.5 * torch.ones_like(U)

            lateral = self.model.map((V, U))

            for i in range(num_points):
                info += "%e, %e, %e\n" % tuple(lateral[:, i])

            f.write(info)

        return name_output + '.stp'
    

    def match_points_surface(self, points: torch.Tensor) -> torch.Tensor:
        
        # get the initial guess
        points_init = self.model.map().cpu()

        distance_init = (points.reshape([3, 1, -1]).cpu() - points_init.reshape([3, -1, 1]).cpu()).norm(dim=0)
        index_init = torch.argmin(distance_init, dim=0)
        del distance_init

        uv_init = self.model.coordinates.reshape([2, -1])[:, index_init].detach().clone().requires_grad_()
        opt = torch.optim.Adam([uv_init], lr=0.01)
        for i in range(100):
            opt.zero_grad()
            surface_points = self.model.map(uv_init)
            loss = ((surface_points - points)**2).sum()
            loss.backward()
            opt.step()

        self._coordinates_fea = uv_init.detach().to(points.device)

    def refine_fea_mesh(self, part, surf_index, nodes_new):

        default_device = torch.tensor(0).device

        from ..utils import mesh
        nodes_new = nodes_new.copy()
        def refine_part_mesh(name: str):
            surface_head_nodes = np.sort(list(part.sets_nodes['surface_%d_%s' % (surf_index, name)]))
            surface_head_elems = part.surfaces_tri['surface_%d_All' % surf_index]
            surface_head_elems_remain = np.where(
                np.isin(surface_head_elems, surface_head_nodes).sum(axis=1) == 3)[0]
            surface_head_elems = surface_head_elems[surface_head_elems_remain]

            new_nodes = mesh.edge_length_regularization_surf3D(nodes0=torch.from_numpy(nodes_new.T).to(default_device), 
                                                        elements=torch.from_numpy(surface_head_elems).to(torch.int64).to(default_device),)
            nodes_new[surface_head_nodes] = new_nodes.cpu().numpy().T[surface_head_nodes]
        refine_part_mesh('Head')
        refine_part_mesh('Bottom')
        return nodes_new


    def get_surface_parameters(self) -> torch.Tensor:
        """
        Get the design variables of the surface.

        Returns:
            torch.Tensor: The design variables of the surface.
        """
        return self.model.control_points
    
    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """
        Set the design variables of the surface.

        Parameters:
            x (torch.Tensor): The new design variables to be set.
        """
        self.model.control_points = x.reshape(self.model.control_points.shape)
        self.model.symmetric_reinitialize()

    def update_variables(self, x_change):
        
        x_change = x_change.reshape_as(self.model.control_points)

        x_change[2, :5, :] = 0
        x_change[2, -5:, :] = 0

        x_change[:, 0, :] = 0
        x_change[:, -1, :] = 0
        
        self.model.control_points = self.model.control_points + x_change.reshape(self.model.control_points.shape)
    
    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get the geometry values of the surface.

        Returns:
            tuple: A tuple containing the geometry values of the surface.
                - r (torch.Tensor): The point coordinates of the surface.
                - rdu (torch.Tensor): The partial derivatives of the surface.
                - rdu2 (torch.Tensor): The second partial derivatives of the surface.
        """
        return self.model._partial_derivative(derivative=2)[0]

    def get_penalty_fairness(self, weight: torch.Tensor, r: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor) -> torch.Tensor:
        
        Normal0 = torch.cross(rdu[:, 1], rdu[:, 0], dim=0)
        Normal = Normal0 / torch.sqrt(torch.sum(Normal0**2, dim=0))

        I = torch.einsum('imp, inp->mnp', rdu, rdu)
        invI = I.permute([2, 0, 1]).inverse().permute([1, 2, 0])
        II = torch.einsum('imnp, ip->mnp', rdu2, Normal)

        detI = I[0, 0] * I[1, 1] - I[0, 1] * I[1, 0]
        detII = II[0, 0] * II[1, 1] - II[0, 1] * II[1, 0]

        H = 0.5 * (invI * II).sum([0, 1])
        K = detII / detI

        C0 = 4 * H**2 - 2 * K
        
        F = I[0, 1]
        E = I[0, 0]
        G = I[1, 1]
        FF0 = I[0, 1] * I[1, 0] / I[1, 1] / I[0, 0]

        Iu = torch.einsum('iuwp, ivp->uvwp', rdu2, rdu) + \
                torch.einsum('iup, ivwp->uvwp', rdu, rdu2)

        RRuu0 = Iu[0, 0, 0]**2 / E**2
        RRuv0 = Iu[0, 0, 1]**2 / E**2
        RRvu0 = Iu[1, 1, 0]**2 / G**2
        RRvv0 = Iu[1, 1, 1]**2 / G**2

        indexC, C = self.barrier_function(C0, self.MaxC, 0.8,
                                                    3)
        
        indexFF, FF = self.barrier_function(
            FF0, self.MaxFF, 0.8, 3)
        indexRRuu, RRuu = (self.barrier_function(
            RRuu0 * self.rr_compensation[0], self.MaxR, 0.8,
            3))
        indexRRuv, RRuv = (self.barrier_function(
            RRuv0 * self.rr_compensation[1], self.MaxR, 0.8,
            3))
        indexRRvu, RRvu = (self.barrier_function(
            RRvu0 * self.rr_compensation[2], self.MaxR, 0.8,
            3))
        indexRRvv, RRvv = (self.barrier_function(
            RRvv0 * self.rr_compensation[3], self.MaxR, 0.8,
            3))

        return (weight[indexC] * C).sum() + \
            (weight[indexFF] * FF).sum() + \
            (weight[indexRRuu] * RRuu).sum() + \
            (weight[indexRRuv] * RRuv).sum() + \
            (weight[indexRRvu] * RRvu).sum() + \
            (weight[indexRRvv] * RRvv).sum()

    def get_points_weight(self):
        
        R0 = self.model._partial_derivative(derivative=0)[0][0]
        
        R_now = R0.reshape([
            3, self.model.coordinates.shape[1],
            self.model.coordinates.shape[2]
        ])
        R_uplus = R_now.roll(-1, dims=2)

        R_vplus = R_now[:, 1:]
        R_now = R_now[:, :-1]
        R_uvplus = R_uplus[:, 1:]
        R_uplus = R_uplus[:, :-1]

        area1 = torch.cross(R_vplus - R_now, R_uplus - R_now,
                            dim=0).norm(dim=0) / 2
        area2 = torch.cross(R_uvplus - R_uplus,
                            R_uvplus - R_vplus,
                            dim=0).norm(dim=0) / 2

        ratio_now = torch.zeros_like(self.model.coordinates[0])

        ratio_now[:-1] += area1 / 3
        ratio_now[1:] += area1 / 3 + area2 / 3
        ratio_now[:-1, (torch.arange(ratio_now.shape[1]) + 1) %
                ratio_now.shape[1]] += area1 / 3 + area2 / 3
        ratio_now[1:, (torch.arange(ratio_now.shape[1]) + 1) %
                ratio_now.shape[1]] += area2 / 3

        return ratio_now.flatten()

    def save(self, filename):
        self.model.save_to_file(filename + '.txt')

    def load(self, filename):
        self.model = self.model.load_from_file(filename + '.txt')
        self.model.pre_load(
            [self.model.num_points[0] * 2, self.model.num_points[1] * 2])

    def get_mesh(self):
        import pyvista as pv
        u = torch.linspace(0, 1, self.model.num_points[0] * 2)
        v = torch.linspace(0, 1, self.model.num_points[1] * 2)
        [U, V] = torch.meshgrid(u, v, indexing='ij')
        result = self.model.map([U, V]).cpu().numpy()
        
        # Convert to numpy arrays for PyVista
        x = result[0]
        y = result[1]
        z = result[2]
        
        # Create structured grid
        grid = pv.StructuredGrid(x, y, z)
        mesh = grid.extract_surface()
        mesh.compute_normals(inplace=True)
        
        return mesh


    @classmethod
    def initialize_cylinder(cls, r0: float, length: float, seed_size: float, flip: bool, num_U_ratio: int = 1, num_V_ratio: int = 1, symmetric: list[int] = [0], degree = 4, init_location = [0.,0.,0.], maxR = 0.2, maxC = 1., maxFF = 0.2, perturbation_L = -1.):    
        """
        Initialize the B-spline surface for the optimization process.

        Parameters:
            r0 (float): The radius of the cylinder.
            length (float): The length of the cylinder.
            seed_size (float): The size of the seed for the B-spline surface.
            num_U_ratio (int, optional): The ratio for the number of points in the U direction. Default is 1.
            num_V_ratio (int, optional): The ratio for the number of points in the V direction. Default is 1.
            symmetric (list[int]): The symmetry of the surface.
            flip (bool): Whether to flip the surface or not.
            degree (int, optional): The degree of the B-spline surface. Default is 4.
            init_location (list[float], optional): The initial location of the surface. Default is [0., 0., 0.].
            maxR (float, optional): The maximum radius for the pre-loading. Default is 0.2.
            maxC (float, optional): The maximum curvature for the pre-loading. Default is 1.0.
            maxFF (float, optional): The maximum fairness factor for the pre-loading. Default is 0.2.
            perturbation_L (float, optional): The perturbation length for the surface. Default is -1. If < 0, no perturbation is applied.

        Returns:
            BSP (BSP_Surf): The initialized B-spline surface object.
            surf_type (int): The type of the surface (0 for B-spline surface).
            symmetric (list[int]): The symmetry of the surface.
        """

        numU = round(r0 * 2 * np.pi / seed_size)
        numV = round(length / seed_size)

        numU = round(numU / 12) * 12

        numU = round(numU / num_U_ratio) * num_U_ratio
        numV = round(numV / num_V_ratio) * num_V_ratio

        P0 = torch.zeros(3, numV, numU)

        x = torch.linspace(0, 1, numU + 1)[:-1]
        y = torch.linspace(0, 1, numV)

        [y, x] = torch.meshgrid(y, x, indexing='ij')
        theta = 2 * torch.pi * x + (1 / numU) * torch.pi

        if flip != 0:
            theta = -theta

        P0[0] = torch.cos(theta) * r0
        P0[1] = torch.sin(theta) * r0
        P0[2] = length * y

        # Apply perturbation if specified
        if perturbation_L > 0:
            r = torch.sqrt(P0[0]**2 + P0[1]**2)
            r_new = (1 + 0.04*torch.cos(2*(P0[2] / length) * np.pi * (length/perturbation_L))) * r0
            P0[0] *= r_new / r
            P0[1] *= r_new / r

        bsp = BSP_Surf(P0, degree, [[0, 0], [2, 2]])
        

        bsp._symmetric = symmetric
        bsp.control_points += torch.tensor(init_location).reshape([3, 1, 1])

        bsp.symmetric_reinitialize()

        bsp.control_points.data[
            2, 0, :] = init_location[2]
        bsp.control_points.data[2, -1, :] = init_location[2] + length

        bsp.pre_load([bsp.num_points[0] * 2, bsp.num_points[1] * 2])

        output = cls(bsp, init_size=seed_size, symmetric=symmetric, MaxR=maxR, MaxC=maxC, MaxFF=maxFF)
        output.flip = flip

        return output