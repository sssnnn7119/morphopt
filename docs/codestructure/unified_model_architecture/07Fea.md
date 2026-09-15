# MorphOpt V4 FEA 组件

本文件定义 FEA component、载荷工况和 `FEAParams`，并说明它们对几何层参考点与当前 `Assembly` 的引用。
返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

FEA 层接收几何层生成的 `torchfea.Assembly`，按照注册表创建 FEA component，按照
`LoadStep` 更新工况值，并将 component 运行对象挂接到当前模型上下文。FEA 定义、当前
Assembly 的解析状态和 TorchFEA component 运行对象分成不同生命周期阶段：

```text
定义阶段：
FEAParams.define_components() → FEAParams.add_component()
FEAParams.define_steps() → FEAParams.initialize()

Assembly 绑定阶段：
FEAParams.reinitialize(iteration, assembly)
    → FEAParams.build_components()
    → FEAParams.assign_components()

逐工况求解阶段：
FEAParams.build_case_assemblies()
    → 为每个 LoadStep 建立独立 Assembly 和 component 运行副本
    → 将 LoadValueBlock 绑定到所属工况副本
    → LoadValueBlock.update_assembly(design_delta)
    → FEAParams.get_case_assemblies()
```

### 目录

- [7. FEA 类定义](#7-fea-类定义)
  - [7.1 `FEAParams`](#71-feaparams)
  - [7.2 `BaseFEAComponent`](#72-basefeacomponent)
  - [7.3 `Pressure`](#73-pressure)
  - [7.4 `BodyForce`](#74-bodyforce)
  - [7.5 `ConcentratedForce`](#75-concentratedforce)
  - [7.6 `ConcentratedMoment`](#76-concentratedmoment)
  - [7.7 `BoundaryCondition`](#77-boundarycondition)
  - [7.8 `BoundaryConditionRP`](#78-boundaryconditionrp)
  - [7.9 `Couple`](#79-couple)
  - [7.10 `SpringToGround`](#710-springtoground)
  - [7.11 `SpringBetweenRPs`](#711-springbetweenrps)
  - [7.12 `PenaltyDoF`](#712-penaltydof)
  - [7.13 `Contact`](#713-contact)
  - [7.14 `SelfContact`](#714-selfcontact)
  - [7.15 `LoadStep`](#715-loadstep)
  - [7.16 `LoadValueBlock`](#716-loadvalueblock)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | `Assembly`、Instance/Surface/NodeSet/ElementSet/RP 名称、component 定义和 load step |
| 输出 | TorchFEA FEA component、component 目标解析缓存、载荷预览缓存和工况状态 |
| 主要读者 | FEA component 实现者、`FEAParams` 实现者、运行时和 UI 实现者 |
| 关联文档 | [几何系统](05Geometry.md)、[材料系统](06Materials.md)、[Solver](08Solver.md)、[目标函数](09Objective.md)、[运行时](13-14Runtime.md) |

## 7. FEA 类定义

### 7.1 `FEAParams`

`FEAParams` 是 FEA 定义集合的统一管理者和唯一入口。它维护 component 注册表和 load step
顺序，接收当前 Assembly 后解析 component 目标并建立各 component 的 TorchFEA 对象。
参考点由几何层定义并写入 Assembly，后续 FEA component 只解析其名称。组件运行对象由
`FEAParams.assign_components()` 写入当前 Assembly，供后续处理器读取。

#### 构造属性（注册表由 `__init__()` 创建，`define_components()` / `define_steps()` 填充）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_fea_components` | dict[str, BaseFEAComponent] | `{}` | component 注册表 |
| `_load_steps` | list[LoadStep] | `[]` | 按 step index 排序的工况 |

#### 运行时属性（`__init__()` 声明，`initialize()` / `reinitialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Assembly` | torchfea.Assembly 或 None | None | 当前迭代绑定的 Assembly |
| `_component_targets` | dict[str, object] | `{}` | component 到 Assembly 目标的索引 |
| `_case_assemblies` | dict[int, torchfea.Assembly] | `{}` | 按工况隔离、保留设计计算图的求解 Assembly |
| `_case_components` | dict[int, dict[str, BaseFEAComponent]] | `{}` | 各工况独立绑定的 component 运行副本 |
| `_load_value_blocks` | dict[tuple[int, str], LoadValueBlock] | `{}` | 工况索引和 component 名称到载荷设计变量 owner 的索引 |
| `_initialized` | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `fea_components` | Mapping[str, BaseFEAComponent] | - | 只读 | 内部维护 | component 注册表只读视图 |
| `load_steps` | tuple[LoadStep, ...] | - | 只读 | 内部维护 | 工况定义只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `define_components()` | None | - | 通过 `add_component()` 注册全部 component |
| `define_steps()` | None | - | 通过 `set_num_steps()` 和 `set_step_values()` 创建工况 |
| `add_component(component, name)` | None | - | 将 component 写入唯一名称注册表 |
| `set_num_steps(num_steps)` | None | - | 创建指定数量的 `LoadStep` |
| `set_step_values(step_index, component_name, values)` | None | - | 修改指定工况的 component 值 |
| `build_components()` | None | - | 使用已绑定的 Assembly 创建并保存基础 component 的 TorchFEA 对象 |
| `assign_components()` | None | - | 将已经建立的 component 对象写入已绑定 Assembly |
| `build_case_assemblies()` | None | - | 从已更新的基础 Assembly 为每个工况建立独立副本，创建并绑定工况 component，再写入已提交值 |
| `get_case_assemblies()` | Mapping[int, `torchfea.Assembly`] | - | 读取已经建立的逐工况 Assembly |
| `update_fea(step_index)` | None | - | 将指定工况的已提交值写入该工况的 Assembly 副本，用于预览和单工况诊断；基础 Assembly 不被修改 |
| `get_design_owners()` | tuple[`LoadValueBlock`, ...] | - | 读取逐工况、逐组件建立的非空设计变量 owner |
| `get_num_load_steps()` | int | - | 读取工况数量 |
| `initialize()` | None | `Initializable` | 初始化注册表和工况定义 |
| `reinitialize(iteration, assembly)` | None | `Initializable` | 解析当前 Assembly 并刷新所有 component |
| `build_meshes()` | None | `Visualizable` | 建立全部 component 预览 |
| `get_meshes()` | list[object] | `Visualizable` | 读取全部 component 预览 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存 FEA 定义和运行状态 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载指定迭代的 FEA 状态 |

#### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_sort_components()` | None | 按注册名称稳定排序 component |
| `_sort_load_steps()` | None | 按 step index 稳定排序工况 |
| `_resolve_component_targets(assembly)` | None | 建立 component 到 Assembly 目标的索引 |
| `_build_load_value_blocks()` | None | 为所有非零值 component 建立逐工况 `LoadValueBlock` |
| `_build_case(step_index)` | None | 建立工况 Assembly 副本与独立 component 运行副本，写入已提交值并绑定该工况的 `LoadValueBlock` |

`FEAParams` 的注册顺序为：

```text
initialize()
    → define_components()
        → add_component(component, name)
    → define_steps()
        → set_num_steps(num_steps)
        → set_step_values(step_index, component_name, values)
reinitialize(iteration, assembly)
build_components()
assign_components()
build_case_assemblies()
get_case_assemblies()
```

模型导入由几何层 `INPPart` 或 `TorchFEAPart` 提供；`FEAParams` 从几何层接收已经建立的
`Assembly`，并依据 Instance、Surface、NodeSet、ElementSet 和几何层 ReferencePoint 名称解析
component 目标。基础 Assembly 保存当前迭代的共享几何和材料状态；每个工况拥有独立
Assembly 与 component 运行对象。`_build_case()` 重建 Assembly、Instance 和各注册
容器，几何节点与材料参数从当前试探 Tensor 重新挂接，从而保留全局设计增量的 autograd
链。工况建立顺序固定为“复制 Assembly → 创建并挂接 component
运行副本 → 写入工况已提交值 → 绑定对应 `LoadValueBlock`”。

#### 工况副本的共享与复制契约

`build_case_assemblies()` 必须遵守以下固定契约，实现和 review 均以此为判据：

| 类别 | 内容 |
|---|---|
| 共享，不得复制 | `Part` 拓扑与名称集合（`nodes`、`elems` 的元素族字典键）、几何与材料的设计 Tensor、曲面映射缓存、`ReferencePoint`、材料本构对象 |
| 复制，必须每个工况独立 | Assembly 的 load / boundary / constraint 注册容器、全部 FEA component 运行对象（含接触的搜索与积分状态）、`LoadStep` 的逐工况值快照、`LoadValueBlock` 绑定的工况 component |
| 禁止 | 任一工况的更新不得原地修改共享 `Part.elems`、共享几何/材料 Tensor 或基础 Assembly；材料适配器与单元包装只在工况副本上注册 |
| 建立后校验 | 每个工况副本的几何/材料 Tensor 与基础 Assembly 是同一对象（`is` 判定），且各工况的 component 运行对象两两不同 |
| 内存 | 副本数量等于工况数量；副本之间不共享可变状态，因此峰值内存随工况数线性增长，`Controller._clear_runtime_cache()` 负责在每轮结束时释放上一轮副本 |

### 7.2 `BaseFEAComponent`

`BaseFEAComponent` 是所有载荷、边界、接触和耦合 component 的协议基类，显式继承
`Visualizable`、`Initializable` 和 `Persistable`。定义阶段保存名称、目标名称和默认值；
运行时阶段在 `_torchfea_Assembly` 中缓存当前 `Assembly`，解析目标并创建 TorchFEA 对象。具体 component 由
`FEAParams.add_component()` 注册。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | `""` | 注册后的稳定 component 名称 |
| `_default_values` | tuple[float, ...] | 按 `num_values` 创建 | 新建 LoadStep 时使用的默认值；零参数组件使用空元组 |
| `_target_names` | tuple[str, ...] | `()` | Instance、Surface、Set 或 RP 名称 |
| `_default_values` | tuple[float, ...] | 按 `num_values` 创建 | 新建 LoadStep 时使用的默认值；零参数组件使用空元组 |

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Assembly` | torchfea.Assembly 或 None | None | `reinitialize()` 绑定的当前 Assembly |
| `_target` | object 或 None | None | 从当前 Assembly 解析出的目标对象 |
| `_mesh_cache` | list[object] | `[]` | 已建立的 component 预览对象 |
| `_initialized` | bool | False | 当前 component 的初始化状态 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `name` | str | - | 只读 | 内部维护 | 返回注册名称 |
| `default_values` | tuple[float, ...] | - | 只读 | 读写 | 返回新建工况的默认值；setter 执行与 `set_default_values()` 相同的校验 |
| `num_values` | int | - | 只读 | 子类重写 | 返回当前 component 的值向量长度 |
| `target_names` | tuple[str, ...] | - | 只读 | 内部维护 | 返回定义阶段记录的目标名称 |

#### 4. 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `build_fea()` | None | - | 创建具体 TorchFEA 对象并写入子类的 `_torchfea_<ConcreteName>` |
| `get_fea_object()` | object | - | 读取已经创建的 TorchFEA 对象 |
| `assign_fea()` | None | - | 按 §7.1 挂接接口列将已建立对象挂接到当前 Assembly |
| `update_fea(values)` | None | - | 将一个工况值写入已有 TorchFEA 对象 |
| `initialize()` | None | `Initializable` | 建立 component 的静态定义状态 |
| `reinitialize(iteration, assembly)` | None | `Initializable` | 解析当前 Assembly 的 Instance、Surface、Set 和 RP |
| `build_meshes()` | None | `Visualizable` | 建立并保存 component 预览缓存 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的预览缓存 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存 component 定义和运行状态 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载指定迭代的 component 状态 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_target(assembly)` | object | 根据目标名称解析 Assembly 对象 |
| `_validate_values(values)` | None | 校验值向量长度和数值类型 |
| `_create_fea_object()` | object | 由具体类型创建 TorchFEA 对象 |
| `_apply_values(values)` | None | 由具体类型把已校验值写入缓存的 TorchFEA 对象 |
| `_build_preview_meshes()` | list[object] | 由具体类型建立预览几何，供 `build_meshes()` 写入缓存 |

`build_fea()` 只创建运行时对象并写入具体子类的 `_torchfea_<ConcreteName>`；
`get_fea_object()` 读取已建立对象，`assign_fea()` 完成 Assembly 挂接，
`update_fea()` 更新当前工况。`FEAParams._build_case()` 复制 component 的构造
定义，并在工况 Assembly 上重新执行 `reinitialize()`、`build_fea()` 和 `assign_fea()`；
每个工况拥有自己的可变 TorchFEA component。
逐工况参数由 `LoadStep` 保存；`LoadValueBlock` 把一个
`(component_name, case_index)` 组合适配为独立 `Updatable` owner。

具体 component 的库对象、构造签名、挂接位置和设计值长度固定如下。`torchfea` 列是唯一的
后端契约，morphopt 类名与库类名不一致时以本表为准：

| morphopt 类 | `torchfea` 类 | 库构造签名 | 挂接接口 | `num_values` |
|---|---|---|---|---:|
| `Pressure` | `loads.Pressure` | `(instance_name, surface_set, pressure)` | `add_load()` | 1 |
| `BodyForce` | `loads.BodyForce` | `(instance_name, element_name, force_density=[0.0, 0.0, -9.81e-6])` | `add_load()` | 3 |
| `ConcentratedForce` | `loads.Concentrate_Force` | `(rp_name, force)` | `add_load()` | 3 |
| `ConcentratedMoment` | `loads.Moment` | `(rp_name, moment)` | `add_load()` | 3 |
| `BoundaryCondition` | `boundarys.Boundary_Condition` | `(instance_name, set_nodes_name, indexDoF=[0, 1, 2])` | `add_boundary()` | 0 |
| `BoundaryConditionRP` | `boundarys.Boundary_Condition_RP` | `(rp_name, indexDoF=[0, 1, 2, 3, 4, 5])` | `add_boundary()` | 0 |
| `Couple` | `constraints.Couple` | `(instance_name, set_nodes_name, rp_name)` | `add_constraint()` | 0 |
| `SpringToGround` | `loads.Spring_RP_Point` | `(rp_name, point, k, rest_length=None)` | `add_load()` | 5 |
| `SpringBetweenRPs` | `loads.Spring_RP_RP` | `(rp_name1, rp_name2, k, rest_length=None)` | `add_load()` | 2 |
| `PenaltyDoF` | `loads.Penalty_DoF` | `(obj_name, s, target, k, obj_type="auto")` | `add_load()` | 2 |
| `Contact` | `loads.Contact` | `(instance_name1, instance_name2, surface_name1, surface_name2, penalty_distance_f=1e-5, penalty_factor_f=40.0, penalty_start_g=-0.4, penalty_end_g=-0.85, penalty_threshold_h=1.5, penalty_ratio_h=0.9, mesh_size=1.0)` | `add_load()` | 0 |
| `SelfContact` | `loads.ContactSelf` | `(instance_name, surface_name, ignore_min_normal=0.5, ignore_max_normal=1.5, initial_detact_ratio=1.5, penalty_distance_f=1e-5, penalty_factor_f=40.0, penalty_start_g=-0.8, penalty_end_g=-0.85, penalty_threshold_h=1.5, penalty_ratio_h=0.9, mesh_size=1.0)` | `add_load()` | 0 |

库构造参数全部由 component 的构造属性透传，默认值采用库默认值；任务不显式给出时不重复声明。
目标解析在 `reinitialize(iteration, assembly)` 中完成，可用 `Assembly.get_object(name, obj_type)`
做通用校验。`assign_fea()` 按上表的“挂接接口”列选择唯一注册入口，并以 component 的稳定
`name` 挂接。工况 component 副本沿用相同名称和注册位置。零值 component 在每个工况中仍会
创建和挂接，从而让边界、耦合与接触关系在所有工况中完整存在。

### 7.3 `Pressure`

`Pressure` 将标量压力施加到某个 Instance 的 Surface set。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_instance_name` | str | `"final_model"` | 目标 Instance 名称 |
| `_surface_set` | str | 构造函数传入 | 目标 surface set 名称；对应库构造的第二个参数 |

注册名称和默认值沿用 `BaseFEAComponent` 的 `_name` 和 `_default_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Pressure` | `torchfea.loads.Pressure` 或 None | None | 已创建的 TorchFEA 压力对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `instance_name` | str | - | 只读 | 内部维护 | 返回目标 Instance |
| `surface_set` | str | - | 只读 | 内部维护 | 返回目标 surface set |
| `pressure` | float | - | 只读 | 读写 | 读取或修改 `_default_values[0]` |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `1` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建、值写入和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 解析目标 Surface set |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA Pressure |
| `_apply_values(values)` | None | `BaseFEAComponent` | 更新压力标量 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立曲面法向压力箭头 |

### 7.4 `BodyForce`

`BodyForce` 将三方向体力密度施加到指定 Instance 的元素集合。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_instance_name` | str | `"final_model"` | 目标 Instance 名称 |
| `_element_name` | str | 构造函数传入 | 目标元素名称 |

注册名称和默认值沿用 `BaseFEAComponent` 的 `_name` 和 `_default_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_BodyForce` | `torchfea.loads.BodyForce` 或 None | None | 已创建的 TorchFEA 体力对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `instance_name` | str | - | 只读 | 内部维护 | 返回目标 Instance |
| `element_name` | str | - | 只读 | 内部维护 | 返回元素名称 |
| `force_density` | tuple[float, float, float] | - | 只读 | 读写 | 读取或修改 `_default_values` 的三方向体力密度 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `3` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建、值写入和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 解析目标元素集合 |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA BodyForce |
| `_apply_values(values)` | None | `BaseFEAComponent` | 更新力密度及 TorchFEA 积分缓存 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 在元素集合中心建立体力箭头 |

### 7.5 `ConcentratedForce`

`ConcentratedForce` 将三方向集中力施加到一个参考点。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name` | str | 构造函数传入 | 目标参考点名称 |

注册名称和默认值沿用 `BaseFEAComponent` 的 `_name` 和 `_default_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_ConcentratedForce` | `torchfea.loads.ConcentratedForce` 或 None | None | 已创建的 TorchFEA 集中力对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `reference_point_name` | str | - | 只读 | 内部维护 | 返回参考点名称 |
| `force` | tuple[float, float, float] | - | 只读 | 读写 | 读取或修改 `_default_values` 的三方向集中力 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `3` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建、值写入和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 解析目标参考点 |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA ConcentratedForce |
| `_apply_values(values)` | None | `BaseFEAComponent` | 更新三方向集中力 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立参考点处的力箭头 |

### 7.6 `ConcentratedMoment`

`ConcentratedMoment` 将三方向集中力矩施加到一个参考点。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name` | str | 构造函数传入 | 目标参考点名称 |

注册名称和默认值沿用 `BaseFEAComponent` 的 `_name` 和 `_default_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_ConcentratedMoment` | `torchfea.loads.ConcentratedMoment` 或 None | None | 已创建的 TorchFEA 集中力矩对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `reference_point_name` | str | - | 只读 | 内部维护 | 返回参考点名称 |
| `moment` | tuple[float, float, float] | - | 只读 | 读写 | 读取或修改 `_default_values` 的三方向集中力矩 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `3` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建、值写入和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 解析目标参考点 |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA ConcentratedMoment |
| `_apply_values(values)` | None | `BaseFEAComponent` | 更新三方向集中力矩 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立参考点处的力矩圆弧与方向箭头 |

### 7.7 `BoundaryCondition`

`BoundaryCondition` 在 Instance 的 Node set 上约束指定自由度。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_instance_name` | str | 构造函数传入 | 目标 Instance 名称 |
| `_node_set_name` | str | 构造函数传入 | 目标 Node set 名称 |
| `_index_dof` | tuple[int, ...] | `(0, 1, 2)` | 被约束的自由度索引 |

注册名称沿用 `BaseFEAComponent` 的 `_name`；约束没有独立的工况值向量。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_BoundaryCondition` | `torchfea.boundarys.BoundaryCondition` 或 None | None | 已创建的 TorchFEA 边界对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `instance_name` | str | - | 只读 | 内部维护 | 返回目标 Instance |
| `node_set_name` | str | - | 只读 | 内部维护 | 返回 Node set 名称 |
| `index_dof` | tuple[int, ...] | - | 只读 | 内部维护 | 返回约束自由度 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 解析目标 Node set 并校验自由度 |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA BoundaryCondition |
| `_apply_values(values)` | None | `BaseFEAComponent` | 校验零长度值向量并保持边界状态 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立受约束节点和自由度方向标记 |

### 7.8 `BoundaryConditionRP`

`BoundaryConditionRP` 在参考点上约束指定自由度。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name` | str | 构造函数传入 | 目标参考点名称 |
| `_index_dof` | tuple[int, ...] | `(0, 1, 2)` | 被约束的自由度索引 |

注册名称沿用 `BaseFEAComponent` 的 `_name`；约束没有独立的工况值向量。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_BoundaryConditionRP` | `torchfea.boundarys.BoundaryConditionRP` 或 None | None | 已创建的 TorchFEA 参考点边界对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `reference_point_name` | str | - | 只读 | 内部维护 | 返回参考点名称 |
| `index_dof` | tuple[int, ...] | - | 只读 | 内部维护 | 返回约束自由度 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 解析目标参考点并校验自由度 |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA BoundaryConditionRP |
| `_apply_values(values)` | None | `BaseFEAComponent` | 校验零长度值向量并保持边界状态 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立参考点和受约束自由度标记 |

### 7.9 `Couple`

`Couple` 将参考点与 Instance 的 Node set 通过指定耦合自由度连接。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name` | str | 构造函数传入 | 目标参考点名称 |
| `_instance_name` | str | 构造函数传入 | 目标 Instance 名称 |
| `_node_set_name` | str | 构造函数传入 | 目标 Node set 名称 |

注册名称沿用 `BaseFEAComponent` 的 `_name`；耦合没有独立的工况值向量。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Couple` | `torchfea.constraints.Couple` 或 None | None | 已创建的 TorchFEA 耦合对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `reference_point_name` | str | - | 只读 | 内部维护 | 返回参考点名称 |
| `instance_name` | str | - | 只读 | 内部维护 | 返回目标 Instance |
| `node_set_name` | str | - | 只读 | 内部维护 | 返回 Node set 名称 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | tuple[object, object] | `BaseFEAComponent` | 解析 RP 和 Node set |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA Couple |
| `_apply_values(values)` | None | `BaseFEAComponent` | 校验零长度值向量并保持耦合状态 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立 RP 到耦合节点集合的连线 |

### 7.10 `SpringToGround`

`SpringToGround` 在参考点和固定空间点之间建立非线性轴向弹簧。值向量为
`[k, rest_length, px, py, pz]`。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name` | str | 构造函数传入 | 目标参考点 |

注册名称和默认值沿用 `BaseFEAComponent` 的 `_name` 和 `_default_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_SpringToGround` | `torchfea.constraints.Spring_RP_Point` 或 None | None | 已创建的 TorchFEA 参考点-固定点弹簧对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `reference_point_name` | str | - | 只读 | 内部维护 | 返回参考点名称 |
| `k` | float | - | 只读 | 读写 | 读取或修改 `_default_values[0]` 的弹簧刚度 |
| `rest_length` | float | - | 只读 | 读写 | 读取或修改 `_default_values[1]` 的弹簧原长 |
| `point` | tuple[float, float, float] | - | 只读 | 读写 | 读取或修改 `_default_values[2:5]` 的固定点坐标 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `5` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建、值写入和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 解析参考点 |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA SpringToGround |
| `_apply_values(values)` | None | `BaseFEAComponent` | 更新刚度、原长和固定点 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立参考点到固定点的弹簧线 |

### 7.11 `SpringBetweenRPs`

`SpringBetweenRPs` 在两个参考点之间建立非线性轴向弹簧。值向量为 `[k, rest_length]`。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name_1` | str | 构造函数传入 | 第一个参考点 |
| `_reference_point_name_2` | str | 构造函数传入 | 第二个参考点 |

注册名称和默认值沿用 `BaseFEAComponent` 的 `_name` 和 `_default_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_SpringBetweenRPs` | `torchfea.constraints.Spring_RP_RP` 或 None | None | 已创建的 TorchFEA 参考点-参考点弹簧对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `reference_point_name_1` | str | - | 只读 | 内部维护 | 返回第一个参考点名称 |
| `reference_point_name_2` | str | - | 只读 | 内部维护 | 返回第二个参考点名称 |
| `k` | float | - | 只读 | 读写 | 读取或修改 `_default_values[0]` 的弹簧刚度 |
| `rest_length` | float | - | 只读 | 读写 | 读取或修改 `_default_values[1]` 的弹簧原长 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `2` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建、值写入和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | tuple[object, object] | `BaseFEAComponent` | 解析两个参考点 |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA SpringBetweenRPs |
| `_apply_values(values)` | None | `BaseFEAComponent` | 更新刚度和原长 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立两个参考点之间的弹簧线 |

### 7.12 `PenaltyDoF`

`PenaltyDoF` 在对象的指定自由度上施加二次惩罚。值向量为 `[k, target]`。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_object_name` | str | 构造函数传入 | 目标对象名称 |
| `_dof_index` | int | 构造函数传入 | 目标自由度索引 |
| `_object_type` | str | `"auto"` | 对象类型解析模式 |

注册名称和默认值沿用 `BaseFEAComponent` 的 `_name` 和 `_default_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_PenaltyDoF` | `torchfea.constraints.Penalty_DoF` 或 None | None | 已创建的 TorchFEA 自由度惩罚对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `object_name` | str | - | 只读 | 内部维护 | 返回目标对象名称 |
| `dof_index` | int | - | 只读 | 内部维护 | 返回目标自由度 |
| `object_type` | str | - | 只读 | 内部维护 | 返回对象类型 |
| `k` | float | - | 只读 | 读写 | 读取或修改 `_default_values[0]` 的惩罚系数 |
| `target` | float | - | 只读 | 读写 | 读取或修改 `_default_values[1]` 的目标值 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `2` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建、值写入和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 根据对象名称和类型解析目标自由度 |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA PenaltyDoF |
| `_apply_values(values)` | None | `BaseFEAComponent` | 更新惩罚系数和目标值 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立目标对象与自由度方向标记 |

### 7.13 `Contact`

`Contact` 定义两个 Instance 的两个 Surface 之间的接触关系。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_instance_name_1` | str | 构造函数传入 | 第一个 Instance |
| `_surface_name_1` | str | 构造函数传入 | 第一个 Surface |
| `_instance_name_2` | str | 构造函数传入 | 第二个 Instance |
| `_surface_name_2` | str | 构造函数传入 | 第二个 Surface |
| `_penalty_threshold_h` | float | `3.0` | 接触阈值 |
| `_penalty_start_f` | float 或 None | None | 惩罚起始系数 |
| `_penalty_end_f` | float 或 None | None | 惩罚终止系数 |

注册名称沿用 `BaseFEAComponent` 的 `_name`；接触没有独立的工况值向量。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Contact` | `torchfea.loads.Contact` 或 None | None | 已创建的 TorchFEA 接触对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `instance_name_1` | str | - | 只读 | 内部维护 | 返回第一个 Instance 名称 |
| `surface_name_1` | str | - | 只读 | 内部维护 | 返回第一个 Surface 名称 |
| `instance_name_2` | str | - | 只读 | 内部维护 | 返回第二个 Instance 名称 |
| `surface_name_2` | str | - | 只读 | 内部维护 | 返回第二个 Surface 名称 |
| `penalty_threshold_h` | float | - | 只读 | 内部维护 | 返回接触阈值 |
| `penalty_start_f` | float 或 None | - | 只读 | 内部维护 | 返回惩罚起始系数 |
| `penalty_end_f` | float 或 None | - | 只读 | 内部维护 | 返回惩罚终止系数 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | tuple[object, object] | `BaseFEAComponent` | 解析两个 Surface |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA Contact |
| `_apply_values(values)` | None | `BaseFEAComponent` | 校验零长度值向量并保持接触参数 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立两侧接触面的分组预览 |

### 7.14 `SelfContact`

`SelfContact` 定义同一个 Instance 的一个 Surface 的自接触关系。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_instance_name` | str | 构造函数传入 | 目标 Instance |
| `_surface_name` | str | 构造函数传入 | 目标 Surface |
| `_penalty_threshold_h` | float 或 None | None | 接触阈值 |

注册名称沿用 `BaseFEAComponent` 的 `_name`；自接触没有独立的工况值向量。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_SelfContact` | `torchfea.loads.ContactSelf` 或 None | None | 已创建的 TorchFEA 自接触对象 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `instance_name` | str | - | 只读 | 内部维护 | 返回目标 Instance |
| `surface_name` | str | - | 只读 | 内部维护 | 返回目标 Surface |
| `penalty_threshold_h` | float 或 None | - | 只读 | 内部维护 | 返回接触阈值 |
| `num_values` | int | `BaseFEAComponent` | 只读 | 内部维护 | 固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体目标解析、后端创建和预览由下列重写钩子提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 本类没有新增或重写的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_resolve_target(assembly)` | object | `BaseFEAComponent` | 解析目标 Surface |
| `_create_fea_object()` | object | `BaseFEAComponent` | 创建 TorchFEA SelfContact |
| `_apply_values(values)` | None | `BaseFEAComponent` | 校验零长度值向量并保持接触参数 |
| `_build_preview_meshes()` | list[object] | `BaseFEAComponent` | 建立自接触曲面的高亮预览 |

### 7.15 `LoadStep`

`LoadStep` 表示一个完整工况行。它保存每个注册 component 的值向量，并在初始化阶段
转换为 Torch Tensor 缓存。值向量长度由 component 的 `num_values` 决定。

#### 值向量布局

| component | `num_values` | 顺序 |
|---|---:|---|
| `Pressure` | 1 | `[pressure]` |
| `BodyForce` | 3 | `[fx, fy, fz]` |
| `ConcentratedForce` | 3 | `[fx, fy, fz]` |
| `ConcentratedMoment` | 3 | `[mx, my, mz]` |
| `SpringToGround` | 5 | `[k, rest_length, px, py, pz]` |
| `SpringBetweenRPs` | 2 | `[k, rest_length]` |
| `PenaltyDoF` | 2 | `[k, target]` |
| `BoundaryCondition`、`BoundaryConditionRP`、`Couple`、`Contact`、`SelfContact` | 0 | 空向量 |

规则：

- 值向量的下标顺序就是 `num_values` 的顺序，也是载荷设计变量块内局部索引的顺序；
- 库已有的 setter 直接复用：`Concentrate_Force.force`、`Moment.moment`、`Spring_RP_RP.k`/`rest_length`；
  其余组件的写入点是 `_apply_values()` 内对库对象属性的赋值，不再经过 morphopt 侧的第二份缓存；
- `BodyForce` 在写入力密度后必须重建积分缓存 `_pdU_values`（用元素的高斯权重与
  `shape_function_d0_gaussian` 重新计算），否则切线会使用旧值；
- `BoundaryCondition.index_dof`、`BoundaryConditionRP.index_dof`、`Contact`/`SelfContact` 的
  罚参数和 `Couple`/`Spring*`/`PenaltyDoF` 的目标名称都是构造参数而不是工况值，构造时按
  元组或标量复制保存，调用方后续修改自己的容器不影响已构造对象；
- `BoundaryConditionRP.index_dof` 默认值为全部 6 个自由度（库默认）；
- 零值 component 在每个工况行中仍然存在（空向量），并参与 `define_steps()` 的完整性校验。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_step_index` | int | 构造函数传入 | 工况序号 |
| `_component_values` | dict[str, list[float]] | `{}` | component 名称到值向量 |

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_resolved_values` | dict[str, torch.Tensor] | `{}` | 校验和转换后的值向量 |
| `_initialized` | bool | False | 初始化状态 |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `step_index` | int | - | 只读 | 内部维护 | 返回工况序号 |
| `component_values` | Mapping[str, tuple[float, ...]] | - | 只读 | 内部维护 | 返回定义阶段值向量 |

#### 4. 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_component_values(name, values)` | None | - | 修改当前工况的已有值向量 |
| `get_resolved_values()` | Mapping[str, torch.Tensor] | - | 读取已校验的 Tensor 值向量 |
| `initialize(components)` | None | `Initializable` | 按注册表补齐并校验 component 值 |
| `reinitialize(iteration)` | None | `Initializable` | 按当前定义刷新已解析值缓存 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存工况数据 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载工况数据 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_validate_component_values(components)` | None | 校验名称集合和向量长度 |
| `_build_resolved_values()` | None | 创建 Tensor 值缓存 |

### 7.16 `LoadValueBlock`

`LoadValueBlock` 将一个 `LoadStep` 中一个参数化 component 的值适配为 `Updatable` owner。
`FEAParams.initialize()` 按 `(component_name, case_index)` 建立这些对象，零参数 component
不建立变量块。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_component_name` | str | - | FEA component 稳定名称 |
| `_case_index` | int | - | 所属工况索引 |
| `_component` | `BaseFEAComponent` | - | 负责更新 TorchFEA 对象的 component |
| `_load_step` | `LoadStep` | - | 已提交参数的唯一事实来源 |

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_design_delta` | torch.Tensor 或 None | None | 当前迭代零基准设计增量 |
| `_case_component` | `BaseFEAComponent` 或 None | None | 绑定到所属工况 Assembly 的独立 component 运行副本 |
| `_torchfea_Assembly` | torchfea.Assembly 或 None | None | 所属工况的独立 Assembly |

#### 3. 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `component_name` | str | - | 只读 | 内部维护 | 返回 component 名称 |
| `case_index` | int | - | 只读 | 内部维护 | 返回工况索引 |
| `component` | `BaseFEAComponent` | - | 只读 | 内部维护 | 返回 component 定义对象 |
| `load_step` | `LoadStep` | - | 只读 | 内部维护 | 返回工况定义 |

#### 4. 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `update_case_binding(assembly, component)` | None | - | 绑定所属工况 Assembly 和已经挂接的独立 component 运行副本 |
| `get_parameters()` | torch.Tensor | `Updatable` | 读取 LoadStep 中已提交值的 detached clone |
| `set_parameters(parameters)` | None | `Updatable` | 写入 LoadStep 中已有 component 值 |
| `build_design_delta()` | None | `Updatable` | 建立同形全零、`requires_grad=True` 的增量 |
| `get_design_delta()` | torch.Tensor | `Updatable` | 读取已经建立的设计增量 |
| `update_assembly(design_delta)` | None | `Updatable` | 将已提交值与试探增量之和写入当前工况独立 component |
| `apply_design_delta(design_delta)` | None | `Updatable` | 将增量提交到 LoadStep 的 component 值 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_validate_design_delta(design_delta)` | None | 校验形状、device、dtype 和有限性 |
| `_get_trial_values(design_delta)` | torch.Tensor | 建立保留计算图的工况试探值 |

同一 component 可在多个工况中拥有不同参数；每个 `LoadValueBlock` 因此对应一个独立的
`DesignKey(category="load", target_name=component_name, case_index=case_index)`。
`FEAParams.build_case_assemblies()` 先为每个工况建立 Assembly 与 component 运行副本，再调用
`update_case_binding()`。随后 Registry 只把该 block 的局部设计增量写入所属工况对象。
`LoadStep` 始终保存已提交值，试探值只存在于工况运行副本中，因此 line search、梯度检查和
多个工况的灵敏度计算可以同时保留各自的 autograd 图。
