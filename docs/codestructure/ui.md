# MorphOpt UI 架构与编码规范

本文是 `src/morphopt/ui/` 的唯一架构规范。目标是让新增功能沿同一条数据流实现，
避免模型规则、文件操作、进程状态和 Qt 展示再次混在一起。

## 1. 总体分层

```text
MainWindow / Workbench / ObserverControls / FiniteElementPage  页面组合
        ↓                     ↓
widgets / presentation      application             展示 / 用例
        ↓                     ↓
visualization              model / codegen / schemes 场景准备 / 领域与文件
        ↓                     ↓
MorphOpt / TorchFEA core                             数值内核
```

目录职责：

```text
ui/
├── app.py / mainwindow.py / workbench.py / observe_panel.py
├── application_icon.py      Qt 应用身份及进程级窗口图标
├── fea_worker.py            独立有限元求解与导出进程入口（无 Qt）
├── refresh.py               Refreshable 协议、刷新上下文和统一调度器
├── model/
│   ├── base_nodes.py        通用节点基类与共享节点家族
│   ├── node_types/          可持久化的具体节点类型
│   ├── registry.py          节点类型与多态家族注册
│   ├── problem.py           问题聚合：跨节点关联、增删排序、不变量
│   ├── fields.py             字段元数据
│   ├── loaders.py           .morph JSON 边界
│   └── modelinfo.py          导入存档摘要
├── application/
│   ├── definitions.py       ProblemSession、模板和文件用例
│   ├── finite_element.py    指定迭代的有限元模型副本、载荷编辑和进程请求
│   ├── edit_history.py      JSON 快照操作树、编辑合并、根节点裁剪与保存标记（无 Qt）
│   ├── editing.py           节点/工况/任务分组、辅助代码、自定义类的编辑用例
│   ├── fields.py            字段、动态选项、目标代码片段的模型参数校验
│   ├── part_sets.py         各类 Part 的集合查询注册表
│   ├── cad.py               UI CAD 节点 → torchfea.cad 操作
│   ├── expressions.py       辅助代码与表达式求值上下文
│   ├── updaters.py           优化器分节投影、统一有序项、对称约束和距离矩阵规则
│   ├── editor_routing.py     Node → EditorRoute
│   ├── imported_models.py   导入文件扫描、模型摘要和外部建模器启动
│   ├── completion.py        代码补全候选
│   ├── values.py / devices.py 数值文本解析、设备发现
│   └── quickstart.py / results.py / runs.py
├── presentation/
│   ├── navigation.py        任务树投影、临时导航节点、稳定选择标识
│   ├── labels.py            树与编辑卡片共用的标题
│   └── history.py           History → 表格数据
├── visualization/
│   ├── scene.py             场景、标签、载荷图元的数据结构
│   ├── geometry.py          Part / Surface visitor、预览资源缓存
│   └── loads.py             工况与边界条件 → 载荷场景
├── theme/
│   ├── palette.py           Qt、代码、图表、预览、PyVista 和布局外观类型
│   ├── themes/              深色、浅色及可注册的主题定义
│   └── styles/*.qss         Qt 控件样式表片段
├── widgets/
│   ├── definition_actions.py 树菜单和编辑页共用的 Qt 操作入口
│   ├── editor_pages.py      页面加入编辑栈、绑定路由、连接 changed 信号
│   ├── edit_history.py      左下角操作历史树、撤销/重做与节点选择（不修改模型）
│   ├── collection_controls.py 集合标题、添加按钮、条目排序/删除与选中边框
│   ├── preview_renderer.py  场景数据 → PyVista actor；管理 actor 生命周期
│   ├── plot_style.py        定义与结果视口共用的光照、背景和透明渲染配置
│   ├── viewer.py            Part / Assembly / 工况选择与视口组合
│   ├── finite_element.py    有限元工作区、载荷表格、独立 QProcess 和导出选择
│   ├── model_tree.py        导航投影 → QTreeWidget；菜单与选择信号
│   ├── language_selector.py 语言选择与 Qt 设置持久化
│   ├── theme_selector.py    主题选择与应用
│   ├── param_form.py        节点与参数字典共用的 schema 表单
│   ├── editor.py            节点编辑页的标题、动作和代码槽
│   ├── codeeditor.py        通用 Python 代码控件
│   ├── helper_editor.py     自由代码与辅助变量/函数卡片中的编辑控件
│   ├── source_view.py       同步后的问题定义 → 只读生成代码
│   └── ...                  专用编辑器、结果页、对话框
├── i18n.py / locales/*.json  无 Qt 的本地化服务与语言资源
├── codegen/ / schemes/ (Python-defined scheme policies)
└── launcher.py              无 Qt 的 subprocess 基础设施
```

依赖规则：

- `model`、`application`、`presentation`、`visualization`、`codegen`、`schemes` 不导入
  Qt、widget、Workbench 或 Observer。
- `application` 处理用例、数值输入和模型查询；对话框及翻译后的用户提示归展示层。
- `presentation` 可查询本地化资源，生成标题、导航和表格数据，不创建控件。
- `visualization` 可使用 PyVista 数据集，不持有 plotter、Qt 控件或 VTK actor。
- `widgets` 将数据渲染成控件；结构操作共用 `DefinitionActions`，不调用其他 widget
  的私有方法来修改模型。文件扫描和进程启动交给应用服务。
- `i18n.py` 仅查询语言资源、格式化参数和通知订阅者；Qt 的设置和语言选择器在
  `widgets/language_selector.py`。
- 顶层窗口只编排页面、对话框和信号，不实现字段规则、代码生成或结果解析。

图标和平台身份统一由 `application_icon.py` 编排，页面只调用 `application_icon()`。
应用通过命令行启动，不提供或安装 `.desktop` 启动器，不写入用户应用目录或设置
Linux 桌面文件 ID。Linux 直接使用 Qt 的运行窗口图标；Wayland 任务栏是否采用该
图标取决于 Qt 和 compositor 对直接设置窗口图标协议的支持。
Windows 在创建 `QApplication` 前通过 `SetCurrentProcessExplicitAppUserModelID` 设置
稳定的 `MorphOpt.MorphOpt` 任务栏身份。Linux/Windows 的运行窗口共用
`assets/morphopt.svg`，由 Qt 按显示尺寸直接渲染。
SVG 是唯一图标资源，随 Python 包发布；更换图标时只编辑 SVG，无需手动转换，
也无需 pip 安装转换钩子。若未来发布 Windows 独立 EXE，EXE 文件和安装器所需的
ICO 应由对应打包流程生成并嵌入；运行时的 Qt 图标设置不修改 EXE 文件资源。

## 2. 状态所有权

每类状态只能有一个所有者：

| 状态 | 唯一所有者 | 说明 |
|---|---|---|
| 可保存的问题定义 | `ProblemDefinition` | `.morph` 的完整业务状态 |
| 定义工作流 | `ProblemSession` | 同步、校验、代码生成和跨对象编辑用例 |
| 当前结果 | `ResultSession` | controller、params、history、iteration、参数载入缓存与变形网格读取 |
| 优化运行 | `OptimizationRunSession` | 当前定义与任务来源、subprocess、进度、输出与结果目录发现 |
| 独立有限元模型与结果 | `FiniteElementSession` | 从指定迭代创建的网格、材料、载荷和结果副本，不与优化共享对象 |
| 共享分析选择 | `MainWindow` | 观察与有限元视图共用的结果目录和迭代，不共享可修改的内核对象 |
| 当前文档路径 | `MainWindow` | `Ctrl+S` 原路径保存，无路径时进入另存为 |
| 导航树与结果表格投影 | `presentation` | 根据当前定义或结果生成，不改模型 |
| 预览几何及查询缓存 | `PreviewGeometry` | 每次构建清除局部资源，导入存档按路径/时间/位姿缓存 |
| VTK actor | `PreviewRenderer` | 统一创建、移除；几何与载荷分别管理 |
| 当前页/节点/相机 | Qt view/widget | 仅短生命周期展示状态 |

禁止在两个 QWidget 中各存一份同一业务值。Widget 缓存只允许用于选中项、相机、
展开状态等展示信息；刷新后必须能从上述所有者恢复内容。

### 定义与优化过程

顶层导航分为“优化定义”和“优化过程”。启动时只允许进入定义；在定义页点击“开始优化”、
通过文件菜单从 `.py` 开始优化，或打开已有优化结果目录后，才开放优化过程。
优化过程内提供“迭代历史／有限元”两个视图，首次使用时创建，之后持续保留。
结果视图切换、目录与迭代摘要、优化状态及当前运行按钮合并在顶层导航的同一行；
观察页将 `task_controls` 提供给窗口组合，不再单独占用控制栏。
运行中只显示停止按钮；空闲时保留继续按钮，有可续跑来源时启用，否则置灰并显示原因提示。状态用短句表达，
过长的摘要与状态由 `ElidedLabel` 省略显示，完整文字保留在悬浮提示中。
同一工具栏的优化名称使用 `ResultPathLabel`：悬停显示当前结果目录的完整路径，
单击直接复制路径，并在状态栏短暂提示；键盘聚焦后也可按回车或空格复制。
目录一经发现即更新，不必等待首轮迭代完成。停止优化、切换结果视图和修改定义不会清空它，
成功切换运行来源时重置。没有结果目录时名称保持展示，点击不复制旧路径。
文件菜单统一拥有新建、打开 `.morph`、打开优化结果、从脚本开始、快速开始、保存、另存为及导出；
设置菜单拥有语言与主题。定义页的开始按钮和分析菜单共用 `Workbench.start_optimization()`
校验入口，校验通过即启动独立运行快照，再切换到观察视图。
“开始优化”位于顶层导航栏右侧，仅在定义模式显示，与工作区标签共用一行。

`MainWindow` 用不可变 `ResultSelection` 编排两个结果视图共同的 `(结果目录, 所选迭代)` 展示状态；观察滑块及有限元
迭代列表通过 `selectionChanged` 双向同步。有限元没有独立打开目录或手动导入观察结果的入口。
进入有限元时固定当前迭代，关闭观察页的自动跟踪；同一来源再次进入时只更新可选迭代，
保留载荷修改、选中的计算结果和日志。新迭代从确切的保存模型重新建立私有副本。
只有存在对应迭代模型时才开放有限元视图。有限元工作进程运行时锁定共享迭代选择，
优化进程仍可在后台继续计算，新增步骤更新滑块范围，但不会改变有限元正在使用的快照。

页面切换不启动、停止或重置任务。优化轮询在页面隐藏后继续，隐藏视口不重绘 VTK 场景。
停止仅由任务的停止按钮或退出窗口触发；运行期间暂停切换优化来源，防止替换当前分析上下文。
手动停止后若已有完整保存结果，运行会话将结果目录保留为续跑来源，保留可视化和当前步骤，
并启用“继续优化”。正常结束后也可继续当前保存结果；没有完整保存步骤时不启用续跑。
打开已有结果只浏览并准备续跑，不自动启动进程；点击继续时仍可选择最后一步或指定迭代。

定义传入观察页时通过 `.morph` 字典创建副本，启动时再次冻结运行快照。后续编辑定义、
打开或新建另一份 `.morph` 不会改变后台任务，也不会改变该任务随结果保存的定义。
定义文件路径与分析来源分别管理；`Ctrl+S` 始终保存当前定义。

有限元从 `log/femodel&results/femodel_<iteration>.npz` 读取当步原始网格和材料，
从 `result_<case>_iter_<iteration>.npz` 恢复原工况。只读取确切迭代，不以其他步模型替代。
载荷表只编辑私有模型的参数，保留工况已有的启用状态，不提供额外的启用开关。
求解和导出通过 `fea_worker` 的独立 QProcess 执行，切页后继续。
停止后保留导入模型；载荷修改会使旧结果失效，防止把旧解导出成新工况结果。

“工况与计算结果”下拉列表统一列出当前优化目录、当前迭代的原工况和各次成功的有限元结果。
`FiniteElementSession` 用 `FiniteElementResult` 描述每项来源；每次收敛后，将模型、解和日志
复制到会话工作目录中的独立快照，再追加条目。失败、停止和导出不会新增结果。
切换条目会从存档加载独立模型、恢复当次载荷与解；继续编辑不会改变已有快照。
同一会话内切换迭代、导入模型或切换语言不会删除计算记录；各目录与迭代分别筛选。
物理量表格导出以选中结果为准，NPZ 内嵌元数据标明原迭代、原工况、结果编号和计算时间。
快照由会话临时目录管理，页面退出清理时释放，不写入优化过程的原始结果文件。

有限元导出入口只放在有限元页。物理量表格通过位置及复选字段导出；
“导出模型与全部结果（TorchFEA）”则独立导出所选迭代的原始模型、全部原工况和会话内已完成的计算快照，
不包含尚未求解的载荷修改。`postprocess/native.py` 直接复制原生 NPZ，
只导出一份迭代模型，所有结果共用该模型，载荷参数保存在各结果的 `work_conditions` 中。
用户指定前缀，例如 `actuator`：模型为 `actuator_femodel.npz`，原工况为
`actuator_case0.npz`，新增计算为 `actuator_analysis1.npz`；
`actuator_manifest.json` 记录结果来源及共享模型。
`FiniteElementSession.native_export_request()` 固定导出清单，由 `fea_worker` 复制文件。
所选目录下新建与前缀同名的文件夹，重名时增加编号；失败会清理本次创建的目录，保留已有导出。
模型通过 `torchfea.load_model()` 读取，结果通过 `StaticResult.load()` 读取；
恢复结果的 `work_conditions` 后可按模型哈希检查配对。

### 有限元场量显示

`ui/application/result_fields.py` 用 `DisplayField` 注册云图分量，`ResultContours` 按当前解缓存场量。
可显示位移模长及分量、Cauchy 应力及 Mises 应力、Green–Lagrange 应变和应变能密度。
显示与导出共享 `postprocess.fields.gauss_values()` 的物理计算，应力、应变采用全局坐标轴。
云图将高斯点值按参考体积加权成单元平均，再对相邻单元作节点平均；界面注明“节点平均”，
这不是节点应力外推，导出仍保留各高斯点原值。无高斯点的模型只提供位移，缺少场量的节点保留 NaN。
切换原工况或有限元结果会替换缓存；编辑载荷后清除旧解与缓存，重新求解后再显示新场量。
有限元视图左下角的 XYZ 方向轴由 `plot_style.add_orientation_axes()` 创建，文字颜色随主题变化，
轴颜色与位置统一放在 `ViewerRenderStyle`，每次重建场景都会恢复。

### 有限元数据导出扩展

`src/morphopt/postprocess/` 不依赖 Qt。`fields.py` 定义物理量提供者 `ResultField`，
通过 `RESULT_FIELDS` 注册；`ResultLocation` 区分节点、参考点与单元，提供者接收 `FieldContext`，
返回带稳定编号的逐行记录 `ResultTable`。`combined_table` 按编号将所选物理量向右拼成列，
每次只导出一种位置、一个文件，不能混选不同位置的物理量。
`exporters.py` 定义 `ResultExporter` 协议及 `EXPORTERS` 格式注册表；当前支持 CSV 与 NPZ。
添加物理量无需修改格式写入器，添加格式无需改动物理量提取器，有限元页从注册表生成选项。

节点坐标、位移以及 Cauchy 应力、Green–Lagrange 张量应变都采用装配体全局坐标轴。
参考点按名称和独立编号输出，每个参考点一行；提供原始坐标、位移、变形后坐标以及
`UR1/UR2/UR3` 转角向量和模长 `UR`。参考点六自由度从解转换后的 RGC 块读取，
不使用模型的初始状态；转角沿用内核全局轴角向量，单位 rad，不转换为欧拉角或角度。
禁用的参考点不输出；模型没有参考点时界面提示并禁止该位置的导出。
高斯点逐点输出，不做节点平滑或单元平均；应变能同时输出密度、参考积分体积和积分能量。
无高斯点的模型不提供高斯点物理量，也不生成高斯点编号列；混合单元模型中，无高斯点的
单元只保留单元记录，高斯点量留空（NPZ 为 NaN），不伪造积分点或零应力。
节点、单元、积分点编号从 1 开始，与 TorchFEA INP 导出约定一致；保留实例和单元块名称。
保存窗口允许填写文件名，并通过文件类型选择 CSV 或 NPZ，不在编辑页重复放置格式控件。
CSV 是单张表（UTF-8 BOM，首行为列名）；NPZ 各列为独立数组，`__metadata__` 保存来源、
模型哈希、单位和张量约定。没有附加目录或 manifest 文件。
导出前验证模型与结果的哈希及收敛状态；先生成完整临时文件，成功后才发布目标文件。
已有文件只在用户确认覆盖后替换；求值失败保留原文件并清理临时文件。
`widgets/file_dialogs.py` 统一主窗口与结果导出的文件对话框、导航图标和覆盖提示。

## 3. 统一变更流

```text
用户结构操作（树右键 / 编辑页按钮）
  → 共用 DefinitionActions（对话框、选中项）
  → DefinitionCommands（创建默认值）/ ProblemDefinition（跨节点规则）
用户字段编辑
  → editor 修改类型化 Node
  → changed(node)，结构操作也携带发生变更的节点
  → RefreshCoordinator 合并短时间内的变化
  → ProblemSession.synchronize()
  → 生成一个 RefreshContext
  → 按注册顺序调用组件的 refresh_ui(context)
  → tree / active editor / generated source / preview 使用同一轮同步结果
```

规则：

1. Widget 不直接修改另一个 Widget 来维持业务一致性。
2. 单个节点内部规则放在节点类；跨节点不变量放在 `ProblemDefinition` 聚合方法。
3. 涉及同步、代码生成、IO 或运行前校验的用例放在 `ProblemSession`。
4. 结构变更必须调用 `ProblemDefinition.add_* / remove_* / move_* / rename_*`，
   禁止直接改 `children` 或手工修补关联引用。
5. 一个用户动作只进入一次统一刷新，不在多个 signal slot 中重复生成代码或重画预览。

结构操作和字段修改先进入 `Workbench` 的统一变更入口，由 `ProblemSession` 同步并记录快照。
结构操作随后通过 `refresh_now(node)` 立即刷新；连续字段输入通过 `request(node)` 合并后刷新。
组件使用已经同步的模型，不重复进行同一批编辑的同步。
两者都进入同一个调度器。

所有需要随定义变更刷新的组件实现 `Refreshable` 协议：

```python
def refresh_ui(self, context: RefreshContext) -> None:
    ...
```

`RefreshContext` 包含问题定义、当前选中节点、变更节点列表和是否完整刷新。
组件负责刷新自己的内容；`Workbench` 只负责同步准备与注册顺序，不判断当前组件的具体类型。
`EditorPages` 将刷新委托给活动编辑页，静态页面不参与数据刷新。

- 新增、删除、排序与字段修改共用 `changed(node)`，删除操作仍传递被删除的节点，
  让预览明确知道发生的是载荷变更或几何变更。
- 未知来源用 `None` 请求完整刷新。合并事件时保留该请求，不能被后来的局部修改覆盖。
- 仅修改载荷或工况时更新载荷 actor；修改几何、材料包络或辅助表达式时重建几何及载荷。
  完整刷新也保留当前工况和相机；更换问题、视图或部件时才重新设置视角。
- 树刷新保留选中项、展开状态和滚动位置；编辑器原位刷新，避免重新导航造成跳动。
- 组件刷新失败会记录完整异常并显示错误，其他独立组件仍完成刷新；成功状态不会覆盖本轮错误。

新增需要刷新的组件时，实现上述方法，并在 `Workbench._register_refreshables()` 中按依赖顺序注册。
新增编辑页时，将其传给 `EditorPages.register(..., refreshable=editor)`。

### 文档撤销与重做

`ProblemSession.history` 持有 `EditHistory`，每个状态保存与 `.morph` 相同结构的 UTF-8 JSON
字节和轻量选择路径。快照不可变，不与模型共享列表或字典；不逐次写磁盘、不存网格和求解结果。
默认整棵树保留至多 100 个节点，历史 JSON 总量上限为 64 MiB，当前状态始终保留。
`EditHistoryNode` 存储快照、父节点 ID、有序子节点 ID 和首选重做子节点；使用 ID 关联，避免父子对象循环引用。
超限时找出旧根通往当前状态的第一个子节点，将它提升为新根；删除旧根及其所有其他子树，逐根重复直到满足上限。

- 所有模型定义通过 `changed(node)` 接入历史；新增组件沿现有编辑页注册即可参与。
- 添加、删除、排序分别记录；同一输入框一次连续输入合并。焦点切换、点击其他操作或提交单行输入结束合并。
- 相同 JSON 不增加记录，撤销后新增编辑创建子分支，已有分支保留。只有本轮输入创建的叶节点允许合并。
  连续输入恢复成父状态时移除该叶节点，其他兄弟分支保持。预览失败不影响已保存的编辑历史。
- 每个历史步骤带稳定 ID 和创建时间；合并输入保留原步骤 ID。`EditHistoryPanel` 在模型树下方展示整棵历史树，
  通过 `jumpRequested(step_id)` 请求跳转，树标识当前与已保存状态。
  `ProblemSession.restore_edit_step(step_id)` 直接解码目标快照，跨多步和跨分支也只刷新一次。
  选取步骤后先提交输入，再按稳定 ID 查找，避免容量淘汰后恢复到错误节点。
- 撤销返回父节点，重做访问当前节点的首选子节点；新建和访问分支会更新祖先链的首选子节点。
- 历史区内的撤销/重做针对整个文档。`Ctrl+Z` / `Ctrl+Shift+Z` 在文本框内优先使用局部文本历史，
  无局部历史时使用文档历史；代码控件的快捷键只作用于自身，避免多个编辑器抢占快捷键。
- 撤销前提交仍在输入框或表格委托中的值，清除旧刷新请求，然后用 `from_dict()` 重建模型及引用。
  断开并重建旧表单，所有组件统一重新绑定；保留相机、工况、树展开状态和同一编辑页的滚动位置。
  延迟布局回调绑定到所属 QObject，表单销毁后不会再执行。
- 选择路径由 `presentation.navigation` 生成，涵盖普通节点、辅助代码、自定义类和 Updater 临时节点，
  不依赖恢复前的 Python `id()`，也不写入 `.morph` 文件。
- 新建、Quickstart、打开文件建立新起点。保存文件保留历史，用 JSON 内容标记已保存状态；标题 `*` 表示有修改。
  切换视角、语言和选择不记录，外部文件及优化过程和结果不回滚。

自定义类由 `DefinitionNavigation` 投影为模型树顶层集合，不再持有独立树控件。
`CustomClassOverview` 提供集合管理入口，`DefinitionActions` 统一负责添加/删除对话框与通知，
`CustomClassEditor` 继续负责类名和方法体编辑。类和方法选择统一使用 `ModelTree`，历史区只导航状态。

`RefreshContext.restoring` 区分历史恢复与普通模型切换：恢复不重新导入外部模型，也不重置预览相机与工况。
恢复期间暂停工作台重绘，重建完成后统一恢复。编辑页创建时即属于编辑栈，旧页面移除前先隐藏；
需要调用 `setVisible()` 的标签在构造时就指定父控件，避免 Qt 将未加入布局的控件临时显示为独立窗口。

辅助变量和辅助函数分别使用 `DefinitionManagerEditor` 集合页：总节点显示该类全部条目，
选择树中的具体条目只定位对应卡片；编辑卡片中的字段反向更新树选择，不重新打开页面。
新增、删除和排序共用 `DefinitionActions`，列表顺序就是脚本中的定义顺序。
字段修改时原位同步，保留焦点、代码撤销历史和页面滚动位置。

集合编辑的控件共用 `widgets/collection_controls.py`：`CollectionHeader` 将标题放在左侧，
添加入口放在右侧；多种类型用菜单直接添加，单一类型直接添加。
`ItemActions` 将上移、下移、删除集中在条目右上角，Quickstart 表格的行操作也放在表格右上方。
颜色、尺寸、悬停和禁用态由应用主题统一定义，删除使用 `actionRole="danger"`，
主操作使用 `actionRole="primary"`。集合页不再各自编写按钮样式。
选中卡片仅更新自身的 `collectionSelected` 属性，不向嵌套子框传播选中边框。

Updater 的目标函数、几何对称约束和罚函数也投影为组节点下的具体树条目。
`UpdaterItemTreeNode` 直接引用配置项字典，以字典身份保持排序后的选择，
点击树条目定位集合页中的参数卡片；编辑卡片只更新树选择，不触发页面导航。
新建几何 updater 默认包含 `ShapeDerivative` 目标项及 `Fairness`、`Distance`、`Cylinder` 三个罚函数，
距离矩阵在绑定目标 Part 时按其曲面数量调整；显式传入空列表则保留为空。

预览标注使用 `locales` 中的完整文本模板，作用对象写明实例与集合名。
耦合同时显示参考点和目标节点集；边界条件显示目标与固定自由度；
集中力/力矩显示参考点与三个分量；弹簧显示两个端点、刚度和原长。
标注显示定义中的数值，不假设模型采用哪一套物理单位。
渲染器按标注行数与相机投影计算纵向占位，避免同侧标注框相互覆盖。

定义预览与结果观察通过 `configure_plotter()` 共用透明渲染设置：关闭多重采样、启用 alpha
平面和深度剥离。清空视口后重新恢复光照与配置，避免半透明外表面消失。
BoundaryPart 的每个曲面使用独立且稳定的 actor 名称，空心部件的外表面半透明、内表面不透明。

### 主题与外观

`ui/theme` 是外观配置入口。`ThemePalette` 组合 Qt 颜色令牌、字体与代码高亮、图表、Quickstart
预览、变形网格、PyVista 的 `ViewerStyle`，以及 `LayoutStyle` 中的窗口尺寸、控件尺寸、间距和
分栏比例。深色、浅色分别在 `themes/` 中配置；新增主题时注册一个完整的不可变 `ThemePalette`。

`styles/*.qss` 统一管理 Qt 控件的状态、边框、通用间距和文字样式。PyVista 和 Matplotlib
通过同一 `theme_manager.palette` 读取对应的渲染与布局配置，不在视图模块中维护外观常量。
主题切换时，工作台重建主题相关的预览 actor 并保留相机位置；图表、代码高亮、Quickstart
预览和结果网格也会刷新。`constants.py` 只保留业务默认值、运行限制、刷新/轮询时序和几何
算法精度；窗口及控件布局尺寸统一保存在 `LayoutStyle`。

## 4. 类型化任务树

持久化模型的顶层结构为：

```text
ProblemNode
├── GeometryNode
│   └── PartNode*
│       ├── InstanceNode*
│       └── SurfaceNode*       # 仅 BoundaryPart
├── LoadsNode
│   └── FEAComponentNode*
├── StepsNode
├── MaterialsNode
│   └── MaterialNode*
├── ObjectiveNode
├── SolverNode
└── UpdaterNode
```

- `kind` 由节点类定义并注册到 `NODE_TYPES`，不在业务代码中临时发明。
- 字段是节点构造函数中的显式属性；`_FIELDS` 只负责枚举序列化字段。
- dict 仅允许出现在 `.morph` 边界和 updater 的结构化配置中。
- Part、Instance、Surface 的索引都按所属容器局部计算；Surface 0 是该 Part 外表面。
- 多 Part、多 Instance 的名称唯一性和关联更新由 `ProblemDefinition` 负责。
- 几何 Part、材料和载荷都是命名接口：统一经
  `ProblemDefinition.rename_interface()` 改名。运行时的材料目标、优化器目标、
  Instance / 参考点引用、载荷步和 Jacobian 都持有目标 Node 对象，不保存名称副本；
  改名后它们天然跟随。名称只在 `.morph`、下拉显示和代码生成边界投影出来。
- Assembly Part 的物理名称通过 `ProblemDefinition.rename_part()` 修改。它会同步
  指向该 Part 的材料，以及仍使用 `<part>-1`（或旧 `<part>`）名称的默认 Instance
  和载荷引用；用户额外命名的 Instance 保持不变。TorchFEA 导入 Part 的物理名称属于
  `.npz` archive，只允许改其 MorphOpt 几何接口名称。
- `.morph` 是唯一可编辑定义格式；Python 只作为生成结果，不反向解析成定义。

### 显示命名

树节点、编辑卡片、添加菜单和对象选择框统一由 `presentation/labels.py` 命名：

- 已定义对象使用 `名称 [ClassName]`，例如 `body [CADPart]`、
  `pressure_1 [Pressure]`、`body-1 [Instance]`。
- 添加菜单使用 `功能说明 [ClassName]`，例如 `长方体 [Box]`、
  `BSP 镜面对称 [BspMirrorConstraint]`。类名由 schema 的 `class_name` 声明，
  语言资源只保存功能说明；选择自定义类时显示实际选用的类。
- 几何优化器同时标明目标部件和对应类；偏置部件显示 `UpdaterOffsetBoundaryPart`。
- 边界 Part 与 SIMP 材料的 schema 显式声明 `design=True`，对应节点以只读
  `is_updatable` 暴露能力。类型菜单、模型树和组件定义页明确显示“可更新”；
  固定几何、均匀材料不提供创建几何/材料优化器的入口。
- 创建优化器直接选择具体 Part 或材料接口，树右键与定义页共用
  `DefinitionActions.add_updater(target)`。不再按“几何/材料”自动挑选第一个对象。
  每个目标只能分配一个 updater，标题使用“目标名称的优化器 [UpdaterClass]”。
- 分组不附加虚构的类名；辅助函数和重写方法使用 `name()`。
  CAD 操作的输入特征保留在提示信息中。
- 中文统一使用“部件 / 实例 / 装配体”和“工况”；CAD 的 STEP 导入写作“导入 STEP”。
- 下拉框的展示标题与 `itemData` 分开，保存和代码生成仍使用原始名称或对象引用。
  禁止从展示标题中解析名称，或把带类名的标题写回定义。

## 5. 模板体系

启动时直接显示空白定义工作台；标准栏目存在，但不预填具体设计。用户可手动定义，或使用 Quickstart。
`application/quickstart.py` 的类型化配置负责参数校验、
独立的几何定义、多目标加权函数、目标对应的载荷工况和更新器生成，`widgets/quickstart.py` 只收集输入及展示
摘要与示意。`ObjectiveDraft` 统一处理方法切换、目标列表与压力通道调整；初始示意的
三角形、光照和投影准备由 `InitialDesignGeometry` 处理，`paintEvent()` 只绘制准备好的数据。
配置保存为辅助变量 `quickstart_settings`，生成物是普通 `ProblemDefinition`，
不建立另一个模型格式。Quickstart 按参数组合创建节点，不克隆模板。
几何工厂、网格构建及其参数化变换归内核；UI 不生成重写几何工厂的类，
也不生成设计块或接触物体的建网格脚本。结构化设计块使用 `BoxPart`；
其他 CAD 几何由 `CADPart` 交给 `torchfea.cad` 建模和网格化。

`ui/model/chamberlayout.py` 中的 `ChamberLayer` / `LayeredChambers` 只负责 Quickstart 的分层气腔配置、排布校验和初始预览；生成的形状优化定义仍使用内核现有的曲面与 Part 接口。
工作空间驱动边界的高斯点、权重、切向和取向由 `optcore/quadrature.py` 生成；应用服务将
边界点映射为载荷工况；用户选择的压力通道映射到驱动积分坐标，同通道气腔联动，未选通道固定零压。目标按所选通道汇总 Jacobian 列，并通过散度定理计算边界积分。
普通目标不使用高斯点密度。
初始预览使用轻量曲面；Box 预览由 UI 的 `BoxPreviewAdapter.mesh()` 生成，
Quickstart 复用该方法。几何准备归 `visualization`，widget 只负责绘制。

内腔偏置 Part 在统一 Part schema 中注册，代码生成器按目标 Part 类型选择
`UpdaterOffsetBoundaryPart`；参数集合、FEA 和求解器仍使用公共接口。

内置方案策略由 `schemes/base.py` 中的 Python 类注册，默认问题由 Quickstart 构建。
`.morph` 文件只作为用户问题定义，由打开/导入流程读取；它不参与方案注册，内置网格
资源改由用户提供的模型路径加载。
新增方案策略时：

1. 继承 `SchemeTemplate`，显式定义方案 id、显示名称、默认材料和代码槽。
2. 将实例加入 `BUILTIN_SCHEMES`。

`SchemeTemplate` 提供 schema 驱动的共享工厂；`BuiltinSchemeTemplate` 以 Python 策略
配合 Quickstart 生成起始问题。方案策略不依赖起始文件目录。

## 6. 编辑器规范

- Node 与中央编辑页的关系只在 `application/editor_routing.py::route_editor()` 定义。
- 参数表单字段由 `application/fields.py` 根据 schema 与模型查询决定；控件只负责渲染。
- 动态集合按所属 Part 经 `PartSetCatalog` 查询，不能用“问题是否包含导入模型”决定所有 Part 的选项。
- 页面加入编辑栈、路由绑定和变更信号连接统一注册在 `EditorPages`；不用维护第二份页面清单。
- `ParamForm` 是唯一 schema 字段渲染器。参数字典直接绑定字典；类型化节点通过 read/write
  回调绑定。禁止将节点字段复制到临时字典，再同步两份值。
- 数字、向量、矩阵和辅助变量表达式统一由 `application/values.py` 解析。
- `HelperCodeEditor` 负责辅助代码页面；辅助定义的保存和语法校验由 `HelperCodeSession` 处理。
- 自定义类名称校验、改名/删除后的全局引用更新由 `CustomClassSession` 处理，树与编辑器复用。
- 载荷工况的矩阵数据操作由 `LoadCaseSession` 处理；求解任务的行/分组转换由 `SolverTasks` 处理。
- 目标、罚函数、对称约束共用 `UpdaterItems` 和 `UpdaterItemList`；不得各写一套增删卡片。
- 普通字段变更保留表单；只有 schema、目标或列表结构变化才重建。动态下拉选项单独刷新。
- 编辑控件获得焦点时，模型树静默跟随对应节点，不向编辑页反向发送导航事件。
  数据刷新原地更新已有表单与关联选项；只有用户主动选择树节点时滚动定位编辑卡片。
  实例、部件或 CAD 输入变更后立即刷新关联下拉框，不等待重新选择模型树。
- `DefinitionNavigation` 生成任务树投影；临时导航节点不加入可保存的问题树。
- 字段编辑器和结构操作统一发出 `changed(node)`，交给 `RefreshCoordinator` 调度；
  树控件不再通过独立的结构刷新信号触发第二轮刷新。
- 编辑器收到 `ProblemDefinition` 是为了动态选项和上下文，不拥有它。
- 所有应用定义的显示文案都在 `locales/zh-CN.json`、`locales/en-US.json` 中维护，
  包括标题、按钮、字段名、帮助文字、模板说明、文件筛选、可视化标签和校验错误。
  Python 和模板元数据只保存稳定 key，不再保留中英文文案副本或按原文生成 key。
- 展示层使用 `tr(key, **values)`。模型、应用服务和代码生成器的校验错误使用
  `localized_message(key, **values)`；异常保存 key 与参数，在显示时才查询当前语言，
  原有 `ValueError` / `KeyError` 等异常类型保留。
- 类名、字段标识、用户名称、路径、数值、物理符号和代码内容是数据，保留原值；
  第三方异常与 Python 语法错误的诊断细节也保留原文，由本地化提示说明上下文。
- 动态句子通过资源中的占位符组合，禁止在代码里拼接中文或英文片段。
- 每种语言的名称使用其资源中的 `locale.name`，模板说明使用 `template.label_key`。
- 缺失翻译按默认语言回退；本地化管理器不依赖 Qt 或 QSettings。
- 语言切换原地刷新文本，不重建 PyVista/OpenGL viewport。
- 一个专用 editor 只在通用 schema 表单无法清楚表达交互时新增。

### 参数与内核的对应

新增接口的实例、部件、集合、参考点、CAD 输入对象和对称目标等引用默认留空，
下拉框提供空选项，允许清空。未选择实例或部件时，不显示其他部件的集合。
不因模型中只有一个部件而自动绑定材料；模板和 Quickstart 必须明确写出自己的引用。
求解前检查必选引用。数值和算法枚举保留各自的有效初值。

`model/schemas.py` 的字段 key 对应构造函数或工厂方法的关键字参数，表单提示显示该 key。
`application/fields.py` 决定当前模型可编辑的字段，`codegen/generator.py` 负责将其写入任务脚本。
材料模型选择映射到 `MaterialModels.<Model>Params`，求解设备 `gpus` 映射到
`Solver.available_gpus`，实例平移和转动组合成 `add_instance` 的六维位姿。

曲面参数中，下列字段通过几何优化器的 `Fairness` 罚函数生效。未添加 `Fairness` 时，
这些阈值不参与优化；添加后，超过对应阈值的 80% 开始惩罚。

| 工厂参数 | 内核属性 | 实际计算 |
| --- | --- | --- |
| BSP `maxC`、CPGEO 圆柱 `maxC`、CPGEO 球 `MaxC` | `MaxC` | 主曲率平方和 `κ₁² + κ₂² = 4H² − 2K`，量纲为长度的负二次方 |
| BSP `maxFF` | `MaxFF` | 参数切向量的非正交程度 `F² / (E·G)` |
| BSP `maxR` | `MaxR` | 第一基本形式 `E`、`G` 的相对导数平方，经 `rr_compensation` 补偿 |

控制点步长由 `UpdaterBoundaryPart.max_step_length` 管理。这些 Fairness 阈值均不是
每步控制点位移、半径变化的上限。`seed_size` 控制曲面初始控制网格及预采样，
体有限元网格由 Part 的 `fea_seed_size` 或 `mesh_size` 单独控制。
CPGEO 曲率罚函数只使用 `MaxC`，因此其表单不提供 BSP 的 `degree`、`maxR`、`maxFF`。

SIMP 中 `initial_ratio` 是设计场控制点初值，材料比例由 sigmoid、RAMP 插值和
`simp_ratio_min` 共同决定。`materialpenalty` 是整数 RAMP 参数，`MinValue` / `MaxValue`
作用于设计场控制变量。Neo-Hookean 模型使用 `mumax` / `kappamax` 生成本构参数，
该模型的表单只提供这一组模量。圆柱包络罚函数的 `height` 是全局 Z 上界，
`bottom` 是全局 Z 下界。

`tests/ui/test_parameter_contracts.py` 核对各类型的 schema、生成调用和内核签名，
检查载荷幅值数量、所有材料模型的可见参数、CAD 预览与脚本参数、对称约束、
辅助变量和 CPU/GPU 选择；同时直接构造 BSP 与 CPGEO 曲面以检查工厂内部的参数传递。

### 可视化的扩展协议

载荷符号使用场景对角线和部件典型宽度共同确定尺寸；细长部件不能仅按长度放大箭头。
直箭头统一长度、箭头和箭杆比例，力矩、弹簧和标记同步缩放，显示尺寸与载荷幅值分离。

```text
ProblemDefinition → PreviewGeometry + PartPreviewVisitor → PreviewScene
工况与边界条件    → LoadPreviewVisitor                  → LoadScene
PreviewScene / LoadScene → PreviewRenderer              → PyVista actors
```

每类 Part 的 adapter 提供 `preview()`、`surface()` 和可选的 `model_part()`：分别负责
初始形状、载荷/边界面的几何、节点集合查询所需的模型。Boundary、Box、CAD、INP、
TorchFEA 导入模型分别实现；`PreviewViewer` 不按 Part 类型写分支。
CAD adapter 只保留三角面实际引用的顶点，按 OCC 顺序显示 `face_0` 起的面号与轮廓边。
Part 视图使用局部坐标；Assembly 视图对每个 Instance 应用位姿后显示工况载荷。

增加 Part 预览时继承 `PartPreviewAdapter` 并注册；增加集合查询时注册 `PartSetCatalog`
的 provider（工作台的 `part_sets` 共享注册表在数据变更时失效缓存）。增加载荷时调用 `LoadPreviewVisitor.register()`，返回已有载荷图元；若需要
新图元，则在 `PreviewRenderer.draw` 的 `singledispatchmethod` 注册处理器。

```python
from morphopt.ui.visualization import PreviewGeometry, PartPreviewAdapter, apply_instance_pose

class MyPartPreview(PartPreviewAdapter):
    def preview(self, context, part, instance):
        mesh = ...  # 从模型或内核获取初始几何
        if instance is not None:
            mesh = apply_instance_pose(mesh, instance, context.values)
        name = instance.name if instance is not None else part.name
        context.scene.add_base(name, mesh, color="#667fa8")

geometry = PreviewGeometry()
geometry.parts.register("MyPartInterface", MyPartPreview())
# 将 geometry 注入 PreviewViewer(geometry=geometry)
```

先调用 `PreviewGeometry.build()` 绑定问题和资源，然后查询集合或构建载荷场景。
单个 Part 预览错误显示在场景中，不阻止其他 Part 的显示；它不会修改优化模型或生成兜底几何。

## 7. 定义、代码生成与文件边界

- View 使用 `ProblemSession.source()`，不直接调用 `generate_source()`。
- MainWindow 使用 `ProblemLibrary` 创建模板、打开、保存和导出 Python。
- `generate_source()` 必须是确定性的，只读同步后的 `ProblemDefinition`。
- 生成前校验 Part、Instance、集合、材料目标和 updater 目标；错误直接阻止进入优化器。
- `.morph` 保存必须可无损 round-trip；新增持久字段时同步更新节点构造、
  `to_dict/from_dict` 和模板测试。
- 模板资源路径通过包位置解析，不依赖当前工作目录。

## 8. 运行与结果观察

- `OptimizationRunSession` 是唯一 subprocess 所有者，负责 fresh/continue 模式、停止
  整个进程组和 timestamp 结果目录发现。
- `RunSource`/`RunSourceKind` 表达下一次运行来源，禁止使用包含魔法键的 dict。
- `ResultSession` 一次绑定一个结果目录；controller/params 每个目录初始化一次，
  History 按滑块选择的 iteration 加载。
- `ObserverControls` 只处理按钮、对话框、定时器和状态文字。任务来源、一次性启动消费、
  标准输出线程、终端日志过滤、伴随定义保存和轮询状态都由 `OptimizationRunSession` 负责。
- `RunProgress` 是一次轮询快照，页面消费快照，不自行比较结果路径或保存另一份运行状态。
- 工况编号与列表行号分开保存；工况 0、3、7 可以显示在连续的三个列表行中。
- `ObserverPanel` 和结果页共用一个 `ResultSession`。参数按迭代载入一次，变形文件路径和
  网格读取不出现在 widget 内；结果页只渲染已准备的对象。
- 参数载入发生在清空视口之前；载入失败时保留现有图像。
- 可更新结构展示由可更新 interface 自身的加载/绘图协议提供，不根据 shape/SIMP
  模板写分支；显示名采用 `Part: name`、`Material: name`。
- 进程 stdout 在线程中读取，通过 Qt signal 回到 UI 线程；不得在 UI 线程阻塞读取。

## 9. 命名与代码风格

- 类名表达角色：`*Session` 是有状态应用会话，`*Library` 是无状态资源/文件入口，
  `*Page`/`*Editor`/`*Viewer` 是 Qt 展示。
- `create/add/remove/move/rename` 用于改变模型；`load/save/export` 用于 IO；
  `bind/reset` 用于会话生命周期；`build/refresh` 用于展示。
- 列表和集合使用复数；不要用 `data/info/tmp` 表示长期业务对象。
- 应用状态用 dataclass/Enum，不使用字符串键 dict。
- 不写只转发且不增加语义的方法；抽象必须拥有明确不变量或边界。
- 注释解释“为什么”和约束，不复述代码；公开边界写简洁 docstring。
- Python 使用 4 空格、类型注解、`pathlib.Path` 处理服务层文件路径。

## 10. 新功能落点

1. 新业务字段：类型化 Node + schema。
2. 新跨节点规则：`ProblemDefinition` 聚合操作。
3. 新定义工作流：`ProblemSession`。
4. 新文件/模板动作：`ProblemLibrary`。
5. 新结果文件：`ResultSession`。
6. 新进程模式：`OptimizationRunSession`。
7. 新编辑页面：widget + `route_editor()` + `EditorPages` 的页面绑定。
8. 新 Part/载荷预览：visitor 注册，render widget 不增加类型分支。
9. 新结构动作：领域操作/应用策略 + `DefinitionActions`，树和编辑页复用。
10. 新模板：一个 `.morph`。

## 11. 提交前检查

至少执行：

```bash
python -m compileall -q src/morphopt/ui tests/ui
python -m pytest -q tests/ui
git diff --check
```

并用项目环境执行离屏 Workbench 冒烟，确认：

- 所有可见模板可加载；
- 每个模板生成的 Python 可 `compile()`；
- Workbench 可构造且代码页不为空；
- 打开/保存 `.morph` 后结构保持一致；
- Observer 可绑定已有结果并切换 iteration；
- fresh/continue/stop 三条进程路径仍可用。
