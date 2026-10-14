# MorphOpt UI 架构与编码规范

本文是 `src/morphopt/ui/` 的唯一架构规范。目标是让新增功能沿同一条数据流实现，
避免模型规则、文件操作、进程状态和 Qt 展示再次混在一起。

## 1. 总体分层

```text
MainWindow / Workbench / ObserverControls          页面组合
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
├── model/
│   ├── nodes.py             节点字段、序列化和节点内部行为
│   ├── problem.py           问题聚合：跨节点关联、增删排序、不变量
│   ├── schemas.py           字段、后端类型和 updater 目录（保存文本 key）
│   ├── loaders.py           .morph JSON 边界
│   └── modelinfo.py          导入存档摘要
├── application/
│   ├── definitions.py       ProblemSession、模板和文件用例
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
├── widgets/
│   ├── definition_actions.py 树菜单和编辑页共用的 Qt 操作入口
│   ├── editor_pages.py      页面加入编辑栈、绑定路由、连接 changed 信号
│   ├── preview_renderer.py  场景数据 → PyVista actor；管理 actor 生命周期
│   ├── viewer.py            Part / Assembly / 工况选择与视口组合
│   ├── model_tree.py        导航投影 → QTreeWidget；菜单与选择信号
│   ├── language_selector.py 语言选择与 Qt 设置持久化
│   ├── param_form.py        节点与参数字典共用的 schema 表单
│   ├── editor.py            节点编辑页的标题、动作和代码槽
│   ├── codeeditor.py        代码控件与独立的 HelperCodeEditor
│   └── ...                  专用编辑器、结果页、对话框
├── i18n.py / locales/*.json  无 Qt 的本地化服务与语言资源
├── codegen/ / schemes/ / templates/
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

## 2. 状态所有权

每类状态只能有一个所有者：

| 状态 | 唯一所有者 | 说明 |
|---|---|---|
| 可保存的问题定义 | `ProblemDefinition` | `.morph` 的完整业务状态 |
| 定义工作流 | `ProblemSession` | 同步、校验、代码生成和跨对象编辑用例 |
| 当前结果 | `ResultSession` | controller、params、history、iteration、参数载入缓存与变形网格读取 |
| 优化运行 | `OptimizationRunSession` | 当前定义与任务来源、subprocess、进度、输出与结果目录发现 |
| 导航树与结果表格投影 | `presentation` | 根据当前定义或结果生成，不改模型 |
| 预览几何及查询缓存 | `PreviewGeometry` | 每次构建清除局部资源，导入存档按路径/时间/位姿缓存 |
| VTK actor | `PreviewRenderer` | 统一创建、移除；几何与载荷分别管理 |
| 当前页/节点/相机 | Qt view/widget | 仅短生命周期展示状态 |

禁止在两个 QWidget 中各存一份同一业务值。Widget 缓存只允许用于选中项、相机、
展开状态等展示信息；刷新后必须能从上述所有者恢复内容。

## 3. 统一变更流

```text
用户结构操作（树右键 / 编辑页按钮）
  → 共用 DefinitionActions（对话框、选中项）
  → DefinitionCommands（创建默认值）/ ProblemDefinition（跨节点规则）
用户字段编辑
  → editor 修改类型化 Node
  → 发出一次 changed
  → Workbench 合并短时间内的变化
  → ProblemSession.synchronize()
  → tree / active editor / generated source / preview 刷新
  → 本轮 source(synchronize=False)，避免重复同步
```

规则：

1. Widget 不直接修改另一个 Widget 来维持业务一致性。
2. 单个节点内部规则放在节点类；跨节点不变量放在 `ProblemDefinition` 聚合方法。
3. 涉及同步、代码生成、IO 或运行前校验的用例放在 `ProblemSession`。
4. 结构变更必须调用 `ProblemDefinition.add_* / remove_* / move_* / rename_*`，
   禁止直接改 `children` 或手工修补关联引用。
5. 一个用户动作只进入一次统一刷新，不在多个 signal slot 中重复生成代码或重画预览。

## 4. 类型化任务树

持久化模型的顶层结构为：

```text
ProblemNode
├── GeometryNode
│   └── PartInterfaceNode*
│       ├── InstanceNode*
│       └── SurfaceNode*       # 仅 BoundaryPart
├── LoadsNode
│   └── InterfaceNode*
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

## 5. 模板体系

启动时直接显示空白定义工作台；标准栏目存在，但不预填具体设计。用户可手动定义，或使用 Quickstart。
`application/quickstart.py` 的类型化配置负责参数校验、
独立的几何定义、多目标加权函数、目标对应的载荷工况和更新器生成，`widgets/quickstart.py` 只收集输入及展示
摘要与示意。`ObjectiveDraft` 统一处理方法切换、目标列表与压力通道调整；初始示意的
三角形、光照和投影准备由 `InitialDesignGeometry` 处理，`paintEvent()` 只绘制准备好的数据。
配置保存为辅助变量 `quickstart_settings`，生成物是普通 `ProblemDefinition`，
不建立另一个模型格式。Quickstart 按参数组合创建节点，不克隆模板。
几何工厂、网格构建及其参数化变换归内核；UI 不生成重写几何工厂的类，
也不生成设计块或接触物体的建网格脚本。结构化设计块使用 `BoxPartInterface`；
其他 CAD 几何由 `CADPartInterface` 交给 `torchfea.cad` 建模和网格化。

`ui/model/chamberlayout.py` 中的 `ChamberLayer` / `LayeredChambers` 只负责 Quickstart 的分层气腔配置、排布校验和初始预览；生成的形状优化定义仍使用内核现有的曲面与 Part 接口。
工作空间驱动边界的高斯点、权重、切向和取向由 `optcore/quadrature.py` 生成；应用服务将
边界点映射为载荷工况；用户选择的压力通道映射到驱动积分坐标，同通道气腔联动，未选通道固定零压。目标按所选通道汇总 Jacobian 列，并通过散度定理计算边界积分。
普通目标不使用高斯点密度。
预览从内核获取初始网格，在 widget 中仅执行正等轴测投影、着色和坐标轴绘制。

内腔偏置 Part 在统一 Part schema 中注册，代码生成器按目标 Part 类型选择
`UpdaterOffsetBoundaryPart`；参数集合、FEA 和求解器仍使用公共接口。

模板是 `ui/templates/*.morph`，由 `schemes/base.py` 自动发现。新增模板不增加新的
“优化方法”类：

1. 复制或创建一个合法 `.morph`。
2. 在顶层 `template` 元数据中给出唯一 id、中英文名称、可用几何/材料类型等。
3. 放入 `ui/templates/`；打包规则会包含 `.morph` 和模板引用的 `.npz`。
4. `codesign` id 目前由 `HIDDEN_TEMPLATE_IDS` 隐藏，未完成前不得显示。
5. 运行全部模板代码生成测试。

`SchemeTemplate` 提供 schema 驱动的共享工厂；`MorphTemplate` 克隆文件中的问题树。
模板只决定初始问题，不形成另一套运行时类型系统。

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
- `DefinitionNavigation` 生成任务树投影；临时导航节点不加入可保存的问题树。
- 所有可编辑 widget 统一发出 `changed`；结构树统一发出 `treeChanged`。
- 编辑器收到 `ProblemDefinition` 是为了动态选项和上下文，不拥有它。
- 标题和提示保存稳定 key，经 `tr(key, **values)` 查询 JSON 资源；业务名称不翻译。
- 缺失翻译按默认语言回退；本地化管理器不依赖 Qt 或 QSettings。
- 语言切换原地刷新文本，不重建 PyVista/OpenGL viewport。
- 一个专用 editor 只在通用 schema 表单无法清楚表达交互时新增。

### 可视化的扩展协议

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
