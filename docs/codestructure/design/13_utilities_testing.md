# 13. 工具、测试与变更准则

返回 [设计导览](../README.md)。

## 用户脚本与示例

`examples/` 是公开组合 API 的可运行说明：

| 文件 | 展示的组合 |
|---|---|
| `bendingactuator.py` | 边界 Part、曲面、压力/边界条件、形状更新器和目标函数。 |
| `gripper.py` | 多 Part/多 instance 的几何声明、载荷和材料组合。 |

示例从顶层 `morphopt` 导入 `Params`、集合、接口和运行对象，再从 `morphopt.shapeopt` 或 `morphopt.simp` 导入对应扩展。每个示例都定义 `ThisController`，可直接由 `start_optimization()`、`debug_optimization()` 或 UI 生成的运行器加载。

## 灵敏度检查

源码：`utils/gradient_check.py`；顶层导出为 `morphopt.check_gradients`。

| 函数 | 职责 |
|---|---|
| `_run_once(controller, fe_template, design_vars)` | 深复制已建立 FEA 模板，写入一组试探设计变量并计算目标。 |
| `_central_difference(...)` | 对选中的变量计算中心差分导数。 |
| `_sample_ids_by_gradient(...)` | 优先选择绝对值较大的自动微分梯度位置。 |
| `check_gradients(controller, N_GEOM_CHECK=10, N_MAT_CHECK=10, MIN_GRAD_ABS=1e-6, FD_EPS=1e-2)` | 初始化问题，分别比较 geometry 和 materials 的 AD 与有限差分梯度，并输出误差表。 |

检查器使用同一份 `Params.modify_assembly()` 与 `ObjectiveFunction` 计算路径，适合验证新 `ProtocalUpdatable` 实现中变量顺序、投影和灵敏度变量的一致性。它在结束时关闭 Controller 所有进程池。

## 历史读取与重启诊断

源码：`utils/history_read.py`；顶层导出为 `morphopt.get_controller`。

`get_controller(path_result, iteration=None)` 从结果目录的 `scripts/MAIN_SCRIPT_FOR_RESTART.py` 动态导入 `ThisController`，创建实例并调用其 `_load_history()`。它提供面向分析与 UI 的已完成/中断优化读取入口；返回 Controller 后可读取 History、Params 状态和结果文件。

## 日志与包入口

`morphopt.__init__` 在 Linux 上配置 `MKL_THREADING_LAYER=GNU`，并提供 `enable_logging(level, log_file, file_log_level)`。日志工具负责 MorphOpt 包级 logger 的控制台/文件 handler 配置。`opt_runner.py` 与 `taskoptmization.py` 负责运行进程边界，详见 [02 运行时内核](02_runtime.md)。

UI 入口是 `morphopt-ui` 控制台脚本，落在 `ui/__main__.py`、`ui/app.py` 与 `ui/launcher.py`；它们创建 Qt application 并显示 `MainWindow`。

## 测试职责

当前自动化测试位于 `tests/`：

| 文件 | 覆盖目标 |
|---|---|
| `tests/optcore/test_objfunc.py` | 多载荷步目标值与灵敏度基础行为。 |
| `tests/optcore/test_solver.py` | Solver 生命周期、任务配置和求解结果路径。 |
| `tests/ui/test_application.py` | `.morph`、模板、应用会话、领域引用和代码生成的集成行为。 |

推荐执行方式：

```bash
pytest -q
```

涉及 UI 的测试使用无界面 Qt 环境；涉及网格、TorchFEA 或 GPU 的扩展测试应显式声明所需后端和设备条件。

## 变更检查表

### 新增核心接口

1. 选择对应的集合：Part 到 Geometry、FEA 对象到 FEAParams、材料到 MaterialsParams。
2. 定义构造参数、公开属性和运行时私有缓存；构造函数调用 `super().__init__()`。
3. 按需要组合 `ProtocalInitializable`、`ProtocalSavable`、`ProtocalVisualizable` 和 `ProtocalUpdatable`。
4. 通过集合 `add_interface()` 注册，并编写 `initialize()`/`reinitialize()` 使声明与迭代状态分离。
5. 为可更新接口实现完整变量顺序、灵敏度与 `modify_assembly()` 契约；为需要持久化的状态实现 `save/load`。
6. 更新对应模块设计页与 [源码清单](14_source_inventory.md)。

### 新增 UI 可编辑类型

1. 在 `ui/model/schemas.py` 定义类型 ID、字段、默认值和引用元数据。
2. 在 `ProblemDefinition` 中定义结构操作、重命名传播和序列化恢复规则。
3. 在代码生成器中实现该节点到公开 MorphOpt API 的投影。
4. 在 ModelTree、编辑路由或专用 widget 中添加展示和编辑入口。
5. 为模板给出最小有效实例，并在 `tests/ui/` 覆盖保存、加载、重命名与生成代码。

### 设备与持久化

- 局部更新器的完整对象图在 `Updaters.update()` 中成对移动到目标设备与原设备。
- 保存状态时使用 `ProtocalSavable.save_directory()` 和 `pathlog_required()` 获得命名空间目录。
- 结果目录中的脚本、Params、Updater、History、FEA 模型和结果共同构成可重启快照；新增设计状态时同步覆盖 save/load。
