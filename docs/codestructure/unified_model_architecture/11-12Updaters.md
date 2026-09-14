# MorphOpt V4 Updater 与联合更新

本文件定义按可更新实体组织的 updater、`UpdaterEntry` 和联合更新流程。每个可更新实体
对应一个 updater 实例；`BoundaryPart` 与 `OffsetShellPart` 使用不同的几何 updater
实现，同时通过公共生命周期参与联合更新。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文定义 updater 如何绑定一个且仅一个可更新 owner、接收顶层目标灵敏度并建立固定的局部
线性目标、在各自的 updater 内定义和执行约束、调用优化算法并提交变化，以及
BoundaryPart、OffsetShellPart、Material 和 FEA 多类 updater 如何在同一问题中联合更新。
每个 updater 的约束函数、等式投影和约束参数都记录在该 updater 内部，由其生命周期统一维护。

### 目录

- [11. Updater 类定义](#11-updater-类定义)
- [11.1 BaseUpdater](#111-baseupdater)
- [11.2 BaseGeometryUpdater](#112-basegeometryupdater)
- [11.3 BoundaryPartUpdater](#113-boundarypartupdater)
- [11.4 OffsetShellPartUpdater](#114-offsetshellpartupdater)
- [11.5 MaterialUpdater](#115-materialupdater)
- [11.6 FEAUpdater](#116-feaupdater)
- [11.7 UpdaterEntry](#117-updaterentry)
- [11.8 Updaters](#118-updaters)
- [12. Updater 联合更新协议](#12-updater-联合更新协议)
  - [12.1 Updater 局部目标协议](#121-updater-局部目标协议)
    - [`LocalSensitivityObjective`](#1211-localsensitivityobjective)
  - [12.2 Geometry、Material 和 Load 的联合更新](#122-geometrymaterial-和-load-的联合更新)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 可更新 owner、目标变量、顶层目标灵敏度、updater 自身约束、优化器配置和设计向量 |
| 输出 | 固定局部线性目标、各 updater 约束结果、设计变化、统一提交结果和联合更新日志 |
| 主要读者 | Geometry/Material/FEA updater 实现者、DesignRegistry、Controller 和 UI 编辑器实现者 |
| 关联文档 | [设计变量注册](10DesignRegistry.md)、[目标函数](09Objective.md)、[运行时](13-14Runtime.md) |

## 11. `Updater` 类定义

### 11.1 `BaseUpdater`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_owner` | `Updatable` 或 None | None | 初始化后注入的具体可更新 owner 对象；定义阶段的目标名称只用于注册和持久化 |
| `_variable_key` | `DesignKey` 或 None | None | 绑定的变量块 |
| `_optimizer_name` | str | "" | 优化器类型名称 |
| `_optimizer_options` | dict[str, object] | {} | 优化器构造参数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_optimizer` | `BaseOptimizer` 或 None | None | 初始化后创建的优化算法状态 |
| `_gradient` | torch.Tensor 或 None | None | 当前局部梯度 |
| `_local_objective` | `LocalSensitivityObjective` 或 None | None | 根据当前局部灵敏度建立的线性目标 |
| `_last_change` | torch.Tensor 或 None | None | 最近变化 |
| `_initialized` | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `optimizer_name` | str | 只读 | 内部维护 | 返回优化器名称 |
| 空 | - | - | - | 局部线性目标和约束通过显式方法读取 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `update_binding(key, owner)` | None | - | 注入已解析的 owner 对象并绑定变量块；后续更新直接使用该对象引用 |
| `get_owner()` | `Updatable` 或 None | - | 读取当前绑定的变量拥有者 |
| `get_variable_key()` | `DesignKey` 或 None | - | 读取当前变量块标识 |
| `get_gradient()` | torch.Tensor 或 None | - | 读取最近梯度 detached clone |
| `get_last_change()` | torch.Tensor 或 None | - | 读取最近变化 detached clone |
| `closure(values, return_list)` | torch.Tensor 或 list[torch.Tensor] | - | 组合固定局部线性目标、具体 updater 的局部约束和材料正则项 |
| `update()` | None | - | 计算并保存变量变化到运行时状态 |
| `get_change()` | torch.Tensor | - | 读取最近一次保存的变量变化 |
| `initialize()` | None | `Initializable` | 初始化优化器；具体 updater 同时准备自己的局部项 |
| `reinitialize(iteration, gradient)` | None | `Initializable` | 接收顶层目标分发的局部梯度并重建局部线性目标 |
| `get_local_objective()` | `LocalSensitivityObjective` 或 None | - | 读取当前 updater 的固定局部线性目标 |
| `save(foldpath, iteration)` | None | `Persistable` | 保存优化器和局部 updater 状态 |
| `load(foldpath, iteration)` | None | `Persistable` | 加载指定 iteration 的 updater 状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_local_objective(gradient)` | None | 根据当前局部灵敏度建立或刷新 `_local_objective` |

`BaseUpdater` 只处理一块变量、维护优化器状态并定义统一生命周期。它接收顶层
`ObjectiveFunction` 分发的局部梯度，在 `reinitialize()` 中建立唯一的
`LocalSensitivityObjective`；局部目标由该生命周期自动建立。具体 updater 只声明自己的
`_constraints`（材料 updater 还维护 `_regularization_terms`），并实现对应项的添加、读取和计算接口。局部线性目标和约束只读取绑定 `owner`
的数据；变化的正式提交由 `Updaters.update()` 统一完成。

实体到 updater 的关系固定为一对一：`BoundaryPart` 使用 `BoundaryPartUpdater`，
`OffsetShellPart` 使用 `OffsetShellPartUpdater`，可更新材料接口使用 `MaterialUpdater`，
可更新 FEA component 使用 `FEAUpdater`。`BaseGeometryUpdater` 承载几何共有能力，
实体注册使用对应的具体 updater；几何更新的差异留在对应的具体 updater 中，而联合调度
只依赖 `BaseUpdater` 生命周期。

```text
BaseUpdater[OwnerT]
├── BaseGeometryUpdater[GeometryOwnerT]
│   ├── BoundaryPartUpdater[BoundaryPart]
│   └── OffsetShellPartUpdater[OffsetShellPart]
├── MaterialUpdater[MaterialOwnerT]
└── FEAUpdater[FEAComponentT]
```

### 11.2 `BaseGeometryUpdater`

`BaseGeometryUpdater` 是几何 updater 的共享基类。它保存固定局部灵敏度目标和几何优化
生命周期；等式投影和不等式/罚函数约束由 `BoundaryPartUpdater` 或
`OffsetShellPartUpdater` 各自声明和执行。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| 空 | - | 等式投影由具体几何 updater 自己保存 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 运行时状态沿用 `BaseUpdater`，本类不新增字段 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| 空 | - | - | - | - | 局部约束 property 由具体几何 updater 定义；局部目标通过 `get_local_objective()` 读取 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 几何生命周期沿用 `BaseUpdater` |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部约束函数 |

几何约束的完整清单和数据契约分别定义在 `BoundaryPartUpdater` 与
`OffsetShellPartUpdater` 的“局部项”表中。两个 updater 都在试探设计值建立后执行自己的
唯一等式投影，再按表中顺序计算局部罚函数；约束回调、阈值、权重、启用掩码和初始化缓存
均由对应 updater 独立保存。

### 11.3 `BoundaryPartUpdater`

`BoundaryPartUpdater` 专门更新一个 `BoundaryPart`，并在初始化后直接持有该对象的引用。
一个 `BoundaryPart` 只能绑定一个 `BoundaryPartUpdater`，一个问题可以为不同的
`BoundaryPart` 注册多个同类 updater。`_owner` 在本类中固定为 `BoundaryPart` 类型，
局部目标、等式约束、不等式约束和几何设计变量都从该引用读取或写回。
曲面控制点、曲面等式约束、Fairness 和边界 Part 的几何更新逻辑均在该 updater 的
owner 范围内完成。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_max_step_length` | float | - | 边界 Part 的最大更新步长 |
| `_line_search_options` | dict[str, object] | {} | 边界 Part 的线搜索配置 |
| `_surface_update_mask` | tuple[bool, ...] 或 None | None | 按曲面控制是否参与本次更新 |
| `_equality_constraint` | Callable 或 None | None | 当前 BoundaryPart 的唯一等式投影回调 |
| `_constraints` | dict[str, Callable] | {} | 当前 BoundaryPart 自己定义的局部约束回调及参数 |

本类约束回调的统一形态为：局部不等式/罚函数回调接收当前设计值并返回 `torch.Tensor`；
唯一等式投影回调接收绑定的 `BoundaryPart` 当前状态并原地完成投影，返回 `None`。

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_surface_gradient` | tuple[torch.Tensor, ...] 或 None | None | 当前各曲面的几何梯度 |
| `_surface_change` | tuple[torch.Tensor, ...] 或 None | None | 最近一次各曲面的更新量 |
| `_step_length_by_surface` | tuple[torch.Tensor, ...] 或 None | None | 各曲面的自适应步长 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `constraints` | Mapping[str, Callable] | `BoundaryPartUpdater` | 只读 | 内部维护 | 当前 BoundaryPart 自己定义的局部约束回调 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_equality_constraint(constraint)` | None | `BoundaryPartUpdater` | 设置或清除 BoundaryPart 的唯一等式投影回调 |
| `get_equality_constraint()` | Callable 或 None | `BoundaryPartUpdater` | 读取当前等式投影回调 |
| `add_constraint(name, constraint)` | None | `BoundaryPartUpdater` | 注册本 updater 的一个局部约束回调 |
| `get_constraints()` | Mapping[str, Callable] | `BoundaryPartUpdater` | 读取本 updater 的局部约束回调 |
| `closure(values, return_list)` | Tensor 或 list[Tensor] | `BaseUpdater` | 重写固定局部线性目标和约束计算，将值映射为边界曲面变量 |
| `initialize()` | None | `BaseUpdater` | 重写初始化，准备边界曲面优化状态 |
| `reinitialize(iteration, gradient)` | None | `BaseUpdater` | 重写梯度刷新，接收边界曲面梯度 |
| `update()` | None | `BaseUpdater` | 重写更新，将变化映射到边界 Part |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_update_surface_values()` | None | 根据试探设计增量更新各曲面几何值 |
| `_update_step_lengths()` | None | 根据相邻迭代的曲面变化调整步长 |
| `_apply_equality_constraint()` | None | 执行本 updater 保存的唯一等式投影回调 |
| `_evaluate_constraints(values)` | list[Tensor] | 计算本 updater 注册的局部约束 |
| `_commit_surface_changes()` | None | 将边界 Part 的曲面变化提交到 owner |

BoundaryPart 的局部项固定由本 updater 持有：

| 局部项 | 类别 | 输入 | 作用与运行时状态 |
|---|---|---|---|
| 固定局部目标 | 局部线性目标 | 顶层 `ObjectiveFunction` 分发的 BoundaryPart 局部灵敏度和当前设计变量 | 建立 `LocalSensitivityObjective` |
| `equality_projection` | 唯一等式投影 | 当前试探控制点、曲面顺序和用户参数 | 执行用户提供的等式/镜像投影；回调原地写回 owner，返回 `None`；代码和参数由 `_equality_constraint` 保存 |
| `Fairness` | 几何罚函数 | 各曲面的 `r`、`rdu`、`rdu2`、曲面 Fairness evaluator 和点权重 | 组合各曲面 Fairness 值；`max_r`、`max_c`、`max_ff` 等公式参数和曲率补偿缓存由曲面 evaluator 保存，权重和启用曲面由本 updater 保存 |
| `Distance` | 几何罚函数 | 曲面点、曲面一阶导数、`min_distance: list[list[float]]` 矩阵和点权重 | 惩罚过近且法向相向的曲面点对；初始化阶段缓存邻接点对和对应最小距离 |
| `MinRadius` | 几何罚函数 | 曲面点、`radius` 和曲面启用掩码 | 惩罚小于指定最小半径的点 |
| `Cylinder` | 几何罚函数 | 曲面点、`radius`、`height`、`bottom` 和曲面启用掩码 | 惩罚超出圆柱半径、顶部或底部边界的点 |
| `VolumeMaximization` | 几何罚函数 | 指定 CPGEO 曲面 `surf_idx`、曲面三角面、曲面点和 `weight` | 返回负的封闭体积，使优化方向最大化体积 |

所有局部约束回调都注册到该 updater 的 `_constraints`，通过 `_evaluate_constraints(values)`
按注册顺序求值并参与 `closure()`；唯一等式投影在试探值建立后、罚函数计算前由
`_apply_equality_constraint()` 执行。约束的阈值、权重、启用曲面和初始化缓存均由本 updater
及其回调状态保存。

### 11.4 `OffsetShellPartUpdater`

`OffsetShellPartUpdater` 专门更新一个 `OffsetShellPart`。一个 `OffsetShellPart` 绑定一个
`OffsetShellPartUpdater`。该 updater 以源边界曲面的元曲面控制点作为唯一设计变量，并
根据固定偏置算法刷新向内偏置曲面、实体/壳单元和偏置节点；偏置规则由 `OffsetShellPart`
持有，更新策略由本类执行。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_max_step_length` | float | - | 偏置壳 Part 的最大更新步长 |
| `_offset_options` | dict[str, object] | {} | 厚度、层数和偏置更新配置 |
| `_equality_constraint` | Callable 或 None | None | 当前 OffsetShellPart 的唯一等式投影回调 |
| `_constraints` | dict[str, Callable] | {} | 当前 OffsetShellPart 自己定义的局部约束回调及参数 |

局部约束回调接收偏置壳当前试探值并返回 `torch.Tensor`；唯一等式投影回调接收绑定的
`OffsetShellPart` 当前状态并原地完成投影，返回 `None`。

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_boundary_gradient` | torch.Tensor 或 None | None | 源边界曲面元曲面控制点的局部梯度 |
| `_offset_change` | torch.Tensor 或 None | None | 根据控制点变化派生的偏置状态更新量 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `constraints` | Mapping[str, Callable] | `OffsetShellPartUpdater` | 只读 | 内部维护 | 当前 OffsetShellPart 自己定义的局部约束回调 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_equality_constraint(constraint)` | None | `OffsetShellPartUpdater` | 设置或清除 OffsetShellPart 的唯一等式投影回调 |
| `get_equality_constraint()` | Callable 或 None | `OffsetShellPartUpdater` | 读取当前等式投影回调 |
| `add_constraint(name, constraint)` | None | `OffsetShellPartUpdater` | 注册本 updater 的一个局部约束回调 |
| `get_constraints()` | Mapping[str, Callable] | `OffsetShellPartUpdater` | 读取本 updater 的局部约束回调 |
| `closure(values, return_list)` | Tensor 或 list[Tensor] | `BaseUpdater` | 重写固定局部线性目标和约束计算，将值映射为偏置变量 |
| `initialize()` | None | `BaseUpdater` | 重写初始化，准备偏置壳优化状态 |
| `reinitialize(iteration, gradient)` | None | `BaseUpdater` | 重写梯度刷新，接收偏置壳梯度 |
| `update()` | None | `BaseUpdater` | 重写更新，将变化映射到偏置壳 Part |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_update_offset_nodes()` | None | 根据源曲面变化更新偏置节点和相关单元数据 |
| `_apply_equality_constraint()` | None | 执行本 updater 保存的唯一等式投影回调 |
| `_evaluate_constraints(values)` | list[Tensor] | 计算本 updater 注册的局部约束 |
| `_commit_offset_changes()` | None | 将偏置壳的变化提交到 owner |

OffsetShellPart 的局部项固定由本 updater 持有：

| 局部项 | 类别 | 输入 | 作用与运行时状态 |
|---|---|---|---|
| 固定局部目标 | 局部线性目标 | 顶层 `ObjectiveFunction` 分发的源边界局部灵敏度和当前设计变量 | 建立 `LocalSensitivityObjective`；偏置曲面不注册独立设计变量 |
| `equality_projection` | 唯一等式投影 | 源边界控制点、偏置规则和用户参数 | 在源曲面控制点上执行用户投影；回调原地写回 owner，返回 `None`；代码和参数由本 updater 保存 |
| `Fairness` | 几何罚函数 | 源曲面的 `r`、`rdu`、`rdu2`、曲面 evaluator 和点权重 | 与 BoundaryPartUpdater 使用同一 Fairness 计算，约束源曲面曲率平滑性；`max_r`、`max_c`、`max_ff` 等公式参数和曲率补偿由曲面 evaluator 保存 |
| `InwardCurvatureRadius` | 偏置安全罚函数 | 源曲面导数、偏置厚度、选定曲面、`surface_start`/`surface_ids`、`margin`、`margin_ratio`、`barrier_thre_ratio`、`barrier_ratio`、`p`、`penalty_scale`、`hard_violation_beta` 和 `normal_sign` | 使用源曲面的主曲率计算偏置后的朝内曲率半径，降低偏置曲面自相交风险；曲面选择、厚度和 barrier 参数由本 updater 保存 |
| `OffsetSurfaceMinThickness` | 偏置距离罚函数 | 源曲面点、源曲面法向、偏置厚度、`min_distance`、`surface_start`/`surface_ids`、`search_ratio`、`barrier_thre_ratio`、`barrier_ratio`、`p`、`penalty_scale`、`hard_violation_beta`、`normal_sign` 和法向筛选阈值 | 先生成偏置点，再惩罚偏置曲面相向点对之间的距离不足；初始化阶段缓存邻接点对和最小距离 |
| `Distance` | 几何距离罚函数 | 源曲面点、法向、最小距离矩阵和点权重 | 约束源曲面点对之间的最小距离；偏置距离由 `OffsetSurfaceMinThickness` 专门处理 |
| `MinRadius` | 几何半径罚函数 | 源曲面点、半径阈值和曲面启用掩码 | 约束源曲面的最小半径 |
| `Cylinder` | 几何边界罚函数 | 源曲面点、圆柱半径和高度边界 | 约束源曲面处于指定圆柱范围 |
| `VolumeMaximization` | 几何体积罚函数 | 源 CPGEO 曲面三角面、曲面点和权重 | 返回负的源曲面封闭体积，使优化方向最大化体积 |

所有局部约束回调注册到该 updater 的 `_constraints`，并按约束类型读取源曲面或派生偏置几何状态作为求值上下文。
`_apply_equality_constraint()` 在源控制点试探更新后执行；随后 `OffsetShellPart` 按固定偏置
算法刷新偏置节点、曲面和单元，最后由 `_evaluate_constraints(values)` 计算偏置约束。

### 11.5 `MaterialUpdater`

`MaterialUpdater` 通过 `BaseUpdater._owner` 绑定一个可更新材料接口，材料引用由基类统一
保存；材料局部约束由本 updater 自己定义和保存，局部目标固定为顶层灵敏度对应的线性展开；
材料对象只提供参数、设计变量和 Assembly 更新能力。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_constraints` | dict[str, Callable] | 当前 MaterialUpdater 自己定义的局部约束回调及参数 |
| `_regularization_terms` | dict[str, Callable] | 材料场附加正则项回调及参数 |

材料约束回调接收当前材料设计值和材料场状态，返回用于优化器的 `torch.Tensor`。

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 运行时状态沿用 `BaseUpdater`，本类不新增字段 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `constraints` | Mapping[str, Callable] | `MaterialUpdater` | 只读 | 内部维护 | 当前 MaterialUpdater 自己定义的局部约束回调 |
| `regularization_terms` | Mapping[str, Callable] | `MaterialUpdater` | 只读 | 内部维护 | 当前材料场附加正则项回调 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_constraint(name, constraint)` | None | `MaterialUpdater` | 注册本 updater 的一个材料约束回调 |
| `get_constraints()` | Mapping[str, Callable] | `MaterialUpdater` | 读取本 updater 的约束回调 |
| `add_regularization(name, term)` | None | `MaterialUpdater` | 注册一个材料场附加正则项回调 |
| `get_regularization_terms()` | Mapping[str, Callable] | `MaterialUpdater` | 读取材料场附加正则项回调 |
| `closure(values, return_list)` | Tensor 或 list[Tensor] | `BaseUpdater` | 重写固定局部线性目标、约束和正则项计算，将值映射为材料变量 |
| `update()` | None | `BaseUpdater` | 重写更新，将变化映射到材料接口 |
| `initialize()` | None | `BaseUpdater` | 重写初始化，准备材料优化状态 |
| `reinitialize(iteration, gradient)` | None | `BaseUpdater` | 重写梯度刷新，接收材料梯度 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_evaluate_constraints(values)` | list[Tensor] | 计算本 updater 注册的局部约束 |
| `_evaluate_regularization(values)` | list[Tensor] | 计算本 updater 注册的附加正则项 |

`MaterialUpdater` 的局部目标固定为顶层 `ObjectiveFunction` 灵敏度对材料设计变量的线性展开；
v3 中的 `Sensitivity` 承担该局部线性目标。材料 updater 的约束清单如下：

| 约束 | 类别 | 输入 | 作用与运行时状态 |
|---|---|---|---|
| `MinValue` | 材料值罚函数 | 材料控制点、`xmin`、`threshold`、barrier 阶数和缩放参数 | 惩罚控制点低于下限的部分；阈值、barrier 参数和控制点权重由本 updater 保存 |
| `MaxValue` | 材料值罚函数 | 材料控制点、`xmax`、`threshold`、barrier 阶数和缩放参数 | 惩罚控制点高于上限的部分；阈值、barrier 参数和控制点权重由本 updater 保存 |
| `VolFrac` | 材料场罚函数 | `SIMPFieldMaterial`、目标 `element_name`、高斯点、积分权重、最小/最大体积分数和 penalty | 将材料控制点映射到高斯点，计算体积分数并惩罚超出区间的情况；高斯映射和积分数据在初始化阶段缓存 |

`DensityFieldMinimize` 在 v3 中属于材料 updater 的附加正则目标，作用是抑制设计域外的
密度场；V4 将其作为 MaterialUpdater 的 `regularization_terms` 保存和计算，和上述约束
共同进入 updater 的 `closure()`，但不改变约束清单的含义。均匀材料没有可更新设计变量，
因此只参加材料赋值，不注册上述材料 updater 约束。

### 11.6 `FEAUpdater`

`FEAUpdater` 通过 `BaseUpdater._owner` 绑定一个可更新 FEA component，组件引用由基类统一
保存；载荷局部约束由本 updater 自己定义和保存，局部目标固定为顶层灵敏度对 FEA component
变量的线性展开；FEA component 只提供载荷参数、参考点、Jacobian 和求解结果。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_constraints` | dict[str, Callable] | 当前 FEAUpdater 自己定义的局部约束回调及参数 |

FEA 约束回调接收绑定 component 的当前参数、Jacobian 或 `StaticResult`，返回用于优化器的
`torch.Tensor`。

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 运行时状态沿用 `BaseUpdater`，本类不新增字段 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `constraints` | Mapping[str, Callable] | `FEAUpdater` | 只读 | 内部维护 | 当前 FEAUpdater 自己定义的局部约束回调 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_constraint(name, constraint)` | None | `FEAUpdater` | 注册本 updater 的一个载荷约束回调 |
| `get_constraints()` | Mapping[str, Callable] | `FEAUpdater` | 读取本 updater 的约束回调 |
| `closure(values, return_list)` | torch.Tensor 或 list[torch.Tensor] | `BaseUpdater` | 重写固定局部线性目标和约束计算，将值映射为 FEA 变量 |
| `update()` | None | `BaseUpdater` | 重写更新，将变化映射到 FEA component |
| `initialize()` | None | `BaseUpdater` | 重写初始化，准备 FEA component 优化状态 |
| `reinitialize(iteration, gradient)` | None | `BaseUpdater` | 重写梯度刷新，接收 FEA component 梯度 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_evaluate_constraints(values)` | list[Tensor] | 计算本 updater 注册的局部约束 |

`FEAUpdater` 的固定局部线性目标接收顶层灵敏度分发的 FEA component 变量梯度；局部约束
由本 updater 自己定义并接收当前工况的 component 参数、Jacobian、`StaticResult` 或用户代码
结果。这些项目只对绑定的 FEA component 生效，并保持在本 updater 的局部计算范围内。

当前 V4 内置 `FEAUpdater` 的约束清单为空。`BoundaryCondition`、`BoundaryConditionRP`、
集中力、集中力矩、接触等属于 [FEA component](07Fea.md) 的物理定义，由 `FEAParams` 写入
`Assembly`；它们不是优化 updater 的局部罚函数。需要对可更新 FEA component 增加优化约束时，
由具体 `FEAUpdater` 子类在自己的 `_constraints` 中声明名称、输入、阈值和求值回调。

### 11.7 `UpdaterEntry`

`UpdaterEntry` 是一个统一的 updater 注册项，目标类别覆盖几何、材料、FEA 以及用户扩展类别。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_name` | str | updater 名称 |
| `_target_kind` | str | 目标类别，例如 `boundary_part`、`offset_shell_part`、`material`、`load` 或用户扩展类别 |
| `_target_name` | str | 目标对象的稳定名称；几何目标使用 `part_name` |
| `_updater` | `BaseUpdater` | 更新策略对象，可以是对应实体类型的内置 updater 或用户自定义子类 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

目标 owner 和变量块由其中的 updater 在 `Updaters.initialize()`
中绑定；updater 自身的运行时属性见 `BaseUpdater`。

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_owner`、`_variable_key` | 由 `BaseUpdater` 绑定 | None | 初始化阶段由内部 updater 写入唯一目标 owner 和变量块 |
| `_initialized` | bool | False | 注册项绑定状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 内部维护 | 返回 updater 名称 |
| `target_kind` | str | 只读 | 内部维护 | 返回目标类别 |
| `target_name` | str | 只读 | 内部维护 | 返回目标名称 |
| `updater` | `BaseUpdater` | 只读 | 内部维护 | 返回与目标类型匹配的更新策略对象 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 注册项通过所属 `Updaters` 统一调度 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

### 11.8 `Updaters`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_entries` | dict[str, `UpdaterEntry`] | {} | 所有 updater 的注册项；每个可更新实体只出现一次 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_initialized` | bool | False | 绑定状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `entries` | Mapping[str, `UpdaterEntry`] | 只读 | 内部维护 | 返回 updater 注册项只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `define_updaters()` | None | - | 用户注册任意数量和类型的 updater |
| `add_updater(target_kind, target_name, updater, name)` | None | - | 注册一个 updater，并校验目标类型、目标名称和唯一绑定关系 |
| `update()` | None | - | 计算并保存所有局部变化，再一次性提交 |
| `get_changes()` | Mapping[`DesignKey`, torch.Tensor] | - | 读取最近一次保存的全部变化 |
| `initialize(params, registry)` | None | `Initializable` | 解析目标、绑定 `owner`、注册变量 |
| `reinitialize(iteration, gradients)` | None | `Initializable` | 分发局部梯度 |
| `save(foldpath, iteration)` | None | `Persistable` | 保存全部 updater 状态 |
| `load(foldpath, iteration)` | None | `Persistable` | 加载指定 iteration 的全部 updater 状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

`Updaters` 是可变长度的 updater 集合。一个问题可以为不同的 `BoundaryPart` 注册多个
`BoundaryPartUpdater`，为不同的 `OffsetShellPart` 注册多个 `OffsetShellPartUpdater`，
也可以混合注册材料、载荷和用户自定义 updater。每个 `UpdaterEntry` 都保存明确的目标
类别和目标名称；`(target_kind, target_name)` 是唯一 owner 键，每个实体对应一个 updater，
每个 updater 绑定一个实体。

内置目标类型与 updater 类型的绑定关系如下：

| `target_kind` | owner 类型 | updater 类型 |
|---|---|---|
| `boundary_part` | `BoundaryPart` | `BoundaryPartUpdater` |
| `offset_shell_part` | `OffsetShellPart` | `OffsetShellPartUpdater` |
| `material` | 可更新材料接口 | `MaterialUpdater` 或其材料专用子类 |
| `load` | 可更新 FEA component | `FEAUpdater` 或其载荷专用子类 |

`add_updater()` 在注册阶段维护 owner 键唯一，并在初始化阶段解析目标名称、取得对应的
`BoundaryPart`、`OffsetShellPart`、材料接口或 FEA component 对象，再注入 updater 的
`_owner`。初始化后 updater 直接使用该对象引用；目标名称保留在 `UpdaterEntry` 中，用于
校验、序列化和 UI 显示。相同 updater 类可以绑定多个不同 owner；一个 owner 对应
一个 updater。

`Updaters.update()` 按注册项逐个调用 updater 的 `update()`，分别计算并保存方向和步长形成的
局部变化；随后将所有变化按 `DesignKey` 汇总，并调用
`DesignRegistry.update_owners(changes)` 一次性写回所有 `owner`。几何、材料、载荷和
其他已注册 updater 在同一个外层迭代中完成同步更新。更新结果通过 `get_changes()`
读取，供日志和历史记录使用。未绑定 updater 的对象保持当前状态并继续参加 FEA。

## 12. Updater 联合更新协议

### 12.1 Updater 局部目标协议

`LocalSensitivityObjective` 是所有 updater 共用的固定局部目标。顶层
`ObjectiveFunction` 完成全局目标计算和灵敏度分析，`Controller` 按 `DesignKey` 将梯度
切分后传给对应 updater；updater 根据本地梯度建立自己的局部线性展开。局部目标由该流程
自动建立；每个 updater 的等式投影、局部约束和约束参数都在对应 updater 内部定义。

约束全部归属于具体 updater。`BoundaryPartUpdater`、`OffsetShellPartUpdater`、
`MaterialUpdater` 和 `FEAUpdater` 各自定义 `_constraints` 回调表、约束参数和
`_evaluate_constraints()`；几何 updater 另外保存一个唯一的 `_equality_constraint` 回调。
`Updaters` 按注册项调度 updater，各 updater 只评估和提交自己保存的约束。

Fairness evaluator 的接口和具体实现归入几何章节；本章只规定几何 updater 调用 evaluator
并把结果组合为自身局部约束的生命周期位置。

`LocalSensitivityObjective` 绑定 updater 的 owner 和局部变量块。各 updater 的约束回调
直接绑定同一 owner、参数和运行时上下文；局部灵敏度目标、等式投影和局部约束都在对应
updater 的生命周期中建立、评估和提交。

所有 updater 的局部约束遵循同一调用顺序，但约束名称、参数和缓存只属于具体 updater：

| 阶段 | updater 行为 | 约束状态 |
|---|---|---|
| 注册 | `add_constraint(name, constraint)` 写入本 updater 的 `_constraints` | 保存名称、回调和约束参数 |
| 初始化 | `initialize()` 用 owner、基准几何/材料/FEA 数据调用约束初始化逻辑 | 建立点权重、启用掩码、邻接点对、积分映射等缓存 |
| 试探求值 | `closure(values)` 先建立试探设计，再调用 `_evaluate_constraints(values)` | 返回每个约束的标量 `torch.Tensor`，参与本 updater 优化器 |
| 正式更新 | `update()` 在优化器确认变化后执行等式投影、owner 更新和约束状态刷新 | 约束缓存与 owner 的新状态保持一致 |
| 查询 | `get_constraints()` 返回本 updater 的只读约束映射 | 读取名称和回调配置，不触发重新求值 |

### 12.1.1 `LocalSensitivityObjective`

`LocalSensitivityObjective` 是每个 updater 唯一的局部目标。它接收顶层
`ObjectiveFunction` 对当前 owner 设计变量的灵敏度，并在当前设计点建立局部线性展开：

```text
L_local(Δx) = L_local(x₀) + gradient_local · Δx
```

不同 owner 只负责提供不同形状的设计变量和更新接口；局部目标的数学职责保持一致。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| 空 | - | 局部线性目标不接收用户定义参数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_owner` | `Updatable` 或 None | None | 初始化后绑定的 updater owner |
| `_context` | object 或 None | None | 当前 owner 的运行上下文 |
| `_gradient` | torch.Tensor 或 None | None | 当前 owner 的局部灵敏度 |
| `_reference_values` | torch.Tensor 或 tuple[torch.Tensor, ...] 或 None | None | 建立线性展开时的设计变量快照 |
| `_scale` | torch.Tensor 或 float 或 None | None | 灵敏度归一化或步长缩放因子 |
| `_initialized` | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `gradient` | torch.Tensor | 只读 | 内部维护 | 返回当前局部灵敏度 |
| `scale` | torch.Tensor 或 float | 只读 | 内部维护 | 返回当前灵敏度缩放因子 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `evaluate(values)` | torch.Tensor | - | 计算局部线性目标值 |
| `initialize(owner, gradient)` | None | `Initializable` | 绑定 owner 并建立当前灵敏度展开 |
| `reinitialize(iteration, gradient)` | None | `Initializable` | 接收新的局部灵敏度并刷新展开 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_flatten_design_values(values)` | torch.Tensor | 统一 owner 设计变量形状 |

### 12.2 Geometry、Material 和 Load 的联合更新

一个问题可以使用以下模式：

| 注册项 | 运行模式 |
|---|---|
| updater 注册项为零 | 固定模型 FEA |
| `BoundaryPartUpdater` × N | 多个边界 Part 的联合优化 |
| `OffsetShellPartUpdater` × N | 多个偏置壳 Part 的联合优化 |
| `MaterialUpdater` × N | 多个材料目标的联合优化 |
| `FEAUpdater` × N | 多个载荷或边界目标的联合优化 |
| 任意组合 | 几何、材料、载荷和其他目标的联合优化 |

联合优化的单次更新顺序：

1. 生成当前 `Assembly`；
2. 赋予全部材料；
3. `FEAParams.assign_components()` 将 FEA component 写入当前 `Assembly`；
4. `Controller` 将 Params 的 `Assembly` 交给 Solver 求解全部 load steps；
5. 计算物理目标；
6. 计算一次完整灵敏度；
7. `DesignRegistry` 按变量块切分梯度并分发给各 updater；
8. 各 updater 用局部梯度建立固定的 `LocalSensitivityObjective`，再计算局部变化；
9. 所有 updater 成功后统一提交；
10. 记录当前 iteration 结果并进入下一 iteration。

任意 updater 失败时，当前 iteration 记录错误并停止提交。
