# MorphOpt V4 UI 与 Codegen

本文件定义 UI 数据树、编辑器字段、任务源码生成和运行结果目录。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文定义 UI 与核心模型之间的前后端边界。UI 节点保存可编辑定义，编辑器负责字段和集合
选择，Codegen 将定义生成可执行 Python 任务，运行结果目录保存脚本、模型和历史结果。

### 目录

- [16. UI 数据模型](#16-ui-数据模型)
- [16.1 UI 类清单](#161-ui-类清单) 与 [16.1.1 ProblemDefinition](#1611-problemdefinition)
- [16.1.2 UI Node 属性](#1612-ui-node-属性)
- [16.2–16.5 编辑器](#162-part-编辑器)
- [16.6 应用外壳与工作台](#166-应用外壳与工作台)
- [16.7 代码编辑与片段](#167-代码编辑与片段)
- [16.8 任务启动与输出](#168-任务启动与输出)
- [16.9 Observer 与 Viewer](#169-observer-与-viewer)
- [16.10 I18nService](#1610-i18nservice)
- [16.11 UI 入口函数](#1611-ui-入口函数)
- [17. Codegen 和任务定义文件](#17-codegen-和任务定义文件)
- [17.1 Codegen 类](#171-codegen-类)、[17.2 生成顺序](#172-生成顺序)、[17.3 任务文件与结果](#173-python-任务定义和运行结果)、[17.4 状态保存](#174-状态保存和历史读取)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 用户编辑的 UI 节点、Part/材料/FEA/Updater 字段、代码槽和模板配置 |
| 输出 | `ProblemDefinition`、校验结果、Python 任务文件、运行目录、状态文件和历史读取入口 |
| 主要读者 | UI 节点/编辑器实现者、Codegen 实现者、任务启动器和结果观察器实现者 |
| 关联文档 | [总览与生命周期](01-04Overview.md)、[几何系统](05Geometry.md)、[运行时](13-14Runtime.md)、[History](15History.md)、[迁移验收](18-22ValidationMigration.md) |

## 16. UI 数据模型

UI 节点记录定义数据，核心运行时对象在生成任务时创建。

### 16.1 UI 类清单

| 类 | 实例属性重点 | 方法重点 |
|---|---|---|
| `ProblemDefinition` | geometry、materials、fea、solver、objective、updaters | 结构编辑、级联改名、校验、Python 源码生成 |
| `GeometryNode` | `Part` 集合、ReferencePoint 集合、公共参数 | `Part` 和 Assembly 级参考点注册与显示 |
| `PartNode` | name、type、BoundaryPart 的 `element_name`、导入 Part 的 `element_names` 或实体/壳元素名称、外表面、源数据 | 创建对应 `Part` |
| `InstanceNode` | name、translation、rotation | 创建/修改 `Instance` |
| `ReferencePointNode` | name、position | 创建 Assembly 级 `ReferencePoint` |
| `MaterialNode` | name、part_name、element_name、接口类型、参数 | 创建携带目标 `Part` 和元素类型的材料接口 |
| `FEANode` | FEA component 集合和 load steps | 创建 `FEAParams` |
| `FEAComponentNode` | name、type、目标名称、值 | 创建 FEA component |
| `LoadStepsNode` | step 数量、值矩阵 | 编辑 load steps |
| `ObjectiveNode` | objective code、metrics code、Jacobian | 编辑目标代码槽 |
| `UpdaterNode` | name、target_kind、target_name、updater 类型、局部约束、几何等式约束 | 创建 `UpdaterEntry`；根据 updater 类型显示对应的约束编辑字段 |
| `SolverNode` | process、devices、task groups、`reuse_previous_solution` | 创建 `Solver` 配置；默认 `None`，由几何设计变量自动判定 |

### 16.1.1 `ProblemDefinition`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_geometry` | `GeometryNode` | 空节点 | 几何定义树 |
| `_materials` | `list[MaterialNode]` | [] | 材料分配节点 |
| `_fea` | `FEANode` | 空节点 | FEA component 和 load step 定义 |
| `_solver` | `SolverNode` | 空节点 | 求解配置 |
| `_objective` | `ObjectiveNode` | 空节点 | 目标和灵敏度代码槽 |
| `_updaters` | `list[UpdaterNode]` | [] | updater 注册节点 |

#### 运行时属性（`__init__()` 声明，生成或校验时填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_node_index` | dict[str, object] | {} | 节点名称索引 |
| `_validation_errors` | list[str] | [] | 当前定义校验错误 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `geometry` | `GeometryNode` | 只读 | 内部维护 | 返回几何定义树 |
| `materials` | tuple[`MaterialNode`, ...] | 只读 | 内部维护 | 返回材料节点只读序列 |
| `fea` | `FEANode` | 只读 | 内部维护 | 返回 FEA component 和工况定义 |
| `solver` | `SolverNode` | 只读 | 内部维护 | 返回求解配置 |
| `objective` | `ObjectiveNode` | 只读 | 内部维护 | 返回目标和灵敏度代码槽 |
| `updaters` | tuple[`UpdaterNode`, ...] | 只读 | 内部维护 | 返回 updater 节点只读序列 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_part(part_node)` | None | - | 添加 `Part` |
| `clone_part(part_name, new_name)` | None | - | 深拷贝 Part 定义并重新建立内部引用 |
| `rename_part(old_name, new_name)` | None | - | 级联更新 Instance、材料和 updater 目标引用 |
| `remove_part(part_name)` | None | - | 删除 `Part` 和相关引用 |
| `add_instance(part_name, instance_node)` | None | - | 添加 `Instance` |
| `clone_instance(part_name, instance_name, new_name)` | None | - | 复制 Instance 变换并注册新名称 |
| `rename_instance(old_name, new_name)` | None | - | 级联更新 FEA component 目标引用 |
| `remove_instance(part_name, instance_name)` | None | - | 删除 `Instance` |
| `add_reference_point(node)` | None | - | 添加 Assembly 级参考点 |
| `rename_reference_point(old_name, new_name)` | None | - | 级联更新力、力矩、边界、耦合、弹簧和代码模板引用 |
| `remove_reference_point(name)` | None | - | 删除参考点及关联 FEA 引用 |
| `add_material(material_node)` | None | - | 添加材料 |
| `clone_material(material_name, new_name)` | None | - | 复制材料定义并生成独立 updater 绑定候选 |
| `rename_material(old_name, new_name)` | None | - | 级联更新材料 updater 目标 |
| `remove_material(material_name)` | None | - | 删除材料和 updater 引用 |
| `add_fea_component(component_node)` | None | - | 添加 FEA component |
| `clone_fea_component(component_name, new_name)` | None | - | 复制组件并扩展全部工况列 |
| `rename_fea_component(old, new)` | None | - | 级联更新 load steps 和 Jacobian |
| `remove_fea_component(name)` | None | - | 删除组件并收缩工况、Jacobian 和 updater 引用 |
| `add_updater(updater_node)` | None | - | 添加任意类型的 updater，并保存目标类别和目标名称 |
| `remove_updater(name)` | None | - | 删除 updater 注册节点 |
| `to_dict()` | dict[str, object] | - | 生成带 schema 版本的纯数据定义 |
| `from_dict(data)` | `ProblemDefinition` | - | 迁移并校验纯数据后创建定义树 |
| `validate()` | None | - | 执行完整定义校验 |
| `get_validation_errors()` | tuple[str, ...] | - | 读取最近一次定义校验结果 |
| `generate_source()` | str | - | 委托 CodeGenerator 生成可直接运行的任务定义源码 |
| `save_definition(target_path)` | pathlib.Path | - | 将版本化 `.morph` 定义写入目标地址 |
| `load_definition(source_path)` | None | - | 读取 `.morph` 定义、迁移 schema 并替换当前节点树 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_rebuild_node_index()` | None | 从定义树重建稳定路径索引并检查重名 |
| `_cascade_reference(kind, old_name, new_name)` | None | 依据引用类型统一执行重命名级联 |
| `_remove_dangling_references(kind, name)` | None | 删除目标后清理关联选择和代码生成配置 |

### 16.1.2 `DefinitionNode`

`DefinitionNode` 是所有 UI 定义节点的基类，只保存可序列化数据。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_node_id` | str | 自动生成 UUID | 跨重命名保持稳定的节点标识 |
| `_name` | str | - | 同级唯一业务名称 |
| `_node_type` | str | - | 稳定节点类型标识 |
| `_schema_version` | int | 当前版本 | 节点数据结构版本 |

#### 运行时属性（`__init__()` 声明，校验时填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_validation_errors` | list[str] | `[]` | 最近一次局部校验错误 |
| `_is_validated` | bool | False | 当前字段版本是否完成校验 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `node_id` | str | - | 只读 | 内部维护 | 返回稳定节点标识 |
| `name` | str | - | 只读 | 读写 | setter 校验非空名称并标记待校验 |
| `node_type` | str | - | 只读 | 内部维护 | 返回节点类型 |
| `schema_version` | int | - | 只读 | 内部维护 | 返回结构版本 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_field(field_name)` | object | - | 读取已经存在的可编辑字段 |
| `set_field(field_name, value)` | None | - | 经 schema 转换后更新字段并使校验状态失效 |
| `validate_local()` | tuple[str, ...] | - | 校验自身字段并保存结构化错误 |
| `get_validation_errors()` | tuple[str, ...] | - | 读取最近一次局部校验错误 |
| `generate_data()` | Mapping[str, object] | - | 生成持久化和 Codegen 使用的纯数据 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_coerce_field(name, value)` | object | 按节点 schema 转换单个字段 |
| `_validate_name()` | None | 校验业务名称格式 |

### 16.1.3 具体定义节点

具体节点只声明本领域构造字段和同名 property；运行时校验状态、外部接口和内部辅助函数继承
`DefinitionNode`。集合 property 返回 tuple 或只读视图，元素增删由 `ProblemDefinition`
统一执行。

#### 16.1.3.1 `GeometryNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_parts` | list[`PartNode`] | `[]` | Part 定义 |
| `_reference_points` | list[`ReferencePointNode`] | `[]` | Assembly 参考点定义 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `parts` | tuple[`PartNode`, ...] | - | 只读 | 内部维护 | 返回 Part 节点 |
| `reference_points` | tuple[`ReferencePointNode`, ...] | - | 只读 | 内部维护 | 返回参考点节点 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.2 `PartNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_type` | str | - | `BoundaryPart`、`INPPart`、`TorchFEAPart` 或 `OffsetShellPart` |
| `_fields` | dict[str, object] | `{}` | 与 Part 类型匹配的构造参数 |
| `_surfaces` | list[`SurfaceNode`] | `[]` | 生成型 Part 的有序曲面定义 |
| `_instances` | list[`InstanceNode`] | `[]` | Instance 定义 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_model_summary` | `TorchFEAModelSummary` 或 None | None | 隔离预览返回的导入模型摘要 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `part_type` | str | - | 只读 | 内部维护 | 返回 Part 类型 |
| `fields` | Mapping[str, object] | - | 只读 | 内部维护 | 返回构造参数只读视图 |
| `surfaces` | tuple[`SurfaceNode`, ...] | - | 只读 | 内部维护 | 返回有序曲面节点 |
| `instances` | tuple[`InstanceNode`, ...] | - | 只读 | 内部维护 | 返回 Instance 节点 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_model_summary(summary)` | None | - | 写入隔离预览返回的 TorchFEA 模型摘要 |
| `get_model_summary()` | `TorchFEAModelSummary` | - | 读取已经写入的模型摘要 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.3 `SurfaceNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_surface_type` | str | - | BSP、CPGEO 或 STL 具体曲面类型 |
| `_fields` | dict[str, object] | `{}` | 曲面构造参数和来源 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `surface_type` | str | - | 只读 | 内部维护 | 返回曲面类型 |
| `fields` | Mapping[str, object] | - | 只读 | 内部维护 | 返回曲面参数只读视图 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.4 `InstanceNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_translation` | tuple[float, float, float] | `(0, 0, 0)` | 平移向量 |
| `_rotation` | tuple[float, float, float] | `(0, 0, 0)` | 旋转向量 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `translation` | tuple[float, float, float] | - | 只读 | 读写 | 返回或设置平移向量 |
| `rotation` | tuple[float, float, float] | - | 只读 | 读写 | 返回或设置旋转向量 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.5 `ReferencePointNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_position` | tuple[float, float, float] | `(0, 0, 0)` | 全局参考点坐标 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `position` | tuple[float, float, float] | - | 只读 | 读写 | 返回或设置三维坐标 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.6 `MaterialNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_name` | str | - | 目标 Part |
| `_element_name` | str | - | 目标元素族 |
| `_material_type` | str | - | 材料接口类型 |
| `_fields` | dict[str, object] | `{}` | 本构和材料场参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `part_name`、`element_name`、`material_type` | str | - | 只读 | 读写 | 返回或设置材料目标与类型 |
| `fields` | Mapping[str, object] | - | 只读 | 内部维护 | 返回材料参数只读视图 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.7 `FEANode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_components` | list[`FEAComponentNode`] | `[]` | FEA component 定义 |
| `_load_steps` | `LoadStepsNode` | 空工况表 | 工况矩阵 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `components` | tuple[`FEAComponentNode`, ...] | - | 只读 | 内部维护 | 返回组件定义 |
| `load_steps` | `LoadStepsNode` | - | 只读 | 内部维护 | 返回工况矩阵节点 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.8 `FEAComponentNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_component_type` | str | - | 具体 FEA component 类型 |
| `_target` | Mapping[str, str] | `{}` | Instance、集合或 RP 名称引用 |
| `_default_values` | tuple[float, ...] | `()` | 默认工况值 |
| `_fields` | dict[str, object] | `{}` | 组件专用参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `component_type` | str | - | 只读 | 内部维护 | 返回组件类型 |
| `target` | Mapping[str, str] | - | 只读 | 读写 | 返回或替换目标名称映射 |
| `default_values` | tuple[float, ...] | - | 只读 | 读写 | 返回或设置默认工况值 |
| `fields` | Mapping[str, object] | - | 只读 | 内部维护 | 返回专用参数只读视图 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.9 `LoadStepsNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_rows` | list[dict[str, tuple[float, ...]]] | `[{}]` | 按工况排列的组件值 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `rows` | tuple[Mapping[str, tuple[float, ...]], ...] | - | 只读 | 内部维护 | 返回工况矩阵只读快照 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_step(source_index=None)` | None | - | 添加空工况或复制指定工况 |
| `remove_step(case_index)` | None | - | 删除工况并级联更新 load updater 和模板索引 |
| `set_component_values(case_index, component_name, values)` | None | - | 更新工况中的组件值 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_validate_matrix()` | None | 校验每行覆盖组件且值长度匹配 `num_values` |

#### 16.1.3.10 `ObjectiveNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_objective_code` | str | - | `compute_case_objective()` 方法体 |
| `_metrics_code` | str | - | `compute_case_metrics()` 方法体 |
| `_metric_names` | tuple[str, ...] | `()` | 展示指标稳定名称 |
| `_jacobian_needed` | tuple[str, ...] | `()` | 需要结果 Jacobian 的组件名称 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `objective_code`、`metrics_code` | str | - | 只读 | 读写 | 返回或设置英文 Python 方法体 |
| `metric_names`、`jacobian_needed` | tuple[str, ...] | - | 只读 | 读写 | 返回或设置稳定名称序列 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

#### 16.1.3.11 `UpdaterNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_target_kind` | str | - | boundary Part、offset Part、material 或 load |
| `_target_name` | str | - | owner 稳定名称 |
| `_case_index` | int 或 None | None | load owner 的工况索引 |
| `_updater_type` | str | - | 具体 updater 类型 |
| `_optimizer_options` | dict[str, object] | `{}` | 局部优化器配置 |
| `_local_constraints` | list[Mapping[str, object]] | `[]` | updater 专属约束定义 |
| `_regularization_terms` | list[Mapping[str, object]] | `[]` | 材料正则项 |
| `_equality_constraint` | str 或 None | None | 几何等式投影代码 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `target_kind`、`target_name`、`updater_type` | str | - | 只读 | 读写 | 返回或设置 owner 绑定与 updater 类型 |
| `case_index` | int 或 None | - | 只读 | 读写 | 返回或设置 load 工况索引 |
| `optimizer_options` | Mapping[str, object] | - | 只读 | 读写 | 返回或替换优化器配置 |
| `local_constraints`、`regularization_terms` | tuple[Mapping[str, object], ...] | - | 只读 | 内部维护 | 返回局部项定义 |
| `equality_constraint` | str 或 None | - | 只读 | 读写 | 返回或设置等式投影代码 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_local_constraint(definition)` | None | - | 添加与 updater 类型匹配的局部约束 |
| `remove_local_constraint(name)` | None | - | 删除指定局部约束 |
| `add_regularization(definition)` | None | - | 添加材料 updater 正则项 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_validate_target()` | None | 校验目标类别、名称、工况和 updater 类型组合 |

#### 16.1.3.12 `SolverNode`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_fields` | dict[str, object] | 求解器默认值 | maximum iterations、tolerance、process、devices、task groups 和初值复用配置 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 继承 `DefinitionNode` 的校验状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `fields` | Mapping[str, object] | - | 只读 | 内部维护 | 返回求解器配置只读视图 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 沿用 `DefinitionNode` 接口 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 沿用 `DefinitionNode` 辅助函数 |

### 16.1.4 `ProblemValidator`

`ProblemValidator` 在源码生成、预览和运行前执行同一套跨节点校验。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_schema_registry` | Mapping[str, object] | - | 节点类型到字段 schema 的只读注册表 |

#### 运行时属性（`__init__()` 声明，校验时填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_issues` | list[Mapping[str, object]] | `[]` | 最近一次按节点路径排序的校验问题 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `schema_registry` | Mapping[str, object] | - | 只读 | 内部维护 | 返回字段 schema 只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `validate(problem, model_summary=None)` | None | - | 执行局部、引用、覆盖、工况、代码 AST 和运行配置校验 |
| `get_issues()` | tuple[Mapping[str, object], ...] | - | 读取最近一次校验的问题代码、节点路径、字段和双语消息 key |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_validate_names(problem)` | None | 校验各注册域名称格式和唯一性 |
| `_validate_references(problem, summary)` | None | 校验 Part、Instance、集合、RP、材料和 updater 引用 |
| `_validate_load_steps(problem)` | None | 校验工况矩阵形状和参数化组件值 |
| `_validate_code_slots(problem)` | None | 解析 Python AST 并校验规定的方法返回契约 |
| `_validate_material_coverage(problem, summary)` | None | 校验每个可变形元素族具有唯一材料分配或显式豁免 |

`.morph` 文件采用 UTF-8、带 `schema_version` 的 JSON 数据，当前版本为 `2`。
`save_definition()` 调用 `ProblemDefinition.to_dict()` 并原子写入；`load_definition()` 校验
版本后调用 `ProblemDefinition.from_dict()`，版本不一致时拒绝加载，不提供旧版本数据迁移。
每次加载完成后立即运行 `ProblemValidator`，并保留未知扩展字段供同一插件版本恢复。
完整 schema 规则见 §17.5。

### 16.1.5 `NodeEditor`

`NodeEditor` 是所有字段编辑器和分类说明页实现的 UI 协议。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | 协议状态由具体编辑器保存 |

#### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 具体编辑器声明绑定状态 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| 空 | - | - | - | - | 协议不定义 property |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_node(node, problem)` | None | - | 绑定定义节点和所属问题并重建控件值 |
| `commit()` | None | - | 将当前控件值写回已绑定节点 |
| `validate()` | tuple[str, ...] | - | 返回当前编辑内容的字段错误 |

所有实现提供 `changed` 信号；用户提交有效变更后发送，程序化刷新期间保持静默。

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 协议不定义内部辅助函数 |

### 16.2 `Part` 编辑器

| `Part` 类型 | 编辑属性 |
|---|---|
| `BoundaryPart` | element_name、曲面顺序、外表面、网格参数、曲面代码、约束代码 |
| `INPPart` | 可选 element_names、INP 路径、源 `Part`、外表面、Instances |
| `TorchFEAPart` | 输出 `part_name`、可选 `element_names`、模型目录、文件名、单一源 Part、源实例选择和模型摘要 |
| `OffsetShellPart` | `solid_element_name`、`shell_element_name`、`source_surface` 布尔列表、`BoundaryPart` 属性、厚度、层数 |

`Instance` 编辑器只编辑名称、translation 和 rotation。外表面由 `Part` 编辑器编辑。
导入 `Part` 的元素名称编辑器按照 `C3D4`、`C3D6`、`C3D8`、`C3D10`、`C3D15`、`C3D20`
的顺序生成字段，未列入的类型按源模型顺序追加；用户不填写自定义名称时，代码生成器
直接使用排序后的源元素类型名称，并在生成前校验名称列表长度和唯一性。
`BoundaryPart` 的外表面选项包含每个 BSP 自动生成的
`surface_{i}_head`、`surface_{i}_bottom`、`surface_{i}_lateral` 和
`surface_{i}_all`，每个 CPGEO 自动生成的 `surface_{i}_all`，以及由
`exterior_surface` 命名的整体集合；默认名称为 `extern`。用户修改名称时，生成的
整体外表面集合同步使用新名称。

`ReferencePointNode` 挂在 `GeometryNode` 下，编辑名称和三维坐标，代码生成时调用
`GeometryParams.add_reference_point()`。集中力、集中力矩、参考点边界条件、耦合和弹簧编辑器
从已经注册的几何参考点名称中提供选择项。

#### 16.2.1 `PropertyEditor`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_schema_registry` | Mapping[str, object] | - | 节点字段、控件类型、双语标签和动态选项定义 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_node` | `DefinitionNode` 或 None | None | 当前节点 |
| `_problem` | `ProblemDefinition` 或 None | None | 当前问题 |
| `_widgets` | dict[str, QWidget] | `{}` | 字段名到编辑控件的映射 |
| `_is_refreshing` | bool | False | 程序化同步保护状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `schema_registry` | Mapping[str, object] | - | 只读 | 内部维护 | 返回字段 schema 只读视图 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_node(node, problem)` | None | `NodeEditor` | 按节点 schema 重建字段控件和动态选项 |
| `commit()` | None | `NodeEditor` | 转换并写回全部已修改字段 |
| `validate()` | tuple[str, ...] | `NodeEditor` | 校验字段类型、范围和动态引用 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_widget(field_schema)` | QWidget | 根据 bool、数值、文本、路径、选择、向量、矩阵或代码类型建立控件 |
| `_get_dynamic_choices(field_name)` | tuple[object, ...] | 从当前问题和模型摘要读取名称选择项 |
| `_browse_path(field_name)` | None | 使用字段 schema 规定的文件或目录对话框更新路径 |

#### 16.2.2 `TorchFEAModelEditor`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_torchfea_ui_command` | tuple[str, ...] | `(sys.executable, "-m", "torchfea.ui")` | TorchFEA 建模 UI 启动命令 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_node` | `PartNode` 或 None | None | 当前 TorchFEAPart 节点 |
| `_problem` | `ProblemDefinition` 或 None | None | 当前问题 |
| `_watcher` | QFileSystemWatcher 或 None | None | 模型目录监控器 |
| `_summary` | `TorchFEAModelSummary` 或 None | None | 当前模型摘要 |
| `_preview_meshes` | tuple[object, ...] | `()` | 隔离检查进程返回的预览网格 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `torchfea_ui_command` | tuple[str, ...] | - | 只读 | 内部维护 | 返回 TorchFEA UI 启动命令 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `launch_torchfea_ui()` | None | - | 显示“只需定义并导出 Assembly”提示后启动建模 UI 并监控目标目录 |
| `scan_directory()` | None | - | 在 worker 中扫描受支持模型文件并刷新选择列表 |
| `select_model(path)` | None | - | 检查模型、建立树/表摘要和预览网格，并把链接写回节点 |
| `add_part_links(source_part_names)` | None | - | 为选中的每个源 Part 建立独立 `TorchFEAPart` 节点并共享模型链接 |
| `add_reference_point_links(reference_point_names)` | None | - | 将选中源参考点的名称和坐标创建为 Assembly 级 `ReferencePointNode`，同名同坐标项复用已有节点 |
| `get_model_summary()` | `TorchFEAModelSummary` | - | 读取已经检查的模型摘要 |
| `get_preview_meshes()` | tuple[object, ...] | - | 读取已经建立的模型预览 |
| `set_node(node, problem)` | None | `NodeEditor` | 绑定 TorchFEAPart 节点并恢复目录监控 |
| `commit()` | None | `NodeEditor` | 将目录、文件、单一源 Part、实例选择和元素名称映射写回节点 |
| `validate()` | tuple[str, ...] | `NodeEditor` | 校验链接、schema、Part/Instance、参考点和集合摘要 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_inspect_in_worker(path)` | None | 在隔离进程反序列化模型并返回摘要/网格或结构化错误 |
| `_populate_summary(summary)` | None | 建立 Assembly→Part→Instance→集合树和规模表 |
| `_handle_directory_change()` | None | 对文件时间戳去抖后触发重新扫描 |

### 16.3 材料编辑器

材料定义与运行时对象的文档顺序保持为
[MaterialsParams](06Materials.md#61-materialsparams) →
[MaterialModels](06Materials.md#62-materialmodels) →
[MaterialParameters](06Materials.md#63-materialparameters) →
[BaseMaterialInterface](06Materials.md#64-basematerialinterface) →
[HomogeneousMaterial](06Materials.md#65-homogeneousmaterial) →
[SIMPFieldMaterial](06Materials.md#66-simpfieldmaterial)。

材料编辑器按以下顺序提供选项：

1. 选择 `part_name`；
2. 从目标 `Part` 的 `elems` 选择 `element_name`；
3. 选择 [`HomogeneousMaterial`](06Materials.md#65-homogeneousmaterial) 或
   [`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial)；
4. 选择参数类并填写全部参数；
5. 填写接口类型的附加字段。

材料节点最终注册到 [`MaterialsParams`](06Materials.md#61-materialsparams)，并通过
`add_material(interface, name)` 保存材料对象。材料对象始终携带 `part_name` 和
`element_name`；这两个字段在生成代码时与材料名称一起传入接口构造函数。
元素选项来自真实 `Part` 的 `elems`。形状优化页面显示几何变量和几何约束；密度场、
材料场和 `VolFrac` 只在 [`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial) 页面显示。

### 16.4 FEA 编辑器

FEA 编辑器中的类顺序与
[FEA 组件](07Fea.md)保持一致：
[`FEAParams`](07Fea.md#71-feaparams) →
[`BaseFEAComponent`](07Fea.md#72-basefeacomponent) → FEA component 子类 →
[`LoadStep`](07Fea.md#715-loadstep)。Solver 使用独立的 [08Solver.md](08Solver.md) 接口。

| 编辑内容 | 目标选择 |
|---|---|
| [`Pressure`](07Fea.md#73-pressure) | `Instance` + surface set |
| [`BodyForce`](07Fea.md#74-bodyforce) | `Instance` + `element_name` |
| [`ConcentratedForce`](07Fea.md#75-concentratedforce) | `ReferencePoint` |
| [`ConcentratedMoment`](07Fea.md#76-concentratedmoment) | `ReferencePoint` |
| [`BoundaryCondition`](07Fea.md#77-boundarycondition) | `Instance` + node set |
| [`BoundaryConditionRP`](07Fea.md#78-boundaryconditionrp) | `ReferencePoint` |
| [`Couple`](07Fea.md#79-couple) | `Instance` + `ReferencePoint` |
| [`SpringToGround`](07Fea.md#710-springtoground) | `ReferencePoint` + DOF |
| [`SpringBetweenRPs`](07Fea.md#711-springbetweenrps) | 两个 `ReferencePoint` + DOF |
| [`PenaltyDoF`](07Fea.md#712-penaltydof) | `Instance`/节点 + DOF |
| [`Contact`](07Fea.md#713-contact) | 两个 `Instance` + surface set |
| [`SelfContact`](07Fea.md#714-selfcontact) | 一个 `Instance` + surface set |
| [`LoadStep`](07Fea.md#715-loadstep) | FEA component 名称和 step 值 |

这些对象由 [`FEAParams`](07Fea.md#71-feaparams) 先执行
`define_components()` / `define_steps()`，再分别通过 `add_component()` 和
`set_step_*()` 注册。每个 component 在 `reinitialize(iteration, assembly)` 中解析
当前 `Instance`、surface、node set、element set 和参考点。
`rename_fea_component()` 级联更新 load step、Jacobian 和代码槽引用。参考点在几何编辑器中
定义，FEA 编辑器只提供参考点名称选择。

#### 16.4.1 `StepMatrix`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | 工况表结构来自当前 `FEANode` |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_node` | `LoadStepsNode` 或 None | None | 当前工况节点 |
| `_problem` | `ProblemDefinition` 或 None | None | 当前问题 |
| `_table` | QTableWidget 或 None | None | component × case 编辑表 |
| `_is_refreshing` | bool | False | 程序化更新保护状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| 空 | - | - | - | - | 工况状态由节点和表格接口维护 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_step(source_index=None)` | None | - | 新建工况或复制选中工况 |
| `remove_step(case_index)` | None | - | 删除工况并更新逐工况引用 |
| `set_node(node, problem)` | None | `NodeEditor` | 按 component 顺序和 `num_values` 建立工况表 |
| `commit()` | None | `NodeEditor` | 将全部单元格值写回 `LoadStepsNode` |
| `validate()` | tuple[str, ...] | `NodeEditor` | 校验行数、列数、数值长度和有限性 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_table()` | None | 建立稳定列顺序和向量编辑器 |
| `_cascade_case_indices()` | None | 同步 Objective、FEAUpdater 和片段上下文的工况索引 |

#### 16.4.2 `ObjectiveEditor`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_snippet_catalog` | `SnippetCatalog` | - | 目标和指标代码片段目录 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_node` | `ObjectiveNode` 或 None | None | 当前目标节点 |
| `_problem` | `ProblemDefinition` 或 None | None | 当前问题 |
| `_objective_editor` | `CodeEditor` 或 None | None | 目标方法体编辑器 |
| `_metrics_editor` | `CodeEditor` 或 None | None | 指标方法体编辑器 |
| `_active_editor` | `CodeEditor` 或 None | None | 当前片段插入目标 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `snippet_catalog` | `SnippetCatalog` | - | 只读 | 内部维护 | 返回代码片段目录 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `insert_snippet(snippet_id)` | None | - | 打开参数对话框并把渲染结果插入当前代码编辑器 |
| `set_node(node, problem)` | None | `NodeEditor` | 绑定目标代码、指标代码、Jacobian 选择和补全上下文 |
| `commit()` | None | `NodeEditor` | 写回代码槽、指标名称和 Jacobian 组件序列 |
| `validate()` | tuple[str, ...] | `NodeEditor` | 校验 AST、返回契约、指标数量和 Jacobian 引用 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_set_active_editor(editor)` | None | 保存最近光标所属编辑器 |
| `_build_jacobian_selector()` | None | 仅列出当前工况中具有参数值的 FEA component |

#### 16.4.3 `SolverEditor`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_device_detector` | Callable[[], tuple[str, ...]] | - | 返回 CPU 和当前可用 CUDA 设备 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_node` | `SolverNode` 或 None | None | 当前求解配置节点 |
| `_problem` | `ProblemDefinition` 或 None | None | 当前问题 |
| `_task_table` | QTableWidget 或 None | None | worker 到工况的分组表 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `device_detector` | Callable | - | 只读 | 内部维护 | 返回设备探测函数 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `detect_devices()` | tuple[str, ...] | - | 读取 CPU/CUDA 设备候选并保留稳定显示顺序 |
| `set_node(node, problem)` | None | `NodeEditor` | 绑定求解参数、设备和工况分组 |
| `commit()` | None | `NodeEditor` | 写回求解器配置 |
| `validate()` | tuple[str, ...] | `NodeEditor` | 校验 worker 数、设备和每个工况恰好出现一次 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_task_table()` | None | 按当前工况数和 worker 数建立分组编辑表 |

### 16.5 Updater 编辑器

~~~text
BoundaryPart updater: chamber_shape → BoundaryPart: chamber
OffsetShellPart updater: shell_shape → OffsetShellPart: shell
Material updater: solid_density → Material: solid (chamber / C3D4)
FEA updater: pressure_shape → FEA component: pressure_1
Custom updater: custom_name → custom target: custom_target
~~~

`UpdaterNode` 的目标选项由 `target_kind` 决定：边界几何目标来自 `BoundaryPart`，偏置几何目标
来自 `OffsetShellPart`，材料目标
来自 Materials，载荷目标来自可设计 FEA components，用户扩展目标来自对应扩展注册表。
每个目标实体只能创建一个 updater 节点；不同实体可以创建多个同类型 updater 节点。
选择 `BoundaryPart` 时生成 `BoundaryPartUpdater`，选择 `OffsetShellPart` 时生成
`OffsetShellPartUpdater`，编辑器根据 updater 类型显示对应的几何配置字段。

| `target_kind` | 目标选择器 | 生成的 updater |
|---|---|---|
| `boundary_part` | `BoundaryPart.part_name` | `BoundaryPartUpdater` |
| `offset_shell_part` | `OffsetShellPart.part_name` | `OffsetShellPartUpdater` |
| `material` | 可更新材料名称 | `MaterialUpdater` |
| `load` | 参数化 FEA component 名称 + `case_index` | `FEAUpdater` |

Updater 编辑器按目标类型显示固定局部灵敏度目标和可配置约束：

| updater | 局部目标（固定） | 局部约束（可配置） | 额外约束入口 |
|---|---|---|---|
| `BoundaryPartUpdater` | `LocalSensitivityObjective`（由顶层灵敏度自动建立） | updater 内的 `Fairness`、`Distance`、`MinRadius`、`Cylinder`、`VolumeMaximization` 回调 | updater 内的唯一等式投影回调 |
| `OffsetShellPartUpdater` | `LocalSensitivityObjective`（由顶层灵敏度自动建立） | updater 内的偏置 `Fairness`、`InwardCurvatureRadius`、`OffsetSurfaceMinThickness` 回调 | updater 内的唯一等式投影回调 |
| `MaterialUpdater` | `LocalSensitivityObjective`（由顶层灵敏度自动建立） | updater 内的 `MinValue`、`MaxValue`、`VolFrac` | `DensityFieldMinimize` 附加正则项 |
| `FEAUpdater` | `LocalSensitivityObjective`（由顶层灵敏度自动建立） | `FEAUpdater` 自己定义的局部约束回调 | 无 |

局部灵敏度目标由 Controller 分发灵敏度后自动建立；编辑器维护对应 updater
的 `local_constraints`、材料 `regularization_terms` 和几何 updater 的唯一 `equality_constraint`，并按 updater
类型校验约束参数和可用模板。等式约束代码字段保存 `(owner, trial_parameters) ->
projected_parameters` 的纯 Tensor 回调，代码生成器将其传给 `set_equality_constraint()`。

#### 16.5.1 `UpdaterEditor`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_constraint_schemas` | Mapping[str, object] | - | 各 updater 可用约束、参数和双语标签 |
| `_snippet_catalog` | `SnippetCatalog` | - | 等式投影与自定义约束代码片段 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_node` | `UpdaterNode` 或 None | None | 当前 updater 节点 |
| `_problem` | `ProblemDefinition` 或 None | None | 当前问题 |
| `_constraint_editors` | list[QWidget] | `[]` | 当前局部约束编辑控件 |
| `_equality_editor` | `CodeEditor` 或 None | None | 几何等式投影代码编辑器 |
| `_is_refreshing` | bool | False | 程序化同步保护状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `constraint_schemas` | Mapping[str, object] | - | 只读 | 内部维护 | 返回约束 schema 只读视图 |
| `snippet_catalog` | `SnippetCatalog` | - | 只读 | 内部维护 | 返回代码片段目录 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_constraint(constraint_type)` | None | - | 添加目标 updater 支持的一项局部约束 |
| `remove_constraint(name)` | None | - | 删除当前 updater 的一项局部约束 |
| `insert_equality_snippet(snippet_id)` | None | - | 渲染并插入镜面对称等式投影等代码片段 |
| `set_node(node, problem)` | None | `NodeEditor` | 绑定 owner、优化器、约束和等式投影配置 |
| `commit()` | None | `NodeEditor` | 将编辑值写回单个 UpdaterNode |
| `validate()` | tuple[str, ...] | `NodeEditor` | 校验 owner 唯一绑定、约束参数和代码返回形状 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_constraint_editor(definition)` | QWidget | 根据 updater 类型和约束 schema 建立参数控件 |
| `_refresh_target_choices()` | None | 更新可用 BoundaryPart、OffsetShellPart、材料和逐工况载荷 owner |

### 16.6 应用外壳与工作台

#### 16.6.1 `MainWindow`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_application_name` | str | `"MorphOpt UI"` | 窗口标题前缀 |
| `_default_language` | Literal["zh_CN", "en_US"] | `"zh_CN"` | 初始界面语言 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_workbench` | `Workbench` 或 None | None | 统一定义、运行和观察工作台 |
| `_current_path` | pathlib.Path 或 None | None | 当前 `.morph` 文件 |
| `_is_modified` | bool | False | 当前定义修改状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `application_name` | str | - | 只读 | 内部维护 | 返回应用名称 |
| `default_language` | str | - | 只读 | 内部维护 | 返回初始语言 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `new_problem(scheme_name)` | None | - | 从可用 scheme 建立新 `ProblemDefinition` |
| `open_definition(path)` | None | - | 加载 `.morph` 并交给工作台 |
| `save_definition(path=None)` | pathlib.Path | - | 保存当前定义并返回路径 |
| `export_source(path)` | pathlib.Path | - | 生成并导出可独立运行的 Python 任务 |
| `set_language(language)` | None | - | 切换翻译器并刷新当前可见文本 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_confirm_unsaved_changes()` | bool | 在替换当前问题前处理未保存状态 |
| `_update_window_title()` | None | 根据路径、修改状态和工作台模式刷新标题 |

`MainWindow` 只创建一个 `Workbench`。优化定义、运行输出和结果观察均在该工作台内切换，
应用入口统一为 `morphopt-ui` / `morphopt.ui.run_app()`。

#### 16.6.2 `Workbench`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_problem` | `ProblemDefinition` | - | 当前前端定义 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_model_tree` | `ModelTree` 或 None | None | 左侧任务树 |
| `_editor_stack` | `EditorStack` 或 None | None | 中部属性/代码编辑区 |
| `_viewer` | `Viewer` 或 None | None | 右侧统一三维视图 |
| `_console` | `OptimizationConsole` 或 None | None | 底部运行输出 |
| `_observer` | `ObserverPanel` 或 None | None | 结果观察控件 |
| `_mode` | Literal["definition", "running", "observation"] | `"definition"` | 工作台模式 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `problem` | `ProblemDefinition` | - | 只读 | 内部维护 | 返回当前定义 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_problem(problem)` | None | - | 替换定义并同步重建树、编辑器和预览 |
| `set_mode(mode)` | None | - | 切换定义、运行或观察布局 |
| `build_preview()` | None | - | 启动隔离预览任务并缓存模型摘要与网格 |
| `get_preview_meshes()` | tuple[object, ...] | - | 读取已完成预览网格 |
| `run_problem()` | None | - | 校验、生成源码并交给 TaskLauncher |
| `run_source(script_path, arguments=())` | None | - | 在统一工作台运行已有 V4 Python 任务文件 |
| `continue_problem(result_path, target_iteration=None)` | None | - | 使用结果 manifest 的任务文件从指定或最新完整 checkpoint 继续计算 |
| `stop_problem()` | None | - | 请求终止当前任务进程树 |
| `open_result(path)` | None | - | 在当前工作台进入观察模式并载入结果目录 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_select_editor(node)` | None | 根据叶节点类型显示唯一编辑器 |
| `_rebuild_tree()` | None | 依据 ProblemDefinition 重建稳定任务树 |
| `_refresh_name_sources()` | None | 更新 Part、Instance、集合、RP、材料和载荷选择器 |
| `_handle_runtime_event(event)` | None | 将结构化任务事件分发给 console、viewer 和 observer |

任务树的大类为“几何（初始模型）”“载荷”“材料”“求解器”“优化问题定义”。载荷大类包含
“载荷定义”和“载荷工况”；优化问题定义包含“优化目标”、各具体几何优化器和材料优化器。
每个几何优化器直接显示最大更新步数、曲面更新掩码、唯一等式约束和局部罚函数。树节点
括号只显示对应代码对象的最后一级类名。协同优化 scheme 从 V4 UI scheme 清单隐藏，
`OffsetShellPart` 和多 updater 的后端能力由通用编辑节点表达。

#### 16.6.3 `ModelTree`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_label_provider` | Callable[[`DefinitionNode`], str] | - | 根据当前语言生成节点显示文本 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_problem` | `ProblemDefinition` 或 None | None | 当前定义树 |
| `_item_to_node` | dict[object, `DefinitionNode`] | `{}` | Qt item 到定义节点的映射 |
| `_selected_node` | `DefinitionNode` 或 None | None | 当前选择节点 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `label_provider` | Callable | - | 只读 | 内部维护 | 返回双语标签提供器 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `build_tree(problem)` | None | - | 按稳定领域顺序建立任务树并写入 item 映射 |
| `get_selected_node()` | `DefinitionNode` 或 None | - | 读取当前选择节点 |
| `set_selected_node(node)` | None | - | 选择指定节点并确保该项可见 |
| `refresh_labels()` | None | - | 使用当前语言刷新已有节点文本 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_geometry_branch()` | None | 建立 Part、Instance、ReferencePoint 和曲面层级 |
| `_build_fea_branch()` | None | 建立载荷定义与载荷工况两个子节点 |
| `_build_optimization_branch()` | None | 建立优化目标和逐 owner updater 节点 |
| `_build_context_menu(node)` | object | 根据节点能力建立增删、复制、移动和重命名动作 |

任务树的大类顺序固定为几何、载荷、材料、求解器、优化问题定义；括号只显示对应代码对象的
最后一级类名。容器节点发送与叶节点相同的选择信号，并由 `EditorStack` 显示说明页。

#### 16.6.4 `EditorStack`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_editor_factories` | Mapping[type[`DefinitionNode`], Callable[[], `NodeEditor`]] | - | 节点类型到编辑器工厂的映射 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_editors` | dict[type[`DefinitionNode`], `NodeEditor`] | `{}` | 延迟建立并复用的编辑器 |
| `_current_editor` | `NodeEditor` 或 None | None | 当前可见编辑器或说明页 |
| `_current_node` | `DefinitionNode` 或 None | None | 当前编辑节点 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `editor_factories` | Mapping[type, Callable] | - | 只读 | 内部维护 | 返回编辑器工厂只读视图 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_editor(node_type, factory)` | None | - | 注册一个节点类型的编辑器工厂 |
| `update_selection(node, problem)` | None | - | 提交旧编辑器、绑定新节点并切换可见页面 |
| `commit()` | None | - | 将当前编辑器值写回定义节点 |
| `validate()` | tuple[str, ...] | - | 返回当前编辑器字段校验错误 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_get_or_build_editor(node_type)` | `NodeEditor` | 延迟创建并连接统一 `changed` 信号 |
| `_build_information_page(node)` | `NodeEditor` | 为容器节点建立实现同一编辑协议的说明页 |

所有编辑器实现 `NodeEditor` 协议的 `set_node(node, problem)`、`commit()`、`validate()` 和
`changed` 信号。这样分类说明页和字段编辑器共享同一连接边界。

### 16.7 代码编辑与片段

#### 16.7.1 `CodeEditor`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_language` | str | `"python"` | 编辑语言 |
| `_completion_delay_ms` | int | `120` | 输入停止到弹出补全的延迟 |
| `_indent_width` | int | `4` | Tab、Shift+Tab 和自动缩进使用的空格数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_completion_provider` | `CompletionProvider` 或 None | None | 当前上下文补全提供器 |
| `_popup` | Qt completion popup 或 None | None | 当前候选弹窗 |
| `_last_cursor_position` | int | `0` | 最近有效光标位置 |
| `_highlighter` | QSyntaxHighlighter 或 None | None | Python 语法高亮器 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `language` | str | - | 只读 | 内部维护 | 返回语言 |
| `completion_delay_ms` | int | - | 只读 | 内部维护 | 返回补全延迟 |
| `indent_width` | int | - | 只读 | 内部维护 | 返回缩进宽度 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_text(text)` | None | - | 设置编辑文本并把初始光标放到末尾 |
| `get_text()` | str | - | 读取当前编辑文本 |
| `set_completion_context(context)` | None | - | 更新工况数、组件、实例、RP、集合和 Tensor 类型信息 |
| `insert_snippet(text)` | None | - | 在当前光标插入代码；编辑器无焦点时使用最近光标，首次使用时插入末尾 |
| `show_completions(manual=False)` | None | - | 请求并显示当前表达式候选 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_extract_expression()` | str | 提取光标前 Python 属性链和索引表达式 |
| `_accept_completion(item)` | None | 替换当前前缀并保持光标位置 |
| `_handle_popup_event(event)` | bool | 保持键盘选择、鼠标选择和焦点转移期间弹窗稳定 |
| `_insert_newline_with_indent()` | None | 按当前代码块和冒号生成下一行缩进 |
| `_indent_selection()` | None | 对当前行或选区增加一级缩进 |
| `_unindent_selection()` | None | 对当前行或选区移除一级缩进 |

#### 16.7.2 补全与片段服务

`CompletionProvider` 根据语法上下文和 `ProblemDefinition` 动态生成候选：

| 上下文 | 候选来源 |
|---|---|
| `self.fe_results[` | `range(num_load_steps)` 中的全部工况索引 |
| `self.fe_results[i].` | `GC`、`jacobian`、能量、误差和收敛字段 |
| Tensor 表达式，例如 `.GC.` | 内置的稳定 `torch.Tensor` 方法白名单及参数提示 |
| `assembly.` | Instance、Part、RP、集合访问和广义坐标转换接口 |
| `assembly.get_instance(` | 实际 `instance_name` 字符串候选 |
| Jacobian 字典 | `jacobian_needed` 中已选参数化载荷名称 |

`SnippetCatalog` 保存 `SnippetDefinition(id, label_key, parameters, render)`；标签和参数说明由
i18n key 提供中英文，渲染后的 Python 代码保持英文。`SnippetInsertDialog` 根据 parameter
schema 创建下拉框、复选框和数值控件，选择项来自当前模型摘要。支持的基础片段为：

| 片段 | 参数 | 生成结果 |
|---|---|---|
| Instance 节点位移 | `case_index`、`instance_name` | `RGC[instance._RGC_index]` 全部节点位移 |
| ReferencePoint 位移/转角 | `case_index`、`reference_point_name` | 使用 `_GC_list_indexStart` 取得 6 个 GC 自由度 |
| Instance 参与力 | `case_index`、`instance_name` | 取得实例对应广义/冗余自由度上的力结果 |
| ReferencePoint 参与力/力矩 | `case_index`、`reference_point_name` | 取得参考点 6 分量反力 |
| 高斯点应变能 | `case_index`、`instance_name`、`element_name` | 返回目标元素全部高斯点应变能 Tensor |
| 高斯点变形梯度 | `case_index`、`instance_name`、`element_name` | 返回目标元素全部高斯点变形梯度 Tensor |
| 末端平移 | `reference_point_name`、`axis`、`sign` | 生成 x/y/z 正负方向位移目标代码 |
| 末端转动 | `reference_point_name`、`axis`、`sign` | 生成 x/y/z 正负方向转角目标代码 |
| 参考点刚度 | `case_index`、force、moment、RP、metric | 生成 `6 × 6` Jacobian 的迹、行列式、特征值、条件数或指定二次型 |
| 镜面对称等式投影 | `part_name`、曲面、平面轴、平面位置 | 返回投影后控制点的 updater 等式约束代码 |

高斯点张量片段返回完整 Tensor。刚度片段要求用户明确选择集中力、集中力矩和参考点；
对话框校验两种载荷都引用该参考点，并把二者加入 `jacobian_needed`。默认 scheme 保持载荷
定义由用户填写，片段插入操作只生成代码。

##### 16.7.2.1 `CompletionProvider`

###### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_tensor_members` | tuple[str, ...] | 内置稳定白名单 | 支持的 `torch.Tensor` 方法和属性 |

###### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_context` | Mapping[str, object] | `{}` | 当前工况、模型名称、结果字段和类型信息 |

###### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `tensor_members` | tuple[str, ...] | - | 只读 | 内部维护 | 返回 Tensor 候选白名单 |

###### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_context(context)` | None | - | 更新动态名称和类型上下文 |
| `complete(expression)` | tuple[Mapping[str, str], ...] | - | 根据当前表达式返回标签、插入文本和说明 |

###### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_infer_expression_type(expression)` | str 或 None | 识别 Tensor、StaticResult、Assembly 和 Jacobian 表达式 |
| `_deduplicate(items)` | tuple[Mapping[str, str], ...] | 按插入文本稳定去重并排序 |

##### 16.7.2.2 `SnippetParameter`

###### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | - | 代码渲染参数名称 |
| `_kind` | str | - | choice、integer、float、boolean 或 text |
| `_label_key` | str | - | 双语标签 key |
| `_source` | str 或 None | None | 动态选项来源标识 |
| `_default` | object | None | 默认值 |
| `_required` | bool | True | 是否必须提供值 |

###### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结参数记录仅保存构造状态 |

###### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `name`、`kind`、`label_key` | str | - | 只读 | 内部维护 | 返回参数标识、控件类型和标签 key |
| `source` | str 或 None | - | 只读 | 内部维护 | 返回动态选项来源 |
| `default` | object | - | 只读 | 内部维护 | 返回默认值 |
| `required` | bool | - | 只读 | 内部维护 | 返回必填状态 |

###### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 参数通过 property 读取 |

###### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结记录不定义辅助函数 |

##### 16.7.2.3 `SnippetDefinition`

###### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_snippet_id` | str | - | 全局稳定片段标识 |
| `_label_key` | str | - | 双语显示标签 key |
| `_parameters` | tuple[`SnippetParameter`, ...] | `()` | 有序参数 schema |
| `_renderer` | Callable[[Mapping[str, object]], str] | - | 英文 Python 代码渲染函数 |
| `_slots` | frozenset[str] | - | 允许插入的代码槽 |

###### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结片段定义仅保存构造状态 |

###### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `snippet_id`、`label_key` | str | - | 只读 | 内部维护 | 返回片段标识和标签 key |
| `parameters` | tuple[`SnippetParameter`, ...] | - | 只读 | 内部维护 | 返回参数定义 |
| `slots` | frozenset[str] | - | 只读 | 内部维护 | 返回允许代码槽 |

###### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `render(parameters)` | str | - | 校验参数完整性后生成英文 Python 代码片段 |

###### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_validate_parameters(parameters)` | None | 校验参数名称、类型和必填值 |

##### 16.7.2.4 `SnippetCatalog`

###### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_snippets` | dict[str, `SnippetDefinition`] | `{}` | 片段注册表 |

###### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 注册表在定义阶段维护 |

###### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `snippets` | Mapping[str, `SnippetDefinition`] | - | 只读 | 内部维护 | 返回片段只读注册表 |

###### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_snippet(snippet)` | None | - | 注册唯一片段标识 |
| `get_for_slot(slot_name)` | tuple[`SnippetDefinition`, ...] | - | 读取适用于指定代码槽的片段 |

###### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 注册和查询由外部接口完整表达 |

##### 16.7.2.5 `SnippetInsertDialog`

###### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_snippet` | `SnippetDefinition` | - | 当前片段定义 |
| `_context` | Mapping[str, object] | - | 动态名称和模型摘要上下文 |

###### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_editors` | dict[str, QWidget] | `{}` | 参数名到控件的映射 |
| `_rendered_text` | str 或 None | None | 已验证并渲染的代码 |

###### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `snippet` | `SnippetDefinition` | - | 只读 | 内部维护 | 返回当前片段定义 |
| `context` | Mapping[str, object] | - | 只读 | 内部维护 | 返回动态上下文只读视图 |

###### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_parameter_values()` | Mapping[str, object] | - | 读取当前控件中的规范化参数 |
| `get_rendered_text()` | str | - | 读取已经验证并渲染的代码片段 |
| `accept()` | None | - | 校验参数、跨对象关系和代码 AST 后保存渲染文本 |

###### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_parameter_editor(parameter)` | QWidget | 根据类型和动态来源建立控件 |
| `_validate_stiffness_selection(values)` | None | 校验 force、moment 与目标 RP 的绑定一致性 |

### 16.8 任务启动与输出

#### 16.8.1 `TaskLauncher`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_python_executable` | pathlib.Path | `sys.executable` | 当前环境 Python |
| `_working_directory` | pathlib.Path | - | 项目/任务工作目录 |
| `_environment` | Mapping[str, str] | `{}` | 在当前进程环境上覆盖的任务变量 |
| `_graceful_stop_timeout_ms` | int | `3000` | 优雅停止到强制回收的等待时间 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_process` | QProcess 或 None | None | 当前任务进程 |
| `_state` | Literal["idle", "starting", "running", "stopping"] | `"idle"` | 启动器状态 |
| `_stdout_decoder` | incremental decoder 或 None | None | 跨 chunk UTF-8 解码器 |
| `_stderr_decoder` | incremental decoder 或 None | None | 跨 chunk UTF-8 解码器 |
| `_last_exit_code` | int 或 None | None | 最近任务退出码 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `python_executable` | pathlib.Path | - | 只读 | 内部维护 | 返回任务解释器 |
| `working_directory` | pathlib.Path | - | 只读 | 内部维护 | 返回任务目录 |
| `environment` | Mapping[str, str] | - | 只读 | 内部维护 | 返回任务环境覆盖只读视图 |
| `graceful_stop_timeout_ms` | int | - | 只读 | 内部维护 | 返回优雅停止超时 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `start(script_path, arguments=())` | None | - | 使用当前 Python 启动生成任务并流式转发输出 |
| `stop()` | None | - | 先请求优雅终止，再按超时升级并回收整个进程树 |
| `get_state()` | str | - | 读取启动器状态 |
| `get_last_exit_code()` | int 或 None | - | 读取最近任务退出码 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_read_stdout()` | None | 增量解码标准输出并发送文本信号 |
| `_read_stderr()` | None | 增量解码标准错误并发送错误文本信号 |
| `_build_process_environment()` | QProcessEnvironment | 合并系统环境、任务覆盖和 UTF-8 配置 |
| `_finalize_process(exit_code, status)` | None | flush 解码器、恢复状态并发送完成事件 |

#### 16.8.2 `OptimizationConsole`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_maximum_blocks` | int | `5000` | 可见文本块上限 |
| `_auto_scroll` | bool | `True` | 输出到达时滚动到底部 |
| `_visible_levels` | frozenset[str] | 全部级别 | UI 日志级别过滤器 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_normalizer` | `AnsiTextNormalizer` | 新实例 | 跨 chunk 终端状态机 |
| `_plain_lines` | list[str] | `[]` | 规范化后的逻辑行缓存 |
| `_raw_log_path` | pathlib.Path 或 None | None | 当前运行原始输出文件 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `maximum_blocks` | int | - | 只读 | 内部维护 | 返回可见文本块上限 |
| `auto_scroll` | bool | - | 只读 | 读写 | 控制自动滚动 |
| `visible_levels` | frozenset[str] | - | 只读 | 读写 | 控制可见日志级别 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `append_output(text, stream="stdout")` | None | - | 增量规范化终端输出并更新可见文本 |
| `clear_output()` | None | - | 清空规范化文本和终端状态 |
| `set_raw_log_path(path)` | None | - | 绑定当前运行的原始输出文件 |
| `export_log(path)` | pathlib.Path | - | 将规范化后的 UTF-8 文本导出到目标文件 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_replace_logical_line(index, text, style)` | None | 处理回车覆写、清行和光标移动产生的行更新 |
| `_trim_blocks()` | None | 保留最近的可见文本块并维持光标索引 |

`AnsiTextNormalizer` 增量处理 ANSI SGR、清行、光标上移/下移、回车覆盖、backspace 和跨 chunk
转义序列，并输出“追加行、替换行、删除行”操作。进度表控制序列据此更新既有行；原始
stdout/stderr 同时写入运行目录日志，Console 显示规范化视图。

#### 16.8.3 `AnsiTextNormalizer`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | 终端状态使用固定 ANSI 解析规则 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_pending_escape` | str | `""` | 跨 chunk 尚未完成的转义序列 |
| `_cursor_row` | int | `0` | 当前逻辑行索引 |
| `_cursor_column` | int | `0` | 当前逻辑列索引 |
| `_style` | Mapping[str, object] | `{}` | 当前 SGR 文本样式 |
| `_lines` | list[str] | `[""]` | 终端逻辑行状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| 空 | - | - | - | - | 解析状态通过 `feed()` 和 `reset()` 维护 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `feed(text)` | tuple[Mapping[str, object], ...] | - | 消费一个文本 chunk 并返回追加、替换或删除行操作 |
| `flush()` | tuple[Mapping[str, object], ...] | - | 将结尾普通文本输出并保留完整终端状态 |
| `reset()` | None | - | 清空转义、光标、样式和逻辑行状态 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_consume_escape(sequence)` | list[Mapping[str, object]] | 解析 SGR、CSI 光标和清除指令 |
| `_write_text(text)` | list[Mapping[str, object]] | 按当前光标处理换行、回车和 backspace |

### 16.9 Observer 与 Viewer

#### 16.9.1 `Viewer`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_theme` | Mapping[str, object] | 默认深色主题 | 背景、实体、边线、选中和标量色图配置 |
| `_show_edges` | bool | `True` | 默认边线显示策略 |
| `_anti_aliasing` | str | `"ssaa"` | 抗锯齿模式 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_plotter` | QtInteractor 或 None | None | PyVistaQt 画布 |
| `_actors` | dict[str, object] | `{}` | 稳定 mesh id 到 actor 的映射 |
| `_meshes` | tuple[object, ...] | `()` | 当前显示网格 |
| `_selection` | Mapping[str, str] 或 None | None | 当前高亮目标类别、对象名称和集合名称 |
| `_scalar_field` | str 或 None | None | 当前标量字段 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `theme` | Mapping[str, object] | - | 只读 | 内部维护 | 返回统一显示主题只读视图 |
| `show_edges` | bool | - | 只读 | 读写 | 控制边线显示 |
| `anti_aliasing` | str | - | 只读 | 内部维护 | 返回抗锯齿模式 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_meshes(meshes, display_options=None)` | None | - | 替换当前网格并按稳定 id 重建 actor |
| `get_meshes()` | tuple[object, ...] | - | 读取当前显示网格 |
| `highlight_selection(selection)` | None | - | 高亮 Part、Instance、Surface、NodeSet 或 ElementSet |
| `set_scalar_field(name, value_range=None)` | None | - | 切换标量字段、范围和色标 |
| `set_deformation_scale(scale)` | None | - | 更新结果网格的变形显示比例 |
| `reset_camera()` | None | - | 应用统一等轴测视角并适配全部 actor |
| `clear()` | None | - | 移除 actor、标量条和选择状态 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_actor(mesh, options)` | object | 使用统一材质、光照和边线策略建立 actor |
| `_apply_selection_style()` | None | 在不重建网格的情况下更新高亮 actor |
| `_apply_theme()` | None | 将主题写入背景、坐标轴、标量条和相机 |

导入 TorchFEA 模型的右侧预览与优化监控变形图共享主题配置和 actor 工厂。

#### 16.9.2 `ObserverPanel`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_viewer` | `Viewer` | - | 共享三维 Viewer |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_result_path` | pathlib.Path 或 None | None | 当前结果目录 |
| `_history` | `History` 或 None | None | 已加载历史 |
| `_iteration` | int 或 None | None | 当前观察迭代 |
| `_case_index` | int 或 None | None | 当前结果工况 |
| `_pages` | dict[str, QWidget] | `{}` | 总览、设计参数、变形、目标和文件页面；设计参数页展示当前迭代与历史迭代的控制点/曲面形态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `viewer` | `Viewer` | - | 只读 | 内部维护 | 返回共享 Viewer |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `open_result(path)` | None | - | 校验结果 manifest、加载 History 并建立观察页面 |
| `set_iteration(iteration)` | None | - | 更新全部页面到指定迭代 |
| `set_case(case_index)` | None | - | 更新逐工况指标和结果网格 |
| `refresh()` | None | - | 增量加载运行中的新 checkpoint 和日志 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_load_checkpoint(iteration)` | None | 加载该轮模型、结果和可视化缓存 |
| `_update_pages()` | None | 同步曲线、统计表、文件树和 Viewer |

模型信息使用树/表展示 Assembly → Part → Instance → Surface/NodeSet/ElementSet/ElementType，
选择任一行时由 `Viewer.highlight_selection()` 高亮对应对象。变形页使用
`ObjectiveFunction.build_mesh_case()` 生成的数据，并提供未变形轮廓、变形比例、位移/能量
标量、工况和迭代选择。总览页显示 History 的 objective、metrics、耗时、网格规模和最大变形。

### 16.10 `I18nService`

`I18nService` 是 UI 文本的唯一翻译入口；模型名称、路径、代码和日志原文保持原值。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_catalogs` | Mapping[str, Mapping[str, str]] | 内置中英文 catalog | language → key → 文本 |
| `_fallback_language` | str | `"en_US"` | 缺失 key 的回退语言 |

#### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_language` | str | 设置文件或 `"zh_CN"` | 当前语言 |
| `_listeners` | list[Callable[[], None]] | `[]` | 语言切换监听器 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `catalogs` | Mapping[str, Mapping[str, str]] | - | 只读 | 内部维护 | 返回翻译表只读视图 |
| `fallback_language` | str | - | 只读 | 内部维护 | 返回回退语言 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_language(language)` | None | - | 校验语言、持久化选择并通知监听器刷新 |
| `get_language()` | str | - | 读取当前语言 |
| `translate(key, **values)` | str | - | 查找文本并格式化命名参数 |
| `add_listener(callback)` | None | - | 注册界面刷新回调 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_validate_catalogs()` | None | 校验中英文 key 集合、占位符和重复项一致 |

字段 schema、任务树、按钮、对话框、验证消息、片段标签和状态文本只保存 i18n key。自动测试
遍历两种 catalog，检查 key 完整性、占位符一致性和界面中残留的直接用户文本。

### 16.11 UI 入口函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `configure_environment()` | None | 在创建 Qt 对象前设置平台、OpenGL、HiDPI 和 PyVistaQt 运行选项 |
| `create_application(arguments=None)` | QApplication | 复用现有 QApplication 或创建一个新实例并安装 `I18nService` |
| `run_app(arguments=None)` | int | 创建 `MainWindow`、显示统一工作台并返回 Qt 退出码 |
| `main()` | int | `python -m morphopt.ui` 和 `morphopt-ui` 共用的控制台入口 |

`morphopt-ui`、`python -m morphopt.ui` 和库函数 `run_app()` 汇入同一入口。定义、运行和观察
由一个 `MainWindow` 与一个 `Workbench` 承载。

## 17. Codegen 和任务定义文件

### 17.1 Codegen 类

#### 17.1.1 `CodeGenerator`

`CodeGenerator` 只消费已经通过 `ProblemValidator` 校验的前端定义，并直接返回 Python 源码。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_formatter_options` | Mapping[str, object] | `{}` | 导入分组、缩进和稳定排序配置 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 源码生成是无状态操作 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `formatter_options` | Mapping[str, object] | - | 只读 | 内部维护 | 返回格式配置只读视图 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `generate_source(problem)` | str | - | 按固定领域顺序生成可执行、可格式化的任务源码 |
| `export_source(problem, target_path)` | pathlib.Path | - | 将生成源码以 UTF-8 原子写入目标 Python 文件 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_generate_imports(problem)` | tuple[str, ...] | 生成去重且稳定排序的导入语句 |
| `_generate_geometry(problem)` | str | 生成 GeometryParams、Part、曲面、Instance 和 RP 定义 |
| `_generate_materials(problem)` | str | 生成 MaterialsParams、材料参数和材料分配定义 |
| `_generate_fea(problem)` | str | 生成 FEAParams、component 和 LoadStep 定义 |
| `_generate_objective(problem)` | str | 生成 ObjectiveFunction 子类及用户代码槽 |
| `_generate_updaters(problem)` | str | 生成 updater 注册、局部约束和等式投影 |
| `_generate_solver(problem)` | str | 生成 Solver 配置 |
| `_generate_entrypoint(problem)` | str | 生成 Params、Controller、TaskRunner 和 `main()` |
| `_format_source(source)` | str | 用统一 formatter 规范生成代码并校验 Python AST |

#### 17.1.2 `SchemeTemplate`

`SchemeTemplate` 是 UI 初始问题工厂。V4 内置 `shapeopt` 和 `simp` 两个 scheme；codesign
（偏置壳 + 材料联合优化）不是 scheme，它由 `OffsetShellPart`、`BoundaryPartUpdater` /
`OffsetShellPartUpdater` 和 `MaterialUpdater` 的对象组合表达，约束项按 `target_kind`
归入对应 updater 目录，见[破坏性变更](24BreakingChanges.md)。通用
`OffsetShellPart` 与多个 updater 的组合由普通节点表达。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | - | 稳定 scheme 标识 |
| `_label_key` | str | - | 双语显示文本的 i18n key |
| `_problem_factory` | Callable[[], `ProblemDefinition`] | - | 创建默认问题定义的工厂 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 每次调用直接创建独立问题定义 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `name` | str | - | 只读 | 内部维护 | 返回 scheme 标识 |
| `label_key` | str | - | 只读 | 内部维护 | 返回双语标签 key |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `create_problem()` | `ProblemDefinition` | - | 创建结构完整、名称唯一且通过默认值校验的新问题 |
| `create_part(part_type, data=None)` | `PartNode` | - | 创建指定 Part 类型的编辑节点 |
| `create_fea_component(component_type, data=None)` | `FEAComponentNode` | - | 创建指定 FEA component 节点 |
| `create_material(material_type, data=None)` | `MaterialNode` | - | 创建指定材料节点 |
| `create_updater(updater_type, data=None)` | `UpdaterNode` | - | 创建指定 updater 节点 |
| `get_snippets(slot_name)` | tuple[`SnippetDefinition`, ...] | - | 读取指定代码槽可用片段定义 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_default_geometry()` | `GeometryNode` | 创建 scheme 的默认几何节点 |
| `_build_default_fea()` | `FEANode` | 创建空组件注册表和一个空工况 |
| `_build_default_optimization()` | tuple[`ObjectiveNode`, tuple[`UpdaterNode`, ...]] | 创建目标和 updater 默认节点 |

默认 scheme 创建可运行结构和空的用户定义槽；载荷、集中力、集中力矩和 Jacobian 选择均由
用户显式添加。所有面向用户的标签由 i18n key 提供，代码模板内容保持英文。

### 17.2 生成顺序

本节是任务文件生成顺序的唯一权威来源；其他章节只引用本节，不重复记录顺序。

~~~text
imports
    → Controller / Params
    → GeometryParams 和 Part 子类
    → MaterialsParams 和材料参数对象
    → FEAParams 和 load steps
    → ObjectiveFunction
    → Updaters
    → Solver 和 main entry
~~~

生成规则：

- 一个 `PartNode` 生成一个 `Part` 定义；
- `BoundaryPart` 节点生成显式的 `element_name` 参数；导入 Part 节点生成可选的
  `element_names` 参数，省略时由源元素类型名称建立；`OffsetShellPart` 生成显式的
  `solid_element_name`、`shell_element_name` 和 `source_surface` 参数，其中两个元素名称
  必须显式提供长度大于零的值，`source_surface` 的长度等于曲面数量，第 0 项固定为
  `False`，第 1 项及以后选择向内偏置曲面；
- 一个 `Part` 下的每个 `InstanceNode` 生成一个 `InstanceDefinition`；
- `SolverNode.reuse_previous_solution` 生成 Solver 的单一求解初值开关；值为 `None` 时由
  Controller 根据 `DesignRegistry.has_geometry_variables()` 自动选择，`True`/`False` 时保留
  用户显式策略；
- 一个 `ReferencePointNode` 生成一次 `add_reference_point()`；
- 从 TorchFEA 模型选择的参考点以摘要中的名称和全局坐标生成 `ReferencePointNode`；同名参考点
  坐标一致时复用，同名坐标不一致时在生成前报告冲突；
- 一个 `MaterialNode` 生成一次 `add_material()`；
- 参数类直接表达材料模型；
- 材料节点将 `part_name` 和 `element_name` 一起生成到材料接口构造参数；
- 几何、材料和 FEA 任务代码分别生成 `define_parts()`、`define_reference_points()`、
  `define_materials()` 和 `define_components()`，并在其中调用对应的 `add_*()` 注册方法；
- `GeometryParams`、`MaterialsParams` 和 `FEAParams` 的构造调用只创建空注册表和运行配置；
- 一个 updater node 生成一个目标绑定，且同一目标实体只能出现一次；
- `BoundaryPart` 目标生成 `BoundaryPartUpdater`，`OffsetShellPart` 目标生成
  `OffsetShellPartUpdater`；
- UI 代码记录目标名称用于定义文件和序列化；运行时初始化阶段由 `Updaters` 将名称解析为
  实体对象并直接注入对应 updater，`BoundaryPartUpdater` 后续只使用绑定的
  `BoundaryPart` 引用；
- `UpdaterNode.local_constraints` 只写回对应 updater，生成该 updater 的 `add_constraint()`；材料
  `regularization_terms` 生成 `add_regularization()`；几何
  updater 的唯一等式约束生成该 updater 的 `set_equality_constraint()` 调用；局部灵敏度目标由
  `Controller` 分发梯度后自动建立，不写入任务文件，也不写入顶层 `ObjectiveFunction`。

### 17.3 Python 任务定义和运行结果

Python 任务文件直接表达用户的构造记录、用户自定义类和用户自定义方法，是任务
定义的唯一来源。UI 编辑树通过 `generate_source()` 生成同样的任务文件。

每次运行都先从任务文件重新创建对象并调用 `initialize()`。需要继续计算时，先执行
同一任务文件建立完整运行时对象，再由 `Controller.load()` 加载指定 iteration 的
设计变量、优化器状态、历史指标和结果索引。

~~~text
<run_root>/<label>_T<timestamp>/
├── log/
│   ├── morphopt.log
│   └── torchfea.log
├── state/
├── results/
├── cache/
├── fea/
└── scripts/
    └── main.py
~~~

运行结果与任务定义分开管理。结果文件服务于日志和 UI 展示，任务文件保存用户定义；
用户自定义类和方法由任务文件恢复。

运行目录契约：

- `<run_root>` 由 `Controller.result_root` 决定，默认 `.results`；UI 启动的任务固定为
  工作目录下的 `ui_runs/`，`ProblemDefinition.result_folder` 为相对该根目录的标签；
- 运行目录名固定为 `<label>_T<timestamp>`；
- `scripts/main.py` 是任务源码快照，也是 checkpoint manifest 中 `main_file_path` 指向的
  文件；续跑由 `load_controller()` 读取 manifest 中的任务文件与 Controller 类路径完成，
  不依赖固定的模块属性名；
- 运行目录同时写入依赖快照（`morphopt`、`torchfea`、`cpgeo`）到 `scripts/`，使结果目录可以
  独立复跑；`load_controller()` 优先使用快照，manifest 的 `task_signature` 记录依赖版本
  用于校验。

### 17.4 状态保存和历史读取

`Persistable` 是显式的文件 I/O 协议。实现该协议的对象保存自己负责的数据：

| 对象 | `save()` 内容 | `load()` 内容 |
|---|---|---|
| `Params`、`GeometryParams` | 当前几何、材料、FEA 数值状态 | 指定 iteration 的模型数值状态 |
| `DesignRegistry` | 变量块、offsets 和当前完整变量 | 指定 iteration 的设计变量 |
| `Solver` | solver 配置和运行元数据 | 指定 iteration 的 solver 状态 |
| `ObjectiveFunction`、`History` | 目标值、metrics、收敛信息和结果路径 | 历史数据和结果索引 |
| `BaseUpdater`、`Updaters` | optimizer memory 和 updater 状态 | 指定 iteration 的 updater 状态 |

### 17.5 `.morph` schema 与补全数据来源

`.morph` 是版本化 JSON：`schema_version` 为 `2`，UTF-8 编码，原子写入。

| 项目 | 规则 |
|---|---|
| 版本读写 | 只接受 `schema_version == 2` 的输入；版本不一致时拒绝加载并报告，V4 不提供旧版本迁移 |
| 未知字段 | 读取时保留在节点的扩展字段中，保存时原样写回，保证新增字段不丢失 |
| 已知字段缺失 | 按节点默认值补齐并记录校验警告，不阻断加载 |
| 节点标识 | 每个节点写入 `node_id`（UUID）与 `_schema_version`，用于局部编辑校验和差异比较 |
| 保存入口 | `ProblemDefinition.save_definition()` / `load_definition()` 是唯一入口；模块级 `save_morph()` / `load_morph()` 只作为薄包装 |
| 保存前校验 | 保存前必须执行 `ProblemValidator.validate()`，存在错误时不写出文件 |

补全上下文的数据来源固定如下。UI 进程不持有运行时对象，因此补全内容只能来自定义树与
模型摘要，运行时对象的成员形状由下表静态契约提供：

| 补全类别 | 来源 |
|---|---|
| 工况数量与工况索引 | `LoadStepsNode.num_steps` |
| component 名称、`jacobian` 可选名称 | `FEAComponentNode` 列表中的 `num_values > 0` 组件 |
| 实例名、Part 名、node/element/surface set 名、参考点名 | `InstanceNode`、`PartNode`、`ReferencePointNode` 与 `TorchFEAModelSummary` |
| 材料名、updater 目标名与局部项 | `MaterialNode`、`UpdaterNode` |
| 设计场与灵敏度表达式 | `SIMPFieldMaterial` 的控制点绑定、updater 局部项 |

| 表达式 | 可补全成员 |
|---|---|
| `fe_results[i]` | `GC`、`converged`、`model_hash`、`jacobian[component_name]`、`work_conditions`、`total_time`、`step_index` |
| `assembly` | `get_instance(name)`、`get_part(name)`、`set_nodes[name]`、`set_elements[name]` |
| Tensor | `detach()`、`cpu()`、`numpy()`、`norm()`、`sum()`、`mean()`、`max()`、`min()`、`reshape()`、`clone()` |

运行时对象新增公共成员时，必须同步更新上表与 §16.7 的候选表，并由 §20.7 的生成任务文件
冒烟测试保证 UI schema 与运行时 API 一致。

#### 17.5.1 运行入口流程

UI 启动任务只有三个入口，交互与校验固定如下：

| 入口 | 输入 | 行为 |
|---|---|---|
| 运行当前定义 | 编辑树 + `result_folder` | `ProblemValidator` 通过后生成任务源码到本轮运行目录的 `scripts/main.py`，再以 headless 子进程运行 |
| 运行已有 Python 文件 | `.py` 路径 | 校验文件可编译且定义了 Controller 类；不修改文件内容，直接运行；`result_folder` 仍作为结果根目录下的标签 |
| 继续计算 | 运行目录或结果目录 | 由 `load_controller()` 读取最新完整 checkpoint，显示其迭代号，用户选择目标迭代（默认最新完整迭代）后运行 |

规则：

- 三个入口都通过 `TaskLauncher` 启动独立进程，UI 进程不 import 任务模块；
- 运行期间不允许编辑定义树；停止通过 `TaskLauncher.stop()` 发送终止信号，对应退出码 `2`；
- 继续计算不以编辑树为准：它以 checkpoint 的任务文件与签名为唯一权威输入，签名不一致时
  报告错误并终止，不回退到编辑树内容；
- 每个入口在启动前校验目标运行目录可写，并提示将使用的运行标签。

`Controller.save()` 按固定顺序调用上述对象的 `save()`；`Controller.load()` 只在
任务文件已经完成 `initialize()` 后调用各对象的 `load()`。用户自定义曲面、约束和
目标函数的方法仍然来自当前任务文件，状态文件只提供这些方法所需的数值状态。
