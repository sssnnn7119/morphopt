
import datetime
import glob
import math
import os
import shutil
import gmsh

import torchfea
import numpy as np
import torch

import morphopt
from .geometryinterfaces.basesurfaceinterface import BaseInterface
from ..base_params import BaseParams

class MeshGenerator:
    def __init__(self, mesh_size_min=None, mesh_size_max=None):
        # print("Initializing GMSH...")
        gmsh.initialize()
        gmsh.option.setNumber("General.NumThreads", 0) # Use all available cores
        gmsh.option.setNumber("General.Verbosity", 2)  # Errors only
        self.files_map = {}
        self.surface_tags_by_index = {}
        self.sorted_indices = []
        
        # Set mesh size options if provided
        if mesh_size_min is not None:
            # print(f"Setting Mesh.MeshSizeMin to {mesh_size_min}")
            gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size_min)
            
        if mesh_size_max is not None:
            # print(f"Setting Mesh.MeshSizeMax to {mesh_size_max}")
            gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size_max)
            

    def scan_directory(self, directory=None):
        if directory is None:
            directory = os.getcwd()
            
        # print(f"Scanning directory {directory} for files...")
        # Pattern: __surface-{number}.(stp|stl)
        import re
        pattern = re.compile(r'^__surface-(\d+)\.(stp|stl)$', re.IGNORECASE)
        
        self.files_map = {}
        for filename in os.listdir(directory):
            match = pattern.match(filename)
            if match:
                idx = int(match.group(1))
                self.files_map[idx] = os.path.join(directory, filename)
                # print(f"  Found: {filename} (Index: {idx})")
        
        if 0 not in self.files_map:
            raise FileNotFoundError("Base surface file (Index 0) not found. Need '__surface-0.stp' or '__surface-0.stl'.")
            
        self.sorted_indices = sorted(self.files_map.keys())
        # print(f"Processing indices: {self.sorted_indices}")

    def _get_all_surface_tags(self):
        return set(dim_tag[1] for dim_tag in gmsh.model.getEntities(2))

    def load_and_process_files(self):
        self.surface_tags_by_index = {}

        for idx in self.sorted_indices:
            filename = self.files_map[idx]
            # print(f"\n--- Processing Index {idx}: {filename} ---")
            
            # Snapshot current surfaces to identify new ones
            pre_surfaces = self._get_all_surface_tags()
            
            ext = os.path.splitext(filename)[1].lower()
            
            if ext in ['.stp', '.step']:
                # print("  Type: STP (CAD)")
                try:
                    # Import OCC
                    gmsh.model.occ.importShapes(filename)
                    gmsh.model.occ.synchronize()
                    
                    # Remove volumes, keep surfaces
                    vols = gmsh.model.getEntities(3)
                    if vols:
                        # print(f"  Found {len(vols)} volume(s) in STP. Removing volume entities, keeping surfaces...")
                        gmsh.model.occ.remove(vols, recursive=False)
                        gmsh.model.occ.synchronize()
                    
                except Exception as e:
                    raise RuntimeError(f"Error loading STP file {filename}: {e}")

            elif ext in ['.stl']:
                # print("  Type: STL (Discrete)")
                try:
                    gmsh.merge(filename)
                except Exception as e:
                    raise RuntimeError(f"Error loading STL file {filename}: {e}")
            
            # Identify newly added surfaces
            post_surfaces = self._get_all_surface_tags()
            new_surfaces = list(post_surfaces - pre_surfaces)
            
            if not new_surfaces:
                # print(f"  Warning: No surfaces found in {filename}.")
                pass
            else:
                # print(f"  Extracted {len(new_surfaces)} surface(s).")
                self.surface_tags_by_index[idx] = new_surfaces

    def construct_volume(self):
        # print("\n--- Constructing Volume ---")
        
        if 0 not in self.surface_tags_by_index or not self.surface_tags_by_index[0]:
            raise RuntimeError("Error: No surfaces available for base (Index 0).")

        loops = []
        
        # Process Base (0) first
        try:
            base_loop = gmsh.model.geo.addSurfaceLoop(self.surface_tags_by_index[0])
            loops.append(base_loop)
            # print("  Added outer surface loop (from Index 0).")
        except Exception as e:
            raise RuntimeError(f"Error creating outer loop: {e}")

        # Process Cavities (>0)
        for idx in self.sorted_indices:
            if idx == 0: continue
            tags = self.surface_tags_by_index.get(idx)
            if tags:
                try:
                    cavity_loop = gmsh.model.geo.addSurfaceLoop(tags)
                    loops.append(cavity_loop)
                    # print(f"  Added cavity loop (from Index {idx}).")
                except Exception as e:
                    raise RuntimeError(f"Error creating cavity loop for index {idx}: {e}")

        # Create Volume
        try:
            vol_tag = gmsh.model.geo.addVolume(loops)
            # print(f"  Created Volume Tag: {vol_tag}")
            gmsh.model.geo.synchronize()
            
            # Create Physical Volume
            gmsh.model.addPhysicalGroup(3, [vol_tag], name="Volume_All")
            
        except Exception as e:
            raise RuntimeError(f"Error creating volume: {e}")

    def generate_mesh(self, dim=3):
        # print("\n--- Meshing ---")
        try:
            gmsh.model.mesh.generate(dim)
        except Exception as e:
            raise RuntimeError(f"Error during meshing: {e}")

    def _generate_abaqus_surface_payload(self):
        """
        Generates the Abaqus SURFACE definition string by mapping 3D element faces
        to the geometric surfaces.
        """
        # print("  Generating Abaqus surface definitions...")

        # Get all 3D tetrahedron elements (Type 4 in GMSH)
        try:
            tet_tags, tet_node_tags = gmsh.model.mesh.getElementsByType(4)
        except:
            # print("  No 3D elements found.")
            return ""

        if len(tet_tags) == 0:
            return ""

        # Map faces to elements
        # Key: frozenset(3 nodes), Value: (element_tag, abaqus_face_id)
        # Abaqus C3D4 Face Defs (Nodes 1-4):
        # S1: 1, 2, 3
        # S2: 1, 4, 2
        # S3: 2, 4, 3
        # S4: 3, 4, 1
        
        # GMSH Tet4 Node Order: 0, 1, 2, 3
        # GMSH flattened check:
        # We need to ensure we use the correct nodes.
        # Assuming compact packing.
        
        face_map = {}

        # Use NumPy for vectorized operations
        tet_nodes = np.array(tet_node_tags).reshape(-1, 4)
        tet_tags_arr = np.array(tet_tags)

        # Nodes for each face definition
        # S1: (0, 1, 2), S2: (0, 3, 1), S3: (1, 3, 2), S4: (2, 3, 0)
        face_defs = [
            ([0, 1, 2], "S1"),
            ([0, 3, 1], "S2"),
            ([1, 3, 2], "S3"),
            ([2, 3, 0], "S4")
        ]

        for col_idx, face_name in face_defs:
            # Extract (N, 3)
            faces = tet_nodes[:, col_idx]
            # Create keys and update map
            for key, tag in zip(map(frozenset, faces), tet_tags_arr):
                face_map[key] = (tag, face_name)

        payload_lines = []
        
        # For each surface index, find which faces belong to it
        for idx, surf_tags in self.surface_tags_by_index.items():
            
            # Collect sets of elements for each face type
            sets_data = {
                "S1": [], "S2": [], "S3": [], "S4": []
            }
            
            found_count = 0
            
            # Set to collect unique node tags for this surface index
            surface_nodes = set()

            # Iterate over the geometric surfaces for this index
            for s_tag in surf_tags:
                # Get 2D elements (Triangles = Type 2) on this surface
                try:
                    tri_tags, tri_node_tags = gmsh.model.mesh.getElementsByType(2, tag=s_tag)
                except:
                    continue
                    
                n_tris = len(tri_tags)
                if n_tris == 0: continue
                
                for t in range(n_tris):
                    base = t * 3
                    tn0 = tri_node_tags[base]
                    tn1 = tri_node_tags[base+1]
                    tn2 = tri_node_tags[base+2]

                    # Add nodes to the set for NSET generation
                    surface_nodes.add(tn0)
                    surface_nodes.add(tn1)
                    surface_nodes.add(tn2)
                    
                    key = frozenset((tn0, tn1, tn2))
                    
                    if key in face_map:
                        etag, face_id = face_map[key]
                        sets_data[face_id].append(etag)
                        found_count += 1
            
            if found_count > 0:
                # print(f"    Mapped {found_count} faces for surface_{idx}_All")
                surf_name = f"surface_{idx}_All"
                
                # Create ELSETs for each face type
                active_faces = []
                for face_id, el_list in sets_data.items():
                    if el_list:
                        set_name = f"_{surf_name}_{face_id}"
                        active_faces.append(f"{set_name}, {face_id}")
                        
                        payload_lines.append(f"*ELSET, ELSET={set_name}, INTERNAL")
                        # Write IDs, 16 per line max usually, plain csv is fine
                        # Join with commas
                        # Chunking for niceness
                        chunk_size = 16
                        for k in range(0, len(el_list), chunk_size):
                            chunk = el_list[k:k+chunk_size]
                            line = ", ".join(str(e) for e in chunk)
                            payload_lines.append(line)
                
                # Create SURFACE definition
                payload_lines.append(f"*SURFACE, TYPE=ELEMENT, NAME={surf_name}")
                payload_lines.extend(active_faces)

                # Create NSET definition
                if surface_nodes:
                    payload_lines.append(f"*Nset, nset={surf_name}")
                    sorted_nodes = sorted(list(surface_nodes))
                    chunk_size = 16
                    for k in range(0, len(sorted_nodes), chunk_size):
                        chunk = sorted_nodes[k:k+chunk_size]
                        line = ", ".join(str(e) for e in chunk)
                        payload_lines.append(line)
        
        return "\n".join(payload_lines)

    def export(self, outfile="output.inp"):
        # print(f"\n--- Exporting to {outfile} ---")
        
        # 1. Generate the surface definition payload based on the mesh
        surface_payload = self._generate_abaqus_surface_payload()
        
        # 2. Write the standard GMSH output (Volume only)
        # Note: We do NOT have Physical Surfaces defined, so they won't be exported as elements.
        gmsh.write(outfile)
        
        # 3. Post-process to insert *Part and append surfaces
        # print("  Post-processing INP file...")
        with open(outfile, 'r') as f:
            lines = f.readlines()

        lines.insert(2, "*Part, name=final_model\n")
            
        # Append surface payload
        if surface_payload:
            lines.append("\n")
            lines.append(surface_payload)
            lines.append("\n")

        # end part
        lines.append("*End Part\n")
            
        # Write back
        with open(outfile, 'w') as f:
            f.writelines(lines)
            
    def finalize(self):
        gmsh.finalize()
        # print("Done.")

    @classmethod
    def run(cls, seed_size: float, output_file="output.inp", directory: str = None):
        generator = cls(mesh_size_max=seed_size*1.4,
                        mesh_size_min=seed_size*0.7)
        try:
            generator.scan_directory(directory=directory)
            generator.load_and_process_files()
            generator.construct_volume()
            generator.generate_mesh(3)
            generator.export(output_file)
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            generator.finalize()


class GeometryParams(BaseParams):
    """
    Class to handle the surfaces of the morphable model.
    """
    from .geometryinterfaces.cssurfaceinterface import CsInterface as CS
    from .geometryinterfaces.bspsurfaceinterface import BspInterface as BSP
    from .geometryinterfaces.cpgeosurfaceinterface import CPGEOSurfaceInterface as CPGEO

    def __init__(self, fea_seed_size: float, fea_mesh_order: int = 1, reinitialize_per_iter: int = 5, *args, **kwargs) -> None:
        """
        Initialize the Surfaces class.

        Parameters:
            thickness (list[float]): The minimum distance between the surfaces.
        """

        self.surface_list: list[BaseInterface] = []
        """
        List of surface objects.
        """

        self.reinitialize_per_iter = reinitialize_per_iter
        """
        The number of iterations after which the surfaces are reinitialized.
        This is useful for ensuring that the surfaces are updated periodically during the optimization process.
        """
        self.fea_seed_size = fea_seed_size
        """
        The seed size for the finite element analysis (FEA).
        """
        
        self.fea_mesh_order = fea_mesh_order
        """
        The mesh order for the finite element analysis (FEA).
        """

        self._surface_node_index: list[np.ndarray] = []
        """
        The indices of the surface nodes.
        """

        self._iter_since_last_regenerate: int = 0
        """
        The number of iterations since the last regeneration of the surfaces.
        """

        self._max_iter_before_regenerate: int = 15
        """
        The maximum number of iterations before the surfaces are regenerated.
        """

        self._nodes_last_regenerate: np.ndarray = None
        """
        The node positions at the last regeneration of the surfaces.
        """

        self._max_nodes_change: float = 1.0
        """
        The maximum allowed change in node positions before the surfaces are regenerated.
        """
        
    def reinitialize(self, iteration: int):
        """
        Initialize the surfaces for the optimization process.
            determine which surfaces need to be updated.
            initialize the surfaces.
        """
        if iteration % self.reinitialize_per_iter == 0:
            for i in range(self.num_surface):
                self.surface_list[i].reinitialize()
            # import copy
            # result = []
            # pools = morphopt.controller.pools
            # for i in range(self.num_surface):
            #     surface_now = copy.deepcopy(self.surface_list[i])
            #     morphopt.controller.change_device(device='cpu', obj=surface_now)
            #     result.append(
            #         pools.apply_async(
            #         surface_now.reinitialize, kwds={}))
                

            # get the result
            # for i in range(self.num_surface):
            #     result[i].get()
            

            morphopt.controller.objfun.inp = None
        self.apply_surface_constraints()

    def add_surface(self, surface_new: BaseInterface) -> None:
        """
        Add a surface object to the list.

        Parameters
        ----------
        surface : Surface
            The surface object to be added.
        """
        self.surface_list.append(surface_new)
        
    @property
    def num_surface(self) -> int:
        """
        Get the number of surfaces.

        Returns:
            length (int) :The number of surfaces.
        """
        return len(self.surface_list)
    
    @property
    def num_variables_list(self) -> list[int]:
        """
        Get the number of variables for each surface.

        Returns:
            list[int]: The number of variables for each surface.
        """
        num_vars = [self.surface_list[i].num_variables for i in range(self.num_surface)]
        return num_vars

    def pathlog_required(self):
        return ['geometry']

    def get_geometry_values(self) -> list[torch.Tensor]:
        """
        Get the geometry values of the surfaces.

        Returns:
            list[tuple]: A tuple containing the geometry values of the surfaces.
                - r (list[torch.Tensor]): The point coordinates of the surfaces.
                - rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
                - rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
        """
        
        rlist = [self.surface_list[i].get_geometry_values() for i in range(self.num_surface)]
        r = [rlist[i][0] for i in range(self.num_surface)]
        rdu = [rlist[i][1] for i in range(self.num_surface)]
        rdu2 = [rlist[i][2] for i in range(self.num_surface)]
        return r, rdu, rdu2
    
    def get_control_points_list(self) -> list[torch.Tensor]:
        """
        Get the control points of the surfaces.

        Returns:
            list[torch.Tensor]: The control points of the surfaces.
        """
        
        ctrl_pts = [self.surface_list[i].control_points.detach().clone() for i in range(self.num_surface)]
        return ctrl_pts

    def get_penalty_fairness(self, weight: list[torch.Tensor], r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor]) -> torch.Tensor:
        """
        Get the penalty fairness of the surfaces.

        Parameters:
            weight (list[torch.Tensor]): The weights for the points in the optimization process.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.

        Returns:
            torch.Tensor: The penalty fairness of the surfaces.
        """
        
        penalty = []
        for i in range(self.num_surface):
            penalty.append(self.surface_list[i].get_penalty_fairness(weight[i], r[i], rdu[i], rdu2[i]))
        
        return penalty
    
    def get_points_weight(self) -> list[torch.Tensor]:
        """
        Get the weights for the points in the optimization process.

        Returns:
            list[torch.Tensor]: The weights for the points in the optimization process.
        """
        
        weight = [self.surface_list[i].get_points_weight() for i in range(self.num_surface)]
        return weight
    
    def get_parameters(self) -> torch.Tensor:
        """
        Get the current variables of the surfaces.

        Returns:
            list[torch.Tensor]: The current variables of the surfaces.
        """
        
        xlist = []
        for i in range(self.num_surface):
            xlist.append(self.surface_list[i].get_surface_parameters().flatten().detach().clone())
        return xlist
    
    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the current variables of the surfaces.

        Parameters:
            xlist (list[torch.Tensor]): The new variables for the surfaces.
        """
        for i in range(self.num_surface):
            self.surface_list[i].set_surface_parameters(xlist[i].detach().clone())
            
    def get_variables(self) -> torch.Tensor:
        """
        Get the current variables of the surfaces.

        Returns:
            torch.Tensor: The current variables of the surfaces.
        """
        xlist = self.get_parameters()
        x_flatten = torch.cat([torch.randn_like(xlist[i].flatten())*1e-6 for i in range(len(xlist))])
        return x_flatten
    
    def update_variables(self, x_change: torch.Tensor, max_step_length: list[torch.Tensor]) -> None:
        """
        Update the surfaces with the new variables.

        Parameters:
            xlist_change (torch.Tensor): The change of variables for the surfaces.
        """
        
        x_change_list: list[torch.Tensor] = []
        start = 0
        for i in range(self.num_surface):
            end = start + self.surface_list[i].num_variables
            x_change_list.append(x_change[start:end].reshape([3, -1]))
            start = end

        for i in range(self.num_surface):

            r = x_change_list[i].norm(dim=0)
            
            dx = 2/torch.pi * torch.atan(r) * x_change_list[i] / (r + 1e-15) * max_step_length[i]
            
            self.surface_list[i].update_variables(dx)

        self.apply_surface_constraints()

    def apply_surface_constraints(self) -> None:
        """
        Apply the constraints (e.g. the symmetric constraint) of the surfaces.
        """
        pass

    def save(self, foldpath, iteration) -> None:
        for i in range(self.num_surface):
            self.surface_list[i].save(foldpath + self.pathlog_required()[0] + '/Surface-%d_iter-%d' %
                              (i, iteration))
        import pyvista as pv

        plotter = pv.Plotter(off_screen=True, window_size=(1200, 1200))
        plotter.set_background('white')

        self.plot(plotter=plotter)
        
        # Get all points to determine bounding box
        all_points = []
        for i in range(self.num_surface):
            r, _, _ = self.surface_list[i].get_geometry_values()
            all_points.append(r)

        all_points = torch.cat(all_points, dim=1)
        x_min, x_max = all_points[0].min().item(), all_points[0].max().item()
        y_min, y_max = all_points[1].min().item(), all_points[1].max().item()
        z_min, z_max = all_points[2].min().item(), all_points[2].max().item()

        # Add some padding to the bounds
        padding = 0.05 * max(x_max-x_min, y_max-y_min, z_max-z_min)
        
        plotter.show_bounds(xtitle='X', ytitle='Y', ztitle='Z', color='black',
                            bounds=[x_min-padding, x_max+padding, 
                                    y_min-padding, y_max+padding, 
                                    z_min-padding, z_max+padding])
        
        plotter.enable_parallel_projection()
        azimuth = 210
        elevation = 20
        plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(elevation))))
        
        plotter.screenshot(foldpath + self.pathlog_required()[0] + '/%d.jpg'%iteration)
        plotter.close()

        
    def load(self, foldpath, iteration):
        for i in range(self.num_surface):
            self.surface_list[i].load(foldpath + self.pathlog_required()[0] + '/Surface-%d_iter-%d' %
                              (i, iteration))
            # self.surface_list[i].initialize()
            
    def plot(self, plotter=None):
        if plotter is None:
            import pyvista as pv
            plotter = pv.Plotter()
            
        for sf in range(self.num_surface):
            if sf == 0:
                alpha = 0.6
            else:
                alpha = 1
            mesh = self.surface_list[sf].get_mesh()
            plotter.add_mesh(mesh, opacity=alpha,  color=(40.0 / 255, 120.0 / 255, 181.0 / 255),
                           diffuse=0.8, specular=0.2, ambient=0.3, specular_power=10,
                           smooth_shading=True, show_edges=False)
            
    def get_meshes(self):
        """
        Get all meshes for the surfaces.

        Returns:
            list[pyvista.PolyData]: The mesh objects for all surfaces.
        """
        mesh_list = []
        for sf in range(self.num_surface):
            mesh = self.surface_list[sf].get_mesh()
            mesh_list.append(mesh)
        return mesh_list
    
    def generate(self) -> None:
        """
        This function generates the geometric model of the soft robot.
        It calls the Rhino application to generate the model and then calls Abaqus for finite element analysis (FEA).
        """

        return self._regenerate()
        


    def _regenerate(self) -> None:
        """
        This function regenerates the geometric model of the soft robot.
        It calls the Rhino application to generate the model and then calls Abaqus for finite element analysis (FEA).
        """
        path_output = morphopt.controller.path_result + '/Cache/'

        # export the data
        self._export_data(foldpath=path_output)

        # call Abaqus for FEA
        inp_path = morphopt.controller.path_result + '/Cache/TopOptRun.inp'
        # self._call_Abaqus(path_output, material_para, self.fea_seed_size, self.fea_mesh_order)
        morphopt.controller.pools.apply_async(MeshGenerator.run, kwds={
            'seed_size': self.fea_seed_size,
            'output_file': inp_path,
            'directory': path_output
        }).get()

        # read the inp file
        inp = torchfea.FEA_INP()
        inp.read_inp(path=inp_path)

        return inp

    def _export_data(self, foldpath: str) -> list[str]:
        """
        This function export the data of each surfaces
        """
        
        # export each surface with Rhino
        for i in range(self.num_surface):
            surf_name0 = '__surface-%d' % i
            self.surface_list[i].output_data(path_output=foldpath, name_output=surf_name0, flip=(i!=0))

        files = sorted(glob.glob(foldpath + "__surface-*.stp"))
        if not files:
            print("No __surface-*.stp files found.")
            return
