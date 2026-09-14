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
    → FEAParams.assign_components(assembly)
    → FEAParams.update_fea(step_index)
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
`FEAParams.assign_components(assembly)` 写入当前 Assembly，供后续处理器读取。

#### 定义属性（注册表由 `__init__()` 创建，`define_components()` / `define_steps()` 填充）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_fea_components` | dict[str, BaseFEAComponent] | `{}` | component 注册表 |
| `_load_steps` | list[LoadStep] | `[]` | 按 step index 排序的工况 |

#### 运行时属性（`__init__()` 声明，`initialize()` / `reinitialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Assembly` | torchfea.Assembly 或 None | None | 当前迭代绑定的 Assembly |
| `_component_targets` | dict[str, object] | `{}` | component 到 Assembly 目标的索引 |
| `_initialized` | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `fea_components` | Mapping[str, BaseFEAComponent] | 只读 | 内部维护 | component 注册表只读视图 |
| `load_steps` | tuple[LoadStep, ...] | 只读 | 内部维护 | 工况定义只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `define_components()` | None | 定义扩展点 | 通过 `add_component()` 注册全部 component |
| `define_steps()` | None | 定义扩展点 | 通过 `set_num_steps()` 和 `set_step_values()` 创建工况 |
| `add_component(component, name)` | None | 注册接口 | 将 component 写入唯一名称注册表 |
| `set_num_steps(num_steps)` | None | 定义接口 | 创建指定数量的 LoadStep |
| `set_step_values(step_index, component_name, values)` | None | 定义接口 | 修改指定工况的 component 值 |
| `assign_components(assembly)` | None | - | 将已经建立的 component 对象写入当前 Assembly |
| `initialize()` | None | `Initializable` | 初始化注册表和工况定义 |
| `reinitialize(iteration, assembly)` | None | `Initializable` | 解析当前 Assembly 并刷新所有 component |
| `build_components()` | None | FEA protocol | 使用已绑定的 Assembly 创建并保存全部 component 的 TorchFEA 对象 |
| `update_fea(step_index)` | None | FEA protocol | 将指定工况的值写入已有 FEA 对象 |
| `get_num_load_steps()` | int | 读取接口 | 读取工况数量 |
| `get_parameters()` | list[torch.Tensor] | `Updatable` | 读取所有工况参数 |
| `set_parameters(parameters)` | None | `Updatable` | 写入所有工况参数 |
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
| `_build_components()` | None | 创建各 component 的 TorchFEA 对象并写入其 `_torchfea_<ConcreteName>` |

`FEAParams` 的注册顺序为：

```text
define_components()
    → add_component(component, name)
define_steps()
    → set_num_steps(num_steps)
    → set_step_values(step_index, component_name, values)
initialize()
reinitialize(iteration, assembly)
build_components()
update_fea(step_index)
```

模型导入由几何层 `INPPart` 或 `TorchFEAPart` 提供；`FEAParams` 从几何层接收已经建立的
`Assembly`，并依据 Instance、Surface、NodeSet、ElementSet 和几何层 ReferencePoint 名称解析
component 目标。

### 7.2 `BaseFEAComponent`

`BaseFEAComponent` 是所有载荷、边界、接触和耦合 component 的协议基类，显式继承
`Visualizable`、`Initializable`、`Updatable` 和 `Persistable`。定义阶段保存名称、目标名称和初始值；
运行时阶段在 `_torchfea_Assembly` 中缓存当前 `Assembly`，解析目标并创建 TorchFEA 对象。具体 component 由
`FEAParams.add_component()` 注册。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | `""` | 注册后的稳定 component 名称 |
| `_values` | list[float] | 按 `num_values` 创建 | 当前工况值向量；约束类的长度为零 |
| `_target_names` | tuple[str, ...] | `()` | Instance、Surface、Set 或 RP 名称 |

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Assembly` | torchfea.Assembly 或 None | None | `reinitialize()` 绑定的当前 Assembly |
| `_target` | object 或 None | None | 从当前 Assembly 解析出的目标对象 |
| `_mesh_cache` | list[object] | `[]` | 已建立的 component 预览对象 |
| `_initialized` | bool | False | 当前 component 的初始化状态 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 内部维护 | 返回注册名称 |
| `values` | tuple[float, ...] | 只读 | 内部维护 | 返回当前值向量的只读副本 |
| `num_values` | int | 只读 | 子类实现 | 返回当前 component 的值向量长度 |
| `target_names` | tuple[str, ...] | 只读 | 内部维护 | 返回定义阶段记录的目标名称 |

#### 4. 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `initialize()` | None | `Initializable` | 建立 component 的静态定义状态 |
| `reinitialize(iteration, assembly)` | None | `Initializable` | 解析当前 Assembly 的 Instance、Surface、Set 和 RP |
| `build_fea()` | None | FEA protocol | 创建具体 TorchFEA 对象并写入子类的 `_torchfea_<ConcreteName>` |
| `get_fea_object()` | object | FEA protocol | 读取已经创建的 TorchFEA 对象 |
| `update_fea(values)` | None | FEA protocol | 更新已有对象的当前工况值 |
| `get_parameters()` | torch.Tensor | `Updatable` | 读取当前值的 detached 副本 |
| `set_parameters(parameters)` | None | `Updatable` | 写入已有值向量 |
| `update_assembly(design_delta)` | None | `Updatable` | 使用自身的 TorchFEA component 和 Assembly 引用更新试探载荷或约束值 |
| `build_meshes()` | None | `Visualizable` | 建立并保存 component 预览缓存 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的预览缓存 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存 component 定义和运行状态 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载指定迭代的 component 状态 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_target(assembly)` | object | 根据目标名称解析 Assembly 对象 |
| `_validate_values(values)` | None | 校验值向量长度和数值类型 |

`build_fea()` 只创建运行时对象并写入具体子类的 `_torchfea_<ConcreteName>`；
`get_fea_object()` 读取已建立对象；
`update_fea()` 更新当前工况。需要设计变量的 component 通过 `get_parameters()`、
`set_parameters()` 和 `update_fea()` 接入设计变量流程。

### 7.3 `Pressure`

`Pressure` 将标量压力施加到某个 Instance 的 Surface set。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_instance_name` | str | `"final_model"` | 目标 Instance 名称 |
| `_surface_name` | str | 构造函数传入 | 目标 Surface set 名称 |

注册名称和工况值向量沿用 `BaseFEAComponent` 的 `_name` 和 `_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Pressure` | `torchfea.loads.Pressure` 或 None | None | 已创建的 TorchFEA 压力对象 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `instance_name` | str | 只读 | 构造阶段 | 返回目标 Instance |
| `surface_name` | str | 只读 | 构造阶段 | 返回目标 Surface set |
| `pressure` | float | 读写 | 读写 | 读取或修改压力标量 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `1` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体压力目标由 `_resolve_surface()` 和 `_build_pressure()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_surface(assembly)` | object | 解析目标 Surface set |
| `_build_pressure(assembly)` | object | 创建 TorchFEA Pressure |

### 7.4 `BodyForce`

`BodyForce` 将三方向体力密度施加到指定 Instance 的元素集合。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_instance_name` | str | `"final_model"` | 目标 Instance 名称 |
| `_element_name` | str | 构造函数传入 | 目标元素名称 |

注册名称和工况值向量沿用 `BaseFEAComponent` 的 `_name` 和 `_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_BodyForce` | `torchfea.loads.BodyForce` 或 None | None | 已创建的 TorchFEA 体力对象 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `instance_name` | str | 只读 | 构造阶段 | 返回目标 Instance |
| `element_name` | str | 只读 | 构造阶段 | 返回元素名称 |
| `force_density` | list[float] | 读写 | 读写 | 三方向体力密度 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `3` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体体力目标由 `_resolve_elements()` 和 `_update_cached_values()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_elements(assembly)` | object | 解析目标元素集合 |
| `_update_cached_values()` | None | 更新 TorchFEA 体力缓存 |

### 7.5 `ConcentratedForce`

`ConcentratedForce` 将三方向集中力施加到一个参考点。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name` | str | 构造函数传入 | 目标参考点名称 |

注册名称和工况值向量沿用 `BaseFEAComponent` 的 `_name` 和 `_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_ConcentratedForce` | `torchfea.loads.ConcentratedForce` 或 None | None | 已创建的 TorchFEA 集中力对象 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `reference_point_name` | str | 只读 | 构造阶段 | 返回参考点名称 |
| `force` | list[float] | 读写 | 读写 | 三方向集中力 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `3` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体集中力对象由 `_resolve_reference_point()` 和
`_build_force_arrow()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_reference_point(assembly)` | object | 解析目标参考点 |
| `_build_force_arrow()` | object | 创建集中力可视化对象 |

### 7.6 `ConcentratedMoment`

`ConcentratedMoment` 将三方向集中力矩施加到一个参考点。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name` | str | 构造函数传入 | 目标参考点名称 |

注册名称和工况值向量沿用 `BaseFEAComponent` 的 `_name` 和 `_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_ConcentratedMoment` | `torchfea.loads.ConcentratedMoment` 或 None | None | 已创建的 TorchFEA 集中力矩对象 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `reference_point_name` | str | 只读 | 构造阶段 | 返回参考点名称 |
| `moment` | list[float] | 读写 | 读写 | 三方向集中力矩 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `3` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，具体集中力矩对象由 `_resolve_reference_point()` 和
`_build_moment_arrow()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_reference_point(assembly)` | object | 解析目标参考点 |
| `_build_moment_arrow()` | object | 创建集中力矩可视化对象 |

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

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `instance_name` | str | 只读 | 构造阶段 | 返回目标 Instance |
| `node_set_name` | str | 只读 | 构造阶段 | 返回 Node set 名称 |
| `index_dof` | tuple[int, ...] | 只读 | 构造阶段 | 返回约束自由度 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，目标解析和 DOF 校验由 `_resolve_node_set()` 和 `_validate_dof()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_node_set(assembly)` | object | 解析目标 Node set |
| `_validate_dof()` | None | 校验自由度索引 |

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

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `reference_point_name` | str | 只读 | 构造阶段 | 返回参考点名称 |
| `index_dof` | tuple[int, ...] | 只读 | 构造阶段 | 返回约束自由度 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，目标解析和 DOF 校验由 `_resolve_reference_point()` 和 `_validate_dof()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_reference_point(assembly)` | object | 解析目标参考点 |
| `_validate_dof()` | None | 校验自由度索引 |

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

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `reference_point_name` | str | 只读 | 构造阶段 | 返回参考点名称 |
| `instance_name` | str | 只读 | 构造阶段 | 返回目标 Instance |
| `node_set_name` | str | 只读 | 构造阶段 | 返回 Node set 名称 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，目标解析和耦合对象建立由 `_resolve_targets()` 和 `_build_couple()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_targets(assembly)` | tuple[object, object] | 解析 RP 和 Node set |
| `_build_couple(assembly)` | object | 创建 TorchFEA Couple |

### 7.10 `SpringToGround`

`SpringToGround` 在参考点和固定空间点之间建立非线性轴向弹簧。值向量为
`[k, rest_length, px, py, pz]`。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name` | str | 构造函数传入 | 目标参考点 |

注册名称和工况值向量沿用 `BaseFEAComponent` 的 `_name` 和 `_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_SpringToGround` | `torchfea.constraints.Spring_RP_Point` 或 None | None | 已创建的 TorchFEA 参考点-固定点弹簧对象 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `reference_point_name` | str | 只读 | 构造阶段 | 返回参考点名称 |
| `k` | float | 读写 | 读写 | 弹簧刚度 |
| `rest_length` | float | 读写 | 读写 | 弹簧原长 |
| `point` | list[float] | 读写 | 读写 | 固定空间点坐标 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `5` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，目标解析和弹簧对象建立由 `_resolve_reference_point()` 和
`_build_spring()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_reference_point(assembly)` | object | 解析参考点 |
| `_build_spring(assembly)` | object | 创建 TorchFEA Spring_RP_Point |

### 7.11 `SpringBetweenRPs`

`SpringBetweenRPs` 在两个参考点之间建立非线性轴向弹簧。值向量为 `[k, rest_length]`。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_reference_point_name_1` | str | 构造函数传入 | 第一个参考点 |
| `_reference_point_name_2` | str | 构造函数传入 | 第二个参考点 |

注册名称和工况值向量沿用 `BaseFEAComponent` 的 `_name` 和 `_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_SpringBetweenRPs` | `torchfea.constraints.Spring_RP_RP` 或 None | None | 已创建的 TorchFEA 参考点-参考点弹簧对象 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `reference_point_name_1` | str | 只读 | 构造阶段 | 返回第一个参考点名称 |
| `reference_point_name_2` | str | 只读 | 构造阶段 | 返回第二个参考点名称 |
| `k` | float | 读写 | 读写 | 弹簧刚度 |
| `rest_length` | float | 读写 | 读写 | 弹簧原长 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `2` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，目标解析和弹簧对象建立由 `_resolve_reference_points()` 和
`_build_spring()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_reference_points(assembly)` | tuple[object, object] | 解析两个参考点 |
| `_build_spring(assembly)` | object | 创建 TorchFEA Spring_RP_RP |

### 7.12 `PenaltyDoF`

`PenaltyDoF` 在对象的指定自由度上施加二次惩罚。值向量为 `[k, target]`。

#### 1. 构造属性

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_object_name` | str | 构造函数传入 | 目标对象名称 |
| `_dof_index` | int | 构造函数传入 | 目标自由度索引 |
| `_object_type` | str | `"auto"` | 对象类型解析模式 |

注册名称和工况值向量沿用 `BaseFEAComponent` 的 `_name` 和 `_values`。

#### 2. 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_PenaltyDoF` | `torchfea.constraints.Penalty_DoF` 或 None | None | 已创建的 TorchFEA 自由度惩罚对象 |

#### 3. 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `object_name` | str | 只读 | 构造阶段 | 返回目标对象名称 |
| `dof_index` | int | 只读 | 构造阶段 | 返回目标自由度 |
| `object_type` | str | 只读 | 构造阶段 | 返回对象类型 |
| `k` | float | 读写 | 读写 | 惩罚系数 |
| `target` | float | 读写 | 读写 | 目标值 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `2` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，目标解析和惩罚对象建立由 `_resolve_object()` 和 `_build_penalty()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_object(assembly)` | object | 根据对象名称和类型解析目标 |
| `_build_penalty(assembly)` | object | 创建 TorchFEA Penalty_DoF |

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

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `instance_name_1` / `instance_name_2` | str | 只读 | 构造阶段 | 两个 Instance 名称 |
| `surface_name_1` / `surface_name_2` | str | 只读 | 构造阶段 | 两个 Surface 名称 |
| `penalty_threshold_h` | float | 只读 | 构造阶段 | 接触阈值 |
| `penalty_start_f` / `penalty_end_f` | float 或 None | 只读 | 构造阶段 | 惩罚起止参数 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，目标解析和接触对象建立由 `_resolve_surfaces()` 和 `_build_contact()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_surfaces(assembly)` | tuple[object, object] | 解析两个 Surface |
| `_build_contact(assembly)` | object | 创建 TorchFEA Contact |

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

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `instance_name` | str | 只读 | 构造阶段 | 返回目标 Instance |
| `surface_name` | str | 只读 | 构造阶段 | 返回目标 Surface |
| `penalty_threshold_h` | float 或 None | 只读 | 构造阶段 | 接触阈值 |
| `num_values` | int | 只读 | 内部维护 | 本类重写 `BaseFEAComponent.num_values`，固定为 `0` |

#### 4. 外部接口方法

本类不重写 `initialize()`、`reinitialize()`、`build_fea()`、`get_fea_object()`、
`update_fea()`、`build_meshes()`、`get_meshes()`、`save()` 或 `load()`；这些接口均继承
`BaseFEAComponent`，目标解析和自接触对象建立由 `_resolve_surface()` 和
`_build_self_contact()` 提供。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | `BaseFEAComponent` | 本类没有额外的外部接口方法 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_surface(assembly)` | object | 解析目标 Surface |
| `_build_self_contact(assembly)` | object | 创建 TorchFEA ContactSelf |

### 7.15 `LoadStep`

`LoadStep` 表示一个完整工况行。它保存每个注册 component 的值向量，并在初始化阶段
转换为 Torch Tensor 缓存。值向量长度由 component 的 `num_values` 决定。

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

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `step_index` | int | 只读 | 内部维护 | 返回工况序号 |
| `component_values` | Mapping[str, tuple[float, ...]] | 只读 | 内部维护 | 返回定义阶段值向量 |

#### 4. 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `initialize(components)` | None | `Initializable` | 按注册表补齐并校验 component 值 |
| `reinitialize(iteration, assembly)` | None | `Initializable` | 刷新当前工况运行缓存 |
| `set_component_values(name, values)` | None | 定义接口 | 修改当前工况的已有值向量 |
| `get_resolved_values()` | Mapping[str, torch.Tensor] | 运行时读取 | 读取已校验的 Tensor 值向量 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存工况数据 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载工况数据 |

#### 5. 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_validate_component_values(components)` | None | 校验名称集合和向量长度 |
| `_build_resolved_values()` | None | 创建 Tensor 值缓存 |
