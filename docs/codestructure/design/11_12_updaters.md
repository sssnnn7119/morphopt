# MorphOpt V4 Updater 与联合更新

Updater 属于优化核心，代码位于 `src/morphopt/optcore/updaters/`，与 Controller、Solver、
Objective 和 DesignRegistry 共同组成运行时优化内核；UI 只通过公开 updater 接口读取和配置。

本文件定义按可更新实体组织的 updater、`UpdaterEntry` 和联合更新流程。每个可更新实体
对应一个 updater 实例；`BoundaryPart` 与 `OffsetShellPart` 使用不同的几何 updater
实现，同时通过公共生命周期参与联合更新。返回[总入口](../design.md)。

## 文档导航与输入/输出摘要

本文定义 updater 如何绑定一个且仅一个可更新 owner、接收顶层目标灵敏度并建立固定的局部
线性目标、在各自的 updater 内定义和执行约束、调用优化算法并提交变化，以及
BoundaryPart、OffsetShellPart、Material 和 FEA 多类 updater 如何在同一问题中联合更新。
每个 updater 的约束函数、等式投影和约束参数都记录在该 updater 内部，由其生命周期统一维护。

文档中的 `UpdaterContext` 是 `optcore.updaters` 定义的运行上下文数据类，包含当前 owner、
局部灵敏度、参考设计值和设备；`JsonValue` 为跨进程配置允许的标量、列表和字典联合类型。

### 目录

- [11. Updater 类定义](#11-updater-类定义)
- [11.1 优化算法](#111-优化算法)
- [11.2 BaseUpdater](#112-baseupdater)
- [11.3 几何 updater 公共规则](#113-几何-updater-公共规则)
- [11.4 BoundaryPartUpdater](#114-boundarypartupdater)
- [11.5 OffsetShellPartUpdater](#115-offsetshellpartupdater)
- [11.6 MaterialUpdater](#116-materialupdater)
- [11.7 FEAUpdater](#117-feaupdater)
- [11.8 UpdaterEntry](#118-updaterentry)
- [11.9 Updaters](#119-updaters)
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
| 关联文档 | [设计变量注册](10_design_registry.md)、[目标函数](09_objective.md)、[运行时](13_14_runtime.md) |

## 11. `Updater` 类定义

### 11.1 优化算法

#### 11.1.1 `BaseOptimizer`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_maximum_iterations` | int | `20` | 单次 updater 内层迭代上限 |
| `_gradient_tolerance` | float | `1e-7` | 一阶最优性容差 |
| `_change_tolerance` | float | `1e-9` | 连续设计变化容差 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_last_result` | `OptimizerResult` 或 None | None | 最近一次优化摘要 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `maximum_iterations` | int | - | 只读 | 内部维护 | 返回内层迭代上限 |
| `gradient_tolerance` | float | - | 只读 | 内部维护 | 返回梯度容差 |
| `change_tolerance` | float | - | 只读 | 内部维护 | 返回变化容差 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `optimize(initial_values, closure)` | torch.Tensor | - | 运行局部优化并返回最终设计变化 |
| `get_last_result()` | `OptimizerResult` | - | 读取最近一次内层迭代、损失、梯度范数和终止原因 |

##### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_validate_closure_output(value)` | None | 校验标量、有限性和梯度连接 |
| `_build_result(...)` | None | 建立并保存优化摘要 |

#### 11.1.2 `BacktrackingLineSearch`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_initial_step` | float | `1.0` | 初始线搜索步长 |
| `_contraction` | float | `0.5` | 每次回退的步长比例 |
| `_armijo_coefficient` | float | `1e-4` | Armijo 充分下降系数 |
| `_maximum_evaluations` | int | `20` | 单次线搜索 closure 调用上限 |
| `_minimum_step` | float | `1e-8` | 最小可接受步长 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_accepted_step` | float 或 None | None | 最近接受步长 |
| `_evaluation_count` | int | `0` | 最近 closure 调用次数 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `initial_step` | float | - | 只读 | 内部维护 | 返回初始步长 |
| `contraction` | float | - | 只读 | 内部维护 | 返回回退比例 |
| `armijo_coefficient` | float | - | 只读 | 内部维护 | 返回充分下降系数 |
| `maximum_evaluations` | int | - | 只读 | 内部维护 | 返回求值上限 |
| `minimum_step` | float | - | 只读 | 内部维护 | 返回最小步长 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `search(values, direction, loss, gradient, closure)` | tuple[torch.Tensor, torch.Tensor] | - | 回退搜索并返回接受值和损失 |
| `get_accepted_step()` | float | - | 读取最近接受步长 |

##### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_satisfies_armijo(...)` | bool | 检查充分下降条件 |

#### 11.1.3 `LBFGSOptimizer`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_history_size` | int | `10` | L-BFGS 曲率对数量 |
| `_line_search` | `BacktrackingLineSearch` | - | 回退线搜索策略 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_s_history` | deque[torch.Tensor] | 空 | 设计差历史 |
| `_y_history` | deque[torch.Tensor] | 空 | 梯度差历史 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `history_size` | int | - | 只读 | 内部维护 | 返回曲率历史长度 |
| `line_search` | `BacktrackingLineSearch` | - | 只读 | 内部维护 | 返回线搜索策略 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `optimize(initial_values, closure)` | torch.Tensor | `BaseOptimizer` | 使用二循环递推和回退线搜索计算局部设计变化 |

##### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_compute_direction(gradient)` | torch.Tensor | 用 L-BFGS 二循环递推计算下降方向 |
| `_update_history(step, gradient_change)` | None | 接受满足正曲率的历史对并限制队列长度 |

#### 11.1.4 `OptimizerResult`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_iterations` | int | - | 已完成内层迭代数 |
| `_final_loss` | float | - | 最终标量损失 |
| `_gradient_norm` | float | - | 最终梯度范数 |
| `_accepted_step` | float | - | 最后接受步长 |
| `_closure_evaluations` | int | - | closure 总调用次数 |
| `_termination_reason` | str | - | 稳定终止原因标识 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结结果仅保存构造状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `iterations` | int | - | 只读 | 内部维护 | 返回迭代数 |
| `final_loss` | float | - | 只读 | 内部维护 | 返回最终损失 |
| `gradient_norm` | float | - | 只读 | 内部维护 | 返回梯度范数 |
| `accepted_step` | float | - | 只读 | 内部维护 | 返回最后步长 |
| `closure_evaluations` | int | - | 只读 | 内部维护 | 返回求值次数 |
| `termination_reason` | str | - | 只读 | 内部维护 | 返回终止原因 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 结果通过 property 读取 |

##### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结结果由 optimizer 建立 |

默认 optimizer 为 `LBFGSOptimizer`；自定义 optimizer 实现 `BaseOptimizer.optimize()` 和
`get_last_result()`。

### 11.2 `BaseUpdater`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_optimizer_name` | str | "" | 优化器类型名称 |
| `_optimizer_options` | dict[str, JsonValue] | {} | 优化器构造参数 |
| `_maximum_update_steps` | int | `100` | 一次外层迭代允许的局部更新步数 |
| `_maximum_step_length` | float | - | 每个局部变量的步长上限 |
| `_minimum_step_ratio` | float | `0.1` | 自适应步长相对下限 |
| `_step_decay` | float | `0.5` | 相邻变化方向冲突时的缩放比例 |
| `_step_growth` | float | `1.5` | 相邻变化方向一致时的放大比例 |
| `_sensitivity_scale_reset_interval` | int | `1` | 灵敏度缩放重置间隔 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_owner` | `Updatable` 或 None | None | 初始化后解析的唯一 owner |
| `_variable_key` | `DesignKey` 或 None | None | owner 对应的变量块 |
| `_optimizer` | `BaseOptimizer` 或 None | None | 初始化后创建的优化算法状态 |
| `_gradient` | torch.Tensor 或 None | None | 当前局部梯度 |
| `_local_objective` | `LocalSensitivityObjective` 或 None | None | 根据当前局部灵敏度建立的线性目标 |
| `_last_change` | torch.Tensor 或 None | None | 最近变化 |
| `_previous_change` | torch.Tensor 或 None | None | 用于自适应步长的上一轮变化 |
| `_step_limits` | torch.Tensor 或 None | None | 当前逐变量步长上限 |
| `_total_update_iterations` | int | `0` | 累计局部优化迭代次数 |
| `_initialized` | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `optimizer_name` | str | - | 只读 | 内部维护 | 返回优化器名称 |
| `optimizer_options` | Mapping[str, JsonValue] | - | 只读 | 内部维护 | 返回优化器构造参数的只读视图 |
| `maximum_update_steps` | int | - | 只读 | 内部维护 | 返回局部更新步数上限 |
| `maximum_step_length` | float | - | 只读 | 内部维护 | 返回步长上限 |
| `minimum_step_ratio` | float | - | 只读 | 内部维护 | 返回相对步长下限 |
| `step_decay` | float | - | 只读 | 内部维护 | 返回步长衰减比例 |
| `step_growth` | float | - | 只读 | 内部维护 | 返回步长增长比例 |
| `sensitivity_scale_reset_interval` | int | - | 只读 | 内部维护 | 返回灵敏度缩放重置间隔 |
| 空 | - | - | - | - | 局部线性目标和约束通过显式方法读取 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `update_binding(key, owner)` | None | - | 注入已解析的 owner 对象并绑定变量块；后续更新直接使用该对象引用 |
| `get_owner()` | `Updatable` 或 None | - | 读取当前绑定的变量拥有者 |
| `get_variable_key()` | `DesignKey` 或 None | - | 读取当前变量块标识 |
| `get_gradient()` | torch.Tensor 或 None | - | 读取最近梯度 detached clone |
| `get_last_change()` | torch.Tensor 或 None | - | 读取最近变化 detached clone |
| `compute_terms(values)` | tuple[torch.Tensor, ...] | - | 纯计算固定局部目标、具体约束和材料正则项 |
| `closure(values)` | torch.Tensor | - | 汇总 `compute_terms()` 并返回优化器使用的标量损失 |
| `update()` | None | - | 计算并保存变量变化到运行时状态 |
| `get_change()` | torch.Tensor | - | 读取最近一次保存的变量变化 |
| `get_local_objective()` | `LocalSensitivityObjective` 或 None | - | 读取当前 updater 的固定局部线性目标 |
| `initialize()` | None | `Initializable` | 初始化优化器；具体 updater 同时准备自己的局部项 |
| `reinitialize(iteration, gradient)` | None | `Initializable` | 接收顶层目标分发的局部梯度并重建局部线性目标 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存优化器和局部 updater 状态 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载指定 iteration 的 updater 状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_local_objective(gradient)` | None | 根据当前局部灵敏度建立或刷新 `_local_objective` |
| `_validate_change(change)` | None | 校验变化形状、有限性和步长限制 |
| `_update_step_limits(change)` | None | 根据当前与上一轮变化的方向一致性调整逐变量步长；饱和映射与步长向量语义按[冻结数值契约](24_breaking_changes.md)执行 |

`BaseUpdater` 只处理一块变量、维护优化器状态并定义统一生命周期。它接收顶层
`ObjectiveFunction` 分发的局部梯度，在 `reinitialize()` 中建立唯一的
`LocalSensitivityObjective`；局部目标由该生命周期自动建立。局部梯度是顶层灵敏度按变量块
切分后的 detached 张量：updater 的 `closure()` 只在参数空间求值，不建立也不持有任何 FEA
计算图，见[目标函数](09_objective.md)的计算图生命周期。具体 updater 只声明自己的
`_constraints`（材料 updater 还维护 `_regularization_terms`），并实现对应项的添加、读取和计算接口。局部线性目标和约束只读取绑定 `owner`
的数据；变化的正式提交由 `Updaters.update()` 统一完成。

实体到 updater 的关系固定为一对一：`BoundaryPart` 使用 `BoundaryPartUpdater`，
`OffsetShellPart` 使用 `OffsetShellPartUpdater`，可更新材料接口使用 `MaterialUpdater`，
可更新 FEA component 使用 `FEAUpdater`。两个几何 updater 都直接继承 `BaseUpdater`；
几何共有的等式投影与局部罚函数规则在 §11.3 统一说明，具体实现留在各自的具体 updater 中，
而联合调度只依赖 `BaseUpdater` 生命周期。

```text
BaseUpdater[OwnerT]
├── BoundaryPartUpdater[BoundaryPart]
├── OffsetShellPartUpdater[OffsetShellPart]
├── MaterialUpdater[MaterialOwnerT]
└── FEAUpdater[FEAComponentT]
```

### 11.3 几何 updater 公共规则

两个几何 updater 直接继承 `BaseUpdater`，不引入中间基类；以下规则由
`BoundaryPartUpdater` 和 `OffsetShellPartUpdater` 共同遵守：

| 规则 | 内容 |
|---|---|
| 局部目标 | 在 `reinitialize()` 中按顶层灵敏度建立唯一的 `LocalSensitivityObjective`，不手工注入 |
| 等式投影 | 每个几何 updater 只保存一个等式投影回调，接收 owner 与试探参数，返回同结构的新 Tensor |
| 不等式约束 | 局部罚函数回调接收 owner、试探参数和几何上下文，返回标量 `torch.Tensor` |
| 状态归属 | 约束回调、阈值、权重、启用掩码和初始化缓存由对应 updater 独立保存，并参与 `save()`/`load()` |
| 求值顺序 | 先建立试探设计值，再执行唯一等式投影，最后按注册顺序计算局部罚函数 |
| 提交 | 变化由 `Updaters.update()` 统一提交；几何 updater 不直接写回已提交参数 |

几何约束的完整清单和数据契约分别定义在 `BoundaryPartUpdater` 与
`OffsetShellPartUpdater` 的“局部项”表中。两个 updater 都在试探设计值建立后执行自己的
唯一等式投影，再按表中顺序计算局部罚函数；约束回调、阈值、权重、启用掩码和初始化缓存
均由对应 updater 独立保存。

### 11.4 `BoundaryPartUpdater`

`BoundaryPartUpdater` 专门更新一个 `BoundaryPart`，并在初始化后直接持有该对象的引用。
一个 `BoundaryPart` 只能绑定一个 `BoundaryPartUpdater`，一个问题可以为不同的
`BoundaryPart` 注册多个同类 updater。`_owner` 在本类中固定为 `BoundaryPart` 类型，
局部目标、等式约束、不等式约束和几何设计变量都从该引用读取或写回。
曲面控制点、曲面等式约束、Fairness 和边界 Part 的几何更新逻辑均在该 updater 的
owner 范围内完成。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_surface_update_mask` | tuple[bool, ...] 或 None | None | 按曲面选择是否作为设计变量；掩码为 `False` 的曲面不进入 `DesignBlock`，其控制点在整个运行期保持固定 |
| `_equality_constraint` | Callable 或 None | None | 当前 BoundaryPart 的唯一等式投影回调 |
| `_constraints` | dict[str, Callable] | {} | 当前 BoundaryPart 自己定义的局部约束回调及参数 |

掩码在 `initialize()` 阶段确定后即为固定定义：掩码为 `False` 的曲面不注册 `DesignBlock`，
因此不占用全局设计向量的任何区间；`get_parameters()` 也只返回参与更新的曲面控制点。
掩码在该 updater 的整个运行期内不可变，规则见[设计变量注册](10_design_registry.md)的变量
布局冻结。

本类约束回调的统一形态为：局部罚函数回调接收 owner、试探参数和几何上下文并返回标量
`torch.Tensor`；唯一等式投影回调接收 owner 与试探参数，返回同结构的投影参数。投影保持
Tensor device、dtype 和 autograd 连接。

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_surface_gradient` | tuple[torch.Tensor, ...] 或 None | None | 当前各曲面的几何梯度 |
| `_surface_change` | tuple[torch.Tensor, ...] 或 None | None | 最近一次各曲面的更新量 |
| `_step_length_by_surface` | tuple[torch.Tensor, ...] 或 None | None | 各曲面的自适应步长 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `constraints` | Mapping[str, Callable] | - | 只读 | 内部维护 | 当前 BoundaryPart 自己定义的局部约束回调 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_equality_constraint(constraint)` | None | - | 设置 BoundaryPart 的唯一等式投影回调；None 表示恒等投影 |
| `get_equality_constraint()` | Callable | - | 读取当前等式投影回调 |
| `add_constraint(name, constraint)` | None | - | 注册本 updater 的一个局部约束回调 |
| `compute_terms(values)` | tuple[Tensor, ...] | `BaseUpdater` | 重写局部目标和约束项计算，将值映射为边界曲面变量 |
| `closure(values)` | Tensor | `BaseUpdater` | 重写标量闭包并使用投影后的试探参数 |
| `initialize()` | None | `BaseUpdater` | 重写初始化，准备边界曲面优化状态 |
| `reinitialize(iteration, gradient)` | None | `BaseUpdater` | 重写梯度刷新，接收边界曲面梯度 |
| `update()` | None | `BaseUpdater` | 重写更新，将变化映射到边界 Part |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_update_surface_values()` | None | 根据试探设计增量更新各曲面几何值 |
| `_update_step_lengths()` | None | 根据相邻迭代的曲面变化调整步长 |
| `_apply_equality_constraint(values)` | torch.Tensor | 执行本 updater 保存的唯一等式投影并返回投影值 |
| `_evaluate_constraints(values)` | list[Tensor] | 计算本 updater 注册的局部约束 |
| `_commit_surface_changes()` | None | 将边界 Part 的曲面变化提交到 owner |

BoundaryPart 的局部项固定由本 updater 持有：

| 局部项 | 类别 | 输入 | 作用与运行时状态 |
|---|---|---|---|
| 固定局部目标 | 局部线性目标 | 顶层 `ObjectiveFunction` 分发的 BoundaryPart 局部灵敏度和当前设计变量 | 建立 `LocalSensitivityObjective` |
| `equality_projection` | 唯一等式投影 | owner、当前试探控制点、曲面顺序和用户参数 | 返回等式/镜像投影后的控制点；代码和参数由 `_equality_constraint` 保存 |
| `Fairness` | 几何罚函数 | 各曲面的 `r`、`rdu`、`rdu2`、曲面 Fairness evaluator 和点权重 | 组合各曲面 Fairness 值；`max_r`、`max_c`、`max_ff` 等公式参数和曲率补偿缓存由曲面 evaluator 保存，权重和启用曲面由本 updater 保存 |
| `Distance` | 几何罚函数 | 曲面点、曲面一阶导数、`min_distance: list[list[float]]` 矩阵和点权重 | 惩罚过近且法向相向的曲面点对；初始化阶段缓存邻接点对和对应最小距离 |
| `MinRadius` | 几何罚函数 | 曲面点、`radius` 和曲面启用掩码 | 惩罚小于指定最小半径的点 |
| `Cylinder` | 几何罚函数 | 曲面点、`radius`、`height`、`bottom` 和曲面启用掩码 | 惩罚超出圆柱半径、顶部或底部边界的点 |
| `VolumeMaximization` | 几何罚函数 | 指定 CPGEO 曲面 `surf_idx`、曲面三角面、曲面点和 `weight` | 返回负的封闭体积，使优化方向最大化体积 |

所有局部约束回调都注册到该 updater 的 `_constraints`，通过 `_evaluate_constraints(values)`
按注册顺序求值并参与 `closure()`；唯一等式投影在试探值建立后、罚函数计算前由
`_apply_equality_constraint()` 执行。约束的阈值、权重、启用曲面和初始化缓存均由本 updater
及其回调状态保存。

### 11.5 `OffsetShellPartUpdater`

`OffsetShellPartUpdater` 专门更新一个 `OffsetShellPart`。一个 `OffsetShellPart` 绑定一个
`OffsetShellPartUpdater`。该 updater 以源边界曲面的元曲面控制点作为唯一设计变量，并
根据固定偏置算法刷新向内偏置曲面、实体/壳单元和偏置节点；偏置规则由 `OffsetShellPart`
持有，更新策略由本类执行。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_equality_constraint` | Callable 或 None | None | 当前 OffsetShellPart 的唯一等式投影回调 |
| `_constraints` | dict[str, Callable] | {} | 当前 OffsetShellPart 自己定义的局部约束回调及参数 |

局部约束回调接收偏置壳 owner、试探参数和几何上下文并返回标量 `torch.Tensor`；唯一
等式投影回调返回同结构的投影参数。

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_boundary_gradient` | torch.Tensor 或 None | None | 源边界曲面元曲面控制点的局部梯度 |
| `_offset_change` | torch.Tensor 或 None | None | 根据控制点变化派生的偏置状态更新量 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `constraints` | Mapping[str, Callable] | - | 只读 | 内部维护 | 当前 OffsetShellPart 自己定义的局部约束回调 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_equality_constraint(constraint)` | None | - | 设置 OffsetShellPart 的唯一等式投影回调；None 表示恒等投影 |
| `get_equality_constraint()` | Callable | - | 读取当前等式投影回调 |
| `add_constraint(name, constraint)` | None | - | 注册本 updater 的一个局部约束回调 |
| `compute_terms(values)` | tuple[Tensor, ...] | `BaseUpdater` | 重写局部目标和约束项计算，将值映射为偏置变量 |
| `closure(values)` | Tensor | `BaseUpdater` | 重写标量闭包并使用投影后的元曲面参数 |
| `initialize()` | None | `BaseUpdater` | 重写初始化，准备偏置壳优化状态 |
| `reinitialize(iteration, gradient)` | None | `BaseUpdater` | 重写梯度刷新，接收偏置壳梯度 |
| `update()` | None | `BaseUpdater` | 重写更新，将变化映射到偏置壳 Part |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_update_offset_nodes()` | None | 根据源曲面变化更新偏置节点和相关单元数据 |
| `_apply_equality_constraint(values)` | torch.Tensor | 执行等式投影并返回投影值 |
| `_evaluate_constraints(values)` | list[Tensor] | 计算本 updater 注册的局部约束 |
| `_commit_offset_changes()` | None | 将偏置壳的变化提交到 owner |

OffsetShellPart 的局部项固定由本 updater 持有：

| 局部项 | 类别 | 输入 | 作用与运行时状态 |
|---|---|---|---|
| 固定局部目标 | 局部线性目标 | 顶层 `ObjectiveFunction` 分发的源边界局部灵敏度和当前设计变量 | 建立 `LocalSensitivityObjective`；偏置曲面不注册独立设计变量 |
| `equality_projection` | 唯一等式投影 | owner、源边界控制点、偏置规则和用户参数 | 返回投影后的元曲面控制点；代码和参数由本 updater 保存 |
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

### 11.6 `MaterialUpdater`

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
| `_constraint_parameters` | dict[str, dict[str, JsonValue]] | `{}` | 各局部约束的运行时参数：阈值、上下限、高斯点、积分权重和 penalty |
| `_regularization_parameters` | dict[str, dict[str, JsonValue]] | `{}` | 各正则项的运行时参数 |

约束与正则项按名称连同参数一起注册；参数表与回调一一对应，参与 `save()` / `load()`，
`initialize()` 负责重新建立高斯映射与积分权重缓存。

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `constraints` | Mapping[str, Callable] | - | 只读 | 内部维护 | 当前 MaterialUpdater 自己定义的局部约束回调 |
| `regularization_terms` | Mapping[str, Callable] | - | 只读 | 内部维护 | 当前材料场附加正则项回调 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_constraint(name, constraint)` | None | - | 注册本 updater 的一个材料约束回调 |
| `add_regularization(name, term)` | None | - | 注册一个材料场附加正则项回调 |
| `compute_terms(values)` | tuple[Tensor, ...] | `BaseUpdater` | 重写局部目标、约束和正则项计算，将值映射为材料变量 |
| `closure(values)` | Tensor | `BaseUpdater` | 重写标量闭包并汇总材料局部项 |
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
| `VolFrac` | 材料场罚函数 | `SIMPFieldMaterial`、目标 `element_name`、高斯点、积分权重、最小/最大体积分数和 penalty | 将材料控制点映射到高斯点，密度取 `sigmoid(design_field)`（不叠加 RAMP，也不叠加 `simp_ratio_min` 偏移），计算体积分数并惩罚超出区间的情况；高斯映射、积分权重和上下限在 `initialize()` 阶段缓存 |

`DensityFieldMinimize` 在 v3 中属于材料 updater 的附加正则目标，作用是抑制设计域外的
密度场；V4 将其作为 MaterialUpdater 的 `regularization_terms` 保存和计算，和上述约束
共同进入 updater 的 `closure()`。均匀材料作为固定材料参加材料赋值；SIMP 材料场注册
材料 updater 及上述约束。

### 11.7 `FEAUpdater`

`FEAUpdater` 通过 `BaseUpdater._owner` 绑定一个 `LoadValueBlock`，该 owner 精确对应一个
component 和一个 `case_index`。载荷局部约束由本 updater 保存，局部目标固定为顶层灵敏度
对该工况参数的线性展开。

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
| `constraints` | Mapping[str, Callable] | - | 只读 | 内部维护 | 当前 FEAUpdater 自己定义的局部约束回调 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_constraint(name, constraint)` | None | - | 注册本 updater 的一个载荷约束回调 |
| `compute_terms(values)` | tuple[torch.Tensor, ...] | `BaseUpdater` | 重写局部目标和约束项计算，将值映射为工况参数 |
| `closure(values)` | torch.Tensor | `BaseUpdater` | 重写标量闭包并汇总 FEA 局部项 |
| `update()` | None | `BaseUpdater` | 重写更新，将变化映射到 FEA component |
| `initialize()` | None | `BaseUpdater` | 重写初始化，准备 FEA component 优化状态 |
| `reinitialize(iteration, gradient)` | None | `BaseUpdater` | 重写梯度刷新，接收 FEA component 梯度 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_evaluate_constraints(values)` | list[Tensor] | 计算本 updater 注册的局部约束 |

`FEAUpdater` 的固定局部线性目标接收顶层灵敏度分发的工况参数梯度；局部约束接收
`LoadValueBlock` 参数、对应 component、Jacobian、`StaticResult` 和用户代码结果。

V4 基础 `FEAUpdater` 使用空约束清单，提供载荷参数的局部线性目标优化。载荷约束扩展类在
自己的 `_constraints` 中声明名称、输入、阈值和求值回调。`BoundaryCondition`、
`BoundaryConditionRP`、集中力、集中力矩和接触由 [FEA component](07_fea.md) 表达物理定义。

### 11.8 `UpdaterEntry`

`UpdaterEntry` 是一个统一的 updater 注册项，目标类别覆盖几何、材料、FEA 以及用户扩展类别。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_name` | str | updater 名称 |
| `_target_kind` | str | 目标类别，例如 `boundary_part`、`offset_shell_part`、`material`、`load` 或用户扩展类别 |
| `_target_name` | str | 目标对象的稳定名称；几何目标使用 `part_name` |
| `_case_index` | int 或 None | load 目标的工况索引；其他目标使用 None |
| `_updater` | `BaseUpdater` | 更新策略对象，可以是对应实体类型的内置 updater 或用户自定义子类 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

目标 owner 和变量块由其中的 updater 在 `Updaters.initialize()`
中绑定；updater 自身的运行时属性见 `BaseUpdater`。

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_initialized` | bool | False | 注册项绑定状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 内部维护 | 返回 updater 名称 |
| `target_kind` | str | 只读 | 内部维护 | 返回目标类别 |
| `target_name` | str | 只读 | 内部维护 | 返回目标名称 |
| `case_index` | int 或 None | 只读 | 内部维护 | 返回 load 工况索引 |
| `updater` | `BaseUpdater` | 只读 | 内部维护 | 返回与目标类型匹配的更新策略对象 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `validate(params, registry)` | None | - | 校验目标存在、key 唯一、owner 类型和 updater 类型匹配 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

### 11.9 `Updaters`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_entries` | list[`UpdaterEntry`] | `[]` | 按注册顺序记录 updater 项；每个可更新实体只出现一次 |
| `_device` | str | `"cpu"` | 全部 updater 局部优化使用的设备 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_initialized` | bool | False | 绑定状态 |
| `_registry` | `DesignRegistry` 或 None | None | 初始化后绑定的设计变量注册表 |
| `_last_changes` | dict[`DesignKey`, torch.Tensor] | `{}` | 最近一次统一提交的变化 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `entries` | tuple[`UpdaterEntry`, ...] | 只读 | 内部维护 | 返回 updater 注册项只读视图 |
| `device` | str | 只读 | 内部维护 | 返回 updater 局部优化设备 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `define_updaters()` | None | - | 用户注册任意数量和类型的 updater |
| `add_updater(target_kind, target_name, updater, name, case_index=None)` | None | - | 注册一个 updater，并校验目标类型、目标名称、工况和唯一绑定关系 |
| `update()` | None | - | 计算并保存所有局部变化，再一次性提交 |
| `get_changes()` | Mapping[`DesignKey`, torch.Tensor] | - | 读取最近一次保存的全部变化 |
| `initialize(params, registry)` | None | `Initializable` | 解析目标、绑定 `owner`、注册变量 |
| `reinitialize(iteration, gradients)` | None | `Initializable` | 分发局部梯度 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存全部 updater 状态 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载指定 iteration 的全部 updater 状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_resolve_owner(entry, params)` | `Updatable` | 解析注册项对应的 geometry/material/load owner |
| `_validate_change_set(changes)` | None | 校验 key 完整性、形状和有限性 |

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
| `load` | `LoadValueBlock` | `FEAUpdater` 或其载荷专用子类 |

`add_updater()` 在注册阶段维护 owner 键唯一，并在初始化阶段解析目标名称、取得对应的
`BoundaryPart`、`OffsetShellPart`、材料接口或 FEA component 对象，再注入 updater 的
`_owner`。初始化后 updater 直接使用该对象引用；目标名称保留在 `UpdaterEntry` 中，用于
校验、序列化和 UI 显示。相同 updater 类可以绑定多个不同 owner；一个 owner 对应
一个 updater。

`Updaters.update()` 按注册项逐个调用 updater 的 `update()`，分别计算并保存方向和步长形成的
局部变化；随后将所有变化按 `DesignKey` 汇总，并调用
`DesignRegistry.apply_design_delta(changes)` 一次性写回所有 `owner`。几何、材料、载荷和
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
| 查询 | `constraints` property 返回本 updater 的只读约束映射 | 读取名称和回调配置 |

### 12.1.1 `LocalSensitivityObjective`

`LocalSensitivityObjective` 是每个 updater 唯一的局部目标。它接收顶层
`ObjectiveFunction` 对当前 owner 设计变量的灵敏度，并在当前设计点建立局部线性展开：

```text
L_local(Δx) = L_local(x₀) + gradient_local · Δx
```

不同 owner 分别提供对应形状的设计变量和更新接口；局部目标的数学职责保持一致。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| 空 | - | 局部线性目标不接收用户定义参数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_owner` | `Updatable` 或 None | None | 初始化后绑定的 updater owner |
| `_context` | `UpdaterContext` 或 None | None | 当前 owner 的运行上下文 |
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
