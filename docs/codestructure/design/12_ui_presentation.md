# 12. UI 展示层

返回 [设计导览](../README.md)。

## 组合关系

源码目录：`ui/` 与 `ui/widgets/`。展示层拥有 Qt 生命周期、信号连接、控件状态与绘制；业务变更通过 `ProblemDefinition` 方法完成，文件和进程操作通过应用服务完成。运行来源与轮询状态只有 `OptimizationRunSession` 一份，结果数据只有 `ResultSession` 一份。

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
| `MainWindow` | `current_problem`、`quickstart()`、`open_morph()`、`export_morph()`、`export_run_py()`、`set_problem()`、`goto_observer()`、`show_definition()` | 应用入口，切换定义与观察页面。 |
| `Workbench` | `problem`、`reload()`、`refresh_code()`、`set_problem()`、`set_message()` | 编辑单个问题树、同步预览和生成代码。 |
| `ObserverPanel` | `ensure_loaded()`、`show_iteration()`、`reset()` | 在结果目录中切换迭代与结果视图。 |
| `ObserverControls` | `set_definition()`、`is_running()` | 选择运行源、启动/继续/停止子进程、采集输出。 |

`MainWindow` 持有当前 `ProblemDefinition` 并将它传给 Workbench 或 Observer。窗口级语言切换经 `LanguageSelector` 广播到页面；`i18n.py` 查询独立 JSON 资源表并通知订阅者；语言控件和设置持久化位于 `widgets/language_selector.py`。

## 结构与属性编辑控件

| 组件 | 责任 |
|---|---|
| `ModelTree` | 渲染 `DefinitionNavigation` 投影；上下文菜单调用共用 `DefinitionActions`。 |
| `DefinitionManagerEditor` | 显示被选中接口及其子项；与树共用操作入口。 |
| `EditorPages` | 注册并绑定 `EditorRoute` 对应的 Qt 编辑页。 |
| `PropertyEditor` | 节点标题、名称与动作；字段交给共用 `ParamForm`。 |
| `ParamForm` | 节点和参数字典共用的 schema 表单；直接绑定来源，按结构变化重建。 |
| `TorchFEAModelEditor` | 选择/监控 `.npz` 目录，读取 `TorchFEAModelSummary`，编辑导入 Part。 |
| `StepMatrix` | 显示 `LoadCaseSession` 的工况矩阵，提交单元格/行操作。 |
| `SolverEditor` | 显示设备和任务表；任务分组转换由 `SolverTasks` 处理。 |
| `UpdaterEditor` | 渲染 `UpdaterSection`；目标、罚函数、对称约束共用有序项管理器。 |
| `ObjectiveEditor` | 编辑 Jacobian 接口选择、目标代码、指标代码和模板片段。 |
| `CodeEditor` | Python 高亮、缩进、完成和片段插入。 |
| `HelperCodeEditor` | 独立辅助代码编辑页；通过 `HelperCodeSession` 保存与校验。 |
| `TemplateInsertDialog` | 填充并验证一个 `CodeSnippet` 的参数。 |

`PropertyEditor` 与专用编辑器都通过领域对象的公开变换方法执行重命名和引用修改；`Workbench._on_any_change()` 负责一次变更后的树、预览、代码与标题刷新。

## 定义预览：`PreviewViewer`

源码入口：`widgets/viewer.py` 负责视图、Part 和工况选择；`visualization/geometry.py`
通过 Part/Surface visitor 生成 `PreviewScene`，`visualization/loads.py` 生成载荷图元，
`widgets/preview_renderer.py` 负责 PyVista actor 的创建与清理。各 Part 的 adapter
分别处理曲面、结构化 Box、CAD、INP 和导入 TorchFEA 模型；实例位姿在几何准备阶段应用。

预览的输入是定义树和导入模型摘要，属于编辑时可视化。网格生成、求解和优化结果读取由运行时与观察页承担。

## 优化结果展示

源码：`widgets/observation_pages.py`。

| 页面 | 数据源与责任 |
|---|---|
| `MetricsPage` | 渲染 `presentation/history.py` 生成的目标、指标、耗时、网格规模和位移表格，以及目标曲线。 |
| `UpdatableStructurePage` | 从指定迭代装载 Params 状态；枚举 `ProtocalUpdatable` 接口，并按 `Part: <name>`、`Material: <name>` 选择展示。边界 Part 显示其曲面，SIMP 材料显示密度场。 |
| `DeformationCasePage` | 从 FEA 结果读取一个载荷步的变形网格。 |
| `PlotViewport` | 管理 Matplotlib/PyVista 图形部件的重建。 |

观察页每次滑动迭代都会调用 `ResultSession.load_iteration()` 并重建选中的可更新接口视图。可更新结构展示的选择项来自设计接口，因此 Part 曲面和材料密度场各自以对应的更新目标呈现。

## 展示层规则

1. Widget 不保存第二份业务真相；当前树只存在于 `ProblemDefinition`。
2. Qt 信号只发起领域变更或应用服务调用；重命名与引用同步集中在领域模型。
3. 定义预览、优化结构展示和变形结果展示各自使用明确数据源与刷新时机。
4. PyVista 对象由所属页面创建、更新和释放，防止跨页面复用已关闭的绘制资源。
