# UI 展示与刷新

[代码结构导览](README.md) · [领域模型](ui-model.md) · [应用服务](ui-application.md) · [结果分析](results.md)

UI 按业务数据与显示分离的原则组织。领域对象和应用会话保存定义、引用与操作状态，展示投影准备导航、源码、资产与场景数据，控件和 renderer 管理交互及显示资源。[UI 数据流与显示分层图](architecture.md#section-业务数据展示投影与显示资源)给出各层的连接关系，本篇说明页面、刷新与渲染的具体接入方式。

## 目录

<!-- docs:toc depth=1 -->

- [1 源码入口](#section-源码入口)
- [2 窗口与页面组合](#section-窗口与页面组合)
- [3 导航投影与标题](#section-导航投影与标题)
- [4 编辑器路由与共享控件](#section-编辑器路由与共享控件)
- [5 统一变更与刷新](#refresh)
- [6 文档历史的展示接入](#section-文档历史的展示接入)
- [7 定义预览与渲染边界](#preview)
- [8 观察页的展示边界](#section-观察页的展示边界)
- [9 主题、本地化与平台资源](#section-主题本地化与平台资源)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 源码入口

| 路径 | 责任 |
|---|---|
| [`ui/app.py`](../../src/morphopt/ui/app.py)、[`mainwindow.py`](../../src/morphopt/ui/mainwindow.py) | Qt 应用和窗口级页面编排 |
| [`ui/workbench.py`](../../src/morphopt/ui/workbench.py) | 定义工作区与刷新组件组合 |
| [`ui/observe_panel.py`](../../src/morphopt/ui/observe_panel.py) | 优化观察页和运行控件 |
| [`ui/refresh.py`](../../src/morphopt/ui/refresh.py) | 刷新协议、上下文和合并调度 |
| [`ui/widgets/`](../../src/morphopt/ui/widgets) | 编辑器、树、视口、页面与对话框 |
| [`ui/presentation/`](../../src/morphopt/ui/presentation) | 导航、标题、历史表格与操作历史投影 |
| [`ui/visualization/`](../../src/morphopt/ui/visualization) | 几何、载荷与场景数据准备 |
| [`ui/theme/`](../../src/morphopt/ui/theme)、[`ui/i18n.py`](../../src/morphopt/ui/i18n.py) | 主题、语言与订阅通知 |

<a id="section-窗口与页面组合"></a>

## 2 窗口与页面组合

```text
MainWindow
├── Workbench：优化定义
│   ├── ModelTree / EditHistoryPanel
│   ├── EditorPages → 当前编辑器
│   ├── PreviewViewer → PreviewRenderer
│   └── GeneratedSourceView / AssetBrowser
└── 优化过程
    ├── ObserverControls + ObserverPanel
    │   ├── MetricsPage
    │   ├── UpdatableStructurePage
    │   └── DeformationCasePage
    └── FiniteElementPage
```

`MainWindow` 管理定义文件路径、菜单、页面切换及结果目录/迭代选择。`Workbench` 组合定义会话和编辑组件。观察页与有限元页持续保留其会话，切页不重新创建任务。

文件菜单统一提供定义、脚本、运行结果及导出入口，设置菜单管理语言与主题。开始优化按钮与分析菜单使用同一工作台校验入口。`Ctrl+S` 保存当前定义，不受结果页来源变化影响。

结果视图共享的是目录与迭代选择，不共享可修改的 FE 模型。该状态及锁定规则集中见[结果选择](results.md#selection)。

<a id="section-导航投影与标题"></a>

## 3 导航投影与标题

`DefinitionNavigation` 将领域对象投影为模型树行。`ParamsTreeNode`、`UpdaterTreeNode`、辅助代码分组等仅作为导航句柄；`UpdaterItemTreeNode` 直接关联条目配置，使排序后仍可定位原条目。

树、卡片和菜单标题通过 `presentation/labels.py` 统一生成：对象显示 `名称 [ClassName]`，类型菜单显示功能名称与类名。选择自定义类后显示实际类名。分组不附加虚构后端类名，可更新能力由节点元数据决定。

下拉框分别保存显示标题与 `itemData` 中的原始值或对象引用。显示文本不参与业务名称解析。编辑器焦点可使树静默跟随当前卡片，只有主动导航才触发页面滚动定位。

<a id="section-编辑器路由与共享控件"></a>

## 4 编辑器路由与共享控件

`application/editor_routing.py` 决定节点的编辑器类型。`EditorPages` 负责页面加入编辑栈、绑定路由和连接变更信号，工作台不为每个页面维护分散的信号路径。

| 组件 | 展示责任 |
|---|---|
| `PropertyEditor`、`ParamForm` | 节点标题和共享 schema 字段表单 |
| `DefinitionManagerEditor` | 部件及子项、载荷或辅助定义的集合卡片 |
| `CollectionHeader`、`ItemActions` | 共用添加、上移、下移与删除入口 |
| `DefinitionActions` | 树菜单与卡片共用的结构动作、对话框与通知 |
| `LoadCaseEditor`、`SolverEditor` | 具名工况卡片和任务分组表 |
| `UpdaterEditor` | 子目标、对称和罚函数的有序卡片 |
| `ObjectiveEditor` | 目标、指标与 Jacobian 选择 |
| `ModelClassSelector` | 根级配置、目标函数和具体子优化器的类选择 |
| `CodeEditor`、`HelperCodeEditor`、`CustomClassEditor` | 代码输入、方法体与辅助定义 |
| `GeneratedSourceView` | 同步定义对应的只读 Python |

`ParamForm` 直接绑定类型化节点的读写接口，或绑定由所属服务持有的参数字典，不复制出需要双向维护的第二份字段值。结构、schema 或目标变化时重建表单；普通字段更新和动态选项刷新尽量保留焦点、滚动与代码编辑历史。

参数选择和业务校验由应用服务提供。控件处理输入事件与渲染，不自行计算材料分配、更新器目标或集合名称。

<a id="refresh"></a>

## 5 统一变更与刷新

```text
字段编辑 / 树菜单 / 集合动作
  → 应用命令或 ProblemDefinition 领域操作
  → changed(node)
  → Workbench 同步与编辑快照
  → RefreshCoordinator 合并变化
  → 一个 RefreshContext
  → 各注册组件 refresh_ui(context)
```

结构操作可通过 `refresh_now(node)` 立即提交；连续字段输入通过 `request(node)` 合并。两条路径进入同一调度器。

| `RefreshContext` 内容 | 作用 |
|---|---|
| `problem` | 本轮已经同步的定义 |
| `selected` | 当前导航对象 |
| `changed_nodes` | 合并后的变更对象，包括已删除节点 |
| `full` | 未知来源触发的完整刷新 |
| `restoring` | 编辑历史恢复，保留适当视图状态 |

`RefreshCoordinator` 按注册顺序调用组件的 `Refreshable.refresh_ui()`。删除通知保留来源节点，未知来源的完整刷新请求不会被后续局部通知覆盖。组件失败记录完整异常并报告错误，其他独立组件仍继续刷新。

树、当前编辑器、生成代码和预览消费同一上下文。组件不调用其他 widget 的私有方法维持模型一致性，也不重复执行领域同步。新增组件在 `Workbench._register_refreshables()` 注册，专用编辑页通过 `EditorPages` 接入。

仅载荷或工况变化时更新载荷场景；几何、辅助表达式或其他几何相关配置变化时重建相应几何与载荷。普通刷新保留选中项、展开状态、工况和相机；替换模型或视图时再按新上下文初始化。

<a id="section-文档历史的展示接入"></a>

## 6 文档历史的展示接入

`EditHistoryPanel` 展示分支历史，通过稳定步骤 ID 请求恢复。历史内容与分支算法由 [EditHistory](ui-application.md#section-编辑历史与恢复)负责。

恢复前提交输入并取消旧刷新，恢复后统一重新绑定对象和表单。`RefreshContext.restoring` 使恢复过程保留相机、工况及适当滚动位置；不能继续引用恢复前的节点对象。

文本控件优先使用局部撤销，文档撤销处理整体定义。代码编辑器快捷键只作用于当前代码控件。延迟布局回调由所属 QObject 管理，页面销毁后不继续操作旧控件。

<a id="preview"></a>

## 7 定义预览与渲染边界

```text
ProblemDefinition + DefinitionValues
  → PreviewGeometry
      ├── PartPreviewVisitor / SurfacePreviewVisitor → PreviewScene
      └── LoadPreviewVisitor                        → LoadScene
  → PreviewRenderer → PyVista / VTK actors
```

`PartPreviewAdapter` 提供 `preview()`、`surface()` 与可选 `model_part()`，分别准备初始几何、载荷作用面和集合查询所需模型。适配器以 **PartNode 的 Python 类** 注册，按继承关系查找，不以显示字符串注册。

Boundary、Box、CAD 和 INP 各有适配器，视口不按类型堆积建模分支。`PartSetCatalog` 的集合 provider 同样按节点类注册。`PreviewGeometry.build()` 先绑定当前定义与资源，再进行集合和载荷查询。

Part 视图使用局部坐标，装配视图应用 Instance 位姿。CAD 将全部显示三角形合并为一个面网格，并将 `face_N` 编号写入单元数据；全部拓扑边合并为一个线网格。载荷和节点集查询按需从该面网格提取指定 `face_N`，不按每个拓扑面或边创建 actor。单个 Part 预览失败记录场景错误，不生成替代优化几何。

CAD 预览由 TorchFEA 重放 OCC 操作历史，再通过 OpenCASCADE 原生三角化生成显示面及拓扑边线，不调用 Gmsh 网格生成接口。边线直接引用对应面的三角化边界节点。显示面和边通过面积或长度、质心和惯性矩匹配原有 Gmsh 拓扑标识。该路径保留周期面的裁剪边界及 `face_N` 选择关系；Gmsh 继续负责建模历史和拓扑查询，有限元体网格仍由其独立生成。预览层统一将底层异常转换为 `RuntimeError`，由界面记录为对应部件的预览错误。

体网格生成前，TorchFEA 使用 OCC 拆分闭合周期面，使裁剪后的周期边界适于 Gmsh 剖分。拆分仅作用于剖分拓扑，不改变几何形状；面、边、顶点及体的网格数据按来源映射回原实体标识，因此 UI 的 `face_N`、节点集和载荷引用保持一致。

各 Part 适配器在基础网格的 `MeshItem.faces` 中提供 `MeshFaces`，记录部件、实例、显示单元分组和对应表面集合名称。`PreviewRenderer` 使用限定基础几何 actor 的 `vtkCellPicker` 识别点击单元，以单个临时 actor 高亮选中分组，并将 `FaceSelection` 交给 `PreviewViewer` 显示可复制的面名称。CAD、Box、Boundary、OffsetBoundary 和 INP 共用这一流程；载荷图元、拓扑边和选择高亮不参与拾取，鼠标拖动不触发选择。常驻面编号标签已移除。

Qt 视口通过事件过滤器获取控件局部坐标，再按实际渲染窗口尺寸转换为 VTK 像素坐标，并翻转纵轴。显示网格携带原始单元 ID，拾取结果经该 ID 映射回 `MeshFaces`，允许渲染管线调整单元顺序。剖视滑条调用 `PreviewRenderer.set_section()` 更新共享 `vtkPlane`，几何 mapper 和选择高亮共用该裁剪平面；平面移动不重建 CAD，不修改模型定义与原始网格，拾取遵循相同裁剪范围。

场景数据可以包含 PyVista 网格、标签和载荷图元，但不拥有 plotter 或 VTK actor。`PreviewRenderer` 负责 actor 的创建、替换与清理；新载荷可注册 visitor 并返回已有图元，新图元在 renderer 的分派入口扩展。

载荷符号尺寸根据场景和部件典型宽度计算，显示尺寸与物理幅值分开。标注模板由语言资源提供，包含目标实例、集合或参考点。`plot_style.py` 统一视口背景、光照、透明渲染及方向轴设置，重建场景后恢复这些配置。

<a id="section-观察页的展示边界"></a>

## 8 观察页的展示边界

`MetricsPage` 消费历史表格投影与曲线数据；`UpdatableStructurePage` 根据已载入的可更新接口展示 Part 曲面或材料场；`DeformationCasePage` 展示选定工况的变形网格。可更新对象通过自身的加载/绘图协议提供展示，不按方案名称复制分支。

结果文件读取与参数载入属于 `ResultSession`，在载入成功后再清理旧视口。隐藏结果页保留轮询与任务状态，暂停无必要的 VTK 重绘。场量解释、独立有限元和导出流程见[结果专题](results.md)。

<a id="section-主题本地化与平台资源"></a>

## 9 主题、本地化与平台资源

`ThemePalette` 组合 Qt、代码、图表、预览、PyVista 与布局样式；`theme/themes/` 注册完整主题，`styles/*.qss` 管理共用控件状态。组件读取同一主题对象，主题切换后刷新外观并保留相机等展示状态。

`constants.py` 保存业务默认值、运行限制和数值配置，窗口尺寸、间距与分栏比例由 `LayoutStyle` 管理。应用显示文本使用 `locales/zh-CN.json` 与 `en-US.json` 的稳定 key；领域身份仍使用原始名称和枚举值。

文件和目录选择统一由 `widgets/file_dialogs.py` 创建。STEP、网格和工程文件导入，以及结果目录和导出文件选择均使用共用入口；导航按钮图标按当前主题绘制，标签使用当前语言资源。新增文件选择功能应调用 `choose_open_file()`、`choose_directory()` 或 `choose_save_file()`。

`application_icon.py` 管理应用图标与平台身份，`assets/morphopt.svg` 为共享图标资源。Windows 在创建应用前设置进程应用 ID，Linux 使用运行窗口图标；平台打包资源与运行时窗口资源分别管理。语言与主题选择不改变问题定义，不进入文档编辑历史。
