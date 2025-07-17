
import torch


import FEA

    
class FE_result:
    """
    A class to store the results of the FEA solver.

    Attributes:
        fe (FEA.FEA_Main): The FEA solver instance.
        U (torch.Tensor): The displacement field.
        Udp (torch.Tensor): The Jacobian.   
        UdF (torch.Tensor): The derivative of the displacement field with respect to the external force on the end-effector.
        ADJu (torch.Tensor): The first adjoint displacement field.
        ADJudp (torch.Tensor): The second adjoint displacement field.
        ADJudf (torch.Tensor): The adjoint displacement field with respect to the external force on the end-effector.
        pressure_list (torch.Tensor): The pressure.

    """

    def __init__(self, fe: FEA.FEA_Main, pressure_list: torch.Tensor,
                    U: torch.Tensor, GCv: torch.Tensor = None, UdF: torch.Tensor = None, Udp: torch.Tensor = None,
                    GCw: torch.Tensor = None, GCudf: torch.Tensor = None):

        self.fe = fe
        """
        The FEA solver instance.
        """

        self.U = U.cpu()
        """
        The displacement field.
        """
        
        self.Udp = Udp.cpu()
        """
        The Jacobian.
        """

        self.UdF = UdF.cpu()
        """
        The direvative of the displacement field with respect to the external force on the end-effector.
        """
        
        self.ADJu = GCv.cpu()
        """
        The first adjoint displacement field.
        """
        
        self.ADJudp = GCw.cpu()
        """
        The second adjoint displacement field.
        """

        self.ADJudf = GCudf.cpu()
        """
        The adjoint displacement field with respect to the external force on the end-effector.
        """
        
        self.pressure_list = pressure_list.cpu()
        """
        The pressure.
        """

    def __str__(self) -> str:

        # 在类中添加矩阵格式化方法
        def format_matrix(matrix, indent=2, float_fmt=".6f"):
            """格式化二维矩阵为对齐的多行字符串"""
            if not matrix or not matrix[0]:
                return []
            
            # 转换为字符串并计算列宽
            str_matrix = []
            col_widths = [0] * len(matrix[0])
            for row in matrix:
                str_row = [format(x, float_fmt) for x in row]
                str_matrix.append(str_row)
                for j, val in enumerate(str_row):
                    if len(val) > col_widths[j]:
                        col_widths[j] = len(val)
            
            # 构建对齐的输出行
            formatted_lines = []
            indent_str = " " * indent
            for row in str_matrix:
                line = indent_str
                for j, val in enumerate(row):
                    # 右对齐数字，元素间保留2个空格
                    line += f"{val:>{col_widths[j]}}  "
                formatted_lines.append(line.rstrip())
            
            return formatted_lines
        

        result = ["FE_result Summary:"]
        
        num_tasks = self.pressure_list.shape[0]

        for i in range(num_tasks):
            result.append(f"=================================Task {i+1}=================================")
            
            # 格式化压力向量（一维）
            pressure = self.pressure_list[i].tolist()
            pressure_str = " ".join([f"{x:.6f}" for x in pressure])
            result.append(f"  Pressure:    {pressure_str}")
            
            # 格式化位移向量（一维）
            u_vector = self.U[i][-6:].tolist()
            u_str = " ".join([f"{x:.6f}" for x in u_vector])
            result.append(f"  Displacement U: {u_str}")
            
            # 格式化Jacobian矩阵（二维）
            if self.Udp is not None:
                matrix = self.Udp[i][:, -6:].T.tolist()  # 二维矩阵
                result.append(f"  Jacobian Udp:")
                # 格式化并添加矩阵每行
                formatted = format_matrix(matrix, indent=4)
                result.extend(formatted)
            
            # 格式化UdF矩阵（二维）
            if self.UdF is not None:
                matrix = self.UdF[i][:, -6:].tolist()  # 二维矩阵
                result.append(f"  UdF:")
                formatted = format_matrix(matrix, indent=4)
                result.extend(formatted)

            result.append(f"============================================================================")
        
        return "\n".join(result)
        
    def __getitem__(self, key):
        """
        Get the attribute with the given key.
        
        Parameters:
            key: The key of the attribute to get.
            
        Returns:
            The attribute value.
            
        Raises:
            KeyError: If the key is not found.
        """
        if hasattr(self, key):
            return getattr(self, key)
        else:
            raise KeyError(f"'{key}' not found in FE_result")

    def save_figure(self, filepath: str, iteration: int) -> None:
        """
        Save the figures of the FEA results.

        Parameters:
            filepath (str): The path to save the figures.
            iteration (int): The current iteration number.
        """
        surfaces = ['surface_0_All'] + ['surface_%d_All' % i for i in range(1, self.pressure_list.shape[1]+1)]
        surface_elements: list[FEA.elements.BaseSurface] = []
        for i in range(len(surfaces)):
            surface_elements = surface_elements + self.fe.get_surface_elements(surfaces[i])
        
        surface_connections = [surface_elements[i].surf_elems_circ.cpu().numpy() for i in range(len(surface_elements))]

        for case in range(self.pressure_list.shape[0]):
            deformed_nodes = (self.fe.nodes + self.fe._GC2RGC(self.U[case].to(self.fe.nodes.device))[0]).detach().cpu().numpy()

            from mayavi import mlab
            from matplotlib.tri import Triangulation
            from tvtk.api import tvtk
            from tvtk.common import configure_input_data

            fig = mlab.figure(size=(800, 800), bgcolor=(1, 1, 1))
            fig.scene.parallel_projection = True
            
            # Draw all surface connections using TVTK

            # Create a dataset with points and cells
            points = tvtk.Points()
            points.from_array(deformed_nodes)

            polys = tvtk.CellArray()
            mesh = tvtk.PolyData()
            mesh.points = points

            # Add all surface connections as polygons - optimized version
            # Pre-calculate the total number of cells and points for pre-allocation
            total_cells = sum(len(connection) for connection in surface_connections)
            polys.allocate(total_cells)

            # Process all faces more efficiently
            for connection in surface_connections:
                for face in connection:
                    # Skip if any node is -1 (placeholder)
                    if -1 in face:
                        continue
                    
                    # More efficient cell insertion
                    n_points = len(face)
                    # Convert face to a list/array compatible with VTK
                    polys.insert_next_cell(n_points)
                    for point_idx in face:
                        polys.insert_cell_point(point_idx)

            mesh.polys = polys

            # Create a mapper and actor
            mapper = tvtk.PolyDataMapper()
            configure_input_data(mapper, mesh)
            actor = tvtk.Actor(mapper=mapper)
            actor.property.color = (40.0/255, 120.0/255, 181.0/255)
            actor.property.opacity = 0.6

            # Add the actor to the scene
            fig.scene.add_actor(actor)

            mlab.view(azimuth=210, elevation=70, distance=300)
            mlab.savefig(f"{filepath}/task_{case}_iter_{iteration}.png")
            mlab.close(fig)