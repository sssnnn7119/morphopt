# MorphOpt V4 目标函数

本文件定义顶层目标函数、指标、Jacobian、结果工况读取和结果网格生成。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文定义顶层 `ObjectiveFunction` 的计算边界：读取 FEA 结果，计算标量目标和展示指标，
按需读取 Jacobian，并提供按结果工况查询和结果网格生成接口。顶层目标完成灵敏度分析后，
由 `Controller` 按设计变量块将梯度分发给各 updater，updater 自动建立固定的局部线性目标；
局部约束由 updater 持有和调度，
运行记录由运行时 `History` 管理，几何 Fairness evaluator 由曲面持有并提供给几何约束调用。

### 目录

- [9. `ObjectiveFunction`](#9-objectivefunction)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | Assembly、StaticResult、目标与指标代码、Jacobian 需求和当前结果上下文 |
| 输出 | 标量目标、指标列表、Jacobian、结果工况数据和结果网格 |
| 主要读者 | ObjectiveFunction、Controller、Updater 和结果分析实现者 |
| 关联文档 | [FEA 组件](07Fea.md)、[Solver](08Solver.md)、[Updater](11-12Updaters.md)、[运行时](13-14Runtime.md)、[History](15History.md) |

## 9. `ObjectiveFunction`

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_jacobian_needed` | list[str] | [] | Jacobian 所需接口名称 |

### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_assembly` | `torchfea.Assembly` 或 None | None | 当前结果对应的 Assembly |
| `_fe_results` | list[`StaticResult`] | [] | 当前工况结果的记录容器 |
| `_metrics` | list[float] | [] | 当前展示指标 |
| `_initialized` | bool | False | 初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `jacobian_needed` | tuple[str, ...] | 只读 | 内部维护 | 返回 Jacobian 所需接口名称 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `compute_objective()` | torch.Tensor | - | 重新计算一个标量目标 |
| `get_metrics(case_index)` | list[float] | - | 读取指定结果工况已经计算的展示指标 |
| `get_fe_results(case_index)` | tuple[`StaticResult`, ...] | - | 读取指定结果工况的 FEA 结果 |
| `update_step(step_index)` | None | - | 通过当前 Assembly 写入指定结果工况的 work condition |
| `compute_multistep_objective(fe_results, assembly)` | torch.Tensor | - | 重新计算并聚合多工况目标 |
| `compute_sensitivity(registry)` | dict[`DesignKey`, torch.Tensor] | - | 重新计算并切分灵敏度 |
| `build_mesh_case(case_index)` | None | - | 创建并缓存指定工况的结果网格 |
| `get_mesh_case(case_index)` | list[object] | - | 读取已经缓存的工况结果网格 |
| `initialize()` | None | `Initializable` | 校验目标和 Jacobian 引用 |
| `save(foldpath, iteration)` | None | `Persistable` | 保存目标值、指标和结果引用 |
| `load(foldpath, iteration)` | None | `Persistable` | 加载指定 iteration 的历史结果 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

`compute_objective()` 读取当前 FEA 结果和 `Assembly`，返回标量 Tensor。目标函数
负责多工况求和、平均、最大值或加权聚合。`metrics` 只服务历史和 UI 展示。
结果网格由 `build_mesh_case(case_index)` 创建并缓存，`get_mesh_case(case_index)` 只读取缓存，不触发结果重算。
`get_metrics(case_index)` 和 `get_fe_results(case_index)` 是 `ObjectiveFunction` 的结果查询接口，
通过同一个 `case_index` 读取对应结果工况的数据。结果网格接口使用
`ObjectiveFunction` 自身的 FEA 结果上下文，和目标计算接口一起组织在本类的外部接口中。
`update_step(step_index)` 使用当前 Assembly，读取
`_fe_results[step_index].work_conditions` 并更新当前工况上下文。

`jacobian_needed` 中的名称来自 `FEAParams`。集中力和集中力矩使用同一
`reference_point` 时，初始化阶段校验目标一致。

`ObjectiveFunction` 负责顶层目标、指标、Jacobian、结果工况读取、结果网格生成和全局灵敏度
分析。各 updater 的局部目标统一为 `LocalSensitivityObjective`，由 Controller 根据切分后的
局部梯度自动建立；局部约束由对应的 `BoundaryPartUpdater`、`OffsetShellPartUpdater`、
`MaterialUpdater` 或 `FEAUpdater` 注册、初始化和计算。
