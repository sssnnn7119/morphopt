# MorphOpt V4 Params、Controller 与主循环

本文件定义问题参数流水线、单步结果和优化主循环。运行记录由独立的
[`History`](15History.md) 文档定义。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

`Params` 依次用 Geometry、Materials 和 FEA 三个处理器加工一个 Assembly；`Controller`
创建运行对象并调度迭代。一次性初始化负责对象关系和资源，`step()` 负责当前迭代的
Assembly、求解、目标、灵敏度和更新，`_opt_loop()` 负责重复、记录、保存和停止。

### 目录

- [13.1 `Params`](#131-params)
- [13.2 Params Assembly 流水线](#132-params-assembly-流水线)
- [14.1 `StepResult`](#141-stepresult)
- [14.2 `Controller`](#142-controller)
- [14.3 运行入口与生命周期](#143-运行入口与生命周期)
- [14.4 `RuntimeEvent`](#144-runtimeevent)
- [14.5 `TaskRunner`](#145-taskrunner)
- [14.6 日志、历史加载与梯度检查工具](#146-日志历史加载与梯度检查工具)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | Geometry、Materials、FEA、Solver、Objective、DesignRegistry、Updaters 和运行配置 |
| 输出 | 当前 Assembly、逐工况结果、目标、灵敏度、设计更新、History 和任务状态 |
| 主要读者 | Controller、Params、Solver、Updater、任务入口和运行监控实现者 |
| 关联文档 | [总览](01-04Overview.md)、[Solver](08Solver.md)、[目标函数](09Objective.md)、[Updater](11-12Updaters.md)、[History](15History.md) |

### 对象层级

```text
Controller
├── Params
│   ├── GeometryParams ──build──> Assembly
│   ├── MaterialsParams ─assign─> Assembly
│   └── FEAParams ───────assign─> Assembly / LoadStep
├── FEAController[step] <─────── Assembly[step] + StaticImplicitSolver[step]
├── Solver ─────────────────────> StaticImplicitSolver[step] / StaticResult[step]
├── ObjectiveFunction ──────────> objective / metrics / result meshes
├── SensitivityAnalyzer ────────> implicit total gradients
├── DesignRegistry ─────────────> ordered design blocks
├── Updaters ───────────────────> committed parameter updates
└── History ────────────────────> HistoryRecord[iteration]
```

## 13.1 `Params`

`Params` 实现 `Initializable`、`Visualizable` 和 `Persistable`。构造参数是三个处理器工厂；
领域定义分别写在 `GeometryParams.define_parts()`、`MaterialsParams.define_materials()`、
`FEAParams.define_components()` 和 `FEAParams.define_steps()` 中。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_geometry_factory` | Callable[[], `GeometryParams`] | - | 几何处理器工厂 |
| `_materials_factory` | Callable[[], `MaterialsParams`] | - | 材料处理器工厂 |
| `_fea_factory` | Callable[[], `FEAParams`] | - | FEA 处理器工厂 |

### 运行时属性（`__init__()` 声明，生命周期方法填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_geometry` | `GeometryParams` 或 None | None | 已初始化几何处理器 |
| `_materials` | `MaterialsParams` 或 None | None | 已初始化材料处理器 |
| `_fea` | `FEAParams` 或 None | None | 已初始化 FEA 处理器 |
| `_iteration` | int 或 None | None | 当前待构建迭代 |
| `_torchfea_Assembly` | `torchfea.Assembly` 或 None | None | 最近建立的完整 Assembly |
| `_initialized` | bool | False | 处理器初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `geometry_factory` | Callable[[], `GeometryParams`] | 只读 | 内部维护 | 返回几何工厂 |
| `materials_factory` | Callable[[], `MaterialsParams`] | 只读 | 内部维护 | 返回材料工厂 |
| `fea_factory` | Callable[[], `FEAParams`] | 只读 | 内部维护 | 返回 FEA 工厂 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `build_assembly()` | None | - | 按 Geometry → Materials → FEA 建立并保存当前完整 Assembly |
| `get_geometry()` | `GeometryParams` | - | 读取已经初始化的几何处理器 |
| `get_materials()` | `MaterialsParams` | - | 读取已经初始化的材料处理器 |
| `get_fea()` | `FEAParams` | - | 读取已经初始化的 FEA 处理器 |
| `get_assembly()` | `torchfea.Assembly` | - | 读取已经建立的完整 Assembly |
| `export_problem_data(target_path)` | pathlib.Path | - | 将当前用户可读模型数据导出到目标地址并返回实际路径 |
| `initialize()` | None | `Initializable` | 创建三个处理器，执行定义扩展点并完成静态校验 |
| `reinitialize(iteration)` | None | `Initializable` | 保存当前迭代、刷新几何状态并清空上一轮 Assembly 引用 |
| `build_meshes()` | None | `Visualizable` | 聚合建立几何、材料和 FEA 预览缓存 |
| `get_meshes()` | tuple[object, ...] | `Visualizable` | 读取已经建立的聚合预览 |
| `save(folder_path, iteration)` | None | `Persistable` | 调度三个处理器保存状态和 Assembly 元数据 |
| `load(folder_path, iteration)` | None | `Persistable` | 恢复三个处理器状态并在下次构建时重建 Assembly |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_create_processors()` | None | 调用三个工厂并校验处理器类型 |
| `_validate_assembly(assembly)` | None | 校验名称、目标、材料覆盖和 component 挂接完整性 |

## 13.2 Params Assembly 流水线

```text
params.reinitialize(iteration)
params.build_assembly()
    → geometry.build_assembly()
    → assembly = geometry.get_assembly()
    → materials.reinitialize(iteration, assembly)
    → materials.build_materials()
    → materials.assign_materials()
    → fea.reinitialize(iteration, assembly)
    → fea.build_components()
    → fea.assign_components()
    → validate assembly
    → save params._torchfea_Assembly
```

三个处理器彼此独立，以同一个 Assembly 形成单向加工流水线。Geometry 建立拓扑、Part、
Instance、集合和 ReferencePoint；Materials 解析 Part/element 目标并写入材料；FEA 解析
Instance/Surface/NodeSet/ElementSet/ReferencePoint 并写入 component。各创建者缓存自己创建的
TorchFEA 对象引用，后续 `update_assembly()` 直接更新这些引用。

## 14.1 `StepResult`

`StepResult` 是冻结 `dataclass`，把 V3 `step()` 的位置元组改为具名结果。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_iteration` | int | - | 本次迭代索引 |
| `_objective` | torch.Tensor | - | 本轮已经评估的 detached 总目标 |
| `_metrics_by_case` | tuple[tuple[float, ...], ...] | - | 逐工况展示指标 |
| `_fe_results` | tuple[`StaticResult`, ...] | - | 按工况排序的求解结果 |
| `_sensitivities` | Mapping[`DesignKey`, torch.Tensor] | - | 按设计变量块切分的灵敏度 |
| `_changes` | Mapping[`DesignKey`, torch.Tensor] | - | updater 已提交的设计增量 |
| `_phase_times` | Mapping[str, float] | - | 各阶段耗时 |

### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结结果仅保存构造状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `iteration` | int | 只读 | 内部维护 | 返回迭代索引 |
| `objective` | torch.Tensor | 只读 | 内部维护 | 返回目标 Tensor |
| `metrics_by_case` | tuple[tuple[float, ...], ...] | 只读 | 内部维护 | 返回逐工况指标 |
| `fe_results` | tuple[`StaticResult`, ...] | 只读 | 内部维护 | 返回 FEA 结果 |
| `sensitivities` | Mapping[`DesignKey`, torch.Tensor] | 只读 | 内部维护 | 返回灵敏度只读视图 |
| `changes` | Mapping[`DesignKey`, torch.Tensor] | 只读 | 内部维护 | 返回变化只读视图 |
| `phase_times` | Mapping[str, float] | 只读 | 内部维护 | 返回耗时只读视图 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 结果通过 property 读取 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结结果不定义内部辅助函数 |

## 14.2 `Controller`

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_params_factory` | Callable[[], `Params`] | - | 问题参数工厂 |
| `_solver_factory` | Callable[[], `Solver`] | - | 求解器工厂 |
| `_objective_factory` | Callable[[], `ObjectiveFunction`] | - | 顶层目标工厂 |
| `_sensitivity_factory` | Callable[[], `SensitivityAnalyzer`] | `SensitivityAnalyzer` | 隐式灵敏度分析器工厂 |
| `_updaters_factory` | Callable[[], `Updaters`] | - | updater 集合工厂 |
| `_result_root` | pathlib.Path | `Path(".results")` | 运行结果根目录 |
| `_optimization_name` | str | `"untitled"` | 任务名称 |
| `_device` | str | `"cpu"` | 优化计算设备 |
| `_maximum_iterations` | int | `100` | 外层迭代上限 |
| `_checkpoint_interval` | int | `1` | checkpoint 间隔 |
| `_worker_restart_interval` | int | `20` | 标准模式子进程完成多少轮后请求监督器续跑；小于等于 0 表示运行到终止条件 |
| `_debug` | bool | False | 调试运行模式 |
| `_data_queue` | object 或 None | None | 向 UI/父进程发送结构化进度的队列 |
| `_stop_event` | object 或 None | None | 任务运行器提供的跨进程停止事件 |

### 运行时属性（`__init__()` 声明，生命周期方法填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_params` | `Params` 或 None | None | 已初始化问题参数 |
| `_solver` | `Solver` 或 None | None | 已初始化求解器 |
| `_objective` | `ObjectiveFunction` 或 None | None | 已初始化顶层目标 |
| `_sensitivity` | `SensitivityAnalyzer` 或 None | None | 已绑定目标、Registry 和试探模型入口的灵敏度分析器 |
| `_registry` | `DesignRegistry` 或 None | None | 已冻结设计变量注册表 |
| `_updaters` | `Updaters` 或 None | None | 已绑定 updater 集合 |
| `_history` | `History` 或 None | None | 当前运行历史 |
| `_result_path` | pathlib.Path 或 None | None | 本次运行目录 |
| `_worker_pool` | object 或 None | None | 求解 worker 池 |
| `_torchfea_FEAController` | dict[int, `torchfea.FEAController`] | `{}` | 按工况保存由当前 Assembly 和 Solver 组合成的 TorchFEA 控制器 |
| `_stop_requested` | bool | False | 循环停止请求 |
| `_restart_requested` | bool | False | 当前子进程到达资源回收轮次的续跑请求 |
| `_initialized` | bool | False | 一次性初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `params_factory` | Callable[[], `Params`] | 只读 | 内部维护 | 返回参数工厂 |
| `solver_factory` | Callable[[], `Solver`] | 只读 | 内部维护 | 返回求解器工厂 |
| `objective_factory` | Callable[[], `ObjectiveFunction`] | 只读 | 内部维护 | 返回目标工厂 |
| `sensitivity_factory` | Callable[[], `SensitivityAnalyzer`] | 只读 | 内部维护 | 返回灵敏度分析器工厂 |
| `updaters_factory` | Callable[[], `Updaters`] | 只读 | 内部维护 | 返回 updater 工厂 |
| `result_root` | pathlib.Path | 只读 | 内部维护 | 返回结果根目录 |
| `optimization_name` | str | 只读 | 内部维护 | 返回任务名称 |
| `device` | str | 只读 | 内部维护 | 返回优化设备 |
| `maximum_iterations` | int | 只读 | 内部维护 | 返回外层迭代上限 |
| `checkpoint_interval` | int | 只读 | 内部维护 | 返回 checkpoint 间隔 |
| `worker_restart_interval` | int | 只读 | 内部维护 | 返回标准模式子进程资源回收间隔 |
| `debug` | bool | 只读 | 内部维护 | 返回调试模式 |
| `data_queue` | object 或 None | 只读 | 内部维护 | 返回进度队列 |
| `stop_event` | object 或 None | 只读 | 内部维护 | 返回跨进程停止事件 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `start_optimization(main_file_path)` | None | - | 创建新运行目录、初始化对象并从 iteration 0 进入循环 |
| `restart_optimization(result_path, target_iteration)` | None | - | 初始化对象、恢复 checkpoint 并从下一 iteration 进入循环 |
| `initialize_path(main_file_path)` | None | - | 建立结果、日志、缓存、脚本和 worker 输出目录并复制任务源码 |
| `step(iteration)` | `StepResult` | - | 完成一个外层迭代的模型、求解、目标、灵敏度和 updater 提交 |
| `build_fea_controllers()` | None | - | 用逐工况 Assembly 创建 `FEAController`，再由 Solver 创建并挂接逐工况静力求解器 |
| `get_fea_controllers()` | Mapping[int, `torchfea.FEAController`] | - | 读取已经建立的逐工况 TorchFEA 控制器 |
| `get_params()` | `Params` | - | 读取已初始化参数对象 |
| `get_assembly()` | `torchfea.Assembly` | - | 读取当前完整 Assembly |
| `update_trial_models(design_delta)` | None | - | 按 geometry/material → 工况副本 → load 的顺序把试探增量写入模型，供目标求值、灵敏度分析和梯度检查复用 |
| `get_history()` | `History` | - | 读取当前 History |
| `request_stop()` | None | - | 设置本次 step 完成后的停止请求 |
| `change_device(device)` | None | - | 迁移已建立的 Tensor 状态并更新后续 worker 设备配置 |
| `initialize()` | None | `Initializable` | 创建并连接 Params、Solver、Objective、SensitivityAnalyzer、Registry、Updaters、History 和 worker pool |
| `save(folder_path, iteration)` | None | `Persistable` | 原子保存所有可持久化对象和 checkpoint manifest |
| `load(folder_path, iteration)` | None | `Persistable` | 按 manifest 恢复对象状态并校验 schema 与任务签名 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_opt_loop(start_iteration)` | None | 调度 step、History、checkpoint、消息和停止判断 |
| `_create_runtime_objects()` | None | 调用工厂建立各运行对象 |
| `_create_worker_pool()` | None | 以 spawn 上下文建立 worker 池和设备分组 |
| `_close_worker_pool()` | None | 正常完成、停止或异常时关闭并回收 worker |
| `_clear_runtime_cache()` | None | 释放上一轮求解、CAD 和 GPU 临时缓存 |
| `_update_trial_models(design_delta)` | None | `update_trial_models()` 的内部实现：调度共享状态更新、工况副本建立和逐工况载荷试探更新 |
| `_export_iteration_results(step_result)` | pathlib.Path | 导出逐工况模型、结果、Jacobian、网格、预览和 iteration manifest，并返回本轮目录 |
| `_build_history_record(step_result)` | `HistoryRecord` | 汇总 step 结果、网格规模、变形和结果路径 |
| `_publish_progress(event, payload)` | None | 向队列发送版本化结构化事件 |
| `_should_stop(iteration, step_result)` | bool | 判断迭代上限、收敛条件、本地停止标志和跨进程停止事件 |

## 14.3 运行入口与生命周期

`initialize()` 每次运行执行一次：

```text
1. 创建 Params、Solver、ObjectiveFunction、SensitivityAnalyzer、DesignRegistry、Updaters 和 History；
2. Params.initialize() 完成三个处理器的定义与静态校验；
3. DesignRegistry.initialize(params) 收集 owner、冻结排序并建立设计增量；
4. `Solver.initialize(fea_params.get_num_load_steps())` 完成求解配置与任务分组；
5. 自动初值策略读取 registry.has_geometry_variables()；
6. ObjectiveFunction.initialize(fea_params)；
7. SensitivityAnalyzer.initialize(objective, registry, solver)；
8. Updaters.initialize(params, registry)；
9. History.initialize()；
10. 创建 worker pool，标记初始化完成。
```

`step(iteration)` 每个外层迭代执行一次：

```text
1. _clear_runtime_cache()
2. params.reinitialize(iteration)
3. params.build_assembly()
4. registry.reinitialize(iteration)
5. registry.build_design_delta()
6. update_trial_models(design_delta)
   6.1 registry.update_assembly(design_delta, categories={"geometry", "material"})
   6.2 fea.build_case_assemblies()
   6.3 registry.update_assembly(design_delta, categories={"load"})
7. case_assemblies = fea.get_case_assemblies()
8. build_fea_controllers()
   8.1 为每个 case_assembly 创建 FEAController 并设置 assembly
9. solver.reinitialize(iteration)
10. solver.build_solvers(fea_controllers) 并设置每个 FEAController.solver
11. solver.solve(fea_controllers, objective.jacobian_needed)
12. results = solver.get_results()
13. objective.reinitialize(iteration, fea_controllers, results)
14. objective.build_evaluation()
15. sensitivity.reinitialize(iteration, results)
16. sensitivity.build_sensitivities()
17. sensitivities = sensitivity.get_sensitivities()
18. updaters.reinitialize(iteration, sensitivities)
19. updaters.update()
20. changes = updaters.get_changes()
21. 返回 StepResult
```

本表是一次外层迭代顺序的唯一权威来源：[Solver](08Solver.md) 的调用示例、
[设计变量注册](10DesignRegistry.md) 的试探-提交流程和 [总览](01-04Overview.md) 的迭代图
按同一顺序执行。`solver.reinitialize(iteration)` 位于 `solver.build_solvers()` 之前，
因为初值策略和 GC 缓存必须在创建逐工况求解器前确定；`build_fea_controllers()` 只创建
`FEAController` 并设置 assembly，求解器挂接由 `solver.build_solvers()` 完成。

步骤 6.1 先更新所有工况共享的几何与材料状态；步骤 6.2 基于该状态建立互不共享可变
component 的 Assembly 副本；步骤 6.3 再把每个 `LoadValueBlock` 写入它绑定的工况副本。该顺序同时用于
完整目标重算、梯度检查和诊断求解。

`_opt_loop()` 对每个成功的 `StepResult` 先导出本轮制品，再建立并追加 `HistoryRecord`，按
`checkpoint_interval` 保存 checkpoint，发布进度事件并判断停止条件。标准模式累计完成
`worker_restart_interval` 轮后保存完整 checkpoint，发布 `restart_requested` 事件并正常退出
当前子进程；`TaskRunner` 回收进程资源并从同一结果目录的最新完整 checkpoint 启动下一段。
入口顺序为：

```text
start_optimization(main_file_path)
    → initialize_path(main_file_path)
    → initialize()
    → _opt_loop(start_iteration=0)

restart_optimization(result_path, target_iteration)
    → 绑定已有结果目录
    → initialize()
    → load(result_path, target_iteration)
    → _opt_loop(start_iteration=history.get_current_iteration() + 1)
```

运行入口用 `try/finally` 包围主循环，统一执行 `_close_worker_pool()`、日志 flush 和设备缓存
释放。debug 模式在当前进程执行任务；标准模式使用 spawn 子进程并通过结构化队列报告
`started`、`iteration_finished`、`restart_requested`、`warning`、`failed`、`stopped` 和
`finished` 事件。

## 14.4 `RuntimeEvent`

`RuntimeEvent` 是冻结 `dataclass`，是 Controller、任务子进程和 UI 之间的版本化消息。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_schema_version` | int | `1` | 事件结构版本 |
| `_event_type` | Literal["started", "iteration_finished", "restart_requested", "warning", "failed", "stopped", "finished"] | - | 稳定事件类型 |
| `_timestamp` | float | - | Unix 时间戳 |
| `_run_id` | str | - | 当前运行唯一标识 |
| `_payload` | Mapping[str, object] | `{}` | 与事件类型匹配的可序列化载荷 |

### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结消息仅保存构造状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `schema_version` | int | 只读 | 内部维护 | 返回事件结构版本 |
| `event_type` | str | 只读 | 内部维护 | 返回事件类型 |
| `timestamp` | float | 只读 | 内部维护 | 返回时间戳 |
| `run_id` | str | 只读 | 内部维护 | 返回运行标识 |
| `payload` | Mapping[str, object] | 只读 | 内部维护 | 返回载荷只读视图 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `to_dict()` | dict[str, object] | - | 生成可跨进程传输的事件数据 |
| `from_dict(data)` | `RuntimeEvent` | - | 校验版本和字段后创建事件对象 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 消息转换由外部接口完整表达 |

每种事件的载荷字段保持稳定：`started` 携带结果目录；`iteration_finished` 携带迭代、目标、
指标和阶段耗时；`restart_requested` 携带最新完整 checkpoint 与结果目录；`warning` 携带代码与消息；`failed` 携带异常类型、消息和 traceback；
`stopped` 携带最后完成迭代；`finished` 携带最终迭代和结果目录。

## 14.5 `TaskRunner`

`TaskRunner` 统一承接 V3 `TaskOptimization`、`start_optimization()` 和
`debug_optimization()` 的任务装载、进程隔离、异常传播和退出码语义。UI 的
`TaskLauncher` 负责启动 Python 任务；生成任务内部由 `TaskRunner` 建立并运行 Controller。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_controller_factory` | Callable[[], `Controller`] | - | 当前任务的 Controller 工厂 |
| `_main_file_path` | pathlib.Path | - | 任务定义源码路径 |
| `_restart_path` | pathlib.Path 或 None | None | 继续计算使用的结果目录 |
| `_target_iteration` | int 或 None | None | 继续计算加载的 checkpoint |
| `_event_queue` | object 或 None | None | 可选结构化事件队列 |
| `_worker_restart_interval` | int | `20` | 单个子进程连续执行的最大迭代数 |

### 运行时属性（`__init__()` 声明，任务运行时填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_process` | multiprocessing.Process 或 None | None | 标准模式任务子进程 |
| `_exit_code` | int 或 None | None | 最近任务退出码 |
| `_result_path` | pathlib.Path 或 None | None | Controller 建立的结果目录 |
| `_stop_event` | multiprocessing.Event 或 None | None | 标准模式的跨进程停止信号 |
| `_restart_count` | int | `0` | 当前任务已完成的受控子进程续跑次数 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `controller_factory` | Callable[[], `Controller`] | 只读 | 内部维护 | 返回 Controller 工厂 |
| `main_file_path` | pathlib.Path | 只读 | 内部维护 | 返回任务文件路径 |
| `restart_path` | pathlib.Path 或 None | 只读 | 内部维护 | 返回继续计算目录 |
| `target_iteration` | int 或 None | 只读 | 内部维护 | 返回目标 checkpoint |
| `worker_restart_interval` | int | 只读 | 内部维护 | 返回子进程资源回收间隔 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `start()` | None | - | 使用 spawn 上下文启动监督循环并保存当前任务进程引用 |
| `run_debug()` | int | - | 在当前进程执行同一任务入口并返回退出码 |
| `request_stop()` | None | - | 向运行中的 Controller 发送停止请求 |
| `wait(timeout=None)` | int | - | 等待任务完成、回收进程并返回退出码 |
| `get_result_path()` | pathlib.Path | - | 读取任务已经建立的结果目录 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_run_task()` | int | 创建 Controller，选择新建/重启入口并把终态转换为退出码 |
| `_run_supervisor()` | int | 循环启动任务子进程；收到受控续跑状态后读取最新完整 checkpoint 并启动下一段 |
| `_publish_failure(error)` | None | 发送结构化失败事件并写入 traceback 日志 |
| `_configure_child_environment()` | None | 设置线程数、日志、设备可见性和工作目录 |

退出码约定为：`0` 正常完成，`2` 用户停止，`1` 定义、初始化、求解或保存失败，`75` 表示
完整 checkpoint 已写入且监督器应在同一结果目录续跑。监督器只对 `75` 执行自动续跑；
失败状态保留错误并结束任务。debug 模式在当前进程连续运行并保留原始 traceback。

## 14.6 日志、历史加载与梯度检查工具

运行工具采用无状态函数，接口如下：

| 函数 | 返回值 | 作用 |
|---|---|---|
| `configure_logging(log_path, level="INFO", console=True)` | None | 配置 UTF-8 文件 handler、可选终端 handler、统一时间/级别格式和重复 handler 去重 |
| `load_controller(result_path, iteration=None)` | `Controller` | 读取 checkpoint manifest 中的任务文件与类路径，初始化对象并加载指定或最新完整迭代 |
| `check_gradients(controller, options)` | `GradientCheckReport` | 对抽样设计变量比较 autograd 梯度与中心差分并返回结构化报告 |

### 14.6.1 `GradientCheckOptions`

`GradientCheckOptions` 是冻结 `dataclass`。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_sample_count` | int | `16` | 抽样变量数量 |
| `_absolute_step` | float | `1e-6` | 中心差分绝对步长 |
| `_relative_step` | float | `1e-4` | 按参数尺度追加的相对步长 |
| `_absolute_tolerance` | float | `1e-5` | 绝对误差容差 |
| `_relative_tolerance` | float | `1e-3` | 相对误差容差 |
| `_seed` | int | `0` | 稳定抽样随机种子 |
| `_design_keys` | tuple[`DesignKey`, ...] 或 None | None | 可选变量块过滤器 |
| `_keep_artifacts` | bool | False | 是否保留每次试探求值的诊断文件 |

#### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结配置仅保存构造状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `sample_count`、`seed` | int | 只读 | 内部维护 | 返回抽样规模和种子 |
| `absolute_step`、`relative_step` | float | 只读 | 内部维护 | 返回差分步长配置 |
| `absolute_tolerance`、`relative_tolerance` | float | 只读 | 内部维护 | 返回误差容差 |
| `design_keys` | tuple[`DesignKey`, ...] 或 None | 只读 | 内部维护 | 返回变量块过滤器 |
| `keep_artifacts` | bool | 只读 | 内部维护 | 返回诊断文件策略 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 配置通过 property 读取 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结配置不定义辅助函数 |

### 14.6.2 `GradientCheckEntry`

`GradientCheckEntry` 是冻结 `dataclass`，记录一个抽样变量的校验结果。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_design_key` | `DesignKey` | - | 变量块标识 |
| `_local_index` | int | - | 变量块内展平索引 |
| `_analytic_gradient` | float | - | autograd 梯度 |
| `_numerical_gradient` | float | - | 中心差分梯度 |
| `_absolute_error` | float | - | 绝对误差 |
| `_relative_error` | float | - | 对称相对误差 |
| `_passed` | bool | - | 是否满足绝对或相对容差 |

#### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结记录仅保存构造状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `design_key` | `DesignKey` | 只读 | 内部维护 | 返回变量块标识 |
| `local_index` | int | 只读 | 内部维护 | 返回块内索引 |
| `analytic_gradient`、`numerical_gradient` | float | 只读 | 内部维护 | 返回两种梯度 |
| `absolute_error`、`relative_error` | float | 只读 | 内部维护 | 返回两种误差 |
| `passed` | bool | 只读 | 内部维护 | 返回校验状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 记录通过 property 读取 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结记录不定义辅助函数 |

### 14.6.3 `GradientCheckReport`

`GradientCheckReport` 是冻结 `dataclass`。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_entries` | tuple[`GradientCheckEntry`, ...] | - | 按 DesignKey 和局部索引排序的校验记录 |
| `_passed` | bool | - | 全部记录的汇总状态 |
| `_maximum_absolute_error` | float | - | 最大绝对误差 |
| `_maximum_relative_error` | float | - | 最大相对误差 |

#### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结报告仅保存构造状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `entries` | tuple[`GradientCheckEntry`, ...] | 只读 | 内部维护 | 返回逐变量记录 |
| `passed` | bool | 只读 | 内部维护 | 返回汇总状态 |
| `maximum_absolute_error` | float | 只读 | 内部维护 | 返回最大绝对误差 |
| `maximum_relative_error` | float | 只读 | 内部维护 | 返回最大相对误差 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 报告通过 property 读取 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结报告不定义辅助函数 |

中心差分的每次目标求值都通过 `DesignRegistry` 的试探更新事务执行并恢复基准状态；相同
抽样与种子产生稳定报告。`load_controller()` 只选择 manifest 标记为完整的 checkpoint，
并验证任务签名、schema 版本、依赖版本和设计变量签名后恢复运行对象。

## 14.7 checkpoint 与重启状态机

本节定义标准模式（受控续跑）的完整规则。debug 模式不写 checkpoint 的续跑标记，只在
当前进程内连续运行。

### 14.7.1 checkpoint 内容与完整性

一次 checkpoint 由 `Controller.save(folder_path, iteration)` 写入 `state/iter_<n>/`，
包含全部 `Persistable` 对象的状态：`Params`（含 `GeometryParams`、`MaterialsParams`、
`FEAParams` 与已提交的 `LoadStep` 值）、`Solver`（配置、工况分组、可复用 GC）、
`DesignRegistry`（key、区间、形状与已提交参数）、`Updaters`（优化器记忆与步长）、
`ObjectiveFunction`（Jacobian 请求与指标）和 `History`。

完整性判定只有一条规则：`state/iter_<n>/manifest.json` 存在、`complete=true`，且
`manifest.json` 引用的全部文件都已落盘。所有文件先写临时文件再原子重命名，
`manifest.json` 最后写入，因此 manifest 存在即代表本次 checkpoint 完整。

### 14.7.2 manifest 字段

| 字段 | 含义 |
|---|---|
| `schema_version` | checkpoint 结构版本，当前为 `2` |
| `iteration` | 本次 checkpoint 对应的迭代 |
| `complete` | 固定为 `true`；不完整状态不写 manifest |
| `main_file_path` | 任务定义源码路径 |
| `controller_class` | 任务模块中的 Controller 类路径 |
| `task_signature` | 任务文件内容摘要与依赖版本摘要 |
| `design_signature` | 设计变量块 key、形状与顺序摘要 |
| `result_path` | 本轮制品目录 |
| `files` | 对象名到状态文件相对路径的映射 |

### 14.7.3 状态机与退出码

| 退出码 | 含义 | `TaskRunner` 的动作 |
|---|---|---|
| `0` | 达到终止条件正常完成 | 结束任务，返回结果目录 |
| `2` | 用户停止（`request_stop()` 或停止事件） | 结束任务，保留已有 checkpoint |
| `1` | 定义、初始化、求解或保存失败 | 结束任务，保留错误与 traceback |
| `75` | 已写入完整 checkpoint，请求监督器续跑 | 读取最新完整 checkpoint，在同一结果目录启动下一段子进程 |

`Controller` 每完成一轮 `step()` 时，若 `iteration % checkpoint_interval == 0` 则写入
checkpoint；当连续完成的迭代数达到 `worker_restart_interval`（且该值大于 `0`）时，
`Controller` 写入完整 checkpoint、发布 `restart_requested` 事件并返回 `75`。
`TaskRunner._run_supervisor()` 是唯一解释 `75` 的一方。

### 14.7.4 崩溃与恢复规则

| 情况 | 规则 |
|---|---|
| 子进程被 SIGKILL、OOM 或被强制终止 | 视为失败（退出码 `1` 语义）；监督器不自动续跑，任务结束并保留已有完整 checkpoint |
| 子进程在写 checkpoint 中途退出 | 该次 checkpoint 没有 manifest，视为不存在；恢复时回退到最近一个完整 checkpoint |
| `checkpoint_interval > 1` | 恢复时按 14.7.1 的完整性规则向前查找最近一个完整 checkpoint |
| 续跑的起始迭代 | `load()` 恢复后从 `history.get_current_iteration() + 1` 继续；同一迭代不会重复求解 |
| schema、任务签名或设计变量签名不一致 | `load()` 抛出装载错误并结束任务，不静默续跑 |
| 续跑次数上限 | `TaskRunner._restart_count` 与 manifest 中的 `iteration` 一起记录；达到 `Controller.maximum_iterations` 时正常结束，不因续跑重置 |

`History.add_record()` 与 checkpoint 写入在同一轮内完成：先写制品，再追加记录，最后写
checkpoint。因此"记录存在但制品缺失"只在崩溃场景出现，恢复时以 checkpoint 的
`iteration` 为唯一进度依据。
