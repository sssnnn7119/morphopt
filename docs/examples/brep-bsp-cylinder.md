# STEP 圆柱外边界与 BSP 内腔优化算例

[打开算例定义](brep-bsp-cylinder.morph)

<a id="section-模型定义"></a>

## 1 模型定义

该算例验证固定 BREP 外边界与可更新 BSP 内腔的混合构建、有限元求解和形状优化。长度采用 mm，力采用 N，应力和材料参数采用 MPa。

| 项目 | 设置 |
|---|---|
| 外边界 | `BREPSurface`，STEP 圆柱，半径 4 mm，长度 16 mm |
| 内腔 | `BspSurface` 圆柱，初始控制点半径 1.4 mm，长度 14 mm，底端 Z=1 mm |
| 内腔参数 | 二次 B 样条；控制网格采样尺寸 2 mm；无初始扰动 |
| 体网格 | 一阶四面体，目标尺寸 2 mm |
| 材料 | `NeoHookeanLnJ`，μ=0.3 MPa，κ=3 MPa |
| 边界条件 | 外圆柱底面节点集 `face_2_nodes` 固定三个平移自由度 |
| 端部连接 | 顶面节点集 `face_1_nodes` 与 `RP_tip` 耦合，参考点位于 `[0, 0, 16]` |
| 载荷 | 内腔压力 0.02 MPa，即 20 kPa；一个工况 |
| 优化目标 | 顶部轴向位移达到 0.15 mm，同时约束横向位移为零 |
| 设计范围 | 外边界 `is_updatable=False`，内腔 `is_updatable=True` |
| 几何约束 | Fairness、最小壁厚 1 mm 的 Distance、半径 4 mm 与 Z∈[0,16] 的 Cylinder 包络 |
| 更新器 | `ShapeDerivative`，每轮最多 5 次局部迭代 |
| 求解资源 | CPU，一个求解进程 |

外圆柱通过 UI 应用服务的 CADPart→BoundaryPart 转换生成，STEP 和原始 `face_N` 映射嵌入 `.morph`。打开算例不需要原始 STEP 文件或特定电脑路径。BSP 的半径参数定义控制点位置，实际曲面由这些控制点构成的 B 样条映射确定。

BREP 曲面通过 `face_N` 和 `face_N_nodes` 引用具体几何面，不生成 BSP 专有的 `Head/Bottom` 节点集。

<a id="section-ui-操作"></a>

## 2 UI 操作

1. 打开 `brep-bsp-cylinder.morph`。
2. 在几何节点选择 `body`。曲面 0 为 `outer_cylinder [BREPSurface]`，曲面 1 为 `inner_cavity [BspSurface]`。
3. 在资产页查看 `outer-cylinder.stp` 与面映射；在编辑页检查内腔参数、材料、压力、固定边界及顶部耦合。
4. 点击“开始优化”，在优化过程页查看目标值、网格及内腔变化。运行结果写入所选运行目录下的 `.results`。

运行持续到手动停止。下述回归脚本执行固定轮数，适合重复验证。

<a id="section-自动验证"></a>

## 3 自动验证

在项目根目录、已安装项目依赖的 Python 环境中执行：

```bash
python scripts/examples/brep_bsp_optimization.py --run --iterations 3
```

脚本读取现有 `.morph`，通过正式导出接口创建脚本与资产副本，再执行三轮实际的“重剖分→非线性求解→灵敏度→几何更新”，并保存普通运行归档。最后重新剖分更新后的几何，检查其仍可生成体网格。报告位于 `.results/brep-bsp-validation/report.json`。

重建初始 `.morph` 的命令为：

```bash
python scripts/examples/brep_bsp_optimization.py
```

自动验证检查外边界设计变量数为零、内腔设计变量非零、各轮求解收敛、目标与控制点有限、内腔控制点实际变化、STEP 文件内容不变、外边界节点仍位于解析圆柱表面，以及面集合、节点集与端部集合有效。

对应回归测试：

```bash
python -m pytest -q tests/optcore/test_brep_bsp_case.py
```

<a id="section-验证记录"></a>

## 4 验证记录

使用 CPU 和一个求解进程完成三轮验证。

| 轮次 | 目标值 | 顶部轴向位移 / mm | 节点数 | 四面体数 |
|---|---|---|---|---|
| 0 | 0.92844944 | 0.00547782 | 226 | 668 |
| 1 | 0.90656862 | 0.00723035 | 229 | 680 |
| 2 | 0.87561475 | 0.00976580 | 245 | 734 |

三轮非线性求解均收敛。最后一次更新后的几何重新剖分得到 256 个节点、770 个四面体；外边界 STEP 内容不变，BSP 控制点变化范数约为 6.02005 mm。目标值下降约 5.69%。该记录确认完整流程可执行，三轮结果尚未达到目标位移或优化收敛。
