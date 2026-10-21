# 12. UI 展示层

返回 [设计导览](../README.md)。

<a id="section-组合关系"></a>

## 1 组合关系

源码目录：`ui/` 与 `ui/widgets/`。展示层拥有 Qt 生命周期、信号连接、控件状态与绘制；业务变更通过 `ProblemDefinition` 方法完成，文件和进程操作通过应用服务完成。运行来源与轮询状态只有 `OptimizationRunSession` 一份，结果数据只有 `ResultSession` 一份。

```text
MainWindow
 ├── Workbench       [优化定义]
 │    ├── ModelTree
 │    ├── editor stack
 │    ├── PreviewViewer
 │    └── generated-code view
 └── 优化过程 [有任务后开放]
      ├── ObserverControls [迭代历史；后台优化和轮询持续运行]
      │    └── ObserverPanel
      │         ├── MetricsPage
      │         ├── UpdatableStructurePage
      │         └── DeformationCasePage*
      └── FiniteElementPage [与观察共用结果目录和所选迭代]
```

<a id="section-窗口与主页面"></a>

## 2 窗口与主页面

| 类 | 关键公开面 | 责任 |
|---|---|---|
| `MainWindow` | `current_problem`、`quickstart()`、`open_morph()`、`export_morph()`、`export_run_py()`、`set_problem()`、`start_optimization()`、`open_python_optimization()`、`open_optimization_result()`、`show_definition()` | 应用入口，编排定义及优化过程导航，并同步观察／有限元的目录与迭代。 |
| `Workbench` | `problem`、`reload()`、`refresh_ui()`、`refresh_coordinator`、`set_problem()`、`set_message()` | 组合编辑页和刷新组件，准备同步后的模型上下文。 |
| `ObserverPanel` | `ensure_loaded()`、`show_iteration()`、`reset()` | 在结果目录中切换迭代与结果视图。 |
| `ObserverControls` | `start_definition()`、`start_python()`、`open_result()`、`is_running()` | 消费定义页或文件菜单提供的运行源，启动/继续/停止子进程并采集输出。 |

`MainWindow` 持有当前 `ProblemDefinition` 并将它传给 Workbench 或 Observer。窗口级语言切换经 `LanguageSelector` 广播到页面；`i18n.py` 查询独立 JSON 资源表并通知订阅者；语言控件和设置持久化位于 `widgets/language_selector.py`。

<a id="section-结构与属性编辑控件"></a>

## 3 结构与属性编辑控件

| 组件 | 责任 |
|---|---|
| `ModelTree` | 渲染 `DefinitionNavigation` 投影；上下文菜单调用共用 `DefinitionActions`。 |
| `DefinitionManagerEditor` | 显示被选中部件及其子项，或载荷、辅助变量、辅助函数集合的全部卡片；与树共用增删排序入口。 |
| `CollectionHeader` / `ItemActions` | 共用集合顶部添加入口与条目右上角排序、删除控件；按钮颜色和状态来自应用主题。 |
| `EditorPages` | 注册并绑定 `EditorRoute` 对应的 Qt 编辑页，将刷新委托给活动页。 |
| `PropertyEditor` | 节点标题、名称与动作；字段交给共用 `ParamForm`。 |
| `ParamForm` | 节点和参数字典共用的 schema 表单；直接绑定来源，按结构变化重建。 |
| `StepMatrix` | 显示 `LoadCaseSession` 的工况矩阵，提交单元格/行操作。 |
| `SolverEditor` | 显示设备和任务表；任务分组转换由 `SolverTasks` 处理。 |
| `UpdaterEditor` | 渲染 `UpdaterSection`；目标、罚函数、对称约束共用有序项管理器。 |
| `ObjectiveEditor` | 编辑 Jacobian 接口选择、目标代码、指标代码和模板片段。 |
| `CodeEditor` | Python 高亮、缩进、完成和片段插入。 |
| `HelperCodeEditor` | 自由代码编辑页及嵌入集合卡片的变量/函数编辑控件；通过 `HelperCodeSession` 保存与校验。 |
| `GeneratedSourceView` | 从同步后的问题定义生成只读代码，保留滚动位置。 |
| `TemplateInsertDialog` | 填充并验证一个 `CodeSnippet` 的参数。 |

`PropertyEditor` 与专用编辑器都通过领域对象的公开变换方法执行重命名和引用修改。
所有需要刷新的组件实现 `ui/refresh.py` 中的 `Refreshable.refresh_ui(context)`。
`RefreshCoordinator` 合并携带变更节点的通知，先同步一次领域模型，再按注册顺序调用组件；
各组件接收同一个 `RefreshContext`，并保留各自的选中项、滚动位置和编辑状态。
新增、删除和排序也走这条路径；删除通知保留被删除节点，用于识别载荷或几何更新范围。
组件异常会记录完整堆栈并显示错误，其他组件仍继续刷新。

<a id="section-定义预览previewviewer"></a>

## 4 定义预览：`PreviewViewer`

源码入口：`widgets/viewer.py` 负责视图、Part 和工况选择；`visualization/geometry.py`
通过 Part/Surface visitor 生成 `PreviewScene`，`visualization/loads.py` 生成载荷图元，
`widgets/preview_renderer.py` 负责 PyVista actor 的创建与清理。各 Part 的 adapter
分别处理曲面、结构化 Box、CAD 和 INP；实例位姿在几何准备阶段应用。

预览的输入是定义树和所引用的几何文件，属于编辑时可视化。网格生成、求解和优化结果读取由运行时与观察页承担。

<a id="section-cadpart-几何导出"></a>

### 4.1 CADPart 几何导出

`DefinitionManagerEditor` 在 CADPart 卡片顶部显示“导出 STEP…”动作。`widgets/file_dialogs.py::choose_save_file()` 提供目录导航、文件名输入、STP / STEP 格式筛选和覆盖确认。用户确认保存后，应用层 `export_cad_step()` 调用 TorchFEA CAD 导出接口；界面显示完成路径或错误信息。保存操作不改变定义树和优化历史。

<a id="section-优化结果展示"></a>

## 5 优化结果展示

源码：`widgets/observation_pages.py`。

| 页面 | 数据源与责任 |
|---|---|
| `MetricsPage` | 渲染 `presentation/history.py` 生成的目标、指标、耗时、网格规模和位移表格，以及目标曲线。 |
| `UpdatableStructurePage` | 从指定迭代装载 Params 状态；枚举 `ProtocalUpdatable` 接口，并按 `Part: <name>`、`Material: <name>` 选择展示。边界 Part 显示其曲面，SIMP 材料显示密度场。 |
| `DeformationCasePage` | 从 FEA 结果读取一个载荷步的变形网格。 |
| `PlotViewport` | 管理 Matplotlib/PyVista 图形部件的重建。 |

观察页每次滑动迭代都会调用 `ResultSession.load_iteration()` 并重建选中的可更新接口视图。可更新结构展示的选择项来自设计接口，因此 Part 曲面和材料密度场各自以对应的更新目标呈现。

<a id="section-展示层规则"></a>

## 6 展示层规则

1. Widget 不保存第二份业务真相；当前树只存在于 `ProblemDefinition`。
2. Qt 信号只发起领域变更或应用服务调用；重命名与引用同步集中在领域模型。
3. 定义预览、优化结构展示和变形结果展示各自使用明确数据源与刷新时机。
4. PyVista 对象由所属页面创建、更新和释放，防止跨页面复用已关闭的绘制资源。
