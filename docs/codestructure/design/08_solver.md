# MorphOpt V4 Solver

本文件定义独立的静力求解器、工况调度和初值复用。返回[总入口](../design.md)。

## 文档导航与输入/输出摘要

Controller 为全部工况直接持有一个共享的 `torchfea.FEAController`，并将 Params 准备的
`Assembly` 写入其公开属性；`Solver` 创建并挂接一个多工况 `StaticImplicitSolver`，负责设备配置、
一次性多工况求解、结果排序和上轮 GC 初值。生命周期测试使用 `_AssemblyController` 这个
`torchfea.FEAController` 的轻量子类，不增加运行时适配层。

### 目录

- [8.1 `Solver`](#81-solver)
- [8.2 工况求解协议](#82-工况求解协议)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 共享 `FEAController`、静力求解参数、Jacobian 名称、worker/设备配置和可选初始 GC |
| 输出 | 共享 `StaticImplicitSolver`、按 `step_index` 排序的 `StaticResult` 和上轮 GC 缓存 |
| 主要读者 | Solver、Controller、Objective 和任务运行器实现者 |
| 关联文档 | [FEA 组件](07_fea.md)、[运行时](13_14_runtime.md)、[目标函数](09_objective.md) |

## 8.1 `Solver`

`Solver` 实现 `Initializable` 和 `Persistable`。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_maximum_iterations` | int | `10000` | 单个静力工况最大迭代次数 |
| `_error_tolerance` | float | `1e-5` | 收敛误差容差 |
| `_num_processes` | int | `4` | worker 数量 |
| `_device_names` | tuple[str, ...] | `()` | 用户指定的 FEA 求解设备；空元组由 Solver 解析为 CPU |
| `_task_groups` | tuple[tuple[int, ...], ...] 或 None | None | 用户指定的工况分组 |
| `_reuse_previous_solution` | bool 或 None | None | `True` 复用上轮 GC，`False` 使用默认初值，`None` 由 Controller 判定 |

### 运行时属性（`__init__()` 声明，生命周期方法填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_resolved_task_groups` | tuple[tuple[int, ...], ...] | `()` | 已校验的 worker 工况分组 |
| `_available_devices` | tuple[str, ...] | `()` | 已解析设备列表 |
| `_torchfea_StaticImplicitSolver` | `torchfea.solver.StaticImplicitSolver` 或 None | None | 共享 `FEAController` 上承载全部工况的 TorchFEA 求解器 |
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
| `build_solvers(fea_controller)` | None | - | 为共享控制器创建并挂接 TorchFEA 静力求解器 |
| `get_solver()` | `torchfea.solver.StaticImplicitSolver` 或 None | - | 读取已经建立的共享求解器 |
| `set_reuse_previous_solution(enabled)` | None | - | 将初值策略设为 `True`、`False` 或自动值 `None` |
| `get_reuse_previous_solution()` | bool 或 None | - | 读取当前初值策略 |
| `solve(fea_controller, jacobian_names=(), initial_gc_by_case=None)` | None | - | 通过共享 `FEAController` 一次求解全部工况，并为指定载荷建立响应 Jacobian 后保存排序结果 |
| `get_results()` | tuple[`StaticResult`, ...] | - | 读取最近一次求解结果 |
| `get_sensitivity_solver()` | `torchfea.solver.StaticImplicitSolver` | - | 读取绑定基座 Assembly 的静力求解器，供灵敏度分析使用 |
| `get_task_groups()` | tuple[tuple[int, ...], ...] | - | 读取已建立工况分组 |
| `get_devices()` | tuple[str, ...] | - | 读取已解析设备 |
| `change_device(device)` | None | - | 设置单一 FEA 求解设备 |
| `change_devices(device_names)` | None | - | 设置 FEA 求解设备列表 |
| `initialize(num_steps)` | None | `Initializable` | 校验配置、解析设备并建立工况分组 |
| `reinitialize(iteration)` | None | `Initializable` | 清空本轮结果并按初值策略维护 GC 缓存 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存配置、工况分组和可复用 GC |
| `load(folder_path, iteration)` | None | `Persistable` | 恢复配置兼容的工况分组和 GC |

### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_build_task_groups(num_steps)` | None | 建立覆盖每个工况一次的稳定分组 |
| `_resolve_devices()` | None | 解析 CPU/CUDA 设备并校验 worker 映射 |
| `_select_initial_gc(case_index, explicit_gc)` | torch.Tensor 或 None | 按显式值、复用缓存和默认值优先级选择初值 |
| `_solve_cases(fea_controller, jacobian_names, initial_gc_by_case)` | list[`StaticResult`] | 调用共享 `FEAController.solve()` 并建立请求的 Jacobian |
| `_sort_results(results)` | tuple[`StaticResult`, ...] | 按 morphopt 附加的 `step_index` 排序并检查唯一性 |
| `_validate_results(results, expected_indices)` | None | 校验数量、索引、有限值和收敛状态 |
| `_update_previous_gc(results)` | None | 保存各工况 GC 的 detached clone |

`Solver` 的固定行为约定：

- **调用顺序**：`initialize(num_steps)` → `reinitialize(iteration)` →
  `build_solvers(fea_controller)` → `solve(...)` → `get_results()`。`reinitialize()` 在
  `build_solvers()` 前准备本轮初值策略和 GC 缓存。
- **收敛失败**：任一工况在 `_maximum_iterations` 内未满足 `_error_tolerance` 时，
  `_validate_results()` 抛出求解错误并中止本次 `step()`。`Solver` 不返回部分结果，也不把
  未收敛结果交给 `SensitivityAnalyzer`，避免用不准确的切线产生错误梯度。
- **Jacobian 名称**：`solve(..., jacobian_names)` 的名称来自
  `ObjectiveFunction.jacobian_needed`，两者是同一列表在不同对象的称呼；名称必须引用
  `FEAParams` 中 `num_values > 0` 的 component，校验在 `ObjectiveFunction.initialize()`
  阶段完成。
- **设备归属**：`Solver.device_names` 是 FEA 求解设备的唯一配置来源；为空元组时由
  `Solver` 解析为 CPU。Controller 的 `device` 只服务于控制器侧的编排和辅助 Tensor，
  不参与 FEA 设备推断。`Controller.change_device()` 只更新控制器设备；需要改变 FEA
  设备时调用 `Controller.change_solver_devices()`，设备解析规则只在
  `_resolve_devices()` 中实现一次。Updater 设备由 `Controller.updater_device` 独立传给
  `Updaters`，不从 Solver 或 Controller 的外部设备继承。
- **冻结默认值**：`_maximum_iterations=10000`、`_error_tolerance=1e-5`、
  `_num_processes=4` 属于跨章冻结数值，见[破坏性变更与冻结契约](24_breaking_changes.md)。

## 8.2 工况求解协议

Controller 使用本轮 `Params.build_assembly()` 创建的共享 Assembly，由 `FEAParams` 将各
`LoadStep` 绑定为工况视图，最后组合一个共享 `FEAController`：

```text
base_assembly = params.get_assembly()
fea.build_case_assemblies()
case_assemblies = fea.get_case_assemblies()  # 每个元素都指向同一 Assembly
fea_controller = controller.build_fea_controller()

solver.reinitialize(iteration)
solver.build_solvers(fea_controller)
solver.solve(fea_controller, jacobian_names=objective.jacobian_needed)
results = solver.get_results()
```

`FEAParams.build_case_assemblies()` 为当前 detached Assembly 建立全部工况视图，把每个
`LoadValueBlock` 的已提交值写入共享控制器的工作条件。灵敏度阶段再由
`DesignRegistry.update_assembly()` 建立试探计算图。Controller 持有一个
`FEAController`；`build_solvers()` 将一个多工况静力求解器挂接到该控制器。库调用链固定为：

```text
static_solver = torchfea.solver.StaticImplicitSolver(maximum_iteration, tol_error)
fea_controller.set_work_conditions(work_conditions)
static_result = static_solver.solve(GC0=initial_gc, need_jacobian=bool(jacobian_names))
static_result = static_solver.get_jacobian(static_result, load_names=tuple(jacobian_names))
```

debug 模式在当前进程求解；标准模式把共享控制器按 `_resolved_task_groups` 发送给
spawn worker。worker 在共享 Assembly 的全部工作条件上完成平衡求解和 Jacobian 建立，再把可 pickle 的
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
