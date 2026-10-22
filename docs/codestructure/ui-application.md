# UI 应用服务

[代码结构导览](README.md) · [领域模型](ui-model.md) · [展示与刷新](ui-presentation.md) · [结果分析](results.md)

## 目录

<!-- docs:toc depth=1 -->

- [1 源码入口](#section-源码入口)
- [2 定义会话与文件入口](#section-定义会话与文件入口)
- [3 编辑命令与参数查询](#section-编辑命令与参数查询)
- [4 编辑历史与恢复](#section-编辑历史与恢复)
- [5 Quickstart 与方案策略](#section-quickstart-与方案策略)
- [6 代码生成边界](#section-代码生成边界)
- [7 自定义类的选择与绑定](#custom-classes)
- [8 CAD 转换与 STEP 导出](#cad)
- [9 优化运行会话](#runs)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 源码入口

| 路径 | 责任 |
|---|---|
| [`application/definitions.py`](../../src/morphopt/ui/application/definitions.py) | `ProblemSession`、`ProblemLibrary` |
| [`application/editing.py`](../../src/morphopt/ui/application/editing.py) | 默认对象创建、辅助代码、自定义类、工况和任务编辑 |
| [`application/edit_history.py`](../../src/morphopt/ui/application/edit_history.py) | 不可变编辑快照与分支历史 |
| [`application/fields.py`](../../src/morphopt/ui/application/fields.py)、[`values.py`](../../src/morphopt/ui/application/values.py) | 可编辑字段、选项及数值文本 |
| [`application/expressions.py`](../../src/morphopt/ui/application/expressions.py)、[`part_sets.py`](../../src/morphopt/ui/application/part_sets.py) | 表达式上下文与 Part 集合查询 |
| [`application/cad.py`](../../src/morphopt/ui/application/cad.py)、[`cad_worker.py`](../../src/morphopt/ui/cad_worker.py) | CAD 几何预览、STEP 导出与部件转换进程 |
| [`application/updaters.py`](../../src/morphopt/ui/application/updaters.py) | 子优化器分节及有序条目编辑 |
| [`application/quickstart.py`](../../src/morphopt/ui/application/quickstart.py)、[`schemes/`](../../src/morphopt/ui/schemes) | 起始问题构造与方案策略 |
| [`codegen/`](../../src/morphopt/ui/codegen) | Python 生成及自定义类投影 |
| [`application/runs.py`](../../src/morphopt/ui/application/runs.py)、[`launcher.py`](../../src/morphopt/ui/launcher.py) | 任务来源、运行会话与进程基础设施 |

结果读取、独立有限元和场量服务集中见[结果专题](results.md)，本篇说明定义编辑到任务启动的应用流程。

<a id="section-定义会话与文件入口"></a>

## 2 定义会话与文件入口

`ProblemSession` 持有当前 `ProblemDefinition` 和 `EditHistory`。

| 接口 | 责任 |
|---|---|
| `replace()` | 替换定义并建立历史起点 |
| `synchronize()` | 解析引用并对齐曲面相关配置 |
| `source()` | 按需同步后生成当前 Python |
| `validate_for_run()` | 执行生成校验与必需引用检查 |
| `record_edit()`、`restore_edit_step()` | 提交和恢复定义快照 |
| `set_label/result_folder/device()` | 修改任务配置 |

`ProblemLibrary` 是创建空白定义、选择方案、打开/保存 `.morph`、导出 Python 和保存运行伴随定义的文件入口。对话框由窗口提供路径，服务层负责文件内容。

字段编辑、结构操作和恢复历史分别触发相应同步。刷新组件消费已同步的上下文，不各自重复调用生成与领域同步。

<a id="section-编辑命令与参数查询"></a>

## 3 编辑命令与参数查询

| 类型或服务 | 责任 |
|---|---|
| `DefinitionCommands` | 使用领域默认值创建 Part、曲面、材料、载荷、CAD 与更新器条目 |
| `set_node_field()`、`rename_node()` | 统一字段写入及名称路由 |
| `HelperCodeSession` | 保存并校验辅助代码、变量与函数 |
| `CustomClassSession` | 类与方法创建、改名、删除及引用同步 |
| `LoadCaseSession` | 工况矩阵的列、值、复制、数量和删除操作 |
| `SolverTasks` | 任务分组与表格分配转换 |
| `UpdaterItems` 等有序项服务 | 目标、罚函数和曲面对称的增删排序 |
| `PartSetCatalog` | 按实际 Part 类型查询节点集、表面集和单元块 |

集合查询按所属 Part 选择 provider，不能用“整个问题是否存在 INPPart”决定其他部件的集合选项。引用字段允许空值；模板和 Quickstart 显式指定目标，运行前检查必需引用。

`DefinitionValues` 构造辅助变量、函数及表达式求值的命名空间，为预览和 CAD 操作转换提供当前定义值。字段表达式的保存表示与预览求值结果分别管理，生成脚本保留对应 Python 表达式。

<a id="section-编辑历史与恢复"></a>

## 4 编辑历史与恢复

`EditSnapshot` 保存与 `.morph` 相同结构的 UTF-8 JSON 字节、操作描述及轻量选择路径。快照不与当前模型共享可修改列表，也不保存网格或结果。

```text
同步后的定义 → snapshot() → EditHistory.commit()
                                    ├── 同次连续输入可合并
                                    └── 撤销后编辑形成新分支
历史步骤 ID → 解码快照 → ProblemDefinition.from_dict()
                         → 恢复导航位置 → 统一刷新
```

`EditHistoryNode` 以稳定 ID 关联父节点、有序子节点和首选重做分支。相同 JSON 不新增记录；容量与字节数限制由配置控制，超限时沿当前分支提升根节点，当前状态始终保留。

恢复先成功解码目标快照，再移动历史游标。恢复前提交正在编辑的值、取消旧刷新请求，再将各表单绑定到新对象。选择位置由导航路径描述，不依赖旧对象的 Python `id()`。

新建、打开和 Quickstart 建立新起点；保存标记已保存内容，但保留历史分支。相机、语言和选择变化不进入文档历史。优化进程、外部文件及结果状态不随定义撤销回滚。

<a id="section-quickstart-与方案策略"></a>

## 5 Quickstart 与方案策略

`application/quickstart.py` 的类型化配置进行输入校验，生成几何、材料、载荷工况、加权目标与更新器。`ObjectiveDraft` 维护目标和压力通道草稿；`model/chamberlayout.py` 维护分层气腔排布。输出仍为普通 `ProblemDefinition`，设置可保存为辅助变量 `quickstart_settings`。

`SchemeTemplate` 提供共享节点工厂、类型选项及目标代码片段，内置策略在 `schemes/base.py` 注册。新增策略是 Python 类注册，不以新增 `.morph` 文件注册方案。

几何工厂与网格生成由内核实现，Quickstart 组合现有 Part/曲面类型。工作空间目标的边界积分点与权重由 `optcore/quadrature.py` 提供，应用层将压力通道映射为载荷工况和目标中的 Jacobian 列。

<a id="section-代码生成边界"></a>

## 6 代码生成边界

`codegen/generator.py` 将同步后的定义投影为标准 `ThisController`。生成器读取模型，不将生成时的临时状态写回定义。

`codegen/assets.py` 统一收集 STL、INP 和 STEP 资源，返回节点到相对路径的映射及 `DefinitionAsset` 记录。记录包含类别、格式、文件内容、来源、关联节点及引用位置。资源名称仅由当前定义与文件内容确定。代码预览、资产页和文件导出使用同一清单；`ProblemLibrary.export_python()` 负责将源码和资源写入磁盘。文件覆盖确认由界面处理。

| 定义内容 | 生成位置 |
|---|---|
| Part、Instance、Surface、CAD 操作 | `Params.GeometryParams` 及对应 Part 子类 |
| 载荷和工况 | `Params.FEAParams` |
| 材料接口与本构参数 | `Params.MaterialsParams` |
| 损失、指标、Jacobian 选择 | `ObjectiveFunction` |
| 设备与任务组 | `Solver` 构造 |
| 几何和材料更新配置 | `Updater` 及子优化器类 |
| 辅助代码与自定义类 | 模块级定义及配置类的继承入口 |

生成调用沿用内核注册顺序和引用名称。相同定义应得到相同文本；`.morph` 是可编辑源，Python 是单向输出，不承担反向重建任意任务的职责。

<a id="asset-previews"></a>

资产页位于 `widgets/asset_browser.py`，按类别注册预览组件。`AssetBrowser.register_preview(category, title_key, factory)` 指定类别标识、语言文本键及组件工厂；组件继承 `AssetPreview` 并实现 `set_asset(asset, problem)`，可通过 `apply_language()` 和 `apply_theme()` 响应界面切换。新增类别的收集逻辑应返回对应的 `DefinitionAsset`，其显示逻辑由注册组件处理。

内置的 `GeometryAssetPreview` 使用 `visualization/assets.py` 将 STEP、STL 和 INP 内容转换为场景，再复用 `PreviewRenderer` 绘制。STEP 场景复用 CAD 面片合并逻辑；INP 场景沿用其关联节点的部件选择。组件在资产页可见且选中条目时创建，隐藏页不额外创建渲染窗口。清单刷新保留当前选择，内容不变时保留已显示场景与视角。

<a id="custom-classes"></a>

## 7 自定义类的选择与绑定

`codegen/custom_classes.py` 解析框架父类、生成配置类位置、方法签名与用户方法体。类目录和方法校验不执行用户方法体；表达式预览的求值属于另一条应用路径。

| 选择对象 | 保存位置 | 投影方式 |
|---|---|---|
| Controller、Params 等固定配置位置 | 固定路径绑定或对应节点字段 | 生成配置类继承选定类 |
| ObjectiveFunction | `ObjectiveNode.custom_class` | 生成目标类继承选定实现 |
| Part、曲面、材料等条目 | `Node.custom_class` | 当前条目的构造表达式使用选定类 |
| 单个几何/材料子优化器 | 配置字典的 `custom_class` | 根据当前配置顺序生成对应嵌套类 |
| 子目标或约束条目 | 条目配置 | 按条目创建选定实现 |

子优化器绑定与配置对象共同保存，不以可变化的列表索引作为持久化业务身份。生成时计算嵌套类路径，调整条目顺序后仍保持原对象选择的类。

创建一个自定义类不会自动替换全部同类型对象。类改名、删除和兼容性检查由共用服务处理，展示层只提供类目录和选择控件。

<a id="cad"></a>

## 8 CAD 转换与 STEP 导出

`application/cad.py` 将 CAD 节点转换为原生 `torchfea.cad` 操作，供预览与导出复用。`export_cad_step(node, path, problem)` 使用当前表达式上下文解析有序操作，再调用 `torchfea.cad.export_step()`。STEP 导出不构建 FE 网格，不改变问题树或编辑历史；保存对话框、扩展名筛选与覆盖确认由 `widgets/file_dialogs.py` 处理。

`convert_cad_to_boundary(node: CADPartNode, problem: ProblemDefinition, asset_directory: str | Path) -> BoundaryPartNode` 通过同一 `ProblemLibrary.export_python()` 生成任务源码和资产，载入已启用自定义类的几何定义，只初始化目标 CADPart，再调用内核的 `to_boundary_part()`。各封闭壳体生成 STEP 与面映射，应用服务将其嵌入 `BREPSurfaceNode`，返回待提交的 BoundaryPart。服务不修改源问题。

`DefinitionActions.convert_cad_to_boundary(part: CADPartNode) -> None` 为编辑卡片和树菜单提供共同入口。动作冻结当前问题，使用 `QProcess` 启动 `cad_worker.py`；工作进程读取快照并生成替换节点。成功后，主线程通过 `ProblemDefinition.replace_part()` 保留实例对象并重定向模型关联，再提交一次可撤销的编辑。进度窗口可取消；失败、取消或源问题已切换时不提交转换结果。临时源码和资产在转换结束后清理，当前定义通过内嵌数据持有 BREP 资产。

<a id="runs"></a>

## 9 优化运行会话

`RunSourceKind`、`RunSource` 与 `RunMode` 表达定义、Python 或已有结果等任务来源。`OptimizationRunSession` 持有唯一活动 `subprocess.Popen`、输出消费状态、结果目录发现和续跑来源。

从界面定义启动时，运行会话创建一份独立定义快照。`launcher.run_job()` 调用与手动导出共用的 `export_python_bundle()`，在独立临时目录中生成脚本和 `morphopt_assets`，随后启动该脚本。控制器将脚本及资源复制到结果目录的 `scripts/` 中。引用检查在启动前执行，完整代码校验在实际生成脚本时执行。

```text
选择任务来源 → 冻结定义/脚本快照 → 启动独立进程
                     → 输出采集与 poll() → RunProgress
                     → 结果目录发现 → 观察页读取归档
停止/退出 → 停止进程组 → 保留完整结果与可续跑来源
```

`ObserverControls` 接入按钮、对话框、定时器与 Qt 信号，消费会话的进度；不保存另一份进程状态。输出读取在后台完成，UI 线程不阻塞等待标准输出。

打开结果只准备浏览与继续计算，不自动启动任务。切换页面不启动、停止或重置进程；运行中的定义快照与当前编辑定义分别持有，后续编辑不会改写正在执行的任务。
