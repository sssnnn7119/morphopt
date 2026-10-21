# 灵敏度与设计更新

[代码结构导览](README.md) · [模型协议](model.md#protocols) · [运行时](runtime.md)

## 目录

<!-- docs:toc depth=1 -->

- [1 源码入口](#section-源码入口)
- [2 目标、指标与梯度路径](#gradients)
- [3 更新器注册与目标所有权](#section-更新器注册与目标所有权)
- [4 局部子问题与写回](#section-局部子问题与写回)
- [5 边界形状设计](#shape)
- [6 SIMP 材料设计](#simp)
- [7 偏置层与协同设计](#section-偏置层与协同设计)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 源码入口

| 路径 | 责任 |
|---|---|
| [`optcore/objfunc.py`](../../src/morphopt/optcore/objfunc.py) | 多工况目标及伴随/自动微分灵敏度 |
| [`optcore/updaters.py`](../../src/morphopt/optcore/updaters.py) | 更新器注册、目标解析、梯度切片与公共优化算法 |
| [`shapeopt/boundary_part.py`](../../src/morphopt/shapeopt/boundary_part.py)、[`surfaces/`](../../src/morphopt/shapeopt/surfaces) | 边界部件与曲面设计变量 |
| [`shapeopt/meshgenerator.py`](../../src/morphopt/shapeopt/meshgenerator.py) | 曲面几何到体网格的构建管线 |
| [`shapeopt/update_boundary_part.py`](../../src/morphopt/shapeopt/update_boundary_part.py)、[`objectivefuncs/`](../../src/morphopt/shapeopt/objectivefuncs) | 形状局部子问题 |
| [`simp/simpmaterial.py`](../../src/morphopt/simp/simpmaterial.py) | B 样条设计场、材料缩放与正则化单元 |
| [`simp/update_simpmaterial.py`](../../src/morphopt/simp/update_simpmaterial.py)、[`objectivefuncs/`](../../src/morphopt/simp/objectivefuncs) | 材料局部子问题 |
| [`codesign/`](../../src/morphopt/codesign) | 偏置部件、专用更新器与约束 |

<a id="gradients"></a>

## 2 目标、指标与梯度路径

`ObjectiveFunction.objective_function()` 返回保留计算图的标量损失，框架执行最小化。`get_metrics()` 返回独立记录的响应，不参与优化驱动。需要载荷响应雅可比的目标通过 `jacobian_needed` 声明载荷名。

```text
Params.obtain_design_sensitivity_vars(assembly)
  → {geometry, feamodel, materials}
  → 按集合顺序展平拼接
  → TorchFEA 多工况目标/伴随灵敏度
      试探设计 → Params.modify_assembly() → 目标求值
  → 按原区间拆分分类梯度
  → Updaters.update(gradients)
```

`geometry`、`feamodel`、`materials` 是梯度集合键。现有更新器管理器提供几何与材料两类注册入口，出现 `feamodel` 梯度不表示已配置载荷设计更新器。

梯度布局由集合、接口及对象内部参数的顺序共同决定。对象的 `num_variables`、参数展平、灵敏度输入和写回顺序必须一致，恢复状态也沿用该布局。

<a id="section-更新器注册与目标所有权"></a>

## 3 更新器注册与目标所有权

`Updaters` 是管理器，`BaseUpdater` 是一个设计对象的局部更新器。

| 机制 | 定义 |
|---|---|
| `add_geometry_updater()` | 绑定几何集合中的目标 |
| `add_material_updater()` | 绑定材料集合中的目标 |
| 注册 `name` | 默认目标接口名及管理器内的键 |
| `interface_name` | 可显式覆盖绑定目标 |
| `update_kind`、`target_type` | 基类声明的集合类型与目标类型约束 |
| `bind_target(target)` | 接收管理器已解析的模型对象 |

子优化器构造时只保存算法参数和目标名。注册时调用 `define_objective()`；管理器初始化时解析目标，再调用子优化器初始化。子优化器绑定后保存 `self.part` 或 `self.material`，不另持整个参数集合。

同一子类可创建多个独立对象，分别绑定不同 Part 或材料。注册方法、显式目标、变量切片与状态目录应共同指向同一设计接口。

<a id="section-局部子问题与写回"></a>

## 4 局部子问题与写回

`reinitialize(gradient)` 接收当前目标的梯度并准备局部基准状态、目标项和约束缓存；`update()` 求解局部 L-BFGS 子问题；`update_variables()` 将改变量写回设计对象。

| 配置或状态 | 作用 |
|---|---|
| `max_step_iter` | 单次设计更新内部迭代上限 |
| `max_step_length` | 更新步长配置 |
| `if_update` | 几何的逐曲面开关，或材料的整体开关 |
| 前次改变量与当前步长 | 局部算法的迭代状态 |
| `save/load()` | 按目标接口保存和恢复局部状态 |

局部更新的设备上下文覆盖目标、约束及其缓存 Tensor，完成后恢复相应设备状态。几何与材料子优化器分别保存到 `geometryupdater/<接口>/` 和 `materialupdater/<接口>/`，不共享一份步长文件。

<a id="shape"></a>

## 5 边界形状设计

`BoundaryPart` 继承 `BasePart` 与可更新协议，管理有序曲面。曲面 0 为外边界，后续曲面为内腔；`define_surfaces()` 声明曲面，`build_part()` 将当前边界网格化为实体。

| 层次 | 实现与职责 |
|---|---|
| `BaseSurface` | 曲面几何、采样、导出与共享行为 |
| `ControlPointSurface` | 控制点参数及预加载数据 |
| `BspSurface` | B 样条曲面与圆柱工厂 |
| `CPGEOSurface` | CPGEO 曲面、圆柱和球面工厂 |
| `FixedSurface` | 固定三角曲面，不提供可更新控制点 |
| 曲面约束 | BSP/CPGEO 镜面、旋转或跨曲面关联 |
| `UpdaterBoundaryPart` | 绑定单个 BoundaryPart 的形状子问题 |

曲面约束在曲面更新与重初始化时按登记顺序执行。局部曲面约束保存在曲面内，Part 级 `apply_surface_constraints()` 提供跨曲面扩展位置。

`ShapeDerivative` 将主目标结构梯度传入局部问题；`Fairness`、`Distance`、圆柱/半径边界及体积辅助项在形状子问题中求值。`Fairness` 使用曲面预计算的一、二阶几何量与阈值；这些阈值不等同于控制点位移上限。

曲面 `seed_size` 控制初始控制网格和采样，Part 的 `fea_seed_size` 控制体网格。更改体网格尺寸不自动改变设计控制点数量。

<a id="simp"></a>

## 6 SIMP 材料设计

`SIMP_BSPFieldMaterials` 继承 `BaseMaterial` 与可更新协议。设计变量是 B 样条标量场控制点，有限元响应通过空间映射获得材料参数与正则化贡献。

```text
控制点 → B 样条设计场 f → sigmoid(f) 得到 ρ
       → RAMP(ρ) 与比例下限 → 材料刚度缩放
       → 正则化单元与本构 → 有限元响应
```

`SIMPScaledMaterial` 缩放基准本构的能量、应力与切线。`SIMPElementFgrad`、`SIMPElementFskew`、`SIMPElementHuHu_LuLu` 表达不同正则化实现，具体体单元通过相应组合类接入。

`initial_ratio` 是初始设计场控制值，不直接等于体积分数。`VolFrac` 对高斯点的 `ρ` 进行体积加权；`MinValue/MaxValue` 约束控制变量。`Sensitivity` 传递材料梯度，`DensityFieldMinimize` 为辅助正则化项。

`UpdaterSIMPMaterial` 绑定一个材料接口，通过其控制点构造局部问题。材料的空间投影与导数由材料接口负责；更新器不复制 B 样条映射实现。

<a id="section-偏置层与协同设计"></a>

## 7 偏置层与协同设计

`OffsetBoundaryPart` 在内腔曲面沿法向构造实体偏置层，属于同一 Part，并复用同一边界设计变量。构建过程检查偏置层网格，厚度、局部曲率与曲面间距应相容。

`UpdaterOffsetBoundaryPart` 复用形状更新流程并限定目标类型。`InwardCurvatureRadius` 与 `OffsetSurfaceMinThickness` 分别控制内凹曲率和偏置后的间距。该能力已在 UI 的 Part、更新器选择及预览中接入。

协同任务仍使用公共参数集合、FEAParams、求解器与更新器管理器。主体与偏置层按实际单元块分配材料，SIMP 材料使用公共 `UpdaterSIMPMaterial`；不建立另一套控制器或专用 FEAParams。

理论与算法推导见[形状优化理论](../theory/morphdesign.md)及[协同优化理论](../theory/codesign.md)，具体配置示例见[脚本更新器参考](../scriptreference.md#section-updater-定义)。
