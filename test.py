from OCC.Core.gp import gp_Pnt, gp_Ax2, gp_Dir, gp_Circ
from OCC.Core.GC import GC_MakeArcOfCircle, GC_MakeSegment
from OCC.Core.Geom import Geom_Curve
from OCC.Core.GeomAPI import GeomAPI_PointsToBSpline
from OCC.Core.TColgp import TColgp_Array1OfPnt
from OCC.Core.GeomAbs import GeomAbs_C2
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge, 
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Sewing
)
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_MakePipe
from OCC.Core.TopoDS import TopoDS_Solid, TopoDS_Shell, topods
from OCC.Core.BRep import BRep_Builder, BRep_Tool
from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCC.Core.Interface import Interface_Static
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
from OCC.Core.TColgp import TColgp_Array2OfPnt
from OCC.Core.Geom import Geom_BSplineSurface
import math

import numpy as np

# ==================== 主要功能函数 ====================

def create_cylinder_with_bottom_and_top(radius, height):
    """
    创建带底面和顶面的圆柱实体
    返回TopoDS_Solid对象
    """
    return create_cylinder_manually(radius, height)

def create_cylinder_manually(radius, height):
    """手动创建带端盖的圆柱 (使用Geom_BSplineSurface)"""

    # 1. 生成控制点 (Control Points)
    numU = 10  # U方向点数 (包含重复的终点)
    numV = 10  # V方向点数
    degree_u = 3 # U方向阶数 (Cubic)
    degree_v = 3 # V方向阶数 (Cubic)
    
    P0 = np.zeros([3, numV, numU])
    for i in range(numU):
        theta = 2 * math.pi * i / (numU - 1)
        for j in range(numV):
            z = height * j / (numV - 1)
            x = radius * math.cos(theta)
            y = radius * math.sin(theta)
            P0[:, j, i] = [x, y, z]

    # 添加随机扰动
    np.random.seed(42)
    noise_scale = 3.0
    perturbation = (np.random.rand(3, numV, numU) - 0.5) * noise_scale
    
    # 约束1: 保持顶底面平整 (Z方向无扰动)
    perturbation[2, 0, :] = 0
    perturbation[2, numV-1, :] = 0
    
    # 约束2: 保持圆柱闭合 (theta=0 和 theta=2pi 处扰动一致)
    perturbation[:, :, numU-1] = perturbation[:, :, 0]
    
    P0 += perturbation

    # 2. 构建 B-Spline 曲面
    # 注意：对于周期性 B-Spline，不需要重复的末端控制点
    # 因此我们取 P0[:, :, :-1]
    poles_np = P0[:, :, :-1] 
    num_poles_u = poles_np.shape[2] # 9
    num_poles_v = poles_np.shape[1] # 10
    
    # 转换 Poles 到 TColgp_Array2OfPnt
    poles = TColgp_Array2OfPnt(1, num_poles_u, 1, num_poles_v)
    for i in range(num_poles_u):
        for j in range(num_poles_v):
            pt = poles_np[:, j, i]
            poles.SetValue(i + 1, j + 1, gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))
            
    # 准备 Knots 和 Mults
    
    # U方向 (Periodic): Uniform Knots
    # Knots: 0, 1, ..., num_poles_u
    # Mults: 1, 1, ..., 1
    knots_u = TColStd_Array1OfReal(1, num_poles_u + 1)
    mults_u = TColStd_Array1OfInteger(1, num_poles_u + 1)
    for i in range(num_poles_u + 1):
        knots_u.SetValue(i + 1, float(i))
        mults_u.SetValue(i + 1, 1)
        
    # V方向 (Non-Periodic): Clamped Knots
    # Knots count = num_poles_v - degree_v + 1
    # Range: 0 to num_poles_v - degree_v
    num_knots_v = num_poles_v - degree_v + 1
    knots_v = TColStd_Array1OfReal(1, num_knots_v)
    mults_v = TColStd_Array1OfInteger(1, num_knots_v)
    
    for i in range(num_knots_v):
        knots_v.SetValue(i + 1, float(i))
        if i == 0 or i == num_knots_v - 1:
            mults_v.SetValue(i + 1, degree_v + 1)
        else:
            mults_v.SetValue(i + 1, 1)
            
    # 创建曲面
    bspline_surface_geom = Geom_BSplineSurface(
        poles, 
        knots_u, knots_v, 
        mults_u, mults_v, 
        degree_u, degree_v, 
        True, False # IsUPeriodic=True, IsVPeriodic=False
    )
    
    # 3. 创建侧面 Face
    cylinder = BRepBuilderAPI_MakeFace(bspline_surface_geom, 1e-6).Face()
    
    # 获取曲面参数范围
    u_min, u_max, v_min, v_max = bspline_surface_geom.Bounds()

    # 4. 创建底面 (直接从曲面提取边界 V=v_min)
    bottom_curve = bspline_surface_geom.VIso(v_min)
    bottom_edge = BRepBuilderAPI_MakeEdge(bottom_curve).Edge()
    bottom_wire = BRepBuilderAPI_MakeWire(bottom_edge).Wire()
    bottom_face = BRepBuilderAPI_MakeFace(bottom_wire).Face()
    
    # 5. 创建顶面 (直接从曲面提取边界 V=v_max)
    top_curve = bspline_surface_geom.VIso(v_max)
    top_edge = BRepBuilderAPI_MakeEdge(top_curve).Edge()
    top_wire = BRepBuilderAPI_MakeWire(top_edge).Wire()
    top_face = BRepBuilderAPI_MakeFace(top_wire).Face()
    
    # 6. 缝合所有面
    sewer = BRepBuilderAPI_Sewing(1e-6)
    sewer.Add(cylinder)
    sewer.Add(bottom_face)
    sewer.Add(top_face)
    sewer.Perform()
    
    # 7. 转换为实体
    sewed_shape = sewer.SewedShape()
    
    # 检查是否是Shell
    from OCC.Core.TopAbs import TopAbs_SHELL
    if sewed_shape.ShapeType() == TopAbs_SHELL:
        builder = BRep_Builder()
        solid = TopoDS_Solid()
        builder.MakeSolid(solid)
        builder.Add(solid, topods.Shell(sewed_shape))
        return solid
    else:
        # 如果已经是Solid，直接返回
        return sewed_shape


def export_to_step(shape, filename, units="MM"):
    """
    导出形状到STEP文件
    
    参数:
        shape: TopoDS_Shape 对象
        filename: 输出文件名
        units: 单位 ("MM", "INCH", "M", "CM"等)
    """
    # 设置STEP单位
    Interface_Static.SetCVal("write.step.unit", units)
    # 设置STEP版本（AP214为常用工业标准）
    Interface_Static.SetCVal("write.step.schema", "AP214")
    
    # 创建STEP写入器
    step_writer = STEPControl_Writer()
    
    # 转换形状
    status = step_writer.Transfer(shape, STEPControl_AsIs)
    
    if status != IFSelect_RetDone:
        print(f"转换失败，状态码: {status}")
        return False
    
    # 写入文件
    status = step_writer.Write(filename)
    
    if status == IFSelect_RetDone:
        print(f"STEP文件已保存: {filename}")
        return True
    else:
        print(f"写入失败，状态码: {status}")
        return False

def check_shape_info(shape):
    """检查形状信息"""
    from OCC.Core.TopAbs import (
        TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_SOLID,
        TopAbs_SHELL, TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE, TopAbs_VERTEX
    )
    
    shape_type = shape.ShapeType()
    
    type_names = {
        TopAbs_COMPOUND: "Compound",
        TopAbs_COMPSOLID: "CompSolid", 
        TopAbs_SOLID: "Solid",
        TopAbs_SHELL: "Shell",
        TopAbs_FACE: "Face",
        TopAbs_WIRE: "Wire",
        TopAbs_EDGE: "Edge",
        TopAbs_VERTEX: "Vertex"
    }
    
    type_name = type_names.get(shape_type, "Unknown")
    print(f"形状类型: {type_name}")
    
    # 计算边界框
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepBndLib import brepbndlib_Add
    bbox = Bnd_Box()
    brepbndlib_Add(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    
    print(f"边界框尺寸: [{xmin:.2f}, {ymin:.2f}, {zmin:.2f}] -> [{xmax:.2f}, {ymax:.2f}, {zmax:.2f}]")
    print(f"尺寸: X={xmax-xmin:.2f}, Y={ymax-ymin:.2f}, Z={zmax-zmin:.2f}")
    
    return type_name

# ==================== 主程序 ====================

def main():
    # 参数设置
    radius = 10.0
    height = 30.0
    
    print("=" * 50)
    print("创建圆柱体")
    print(f"半径: {radius}, 高度: {height}")
    print("=" * 50)
    
    # 创建圆柱实体
    print("\n1. 创建圆柱实体...")
    cylinder_solid = create_cylinder_with_bottom_and_top(radius, height)
    
    # 检查形状信息
    print("\n2. 检查形状信息...")
    shape_type = check_shape_info(cylinder_solid)
    
    if shape_type != "Solid":
        print(f"警告：形状类型为 {shape_type}，不是Solid")
    
    # 验证实体
    print("\n3. 验证实体有效性...")
    try:
        from OCC.Core.BRepCheck import BRepCheck_Analyzer
        analyzer = BRepCheck_Analyzer(cylinder_solid)
        if analyzer.IsValid():
            print("✓ 实体验证通过：有效的封闭实体")
        else:
            print("⚠ 实体验证未通过，但继续导出")
    except ImportError:
        print("⚠ 无法导入BRepCheck_Analyzer，跳过验证")
    
    # 导出STEP文件
    print("\n4. 导出STEP文件...")
    output_files = ["Z:/temp/cylinder.stp", "Z:/temp/cylinder.step"]
    
    for filename in output_files:
        success = export_to_step(cylinder_solid, filename)
        if success:
            print(f"✓ 成功导出: {filename}")
            break
    
    print("\n" + "=" * 50)
    print("完成！")
    print("=" * 50)
    
    # 可选：显示形状（需要可视化支持）
    try:
        from OCC.Display.SimpleGui import init_display
        # init_display 通常返回4个对象，需要全部接收
        display, start_display, add_menu, add_function_to_menu = init_display()
        display.DisplayShape(cylinder_solid, update=True)
        print("n提示：按ESC键退出显示窗口")
        start_display()
    except ImportError:
        print("\n提示：安装pythonocc-core[visualization]以启用可视化")
        print(" pip install pythonocc-core[visualization]")

# ==================== 直接执行 ====================

if __name__ == "__main__":
    main()