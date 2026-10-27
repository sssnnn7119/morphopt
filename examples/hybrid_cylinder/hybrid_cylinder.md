# STEP 圆柱外边界与 BSP 内腔

本例使用固定的 STEP 外圆柱和可更新的 BSP 内腔完成有限元求解与形状优化。长度采用 mm，力采用 N，应力及材料参数采用 MPa。

## 文件

- [hybrid_cylinder.py](hybrid_cylinder.py)：可直接运行的任务脚本。
- [hybrid_cylinder.morph](hybrid_cylinder.morph)：对应的 UI 定义。STEP 几何以 Base64 保存在定义中。
- [assets/](assets/)：脚本运行时使用的 STEP 文件及其 BREP 元数据。

## 模型定义

| 项目 | 设置 |
|---|---|
| 外边界 | 半径 4 mm、长度 16 mm 的固定 BREP 圆柱 |
| 内腔 | 半径 1.4 mm、长度 14 mm，底端 Z=1 mm 的可更新 BSP 圆柱 |
| 网格 | 一阶四面体，目标尺寸 2 mm |
| 材料 | Neo-Hookean，μ=0.3 MPa，κ=3 MPa |
| 边界条件 | 圆柱底面固定；顶面与 `[0, 0, 16]` 处的参考点耦合 |
| 载荷 | 内腔压力 0.02 MPa |
| 优化目标 | 顶部位移逼近 Z 向 0.15 mm，横向位移保持为零 |
| 几何约束 | 平滑性、曲面最小间距和圆柱包络 |

BREP 曲面通过面映射提供网格集合；BSP 内腔提供可微的几何设计变量。形状更新只作用于 BSP 内腔，外侧 STEP 边界保持固定。

## 运行

在已安装 MorphOpt 的 Python 环境中，从仓库根目录执行：

```bash
python examples/hybrid_cylinder/hybrid_cylinder.py
```

UI 使用方式为打开 `hybrid_cylinder.morph` 并启动优化。运行结果保存在算例目录下的 `.results/`。
