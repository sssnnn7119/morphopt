"""
This module contains the GenerationModel class, which is responsible for generating the geometric model of the soft robot.
"""

import datetime
import math
import os
import shutil
import time
import numpy as np
import torch
from ..modelparams import Surfaces

class Genetrator:
    """
    This class is responsible for generating the geometric model of the soft robot.
    It uses Rhino for 3D modeling and Abaqus for finite element analysis (FEA).
    """
    
    def __init__(self, seed_size: float, surfaces: Surfaces, path_output: str, path_queue: str, ) -> None:
        """
        Initialize the Genetrator class.
        
        Parameters:
            surfaces (Surfaces): The surfaces of the soft robot.
            path_output (str): The path to the output directory.
            path_queue (str): The path to the queue directory.
        """
        

        self.surfaces = surfaces
        """
        Surfaces: The surfaces of the soft robot.
        """
        
        self.path_output = path_output
        """
        str: The path to the output directory.
        """
        
        self.path_queue = path_queue
        """
        str: The path to the queue directory.
        """
        
        self.seed_size = seed_size
        """
        float: The seed size for the finite element analysis (FEA).
        """
        
    def initialize(self, iteration: int) -> None:
        """
        This function initializes the generator.
        It is currently a placeholder and does not perform any operations.
        """
        pass
    
    def export_data(self, surfaces: Surfaces, path_output: str, path_queue: str) -> list[str]:
        """
        This function export the data of each surfaces
        """
        
        # export each surface with Rhino
        que_Names = []
        name_list = surfaces.export_data(filepath=path_output)
        for i in range(surfaces.num_surface):
            surf_name0 = '__surface-%d' % i
            name = name_list[i]
            
            info = '%d\n%s\n%s' % (surfaces.surface_list[i].surf_type, path_output +
                                name, path_output + surf_name0 + '.stp')
            que_name = 'T' + datetime.datetime.now().strftime(
                "%Y%m%d%H%M%S") + '_%d.txt' % i
            with open(path_queue + que_name, 'w') as f:
                f.write(info.replace('/', '\\\\'))
            que_Names.append(path_queue + que_name)
        for que_file in que_Names:
            while os.path.exists(que_file):
                time.sleep(0.1)    
        return que_Names
    

    def generate(self, material_para: list[float] | list[torch.Tensor]) -> None:
        """
        This function generates the geometric model of the soft robot.
        It calls the Rhino application to generate the model and then calls Abaqus for finite element analysis (FEA).
        """

        # export the data
        que_names = self.export_data(self.surfaces, self.path_output, self.path_queue)
        
        # call Rhino to generate the model
        self.__class__._call_rhino(que_Names=que_names)

        # call Abaqus for FEA
        self.__class__._call_Abaqus(self.surfaces, self.path_output, material_para, self.seed_size)
        
    @staticmethod
    def _call_rhino(que_Names: list[str]) -> None:
        """
        This function is a placeholder for calling Rhino, a 3D computer graphics and computer-aided design (CAD) application.
        It is currently not implemented.
        """
        for que_file in que_Names:
            while os.path.exists(que_file):
                time.sleep(0.1)

    @staticmethod
    def _call_Abaqus(surfaces: Surfaces, path_output: str, material_para: list[float], seed_size: float) -> None:
        
        current_path = os.getcwd()

        shutil.copy(os.path.dirname(os.path.abspath(__file__)) + '/_Abaqus/GenModel.py', path_output)
        with open(path_output + '__FEM_Para_Base.txt', 'w') as f:

            # surface type
            f.write('Surfaces*\t')
            for sf in surfaces.surface_list:
                f.write('%d\t' % sf.surf_type)
            f.write('\n')

            # materials
            f.write(
                'Material*\t%s\t%e\t%d\t%e\t%e\n' %
                ('Rubber', material_para[0], material_para[1],
                material_para[2], material_para[3]))

            # Seed size
            f.write('SeedSize*\t%e\n' % seed_size)
        
        os.chdir(path_output)
        os.system('abaqus cae noGUI=' + path_output + '/GenModel.py')
        os.chdir(current_path)

class ObjToStpConverter:
    def __init__(self):
        self.vertices = []
        self.faces = []
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
    
    def generate_stp_header(self, filename="model"):
        """生成STP文件头部"""
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
        
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
    
    def generate_stp_footer(self):
        """生成STP文件尾部"""
        return "ENDSEC;\nEND-ISO-10303-21;"
    
    def get_next_entity_id(self):
        """获取下一个实体ID"""
        current_id = self.entity_counter
        self.entity_counter += 1
        return current_id
    
    def find_unique_vertices(self):
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
    
    def find_shared_edges(self, vertex_map):
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
    
    def convert_obj_to_stp(self, obj_content, filename="model"):
        """将OBJ内容转换为STP格式，严格按照原始STP结构"""
        # 解析OBJ文件
        self.parse_obj_file(obj_content)
        
        if not self.vertices or not self.faces:
            raise ValueError("OBJ文件中没有找到有效的顶点或面数据")
        
        # 去重顶点
        unique_vertices, vertex_map = self.find_unique_vertices()
        edge_usage = self.find_shared_edges(vertex_map)
        
        # 生成STP内容
        stp_content = []
        stp_content.append(self.generate_stp_header(filename))
        
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
        self.add_supporting_entities_v2(stp_content, unique_vertices, vertex_map, cartesian_point_map, 
                                       spline_point_map, direction_ids, axis_placement_ids,
                                       product_def_id, product_def_context_id, product_def_formation_id,
                                       application_context_id, product_id, product_context_id,
                                       length_unit_id, plane_angle_unit_id, solid_angle_unit_id,
                                       uncertainty_measure_id, geometric_rep_context_id, shape_representation_id,
                                       axis2_placement_1_id, axis2_placement_2_id, direction_1_id, direction_2_id,
                                       direction_3_id, direction_4_id, cartesian_point_1_id, cartesian_point_2_id)
        
        stp_content.append(self.generate_stp_footer())
        return '\n'.join(stp_content)
    
    def add_supporting_entities_v2(self, stp_content, unique_vertices, vertex_map, cartesian_point_map, 
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


# def mesh_operation(input_files, output_file, mesh_size=1.5):
#     """
#     Perform boolean operations on multiple STP files and generate mesh
    
#     Args:
#         input_files: List of STP file names, first one is main body, others are subtracted
#         output_file: Output INP file name
#         mesh_size: Mesh element size
#     """

#     import gmsh
#     import time
#     # Initialize gmsh
#     gmsh.initialize()
    
#     # Set gmsh to quiet mode - reduce output
#     gmsh.option.setNumber("General.Terminal", 0)
#     gmsh.option.setNumber("General.Verbosity", 1)
#     gmsh.option.setNumber("General.NumThreads", 0)
#     gmsh.option.setNumber("Geometry.OCCParallel", 1)
    
#     start_time = time.time()
    
#     try:
#         # Import all STEP files
#         print("Importing STEP files........", end="")
#         import_start = time.time()
#         for file in input_files:
#             gmsh.merge(file)
#         import_time = time.time() - import_start
#         print(f" done ({import_time:.2f}s)")
        
#         # Get all volumes after import
#         volumes = gmsh.model.getEntities(3)
        
#         if len(volumes) >= 2:
#             # Optimize boolean operations
#             gmsh.option.setNumber("Geometry.Tolerance", 1e-2)
#             gmsh.option.setNumber("Geometry.ToleranceBoolean", 1e-2)
            
#             # Perform boolean subtraction: volume 0 - (volume 1 + volume 2 + ...)
#             print("Boolean operation...........", end="")
#             boolean_start = time.time()
#             main_volume = [(3, volumes[0][1])]
#             subtract_volumes = [(3, vol[1]) for vol in volumes[1:]]
            
#             result = gmsh.model.occ.cut(main_volume, subtract_volumes)
#             gmsh.model.occ.synchronize()
#             boolean_time = time.time() - boolean_start
#             print(f" done ({boolean_time:.2f}s)")
            
    
#         # Set mesh parameters for faster meshing
#         gmsh.option.setNumber("Mesh.ElementOrder", 1)  # Linear elements
#         gmsh.option.setNumber("Mesh.Algorithm", 1)     # MeshAdapt (faster than Frontal-Delaunay)
#         gmsh.option.setNumber("Mesh.Algorithm3D", 1)   # Delaunay (faster option)
#         gmsh.option.setNumber("Mesh.Optimize", 1)      # Enable optimization
#         gmsh.option.setNumber("Mesh.QualityType", 1)   # Enable quality checks
        
#         # Control mesh size (triangle size)
#         gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size)    # Minimum element size
#         gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size)    # Maximum element size
#         gmsh.option.setNumber("Mesh.MeshSizeFactor", mesh_size) # Global mesh size factor
        
#         # Use faster meshing options
#         gmsh.option.setNumber("Mesh.CharacteristicLengthFromPoints", 1)
#         gmsh.option.setNumber("Mesh.CharacteristicLengthFromCurvature", 0)
        
#         # Don't generate 2D surface elements, only 3D volume elements
#         gmsh.option.setNumber("Mesh.SaveAll", 0)
#         gmsh.option.setNumber("Mesh.MeshOnlyVisible", 0)
        
#         # Generate only 3D mesh (skip 2D generation)
#         print("Mesh generation.............", end="")
#         mesh_start = time.time()
#         gmsh.model.mesh.generate(3)
#         mesh_time = time.time() - mesh_start
#         print(f" done ({mesh_time:.2f}s)")
        
#         # Export to INP format
#         print("Exporting...................", end="")
#         export_start = time.time()
#         gmsh.write(output_file)
#         export_time = time.time() - export_start
#         print(f" done ({export_time:.2f}s)")
        
#         # Post-process INP file to remove 2D elements
#         post_process_inp(output_file)
        
#         total_time = time.time() - start_time
#         print(f"Total: {total_time:.2f}s | Output: {output_file}")
#         # Print mesh statistics
#         node_count = len(gmsh.model.mesh.getNodes()[0])
#         element_count = len(gmsh.model.mesh.getElements(3)[1][0])
#         print(f"Mesh statistics: {node_count} nodes, {element_count} elements")
        
#     except Exception as e:
#         print(f"Error: {e}")
    
#     finally:
#         gmsh.finalize()

# def post_process_inp(inp_file):
#     """
#     Post-process INP file to remove all 2D elements and renumber 3D elements
    
#     Args:
#         inp_file: Path to the INP file to process
#     """

#     import time
#     print("Post-processing INP file....", end="")
#     post_start = time.time()
    
#     try:
#         with open(inp_file, 'r') as f:
#             lines = f.readlines()
        
#         processed_lines = []
#         in_elements = False
#         skip_current_element_section = False
#         element_counter = 1
        
#         for line in lines:
#             line = line.strip()
            
#             # Check if we're entering elements section
#             if line.startswith('*ELEMENT'):
#                 in_elements = True
#                 skip_current_element_section = False
                
#                 # Check if this is a 2D element type that should be skipped
#                 line_upper = line.upper()
#                 # Common 2D element types in Abaqus
#                 if any(elem_type in line_upper for elem_type in [
#                     'CPS3', 'CPS4', 'CPS6', 'CPS8',  # Plane stress
#                     'CPE3', 'CPE4', 'CPE6', 'CPE8',  # Plane strain
#                     'CAX3', 'CAX4', 'CAX6', 'CAX8',  # Axisymmetric
#                     'S3', 'S4', 'S6', 'S8',          # Shell elements
#                     'M3D3', 'M3D4', 'M3D6', 'M3D8',  # Membrane
#                     'STRI3', 'STRI65', 'S3R', 'S4R', # Shell/membrane variants
#                     'DS3', 'DS4', 'DS6', 'DS8',       # Cohesive surface
#                     'T3D2'
#                 ]):
#                     skip_current_element_section = True
#                     continue
                
#                 # If it's a 3D element type or unspecified, keep it
#                 processed_lines.append(line + '\n')
#                 continue
            
#             # Check if we're leaving elements section
#             if line.startswith('*') and in_elements and not line.startswith('*ELEMENT'):
#                 in_elements = False
#                 skip_current_element_section = False
#                 processed_lines.append(line + '\n')
#                 continue
            
#             # Skip lines if we're in a 2D element section
#             if skip_current_element_section:
#                 continue
            
#             # Process element lines
#             if in_elements and line and not line.startswith('*'):
#                 # Parse element line
#                 parts = line.split(',')
#                 if len(parts) > 1:
#                     node_count = len(parts) - 1  # Subtract 1 for element ID
                    
#                     # Keep only 3D elements
#                     if node_count in [4, 6, 8, 10, 13, 14, 15, 20, 27]:
#                         # Renumber the element
#                         parts[0] = str(element_counter)
#                         processed_lines.append(','.join(parts) + '\n')
#                         element_counter += 1
#                 continue
            
#             # Keep all other lines
#             processed_lines.append(line + '\n' if line else '\n')
        
#         # Write processed content back to file
#         with open(inp_file, 'w') as f:
#             f.writelines(processed_lines)
        
#         post_time = time.time() - post_start
#         print(f" done ({post_time:.2f}s)")
        
#     except Exception as e:
#         print(f"Error in post-processing: {e}")
