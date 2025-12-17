import numpy as np
import math
from OCC.Core.gp import gp_Pnt, gp_Ax2, gp_Dir
from OCC.Core.TColgp import TColgp_Array2OfPnt
from OCC.Core.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
from OCC.Core.Geom import Geom_BSplineSurface
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge, 
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Sewing
)
from OCC.Core.TopoDS import TopoDS_Solid, topods
from OCC.Core.BRep import BRep_Builder
from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCC.Core.Interface import Interface_Static
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopAbs import TopAbs_SHELL

class BSplineSolidGenerator:
    def __init__(self, P0, degree_u=3, degree_v=3):
        """
        初始化 B-Spline 实体生成器
        
        参数:
            P0: numpy array, shape (3, numV, numU). 
                代表控制点 (Poles). 
                注意: U方向应为非重复的唯一控制点 (Periodic).
                如果输入数据包含重复的最后一列，请在传入前自行切片，或者本类会将其视为独立的控制点。
            degree_u: U方向阶数
            degree_v: V方向阶数
        """
        self.P0 = P0
        self.degree_u = degree_u
        self.degree_v = degree_v
        self.solid = None

    def build(self):
        """构建实体"""
        # 1. 准备数据
        # P0 shape: [3, numV, numU]
        num_poles_v = self.P0.shape[1]
        num_poles_u = self.P0.shape[2]
        
        # 转换 Poles 到 OCC 格式
        poles = TColgp_Array2OfPnt(1, num_poles_u, 1, num_poles_v)
        for i in range(num_poles_u):
            for j in range(num_poles_v):
                pt = self.P0[:, j, i]
                poles.SetValue(i + 1, j + 1, gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))

        # 2. 准备 Knots 和 Mults
        
        # U方向 (Periodic): Uniform Knots
        # 对于周期性曲面，Knots 数量通常为 num_poles_u + 1
        knots_u = TColStd_Array1OfReal(1, num_poles_u + 1)
        mults_u = TColStd_Array1OfInteger(1, num_poles_u + 1)
        for i in range(num_poles_u + 1):
            knots_u.SetValue(i + 1, float(i))
            mults_u.SetValue(i + 1, 1)
            
        # V方向 (Non-Periodic, Clamped):
        # Knots 数量 = num_poles_v - degree_v + 1
        num_knots_v = num_poles_v - self.degree_v + 1
        knots_v = TColStd_Array1OfReal(1, num_knots_v)
        mults_v = TColStd_Array1OfInteger(1, num_knots_v)
        
        for i in range(num_knots_v):
            knots_v.SetValue(i + 1, float(i))
            if i == 0 or i == num_knots_v - 1:
                mults_v.SetValue(i + 1, self.degree_v + 1)
            else:
                mults_v.SetValue(i + 1, 1)

        # 3. 创建曲面
        bspline_surface = Geom_BSplineSurface(
            poles, 
            knots_u, knots_v, 
            mults_u, mults_v, 
            self.degree_u, self.degree_v, 
            True, False # IsUPeriodic=True, IsVPeriodic=False
        )

        # 4. 创建面
        # 侧面
        face_side = BRepBuilderAPI_MakeFace(bspline_surface, 1e-6).Face()
        
        # 顶底面 (使用 VIso 提取等参线，保证水密性)
        u_min, u_max, v_min, v_max = bspline_surface.Bounds()
        
        # 底面 (V=v_min)
        edge_bottom = BRepBuilderAPI_MakeEdge(bspline_surface.VIso(v_min)).Edge()
        wire_bottom = BRepBuilderAPI_MakeWire(edge_bottom).Wire()
        face_bottom = BRepBuilderAPI_MakeFace(wire_bottom).Face()
        
        # 顶面 (V=v_max)
        edge_top = BRepBuilderAPI_MakeEdge(bspline_surface.VIso(v_max)).Edge()
        wire_top = BRepBuilderAPI_MakeWire(edge_top).Wire()
        face_top = BRepBuilderAPI_MakeFace(wire_top).Face()

        # 5. 缝合所有面
        sewer = BRepBuilderAPI_Sewing(1e-6)
        sewer.Add(face_side)
        sewer.Add(face_bottom)
        sewer.Add(face_top)
        sewer.Perform()
        
        sewed_shape = sewer.SewedShape()
        
        # 6. 转换为实体
        if sewed_shape.ShapeType() == TopAbs_SHELL:
            builder = BRep_Builder()
            self.solid = TopoDS_Solid()
            builder.MakeSolid(self.solid)
            builder.Add(self.solid, topods.Shell(sewed_shape))
        else:
            self.solid = sewed_shape
            
        return self.solid

    def export_step(self, filename):
        """导出 STEP 文件"""
        if not self.solid:
            print("Error: Solid not built yet. Call build() first.")
            return False
            
        Interface_Static.SetCVal("write.step.unit", "MM")
        Interface_Static.SetCVal("write.step.schema", "AP214")
        
        writer = STEPControl_Writer()
        status = writer.Transfer(self.solid, STEPControl_AsIs)
        
        if status != IFSelect_RetDone:
            print(f"Transfer failed with status: {status}")
            return False
            
        status = writer.Write(filename)
        if status == IFSelect_RetDone:
            print(f"Successfully exported to {filename}")
            return True
        else:
            print(f"Write failed with status: {status}")
            return False

def main():
    print("="*50)
    print("BSpline Cylinder Generator Test")
    print("="*50)

    # 1. 生成测试数据 (Unique Poles)
    radius = 10.0
    height = 30.0
    numU = 10 # U方向唯一控制点数量 (不包含重复点)
    numV = 10 # V方向控制点数量
    
    print(f"Generating control points: {numU}x{numV}")
    
    P0 = np.zeros([3, numV, numU])
    for i in range(numU):
        # 均匀分布在 0 到 2pi 之间 (不包含 2pi，因为是周期性的)
        theta = 2 * math.pi * i / numU 
        for j in range(numV):
            z = height * j / (numV - 1)
            x = radius * math.cos(theta)
            y = radius * math.sin(theta)
            P0[:, j, i] = [x, y, z]
            
    # 2. 添加随机扰动
    print("Adding perturbation...")
    np.random.seed(42)
    noise_scale = 5.0
    perturbation = (np.random.rand(3, numV, numU) - 0.5) * noise_scale
    
    # 约束: 保持顶底面平整 (Z方向无扰动)
    perturbation[2, 0, :] = 0
    perturbation[2, numV-1, :] = 0
    
    P0 += perturbation
    
    # 3. 使用类生成实体
    print("Building solid...")
    generator = BSplineSolidGenerator(P0, degree_u=4, degree_v=4)
    solid = generator.build()
    
    # 4. 导出
    output_file = "Z:/temp/cylinder_class.stp"
    print(f"Exporting to {output_file}...")
    generator.export_step(output_file)
    
    # 5. 可视化 (可选)
    try:
        from OCC.Display.SimpleGui import init_display
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        display, start_display, add_menu, add_function_to_menu = init_display()
        
        ais_shapes = display.DisplayShape(solid, update=True)
        if not isinstance(ais_shapes, list):
            ais_shapes = [ais_shapes]
            
        for ais_shape in ais_shapes:
            # 显示 B-Spline 的等参线 (Isoparametric curves) - 即曲面的"线框"
            drawer = ais_shape.Attributes()
            drawer.UIsoAspect().SetNumber(11) # U方向显示11条线
            drawer.VIsoAspect().SetNumber(11) # V方向显示11条线
            drawer.SetFaceBoundaryDraw(True)  # 显示面边界
            display.Context.Redisplay(ais_shape, True)
            
        # 显示控制点
        print("Displaying control points...")
        for i in range(numU):
            for j in range(numV):
                pt = P0[:, j, i]
                pnt = gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2]))
                vertex = BRepBuilderAPI_MakeVertex(pnt).Vertex()
                display.DisplayShape(vertex, update=False, color="RED")
        
        display.Repaint()
        
        print("\nPress ESC to exit viewer.")
        start_display()
    except ImportError:
        print("Visualization not available (pythonocc-core not installed or no GUI).")


if __name__ == "__main__":
    main()
