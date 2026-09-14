# MorphOpt V4 Solver

本文件定义独立的 `Solver`。`Solver` 接收 `Params.get_assembly()` 提供的当前
`torchfea.Assembly`，创建 `StaticImplicitSolver`，执行多工况求解并保存 `StaticResult`。
求解初值策略直接由 `Solver` 的一个开关控制：当所有几何都没有设计变量时复用上一轮各
工况的 `GC`，存在几何设计变量时清空旧初值并重新求解。FEA component 的定义和维护属于
其他参数处理器；Solver 的输入边界是已经准备好的 Assembly。

返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

Solver 处理一条清晰的求解流水线：读取当前 Assembly、建立静力求解器、按工况分组执行
求解、收集结果。`Controller` 负责将 `Params` 生成的 Assembly 传给 Solver，并调度
优化迭代和结果消费。

```text
Controller.initialize()
    → Solver.initialize(num_steps)
    → Solver.build_solver()
    → Solver.set_reuse_previous_solution(not registry.has_geometry_variables())

Controller.step()
    → Params.reinitialize(iteration)
    → Params.build_assembly(iteration)
    → assembly = Params.get_assembly()
    → Solver.reinitialize(iteration)
    → Solver.solve(assembly)
    → Solver.get_results()
```

### 目录

- [8. Solver 类定义](#8-solver-类定义)
  - [8.1 `Solver`](#81-solver)
  - [8.2 Solver 调用约定](#82-solver-调用约定)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 当前 `torchfea.Assembly`、静力求解参数、工况数量、worker 配置、设备配置、几何设计变量状态和可选初始广义坐标 |
| 输出 | `StaticImplicitSolver` 运行对象、按工况排序的 `StaticResult` 和求解状态 |
| 主要读者 | Solver 实现者、Controller、目标函数、运行时和 UI 实现者 |
| 关联文档 | [总览与生命周期](01-04Overview.md)、[运行时](13-14Runtime.md)、[目标函数](09Objective.md)、[功能迁移清单](23FunctionInventory.md) |

## 8. Solver 类定义

### 8.1 `Solver`

`Solver` 是静力求解器的定义与执行对象。它保存 `StaticImplicitSolver` 的参数，
创建 TorchFEA 静力求解器，并使用 `Params.get_assembly()` 提供的 Assembly 执行求解。
求解结果由 `Solver` 按工况顺序保存并通过 `get_results()` 读取。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_maximum_iteration` | int | `10000` | `StaticImplicitSolver` 最大迭代次数 |
| `_tol_error` | float | `1e-5` | `StaticImplicitSolver` 收敛容差 |
| `_num_process` | int | `4` | worker 数量 |
| `_gpu_names` | list[str] | `[]` | 用户指定的 GPU 名称 |
| `_task_index_list` | list[list[int]] 或 None | None | 用户指定的工况分组 |
| `_reuse_previous_solution` | bool 或 None | None | 求解初值开关；`None` 由 Controller 根据几何设计变量自动决定，`True` 复用上一轮 GC，`False` 每轮重新求解 |

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_task_groups` | tuple[tuple[int, ...], ...] | `()` | 初始化后生成的 worker 分组 |
| `_available_gpus` | tuple[str, ...] | `()` | 解析后的设备列表 |
| `_torchfea_StaticImplicitSolver` | `torchfea.solver.static.StaticImplicitSolver` 或 None | None | 由 Solver 创建的 TorchFEA 静力求解器 |
| `_results` | tuple[StaticResult, ...] | `()` | 最近一次按 step 排序的结果 |
| `_previous_gc` | tuple[torch.Tensor, ...] 或 None | None | 上一轮各工况的 GC detached clone；仅在复用开关开启时作为下一轮初值 |
| `_initialized` | bool | False | 初始化状态 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `num_process` | int | 只读 | 内部维护 | 返回 worker 数量 |
| `gpu_names` | tuple[str, ...] | 只读 | 内部维护 | 返回设备配置 |
| `reuse_previous_solution` | bool 或 None | 只读 | 内部维护 | 返回当前求解初值开关；`None` 表示等待 Controller 自动判定 |

#### 4. 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `initialize(num_steps)` | None | `Initializable` | 根据工况数量创建任务分组 |
| `reinitialize(iteration)` | None | `Initializable` | 刷新当前迭代的求解器状态；开关为 `False` 时清空上一轮 GC |
| `build_solver()` | None | - | 根据 Solver 配置创建并保存 `StaticImplicitSolver` |
| `get_solver()` | `torchfea.solver.static.StaticImplicitSolver` | - | 读取已经创建的静力求解器 |
| `set_reuse_previous_solution(enabled)` | None | - | 设置是否复用上一轮各工况的 GC；传入 `None` 恢复自动判定 |
| `get_reuse_previous_solution()` | bool 或 None | - | 读取当前求解初值开关 |
| `solve(assembly, U_guess=None)` | None | Solver protocol | 使用当前 Assembly 调用静力求解器并写入 `_results` |
| `get_results()` | tuple[StaticResult, ...] | Solver protocol | 读取最近一次排序后的结果 |
| `get_task_index_list()` | tuple[tuple[int, ...], ...] | Solver protocol | 读取 worker 工况分组 |
| `get_available_gpus()` | tuple[str, ...] | Solver protocol | 读取可用设备列表 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存求解器状态和任务配置 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载指定迭代的求解器状态 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_build_task_groups(num_steps)` | None | 生成工况到 worker 的分组 |
| `_resolve_devices()` | None | 解析 CPU/GPU 设备配置 |
| `_build_solver()` | None | 创建 `StaticImplicitSolver` 并写入 `_torchfea_StaticImplicitSolver` |
| `_build_solver_context(assembly)` | object | 根据当前 Assembly 建立 TorchFEA 求解上下文 |
| `_select_initial_guess(U_guess)` | tuple[torch.Tensor, ...] 或 None | 按显式参数和复用开关选择本轮各工况初始 GC |
| `_solve_task(assembly, task_indices, U_guess)` | list[StaticResult] | 在一个 worker 中求解任务组 |
| `_sort_results(results)` | tuple[StaticResult, ...] | 按 step index 排序结果 |
| `_validate_results(results)` | None | 检查结果收敛状态和数量 |
| `_store_previous_gc(results)` | None | 从当前结果保存各工况 GC 的 detached clone |

`Solver` 的公共输入是 `Assembly` 和可选的初始广义坐标；静力求解器的运行上下文由
`_build_solver_context(assembly)` 建立。`Solver` 通过 `build_solver()` 创建
`StaticImplicitSolver`，通过 `solve()` 更新 `_results`，通过 `get_results()` 读取结果。

求解初值策略由一个开关统一控制：

1. `U_guess` 显式传入时，优先使用调用者给出的初值；
2. 开关为 `True` 且存在 `_previous_gc` 时，按 `step_index` 使用上一轮结果的 GC；
3. 开关为 `False`，或开关为 `True` 但尚无历史结果时，从当前静力求解器默认初值开始；
4. 当前求解完成后，`_store_previous_gc()` 保存每个工况的 detached GC，供下一轮使用。

Controller 在 `DesignRegistry.finalize()` 后检查是否存在 `geometry` 变量：当开关仍为 `None`
时，没有几何设计变量就设置 `set_reuse_previous_solution(True)`，存在任意几何设计变量就
设置为 `False`。用户也可显式传入 `True` 或 `False` 覆盖自动策略，传入 `None` 恢复自动判定；
几何设计变量变化时不复用历史 GC。

### 8.2 Solver 调用约定

```text
# 一次性运行时初始化
Controller.initialize()
solver.initialize(num_steps)
solver.build_solver()
solver.set_reuse_previous_solution(not registry.has_geometry_variables())

# 每个外层 iteration
Controller.step()
params.reinitialize(iteration)
params.build_assembly(iteration)
assembly = params.get_assembly()
solver.reinitialize(iteration)
solver.solve(assembly)
results = solver.get_results()
```

`Params` 负责生成当前迭代的 Assembly；`Solver` 接收该 Assembly，建立静力求解器并
根据几何设计变量状态选择初始 GC，返回当前工况结果。Controller 负责在优化主循环中安排
上述调用、结果消费和下一次迭代。
