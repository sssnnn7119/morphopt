# 12. UI 展示层

返回 [设计导览](../README.md)。

## 组合关系

源码目录：`ui/` 与 `ui/widgets/`。展示层拥有 Qt 生命周期、信号连接、控件状态与绘制；业务变更通过 `ProblemDefinition` 方法完成，文件和进程操作通过应用服务完成。

```text
MainWindow
 ├── Workbench       [优化定义]
 │    ├── ModelTree
 │    ├── editor stack
 │    ├── PreviewViewer
 │    └── generated-code view
 └── ObserverPanel   [优化观察]
      ├── ObserverControls
      ├── MetricsPage
      ├── UpdatableStructurePage
      └── DeformationCasePage*
```

## 窗口与主页面

| 类 | 关键公开面 | 责任 |
|---|---|---|
| `MainWindow` | `current_problem`、`open_scheme()`、`open_morph()`、`export_morph()`、`export_run_py()`、`set_problem()`、`goto_observer()`、`show_definition()` | 应用入口，切换定义与观察页面。 |
| `Workbench` | `problem`、`reload()`、`refresh_code()`、`set_problem()`、`set_message()` | 编辑单个问题树、同步预览和生成代码。 |
| `ObserverPanel` | `ensure_loaded()`、`show_iteration()`、`reset()` | 在结果目录中切换迭代与结果视图。 |
| `ObserverControls` | `set_definition()`、`is_running()` | 选择运行源、启动/继续/停止子进程、采集输出。 |

`MainWindow` 持有当前 `ProblemDefinition` 并将它传给 Workbench 或 Observer。窗口级语言切换经 `LanguageSelector` 广播到页面；`i18n.py` 保存翻译表与控件包装。

## 结构与属性编辑控件

| 组件 | 责任 |
|---|---|
| `ModelTree` | 将问题树投影为可编辑树形菜单；上下文操作调用 `ProblemDefinition` 的 add/clone/move/remove/rename 方法。 |
| `PropertyEditor` | 根据 schema 创建字段控件、选择引用并保存字段。 |
| `ParamForm` | 通用 schema 字段表单。 |
| `TorchFEAModelEditor` | 选择/监控 `.npz` 目录，读取 `TorchFEAModelSummary`，编辑导入 Part。 |
| `StepMatrix` | 编辑 `StepsNode` 的步数与数值矩阵。 |
| `SolverEditor` | 编辑求解器进程、设备和任务表。 |
| `UpdaterEditor` | 编辑多个几何/材料更新器、各自目标、设备和局部目标/约束配置。 |
| `ObjectiveEditor` | 编辑 Jacobian 接口选择、目标代码、指标代码和模板片段。 |
| `CodeEditor` | Python 高亮、缩进、完成和片段插入。 |
| `TemplateInsertDialog` | 填充并验证一个 `CodeSnippet` 的参数。 |

`PropertyEditor` 与专用编辑器都通过领域对象的公开变换方法执行重命名和引用修改；`Workbench._on_any_change()` 负责一次变更后的树、预览、代码与标题刷新。

## 定义预览：`PreviewViewer`

源码：`widgets/viewer.py`。它从当前 `ProblemDefinition` 构建 PyVista 场景：导入 TorchFEA 模型的 Part/instances、形状曲面、参考点、载荷、边界集合和接触相关对象。`_apply_instance_pose()` 对每一个 instance 应用六维位姿；`_assembly_for_problem()` 组合当前问题所需的 Assembly 视图；`_draw_boundary_parts()` 展示每个边界 Part 的曲面。

预览的输入是定义树和导入模型摘要，属于编辑时可视化。网格生成、求解和优化结果读取由运行时与观察页承担。

## 优化结果展示

源码：`widgets/observation_pages.py`。

| 页面 | 数据源与责任 |
|---|---|
| `MetricsPage` | 从 History 读取目标、指标、耗时、网格规模和位移，绘制曲线和表格。 |
| `UpdatableStructurePage` | 从指定迭代装载 Params 状态；枚举 `ProtocalUpdatable` 接口，并按 `Part: <name>`、`Material: <name>` 选择展示。边界 Part 显示其曲面，SIMP 材料显示密度场。 |
| `DeformationCasePage` | 从 FEA 结果读取一个载荷步的变形网格。 |
| `PlotViewport` | 管理 Matplotlib/PyVista 图形部件的重建。 |

观察页每次滑动迭代都会调用 `ResultSession.load_iteration()` 并重建选中的可更新接口视图。可更新结构展示的选择项来自设计接口，因此 Part 曲面和材料密度场各自以对应的更新目标呈现。

## 展示层规则

1. Widget 不保存第二份业务真相；当前树只存在于 `ProblemDefinition`。
2. Qt 信号只发起领域变更或应用服务调用；重命名与引用同步集中在领域模型。
3. 定义预览、优化结构展示和变形结果展示各自使用明确数据源与刷新时机。
4. PyVista 对象由所属页面创建、更新和释放，防止跨页面复用已关闭的绘制资源。
