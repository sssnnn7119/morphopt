# 10. UI 领域模型

返回 [设计导览](../README.md)。另见已有的 [UI 架构规范](../ui.md)。

## 边界与状态所有权

源码目录：`ui/model/`。UI 的业务真相是 `ProblemDefinition` 与其类型化 `Node` 树；Qt widget 只是这棵树的编辑器，Python 脚本是由它确定性生成的产物，`.morph` 是它的持久化表示。

```text
.morph ──load──► ProblemDefinition ──generate──► ThisController Python
                     ▲       │
                     │       └── UI widgets edit typed nodes
                 template
```

每个领域关系保留对象引用：载荷接口保留目标 instance、surface、参考点等 Node；材料保留目标 Part Node；更新器配置保留目标 Part/材料 Node。序列化时将引用转换为名称，读取时由 `resolve_references()` 恢复对象关系。这样 UI 的重命名操作可以集中更新关联状态。

## 基础节点：`Node`

源码：`ui/model/problem.py`。

| 状态 | 说明 |
|---|---|
| `kind` | 节点稳定种类，用于路由、序列化和 schema。 |
| `name` | 用户可见的注册名称。 |
| `fields` | schema 驱动的普通字段字典。 |
| `children` | 有序子节点列表。 |
| `parent` | 父节点引用。 |

| 公开方法 | 职责 |
|---|---|
| `field_names/has_field/get_field/set_field/field_items` | 访问和更新字段。 |
| `add_child/remove_child/child/children_of` | 管理树结构。 |
| `iter_nodes/find` | 遍历或查询子树。 |
| `to_dict/from_dict/clone` | 将业务树转换为持久化数据或副本。 |

`Node` 负责通用树操作；领域节点把类型、引用和结构约束封装在自己的方法中。

## 问题树

```text
ProblemNode
├── GeometryNode
│   └── PartInterfaceNode
│        ├── InstanceNode*
│        └── SurfaceNode*
├── LoadsNode
│   └── InterfaceNode*
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
| `GeometryNode` | `add_interface()`、`interfaces()`、`owner(surface)`、`surfaces()`；拥有所有 Part 接口。 |
| `PartInterfaceNode` | `interface_type`、`spec`、`has_surfaces`、`resolved_part_name()`、`resolved_instance_names()`；`add_instance()`、`add_surface()`。 |
| `InstanceNode` | `translation`、`rotation` 字段与 `pose` 属性，规范为六维位姿。 |
| `SurfaceNode` | `surface_type`、`is_inner`；`create()` 从曲面 schema 创建。 |
| `LoadsNode` | `add_interface()`、`interfaces()`；拥有全部 FEA 接口。 |
| `InterfaceNode` | `interface_type`；`set_reference()`、`reference_name()`、`pending_reference_name()` 维护载荷目标引用。 |
| `StepsNode` | 载荷步数量与步值矩阵；`field_items()` 提供序列化字段。 |
| `MaterialsNode` | `add_material()`、`materials()`。 |
| `MaterialNode` | `material_type`、`part_name`；`set_part()` 与 `pending_part_name` 管理目标 Part 引用。 |
| `ObjectiveNode` | `jacobian_needed`、`objective_body`、`metrics_body` 三类用户代码/选择。 |
| `SolverNode` | 求解器、进程和任务分配字段。 |
| `UpdaterNode` | 几何/材料更新器配置；`add_geometry_config()`、`add_materials_config()`。 |

## `ProblemDefinition`

`ProblemDefinition` 是领域操作的唯一服务面。它拥有根节点、问题标签、结果路径和设备配置，并集中提供结构变换和引用同步。

| 类别 | 公开方法 |
|---|---|
| 查询 | `node()`、`nodes()`、`geometry`、`loads`、`steps`、`materials`、`objective`、`solver`、`updater`、`part_interfaces()`、`material_nodes()`、`interfaces()`。 |
| 模型摘要 | `imported_model_summary()`、`node_set_names()`、`surface_set_names()`、`element_set_names()`、`reference_point_names()`、`element_names()`。 |
| 引用 | `resolve_references()`、`set_interface_reference()`、`set_material_part()`、`set_geometry_updater_target()`、`set_material_updater_target()`。 |
| 结构编辑 | `add/remove/move/clone` Part、instance、surface、载荷接口、材料接口和更新器配置。 |
| 命名 | `suggest_*_name()`、`rename_instance()`、`rename_interface()`、`rename_part()`。 |
| 曲面一致性 | `align_surface_dependent_state()`、`add/clone/remove/move_surface()`。 |
| 持久化 | `to_dict()`、`from_dict()`。 |

`rename_interface()`、`rename_part()` 及其私有辅助函数统一更新注册名、默认 instance 名、载荷引用、材料目标、载荷步键和更新器目标。用户界面通过这些领域操作修改名称，保证树内每条引用始终指向有效对象。

## Schema、导入模型与持久化

| 文件 | 责任 |
|---|---|
| `schemas.py` | 所有节点/接口/材料/曲面类型的字段定义、默认值、编辑控件元数据与可选项。 |
| `loaders.py` | `.morph` 文件读写，负责调用 `ProblemDefinition.to_dict/from_dict`。 |
| `modelinfo.py` | 读取 TorchFEA `.npz`，生成 `TorchFEAModelSummary`、`PartSummary`、`InstanceSummary`，供 UI 选择集合与引用。 |

Schema 是新增可编辑类型的单一描述位置。每个新接口类型先定义 schema，再让领域节点、代码生成器和编辑器按照同一类型 ID 工作。

## 领域不变量

1. Part 接口、instance、曲面、材料、载荷与更新器在各自拥有者中保持稳定顺序。
2. 每个引用字段拥有对象引用与序列化名称投影；`resolve_references()` 负责从名称恢复对象。
3. 默认 instance 与 Part 同名；`rename_part()` 在该关系仍为默认关系时同步更新 instance。
4. 每个边界 Part 的曲面索引局部编号；曲面增删移动时同步调整 `if_update`、距离矩阵等依赖状态。
5. `.morph` 只保存声明数据；模型预览/结果缓存不写入业务树。
