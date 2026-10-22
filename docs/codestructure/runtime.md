# 运行时与进程

[代码结构导览](README.md) · [模型构建](model.md) · [设计更新](optimization.md) · [结果分析](results.md)

## 目录

<!-- docs:toc depth=1 -->

- [1 源码入口](#section-源码入口)
- [2 任务加载与进程层次](#section-任务加载与进程层次)
- [3 控制器初始化](#section-控制器初始化)
- [4 单轮计算](#section-单轮计算)
- [5 求解调度与初始解](#section-求解调度与初始解)
- [6 分段运行与恢复](#section-分段运行与恢复)
- [7 运行目录与保存责任](#section-运行目录与保存责任)
- [8 设备、资源与错误边界](#section-设备资源与错误边界)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 源码入口

| 文件 | 主要对象与职责 |
|---|---|
| [`opt_runner.py`](../../src/morphopt/opt_runner.py) | `start_optimization()`、`debug_optimization()` |
| [`taskoptmization.py`](../../src/morphopt/taskoptmization.py) | `TaskOptimization`，任务工作进程与继续计算循环 |
| [`optcore/controller.py`](../../src/morphopt/optcore/controller.py) | `Controller`，运行对象、计算主循环、保存与设备切换 |
| [`optcore/solver.py`](../../src/morphopt/optcore/solver.py) | 工况任务分配、有限元初值与求解进程调用 |
| [`optcore/objfunc.py`](../../src/morphopt/optcore/objfunc.py) | 目标计算、灵敏度与模型/结果保存 |
| [`optcore/history.py`](../../src/morphopt/optcore/history.py) | `History` 及 CSV 读写 |

<a id="section-任务加载与进程层次"></a>

## 2 任务加载与进程层次

```text
用户任务文件的 __main__ 入口
└── start_optimization()
    └── TaskOptimization.task_optimization()
        └── TaskOptimization.optmain() 工作进程
            ├── 导入任务模块的 ThisController
            ├── 创建 Controller 并初始化
            └── spawn 进程池 → Solver 的各工况任务
```

运行器使用 `spawn`，工作进程导入模块级 `ThisController`。任务启动调用位于 `if __name__ == "__main__":` 内。工作进程设置浮点精度与设备，并将工作目录切换到任务脚本目录，因此相对输入与输出路径按脚本目录解析。

新运行从用户任务文件加载类；继续运行从具体结果目录的 `scripts/MAIN_SCRIPT_FOR_RESTART.py` 加载类。`path_result` 表示已有运行目录，`target_iteration` 决定读取的保存状态。

UI 启动与停止外层任务的责任位于 `OptimizationRunSession`，见 [UI 运行会话](ui-application.md#runs)。该会话不替换内核中的计算流程。

<a id="section-控制器初始化"></a>

## 3 控制器初始化

`Controller.initialize()` 先将自身登记为 `morphopt.controller`，再创建 `Params`、`Solver(params)`、`Updater(params)` 与 `ObjectiveFunction` 四个运行对象。初始化顺序为参数、求解器、更新器、目标与历史，随后建立求解进程池。

| 调用阶段 | 内容 |
|---|---|
| 对象构造 | 保存任务配置与声明参数，建立容器 |
| `params.initialize()` | 注册模型接口，声明曲面、实例、工况和材料状态 |
| `solver.initialize()` | 准备工况任务分组 |
| `updater.initialize()` | 解析更新目标并准备对应设计对象的局部状态 |
| `objfun.initialize()`、`history.initialize()` | 准备目标与新历史 |
| `initialize_path()` | 创建具体运行目录，分配日志目录，保存脚本与依赖快照 |

声明和构建属于不同阶段。参数集合初始化不等于有限元网格已经生成；装配体在每轮 `Params.create_feamodel()` 中建立。

<a id="section-单轮计算"></a>

## 4 单轮计算

```text
Controller.opt_loop()
├── clear_cache()
├── step()
│   ├── Params / Solver / Updaters / ObjectiveFunction.reinitialize()
│   ├── Params.create_feamodel()                 → FEAController
│   ├── Solver.solve()                          → 各工况 StaticResult
│   ├── ObjectiveFunction.sensitivity_analysis()→ 分类梯度
│   ├── Updaters.update()                       → 局部变量改变量
│   ├── Updaters.update_variables()             → 写回设计对象
│   └── objective_function()                    → 本轮记录的损失
├── record_history()、print_info()
└── save()、发布完成迭代通知
```

`step()` 负责数值阶段，历史记录和保存发生在外层循环。FEA 模型与结果对应本轮已求解的状态，设计变量更新为后续计算准备。分析时按归档中同一轮的模型和解配对，不能直接用更新后的参数重建网格替换该模型。

`History` 记录 objective、metrics、分阶段耗时及网格统计。`get_metrics()` 仅提供记录量；设计梯度来自目标函数的灵敏度计算，详见[优化数据流](optimization.md#gradients)。

<a id="section-求解调度与初始解"></a>

## 5 求解调度与初始解

`Solver` 默认 `num_process=1`，GPU 列表省略或为空时使用 CPU。`Controller.optdevice` 与 `Solver.available_gpus` 分别控制优化侧和有限元侧的设备配置。

`task_step_list` 以字符串工况名称分为若干顺序执行的任务，进程池调度这些任务。未指定分组时，每个工况构成单独任务。一个任务内的后续工况可使用上一工况的解作为初值，因此分组还影响初值延续关系。

当模型中全部 Part 均为 `is_variable=False` 且未显式提供 `U_guess` 时，求解器尝试读取最近保存结果作为初值。不存在对应解时使用 `None`。形状或网格随迭代变化的 Part 应声明为可变；固定网格上的材料优化不改变这一几何标记。

`U_guess` 使用工况名称到初值数组的映射，再按任务组中的工况名称提取。工况名称与 UI 列表行号分别处理，结果文件使用工况名称命名。

<a id="section-分段运行与恢复"></a>

## 6 分段运行与恢复

`restart_per_iteration` 控制工作进程分段返回，外层任务循环取得结果目录后，从保存状态继续。工作进程返回不表示优化达到收敛。

当前 `Controller.opt_loop()` 还包含 `history.iteration == 2` 的返回分支。这是现有实现中的额外工作段退出条件，不是总迭代数或目标收敛判据。运行机制变更时应同时核对 `Controller` 与 `TaskOptimization`，不能只修改一处循环。

`Controller._load_history()` 初始化运行对象后读取指定历史、参数和更新器状态；`restart_optimization()` 随后进入计算循环。原任务文件与运行快照相互独立。改变变量布局、材料分配或工况结构后，旧状态不能直接解释为新模型的状态。

<a id="section-运行目录与保存责任"></a>

## 7 运行目录与保存责任

| 位置 | 写入责任与内容 |
|---|---|
| `scripts/` | 控制器保存任务脚本及运行依赖快照 |
| `cache/` | 模型构建过程的中间网格与几何文件 |
| `log/history_record.csv` | `History.save()` 写入历史 |
| `log/geometry/`、`log/materials/` | 参数接口保存设计状态 |
| `log/geometryupdater/`、`log/materialupdater/` | 子优化器按目标接口保存状态 |
| `log/deformation/` | 目标对象保存各工况变形图与表面文件 |
| `log/femodel&results/` | 目标对象保存每轮匹配的 FE 模型和结果 |

子目录由各对象的 `pathlog_required()` 聚合分配。`Controller.save()` 先保存参数、求解器、更新器及本轮有限元模型和结果，最后写入历史记录；历史中的完成轮次表示相应归档已保存。分析会话只消费已完成的归档；模型配对、独立求解和导出约定见[结果分析与导出](results.md)。

<a id="section-设备资源与错误边界"></a>

## 8 设备、资源与错误边界

控制器承担对象设备切换与迭代间缓存清理，子优化器管理自身局部问题的 Tensor 与优化状态。有限元进程接收独立的模型副本，避免共享可修改的求解状态。

工作进程返回前关闭对应进程池；UI 停止操作由运行会话处理外层进程组。错误日志、工作进程退出和结果是否完整保存是不同状态，恢复计算依据完整归档，不仅依据进程退出码或某个文件是否存在。
