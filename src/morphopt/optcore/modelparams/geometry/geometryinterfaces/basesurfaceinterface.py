import datetime
import math
import numpy as np
import torch
from typing import Optional

import pyvista as pv

class BaseInterface():
    """
    Class to handle the surface of the morphable model.
    """
    
    def __init__(self, symmetric: list[int] = None, *args, **kwargs) -> None:
        """
        Initialize the Surface class.

        Parameters:
            surface (Surface_Base) : The surface model.
            surf_type (int) : The type of the surface.
                - 0: bspline surface
                - 1: closed surface
            symmetric (list[int]) : The symmetry of the surface.
                - 0: no symmetry
                - 1: axis symmetry
                    0: x-axis symmetry
                    1: y-axis symmetry
                    2: z-axis symmetry
        """

        self.symmetric: list[int] = symmetric
        """
        the symmetry of the surface.
        # 0: no symmetry
        # 1: axis symmetry
            ## 0: x-axis symmetry
            ## 1: y-axis symmetry
            ## 2: z-axis symmetry
        """

        self.surf_node_idx: np.ndarray
        """the node index of the surface at the fea mesh."""

        self.surf_node_uv: np.ndarray
        """the (u, v) coordinates of the surface nodes."""
        


        self.flip: bool = False
        
    def map(self, uv: torch.Tensor) -> torch.Tensor:
        """
        Map from UV space to 3D space using the surface model.

        Parameters:
            uv (torch.Tensor): The UV coordinates to be mapped.

        Returns:
            torch.Tensor: The corresponding 3D coordinates in the physical space.
        """
        raise NotImplementedError("The map method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def get_normals(self, uv: torch.Tensor) -> torch.Tensor:
        """
        Get the normals of the surface at the given UV coordinates.

        Parameters:
            uv (torch.Tensor): The UV coordinates to get the normals.

        Returns:
            torch.Tensor: The normals of the surface at the given UV coordinates.
        """
        raise NotImplementedError("The get_normals method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def initialize(self) -> None:
        """
        Initialize the surface.
        """
        pass
    
    def reinitialize(self) -> 'BaseInterface':
        """
        ReInitialize the surface.
        """
        return self

    @property
    def control_points(self) -> torch.Tensor:
        """
        Get the control points of the surface.

        Returns:
            torch.Tensor: The control points of the surface.
        """
        raise NotImplementedError("The control_points property is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def output_data(self, path_output, name_output, seed_size=-1, flip=False, ):
        """
        Output the surface data to a file.
        """
        raise NotImplementedError("The output_data method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def get_surface_parameters(self) -> torch.Tensor:
        """
        Get the design variables of the surface.

        Returns:
            torch.Tensor: The design variables of the surface.
        """
        raise NotImplementedError("The get_variables method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """
        Set the design variables of the surface.

        Parameters:
            x (torch.Tensor): The new design variables to be set.
        """
        raise NotImplementedError("The set_variables method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the surface with the new design variables.

        Parameters:
            x_change (torch.Tensor): The change of design variables to be applied.
        """

        raise NotImplementedError("The update_variables method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get the geometry values of the surface.

        Returns:
            tuple: A tuple containing the geometry values of the surface.
                - r (torch.Tensor): The point coordinates of the surface.
                - rdu (torch.Tensor): The partial derivatives of the surface.
                - rdu2 (torch.Tensor): The second partial derivatives of the surface.
        """
        raise NotImplementedError("The get_geometry_values method is not implemented in the BaseInterface class. Please implement it in the derived class.")
    
    def get_penalty_fairness(self, r: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor) -> torch.Tensor:
        """
        Get the penalty fairness of the surface.

        Returns:
            torch.Tensor: The penalty fairness of the surface.
        """
        return 0.0
    
    def get_points_weight(self) -> torch.Tensor:
        """
        Get the points weight of the surface.

        Returns:
            torch.Tensor: The points weight of the surface.
        """
        raise NotImplementedError("The get_points_weight method is not implemented in the BaseInterface class. Please implement it in the derived class.")
    
    @staticmethod
    def barrier_function(f: torch.Tensor, f_max: torch.Tensor|float, ratio: float, p: int):
        """
        Apply a barrier function to the objective function.
        
        Args:
            f (torch.Tensor): The objective function value.
            f_max (float or torch.Tensor): The maximum value of the objective function.
            ratio (float): The ratio for the barrier function.
            p (float): The exponent for the barrier function.
            
        Returns:
            index (torch.Tensor): The indices of the elements that are greater than the barrier.
            fnew (torch.Tensor): The new objective function value after applying the barrier function.
        
        """
        if type(f_max) != torch.Tensor:
            f_max = torch.tensor(f_max).repeat(f.shape)
        index = torch.where(f > f_max * ratio)[0]

        if index.numel() > 0:
            f = f[index]
            f_max = f_max[index]
            fnew = ((f - f_max * ratio) / (f_max - f_max * ratio))**(p)
        else:
            fnew = f[index]
        return index, fnew

    @property
    def num_variables(self) -> int:
        """
        Get the number of design variables.

        Returns:
            int: The number of design variables.
        """
        raise NotImplementedError("The num_variables property is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def save(self, filename: str) -> None:
        """
        Save the surface data to a file.

        Parameters:
            filename (str): The name of the file to save the surface data.
        """
        raise NotImplementedError("The save method is not implemented in the BaseInterface class. Please implement it in the derived class.")
    
    def load(self, filename: str) -> None:
        """
        Load the surface data from a file.

        Parameters:
            filename (str): The name of the file to load the surface data from.
        """
        raise NotImplementedError("The load method is not implemented in the BaseInterface class. Please implement it in the derived class.")

    def get_mesh(self) -> pv.PolyData:
        """
        Get the mesh for the surface.

        Returns:
            object: The mesh object.
        """
        raise NotImplementedError("The get_mesh method is not implemented in the BaseInterface class. Please implement it in the derived class.")
    
    def plot(self):
        """
        Plot the surface mesh.
        """
        mesh = self.get_mesh()
        plotter = pv.Plotter()
        plotter.add_mesh(mesh, color='lightblue', show_edges=True)
        plotter.show()

    class MeshSurfaceConverter:
        def __init__(self):
            self.vertices: np.ndarray
            self.faces: np.ndarray
            self.entity_counter = 10
            
        def parse_obj_file(self, obj_content):
            """解析OBJ文件内容"""
            self.vertices = []
            self.faces = []
            
            lines = obj_content.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if line.startswith('v '):
                    # 解析顶点
                    parts = line.split()
                    if len(parts) >= 4:
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        self.vertices.append((x, y, z))
                elif line.startswith('f '):
                    # 解析面
                    parts = line.split()
                    face_vertices = []
                    for part in parts[1:]:
                        # 处理面索引，可能包含纹理和法向量信息 (v/vt/vn)
                        vertex_index = int(part.split('/')[0]) - 1  # OBJ索引从1开始
                        face_vertices.append(vertex_index)
                    self.faces.append(face_vertices)
        
        def _generate_stp_header(self, filename="model"):
            """生成STP文件头部"""
            timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
            
            header = f"""ISO-10303-21;
    HEADER;
    /* Generated by ObjToStpConverter */

    FILE_DESCRIPTION(
    /* description */ ('Converted from OBJ file'),
    /* implementation_level */ '2;1');

    FILE_NAME(
    /* name */ '{filename}',
    /* time_stamp */ '{timestamp}',
    /* author */ (''),
    /* organization */ (''),
    /* preprocessor_version */ 'ObjToStpConverter v1.0',
    /* originating_system */ 'Python Script',
    /* authorisation */ '');

    FILE_SCHEMA (('CONFIG_CONTROL_DESIGN'));
    ENDSEC;

    DATA;"""
            return header
        
        def _generate_stp_footer(self):
            """生成STP文件尾部"""
            return "ENDSEC;\nEND-ISO-10303-21;"
        
        def _get_next_entity_id(self):
            """获取下一个实体ID"""
            current_id = self.entity_counter
            self.entity_counter += 1
            return current_id
        
        def _find_unique_vertices(self):
            """去重顶点，合并重复的顶点"""
            unique_vertices = []
            vertex_map = {}
            tolerance = 1e-6
            
            for i, vertex in enumerate(self.vertices):
                found = False
                for j, unique_vertex in enumerate(unique_vertices):
                    if (abs(vertex[0] - unique_vertex[0]) < tolerance and 
                        abs(vertex[1] - unique_vertex[1]) < tolerance and 
                        abs(vertex[2] - unique_vertex[2]) < tolerance):
                        vertex_map[i] = j
                        found = True
                        break
                
                if not found:
                    vertex_map[i] = len(unique_vertices)
                    unique_vertices.append(vertex)
            
            return unique_vertices, vertex_map
        
        def _find_shared_edges(self, vertex_map):
            """找到共享的边"""
            edge_usage = {}
            
            for face in self.faces:
                mapped_face = [vertex_map[v] for v in face]
                for i in range(len(mapped_face)):
                    v1 = mapped_face[i]
                    v2 = mapped_face[(i + 1) % len(mapped_face)]
                    
                    edge = (min(v1, v2), max(v1, v2))
                    
                    if edge not in edge_usage:
                        edge_usage[edge] = 0
                    edge_usage[edge] += 1
            
            return edge_usage
        
        def convert_mesh_to_stp(self, faces: np.ndarray, vertices: np.ndarray, filename="model"):
            """将OBJ内容转换为STP格式，严格按照原始STP结构"""
            # 解析OBJ文件
            self.vertices = vertices
            self.faces = faces
            
            # 去重顶点
            unique_vertices, vertex_map = self._find_unique_vertices()
            edge_usage = self._find_shared_edges(vertex_map)
            
            # 生成STP内容
            stp_content = []
            stp_content.append(self._generate_stp_header(filename))
            
            # 统一分配所有ID，避免冲突
            
            # 1. 顶级结构实体（固定ID范围：10-20）
            shape_rel_id = 10
            brep_id = 11
            brep_shape_rep_id = 12
            closed_shell_id = 13
            
            # 2. 面实体（从14开始）
            face_ids = list(range(14, 14 + len(self.faces)))
            face_bound_ids = list(range(14 + len(self.faces), 14 + 2 * len(self.faces)))
            edge_loop_ids = list(range(14 + 2 * len(self.faces), 14 + 3 * len(self.faces)))
            
            current_id = 14 + 3 * len(self.faces)
            
            # 3. 为每个面的边创建ORIENTED_EDGE
            oriented_edges_per_face = []
            for face in self.faces:
                face_oriented_edges = []
                for _ in range(len(face)):
                    face_oriented_edges.append(current_id)
                    current_id += 1
                oriented_edges_per_face.append(face_oriented_edges)
            
            # 4. 创建共享的EDGE_CURVE
            edge_curve_map = {}
            for edge in edge_usage.keys():
                edge_curve_map[edge] = current_id
                current_id += 1
            
            # 5. 创建B_SPLINE_CURVE
            spline_map = {}
            for edge in edge_usage.keys():
                spline_map[edge] = current_id
                current_id += 1
            
            # 6. 创建VERTEX_POINT
            vertex_point_map = {}
            for i in range(len(unique_vertices)):
                vertex_point_map[i] = current_id
                current_id += 1
            
            # 7. 创建PLANE
            plane_ids = []
            for _ in range(len(self.faces)):
                plane_ids.append(current_id)
                current_id += 1
            
            # 8. 预留产品结构实体的ID
            shape_def_rep_id = current_id
            current_id += 1
            product_def_shape_id = current_id
            current_id += 1
            product_def_id = current_id
            current_id += 1
            product_def_context_id = current_id
            current_id += 1
            
            # 9. 分配固定上下文实体的ID
            product_def_formation_id = current_id
            current_id += 1
            application_context_id = current_id
            current_id += 1
            product_id = current_id
            current_id += 1
            product_context_id = current_id
            current_id += 1
            length_unit_id = current_id
            current_id += 1
            plane_angle_unit_id = current_id
            current_id += 1
            solid_angle_unit_id = current_id
            current_id += 1
            uncertainty_measure_id = current_id
            current_id += 1
            geometric_rep_context_id = current_id
            current_id += 1
            shape_representation_id = current_id
            current_id += 1
            axis2_placement_1_id = current_id
            current_id += 1
            axis2_placement_2_id = current_id
            current_id += 1
            direction_1_id = current_id
            current_id += 1
            direction_2_id = current_id
            current_id += 1
            direction_3_id = current_id
            current_id += 1
            direction_4_id = current_id
            current_id += 1
            cartesian_point_1_id = current_id
            current_id += 1
            cartesian_point_2_id = current_id
            current_id += 1
            
            # 10. 方向和轴放置
            direction_ids = []
            axis_placement_ids = []
            for _ in range(len(self.faces)):
                direction_ids.append(current_id)
                current_id += 1
                axis_placement_ids.append(current_id)
                current_id += 1
            
            # 11. 为CARTESIAN_POINT分配ID
            cartesian_point_map = {}
            for i in range(len(unique_vertices)):
                cartesian_point_map[i] = current_id
                current_id += 1
            
            # 12. 为B_SPLINE控制点分配ID  
            spline_point_map = {}
            for edge in edge_usage.keys():
                spline_point_map[edge] = (current_id, current_id + 1)
                current_id += 2
            
            # 开始生成实体
            
            # 核心结构
            stp_content.append(f"#{shape_rel_id}=SHAPE_REPRESENTATION_RELATIONSHIP('','',#{shape_representation_id},#{brep_shape_rep_id});")
            stp_content.append(f"#{brep_id}=MANIFOLD_SOLID_BREP('brep_1',#{closed_shell_id});")
            stp_content.append(f"#{brep_shape_rep_id}=ADVANCED_BREP_SHAPE_REPRESENTATION('brep_rep_0',(#{brep_id},#{axis2_placement_2_id}),#{geometric_rep_context_id});")
            
            # CLOSED_SHELL
            face_refs = ','.join([f"#{fid}" for fid in face_ids])
            stp_content.append(f"#{closed_shell_id}=CLOSED_SHELL('',({face_refs}));")
            
            # ADVANCED_FACE
            for i, face_id in enumerate(face_ids):
                stp_content.append(f"#{face_id}=ADVANCED_FACE('',(#{face_bound_ids[i]}),#{plane_ids[i]},.T.);")
            
            # FACE_OUTER_BOUND
            for i, bound_id in enumerate(face_bound_ids):
                stp_content.append(f"#{bound_id}=FACE_OUTER_BOUND('',#{edge_loop_ids[i]},.T.);")
            
            # EDGE_LOOP
            for i, loop_id in enumerate(edge_loop_ids):
                oriented_refs = ','.join([f"#{oe_id}" for oe_id in oriented_edges_per_face[i]])
                stp_content.append(f"#{loop_id}=EDGE_LOOP('',({oriented_refs}));")
            
            # ORIENTED_EDGE
            for face_idx, face in enumerate(self.faces):
                mapped_face = [vertex_map[v] for v in face]
                for edge_idx in range(len(mapped_face)):
                    v1 = mapped_face[edge_idx]
                    v2 = mapped_face[(edge_idx + 1) % len(mapped_face)]
                    edge = (min(v1, v2), max(v1, v2))
                    
                    oriented_edge_id = oriented_edges_per_face[face_idx][edge_idx]
                    edge_curve_id = edge_curve_map[edge]
                    
                    # 修正方向逻辑：确保边的方向与面的定义一致
                    if (v1, v2) == edge:
                        orientation = '.T.'
                    else:
                        orientation = '.F.'
                    
                    stp_content.append(f"#{oriented_edge_id}=ORIENTED_EDGE('',*,*,#{edge_curve_id},{orientation});")
            
            # EDGE_CURVE
            for edge, edge_id in edge_curve_map.items():
                v1, v2 = edge
                vertex_point_1 = vertex_point_map[v1]
                vertex_point_2 = vertex_point_map[v2]
                spline_id = spline_map[edge]
                stp_content.append(f"#{edge_id}=EDGE_CURVE('',#{vertex_point_1},#{vertex_point_2},#{spline_id},.T.);")
            
            # B_SPLINE_CURVE_WITH_KNOTS
            for edge, spline_id in spline_map.items():
                point1_id, point2_id = spline_point_map[edge]
                stp_content.append(f"#{spline_id}=B_SPLINE_CURVE_WITH_KNOTS('',1,(#{point1_id},#{point2_id}),.UNSPECIFIED.,.F.,.F.,(2,2),(0.,1.),.UNSPECIFIED.);")
            
            # VERTEX_POINT
            for i, vertex_point_id in vertex_point_map.items():
                cartesian_id = cartesian_point_map[i]
                stp_content.append(f"#{vertex_point_id}=VERTEX_POINT('',#{cartesian_id});")
            
            # PLANE and supporting entities
            for i, plane_id in enumerate(plane_ids):
                stp_content.append(f"#{plane_id}=PLANE('',#{axis_placement_ids[i]});")
            
            # 生成产品结构
            stp_content.append(f"#{shape_def_rep_id}=SHAPE_DEFINITION_REPRESENTATION(#{product_def_shape_id},#{shape_representation_id});")
            stp_content.append(f"#{product_def_shape_id}=PRODUCT_DEFINITION_SHAPE('Document','',#{product_def_id});")
            
            # 添加所有支持实体
            self._add_supporting_entities(stp_content, unique_vertices, vertex_map, cartesian_point_map, 
                                        spline_point_map, direction_ids, axis_placement_ids,
                                        product_def_id, product_def_context_id, product_def_formation_id,
                                        application_context_id, product_id, product_context_id,
                                        length_unit_id, plane_angle_unit_id, solid_angle_unit_id,
                                        uncertainty_measure_id, geometric_rep_context_id, shape_representation_id,
                                        axis2_placement_1_id, axis2_placement_2_id, direction_1_id, direction_2_id,
                                        direction_3_id, direction_4_id, cartesian_point_1_id, cartesian_point_2_id)
            
            stp_content.append(self._generate_stp_footer())
            return '\n'.join(stp_content)
        
        def _add_supporting_entities(self, stp_content, unique_vertices, vertex_map, cartesian_point_map, 
                                    spline_point_map, direction_ids, axis_placement_ids,
                                    product_def_id, product_def_context_id, product_def_formation_id,
                                    application_context_id, product_id, product_context_id,
                                    length_unit_id, plane_angle_unit_id, solid_angle_unit_id,
                                    uncertainty_measure_id, geometric_rep_context_id, shape_representation_id,
                                    axis2_placement_1_id, axis2_placement_2_id, direction_1_id, direction_2_id,
                                    direction_3_id, direction_4_id, cartesian_point_1_id, cartesian_point_2_id):
            """添加支持实体，使用唯一ID避免冲突"""
            
            # 产品定义结构
            stp_content.append(f"#{product_def_context_id}=PRODUCT_DEFINITION_CONTEXT('3D Mechanical Parts',#{application_context_id},'design');")
            stp_content.append(f"#{product_def_id}=PRODUCT_DEFINITION('A','First version',#{product_def_formation_id},#{product_def_context_id});")
            stp_content.append(f"#{product_def_formation_id}=PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('A','First version',#{product_id},.MADE.);")
            stp_content.append(f"#{application_context_id}=APPLICATION_CONTEXT('configuration controlled 3d designs of mechanical parts and assemblies');")
            stp_content.append(f"#{product_id}=PRODUCT('Document','Document','',(#{product_context_id}));")
            stp_content.append(f"#{product_context_id}=PRODUCT_CONTEXT('3D Mechanical Parts',#{application_context_id},'mechanical');")
            
            # 单位定义
            stp_content.append(f"#{length_unit_id}=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));")
            stp_content.append(f"#{plane_angle_unit_id}=(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.));")
            stp_content.append(f"#{solid_angle_unit_id}=(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT());")
            
            # 几何表示上下文
            stp_content.append(f"#{uncertainty_measure_id}=UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.001),#{length_unit_id},'DISTANCE_ACCURACY_VALUE','Maximum model space distance');")
            stp_content.append(f"#{geometric_rep_context_id}=(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{uncertainty_measure_id})) GLOBAL_UNIT_ASSIGNED_CONTEXT((#{solid_angle_unit_id},#{plane_angle_unit_id},#{length_unit_id})) REPRESENTATION_CONTEXT('ID1','3D'));")
            
            # 形状表示
            stp_content.append(f"#{shape_representation_id}=SHAPE_REPRESENTATION('Document',(#{axis2_placement_1_id},#{axis2_placement_2_id}),#{geometric_rep_context_id});")
            stp_content.append(f"#{axis2_placement_1_id}=AXIS2_PLACEMENT_3D('',#{cartesian_point_1_id},#{direction_1_id},#{direction_2_id});")
            stp_content.append(f"#{axis2_placement_2_id}=AXIS2_PLACEMENT_3D('',#{cartesian_point_2_id},#{direction_3_id},#{direction_4_id});")
            stp_content.append(f"#{direction_1_id}=DIRECTION('',(0.,0.,1.));")
            stp_content.append(f"#{direction_2_id}=DIRECTION('',(1.,0.,0.));")
            stp_content.append(f"#{direction_3_id}=DIRECTION('',(0.,0.,1.));")
            stp_content.append(f"#{direction_4_id}=DIRECTION('',(1.,0.,0.));")
            stp_content.append(f"#{cartesian_point_1_id}=CARTESIAN_POINT('',(0.,0.,0.));")
            stp_content.append(f"#{cartesian_point_2_id}=CARTESIAN_POINT('',(0.,0.,0.));")
            
            # 生成面的方向和轴放置
            for i, (direction_id, axis_id) in enumerate(zip(direction_ids, axis_placement_ids)):
                # 计算面法向量
                face = self.faces[i]
                mapped_face = [vertex_map[v] for v in face]
                
                v1 = unique_vertices[mapped_face[0]]
                v2 = unique_vertices[mapped_face[1]]
                v3 = unique_vertices[mapped_face[2]]
                
                edge1 = (v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2])
                edge2 = (v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2])
                normal = (
                    edge1[1] * edge2[2] - edge1[2] * edge2[1],
                    edge1[2] * edge2[0] - edge1[0] * edge2[2],
                    edge1[0] * edge2[1] - edge1[1] * edge2[0]
                )
                
                length = math.sqrt(normal[0]**2 + normal[1]**2 + normal[2]**2)
                if length > 0:
                    normal = (normal[0]/length, normal[1]/length, normal[2]/length)
                else:
                    normal = (0, 0, 1)
                
                stp_content.append(f"#{direction_id}=DIRECTION('',({normal[0]},{normal[1]},{normal[2]}));")
                
                # 使用第一个顶点作为原点
                point_id = cartesian_point_map[mapped_face[0]]
                stp_content.append(f"#{axis_id}=AXIS2_PLACEMENT_3D('',#{point_id},#{direction_id},$);")
            
            # 生成CARTESIAN_POINT
            for i, (x, y, z) in enumerate(unique_vertices):
                point_id = cartesian_point_map[i]
                stp_content.append(f"#{point_id}=CARTESIAN_POINT('',({x},{y},{z}));")
            
            # 生成B样条控制点
            for edge, (point1_id, point2_id) in spline_point_map.items():
                v1, v2 = edge
                v1_coords = unique_vertices[v1]
                v2_coords = unique_vertices[v2]
                stp_content.append(f"#{point1_id}=CARTESIAN_POINT('',({v1_coords[0]},{v1_coords[1]},{v1_coords[2]}));")
                stp_content.append(f"#{point2_id}=CARTESIAN_POINT('',({v2_coords[0]},{v2_coords[1]},{v2_coords[2]}));")

    def match_coordinates(self, surf_node_idx: np.ndarray, surf_nodes: np.ndarray, *args, **kwargs) -> np.ndarray:
        """
        Match the coordinates of the nodes to the surface.

        Parameters:
            surf_node_idx (np.ndarray): The indices of the surface nodes.
            surf_nodes (np.ndarray): The coordinates of the surface nodes.

        Returns:
            np.ndarray: The nodes position updated to match the surface.
        """
        raise NotImplementedError("The match_coordinates method is not implemented in the BaseInterface class. Please implement it in the derived class.")

class CpBasedInterface(BaseInterface):
    """
    Class to handle the surface of the morphable model.
    """

    class PreLoadData:
        """
        Class to handle the preloaded data for the surface.

        Attributes:
            uv (torch.Tensor): The preloaded UV parameters for the surface.
            cp_weights (torch.Tensor): The preloaded weights for the control points.
            cp_weights_du (torch.Tensor): The preloaded derivative of the weights with respect to the `first` parameter.
            cp_weights_dv (torch.Tensor): The preloaded derivative of the weights with respect to the `second` parameter.
            cp_weights_du2 (torch.Tensor): The preloaded second derivative of the weights with respect to the `first` parameter.
            cp_weights_dudv (torch.Tensor): The preloaded mixed derivative of the weights with respect to the `first` and `second` parameters.
            cp_weights_dv2 (torch.Tensor): The preloaded second derivative of the weights with respect to the `second` parameter.
            indices (torch.Tensor): The flattened preload indices for scatter-add mapping.
            faces (torch.Tensor | None): Optional mesh face connectivity for the preload points.
        """

        def __init__(
            self,
            uv: torch.Tensor,
            cp_weights: torch.Tensor,
            cp_weights_du: torch.Tensor,
            cp_weights_dv: torch.Tensor,
            cp_weights_du2: torch.Tensor,
            cp_weights_dudv: torch.Tensor,
            cp_weights_dv2: torch.Tensor,
            indices: torch.Tensor,
            faces: torch.Tensor,
        ) -> None:
            self.uv = uv
            self.cp_weights = cp_weights
            self.cp_weights_du = cp_weights_du
            self.cp_weights_dv = cp_weights_dv
            self.cp_weights_du2 = cp_weights_du2
            self.cp_weights_dudv = cp_weights_dudv
            self.cp_weights_dv2 = cp_weights_dv2
            self.indices = indices
            self.faces = faces

        @property
        def num_points(self) -> int:
            return int(self.uv.shape[0])

        def to_device(self, device: torch.device) -> 'BaseInterface.CpBasedInterface.PreLoadData':
            self.uv = self.uv.to(device)
            self.cp_weights = self.cp_weights.to(device)
            self.cp_weights_du = self.cp_weights_du.to(device)
            self.cp_weights_dv = self.cp_weights_dv.to(device)
            self.cp_weights_du2 = self.cp_weights_du2.to(device)
            self.cp_weights_dudv = self.cp_weights_dudv.to(device)
            self.cp_weights_dv2 = self.cp_weights_dv2.to(device)
            self.indices = self.indices.to(device)
            self.faces = self.faces.to(device)
            return self

        def compute_point_weights(self, r: torch.Tensor) -> torch.Tensor:
            """Compute integration weights for preload points from mesh faces.

            Each triangular face contributes one-third of its area to each vertex.
            For quad faces, the face is split into two triangles.
            """
            faces = self.faces
            if faces.ndim != 2 or faces.shape[1] not in (3, 4):
                raise ValueError('PreLoadData.faces must be triangular or quadrilateral connectivity.')

            if faces.shape[1] == 4:
                triangles = torch.cat([
                    faces[:, [0, 1, 2]],
                    faces[:, [0, 2, 3]],
                ], dim=0)
            else:
                triangles = faces

            v0 = r[triangles[:, 0]]
            v1 = r[triangles[:, 1]]
            v2 = r[triangles[:, 2]]
            areas = torch.cross(v1 - v0, v2 - v0, dim=1).norm(dim=1) / 2.0

            weights = torch.zeros(r.shape[0], dtype=areas.dtype, device=r.device)
            weights = weights.index_add_(0, triangles[:, 0], areas / 3.0)
            weights = weights.index_add_(0, triangles[:, 1], areas / 3.0)
            weights = weights.index_add_(0, triangles[:, 2], areas / 3.0)
            return weights

    def __init__(self, *args, **kwargs) -> None:
        """
        Initialize the Surface class.

        Parameters:
            surface (Surface_Base) : The surface model.
            surf_type (int) : The type of the surface.
                - 0: bspline surface
                - 1: closed surface
            symmetric (list[int]) : The symmetry of the surface.
                - 0: no symmetry
                - 1: axis symmetry
                    0: x-axis symmetry
                    1: y-axis symmetry
                    2: z-axis symmetry
        """

        super().__init__(*args, **kwargs)

        self._cps: torch.Tensor
        """Control points tensor."""
        self._preload_data: CpBasedInterface.PreLoadData | None = None
        """Single container for all preloaded surface evaluation data."""

    def synchronize(self) -> None:
        """Synchronize the surface state with its model."""
        pass

    def _map(self, weights: torch.Tensor, indices: torch.Tensor, num_pts: int = None) -> torch.Tensor:

        if num_pts is None:
            num_pts = indices[0].max().item() + 1
        
        result = torch.zeros([num_pts, 3], dtype=self._cps.dtype)
        for i in range(3):
            result[:, i].scatter_add_(0, indices[0], weights * self._cps[indices[1], i])
        return result

    def apply_preload_data(self, preload: 'CpBasedInterface.PreLoadData') -> None:
        """Apply a standardized preload container to the interface."""
        self._preload_data = preload

    def pre_load(self, *args, **kwargs) -> None:
        """Preload data for surface evaluation. This method should be called before any geometry evaluation."""
        self._preload_data = self.get_preloaddata(*args, **kwargs)

    def get_preloaddata(self, pre_points: torch.Tensor | None = None, faces: torch.Tensor | None = None) -> 'CpBasedInterface.PreLoadData':
        """
        Create and return preload data for the surface.

        Args:
            pre_points (torch.Tensor | None): Optional sample points used for preload evaluation.
            faces (torch.Tensor | None): Optional face connectivity information used for point-weight calculations.

        Returns:
            CpBasedInterface.PreLoadData: The computed preload data. The returned object must include explicit face connectivity.
        """
        raise NotImplementedError("The preload method is not implemented in the CpBasedInterface class. Please implement it in the derived class.")

    @property
    def preload_data(self) -> 'CpBasedInterface.PreLoadData':
        if self._preload_data is None:
            raise RuntimeError('Preload data has not been initialized.')
        return self._preload_data

    def get_r(self, preload_data: Optional['CpBasedInterface.PreLoadData'] = None):
        """
        Get the point coordinates of the surface.

        Args:
            preload_data (Optional[CpBasedInterface.PreLoadData]): Optional external preload data.

        Returns:
            torch.Tensor: The point coordinates of the surface.
        """
        preload = preload_data if preload_data is not None else self.preload_data
        return self._map(preload.cp_weights, preload.indices, num_pts=preload.num_points)
    
    def get_rdu(self, preload_data: Optional['CpBasedInterface.PreLoadData'] = None):
        """
        Get the first partial derivatives of the surface.

        Args:
            preload_data (Optional[CpBasedInterface.PreLoadData]): Optional external preload data.

        Returns:
            torch.Tensor: The first partial derivatives of the surface.
                - shape: (num_points, 3, 2), the first derivative with respect to the first parameter and the second parameter.
        """
        preload = preload_data if preload_data is not None else self.preload_data
        rdu = self._map(preload.cp_weights_du, preload.indices, num_pts=preload.num_points)
        rdv = self._map(preload.cp_weights_dv, preload.indices, num_pts=preload.num_points)

        if not self.flip:
            rdu = -rdu
        return torch.stack([rdu, rdv], dim=2)
    
    def get_rdu2(self, preload_data: Optional['CpBasedInterface.PreLoadData'] = None):
        """
        Get the second partial derivatives of the surface.

        Args:
            preload_data (Optional[CpBasedInterface.PreLoadData]): Optional external preload data.

        Returns:
            torch.Tensor: The second partial derivatives of the surface.
                - shape: (num_points, 3, 2, 2), the second derivative with respect to the first parameter and the second parameter.
        """

        preload = preload_data if preload_data is not None else self.preload_data
        rdu2 = self._map(preload.cp_weights_du2, preload.indices, num_pts=preload.num_points)
        rduv = self._map(preload.cp_weights_dudv, preload.indices, num_pts=preload.num_points)
        rdv2 = self._map(preload.cp_weights_dv2, preload.indices, num_pts=preload.num_points)

        if not self.flip:
            rduv = -rduv
        return torch.stack([torch.stack([rdu2, rduv], dim=2),
                            torch.stack([rduv, rdv2], dim=2)], dim=2)

    @property
    def control_points(self) -> torch.Tensor:
        """
        Get the control points of the surface.

        Returns:
            torch.Tensor: The control points of the surface.
        """
        return self._cps

    def get_surface_parameters(self) -> torch.Tensor:
        """
        Get the design variables of the surface.

        Returns:
            x (torch.Tensor): The design variables of the surface.
        """
        return self._cps.flatten()
        

    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """
        Set the design variables of the surface.

        Parameters:
            x (torch.Tensor): The new design variables to be set.
        """
        self._cps = x.reshape(self._cps.shape)

    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the surface with the new design variables.

        Parameters:
            x_change (torch.Tensor): The change of design variables to be applied.
        """
        self._cps = self._cps + x_change.reshape(self._cps.shape)

    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get the geometry values of the surface.

        Returns:
            tuple: A tuple containing the geometry values of the surface.
                - r (torch.Tensor): The point coordinates of the surface.
                - rdu (torch.Tensor): The partial derivatives of the surface.
                - rdu2 (torch.Tensor): The second partial derivatives of the surface.
        """
        r = self.get_r()
        rdu = self.get_rdu()
        rdu2 = self.get_rdu2()
        return r, rdu, rdu2

    @property
    def num_variables(self) -> int:
        """
        Get the number of design variables.

        Returns:
            int: The number of design variables.
        """
        return self._cps.numel()


