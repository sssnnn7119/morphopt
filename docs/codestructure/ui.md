# MorphOpt UI 架构与编码规范

本文是 `src/morphopt/ui/` 的唯一架构规范。目标是让新增功能沿同一条数据流实现，
避免模型规则、文件操作、进程状态和 Qt 展示再次混在一起。

## 1. 总体分层

```text
MainWindow / Workbench / ObserverControls       组合视图
                    ↓
ui.application                                  应用服务
                    ↓
model / codegen / launcher / schemes            领域与基础设施
                    ↓
MorphOpt / TorchFEA core                        数值内核
```

目录职责固定如下：

```text
ui/
├── app.py                    QApplication、主题和进程环境
├── mainwindow.py             页面组合、导航、文件对话框和用户确认
├── workbench.py              定义页组合视图
├── observe_panel.py          运行与结果观察组合视图
├── application/
│   ├── definitions.py        定义同步、校验、模板和文件用例
│   ├── editor_routing.py     Node → editor 的纯路由
│   ├── results.py            结果目录、History、Params 的只读会话
│   └── runs.py               优化进程和新结果目录发现
├── model/
│   ├── problem.py            类型化任务树与跨节点不变量
│   ├── schemas.py            字段、后端类型和 updater 项目录
│   ├── loaders.py            `.morph` JSON 边界
│   └── modelinfo.py          TorchFEA 模型摘要
├── codegen/generator.py      ProblemDefinition → 可运行 Python
├── schemes/
│   ├── base.py               文件模板发现、模板元数据和共享工厂
│   └── snippets.py           目标函数可插入代码片段
├── templates/*.morph         可发现的问题模板
├── widgets/                  Qt 编辑器和可视化组件
└── launcher.py               无 Qt 的 subprocess 基础设施
```

依赖只能向下：

- `model/` 不得 import Qt、widget、Workbench 或 Observer。
- `application/` 不得创建 Qt widget、对话框或翻译文案。
- `widgets/` 可以读取 model，并通过信号表达用户操作；不得启动进程、解析结果目录或
  生成运行脚本。
- `launcher.py` 不得持有界面状态；视图只能通过 `OptimizationRunSession` 使用它。
- `mainwindow.py` 是组合根，不实现字段规则、代码生成规则或结果解析。

## 2. 状态所有权

每类状态只能有一个所有者：

| 状态 | 唯一所有者 | 说明 |
|---|---|---|
| 可保存的问题定义 | `ProblemDefinition` | `.morph` 的完整业务状态 |
| 定义工作流 | `ProblemSession` | 同步、校验、代码生成和跨对象编辑用例 |
| 当前结果 | `ResultSession` | controller、params、history、iteration |
| 优化进程 | `OptimizationRunSession` | subprocess、运行模式、结果目录发现 |
| 当前页/节点/相机 | Qt view/widget | 仅短生命周期展示状态 |

禁止在两个 QWidget 中各存一份同一业务值。Widget 缓存只允许用于选中项、相机、
展开状态等展示信息；刷新后必须能从上述所有者恢复内容。

## 3. 统一变更流

```text
用户编辑
  → editor 调用类型化 Node 或 ProblemDefinition 聚合操作
  → 发出一次 changed
  → Workbench 合并短时间内的变化
  → ProblemSession.synchronize()
  → tree / active editor / generated source / preview 仅刷新一次
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
- 参数表单字段只读 `model/schemas.py`，不在 widget 保存第二份字段目录。
- 所有可编辑 widget 统一发出 `changed`；结构树统一发出 `treeChanged`。
- 编辑器收到 `ProblemDefinition` 是为了动态选项和上下文，不拥有它。
- 标题和提示使用 `T(zh, en)`；业务名称、Part 名和接口名不翻译。
- 语言切换原地刷新文本，不重建 PyVista/OpenGL viewport。
- 一个专用 editor 只在通用 schema 表单无法清楚表达交互时新增。

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
- `ObserverControls` 只处理按钮、对话框、轮询定时器和状态文字。
- `ObserverPanel` 只将 ResultSession 的对象交给 observation page 渲染。
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
7. 新编辑页面：widget + `route_editor()` 一处注册。
8. 新模板：一个 `.morph`，不是一套新 UI 分支。

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
