# MorphOpt V4 Solver

本文件定义独立的静力求解器、工况调度和初值复用。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

Controller 为每个工况创建 `torchfea.FEAController`，将 Params 准备的 `Assembly` 挂到
`FEAController.assembly`；`Solver` 创建逐工况 `StaticImplicitSolver`，挂到
`FEAController.solver`，并负责设备分组、求解、结果排序和上轮 GC 初值。

### 目录

- [8.1 `Solver`](#81-solver)
- [8.2 工况求解协议](#82-工况求解协议)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | `step_index → FEAController`、静力求解参数、Jacobian 名称、worker/设备配置和可选初始 GC |
| 输出 | 逐工况 `StaticImplicitSolver`、按 `step_index` 排序的 `StaticResult` 和上轮 GC 缓存 |
| 主要读者 | Solver、Controller、Objective 和任务运行器实现者 |
| 关联文档 | [FEA 组件](07Fea.md)、[运行时](13-14Runtime.md)、[目标函数](09Objective.md) |

## 8.1 `Solver`

`Solver` 实现 `Initializable` 和 `Persistable`。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_maximum_iterations` | int | `10000` | 单个静力工况最大迭代次数 |
| `_error_tolerance` | float | `1e-5` | 收敛误差容差 |
| `_num_processes` | int | `4` | worker 数量 |
| `_device_names` | tuple[str, ...] | `()` | 用户指定设备；空元组使用 CPU |
| `_task_groups` | tuple[tuple[int, ...], ...] 或 None | None | 用户指定的工况分组 |
| `_reuse_previous_solution` | bool 或 None | None | `True` 复用上轮 GC，`False` 使用默认初值，`None` 由 Controller 判定 |

### 运行时属性（`__init__()` 声明，生命周期方法填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_resolved_task_groups` | tuple[tuple[int, ...], ...] | `()` | 已校验的 worker 工况分组 |
| `_available_devices` | tuple[str, ...] | `()` | 已解析设备列表 |
| `_torchfea_StaticImplicitSolver` | dict[int, `torchfea.solver.static.StaticImplicitSolver`] | `{}` | 按工况保存并已挂接到 `FEAController` 的 TorchFEA 求解器 |
| `_results` | tuple[`StaticResult`, ...] | `()` | 最近一次按工况排序的结果 |
| `_previous_gc_by_case` | dict[int, torch.Tensor] | `{}` | 上一轮各工况 GC 的 detached clone |
| `_initialized` | bool | False | 求解器初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `maximum_iterations` | int | 只读 | 内部维护 | 返回最大迭代次数 |
| `error_tolerance` | float | 只读 | 内部维护 | 返回误差容差 |
| `num_processes` | int | 只读 | 内部维护 | 返回 worker 数量 |
| `device_names` | tuple[str, ...] | 只读 | 内部维护 | 返回设备配置 |
| `task_groups` | tuple[tuple[int, ...], ...] 或 None | 只读 | 内部维护 | 返回显式工况分组 |
| `reuse_previous_solution` | bool 或 None | 只读 | 内部维护 | 返回初值策略 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `build_solvers(fea_controllers)` | None | - | 为每个工况创建、保存并挂接 TorchFEA 静力求解器 |
| `get_solver(case_index)` | `torchfea.solver.static.StaticImplicitSolver` | - | 读取指定工况已经建立的求解器 |
| `set_reuse_previous_solution(enabled)` | None | - | 将初值策略设为 `True`、`False` 或自动值 `None` |
| `get_reuse_previous_solution()` | bool 或 None | - | 读取当前初值策略 |
| `solve(fea_controllers, jacobian_names=(), initial_gc_by_case=None)` | None | - | 通过逐工况 `FEAController` 求解全部工况，并为指定载荷建立响应 Jacobian 后保存排序结果 |
| `get_results()` | tuple[`StaticResult`, ...] | - | 读取最近一次求解结果 |
| `get_sensitivity_solver()` | `torchfea.solver.static.StaticImplicitSolver` | - | 读取绑定基座 Assembly 的静力求解器，供灵敏度分析使用 |
| `get_task_groups()` | tuple[tuple[int, ...], ...] | - | 读取已建立工况分组 |
| `get_devices()` | tuple[str, ...] | - | 读取已解析设备 |
| `initialize(num_steps)` | None | `Initializable` | 校验配置、解析设备并建立工况分组 |
| `reinitialize(iteration)` | None | `Initializable` | 清空本轮结果并按初值策略维护 GC 缓存 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存配置、工况分组和可复用 GC |
| `load(folder_path, iteration)` | None | `Persistable` | 恢复配置兼容的工况分组和 GC |

### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_build_task_groups(num_steps)` | None | 建立覆盖每个工况一次的稳定分组 |
| `_resolve_devices()` | None | 解析 CPU/CUDA 设备并校验 worker 映射 |
| `_create_solver()` | `torchfea.solver.static.StaticImplicitSolver` | 按当前配置创建一个全新的静力求解器 |
| `_select_initial_gc(case_index, explicit_gc)` | torch.Tensor 或 None | 按显式值、复用缓存和默认值优先级选择初值 |
| `_solve_task(fea_controllers, task_indices, jacobian_names, initial_gc)` | list[`StaticResult`] | 在一个 worker 中按顺序调用逐工况 `FEAController.solve()` 并建立请求的 Jacobian |
| `_sort_results(results)` | tuple[`StaticResult`, ...] | 按 morphopt 附加的 `step_index` 排序并检查唯一性 |
| `_validate_results(results, expected_indices)` | None | 校验数量、索引、有限值和收敛状态 |
| `_update_previous_gc(results)` | None | 保存各工况 GC 的 detached clone |

`Solver` 的固定行为约定：

- **调用顺序**：`initialize(num_steps)` → `reinitialize(iteration)` →
  `build_solvers(fea_controllers)` → `solve(...)` → `get_results()`。`reinitialize()` 必须在
  `build_solvers()` 之前执行，因为初值策略和 GC 缓存要在创建逐工况求解器之前确定。
- **收敛失败**：任一工况在 `_maximum_iterations` 内未满足 `_error_tolerance` 时，
  `_validate_results()` 抛出求解错误并中止本次 `step()`。`Solver` 不返回部分结果，也不把
  未收敛结果交给 `SensitivityAnalyzer`，避免用不准确的切线产生错误梯度。
- **Jacobian 名称**：`solve(..., jacobian_names)` 的名称来自
  `ObjectiveFunction.jacobian_needed`，两者是同一列表在不同对象的称呼；名称必须引用
  `FEAParams` 中 `num_values > 0` 的 component，校验在 `ObjectiveFunction.initialize()`
  阶段完成。
- **设备归属**：`Solver.device_names` 显式配置时优先；为空元组时使用
  `Controller.device`（默认 `"cpu"`）。`Controller.change_device()` 只更新
  `Controller.device` 并转调 `Solver` 重新解析设备，设备解析规则只在 `_resolve_devices()`
  中实现一次。
- **冻结默认值**：`_maximum_iterations=10000`、`_error_tolerance=1e-5`、
  `_num_processes=4` 属于跨章冻结数值，见[破坏性变更与冻结契约](24BreakingChanges.md)。

## 8.2 工况求解协议

Controller 先把几何和材料试探状态写入基础 Assembly，再由 `FEAParams` 建立相互隔离的
工况 Assembly，最后把各载荷设计块写入所属工况，并组合逐工况 `FEAController`：

```text
base_assembly = params.get_assembly()
registry.update_assembly(design_delta, categories={"geometry", "material"})
fea.build_case_assemblies()
registry.update_assembly(design_delta, categories={"load"})
case_assemblies = fea.get_case_assemblies()

controller.build_fea_controllers(case_assemblies)
fea_controllers = controller.get_fea_controllers()

solver.reinitialize(iteration)
solver.build_solvers(fea_controllers)
solver.solve(fea_controllers, jacobian_names=objective.jacobian_needed)
results = solver.get_results()
```

`FEAParams.build_case_assemblies()` 保留几何和材料设计 Tensor 的 autograd 连接，为每个
工况复制可变状态、创建独立 TorchFEA component，并把 `LoadValueBlock` 绑定到所属副本。
Controller 为每个副本创建独立 `FEAController`；`build_solvers()` 为其挂接独立求解器。
每个求解器的库调用链固定为：

```text
static_solver = torchfea.solver.static.StaticImplicitSolver(maximum_iteration, tol_error)
fea_controller.set_work_conditions(work_conditions)
static_result = static_solver.solve(GC0=initial_gc, need_jacobian=bool(jacobian_names))
static_result = static_solver.get_jacobian(static_result, load_names=tuple(jacobian_names))
```

debug 模式在当前进程顺序求解；标准模式把逐工况控制器按 `_resolved_task_groups` 发送给
spawn worker。worker 在同一工况 Assembly 上完成平衡求解和 Jacobian 建立，再把可 pickle 的
detached `StaticResult` 返回主进程（库的 `__getstate__` 已排除稀疏分解对象）。库结果字段固定
为 `GC`、`converged`、`model_hash`、`jacobian`、`work_conditions`、`total_time` 和
`time_items`；库不提供工况序号、能量和残差误差字段，因此 `Solver` 读取结果后附加
`step_index` 属性，能量按需通过 `StaticImplicitSolver.get_total_energy(GC)` 计算，误差只用
于收敛判定。

显式 `initial_gc_by_case` 优先级最高；随后使用 `_previous_gc_by_case`；其余工况使用
TorchFEA 默认初值。同一个任务组从显式或缓存初值开始，后续工况默认使用前一工况的收敛
`GC`；各工况自由度数量不一致时改用该工况自己的初值策略。Controller 在 Registry 初始化后
设置自动策略：几何变量块为空时复用上轮 GC，存在几何变量块时使用默认初值。求解完成后
按工况更新 GC 缓存。
