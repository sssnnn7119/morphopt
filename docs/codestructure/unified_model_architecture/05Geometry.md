# MorphOpt V4 几何系统

本文件定义 Part、Instance、ReferencePoint、BoundaryPart、曲面接口、STP/STL 导出和偏置壳。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文定义几何系统的对象边界和运行时产物：`GeometryParams` 负责 Part/Instance 注册与
Assembly 聚合和参考点注册，`BoundaryPart` 负责曲面和网格，导入型 Part 负责固定 Assembly 缓存，
曲面接口负责几何值、预览网格和外部曲面导出，`OffsetShellPart` 负责向内偏置。

### 目录

- [5. 几何类定义](#5-几何类定义)
- [5.1 GeometryParams](#51-geometryparams) 与 [5.2 BasePartDefinition](#52-basepartdefinition)
- [5.3 InstanceDefinition](#53-instancedefinition) 与 [5.4 BoundaryPart](#54-boundarypart)
- [5.4.1–5.4.8 曲面接口与具体曲面](#541-basesurfaceinterface)
- [5.4.9 曲面导出与最终模型构建](#549-曲面导出与最终模型构建)
- [5.5 INPPart](#55-inppart)、[5.6 TorchFEAPart](#56-torchfeapart)、[5.7 OffsetShellPart](#57-offsetshellpart)
- [5.8 ReferencePoint](#58-referencepoint)
- [5.9 几何运行服务与摘要](#59-几何运行服务与摘要)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | Part/Instance/ReferencePoint 定义、曲面参数与控制点、INP/TorchFEA 模型路径、网格参数、偏置选择和元素名称 |
| 输出 | `torchfea.Part`、`torchfea.Assembly`、ReferencePoint、surface/node/element set、预览网格、几何设计变量和 STP/STL 文件 |
| 主要读者 | 几何对象实现者、材料/FEA 目标解析者、可视化和 UI/Codegen 实现者 |
| 关联文档 | [总览与生命周期](01-04Overview.md)、[FEA 组件](07Fea.md)、[Solver](08Solver.md)、[运行时](13-14Runtime.md)、[功能迁移清单](23FunctionInventory.md) |

## 5. 几何类定义

### 5.1 `GeometryParams`

#### 构造属性（注册表由 `__init__()` 创建，`define_parts()` / `define_reference_points()` 填充）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_parts` | dict[str, `BasePartDefinition`] | {} | 按注册顺序记录每个输出 `Part` 的定义 |
| `_reference_points` | dict[str, `ReferencePoint`] | {} | 按注册顺序记录 Assembly 级参考点定义 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Assembly` | `torchfea.Assembly` 或 None | None | 当前生成或复用的 `Assembly` |
| `_element_names` | dict[str, tuple[str, ...]] | {} | `part_name` 到已校验元素名称集合的派生索引 |
| `_initialized` | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `parts` | Mapping[str, `BasePartDefinition`] | 只读 | 内部维护 | 返回以输出 `part_name` 为键的 Part 定义只读视图 |
| `reference_points` | Mapping[str, `ReferencePoint`] | 只读 | 内部维护 | 返回 Assembly 级参考点定义的只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `define_parts()` | None | - | 在定义阶段通过 `add_part()` 注册全部 `Part` 的扩展点 |
| `add_part(part)` | None | - | 使用 `part.part_name` 注册一个 Part 定义，并校验元素名称集合长度大于零 |
| `define_reference_points()` | None | - | 在定义阶段通过 `add_reference_point()` 注册全部 Assembly 级参考点的扩展点 |
| `add_reference_point(reference_point)` | None | - | 使用 `reference_point.name` 注册一个 Assembly 级参考点定义 |
| `build_assembly(path_result, pools)` | None | - | 从当前定义创建 `Assembly` 并写入 `_torchfea_Assembly`；返回值为 `None` |
| `get_assembly()` | `torchfea.Assembly` | - | 读取已经创建的 `Assembly`，不重新构建 |
| `get_design_owners()` | tuple[`BoundaryPart` 或 `OffsetShellPart`, ...] | - | 按 `part_name` 读取具体可更新 Part |
| `initialize()` | None | `Initializable` | 初始化并校验所有 `Part`、元素名称集合、`Instance` 和 `ReferencePoint` |
| `reinitialize(iteration)` | None | `Initializable` | 调用每个 `Part` 的迭代刷新 |
| `build_meshes()` | None | `Visualizable` | 建立并保存全部 `Part` 的可视化预览网格缓存 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的所有 `Part` 预览网格 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存几何状态和相关结果 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载几何状态和相关结果 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

`BoundaryPart`、`OffsetShellPart`、`INPPart` 和 `TorchFEAPart` 都实现
`BasePartDefinition` 的单 Part 生命周期。导入类型额外缓存源 Assembly，并从中提取一个
选定 Part、集合和实例定义。需要从同一源模型使用多个 Part 时，为每个源 Part 注册一个
`INPPart` 或 `TorchFEAPart`，这些定义可以共享同一模型路径和读取缓存。

`add_part()` 接收带有稳定输出 `part_name` 的几何定义；名称来源只有 `part.part_name`。单个定义通过
`geometry.parts[part_name]` 访问，注册表是单一事实来源。
`GeometryParams.get_design_owners()` 向 `DesignRegistry` 提供具体 owner，设计增量和更新由
各可更新 `Part` 独立维护。`GeometryParams.build_assembly()` 负责
创建新的 `Assembly` 并写入 `_torchfea_Assembly`；已有模型的可微更新由具体 owner 的
`update_assembly()` 负责，调用方通过 `get_assembly()` 读取已经创建的对象。

`GeometryParams.build_assembly()` 按 `parts` 的稳定顺序调用每个定义的 `build_part()` 和
`get_part()`，再创建该定义的全部 `Instance` 并写入新的目标 Assembly。生成型 Part 根据
当前几何状态建立；导入 Part 从内部缓存的源 Assembly 提取并复制选定 Part。统一装配过程
负责全局名称冲突校验，并保持 Part、Instance、Surface、NodeSet、ElementSet 和元素族名称。

`GeometryParams.build_assembly()` 在 Part 和 Instance 装配完成后，按
`reference_points` 的注册顺序调用每个参考点的 `build_reference_point()`，将全部参考点写入
`_torchfea_Assembly`。参考点定义由几何层持有，FEA 层通过名称解析已建立对象。

### 5.2 `BasePartDefinition`

这是生成型 `Part` 类型的共同基类，显式继承 `Visualizable`、`Initializable` 和
`Persistable`，维护一个 `Part` 的实例属性和生命周期。`build_part()` 是生成型
`Part` 的抽象核心方法，由 `BoundaryPart`、`OffsetShellPart` 等具体类型实现。
`INPPart` 和 `TorchFEAPart` 继承本节接口，以只读源 `Assembly` 作为导入缓存，并把选定
Part 写入 `_torchfea_Part`。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_name` | str | 构造函数必填 | `Part` 唯一名称 |
| `_element_names` | tuple[str, ...] 或 None | None | 当前 `Part` 的输出元素名称；生成型定义显式提供，导入型定义在初始化时解析 |
| `_exterior_surface` | str | `'extern'` | `Part` 级外表面集合名称；由具体 `Part` 定义 |
| `_instances` | dict[str, `InstanceDefinition`] | {} | `Instance` 定义集合 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Part` | `torchfea.Part` 或 None | None | 最近建立或从源 Assembly 提取的 TorchFEA `Part` |
| `_initialized` | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `part_name` | str | 只读 | 内部维护 | 返回稳定的 `Part` 名称 |
| `element_names` | tuple[str, ...] 或 None | 只读 | 内部维护 | 返回构造阶段声明的元素名称；导入型定义初始化后返回解析结果 |
| `exterior_surface` | str | 只读 | 读写 | setter 校验并更新整体 surface set 名称 |
| `instances` | Mapping[str, `InstanceDefinition`] | 只读 | 内部维护 | 返回 `Instance` 的只读视图 |

构造属性和运行时属性都属于每个 `Part` 实例；运行时属性在构造
阶段先声明初始值，再由 `initialize()` 填充。

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `define_instances()` | None | - | 通过 `add_instance()` 注册本 Part 的实例定义 |
| `add_instance(instance)` | None | - | 按全局唯一名称注册一个 `InstanceDefinition` |
| `build_part(path_result, pools)` | None | - | 从当前定义创建 `Part` 并写入 `_torchfea_Part`；返回值为 `None` |
| `get_part()` | `torchfea.Part` | - | 读取已经创建的 `Part`，不重新构建 |
| `initialize()` | None | `Initializable` | 初始化源数据、拓扑和缓存，并校验 `element_names` |
| `reinitialize(iteration)` | None | `Initializable` | 准备当前迭代数据 |
| `build_meshes()` | None | `Visualizable` | 建立并保存当前 Part 的预览网格 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的预览网格 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存当前几何状态 |
| `load(folder_path, iteration)` | None | `Persistable` | 加载指定 `iteration` 的几何状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 具体 Part 的内部辅助函数由具体子类定义 |

`build_part()` 创建一个 TorchFEA `Part` 并写入 `_torchfea_Part`；调用方通过
`get_part()` 读取该对象。`GeometryParams.build_assembly()` 负责将生成型 `Part` 和
`Instance` 放入 `Assembly`。需要参与形状优化的具体 `Part` 通过 `Updatable` 提供
Assembly 试探更新和正式提交方法。导入类型在内部缓存源 Assembly，并通过统一的
`build_part()` / `get_part()` 将选定 Part 交给 GeometryParams 装配。

`build_meshes()` 和 `get_meshes()` 只属于 `Visualizable` 可视化协议：前者建立并写入
预览缓存，后者读取缓存。生成型 `Part` 的预览流程与 `build_part()`/`get_part()` 配合；
导入模型的预览流程读取内部源 Assembly 与选定 Part。

`BasePartDefinition.element_names` 是该 `Part` 输出的 `elems` 名称集合。普通具体
`BoundaryPart` 的构造函数接收一个必填 `element_name` 并形成单元素集合；
`OffsetShellPart` 接收必填的 `solid_element_name` 和 `shell_element_name` 并形成
两元素集合。`initialize()` 校验生成或导入结果中存在对应元素。
材料接口使用自身的 `part_name` 和 `element_name` 成对定位这些 `elems`；一个材料对象
对应一个 `Part` 中的一种元素类型。

对于 `INPPart` 和 `TorchFEAPart`，构造函数传入的 `element_names` 是与源模型元素族
一一对应的名称列表；列表长度必须等于源模型元素族数量。省略该列表时，
`initialize()` 直接采用源元素类型名称，并完成元素名称映射。对于
`BoundaryPart`，它是新建元素集合在 `Part.elems` 中使用的名称；对于
`OffsetShellPart`，`source_surface` 是与边界曲面顺序对应的布尔列表：索引 `0` 固定为
`False` 并保留原始曲面，索引 `1` 及以后表示对应曲面是否生成向内偏置；偏置曲面集合使用
`surface_{i}_offset` 命名。

`initialize()` 执行 `define_instances()` 并校验实例注册表；注册表为空时建立一个名称等于
`part_name` 的零变换实例。导入 Part 可以从源 Assembly 生成实例定义，用户注册的实例定义
按名称和变换形成最终装配配置。

### 5.3 `InstanceDefinition`

`InstanceDefinition` 是一个稳定的数据对象。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | 必填 | `Assembly` 全局唯一名称 |
| `_translation` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 平移向量 |
| `_rotation` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 旋转向量 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Instance` | `torchfea.Instance` 或 None | None | 由 `build_instance()` 创建的运行时实例 |

运行时对象由 `build_instance()` 创建并写入 `_torchfea_Instance`；`InstanceDefinition` 保存名称和
变换，调用方通过 `get_instance()` 读取已经创建的对象。

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 内部维护 | 返回实例名称 |
| `translation` | tuple[float, float, float] | 只读 | 内部维护 | 返回平移向量 |
| `rotation` | tuple[float, float, float] | 只读 | 内部维护 | 返回旋转向量 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `validate()` | None | - | 校验名称和变换维度 |
| `build_instance(part)` | None | - | 创建 TorchFEA `Instance` 并写入 `_torchfea_Instance` |
| `get_instance()` | `torchfea.Instance` | - | 读取已经创建的 `Instance`，不重新创建 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

一个 `Part` 可以定义任意多个 `Instance`。所有 `Instance` 共享 `Part` 的网格和设计
变量。用户未注册 `Instance` 时，系统创建一个与 part_name 同名的零变换 `Instance`。

### 5.4 `BoundaryPart`

`BoundaryPart` 由有序边界曲面集合生成可网格化的 TorchFEA `Part`，是形状优化的
基础类型，并显式继承 `Updatable`。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_name` | str | final_model | 形状优化默认名称 |
| `_element_name` | str | 构造函数必填 | 生成的单一 `Part.elems` 名称 |
| `_surfaces` | list[`BaseSurfaceInterface`] | [] | 有序曲面集合 |
| `_fea_seed_size` | float | 由网格器确定 | 网格种子尺寸 |
| `_mesh_order` | int | 由网格器确定 | 网格阶数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_control_points` | list[torch.Tensor] | [] | 曲面控制点 |
| `_surface_sets` | dict[str, object] | {} | 自动生成的 surface set 缓存 |
| `_geometry_values` | tuple[list[torch.Tensor], list[torch.Tensor], list[torch.Tensor]] 或 None | None | 各曲面的 `r`、`rdu`、`rdu2` 缓存 |
| `_points_weight` | list[torch.Tensor] 或 None | None | 各曲面的积分权重缓存 |
| `_preview_meshes` | list[object] | [] | 各曲面的预览网格缓存 |
| `_surface_node_index` | list[numpy.ndarray] | [] | 曲面节点到 FEA 节点的索引映射 |
| `_surface_node_parameters` | list[numpy.ndarray] | [] | FEA 节点对应的曲面参数坐标 |
| `_iter_since_last_regenerate` | int | 0 | 距离上次重网格的迭代数 |
| `_max_iter_before_regenerate` | int | 15 | 触发重网格的迭代阈值 |
| `_nodes_last_regenerate` | numpy.ndarray 或 None | None | 上次重网格时的节点位置 |
| `_max_nodes_change` | float | 1.0 | 触发重网格的节点变化阈值 |

`BoundaryPart.initialize()` 按 `_surfaces` 的稳定顺序设置每个曲面的运行时参数方向，
然后再建立曲面后端和几何缓存。第一个曲面是参数方向基准，`flip=False`；从第二个
曲面开始统一使用 `flip=True`。`flip` 由 `BoundaryPart.initialize()` 按曲面
序号设置，属于运行时方向状态。

当 `mesh_order == 2` 时，二阶单元的边中点节点映射由已建立的 TorchFEA `Part` 统一持有，
使用其 `mid_pt_idxmap_torch`。该张量的每一行是
`[端点节点索引_1, 端点节点索引_2, 中点节点索引]`，用于在一阶节点移动后更新二阶
中点节点，并保持 `C3D10`、`C3D15`、`C3D20` 等二阶单元的几何一致性。`BoundaryPart`
读取这份唯一映射执行节点回写。

| 曲面在 `_surfaces` 中的索引 | 初始化后的 `flip` | 约定 |
|---:|---:|---|
| `0` | `False` | 保持曲面原始的 `v` 参数方向 |
| `1, 2, ...` | `True` | 将曲面的 `v` 参数方向反向 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `surfaces` | tuple[`BaseSurfaceInterface`, ...] | - | 只读 | 内部维护 | 返回有序曲面定义 |
| `element_name` | str | - | 只读 | 内部维护 | 返回生成的元素名称 |
| `fea_seed_size` | float | - | 只读 | 内部维护 | 返回网格种子尺寸 |
| `mesh_order` | int | - | 只读 | 内部维护 | 返回网格阶数 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `define_surfaces()` | None | - | 用户按顺序注册曲面 |
| `add_surface(surface)` | None | - | 添加一个曲面接口 |
| `get_geometry_values()` | tuple[list[torch.Tensor], list[torch.Tensor], list[torch.Tensor]] | - | 读取按曲面顺序缓存的 `r`、`rdu` 和 `rdu2`，不重新计算 |
| `get_points_weight()` | list[torch.Tensor] | - | 读取按曲面顺序已经建立的控制点权重 |
| `get_control_points_list()` | list[torch.Tensor] | - | 读取已经建立的控制点张量 |
| `export_model(path, format)` | `pathlib.Path` | - | 接收目标地址，调用各曲面导出接口生成当前 `Part` 的 STP 或 STL 文件；格式必须是所有曲面共同支持的格式 |
| `build_part(path_result, pools)` | None | `BasePartDefinition` | 从当前曲面定义创建网格和 TorchFEA `Part`，并写入 `_torchfea_Part` |
| `initialize()` | None | `Initializable` | 按曲面序号设置 `flip`（第 0 个为 `False`，其余为 `True`），再初始化曲面和几何缓存 |
| `reinitialize(iteration)` | None | `Initializable` | 应用变量并准备重网格 |
| `get_parameters()` | list[torch.Tensor] | `BasePartDefinition` | 读取几何参数的 detached clone |
| `set_parameters(parameters)` | None | `BasePartDefinition` | 导入几何参数的 detached clone |
| `build_design_delta()` | None | `Updatable` | 建立并保存全 0 的几何设计增量 |
| `get_design_delta()` | torch.Tensor | `Updatable` | 读取已经建立的几何设计增量 |
| `update_assembly(design_delta)` | None | `Updatable` | 使用自身的 TorchFEA `Part` 引用将试探增量映射到节点并保留计算图 |
| `apply_design_delta(design_delta)` | None | `Updatable` | 通过几何映射正式写回控制点 |
| `build_meshes()` | None | `Visualizable` | 建立并保存各曲面的可视化预览网格缓存 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经由可视化接口建立的预览网格缓存 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_register_surface_sets(part)` | None | 按曲面类型注册 surface set，并按 `exterior_surface` 命名整体外表面集合 |

任务文件定义 `BoundaryPart` 子类并提供 `define_surfaces()` 曲面注册入口，曲面类型使用
BSP、CPGEO、STL 等命名空间访问。等式投影和局部罚函数由绑定的 geometry updater 自己保存
并在 updater 生命周期中应用，`BoundaryPart` 只提供曲面状态、设计变量和几何更新能力。

每个 `BSPSurface` 在 `BoundaryPart` 中按其在 `surfaces` 列表中的索引 `i` 自动注册
四个 surface set：

| 名称 | 内容 |
|---|---|
| `surface_{i}_head` | BSP 顶部端面 |
| `surface_{i}_bottom` | BSP 底部端面 |
| `surface_{i}_lateral` | BSP 侧面 |
| `surface_{i}_all` | 顶面、底面和侧面的合集 |

`i` 使用曲面在 `BoundaryPart.surfaces` 中的稳定顺序，从 `0` 开始。上述名称属于
`Part` 的 surface set 注册表，供 FEA 载荷、边界条件、geometry updater 和 UI 选择使用。
`_register_surface_sets(part)` 在网格生成后完成节点/面集合登记，并将
`surface_{i}_all` 组装为该 BSP 的三个局部面的合集。

每个 `CPGEOSurface` 注册一个 `surface_{i}_all`，其内容是该 CPGEO 曲面的全部
三角面；CPGEO 面集合统一采用这一全集命名。

在上述集合之外，`BoundaryPart` 还注册一个整体 surface set。该集合的名称由
`exterior_surface` 定义，默认名称为 `extern`：

| 名称 | 内容 |
|---|---|
| `exterior_surface` 的值 | 所有曲面的 `surface_0_all + surface_1_all + ...` 合集 |

`BoundaryPart.exterior_surface` 是整体外表面 surface set 的定义名称，默认值为
`extern`。因此，`part.exterior_surface` 对应所有曲面登记的 `surface_{i}_all` 合集，
该集合覆盖所有曲面的全集面。用户输入其他名称时，整体集合就使用该名称创建，
并同步写入 `part.exterior_surface`。该字段直接记录整体集合名称，曲面数据由各曲面集合维护。

#### 5.4.1 `BaseSurfaceInterface`

本节定义可以注册到 `BoundaryPart` 的曲面接口。所有曲面接口只负责几何数据、控制点、
导数、权重和曲面网格；Fairness、曲率和距离等约束由对应的具体几何 updater/evaluator
负责。每个接口及其具体类型单独列为一个小节，专用参数和运行时数据在对应小节中说明。

曲面对象也遵循构造属性和运行时属性的分离。具体曲面类只增加自己的参数字段，
公共缓存由基类维护。

曲面导出候选格式统一定义为 `SurfaceExportFormat = Literal["stp", "stl"]`；每个曲面的实际格式由
`get_export_formats()` 限定。BSP 曲面只提供 STP，CPGEO 曲面和 STL 曲面只提供 STL。

曲面导出是曲面基类的稳定外部接口。最终模型构建阶段直接调用曲面的导出方法，
获得当前曲面对应的 CAD 或三角网格文件；`get_meshes()` 专用于预览数据。

曲面几何值由 `initialize()` 首次建立，由 `update_geometry()` 在控制点或设计增量变化后
更新缓存；`get_geometry_values()` 只读取已经缓存的 `r`、`rdu`、`rdu2` 三个 Tensor，
不执行重新计算。几何设计变量由 `BoundaryPart` 统一收集曲面控制点并向
`DesignRegistry` 注册。`update_geometry()` 写入前应用当前运行时 `flip`，调用方通过
`get_geometry_values()` 直接获得方向一致的结果。

##### 构造属性（`__init__()` 记录）

曲面方向由 `initialize()` 阶段的运行时状态记录。曲面参数、控制点、采样尺寸、几何
阈值和初始化方式由具体曲面类型自己的构造属性记录。

曲面名称由 `BoundaryPart` 根据曲面在 `surfaces` 中的索引统一生成。曲面方程、
控制点、采样尺寸、几何阈值和初始化方式由具体曲面类型自己的构造属性记录。

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | 当前接口不增加构造属性，具体曲面类型在各自小节中声明 |

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_flip` | bool | False | 当前 `v` 参数方向是否反向；由 `BoundaryPart.initialize()` 按曲面序号统一设置 |
| `_surf_node_idx` | `numpy.ndarray` 或 None | None | 曲面节点在 FEA 网格节点中的索引 |
| `_surf_node_uv` | `numpy.ndarray` 或 None | None | FEA 曲面节点对应的参数坐标 |
| `_preview_meshes` | list[object] | [] | 已建立的曲面预览网格缓存 |
| `_initialized` | bool | False | 初始化状态 |

曲面导出能力属于后端运行时状态，通过 `get_export_formats()` 查询。

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| 空 | - | - | - | - | 当前接口不增加 property，具体曲面类型按需声明 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_geometry_values()` | tuple[`torch.Tensor`, `torch.Tensor`, `torch.Tensor`] | - | 读取已经缓存的当前曲面点、一阶导数和二阶导数，不重新计算 |
| `get_points_weight()` | `torch.Tensor` | - | 读取已经建立的采样点积分权重 |
| `get_flip()` | bool | - | 返回当前 `v` 参数方向状态 |
| `get_export_formats()` | tuple[SurfaceExportFormat, ...] | - | 返回当前曲面实际支持的导出格式 |
| `export_surface(path, format)` | `pathlib.Path` | - | 按当前曲面支持的格式导出，并返回实际文件路径 |
| `map(uv)` | `torch.Tensor` | - | 将参数域坐标映射到三维坐标 |
| `compute_normals(uv)` | `torch.Tensor` | - | 根据指定参数点计算法向量 |
| `match_coordinates(node_index, nodes)` | `numpy.ndarray` | - | 建立 FEA 节点到曲面参数域的映射 |
| `get_surface_parameters()` | `torch.Tensor` | - | 读取曲面设计参数 |
| `set_surface_parameters(parameters)` | None | - | 写入曲面设计参数 |
| `update_geometry()` | None | - | 使用当前曲面参数和映射缓存刷新几何值、权重及预览失效状态 |
| `initialize()` | None | `Initializable` | 根据具体曲面属性创建后端对象，并建立初始参数映射与运行时几何缓存 |
| `reinitialize(iteration)` | None | `Initializable` | 更新当前迭代的曲面数据和几何缓存 |
| `build_meshes()` | None | `Visualizable` | 建立并保存曲面预览网格 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的曲面预览网格 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存曲面定义、控制点和映射元数据 |
| `load(folder_path, iteration)` | None | `Persistable` | 恢复指定迭代的曲面状态并重建后端缓存 |

具体曲面的后端对象或固定网格数据由具体类型在构造工厂或 `initialize()` 阶段建立/载入，
`initialize()` 同时准备参数映射缓存、几何值缓存和导出能力；曲面预览通过
`get_meshes()` 获取已经建立的网格，几何值通过 `get_geometry_values()` 读取缓存，
几何变化由 `update_geometry()` 写入缓存，最终曲面文件通过 `export_surface()` 生成。

可视化调用顺序为：公共接口 `build_meshes()` 调用具体曲面的内部辅助函数
`_compute_preview_meshes()`，将 BSP、CPGEO 或 STL 后端数据转换为预览网格列表并写入
基类 `_preview_meshes`；随后由公共接口 `get_meshes()` 读取该缓存。

`flip=True` 表示沿曲面参数域的 `v` 方向反向，所有方向相关导数按参数变换规则同步更新。
对于任意参数导数 `r_{u^a v^b} = ∂^{a+b}r/(∂u^a∂v^b)`，反向规则统一为
`r_{u^a v^b} -> (-1)^b r_{u^a v^b}`。因此 `r_v`、`r_uv` 以及含奇数次 `v`
导数的项取反；`r_vv`、`r_uvv` 以及含偶数次 `v` 导数的项保持原值。当前一、
二阶几何数据中，`r_u` 和 `r_uu` 保持原值，`r_v` 与 `r_uv` 取反，`r_vv` 保持原值。
法向量由变换后的切向导数重新计算，保证法向量与参数导数保持一致。
在当前张量布局中，`rdu[..., 0]` 和 `rdu[..., 1]` 分别表示 `r_u` 和 `r_v`；
`rdu2[..., 0, 1]`、`rdu2[..., 1, 0]` 表示 `r_uv`，`rdu2[..., 1, 1]` 表示
`r_vv`。应用 `flip` 时必须同步变换这些分量。

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_compute_preview_meshes()` | list[object] | 由具体曲面实现后端相关的预览网格转换；公共 `build_meshes()` 保存返回值 |

#### 5.4.2 `CpBasedSurface`

`BSPSurface` 和 `CPGEOSurface` 都使用控制点映射到采样点，因此共享以下运行时
属性。具体曲面的构造属性仍由各自的具体定义类记录。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | 共享状态类不增加构造属性 |

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_control_points` | `torch.Tensor` 或 None | None | 当前控制点张量 |
| `_preload_data` | `PreLoadData` 或 None | None | 参数点到控制点的映射缓存：参数坐标、零/一/二阶权重、控制点索引和面拓扑；供几何值快速求值 |
| `_geometry_values` | tuple[`torch.Tensor`, `torch.Tensor`, `torch.Tensor`] 或 None | None | 已建立的 `r`、`rdu`、`rdu2` 缓存 |
| `_points_weight` | `torch.Tensor` 或 None | None | 已建立的采样点积分权重 |

控制点和 `PreLoadData` 是运行时缓存；曲面通过
`get_control_points_list()`、`get_geometry_values()` 等方法使用这些数据。

`PreLoadData` 是控制点曲面的映射缓存，保存参数映射信息。它包含 `uv`、
`cp_weights`、`cp_weights_du`、`cp_weights_dv`、
`cp_weights_du2`、`cp_weights_dudv`、`cp_weights_dv2`、`indices` 和 `faces`。
这些数据由 `initialize()` 或 `reinitialize()` 建立；`update_geometry()` 使用缓存的
权重/索引更新点坐标和各阶导数，`get_geometry_values()` 只读取更新后的结果。控制点
变化时复用这份参数映射缓存，参数基函数权重在采样网格或后端拓扑变化时重建。
`_surf_node_uv` 专门表示 FEA 网格节点的参数坐标，与 `PreLoadData` 承担不同的数据职责。

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| 空 | - | - | - | - | 共享状态类不增加 property |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `update_backend()` | None | - | 将当前控制点同步到具体曲面后端 |
| `build_preload(points, faces)` | None | - | 建立并保存参数映射权重和索引 |
| `get_preload_data()` | `PreLoadData` | - | 读取已经建立的参数映射缓存 |
| `set_preload_data(preload)` | None | - | 写入外部建立的参数映射缓存 |
| `update_geometry(parameters=None)` | None | `BaseSurfaceInterface` | 根据当前或试探控制点和映射缓存刷新几何值、权重和预览状态 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

#### 5.4.2.1 `PreLoadData`

`PreLoadData` 是冻结拓扑、可迁移设备的参数映射记录。控制点变化复用这份缓存；采样参数域
或拓扑变化时由 `build_preload()` 建立新记录。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_parameters` | torch.Tensor | - | 采样点 `(u, v)` 参数坐标 |
| `_control_point_indices` | torch.Tensor | - | 每个采样点关联的控制点索引 |
| `_position_weights` | torch.Tensor | - | 零阶基函数权重 |
| `_first_derivative_weights` | torch.Tensor | - | `u`、`v` 一阶权重 |
| `_second_derivative_weights` | torch.Tensor | - | `uu`、`uv`、`vv` 二阶权重 |
| `_faces` | torch.Tensor | - | 采样网格三角面连接 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 映射记录仅保存构造状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `parameters` | torch.Tensor | - | 只读 | 内部维护 | 返回参数坐标 |
| `control_point_indices` | torch.Tensor | - | 只读 | 内部维护 | 返回控制点索引 |
| `position_weights` | torch.Tensor | - | 只读 | 内部维护 | 返回零阶权重 |
| `first_derivative_weights` | torch.Tensor | - | 只读 | 内部维护 | 返回一阶权重 |
| `second_derivative_weights` | torch.Tensor | - | 只读 | 内部维护 | 返回二阶权重 |
| `faces` | torch.Tensor | - | 只读 | 内部维护 | 返回采样拓扑 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_num_points()` | int | - | 读取采样点数量 |
| `to_device(device)` | `PreLoadData` | - | 返回所有 Tensor 位于目标设备的新记录 |
| `compute_point_weights(points)` | torch.Tensor | - | 根据采样点和三角拓扑计算积分面积权重 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 映射计算由公开纯计算接口表达 |

#### 5.4.3 `BSPSurface`

`BSPSurface` 是 B-spline 曲面的共同类型，使用控制点和参数域定义连续曲面。
具体几何形状通过专门的定义类记录；例如圆柱使用 `BSPCylinderSurface`。

##### 构造属性（`__init__()` 记录）

`BSPSurface` 继承基类的运行时 `flip`，并使用 `CpBasedSurface` 的控制点和 preload
运行时状态。形状参数放在具体 BSP 定义中；几何导数按基类规定的 `v` 方向规则变换。

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_fairness_evaluator` | `BSPFairnessEvaluator` | 构造函数创建 | 当前 BSP 曲面的 Fairness 评估器 |

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_bsp_model` | object 或 None | None | BSP 后端对象 |
| `_preload_size` | tuple[int, int] 或 None | None | preload UV 网格尺寸 |

BSP 控制点和设计变量数量属于运行时状态；分别通过
`get_control_points_list()` 和 `get_num_variables()` 获取。

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `fairness_evaluator` | `BSPFairnessEvaluator` | - | 只读 | 内部维护 | 返回当前曲面持有的 Fairness evaluator |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_control_points_list()` | list[torch.Tensor] | - | 读取已经建立的 BSP 控制点 |
| `get_num_variables()` | int | - | 读取当前 BSP 设计变量数量 |
| `get_points_weight()` | torch.Tensor | - | 读取已经建立的 BSP 采样点权重 |
| `compute_normals(uv)` | torch.Tensor | - | 根据 BSP 参数点计算法向量 |
| `match_coordinates(node_index, nodes)` | numpy.ndarray | - | 建立 FEA 节点到 BSP 参数域的映射 |
| `update_geometry(parameters=None)` | None | `BaseSurfaceInterface` | 使用当前或试探控制点更新可微几何数据缓存 |
| `update_backend()` | None | `CpBasedSurface` | 将当前控制点同步到 BSP 后端 |
| `get_export_formats()` | tuple[Literal["stp"], ...] | `BaseSurfaceInterface` | 返回 BSP 曲面支持的导出格式；仅为 STP |
| `export_surface(path, format="stp")` | `pathlib.Path` | `BaseSurfaceInterface` | 导出当前 BSP 曲面为 STP |
| `build_meshes()` | None | `Visualizable` | 根据当前控制点建立并保存 BSP 预览网格 |
| `get_meshes()` | list[object] | `Visualizable` | 读取 BSP 当前预览网格缓存 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存 BSP 定义、控制点和映射元数据 |
| `load(folder_path, iteration)` | None | `Persistable` | 恢复 BSP 状态并重建后端缓存 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_compute_preview_meshes()` | list[object] | 根据当前 BSP 控制点生成预览网格列表 |

`BSPSurface` 持有 `BSPFairnessEvaluator`，通过 `fairness_evaluator` property 将评估器提供给
几何罚函数；Fairness 参数和曲率项补偿由评估器维护。
控制点的参数快照、设计增量和正式提交由所属 `BoundaryPart` 统一完成。
具备 CAD 后端时，`BSPSurface.get_export_formats()` 返回 `("stp",)`。

#### 5.4.3.1 `BSPFairnessEvaluator`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_maximum_radius_change` | float | `0.2` | 二阶导数与曲率半径变化阈值 |
| `_maximum_curvature` | float | `1.0` | 主曲率阈值 |
| `_maximum_fairness_factor` | float | `0.2` | Fairness factor 阈值 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_rr_compensation` | torch.Tensor 或 None | None | 基准曲率项补偿系数 |
| `_reference_geometry` | tuple[torch.Tensor, ...] 或 None | None | 初始化时的方向一致几何数据 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `maximum_radius_change` | float | - | 只读 | 内部维护 | 返回半径变化阈值 |
| `maximum_curvature` | float | - | 只读 | 内部维护 | 返回曲率阈值 |
| `maximum_fairness_factor` | float | - | 只读 | 内部维护 | 返回 Fairness factor 阈值 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `compute_fairness(geometry_values, point_weights)` | torch.Tensor | - | 纯计算 BSP 曲面的曲率变化、曲率和 Fairness barrier 标量 |
| `initialize(geometry_values, point_weights)` | None | `Initializable` | 建立参考几何和 `_rr_compensation` |
| `reinitialize(iteration, geometry_values, point_weights)` | None | `Initializable` | 更新依赖采样拓扑的 evaluator 缓存 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_compute_fundamental_forms(geometry_values)` | tuple[torch.Tensor, ...] | 计算第一、第二基本形式 |
| `_compute_principal_curvatures(geometry_values)` | tuple[torch.Tensor, torch.Tensor] | 计算两个主曲率 |
| `_compute_barrier(value, limit)` | torch.Tensor | 计算连续 barrier |

#### 5.4.4 `BSPCylinderSurface`

`BSPCylinderSurface` 对应现有 `initialize_cylinder()` 的构造逻辑。构造函数只记录
圆柱定义；Fairness 参数交给曲面持有的 `BSPFairnessEvaluator`，`initialize()` 再根据
这些定义创建初始控制点、B-spline basis、BSP 后端对象和 preload 数据。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_radius` | float | 构造函数必填 | 圆柱半径，对应现有 `r0` |
| `_length` | float | 构造函数必填 | 圆柱长度 |
| `_seed_size` | float | 构造函数必填 | 初始网格和 preload 尺寸 |
| `_num_u_ratio` | int | 1 | 圆周方向控制点数量比例 |
| `_num_v_ratio` | int | 1 | 轴向控制点数量比例 |
| `_degree` | int | 3 | B-spline 阶数 |
| `_init_location` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 圆柱初始位置 |
| `_perturbation_length` | float 或 None | None | 初始半径扰动周期；None 表示保持基础半径 |

`flip` 只由 `BaseSurfaceInterface` 保存为运行时状态，圆柱定义直接继承该属性。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 运行时后端状态由 `BSPSurface` 统一维护 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `radius` | float | - | 只读 | 内部维护 | 圆柱半径 |
| `length` | float | - | 只读 | 内部维护 | 圆柱长度 |
| `seed_size` | float | - | 只读 | 内部维护 | 初始网格和 preload 尺寸 |
| `num_u_ratio` | int | - | 只读 | 内部维护 | 圆周方向比例 |
| `num_v_ratio` | int | - | 只读 | 内部维护 | 轴向比例 |
| `degree` | int | - | 只读 | 内部维护 | B-spline 阶数 |
| `init_location` | tuple[float, float, float] | - | 只读 | 内部维护 | 初始位置 |
| `perturbation_length` | float 或 None | - | 只读 | 内部维护 | 初始半径扰动周期 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `initialize()` | None | `Initializable` | 依据圆柱参数生成控制点、basis、BSP 模型和 preload 数据 |
| `get_meshes()` | list[object] | `Visualizable` | 读取圆柱 BSP 预览网格缓存 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_create_initial_control_points()` | `torch.Tensor` | 按半径、长度、比例和扰动参数生成控制点 |
| `_create_bsp_model()` | object | 创建圆周方向周期、轴向方向夹持的 B-spline 模型 |

#### 5.4.5 `CPGEOSurface`

`CPGEOSurface` 使用 CPGEO 控制网格和三角形拓扑定义曲面，同样支持形状优化，
但其几何导数、采样点和 Fairness 计算方式独立于 BSP。具体形状通过
`CPGEOCylinderSurface` 或 `CPGEOSphereSurface` 等定义类记录。

##### 构造属性（`__init__()` 记录）

`CPGEOSurface` 继承基类的运行时 `flip`，并使用 `CpBasedSurface` 的控制点和 preload
运行时状态。控制点和三角形拓扑由具体形状定义在 `initialize()` 中生成，几何导数
按基类规定的 `v` 方向规则变换。

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_fairness_evaluator` | `CPGEOFairnessEvaluator` | 构造函数创建 | 当前 CPGEO 曲面的 Fairness 评估器 |

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_cpgeo_model` | object 或 None | None | CPGEO 后端对象 |
| `_knots` | `torch.Tensor` 或 None | None | CPGEO 采样或 knot 点 |
| `_control_faces` | `numpy.ndarray` 或 None | None | 当前控制网格拓扑 |
| `_requires_reconstruction` | bool | True | CPGEO 后端重构待执行状态 |
| `_output_parameter_points` | `numpy.ndarray` 或 None | None | 输出和可视化使用的参数点 |
| `_output_control_faces` | `numpy.ndarray` 或 None | None | 输出和可视化使用的控制面拓扑 |

CPGEO 控制点和控制网格拓扑属于运行时缓存；控制点通过
`get_control_points_list()` 获取，拓扑由 `get_meshes()` 和导出方法消费。

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `fairness_evaluator` | `CPGEOFairnessEvaluator` | - | 只读 | 内部维护 | 返回当前曲面持有的 Fairness evaluator |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_control_points_list()` | list[torch.Tensor] | - | 读取已经建立的 CPGEO 控制点 |
| `get_points_weight()` | torch.Tensor | - | 读取已经建立的 CPGEO 采样点权重 |
| `compute_normals(uv)` | torch.Tensor | - | 根据 CPGEO 参数点计算法向量 |
| `match_coordinates(node_index, nodes)` | numpy.ndarray | - | 建立 FEA 节点到 CPGEO 参数域的映射 |
| `update_geometry(parameters=None)` | None | `BaseSurfaceInterface` | 使用当前或试探控制点更新可微几何数据缓存 |
| `update_backend()` | None | `CpBasedSurface` | 将当前控制点同步到 CPGEO 后端 |
| `get_export_formats()` | tuple[Literal["stl"], ...] | `BaseSurfaceInterface` | 返回 CPGEO 曲面支持的导出格式；仅为 STL |
| `export_surface(path, format="stl")` | `pathlib.Path` | `BaseSurfaceInterface` | 导出当前 CPGEO 曲面为 STL |
| `build_meshes()` | None | `Visualizable` | 根据当前控制点和拓扑建立并保存 CPGEO 预览网格 |
| `get_meshes()` | list[object] | `Visualizable` | 读取 CPGEO 当前预览网格缓存 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存 CPGEO 定义、控制点和拓扑元数据 |
| `load(folder_path, iteration)` | None | `Persistable` | 恢复 CPGEO 状态并重建后端缓存 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_compute_preview_meshes()` | list[object] | 根据当前 CPGEO 控制点和拓扑生成预览网格列表 |

`CPGEOSurface` 持有 `CPGEOFairnessEvaluator`，通过 `fairness_evaluator` property 将评估器
提供给几何罚函数；曲率阈值由评估器维护。
控制点的参数快照、设计增量和正式提交由所属 `BoundaryPart` 统一完成。
具备 CAD 后端时，`CPGEOSurface.get_export_formats()` 返回 `("stl",)`。

#### 5.4.5.1 `CPGEOFairnessEvaluator`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_maximum_curvature` | float | `1.0` | 离散曲率阈值 |
| `_maximum_fairness_factor` | float | `0.2` | 离散 Fairness factor 阈值 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_reference_geometry` | tuple[torch.Tensor, ...] 或 None | None | 初始化时的离散几何数据 |
| `_adjacency` | torch.Tensor 或 None | None | 控制网格邻接关系 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `maximum_curvature` | float | - | 只读 | 内部维护 | 返回曲率阈值 |
| `maximum_fairness_factor` | float | - | 只读 | 内部维护 | 返回 Fairness factor 阈值 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `compute_fairness(geometry_values, point_weights)` | torch.Tensor | - | 纯计算 CPGEO 离散曲率和平滑 barrier 标量 |
| `initialize(geometry_values, point_weights)` | None | `Initializable` | 建立参考几何和控制网格邻接缓存 |
| `reinitialize(iteration, geometry_values, point_weights)` | None | `Initializable` | 在控制拓扑重建后刷新 evaluator 缓存 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_adjacency(faces)` | None | 建立控制点邻接关系 |
| `_compute_discrete_curvature(geometry_values)` | torch.Tensor | 计算控制网格离散曲率 |
| `_compute_barrier(value, limit)` | torch.Tensor | 计算连续 barrier |

#### 5.4.6 `CPGEOCylinderSurface`

`CPGEOCylinderSurface` 对应现有 `CPGEO.initialize_cylinder()` 的构造逻辑。构造函数
记录圆柱网格定义，Fairness 参数由继承的 `CPGEOFairnessEvaluator` 维护，`initialize()`
再生成三角形控制网格并创建 CPGEO 后端对象。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_radius` | float | 构造函数必填 | 圆柱半径，对应现有 `r0` |
| `_length` | float | 构造函数必填 | 圆柱长度 |
| `_seed_size` | float | 构造函数必填 | 圆周和轴向网格尺寸 |
| `_num_u_ratio` | int | 1 | 圆周方向网格数量比例 |
| `_num_v_ratio` | int | 1 | 轴向网格数量比例 |
| `_init_location` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 圆柱初始位置 |
| `_perturbation_length` | float 或 None | None | 初始半径扰动周期；None 表示保持基础半径 |

`flip` 由 `BaseSurfaceInterface` 统一记录；圆柱的参数导数和由其计算出的法向量
均按 `v` 方向反向规则处理，法向量由变换后的导数计算。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 运行时后端状态由 `CPGEOSurface` 统一维护 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `radius` | float | - | 只读 | 内部维护 | 圆柱半径 |
| `length` | float | - | 只读 | 内部维护 | 圆柱长度 |
| `seed_size` | float | - | 只读 | 内部维护 | 初始尺寸 |
| `num_u_ratio` | int | - | 只读 | 内部维护 | 圆周方向比例 |
| `num_v_ratio` | int | - | 只读 | 内部维护 | 轴向比例 |
| `init_location` | tuple[float, float, float] | - | 只读 | 内部维护 | 初始位置 |
| `perturbation_length` | float 或 None | - | 只读 | 内部维护 | 初始半径扰动周期 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `initialize()` | None | `Initializable` | 生成圆柱顶点/三角面并创建 CPGEO 模型 |
| `get_meshes()` | list[object] | `Visualizable` | 读取圆柱 CPGEO 预览网格缓存 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_create_cylinder_mesh()` | tuple[`numpy.ndarray`, `numpy.ndarray`] | 生成圆柱顶点和三角形拓扑 |

#### 5.4.7 `CPGEOSphereSurface`

`CPGEOSphereSurface` 对应现有 `CPGEO.initialize_Sphere()` 的构造逻辑，使用
Fibonacci 分布生成球面点，再由球面三角剖分得到控制面；Fairness 参数由继承的
`CPGEOFairnessEvaluator` 维护。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_radius` | float | 构造函数必填 | 球面半径 |
| `_seed_size` | float | 构造函数必填 | 初始点数量和采样尺寸 |
| `_init_location` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 球面中心位置 |

`flip` 由 `BaseSurfaceInterface` 统一记录为运行时参数方向状态。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 运行时后端状态由 `CPGEOSurface` 统一维护 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `radius` | float | - | 只读 | 内部维护 | 球面半径 |
| `seed_size` | float | - | 只读 | 内部维护 | 初始尺寸 |
| `init_location` | tuple[float, float, float] | - | 只读 | 内部维护 | 球面中心位置 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `initialize()` | None | `Initializable` | 生成球面点、三角拓扑并创建 CPGEO 模型 |
| `get_meshes()` | list[object] | `Visualizable` | 读取球面 CPGEO 预览网格缓存 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_create_sphere_mesh()` | tuple[`numpy.ndarray`, `numpy.ndarray`] | 生成球面顶点和三角形拓扑 |

#### 5.4.8 `STLSurface`

`STLSurface` 从 STL 三角网格读取固定曲面，只参与几何构建、集合注册和可视化。

`STLSurface` 同时支持文件来源和内存来源：文件来源由 `from_stl(path)` 创建，内存来源由
`vertices` 与 `faces` 构造。两种来源统一写入顶点、面连接和预览网格缓存。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_stl_path` | pathlib.Path 或 None | None | STL 文件来源 |
| `_source_vertices` | numpy.ndarray 或 None | None | 内存顶点来源 |
| `_source_faces` | numpy.ndarray 或 None | None | 内存三角面来源 |
| `_scale` | float | 1.0 | 导入缩放比例 |

`flip` 由 `BaseSurfaceInterface` 统一记录为运行时参数方向状态。`STLSurface` 采用
固定三角网格数据，网格方向由 STL 后端规则处理；参数导数接口由控制点曲面类型提供。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_vertices` | `numpy.ndarray` 或 None | None | 导入后的顶点坐标 |
| `_faces` | `numpy.ndarray` 或 None | None | 导入后的三角形拓扑 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `stl_path` | pathlib.Path 或 None | - | 只读 | 内部维护 | 返回 STL 文件来源 |
| `source_vertices` | numpy.ndarray 或 None | - | 只读 | 内部维护 | 返回内存顶点的副本 |
| `source_faces` | numpy.ndarray 或 None | - | 只读 | 内部维护 | 返回内存面连接的副本 |
| `scale` | float | - | 只读 | 内部维护 | 导入缩放比例 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `from_stl(path)` | `STLSurface` | - | 从 STL 文件创建固定曲面定义 |
| `from_mesh(vertices, faces)` | `STLSurface` | - | 从内存三角网格创建固定曲面定义 |
| `get_surface_points()` | `torch.Tensor` | - | 读取已经导入的 STL 顶点或采样点 |
| `get_export_formats()` | tuple[Literal["stl"], ...] | `BaseSurfaceInterface` | 返回 STL 曲面支持的导出格式 |
| `export_surface(path, format="stl")` | `pathlib.Path` | `BaseSurfaceInterface` | 导出当前 STL 三角网格 |
| `initialize()` | None | `Initializable` | 读取 STL 并建立网格缓存 |
| `reinitialize(iteration)` | None | `Initializable` | 刷新当前网格引用 |
| `build_meshes()` | None | `Visualizable` | 根据 STL 顶点和面连接建立并保存预览网格 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的 STL 网格 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存 STL 来源、顶点和面连接 |
| `load(folder_path, iteration)` | None | `Persistable` | 恢复 STL 状态并建立预览缓存 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_compute_preview_meshes()` | list[object] | 根据 STL 顶点和面连接生成预览网格列表 |

`STLSurface` 作为固定网格曲面参与几何构建、集合注册和可视化，并声明
`get_export_formats() == ("stl",)`。Fairness evaluator 由 BSP 和 CPGEO 曲面类型提供，
STL 曲面提供固定几何数据。

#### 5.4.9 曲面导出与最终模型构建

曲面导出接口采用统一签名：

```python
surface.export_surface(path: str | pathlib.Path,
                       format: SurfaceExportFormat | None = None) -> pathlib.Path
```

规则如下：

| 项目 | 约定 |
|---|---|
| `path` | 目标文件路径；父目录由调用方提前准备，返回值为规范化后的实际路径 |
| `format` | 显式指定当前曲面 `get_export_formats()` 返回的格式；`format=None` 时根据 `.stp`、`.step` 或 `.stl` 后缀推断，并校验该格式受当前曲面支持 |
| STP | 仅由 `BSPSurface` 导出当前曲面的 CAD/BREP 表示，用于最终实体或边界模型构建 |
| STL | 由 `CPGEOSurface` 和 `STLSurface` 导出当前曲面的三角网格表示，用于网格交换、快速预览和离散模型构建 |
| 几何状态 | 导出前读取当前控制点、`flip`、约束结果和最新映射缓存 |
| 导出能力 | 由 `get_export_formats()` 返回，UI 根据能力提供格式选项 |

`BSPSurface` 的导出由对应后端适配器完成并生成 STP/CAD-BREP；`CPGEOSurface` 和
`STLSurface` 生成 STL 三角网格。导出适配器沿用曲面的坐标系、方向和单位设置。

`BoundaryPart` 在模型导出前计算所有曲面导出能力的交集。只有目标格式属于该交集时，
`export_model(path, format)` 才能生成完整的 Part 文件；格式不受支持时返回明确的校验错误。
因此，全部由 BSP 曲面组成的 Part 导出 STP；全部由 CPGEO 或 STL 曲面组成的 Part
导出 STL；混合曲面只有在目标格式属于各曲面能力交集时才能导出。

`BoundaryPart.export_model(path, format)` 负责最终模型文件：它按
`BoundaryPart.surfaces` 的稳定顺序调用每个曲面的 `export_surface()`，将曲面文件合并为
指定格式的 Part 模型，并同步使用 `part_name`、`element_names` 和
`exterior_surface` 作为模型元数据。`build_part()` 继续负责 TorchFEA 网格和
集合注册；`export_model()` 负责 CAD/三角网格文件，两条流程共享同一组当前几何状态。

### 5.5 `INPPart`

`INPPart` 继承 `BasePartDefinition`。一个对象从 INP 源 Assembly 中提取一个指定 Part，
保留其 Surface、NodeSet、ElementSet 和选定源实例，并以统一 Part 接口参与目标 Assembly 装配。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_inp_path` | pathlib.Path | 必填 | INP 文件路径 |
| `_source_part_name` | str | 必填 | INP 中的源 Part 名称 |
| `_source_instance_names` | tuple[str, ...] 或 None | None | 需要继承的源实例；None 表示该 Part 的全部源实例 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Assembly` | `torchfea.Assembly` 或 None | None | 从 INP 建立的只读源 Assembly 缓存 |
| `_source_element_types` | tuple[str, ...] | `()` | 按统一顺序排列的源元素类型 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `inp_path` | pathlib.Path | - | 只读 | 内部维护 | 返回 INP 文件路径 |
| `source_part_name` | str | - | 只读 | 内部维护 | 返回源 Part 名称 |
| `source_instance_names` | tuple[str, ...] 或 None | - | 只读 | 内部维护 | 返回源实例选择 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_source_assembly()` | `torchfea.Assembly` | - | 读取已经载入的只读源 Assembly |
| `build_part(path_result, pools)` | None | `BasePartDefinition` | 从源 Assembly 提取、重命名并保存选定 Part 到 `_torchfea_Part` |
| `initialize()` | None | `Initializable` | 载入源 Assembly、解析元素名称映射，并建立选定源实例的 `InstanceDefinition` |
| `build_meshes()` | None | `Visualizable` | 根据选定 Part 和实例建立预览缓存 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的 INP Part 预览 |

#### 内部辅助函数

| 函数 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_load_source_assembly()` | None | - | 使用 TorchFEA INP 读取入口建立源 Assembly 缓存 |
| `_resolve_element_names()` | None | - | 按元素族顺序建立源名称到输出名称的映射 |
| `_build_source_instances()` | None | - | 把选定源实例的平移和旋转转换为实例定义 |

元素类型按 `C3D4`、`C3D6`、`C3D8`、`C3D10`、`C3D15`、`C3D20` 排列，其他类型按源
模型顺序追加。用户提供的 `element_names` 长度等于源元素类型数量，并按该顺序逐项映射；
`element_names=None` 时使用排序后的源元素类型名称。输出 Part 使用继承的 `part_name`，
因此同一 INP 的不同源 Part 可以注册为多个独立 `INPPart`。

### 5.6 `TorchFEAPart`

`TorchFEAPart` 继承 `BasePartDefinition`。一个对象链接一个 TorchFEA 模型文件中的一个源
Part，并缓存完整源 Assembly 以读取该 Part 的实例、Surface、NodeSet、ElementSet 和元素族。
多个对象可以链接同一模型并选择不同源 Part。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_model_directory` | pathlib.Path | 必填 | TorchFEA 模型目录 |
| `_model_filename` | str | 必填 | TorchFEA 模型文件名 |
| `_source_part_name` | str | 必填 | 模型中的源 Part 名称 |
| `_source_instance_names` | tuple[str, ...] 或 None | None | 需要继承的源实例；None 表示该 Part 的全部源实例 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_model_summary` | `TorchFEAModelSummary` 或 None | None | 完整源模型摘要 |
| `_torchfea_Assembly` | `torchfea.Assembly` 或 None | None | 已载入的只读源 Assembly |
| `_source_element_types` | tuple[str, ...] | `()` | 选定源 Part 的有序元素类型 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `model_directory` | pathlib.Path | - | 只读 | 内部维护 | 返回模型目录 |
| `model_filename` | str | - | 只读 | 内部维护 | 返回模型文件名 |
| `source_part_name` | str | - | 只读 | 内部维护 | 返回源 Part 名称 |
| `source_instance_names` | tuple[str, ...] 或 None | - | 只读 | 内部维护 | 返回源实例选择 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_model_summary()` | `TorchFEAModelSummary` | - | 读取已经建立的源模型摘要 |
| `get_source_assembly()` | `torchfea.Assembly` | - | 读取已经载入的只读源 Assembly |
| `build_part(path_result, pools)` | None | `BasePartDefinition` | 从源 Assembly 提取、重命名并保存选定 Part 到 `_torchfea_Part` |
| `initialize()` | None | `Initializable` | 载入模型、建立摘要、解析元素名称映射，并建立选定源实例定义 |
| `build_meshes()` | None | `Visualizable` | 根据选定 Part 和实例建立预览缓存 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的 TorchFEA Part 预览 |

#### 内部辅助函数

| 函数 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_compute_model_path()` | pathlib.Path | - | 组合并规范化模型目录和文件名 |
| `_load_source_assembly()` | None | - | 读取 TorchFEA 模型并保存源 Assembly |
| `_build_model_summary()` | None | - | 从源 Assembly 建立完整结构摘要 |
| `_resolve_element_names()` | None | - | 建立选定源 Part 的元素名称映射 |
| `_build_source_instances()` | None | - | 把选定源实例的变换转换为实例定义 |

源模型摘要为 UI 提供全部 Part、Instance、Surface、NodeSet、ElementSet、ReferencePoint
坐标和元素类型；
`TorchFEAPart` 只把 `source_part_name` 指定的 Part 及其选定实例写入目标 Assembly。一个模型
包含多个 Part 时，UI 根据摘要创建多个 `TorchFEAPart` 定义，用户可以分别设置输出
`part_name`、`element_names` 和实例选择。用户从同一摘要选择需要带入的参考点，UI 将其
名称和坐标创建为独立 `ReferencePoint` 定义；多个 Part 链接共享同名参考点时只注册一次。
目标 Assembly 的材料、载荷、边界、约束和求解器由 MorphOpt Materials/FEA/Solver 流水线建立。

### 5.7 `OffsetShellPart`

`OffsetShellPart` 继承 `BoundaryPart` 的曲面能力，并负责从选定的源曲面向内生成偏置层，
同时生成实体元素和壳元素。实体元素通常使用 `C3D4`，壳元素通常使用 `C3D6`，两者在
`Part.elems` 中使用不同名称。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_solid_element_name` | str | 构造函数必填 | 实体部分的 `Part.elems` 名称，例如 `C3D4` |
| `_shell_element_name` | str | 构造函数必填 | 壳部分的 `Part.elems` 名称，例如 `C3D6` |
| `_source_surface` | list[bool] | 必填 | 按曲面顺序选择偏置源曲面；索引 `0` 固定为 `False` 并保留原始曲面 |
| `_thickness` | float | 必填 | 壳层厚度 |
| `_num_layers` | int | 必填 | 偏置层数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_offset_nodes` | torch.Tensor 或 None | None | 偏置节点缓存 |
| `_offset_elements` | dict[str, object] | `{}` | 实体和壳元素名称到 TorchFEA Element 的缓存 |
| `_offset_surface_sets` | dict[str, object] | `{}` | `surface_{i}_offset` 到面集合的缓存 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `solid_element_name` | str | - | 只读 | 内部维护 | 返回实体元素名称 |
| `shell_element_name` | str | - | 只读 | 内部维护 | 返回壳元素名称 |
| `source_surface` | tuple[bool, ...] | - | 只读 | 内部维护 | 返回按曲面顺序排列的偏置选择；第 `0` 项为 `False` 并对应原始曲面 |
| `thickness` | float | - | 只读 | 内部维护 | 返回壳层厚度 |
| `num_layers` | int | - | 只读 | 内部维护 | 返回偏置层数 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `compute_offset_nodes(source_points, source_normals)` | torch.Tensor | - | 按厚度、层数和向内方向纯计算偏置节点 |
| `build_offset_elements()` | None | - | 根据源面拓扑和偏置层建立实体、壳元素与偏置面集合缓存 |
| `get_offset_nodes()` | torch.Tensor | - | 读取已经建立的偏置节点 |
| `get_offset_elements()` | Mapping[str, object] | - | 读取已经建立的实体和壳元素 |
| `define_surfaces()` | None | `BoundaryPart` | 定义源边界曲面并校验 `source_surface` 长度 |
| `build_part(path_result, pools)` | None | `BasePartDefinition` | 生成实体节点/元素和偏置壳元素，并写入 `_torchfea_Part` |
| `initialize()` | None | `Initializable` | 初始化边界和偏置缓存 |
| `reinitialize(iteration)` | None | `Initializable` | 根据源边界刷新偏置数据 |
| `get_parameters()` | list[torch.Tensor] | `BoundaryPart` | 读取源边界曲面的元曲面控制点参数 detached clone |
| `set_parameters(parameters)` | None | `BoundaryPart` | 写入源边界曲面的元曲面控制点参数 detached clone |
| `build_design_delta()` | None | `Updatable` | 建立并保存源边界曲面控制点的全 0 设计增量 |
| `get_design_delta()` | torch.Tensor | `Updatable` | 读取已经建立的源边界曲面控制点设计增量 |
| `update_assembly(design_delta)` | None | `Updatable` | 使用源曲面控制点增量更新边界和偏置节点、单元及曲面，并保留计算图 |
| `apply_design_delta(design_delta)` | None | `Updatable` | 将源曲面控制点设计增量正式写回并刷新偏置派生数据 |

#### 内部辅助函数

| 函数 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `_build_solid_elements()` | None | - | 建立相邻层之间的实体单元 |
| `_build_shell_elements()` | None | - | 建立最内层壳单元 |
| `_register_offset_sets()` | None | - | 按 `surface_{i}_offset` 写入偏置面集合 |
| `_update_second_order_nodes()` | None | - | 使用 `Part.mid_pt_idxmap_torch` 更新二阶中间节点 |

偏置壳的属性和更新方法集中在 `OffsetShellPart` 中。`BoundaryPart` 保留曲面定义
和边界几何能力。偏置计算只处理 `source_surface[i] is True` 且 `i >= 1` 的曲面，
所有偏置方向统一为向内；每个生成曲面注册为 `surface_{i}_offset`。`OffsetShellPart`
的设计变量仍是源边界曲面的元曲面控制点，偏置节点、单元和偏置曲面由固定算法根据
这些控制点派生。

### 5.8 `ReferencePoint`

`ReferencePoint` 是 Assembly 级几何定义，记录空间坐标并在 `GeometryParams.build_assembly()`
阶段创建对应的 TorchFEA 参考点。集中力、集中力矩、参考点边界条件、耦合和弹簧等 FEA
component 通过名称引用它。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | 构造函数必填 | Assembly 内唯一的参考点名称 |
| `_position` | tuple[float, float, float] | `(0.0, 0.0, 0.0)` | 参考点在全局坐标系中的位置 |

#### 运行时属性（`__init__()` 声明，`build_reference_point()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_ReferencePoint` | `torchfea.ReferencePoint` 或 None | None | 当前 Assembly 中已经建立的 TorchFEA 参考点 |
| `_initialized` | bool | False | 定义校验状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 内部维护 | 返回参考点名称 |
| `position` | tuple[float, float, float] | 只读 | 内部维护 | 返回参考点坐标 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `build_reference_point(assembly)` | None | - | 在指定 Assembly 中创建参考点并写入 `_torchfea_ReferencePoint` |
| `get_reference_point()` | `torchfea.ReferencePoint` | - | 读取已经建立的 TorchFEA 参考点 |
| `initialize()` | None | `Initializable` | 校验名称和坐标维度 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_validate_position()` | None | 校验坐标为三个有限浮点数 |

参考点定义由 `GeometryParams.define_reference_points()` 通过 `add_reference_point()` 注册。
参考点的构建属于 Assembly 构建流程；FEA component 只保存
`reference_point_name`，并在 `reinitialize(iteration, assembly)` 阶段从 Assembly 解析目标。

### 5.9 几何运行服务与摘要

#### 5.9.1 `MeshBuilder`

`MeshBuilder` 集中封装 V3 `MeshGenerator` 的曲面扫描、体构造、Gmsh 剖分、Abaqus surface
集合生成、INP 导出和资源释放。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_minimum_size` | float 或 None | None | Gmsh 全局最小尺寸 |
| `_maximum_size` | float 或 None | None | Gmsh 全局最大尺寸 |
| `_mesh_order` | int | `1` | 网格阶数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_surface_paths` | tuple[pathlib.Path, ...] | `()` | 已扫描曲面文件 |
| `_surface_tags` | tuple[int, ...] | `()` | 已导入 Gmsh 曲面 tag |
| `_volume_tags` | tuple[int, ...] | `()` | 已建立封闭体 tag |
| `_mesh_data` | object 或 None | None | 已建立节点、单元和物理组数据 |
| `_session` | object 或 None | None | Gmsh/CAD 会话句柄 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `minimum_size` | float 或 None | - | 只读 | 内部维护 | 返回最小尺寸 |
| `maximum_size` | float 或 None | - | 只读 | 内部维护 | 返回最大尺寸 |
| `mesh_order` | int | - | 只读 | 内部维护 | 返回网格阶数 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `set_surface_paths(paths)` | None | - | 写入已有曲面输入列表并校验扩展名 |
| `build_volume()` | None | - | 导入曲面、缝合封闭壳并建立体 |
| `build_mesh(dimension=3)` | None | - | 建立指定维度网格、物理组和 surface payload |
| `get_mesh_data()` | object | - | 读取已经建立的网格数据 |
| `export_inp(target_path)` | pathlib.Path | - | 导出 Abaqus INP 并返回实际路径 |
| `finalize()` | None | - | 释放 CAD/Gmsh 会话和临时实体 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_scan_surface_paths()` | None | 稳定排序并校验曲面文件 |
| `_collect_surface_tags()` | None | 收集导入曲面 tag |
| `_build_surface_payload()` | None | 生成 Abaqus surface、node set 和 element set 数据 |
| `_validate_closed_shell()` | None | 校验曲面闭合性和方向一致性 |

`BoundaryPart.build_part()` 使用 `try/finally` 调用 `MeshBuilder.finalize()`；网格阶数为 2 时，
TorchFEA Part 建立 `mid_pt_idxmap_torch` 供后续节点更新。

#### 5.9.2 模型读取与摘要函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `compute_model_path(directory, filename)` | pathlib.Path | 规范化模型目录与文件名，并校验目标位于选定目录 |
| `load_geometry_assembly(model_path)` | `torchfea.Assembly` | 读取 TorchFEA Controller/Assembly 文件并返回只包含持久几何层的深复制 |
| `compute_model_summary(model_path)` | `TorchFEAModelSummary` | 读取模型并生成 Part、Instance、ReferencePoint 和集合摘要 |

读取器保留 Part、Instance、Surface、NodeSet、ElementSet、ReferencePoint、元素对象和变换；
目标几何流水线随后由 Materials、FEA 和 Solver 建立材料、载荷、边界、约束与求解状态。
文件反序列化在 UI 隔离检查进程或任务进程中执行。相同规范化路径、文件尺寸和修改时间
组成读取缓存键，多个 `TorchFEAPart` 可以复用同一源 Assembly 与摘要的只读缓存。

#### 5.9.3 `PartSummary`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | - | Part 名称 |
| `_num_nodes` | int | - | 节点数量 |
| `_element_types` | tuple[str, ...] | - | 稳定排序的元素类型 |
| `_surface_names` | tuple[str, ...] | - | 面集名称 |
| `_node_set_names` | tuple[str, ...] | - | 节点集名称 |
| `_element_set_names` | tuple[str, ...] | - | 单元集名称 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结摘要仅保存构造状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `name`、`num_nodes`、`element_types` | 对应构造类型 | - | 只读 | 内部维护 | 返回 Part 标识、规模和元素族 |
| `surface_names`、`node_set_names`、`element_set_names` | tuple[str, ...] | - | 只读 | 内部维护 | 返回可供材料和 FEA 选择的集合名称 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 摘要通过 property 读取 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结摘要由模型检查器建立 |

#### 5.9.4 `InstanceSummary`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | - | Instance 名称 |
| `_part_name` | str | - | 引用的 Part 名称 |
| `_surface_names` | tuple[str, ...] | - | 实例可见面集 |
| `_node_set_names` | tuple[str, ...] | - | 实例可见节点集 |
| `_element_set_names` | tuple[str, ...] | - | 实例可见单元集 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结摘要仅保存构造状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `name` | str | - | 只读 | 内部维护 | 返回 Instance 名称 |
| `part_name` | str | - | 只读 | 内部维护 | 返回 Part 名称 |
| `surface_names`、`node_set_names`、`element_set_names` | tuple[str, ...] | - | 只读 | 内部维护 | 返回实例集合名称 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 摘要通过 property 读取 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结摘要由模型检查器建立 |

#### 5.9.5 `TorchFEAModelSummary`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_model_path` | pathlib.Path | - | 被检查模型文件 |
| `_parts` | tuple[`PartSummary`, ...] | - | Part 摘要 |
| `_instances` | tuple[`InstanceSummary`, ...] | - | Instance 摘要 |
| `_reference_points` | Mapping[str, tuple[float, float, float]] | `{}` | Assembly 参考点名称到全局坐标的稳定映射 |
| `_schema_version` | str | - | TorchFEA 文件 schema 版本 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结摘要仅保存构造状态 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `model_path` | pathlib.Path | - | 只读 | 内部维护 | 返回模型路径 |
| `parts` | tuple[`PartSummary`, ...] | - | 只读 | 内部维护 | 返回 Part 摘要 |
| `instances` | tuple[`InstanceSummary`, ...] | - | 只读 | 内部维护 | 返回 Instance 摘要 |
| `reference_points` | Mapping[str, tuple[float, float, float]] | - | 只读 | 内部维护 | 返回参考点名称和全局坐标的只读映射 |
| `schema_version` | str | - | 只读 | 内部维护 | 返回模型版本 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `generate_tree()` | Mapping[str, object] | - | 生成包含 Part、Instance、集合和参考点坐标的 UI 只读层级数据 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 层级数据直接由冻结记录生成 |
