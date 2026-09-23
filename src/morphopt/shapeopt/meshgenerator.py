"""Gmsh-based volume mesher for optimizable boundary-surface geometry.

The mesher consumes the ``__surface-<index>.stp|stl`` files exported by the
surface interfaces (index ``0`` = outer boundary, ``1..n`` = cavities), builds
one volume, meshes it, and writes an Abaqus ``.inp`` part whose element faces
are grouped into ``surface_<index>_All`` surfaces and node sets.
"""

import os

import gmsh
import numpy as np


class MeshGenerator:
    def __init__(self, mesh_size_min=None, mesh_size_max=None):
        gmsh.initialize()
        gmsh.option.setNumber("General.NumThreads", 0)  # Use all available cores
        gmsh.option.setNumber("General.Verbosity", 2)  # Errors only
        self.files_map = {}
        self.surface_tags_by_index = {}
        self.sorted_indices = []

        # Set mesh size options if provided
        if mesh_size_min is not None:
            gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size_min)

        if mesh_size_max is not None:
            gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size_max)

    def scan_directory(self, directory=None):
        if directory is None:
            directory = os.getcwd()

        # Pattern: __surface-{number}.(stp|stl)
        import re

        pattern = re.compile(r"^__surface-(\d+)\.(stp|stl)$", re.IGNORECASE)

        self.files_map = {}
        for filename in os.listdir(directory):
            match = pattern.match(filename)
            if match:
                idx = int(match.group(1))
                self.files_map[idx] = os.path.join(directory, filename)

        if 0 not in self.files_map:
            raise FileNotFoundError(
                "Base surface file (Index 0) not found. Need '__surface-0.stp' or '__surface-0.stl'."
            )

        self.sorted_indices = sorted(self.files_map.keys())

    def _get_all_surface_tags(self):
        return set(dim_tag[1] for dim_tag in gmsh.model.getEntities(2))

    def load_and_process_files(self):
        self.surface_tags_by_index = {}

        for idx in self.sorted_indices:
            filename = self.files_map[idx]

            # Snapshot current surfaces to identify new ones
            pre_surfaces = self._get_all_surface_tags()

            ext = os.path.splitext(filename)[1].lower()

            if ext in [".stp", ".step"]:
                try:
                    gmsh.model.occ.importShapes(filename)
                    gmsh.model.occ.synchronize()

                    vols = gmsh.model.getEntities(3)
                    if vols:
                        gmsh.model.occ.remove(vols, recursive=False)
                        gmsh.model.occ.synchronize()

                except Exception as e:
                    raise RuntimeError(f"Error loading STP file {filename}: {e}")

            elif ext == ".stl":
                try:
                    gmsh.merge(filename)
                except Exception as e:
                    raise RuntimeError(f"Error loading STL file {filename}: {e}")

            # Identify newly added surfaces
            post_surfaces = self._get_all_surface_tags()
            new_surfaces = list(post_surfaces - pre_surfaces)

            if new_surfaces:
                self.surface_tags_by_index[idx] = new_surfaces

    def construct_volume(self):
        if 0 not in self.surface_tags_by_index or not self.surface_tags_by_index[0]:
            raise RuntimeError("Error: No surfaces available for base (Index 0).")

        loops = []

        # Process Base (0) first
        try:
            base_loop = gmsh.model.geo.addSurfaceLoop(self.surface_tags_by_index[0])
            loops.append(base_loop)
        except Exception as e:
            raise RuntimeError(f"Error creating outer loop: {e}")

        # Process Cavities (>0)
        for idx in self.sorted_indices:
            if idx == 0:
                continue
            tags = self.surface_tags_by_index.get(idx)
            if tags:
                try:
                    cavity_loop = gmsh.model.geo.addSurfaceLoop(tags)
                    loops.append(cavity_loop)
                except Exception as e:
                    raise RuntimeError(
                        f"Error creating cavity loop for index {idx}: {e}"
                    )

        # Create Volume
        try:
            vol_tag = gmsh.model.geo.addVolume(loops)
            gmsh.model.geo.synchronize()

            gmsh.model.addPhysicalGroup(3, [vol_tag], name="Volume_All")

        except Exception as e:
            raise RuntimeError(f"Error creating volume: {e}")

    def generate_mesh(self, dim=3):
        try:
            gmsh.model.mesh.generate(dim)
        except Exception as e:
            raise RuntimeError(f"Error during meshing: {e}")

    def _generate_abaqus_surface_payload(self):
        """
        Generates the Abaqus SURFACE definition string by mapping 3D element faces
        to the geometric surfaces.
        """
        # Get all 3D tetrahedron elements (Type 4 in GMSH)
        try:
            tet_tags, tet_node_tags = gmsh.model.mesh.getElementsByType(4)
        except Exception:
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
            ([2, 3, 0], "S4"),
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
            sets_data = {"S1": [], "S2": [], "S3": [], "S4": []}

            found_count = 0

            # Set to collect unique node tags for this surface index
            surface_nodes = set()

            # Iterate over the geometric surfaces for this index
            for s_tag in surf_tags:
                # Get 2D elements (Triangles = Type 2) on this surface
                try:
                    tri_tags, tri_node_tags = gmsh.model.mesh.getElementsByType(
                        2, tag=s_tag
                    )
                except Exception:
                    continue

                n_tris = len(tri_tags)
                if n_tris == 0:
                    continue

                for t in range(n_tris):
                    base = t * 3
                    tn0 = tri_node_tags[base]
                    tn1 = tri_node_tags[base + 1]
                    tn2 = tri_node_tags[base + 2]

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
                surf_name = f"surface_{idx}_All"

                # Create ELSETs for each face type
                active_faces = []
                for face_id, el_list in sets_data.items():
                    if el_list:
                        set_name = f"_{surf_name}_{face_id}"
                        active_faces.append(f"{set_name}, {face_id}")

                        payload_lines.append(f"*ELSET, ELSET={set_name}, INTERNAL")
                        chunk_size = 16
                        for k in range(0, len(el_list), chunk_size):
                            chunk = el_list[k : k + chunk_size]
                            line = ", ".join(str(e) for e in chunk)
                            payload_lines.append(line)

                # Create SURFACE definition
                payload_lines.append(f"*SURFACE, TYPE=ELEMENT, NAME={surf_name}")
                payload_lines.extend(active_faces)

                # Create NSET definition
                if surface_nodes:
                    payload_lines.append(f"*Nset, nset={surf_name}")
                    sorted_nodes = sorted(surface_nodes)
                    chunk_size = 16
                    for k in range(0, len(sorted_nodes), chunk_size):
                        chunk = sorted_nodes[k : k + chunk_size]
                        line = ", ".join(str(e) for e in chunk)
                        payload_lines.append(line)

        return "\n".join(payload_lines)

    def export(
        self, outfile: str = "output.inp", part_name: str = "final_model"
    ) -> None:
        surface_payload = self._generate_abaqus_surface_payload()

        gmsh.write(outfile)

        with open(outfile, "r") as f:
            lines = f.readlines()

        lines.insert(2, f"*Part, name={part_name}\n")

        if surface_payload:
            lines.append("\n")
            lines.append(surface_payload)
            lines.append("\n")

        lines.append("*End Part\n")

        with open(outfile, "w") as f:
            f.writelines(lines)

    def finalize(self):
        gmsh.finalize()

    @classmethod
    def run(
        cls,
        seed_size: float,
        output_file: str = "output.inp",
        directory: str | None = None,
        part_name: str = "final_model",
    ) -> None:
        generator = cls(mesh_size_max=seed_size * 1.0, mesh_size_min=seed_size * 0.5)
        try:
            generator.scan_directory(directory=directory)
            generator.load_and_process_files()
            generator.construct_volume()
            generator.generate_mesh(3)
            generator.export(output_file, part_name=part_name)
        except Exception as exc:
            raise RuntimeError(
                f"Volume mesh generation failed for Part {part_name!r} "
                f"in {directory!r}: {exc}"
            ) from exc
        finally:
            generator.finalize()
