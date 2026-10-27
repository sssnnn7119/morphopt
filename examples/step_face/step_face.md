# STEP 圆柱单面优化

本例将 STEP 圆柱的侧面 `face_0` 转换为 NURBS 设计面，并保持上下端盖固定。控制点间距由 `control_point_spacing` 设置。

## 文件

- [step_face.py](step_face.py)：可直接运行的任务脚本。
- [step_face.morph](step_face.morph)：对应的 UI 定义；`design_faces` 显式指定 `face_0`。
- [assets/cylinder.stp](assets/cylinder.stp)：输入 STEP 几何。
- [assets/cylinder.brep.json](assets/cylinder.brep.json)：STEP 几何的面、边和节点集合元数据。

## 模型定义

圆柱半径为 2 mm，长度为 5 mm，有限元网格尺寸为 1.2 mm。底面固定，顶部通过参考点施加 0.05 MPa 压力。材料为 Neo-Hookean，剪切模量 μ=10 MPa、体积模量 κ=100 MPa。几何更新器仅更新侧面 NURBS 控制点，上下端盖作为固定几何边界。

## 运行

在已安装 MorphOpt 的 Python 环境中，从仓库根目录执行：

```bash
python examples/step_face/step_face.py
```

UI 使用方式为打开 `step_face.morph`。运行脚本时，STEP 和 BREP 元数据从同目录的 `assets/` 读取。
