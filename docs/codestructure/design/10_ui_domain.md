# 10. UI 领域模型

返回 [设计导览](../README.md)。另见已有的 [UI 架构规范](../ui.md)。

<a id="section-边界与状态所有权"></a>

## 1 边界与状态所有权

源码目录：`ui/model/`。UI 的业务真相是 `ProblemDefinition` 与其类型化 `Node` 树；Qt widget 只是这棵树的编辑器，Python 脚本是由它确定性生成的产物，`.morph` 是它的持久化表示。

```text
.morph ──load──► ProblemDefinition ──generate──► ThisController Python
                     ▲       │
                     │       └── UI widgets edit typed nodes
                 template
```

每个领域关系保留对象引用：载荷接口保留目标 instance、surface、参考点等 Node；材料保留目标 Part Node；更新器配置保留目标 Part/材料 Node。序列化时将引用转换为名称，读取时由 `resolve_references()` 恢复对象关系。这样 UI 的重命名操作可以集中更新关联状态。

<a id="section-基础节点node"></a>

## 2 基础节点：`Node`

源码：`ui/model/base_nodes.py`、`ui/model/node_types/`。

| 状态 | 说明 |
|---|---|
| `kind` | 节点稳定种类，用于路由、序列化和 schema。 |
| `name` | 用户可见的注册名称。 |
| `fields` | `tuple[FieldSpec, ...]`：不可变的编辑元数据；参数值存储在节点的类型化属性中。 |
| `children` | 只读的子节点遍历元组，由各容器的显式成员集合组成。 |

| 公开方法 | 职责 |
|---|---|
| `field_names/has_field/get_field/set_field/field_items` | 访问和更新字段。 |
| `add_child/remove_child` | 管理树结构。 |
| `iter_nodes/find` | 遍历或查询子树。 |
| `to_dict/from_dict/clone` | 将业务树转换为持久化数据或副本。 |

`Node` 负责通用树操作；领域节点把类型、引用和结构约束封装在领域方法中。

<a id="section-问题树"></a>

## 3 问题树

```text
ProblemNode
├── GeometryNode
│   ├── PartNode.instances: InstanceNode*
│   ├── BoundaryPartNode.surfaces: SurfaceNode*（并拥有 instances）
│   └── CADPartNode.operations: CADOperationNode*（并拥有 instances）
├── LoadsNode
│   └── FEAComponentNode*
├── StepsNode
├── MaterialsNode
│   └── MaterialNode*
├── ObjectiveNode
├── SolverNode
└── UpdaterNode
     ├── geometry config*
     └── materials config*
```

| 节点 | 关键状态与公开方法 |
|---|---|
| `ProblemNode` | 根节点；`add_section()`、`section()`、`sections()` 管理唯一章节。 |
| `GeometryNode` | `parts: list[PartNode]`；`add_interface()`、`owner(surface)`、`surfaces()`。 |
| `PartNode` | `instances: list[InstanceNode]`、`assembly_name`、`instance_names`；`add_instance()`。 |
| `BoundaryPartNode` | `surfaces: list[SurfaceNode]`；`add_surface()`。 |
| `CADPartNode` | `operations: list[CADOperationNode]`；`add_cad_operation()`、`live_cad_operations()`。 |
| `InstanceNode` | `translation`、`rotation` 字段与 `pose` 属性，规范为六维位姿。 |
| `SurfaceNode` | `surface_type`、`is_inner`；`create()` 从曲面 schema 创建。 |
| `LoadsNode` | `components: list[FEAComponentNode]`；`add_interface()`。 |
| `FEAComponentNode` | `interface_type`；`set_reference()`、`reference_name()`、`pending_reference_name()` 维护载荷目标引用。 |
| `StepsNode` | 载荷步数量与步值矩阵；`field_items()` 提供序列化字段。 |
| `MaterialsNode` | `assignments: list[MaterialNode]`；`add_material()`。 |
| `MaterialNode` | `material_type`、`part_name`；`set_part()` 与 `pending_part_name` 管理目标 Part 引用。 |
| `ObjectiveNode` | `jacobian_needed`、`objective_body`、`metrics_body` 三类用户代码/选择。 |
| `SolverNode` | 求解器、进程和任务分配字段。 |
| `UpdaterNode` | 几何/材料更新器配置；`add_geometry_config()`、`add_materials_config()`。 |

<a id="section-problemdefinition"></a>

## 4 `ProblemDefinition`

`ProblemDefinition` 是领域操作的唯一服务面。它拥有根节点、问题标签、结果路径和设备配置，并集中提供结构变换和引用同步。

| 类别 | 公开方法 |
|---|---|
| 查询 | `node()`、`nodes()`、`geometry`、`loads`、`steps`、`materials`、`objective`、`solver`、`updater`、`part_interfaces()`、`material_nodes()`、`interfaces()`。 |
| 引用名称 | `instance_names()`、`part_names()`、`reference_point_names()`、`element_names()`；集合选项由 `PartSetCatalog` 按所属 Part 提供。 |
| 引用 | `resolve_references()`、`set_interface_reference()`、`set_material_part()`、`set_geometry_updater_target()`、`set_material_updater_target()`。 |
| 结构编辑 | `add/remove/move/clone` Part、instance、surface、载荷接口、材料接口和更新器配置。 |
| 命名 | `suggest_*_name()`、`rename_instance()`、`rename_interface()`、`rename_part()`。 |
| 曲面一致性 | `align_surface_dependent_state()`、`add/clone/remove/move_surface()`。 |
| 持久化 | `to_dict()`、`from_dict()`。 |

`rename_interface()`、`rename_part()` 及其私有辅助函数统一更新注册名、默认 instance 名、载荷引用、材料目标、载荷步键和更新器目标。用户界面通过这些领域操作修改名称，保证树内每条引用始终指向有效对象。

<a id="section-schema导入模型与持久化"></a>

## 5 Schema、导入模型与持久化

| 文件 | 责任 |
|---|---|
| `base_nodes.py` | `Node`、共享字段行为和 Part/Surface/Load 等节点家族基类；不声明具体持久化类型。 |
| `node_types/` | 所有具体、可持久化节点的类声明，按结构、几何、载荷、材料和优化器分组。 |
| `fields.py` | 不可变的 `FieldSpec`，供节点声明和动态编辑器共同使用。 |
| `registry.py` | 显式注册具体 kind 与多态家族，供 `.morph` 恢复和编辑器菜单使用。 |
| `configuration.py` | 从节点默认值创建优化器配置。 |
| `material_models.py` | 枚举后端材料模型及其参数。 |
| `loaders.py` | `.morph` 文件读写，负责调用 `ProblemDefinition.to_dict/from_dict`。 |

具体节点类是字段与后端类型的唯一声明位置。例如 `CADPartNode` 继承 `PartNode`，额外声明 `operations`；`BoundaryPartNode` 额外声明 `surfaces`。容器直接管理这些类型化集合，`children` 只用于统一遍历和 JSON 保存。叶节点拒绝添加子节点，根节点显式保存唯一的 geometry、loads、steps 等章节。

新增类型时在 `node_types/` 对应领域文件中继承节点家族基类，声明类型化属性、`fields` 元组和后端类名，再将类加入 `registry.py` 的对应目录。唯一 kind 的节点登记在 `NODE_TYPES`；共用 kind 的节点登记在相应 `NODE_FAMILIES`。预览适配器按节点类注册，继承类型可以复用父类适配器。

<a id="section-领域不变量"></a>

## 6 领域不变量

1. Part 接口、instance、曲面、材料、载荷与更新器在各自拥有者中保持稳定顺序。
2. 每个引用字段拥有对象引用与序列化名称投影；`resolve_references()` 负责从名称恢复对象。
3. 默认 instance 与 Part 同名；`rename_part()` 在该关系仍为默认关系时同步更新 instance。
4. 每个边界 Part 的曲面索引局部编号；曲面增删移动时同步调整 `if_update`、距离矩阵等依赖状态。
5. `.morph` 只保存声明数据；模型预览/结果缓存不写入业务树。
