# MorphOpt V4 Params、Controller 与主循环

本文件定义 `Params`、`Controller` 和优化主循环。运行记录由独立的
[`History`](15History.md) 文档定义。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文定义问题级运行时对象和优化主循环：`Params` 持有 `GeometryParams`、`MaterialsParams`
与 `FEAParams`，聚合三大参数处理器的定义并生成当前 `Assembly`。`Assembly` 是 `Params`
保存的运行时模型，不是与三大 Params 并列的管理器；`FEAParams` 创建的 component 直接写入
该 Assembly。`Controller` 将加工完成的 Assembly 交给 Solver，管理一次性初始化、单步迭代、
循环调度、状态保存和重启。

### 目录

- [13. Params](#13-params)
- [14. Controller](#14-controller)
  - [14.1 运行入口顺序](#141-运行入口顺序)
- [`step()` 调用顺序](#step-调用顺序)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | Geometry、Materials、FEA、Solver、ObjectiveFunction、DesignRegistry 和 Updaters 定义 |
| 输出 | 当前 Assembly、StaticResult、优化迭代状态、目标/梯度/更新结果和结果路径 |
| 主要读者 | Controller、Params、Solver、Updater、任务定义和运行结果监控实现者 |
| 关联文档 | [总览与生命周期](01-04Overview.md)、[FEA 组件](07Fea.md)、[Solver](08Solver.md)、[目标函数](09Objective.md)、[Updater](11-12Updaters.md)、[History](15History.md) |

### 对象层级

| 层级 | 对象 | 关系与职责 |
|---|---|---|
| 问题级容器 | `Params` | 持有并调度三个子参数处理器，保存当前 Assembly |
| 子参数处理器 | `GeometryParams` | 生成几何 Part、Instance、ReferencePoint 和 Assembly 基础结构 |
| 子参数处理器 | `MaterialsParams` | 根据材料定义向当前 Assembly 写入材料对象 |
| 子参数处理器 | `FEAParams` | 创建 FEA component 和 load step，并将 component 写入当前 Assembly |
| 运行时模型 | `torchfea.Assembly` | 由 `Params.build_assembly()` 建立，承载几何、材料和 FEA component |
| 求解器 | `Solver` | 接收 `Params.get_assembly()`，创建静力求解上下文并返回结果 |

## 13. `Params`

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_geometry` | `GeometryParams` | 几何定义 |
| `_materials` | `MaterialsParams` | 材料定义 |
| `_feamodel` | `FEAParams` | FEA 定义 |

### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_initialized` | bool | False | 初始化状态 |
| `_torchfea_Assembly` | `torchfea.Assembly` 或 None | None | 最近一次生成的 `Assembly` |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `geometry` | `GeometryParams` | 只读 | 内部维护 | 返回几何定义 |
| `materials` | `MaterialsParams` | 只读 | 内部维护 | 返回材料定义 |
| `feamodel` | `FEAParams` | 只读 | 内部维护 | 返回 FEA 定义 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `build_assembly(iteration)` | None | - | 汇总三个子 Params 已建立的对象，保存包含材料和 FEA component 的当前 `Assembly` |
| `get_assembly()` | `torchfea.Assembly` | - | 读取已经创建的 `Assembly` |
| `export_data(filepath)` | None | - | 将用户可读数据写入指定地址 |
| `initialize()` | None | `Initializable` | 初始化三个子系统 |
| `reinitialize(iteration)` | None | `Initializable` | 刷新当前 iteration |
| `build_meshes()` | None | `Visualizable` | 建立并保存几何、材料和 FEA 预览 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经创建的几何和材料预览 |
| `save(foldpath, iteration)` | None | `Persistable` | 保存三个子系统的当前状态 |
| `load(foldpath, iteration)` | None | `Persistable` | 加载指定 iteration 的三个子系统状态 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

`build_assembly()` 的固定顺序：

~~~text
assembly = geometry.get_assembly()
    → materials.assign_materials()
    → feamodel.build_components()
    → feamodel.assign_components(assembly)
    → Params 保存 `_torchfea_Assembly`
~~~

三大 Params 由 `Params` 统一持有和调度。`Params.reinitialize(iteration)` 刷新
`GeometryParams`、`MaterialsParams` 和 `FEAParams` 的当前迭代状态，并先由
`GeometryParams.build_assembly()` 建立几何 Assembly；`build_assembly()`
只负责按顺序取得几何 Assembly、写入材料、建立 FEA component 并将 component 写入同一个
Assembly。`Params` 完成 Assembly 后，Controller 将 `Params.get_assembly()` 交给 Solver。

## 14. `Controller`

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_params` | `Params` | 模型参数 |
| `_path_result` | str | 当前结果目录 |
| `_optdevice` | str | 优化设备 |

### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_solver` | `Solver` 或 None | None | 初始化后创建的 FEA 求解器 |
| `_objfun` | `ObjectiveFunction` 或 None | None | 初始化后绑定的目标和灵敏度对象 |
| `_registry` | `DesignRegistry` 或 None | None | 初始化后完成的变量注册表 |
| `_updater` | `Updaters` 或 None | None | 初始化后完成的更新策略集合 |
| `_history` | `History` 或 None | None | 当前运行的历史记录对象 |
| `_pools` | object 或 None | None | 初始化后创建的 worker pool |
| `_iteration` | int | 0 | 当前待执行的外层迭代编号 |
| `_max_iterations` | int | - | 外层迭代上限 |
| `_stop_requested` | bool | False | 外部停止请求状态 |
| `_initialized` | bool | False | 初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `params` | `Params` | 只读 | 内部维护 | 返回模型参数 |
| `path_result` | str | 只读 | 内部维护 | 返回当前结果目录 |
| `optdevice` | str | 只读 | 内部维护 | 返回优化设备 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `start_optimization(main_filepath)` | None | - | 从 iteration 0 开始 |
| `restart_optimization(path_result, target_iteration)` | None | - | 从指定 iteration 继续优化 |
| `initialize_path(main_filepath)` | None | - | 创建当前运行的结果、日志、缓存、脚本和 worker 输出目录 |
| `get_assembly()` | `torchfea.Assembly` | - | 委托 `Params.get_assembly()` 读取当前 Assembly |
| `initialize()` | None | `Initializable` | 创建和初始化全部对象 |
| `step()` | tuple[`torch.Tensor`, float, float, float, float, float] | - | 执行一个完整的外层优化迭代并返回目标值与阶段计时 |
| `request_stop()` | None | - | 设置单次循环结束后的停止请求 |
| `save(foldpath, iteration)` | None | `Persistable` | 调度 Params、DesignRegistry、Updaters 和 History 保存状态 |
| `load(foldpath, iteration)` | None | `Persistable` | 在任务初始化后加载指定 iteration 的状态和历史 |

`Controller.initialize()` 建立一次性运行时关系：完成静态定义、运行时对象、设计变量注册、
求解器、History 和 worker pool 的连接；当前 iteration 的 Assembly、求解结果、目标、灵敏度
和 History 记录由后续 `step()` 与 `_opt_loop()` 接续处理。固定顺序为：

~~~text
1. 绑定当前 Controller 到运行时上下文；
2. Params.initialize()
   2.1 GeometryParams.initialize()
   2.2 MaterialsParams.initialize()
   2.3 FEAParams.initialize()
3. Solver.initialize(num_steps)
4. Solver.build_solver()
5. DesignRegistry.initialize(params)
   5.1 收集 geometry、material 和 FEA design block；
   5.2 finalize 并冻结变量顺序；
   5.3 各 owner.build_design_delta()；
   5.4 建立完整设计向量；
6. 若 Solver 的初值开关为自动，则根据 DesignRegistry.has_geometry_variables() 设置 GC 复用策略；
7. Updaters.initialize(params, registry)
8. ObjectiveFunction.initialize()
9. History.initialize()
10. 创建 solver worker pool；
11. 标记 Controller 已初始化。
~~~

`initialize()` 完成后，三个 Params、Solver、DesignRegistry、Updaters、ObjectiveFunction、
History 和 worker pool 均已连接；当前 iteration 仍保持为待执行状态，`step()` 按该 iteration
建立 Assembly 并产出求解结果，随后由 `_opt_loop()` 接续记录和调度。

### 14.1 运行入口顺序

两个运行入口都复用同一套初始化和循环协议；重启入口只在进入循环前增加状态恢复：

~~~text
start_optimization(main_filepath)
    → initialize()
    → initialize_path(main_filepath)
    → _opt_loop()

restart_optimization(path_result, target_iteration)
    → 设置当前结果目录
    → initialize()
    → History.load(path_result/log, target_iteration)
    → Params.load(path_result/log, target_iteration)
    → Solver.load(path_result/log, target_iteration)
    → Updaters.load(path_result/log, target_iteration)
    → _opt_loop()
~~~

`initialize()` 执行一次；`initialize_path()` 负责结果目录、日志、缓存、脚本和 worker
输出目录；`_opt_loop()` 反复调用 `step()`，并在单步完成后记录、保存、发送进度和判断
停止条件。重启入口恢复已初始化对象的持久化状态，下一次 `step()` 按恢复后的 iteration
建立当前 Assembly。

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_opt_loop()` | None | 循环执行 `step()`、记录 History、保存状态、发送进度并处理停止条件 |
| `_clear_cache()` | None | 清理 FEA 和 worker 缓存 |
| `_record_step(result)` | None | 将单步目标、指标、计时和模型统计写入 History |
| `_should_stop()` | bool | 根据最大迭代次数、收敛状态、停止请求和重启间隔判断循环状态 |

### `initialize()`、`step()` 与 `_opt_loop()` 的边界

| 方法 | 调用频率 | 建立/更新内容 | 循环控制、保存和历史 |
|---|---|---|---|
| `initialize()` | 每个进程一次 | 静态定义、运行时对象、设计变量注册、求解器和 worker pool | 交给 `_opt_loop()` 调度 |
| `step()` | 每个外层 iteration 一次 | 当前 Params、Assembly、FEA 求解、目标、灵敏度和 updater 变化 | 返回单步结果 |
| `_opt_loop()` | 每次运行一次 | 调度多个 `step()` | 记录 History、保存、发送 UI 进度、重启或停止 |

### `step()` 调用顺序

~~~text
1. 清理上一轮 FEA 临时对象；
2. `Params.reinitialize(iteration)` 刷新 Geometry、Materials 和 FEA 的当前状态；
3. `Params.build_assembly(iteration)` 按 Geometry → Materials → FEA 顺序写入当前 Assembly；
4. `Solver.reinitialize(iteration)` 准备当前求解上下文；
5. `ObjectiveFunction.reinitialize(iteration)` 绑定当前结果上下文；
6. `Solver.solve(Params.get_assembly())` 求解全部 load steps；
7. `ObjectiveFunction.compute_multistep_objective(...)` 计算当前结果目标和指标；
8. `ObjectiveFunction.compute_sensitivity(registry)` 完成一次全局灵敏度分析并按 DesignKey 切分；
9. `Updaters.reinitialize(iteration, local_gradients)` 将局部梯度送入对应 updater；
10. `Updaters.update()` 计算各 updater 的试探变化并统一提交 owner；
11. 返回当前目标值、阶段时间和 `Updaters.get_changes()` 所需的更新结果；
12. `_opt_loop()` 接收返回值并负责 History、保存和停止判断。
~~~
