# UI 领域模型

[代码结构导览](README.md) · [UI 应用服务](ui-application.md) · [UI 展示与刷新](ui-presentation.md)

## 目录

<!-- docs:toc depth=1 -->

- [1 源码入口](#section-源码入口)
- [2 定义树与导航树](#section-定义树与导航树)
- [3 类型、字段与注册](#section-类型字段与注册)
- [4 对象引用与名称投影](#section-对象引用与名称投影)
- [5 聚合操作与结构不变量](#section-聚合操作与结构不变量)
- [6 `.morph` 边界与兼容处理](#section-morph-边界与兼容处理)
- [7 具名工况的接口投影](#section-具名工况的接口投影)
- [8 分量字段与求解器参数](#section-分量字段与求解器参数)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 源码入口

| 路径 | 责任 |
|---|---|
| [`ui/model/base_nodes.py`](../../src/morphopt/ui/model/base_nodes.py) | 通用 Node、字段访问和节点家族基类 |
| [`ui/model/node_types/`](../../src/morphopt/ui/model/node_types) | 可持久化的具体节点 |
| [`ui/model/fields.py`](../../src/morphopt/ui/model/fields.py) | 不可变字段元数据 `FieldSpec` |
| [`ui/model/registry.py`](../../src/morphopt/ui/model/registry.py) | kind、多态家族与菜单类型注册 |
| [`ui/model/problem.py`](../../src/morphopt/ui/model/problem.py) | `ProblemDefinition` 聚合与跨节点操作 |
| [`ui/model/configuration.py`](../../src/morphopt/ui/model/configuration.py) | 更新器等默认配置的创建 |
| [`ui/model/loaders.py`](../../src/morphopt/ui/model/loaders.py) | `.morph` 文件边界 |
| [`ui/model/material_models.py`](../../src/morphopt/ui/model/material_models.py) | 后端材料模型及可见参数描述 |

<a id="section-定义树与导航树"></a>

## 2 定义树与导航树

`ProblemDefinition` 是可保存定义的聚合根，包含问题标签、路径、设备、持久化节点树、辅助代码和自定义类。

```text
ProblemDefinition
├── root: ProblemNode
│   ├── GeometryNode → PartNode*
│   │   ├── instances: InstanceNode*
│   │   ├── surfaces: SurfaceNode*       仅边界部件
│   │   └── operations: CADOperationNode*仅 CAD 部件
│   ├── LoadsNode → FEAComponentNode*
│   ├── StepsNode
│   ├── MaterialsNode → MaterialNode*
│   ├── ObjectiveNode
│   ├── SolverNode
│   └── UpdaterNode → geometry / materials 配置列表
├── helper_code / helper_variables / helper_functions
└── custom_classes / class_bindings
```

星号表示有序集合。节点树表达模型内容，界面中的 Controller、Params、辅助代码分组和更新器条目由 `presentation/navigation.py` 投影。临时导航节点不插入持久化树，不改变 `.morph` 的章节结构。

`Node.children` 提供统一遍历，实际子对象由各容器的显式类型化成员保存，例如 `parts`、`instances`、`surfaces` 和 `operations`。叶节点不接受任意子节点，根节点维护唯一的标准章节。

<a id="section-类型字段与注册"></a>

## 3 类型、字段与注册

| 机制 | 约定 |
|---|---|
| `kind` | 稳定的节点种类，用于路由和序列化 |
| 具体 Python 类 | 表达 Part、Surface、材料或载荷的后端类型 |
| `fields` | 字段元数据，描述 key、默认值、编辑类型及标签等信息 |
| 类型化属性 | 保存实际字段值与对象引用 |
| `NODE_TYPES` | 恢复唯一 kind 对应的节点类型 |
| `NODE_FAMILIES` | 恢复共用 kind 下的多态类型 |

具体字段在 `node_types/` 声明，字段元数据类型由 `model/fields.py` 提供。共享元数据由模型节点、动态表单、菜单和生成器消费。枚举值或字段默认值的变更应同时核查后端参数契约。

`Node.custom_class` 保存适用节点选用的自定义类。根级配置和子优化器还使用各自的绑定位置，详细生成规则见[自定义类](ui-application.md#custom-classes)。

<a id="section-对象引用与名称投影"></a>

## 4 对象引用与名称投影

内存中的领域关系保留对象引用，持久化和代码生成时再投影为名称。

| 关系 | 内存目标 | 边界名称 |
|---|---|---|
| 载荷 → 实例/RP/曲面 | 对应节点 | `instance_name`、`rp_name`、`surface_name` 等 |
| 材料 → Part | Part 节点 | `part_name` |
| 几何更新器 → Part | 配置中的目标节点 | 目标 Part 名 |
| 材料更新器 → 材料接口 | 配置中的目标节点 | 目标材料名 |
| 目标/Jacobian → 载荷或 RP | 对应引用 | 生成脚本使用的名称 |

`resolve_references()` 从边界名称恢复对象关系，并清理失效关联。未解析的名称与对象引用应分别处理，不能依靠带类名的显示标题恢复引用。

UI Part 只有一个可编辑名称，`assembly_name` 是派生值。`rename_part()` 不更改已有实例名；实例通过 `rename_instance()` 独立改名。材料和更新器持有 Part 对象引用，部件改名后读取其当前名称。

<a id="section-聚合操作与结构不变量"></a>

## 5 聚合操作与结构不变量

| 操作类别 | 当前入口 |
|---|---|
| 查询 | `parts()`、`surfaces()`、`fea_components()`、`material_nodes()`、`instance_names()` |
| 所属关系 | `owner_of_surface()`、`owner_of_instance()`、`owner_of_cad_operation()` |
| 引用设置 | `set_component_reference()`、`set_material_part()`、`set_*_updater_target()` |
| 对象改名 | `rename_definition()`、`rename_part()`、`rename_instance()` |
| 结构编辑 | `add/clone/remove/move` 对应 Part、Instance、Surface、载荷、材料及 CAD 操作 |
| 曲面相关状态 | `align_surface_dependent_state()` |
| 持久化 | `to_dict()`、`from_dict()` |

部件、实例、材料和载荷在各自范围内检查名称有效性。曲面索引在所属边界 Part 内局部编号，增删排序后同步调整距离矩阵及对称条目的曲面索引。`is_updatable` 保存在曲面对象中，随对象移动，不需要按索引同步开关列表。

删除目标对象时，通过聚合操作处理引用与相关配置，不能只从展示列表中移除条目。UI 结构按钮与树菜单应调用相同的应用命令或聚合方法，不直接维护第二套关联表。

<a id="section-morph-边界与兼容处理"></a>

## 6 `.morph` 边界与兼容处理

当前 `ProblemDefinition.to_dict()` 写入版本 4：根节点、方案标识、任务/设备配置、辅助定义和自定义类。`from_dict()` 恢复类型化节点及引用，`loaders.py` 负责文件读写。

文件导入采用 `loaders._DefinitionReader` 将内容投影到当前 schema：支持字段保留，缺失字段使用当前工厂默认值，额外字段和不支持条目被忽略并记录原因。`ProblemLibrary.load(..., issues=...)` 返回定义及汇总问题，窗口显示一个可展开详情的警告。格式不是对象或 JSON 语法无效时仍报告读取错误；导入后继续进行普通定义校验。

该宽容策略仅属于外部文件边界。`Node.from_dict()`、内部快照恢复与领域构造保持严格，不将不完整数据处理分散到各控件或内核。导入器不恢复已移除算法的语义，不保证被忽略的参数仍具有效果。再次保存得到当前格式。

定义文件只保存声明内容，不包含网格缓存、VTK actor、历史导航状态或独立有限元结果。编辑历史以同一序列化表示保存快照，但历史树本身不写入 `.morph`。

新字段需同时覆盖构造、读写字段、序列化与恢复路径。新多态类型需登记节点注册表，并明确其可更新能力、后端类和适用编辑器。具体流程见[扩展与维护](development.md)。

具名工况由 `StepsNode.step_values` 按注册顺序保存，键为唯一字符串。目标、指标及求解器任务组引用名称。工作空间目标记录生成工况的归属，应用服务在配置变化及目标删除时检查引用并清理无引用的生成工况。

当前 `.morph` 格式版本为 4，工况使用字符串键保存；仓库内算例已同步更新。旧版或其他版本文件按上述导入规则读取支持部分，并报告不能保留的内容。

<a id="section-具名工况的接口投影"></a>

## 7 具名工况的接口投影

`StepsNode.step_values` 是工况幅值的唯一数据来源。`LoadCaseNode` 仅持有所属 `StepsNode` 与该工况字典引用，在导航中显示为 `name [LoadCase]`，不登记第二份持久化节点。名称通过字典身份解析，改名、排序和重新生成导航后保持同一编辑目标。`resolve_references()` 原位更新工况字典，避免卡片持有失效副本。

`LoadCaseNode.parameters()` 从各载荷的 `value_fields` 取得具名标量字段；字段键形如 `载荷名.参数名`，读写通过 `LoadCaseSession` 定位原始参数列表。Tree、卡片和生成代码共用该数据，文件结构仍是字符串键的工况映射。

<a id="section-分量字段与求解器参数"></a>

## 8 分量字段与求解器参数

`FieldSpec.components` 声明列表分量名称，`item_type` 声明列表项类型；节点继续保存原始列表，UI 通过 `SequenceInput` 分量编辑。载荷的 `value_fields` 同时服务工况卡片、独立有限元载荷编辑和工作空间输入标签，避免分别维护参数顺序。

`PenaltyDoFNode.node_index` 和 `direction` 是由求解器自由度 `s` 推导的虚拟字段。实例使用 `s=3*node_index+direction`，参考点显示六个具名自由度。`fields_for_node()` 根据当前对象选择 UI 字段，持久化和代码生成仍只保存 `s`，不产生重复状态。
