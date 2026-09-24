# 02. 运行时内核

返回 [设计导览](../README.md)。

## 责任与协作

运行时位于 `src/morphopt/optcore/`。`Controller` 是唯一的迭代编排者；`Solver` 只负责 FEA 求解，`ObjectiveFunction` 只定义指标和灵敏度，`Updaters` 只协调局部设计更新，`History` 只记录可持久化的时序数据。

```text
Controller.step()
 ├─ Params.reinitialize(iteration)
 ├─ Params.create_feamodel() ───────────────────────────► torchfea.FEAController
 ├─ Solver.solve() ─────────────────────────────────────► StaticResult[]
 ├─ ObjectiveFunction.compute_multistep_objective()
 ├─ ObjectiveFunction.sensitivity_analysis(params) ─────► gradient dict
 ├─ Updaters.update(gradients) ─────────────────────────► interface updates
 ├─ record_history()
 └─ save()
```

## `Controller`

源码：`optcore/controller.py`。它不继承协议；它聚合所有顶层运行对象，并定义结果目录和设备边界。

| 类别 | 属性 |
|---|---|
| 构造参数/公开状态 | `params`, `solver`, `updater`, `objfun`, `opt_label`, `path_result_folder`, `restart_per_iteration`, `dataqueue`, `pools`, `optdevice` |
| 运行时状态 | `path_result`, `history` |
| 私有状态 | `_debug_mode` |

| 公开方法 | 职责 |
|---|---|
| `initialize_path(main_filepath=None)` | 创建本次运行目录，复制用户脚本和必要输入文件。 |
| `initialize()` | 初始化 Params、Solver、ObjectiveFunction、Updaters 和 History。 |
| `start_optimization(main_filepath=None)` | 创建目录、初始化并执行优化循环。 |
| `restart_optimization(path_result, target_iteration=None)` | 装载历史与对象状态，从指定迭代继续。 |
| `opt_loop()` | 迭代调用 `step()`，处理收敛、保存和状态推送。 |
| `step()` | 完成一轮装配、求解、目标计算、灵敏度、更新与记录。 |
| `record_history(...)` | 记录目标、耗时、网格规模、位移和附加指标。 |
| `print_info(...)` | 输出一轮计时和指标。 |
| `save()` | 保存 Params、Updaters、ObjectiveFunction、History 与 FEA 产物。 |
| `clear_cache()` | 清理当前结果目录中的中间缓存。 |
| `change_device(device, obj=None)` | 递归移动对象图中的 Tensor 到目标设备。 |

`_detach_recursive()` 与 `_change_device_recursive()` 是实现细节：前者在保存前断开计算图，后者遍历实例属性、容器和 Tensor。新增运行时对象时应将 Tensor 放在普通实例属性或容器中，便于该递归逻辑覆盖。

## `History`

源码：`optcore/history.py`；继承 `ProtocalInitializable`、`ProtocalSavable`。

| 状态 | 语义 |
|---|---|
| `data: dict[str, numpy.ndarray]` | 键到按迭代增长数组的映射。 |
| `iteration` | 最近记录的迭代号。 |

`history_objective`、`history_time`、`history_num_elements`、`history_num_nodes`、`history_deformation`、`history_metrics` 是常用键的属性视图。`append(name, value)` 接受本轮值；`save(foldpath)` 写出历史；`load(foldpath, iteration=None)` 恢复全部或截至目标迭代的数据。

## `Solver`

源码：`optcore/solver.py`；继承 `ProtocalInitializable`、`ProtocalSavable`。

| 状态 | 语义 |
|---|---|
| `params` | 当前模型参数集合，用于读取载荷步和装配信息。 |
| `num_process`、`task_index_list` | 并行求解任务配置。 |
| `_GC_pre` | 前一轮自由度解，用于下一轮 warm start。 |
| `available_gpus` | 可用于并行任务的 GPU 信息。 |

`initialize()` 建立任务配置，`reinitialize(iteration)` 依据当前参数刷新，`solve(U_guess=None)` 对每个载荷步求解并返回 `torchfea.solver.StaticResult` 列表。`_previous_solution()` 与 `_solve_FEA()` 分别封装 warm start 选择和单个 FEA 任务。

## `ObjectiveFunction`

源码：`optcore/objfunc.py`；继承 `ProtocalInitializable`、`ProtocalSavable`。

| 状态 | 语义 |
|---|---|
| `fe` | 当轮 `torchfea.FEAController`。 |
| `fe_results` | 各载荷步静力结果。 |
| `jacobian_needed` | 当前目标是否要求位移对设计的雅可比。 |

| 公开成员 | 职责 |
|---|---|
| `num_tasks` | 目标涉及的载荷步数。 |
| `get_metrics()` | 返回供 History 和 UI 展示的附加指标。 |
| `objective_function()` | 子类实现单载荷步目标。 |
| `set_step(step)` | 将当前目标上下文切换到某一载荷步。 |
| `compute_multistep_objective(fe_results, assembly)` | 汇总每个载荷步目标值。 |
| `sensitivity_analysis(params)` | 对可更新几何/材料设计值求导，返回以参数集合为键的梯度。 |
| `get_mesh_case(case)` / `plot(case)` | 提供结果网格和可视化。 |
| `save(foldpath, iteration)` | 保存本轮结果所需的目标相关状态。 |

目标函数子类只描述物理量与聚合逻辑；设计变量分块和 L-BFGS 步长策略由更新器承担。

## `BaseUpdater` 与 `Updaters`

源码：`optcore/updaters.py`。`BaseUpdater` 继承初始化、保存协议，作为一个局部优化问题的基类；具体类位于 shapeopt 或 simp。

| `BaseUpdater` 状态 | 语义 |
|---|---|
| `_interface_name`、`_target` | 目标接口的稳定引用和运行时对象。 |
| `obj_funcs`、`constraints_funcs` | 局部目标与约束列表。 |
| `optimizer` | 本地 L-BFGS 求解器。 |

`bind_target()` 绑定可更新接口，`define_objective()` 声明子问题，`add_objective_function()` 与 `add_constraints()` 注册项。`initialize()`、`reinitialize()`、`closure()`、`update_variables()`、`update()` 是具体更新器实现的生命周期钩子。

`Updaters` 聚合器保存 `params`、`updaters: dict[str, BaseUpdater]`、`_var_updaters`、`_device` 与 `_updater_defined`。它的 `define_updater()` 负责用户声明，`add_geometry_updater()`、`add_material_updater()`、`add_updater()` 完成目标校验和命名注册；`initialize()` 完成绑定；`update(gradients)` 为每个 updater 切出自身梯度并执行局部优化；`update_variables()` 将更新量写回目标。

设备策略属于 `Updaters.update()`：每个局部子问题开始前，目标对象、约束对象、梯度和相关 Tensor 整体移动到该 updater 的设备；子问题完成后回到调用前设备。该范围保证 TorchFEA 元素、节点、约束缓存和灵敏度张量在同一设备上参与运算。

`BaseUpdater.Optimizer` 是局部求解器命名空间：`BaseOpt` 保存 `closure`、自动微分梯度和回溯线搜索参数；`LBFGS` 保存有限长度的 `(S_k, Y_k, rho_k)` 记忆对，并通过 `step()` 产生局部更新。具体形状/SIMP updater 负责将各自的目标和约束封装为 closure。

`ObjectiveFunction.save()` 为每个载荷步写出变形截图与 STL，并将本轮 `FEAController` 保存为 `femodel_<iteration>`、对应 `StaticResult` 保存为 `result_<case>_iter_<iteration>.npz`。模型与结果以同一迭代号配对，供观察页读取。

## 进程入口

| 文件 | 公开对象 | 职责 |
|---|---|---|
| `opt_runner.py` | `start_optimization`, `debug_optimization` | 前者启动隔离进程，后者在当前进程执行，适合调试。 |
| `taskoptmization.py` | `TaskOptimization` | 子进程导入用户脚本中的 `ThisController`，设置 Torch 默认 dtype/device，并处理重启循环。 |

用户脚本导出 `ThisController`。UI 的运行器只传递脚本路径、结果目录和目标迭代，核心运行时保持与 Qt 进程隔离。
