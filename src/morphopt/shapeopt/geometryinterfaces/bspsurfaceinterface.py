
import os
import numpy as np
import torch
import gmsh

import morphopt

from .basesurfaceinterface import CpBasedInterface
import bspmap





class BspInterface(CpBasedInterface):
    """
    Class to handle the B-spline surface interface.
    """
    class BSplineSolidGenerator:
        def __init__(self, P0, degree_u=3, degree_v=3):
            """
            初始化 B-Spline 实体生成器 (使用 Gmsh)
            
            参数:
                P0: numpy array, shape (numV, numU, 3). 
                    代表控制点 (Poles). 
                    注意: U方向应为非重复的唯一控制点 (Periodic).
                degree_u: U方向次数（多项式最高次数，如degree=3表示三次B样条）
                degree_v: V方向次数（多项式最高次数，如degree=3表示三次B样条）
            """
            self.P0 = P0
            self.degree_u = degree_u
            self.degree_v = degree_v
            self.volume_tag = None
            
        def build(self):
            """
            构建版本 - 改用 addBSplineSurface + Wrapping + Trim
            通过上下游双重延伸(Padding)确保接缝处C2连续性
            """
            self.volume_tag = None
            
            # 初始化 Gmsh
            gmsh.initialize()
            gmsh.option.setNumber("General.Terminal", 0) # Suppress Gmsh output
            gmsh.option.setNumber("General.Verbosity", 0)
            gmsh.model.add("bspline_solid")
            
            # 获取维度
            num_poles_v = self.P0.shape[0]
            num_poles_u_raw = self.P0.shape[1]
            du = self.degree_u
            dv = self.degree_v
            
            # ----------------------------------------------------
            # 0. Sanitize Input (Check for explicit closure)
            # ----------------------------------------------------
            # 用户可能传入了闭合的控制点序列 (P_start == P_end)
            # B-Spline 周期性数学构造需要唯一控制点序列。
            # 如果发现首尾重合，去掉最后一个。
            
            # 检查第一行即可
            p_start = self.P0[0, 0]
            p_end = self.P0[0, -1]
            dist = np.linalg.norm(p_start - p_end)
            
            if dist < 1e-6:
                # print("Detecting closed input poles (Start == End). Removing last pole for periodic construction.")
                poles_to_use = self.P0[:, :-1]
            else:
                poles_to_use = self.P0
                
            num_poles_u = poles_to_use.shape[1]
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
                    pt = poles_to_use[j, i, :]
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


    def __init__(self, surface: bspmap.BSP, init_size: float, MaxR = 0.2, MaxFF = 0.1, MaxC = 1.0):
        super().__init__(surface)

        self.model = surface
        """The B-spline surface model."""

        self._cps = torch.from_numpy(self.model.control_points).to(torch.get_default_device())
        
        self.MaxR = MaxR
        self.MaxFF = MaxFF
        self.MaxC = MaxC

        self.init_size = init_size


        self.rr_compensation: torch.Tensor

        self._preload_size: tuple[int, int]
        """The preloaded size of the UV grid."""

    def synchronize(self):
        self.model._control_points = self._cps.detach().cpu().numpy()

    def map(self, uv: torch.Tensor) -> torch.Tensor:
        """Map from UV space to 3D space using the B-spline surface model."""
        uv_np = uv.detach().cpu().numpy().reshape(-1, 2)
        weights, indices = self.model.get_weights(uv_np, derivative=[0,0])

        indices_cps = torch.from_numpy(indices).to(torch.get_default_device()).reshape([uv.shape[0], -1])
        indices_pts = torch.arange(uv.shape[0], device=torch.get_default_device()).reshape([-1,1]).repeat(1, indices_cps.shape[1])
        indices = torch.stack([indices_pts, indices_cps], dim=0).reshape(2, -1)


        return self._map(torch.from_numpy(weights).to(torch.get_default_device()).flatten(), indices, num_pts=uv.shape[0])

    def get_normals(self, uv: torch.Tensor) -> torch.Tensor:
        """Get the normals of the surface at the given UV coordinates."""
        uv_np = uv.detach().cpu().numpy().reshape(-1, 2)
        weightsdu, indices = self.model.get_weights(uv_np, derivative=[1,0])
        weightsdv, _ = self.model.get_weights(uv_np, derivative=[0,1])

        indices_cps = torch.from_numpy(indices).to(torch.get_default_device()).reshape([uv.shape[0], -1])
        indices_pts = torch.arange(uv.shape[0], device=torch.get_default_device()).reshape([-1,1]).repeat(1, indices_cps.shape[1])
        indices = torch.stack([indices_pts, indices_cps], dim=0).reshape(2, -1)

        rdu = self._map(torch.from_numpy(weightsdu).to(torch.get_default_device()).flatten(), indices, num_pts=uv.shape[0])
        rdv = self._map(torch.from_numpy(weightsdv).to(torch.get_default_device()).flatten(), indices, num_pts=uv.shape[0])
        normals = torch.cross(rdv, rdu, dim=1)
        normals = normals / torch.norm(normals, dim=1, keepdim=True)
        return normals * (1 if self.flip else -1)

    def initialize(self):

        self.pre_load()
        
        # initialize fairness compensation
        RRuu, RRuv, RRvu, RRvv = self._geofair_data(r=self.get_r(), 
                                                    rdu=self.get_rdu(), 
                                                    rdu2=self.get_rdu2())[-4:]
        


        lengthU = (2 * self.model.size[0] * self.init_size)**2
        lengthV = (2 * self.model.size[1] * self.init_size)**2
        
        
        RRuu /= lengthU
        RRuv /= lengthV
        RRvu /= lengthU
        RRvv /= lengthV

        self.rr_compensation = torch.ones(4, RRuu.shape[0])
        self.rr_compensation[0, RRuu > self.MaxR *
                                0.2] = self.MaxR * 0.2 / RRuu[RRuu > self.MaxR * 0.2]
        self.rr_compensation[0] /= lengthU
        self.rr_compensation[1, RRuv > self.MaxR *
                                0.2] = self.MaxR * 0.2 / RRuv[RRuv > self.MaxR *
                                                        0.2] / lengthV
        self.rr_compensation[1] /= lengthV
        self.rr_compensation[2, RRvu > self.MaxR *
                                0.2] = self.MaxR * 0.2 / RRvu[RRvu > self.MaxR *
                                                        0.2] / lengthU
        self.rr_compensation[2] /= lengthU
        self.rr_compensation[3, RRvv > self.MaxR *
                                0.2] = self.MaxR * 0.2 / RRvv[RRvv > self.MaxR *
                                                        0.2] / lengthV
        self.rr_compensation[3] /= lengthV

    def pre_load(self, pre_points: torch.Tensor = None, faces: torch.Tensor = None) -> None:
        preload_data = self.get_preloaddata(pre_points=pre_points, faces=faces)
        self.apply_preload_data(preload_data)

    def get_preloaddata(self, pre_points: torch.Tensor = None, faces: torch.Tensor = None):

        if pre_points is None and faces is None:
            # preload the uv grid
            ratio = 2
            preload_size = (self.model.size[0] * ratio, self.model.size[1] * ratio)

            uvgrids = np.meshgrid(np.linspace(0, 1, preload_size[0]), np.linspace(0, 1, preload_size[1]+1)[1:], indexing='ij')
            pts_np = np.stack(uvgrids, axis=-1).reshape([-1, 2])
            preload_uv = torch.tensor(np.stack([uvgrids[0].reshape([-1]), uvgrids[1].reshape([-1])], axis=1), dtype=torch.float64).to(torch.get_default_device())
            
            # Build square-grid faces for the structured UV sampling grid
            num_u, num_v = preload_size
            faces_list = []
            for iu in range(num_u - 1):
                for iv in range(num_v - 1):
                    idx00 = iu * num_v + iv
                    idx01 = iu * num_v + (iv + 1)
                    idx10 = (iu + 1) * num_v + iv
                    idx11 = (iu + 1) * num_v + (iv + 1)
                    faces_list.append([idx00, idx01, idx11, idx10])
            faces = torch.tensor(faces_list, dtype=torch.long, device=torch.get_default_device())
        else:
            preload_uv = pre_points
            pts_np = pre_points.detach().cpu().numpy()

        _weights, indices = self.model.get_weights(pts_np, derivative=[0,0])
        _weights_du = self.model.get_weights(pts_np, derivative=[1,0])[0]
        _weights_du2 = self.model.get_weights(pts_np, derivative=[2,0])[0]
        _weights_dv = self.model.get_weights(pts_np, derivative=[0,1])[0]
        _weights_dv2 = self.model.get_weights(pts_np, derivative=[0,2])[0]
        _weights_dudv = self.model.get_weights(pts_np, derivative=[1,1])[0]

        indices_cps = torch.from_numpy(indices).to(torch.get_default_device()).reshape([preload_uv.shape[0], -1])
        indices_pts = torch.arange(preload_uv.shape[0], device=torch.get_default_device()).reshape([-1,1]).repeat(1, indices_cps.shape[1])
        indices = torch.stack([indices_pts, indices_cps], dim=0).reshape(2, -1)

        preload_data = self.PreLoadData(
            uv=preload_uv,
            cp_weights=torch.from_numpy(_weights).to(torch.get_default_device()).flatten(),
            cp_weights_du=torch.from_numpy(_weights_du).to(torch.get_default_device()).flatten(),
            cp_weights_dv=torch.from_numpy(_weights_dv).to(torch.get_default_device()).flatten(),
            cp_weights_du2=torch.from_numpy(_weights_du2).to(torch.get_default_device()).flatten(),
            cp_weights_dudv=torch.from_numpy(_weights_dudv).to(torch.get_default_device()).flatten(),
            cp_weights_dv2=torch.from_numpy(_weights_dv2).to(torch.get_default_device()).flatten(),
            indices=indices,
            faces=faces,
        )

        return preload_data

    @staticmethod
    def output_stp_file(control_points, degree_u, degree_v, path_output, name_output):
        generator = BspInterface.BSplineSolidGenerator(P0=control_points, degree_u=degree_u, degree_v=degree_v)
        generator.build()
        output_file = path_output + '/' + name_output + '.stp'
        generator.export_step(output_file)
        generator.finalize()

    def output_data(self, path_output, name_output, seed_size=-1, flip=False):
        flip = not flip
        
        pools = morphopt.controller.pools
        result = pools.apply_async(self.output_stp_file, args=(self._cps.detach().cpu().numpy().reshape([
                                                    self.model.size[0],
                                                    self.model.size[1],
                                                    3]),
                                                  self.model.degree,
                                                    self.model.degree,
                                                    path_output,
                                                    name_output))
        result.get()

        return name_output + '.stp'

    def update_variables(self, x_change):
        
        x_change = x_change.reshape([self.model.size[0], self.model.size[1], 3])

        x_change[:5, :, 2] = 0
        x_change[-5:, :, 2] = 0

        x_change[0] = 0
        x_change[-1] = 0
        
        super().update_variables(x_change)

    def _geofair_data(self, r: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor):
        """
        To compute the geometric fairness data.

        Parameters:
            r (torch.Tensor): The surface points.
            rdu (torch.Tensor): The first derivatives of the surface points.
            rdu2 (torch.Tensor): The second derivatives of the surface points.

        Returns:
            C0 (torch.Tensor): The curvature-based fairness measure.
            FF0 (torch.Tensor): The first fundamental form-based fairness measure.
            RRuu0 (torch.Tensor): The second derivative in u direction-based fairness measure.
            RRuv0 (torch.Tensor): The mixed second derivative-based fairness measure.
            RRvu0 (torch.Tensor): The mixed second derivative-based fairness measure.
            RRvv0 (torch.Tensor): The second derivative in v direction-based fairness measure.
        """
        Normal0 = torch.cross(rdu[:, :, 1], rdu[:, :, 0], dim=1)
        Normal = Normal0 / torch.sqrt(torch.sum(Normal0**2, dim=1, keepdim=True))

        I = torch.einsum('pim, pin->pmn', rdu, rdu)
        invI = I.inverse()
        II = torch.einsum('pimn, pi->pmn', rdu2, Normal)

        detI = I[:, 0, 0] * I[:, 1, 1] - I[:, 0, 1] * I[:, 1, 0]
        detII = II[:, 0, 0] * II[:, 1, 1] - II[:, 0, 1] * II[:, 1, 0]

        H = 0.5 * (invI * II).sum([1, 2])
        K = detII / detI

        C0 = 4 * H**2 - 2 * K
        
        F = I[:, 0, 1]
        E = I[:, 0, 0]
        G = I[:, 1, 1]
        FF0 = I[:, 0, 1] * I[:, 1, 0] / I[:, 1, 1] / I[:, 0, 0]

        Iu = torch.einsum('piuw, piv->puvw', rdu2, rdu) + \
                torch.einsum('piu, pivw->puvw', rdu, rdu2)

        RRuu0 = Iu[:, 0, 0, 0]**2 / E**2
        RRuv0 = Iu[:, 0, 0, 1]**2 / E**2
        RRvu0 = Iu[:, 1, 1, 0]**2 / G**2
        RRvv0 = Iu[:, 1, 1, 1]**2 / G**2

        return C0, FF0, RRuu0, RRuv0, RRvu0, RRvv0

    def get_penalty_fairness(self, weight: torch.Tensor, r: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor) -> torch.Tensor:
    
        C0, FF0, RRuu0, RRuv0, RRvu0, RRvv0 = self._geofair_data(r, rdu, rdu2)

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
        """Get vertex-based integration weights for the preload mesh."""
        r = self.get_r().detach()
        return self.preload_data.compute_point_weights(r)

    def save(self, filename):
        self.model.control_points = self._cps.detach().cpu().numpy()
        self.model.save(filename)

    def load(self, filename):
        self.model = bspmap.BSP.load(filename + '.npz')
        self._cps = torch.from_numpy(self.model.control_points).to(torch.get_default_device())

    def get_mesh(self):
        import pyvista as pv
        ratio = 2
        preload_size = (self.model.size[0] * ratio, self.model.size[1] * ratio)

        uvgrids = np.meshgrid(np.linspace(0, 1, preload_size[0]), np.linspace(0, 1, preload_size[1]+1)[1:], indexing='ij')
        pts_np = np.stack(uvgrids, axis=-1).reshape([-1, 2])

        self.model.control_points = self._cps.detach().cpu().numpy().reshape([-1, 3])

        r = self.model.map(pts_np, derivative=[0, 0]).reshape([preload_size[0], preload_size[1], 3])
        
        # Convert to numpy arrays for PyVista
        x = r[:, :, 0]
        y = r[:, :, 1]
        z = r[:, :, 2]


        x = np.concatenate([x, x[:, :1]], axis=1)
        y = np.concatenate([y, y[:, :1]], axis=1)
        z = np.concatenate([z, z[:, :1]], axis=1)
        
        # Create structured grid
        grid = pv.StructuredGrid(x, y, z)
        mesh = grid.extract_surface(algorithm='dataset_surface')
        mesh.compute_normals(inplace=True)
        
        return mesh


    @classmethod
    def initialize_cylinder(cls, r0: float, length: float, seed_size: float, flip: bool, num_U_ratio: int = 1, num_V_ratio: int = 1, degree = 3, init_location = [0.,0.,0.], maxR = 0.2, maxC = 1., maxFF = 0.2, perturbation_L = -1.):    
        """
        Initialize the B-spline surface for the optimization process.

        Parameters:
            r0 (float): The radius of the cylinder.
            length (float): The length of the cylinder.
            seed_size (float): The size of the seed for the B-spline surface.
            num_U_ratio (int, optional): The ratio for the number of points in the U direction. Default is 1.
            num_V_ratio (int, optional): The ratio for the number of points in the V direction. Default is 1.
            flip (bool): Whether to flip the surface or not.
            degree (int, optional): The degree of the B-spline surface. Default is 3.
            init_location (list[float], optional): The initial location of the surface. Default is [0., 0., 0.].
            maxR (float, optional): The maximum radius for the pre-loading. Default is 0.2.
            maxC (float, optional): The maximum curvature for the pre-loading. Default is 1.0.
            maxFF (float, optional): The maximum fairness factor for the pre-loading. Default is 0.2.
            perturbation_L (float, optional): The perturbation length for the surface. Default is -1. If < 0, no perturbation is applied.

        Returns:
            BSP (BSP_Surf): The initialized B-spline surface object.
            surf_type (int): The type of the surface (0 for B-spline surface).
        """

        numU = round(r0 * 2 * np.pi / seed_size)
        numV = round(length / seed_size)

        numU = round(numU / 12) * 12

        numU = round(numU / num_U_ratio) * num_U_ratio
        numV = round(numV / num_V_ratio) * num_V_ratio

        P0 = torch.zeros(numV, numU, 3)

        x = torch.linspace(0, 1, numU + 1)[:-1]
        y = torch.linspace(0, 1, numV)

        [y, x] = torch.meshgrid(y, x, indexing='ij')
        theta = 2 * torch.pi * x + (1 / numU) * torch.pi

        P0[:, :, 0] = torch.cos(theta) * r0
        P0[:, :, 1] = torch.sin(theta) * r0
        P0[:, :, 2] = length * y
        # Apply perturbation if specified
        if perturbation_L > 0:
            r = torch.sqrt(P0[:, :, 0]**2 + P0[:, :, 1]**2)
            r_new = (1 + 0.04*torch.cos(2*(P0[:, :, 2] / length) * np.pi * (length/perturbation_L))) * r0
            P0[:, :, 0] *= r_new / r
            P0[:, :, 1] *= r_new / r

        basis_u = bspmap.BasisCircular(num_cps=numU, degree=degree)
        basis_v = bspmap.BasisClamped(num_cps=numV, degree=degree)



        P0 += torch.tensor(init_location)        
        P0.data[
            0, :, 2] = init_location[2]
        P0.data[-1, :, 2] = init_location[2] + length

        bsp = bspmap.BSP(basis=[basis_v, basis_u],
                         degree=degree,
                         size=[numV, numU],
                         control_points=P0.cpu().numpy().reshape([-1, 3]))

        output = cls(bsp, init_size=seed_size, MaxR=maxR, MaxC=maxC, MaxFF=maxFF)
        output.flip = flip

        return output

    def match_coordinates(self, surf_node_idx: np.ndarray, surf_nodes: np.ndarray, batch_size: int | None = None):
        """Find closest (u, v) on `bspsurf` for each 3D point in `nodes`.

        Improvements (memory-efficient):
        - use a KD-tree (if available) to find nearest initial grid seed without forming MxN distance matrix
        - perform Newton refinement in configurable batches to reduce peak memory
        - fallback to chunked search if scipy is not present
        """

        # filter out the head and bottom nodes

        bottom_z = self._cps[:, 2].min().item()
        top_z = self._cps[:, 2].max().item()

        idx_remain = (surf_nodes[:, 2] > bottom_z + 1e-5) & (surf_nodes[:, 2] < top_z - 1e-5)
        nodes = surf_nodes[idx_remain]
        self.surf_node_idx = surf_node_idx[idx_remain]


        nodes = np.asarray(nodes, dtype=float)
        if nodes.ndim == 1:
            nodes = nodes.reshape(1, 3)
        N = nodes.shape[0]

        num_U = self.model.size[1] + 1
        num_V = self.model.size[0]

        # initial sampling grid (same orientation as before)
        initgrid_V, initgrid_U = np.meshgrid(np.linspace(0, 1, num_V * 5),
                                            np.linspace(0, 1, num_U * 5)[:-1],
                                            indexing='ij')
        initpts = np.stack([initgrid_V.ravel(), initgrid_U.ravel()], axis=1)

        # evaluate surface at seed points (M x 3)
        r0 = self.model.map(initpts)

        # --- find nearest seed for each node (memory-efficient) ---
        try:
            # fast & memory-friendly when scipy is available
            import scipy.spatial as sp
            tree = sp.KDTree(r0)
            _, min_dist_uv_idx = tree.query(nodes, k=1)
        except Exception:
            # fallback: chunked search over nodes to avoid creating an MxN matrix
            min_dist_uv_idx = np.empty(N, dtype=int)
            node_chunk = 1024
            for i in range(0, N, node_chunk):
                j = min(N, i + node_chunk)
                nb = nodes[i:j]                                # (B, 3)
                # compute squared distances in a chunk (M, B)
                d2 = np.sum((r0[:, None, :] - nb[None, :, :]) ** 2, axis=2)
                min_dist_uv_idx[i:j] = np.argmin(d2, axis=0)

        min_dist_uv = initpts[min_dist_uv_idx]                  # (N, 2)

        # --- Newton refinement in batches (reduces peak memory) ---
        max_iter = 10
        tol = 1e-2
        
        if batch_size is None:
            batch_size = N if N <= 40960 else 40960

        uv_out = np.empty((N, 2), dtype=float)

        for start in range(0, N, batch_size):
            end = min(N, start + batch_size)
            uv = min_dist_uv[start:end].copy()
            pts = nodes[start:end]

            for it in range(max_iter):
                r = self.model.map(uv)
                ru = self.model.map(uv, derivative=[1, 0])
                rv = self.model.map(uv, derivative=[0, 1])
                ruu = self.model.map(uv, derivative=[2, 0])
                ruv = self.model.map(uv, derivative=[1, 1])
                rvv = self.model.map(uv, derivative=[0, 2])

                diff = r - pts
                gu = np.einsum('ij,ij->i', diff, ru)
                gv = np.einsum('ij,ij->i', diff, rv)
                gnorm = np.sqrt(gu * gu + gv * gv)

                if np.all(gnorm < tol):
                    break

                A = np.einsum('ij,ij->i', ru, ru) + np.einsum('ij,ij->i', diff, ruu)
                B = np.einsum('ij,ij->i', ru, rv) + np.einsum('ij,ij->i', diff, ruv)
                C = np.einsum('ij,ij->i', rv, rv) + np.einsum('ij,ij->i', diff, rvv)

                det = A * C - B * B
                det_reg = det.copy()
                det_reg[np.abs(det_reg) < 1e-12] = 1e-12

                du = -(C * gu - B * gv) / det_reg
                dv = -(-B * gu + A * gv) / det_reg
                delta = np.stack([du, dv], axis=1)

                f = np.einsum('ij,ij->i', diff, diff)

                uv_new = uv.copy()
                f_best = f.copy()
                accept = np.zeros(f.shape, dtype=bool)

                uv_step = np.clip(uv + delta, 0.0, 1.0)
                r_step = self.model.map(uv_step)
                f_step = np.einsum('ij,ij->i', (r_step - pts), (r_step - pts))
                improved = f_step < f_best
                if improved.any():
                    uv_new[improved] = uv_step[improved]
                    f_best[improved] = f_step[improved]
                    accept[improved] = True

                if not np.all(accept):
                    remaining = ~accept
                    for k in range(1, 8):
                        alpha = 0.5 ** k
                        uv_try = np.clip(uv + alpha * delta, 0.0, 1.0)
                        r_try = self.model.map(uv_try)
                        f_try = np.einsum('ij,ij->i', (r_try - pts), (r_try - pts))

                        improved = (f_try < f_best) & remaining
                        if improved.any():
                            uv_new[improved] = uv_try[improved]
                            f_best[improved] = f_try[improved]
                            accept[improved] = True
                            remaining = ~accept

                        if not remaining.any():
                            break

                uv = uv_new.copy()

                # print(f'Batch {start}-{end}, Iter {it}, Mean Residual {np.sqrt(f_best).mean():.3e}, Accept Rate {accept.mean():.2%}')

            uv_out[start:end] = uv
        self.surf_node_uv = uv_out

        return self.model.map(uv_out)