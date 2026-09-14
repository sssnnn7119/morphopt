# MorphOpt V4 功能基线与类迁移清单

> 文档属性：维护性迁移文档。本清单用于追踪旧版功能、V4 归属和迁移状态，不定义 V4 公共接口；接口以第 1–17 章主题设计文档为准。

本章以 `src/morphopt3` 的现有实现为功能基线，逐类记录 MorphOpt V4 的职责、接口和迁移动作。
V4 的目标是重组模块边界、统一运行时状态和方法语义；每一项已有用户功能都在本清单中找到
对应的 V4 归属。

核对范围包括 `optcore/modelparams`、`shapeopt/geometryinterfaces`、`shapeopt/geometryparams.py`、
`shapeopt/objectivefuncs`、`simp`、`codesign`、`taskoptmization.py` 以及 `ui/model`、
`ui/schemes`、`ui/codegen`、`ui/widgets` 和 `ui/launcher.py`。

返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文是 V3 到 V4 的功能基线和类迁移清单。它按领域记录旧功能、V4 归属、方法迁移动作、
职责边界和实施顺序，用于确认架构重构后的功能覆盖情况。

### 目录

- [23.1 核对规则](#231-核对规则)
- [23.2 几何系统](#232-几何系统)
- [23.3 材料系统](#233-材料系统)
- [23.4 FEA、目标与求解器](#234-fea目标与求解器)
- [23.5 DesignRegistry、Updater 与运行时](#235-designregistryupdater-与运行时)
- [23.6 UI、Codegen 与 Observer](#236-ui-codegen-与-observer)
- [23.7 V4 实现顺序](#237-v4-实现顺序)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | `src/morphopt3` 功能实现、旧接口、示例/任务文件、V4 主题设计和迁移约束 |
| 输出 | 类职责清单、旧接口到 V4 方法映射、功能覆盖记录、迁移状态和实现顺序 |
| 主要读者 | V4 开发者、功能迁移负责人、测试人员和 review 者 |
| 关联文档 | [架构总览](01-04Overview.md)、[校验与迁移](18-22ValidationMigration.md)、[编码规范](../style.md) |

## 23.1 核对规则

每个类按下列顺序核对：构造输入、构造属性、运行时属性、属性接口、生命周期、数据访问、纯计算、
预览、导出、持久化、设计变量和 UI 绑定。方法表使用以下迁移标记：

| 标记 | 含义 |
|---|---|
| 保留 | 功能和责任在 V4 中继续存在，方法名可以保持 |
| 重命名 | 功能保持，方法名按 `get/build/update/compute/export` 语义调整 |
| 拆分 | 一个旧方法拆成建立状态的方法和读取状态的方法 |
| 合并 | 多个旧入口归入一个唯一事实来源 |
| 新增 | 为完成已有流程的清晰分层而增加显式接口 |

所有预览对象遵循统一契约：`build_meshes()` 建立并写入预览缓存，`get_meshes()` 读取已有缓存。
所有几何值、积分权重、材料场和结果网格都使用同一规则。每个具体曲面类都在自己的类表中声明
`get_meshes()`，并明确其缓存的网格类型。

## 23.2 几何系统

### 23.2.1 `GeometryParams`

旧来源：`shapeopt.geometryparams.GeometryParams`。它负责有序 Part 注册、设计变量聚合、曲面约束、
网格/Assembly 构建、节点映射和几何灵敏度回写。

| 旧接口或能力 | V4 接口 | 迁移动作 | 功能契约 |
|---|---|---|---|
| Part 注册 | `define_parts()`、`add_part()` | 新增 | `GeometryParams` 按 `part_name` 注册多个 Part |
| `define_surfaces()` | `BoundaryPart.define_surfaces()` | 迁移 | 用户按顺序注册一个边界 Part 的曲面 |
| `add_surface()` | `BoundaryPart.add_surface()` | 迁移 | 向边界 Part 的曲面列表添加一个曲面 |
| `initialize()` | `initialize()` | 保留 | 初始化全部 Part、曲面缓存和名称索引 |
| `reinitialize()` | `reinitialize(iteration)` | 保留 | 刷新当前迭代的曲面、网格和映射状态 |
| `get_geometry_values()` | `get_geometry_values()` | 保留 | 读取各 Part 已缓存的 `r`、`rdu`、`rdu2` |
| `get_control_points_list()` | `get_control_points_list()` | 保留 | 读取曲面控制点快照 |
| `get_points_weight()` | `get_points_weight()` | 保留 | 读取按曲面排列的权重列表 |
| `get_penalty_fairness()` | 对应 geometry updater 的 Fairness 回调 → `surface.get_fairness_evaluator().evaluate()` | 拆分 | updater 绑定曲面并借用其 evaluator 计算 Fairness 约束值 |
| `get_parameters()` / `set_parameters()` | 同名 | 保留 | 读取和写入全部几何设计参数 |
| `get_variables()` | `get_design_values()` | 重命名 | 读取当前设计变量向量 |
| `update_variables()` | `update_design_values()` | 重命名 | 更新曲面控制点并刷新约束状态 |
| `apply_surface_constraints()` | `BoundaryPartUpdater`/`OffsetShellPartUpdater` 的 `_equality_constraint` + `_apply_equality_constraint()` | 拆分 | 将 v3 的 owner 生命周期钩子迁移为具体 geometry updater 持有并应用的唯一等式/投影约束；V4 owner 接口集中提供曲面状态、设计变量和几何更新能力 |
| `generate()` | `build_assembly()` | 重命名 | 生成型 Part 建立网格、集合和 Assembly；INPPart/TorchFEAPart 复用自身缓存的不可变 Assembly |
| 无统一旧入口 | `build_meshes()` | 新增 | 通过 `Visualizable` 建立全部 Part 的预览网格缓存 |
| `get_meshes()` | `get_meshes()` | 保留 | 读取全部 Part 的预览网格缓存 |
| `plot()` | `plot()` | 保留 | 将已缓存网格加入 PyVista 画布 |
| `obtain_design_sensitivity_vars()` | `compute_design_sensitivity_variables()` | 重命名 | 从当前 Assembly 计算几何灵敏度变量 |
| `modify_assembly()` | `update_sensitivity_assembly()` | 重命名 | 将灵敏度变量写回已有 Assembly 节点 |
| `save()` / `load()` | 同名 | 保留 | 保存和恢复几何设计、曲面映射和迭代状态 |
| `_regenerate()` | `MeshBuilder.build_part()` | 迁移 | 网格生成、INP 读取、集合注册和节点匹配归入网格构建后端 |
| `_export_data()` | `export_surfaces(directory)` | 重命名 | 按曲面能力导出 STP 或 STL 文件 |

必须显式记录的运行时状态：`_geometry_values`、`_points_weight`、`_preview_meshes`、
`_surface_node_index`、`_surface_node_parameters`、`_iter_since_last_regenerate`、
`_max_iter_before_regenerate`、`_nodes_last_regenerate` 和 `_max_nodes_change`。这些状态
支撑只读读取、重网格判据和灵敏度回写。二阶单元的边中点映射使用 TorchFEA `Part` 的
`mid_pt_idxmap_torch` 作为唯一来源，`BoundaryPart` 不再维护重复副本。

### 23.2.2 `ReferencePoint`

参考点属于几何层的 Assembly 定义，由 `GeometryParams` 注册并在 Assembly 构建阶段创建。
FEA component 通过参考点名称使用它。

| 旧方法或能力 | V4 方法 | 迁移动作 | 功能契约 |
|---|---|---|---|
| 参考点注册 | `define_reference_points()`、`add_reference_point()` | 新增 | 在 GeometryParams 中按名称注册 Assembly 级参考点 |
| 参考点建立 | `build_reference_point(assembly)` | 迁移 | 在指定 Assembly 中建立并保存 TorchFEA 参考点 |
| 参考点读取 | `get_fea_reference_point()` | 重命名 | `get_reference_point()` 读取已经建立的 TorchFEA 参考点 |
| 参考点校验 | `_validate_position()` | 迁移 | 校验名称唯一性和三维坐标 |

### 23.2.3 `MeshBuilder`

旧来源：`shapeopt.geometryparams.MeshGenerator`。该类保持外部网格后端的独立性，
`BoundaryPart` 只调用它构建 Part。

| 旧方法 | V4 方法 | 迁移动作 | 功能 |
|---|---|---|---|
| `scan_directory()` | `scan_sources()` | 重命名 | 扫描曲面文件和面标签 |
| `load_and_process_files()` | `load_sources()` | 重命名 | 读取并整理 CAD/网格源数据 |
| `construct_volume()` | `build_volume()` | 重命名 | 根据曲面构造体域 |
| `generate_mesh()` | `build_mesh()` | 重命名 | 按网格尺寸生成体网格 |
| `_generate_abaqus_surface_payload()` | `_build_surface_payload()` | 重命名 | 生成面集合和节点集合数据 |
| `export()` | `export_mesh(path)` | 重命名 | 将网格写入 INP 或中间文件 |
| `finalize()` | `close()` | 重命名 | 释放 CAD/网格后端资源 |
| `run()` | `build_part()` | 重命名 | 完成源扫描、体构造、网格导出和 Part 装载 |

### 23.2.4 `BasePartDefinition` 与 `InstanceDefinition`

| 类 | V4 外部接口 | 功能 |
|---|---|---|
| `BasePartDefinition` | `initialize()`、`build_part()`、`get_part()`、`get_meshes()`、`get_parameters()`、`set_parameters()`、`save()`、`load()` | 维护生成型 Part 的名称、元素名称、外表面、Instance 定义、TorchFEA Part 和预览缓存 |
| `InstanceDefinition` | `validate()`、`build_instance(part)`、`get_instance()` | 维护 Instance 名称、平移、旋转和 Assembly 运行时实例 |
| `GeometryParams` | `build_assembly()`、`get_assembly()` | 将多个 Part 和 Instance 装配到同一个 Assembly |

`BasePartDefinition.build_part()` 建立并保存生成型 TorchFEA `Part`；
`GeometryParams.build_assembly()` 负责装配生成型 Part 和 Instance。`INPPart` 与
`TorchFEAPart` 直接使用 `build_assembly()` 建立不可变 Assembly，并由
`get_assembly()` 读取缓存。

运行时后端对象由创建者持有，字段分别为
`_torchfea_Part`、`_torchfea_Instance`、
`_torchfea_Assembly` 和 `_torchfea_ReferencePoint`；几何更新接口只接收
设计增量，直接操作这些已缓存对象。

### 23.2.5 `BoundaryPart`

旧来源：`shapeopt.geometryparams.GeometryParams` 中的可变形边界流程。

| 能力 | V4 方法 | 功能契约 |
|---|---|---|
| 曲面注册 | `define_surfaces()`、`add_surface()` | 保存稳定曲面顺序，顺序决定 `flip` |
| 初始化 | `initialize()` | 设置方向、建立映射缓存、几何值缓存、权重和预览网格 |
| 迭代刷新 | `reinitialize(iteration)` | 按重网格判据更新曲面、网格和节点参数映射 |
| 几何读取 | `get_geometry_values()`、`get_control_points_list()`、`get_points_weight()` | 读取已缓存的集合级几何数据 |
| 约束执行 | `BoundaryPartUpdater._apply_equality_constraint()`、`OffsetShellPartUpdater._apply_equality_constraint()` | 执行对应 geometry updater 持有的唯一等式/投影约束并写回绑定几何对象 |
| 网格 | `build_part(path_result, pools)`、`get_part()` | 生成节点、单元、面集、节点集和元素集 |
| 节点映射 | `match_surface_nodes(part)` | 调用各曲面的 `match_coordinates()`，保存节点到参数域的映射 |
| 设计变量 | `build_design_delta()`、`get_design_delta()`、`update_assembly(design_delta)`、`apply_design_delta()` | 使用对象自身的 TorchFEA 引用支持试探更新和正式提交 |
| 预览 | `get_meshes()` | 读取各曲面的预览网格 |
| 导出 | `export_model(path, format)` | 按所有曲面的共同格式导出 Part |
| 灵敏度 | `compute_design_sensitivity_variables()`、`update_sensitivity_assembly()` | 保存几何设计变量和 FEA 节点回写关系 |

曲面集合注册、外表面合并和重网格状态归属 `BoundaryPart` 或 `MeshBuilder`；二阶单元
中间节点映射归属 TorchFEA `Part`，载荷层只读取生成后的集合和模型状态。

### 23.2.6 导入 Part

| 类/服务 | V4 方法 | 功能 |
|---|---|---|
| `INPPart` | `resolve_source()`、`build_assembly()`、`get_assembly()`、`initialize()`、`get_meshes()` | 读取 INP、选择源 Part、按统一元素类型顺序解析 `element_names`，直接建立并缓存不可变 `Assembly`，生成固定预览 |
| `TorchFEAPart` | `resolve_model_path()`、`inspect_model()`、`build_assembly()`、`get_assembly()`、`initialize()`、`get_meshes()` | 扫描模型目录，按统一元素类型顺序解析 `element_names`，提取多个 Part、Instance、surface/node/element set 和元素类型，直接建立并缓存不可变 `Assembly` |
| `TorchFEAModelSummary` | `part_for_instance()` | 为 UI 和 FEA 目标选择提供摘要查询 |
| 模型导入服务 | `load_geometry_assembly()` | 反序列化所有 Part/Instance，补充 `extern` 集合并建立干净 Assembly |

导入模型中的 Part、Instance、surface set、node set 和 element set 都作为后续材料、载荷、边界和
目标定义的可选项。导入流程从用户配置读取外表面名称，集合名称不依赖固定字符串。

### 23.2.7 曲面接口功能基线

| 类 | 必须提供或重写的方法 | 运行时缓存 |
|---|---|---|
| `BaseSurfaceInterface` | `map()`、`compute_normals()`、`initialize()`、`reinitialize()`、`get_geometry_values()`、`get_surface_parameters()`、`set_surface_parameters()`、`update_variables()`、`get_points_weight()`、`match_coordinates()`、`build_meshes()`、`get_meshes()`、`get_export_formats()`、`export_surface()`、`save()`、`load()` | 节点索引、节点参数、几何值、权重和预览网格 |
| `CpBasedSurface` | `synchronize()`、`build_preload()`、`get_preload_data()`、`apply_preload_data()`、`get_r()`、`get_rdu()`、`get_rdu2()`、`get_fairness_evaluator()`、`update_geometry()` | 控制点、参数映射权重、索引、面拓扑、`r/rdu/rdu2` 和 Fairness evaluator |
| `BSPSurface` | `map()`、`compute_normals()`、`initialize()`、`build_preload()`、`synchronize()`、`match_coordinates()`、`build_meshes()`、`get_meshes()`、`export_surface()` | BSP 后端、UV 映射、预览网格；导出格式为 STP |
| `CPGEOSurface` | `map()`、`compute_normals()`、`initialize()`、`reinitialize()`、`build_preload()`、`synchronize()`、`match_coordinates()`、`build_meshes()`、`get_meshes()`、`export_surface()` | CPGEO 后端、knot/拓扑、重构状态、预览网格；导出格式为 STL |
| `STLSurface` | `initialize()`、`reinitialize()`、`get_surface_points()`、`build_meshes()`、`get_meshes()`、`export_surface()` | STL 顶点、面连接和预览网格；导出格式为 STL |

`BSPSurface.get_meshes()` 读取 BSP 预览缓存，`CPGEOSurface.get_meshes()` 读取 CPGEO knot/拓扑
预览缓存，`STLSurface.get_meshes()` 读取 STL 三角网格缓存。具体曲面的小节必须保留这三项声明。

曲面几何值通过 `build_preload()` 和 `update_geometry()` 建立、更新缓存；
`get_geometry_values()`、`get_points_weight()` 和 `get_meshes()` 只读取对应缓存。
Fairness 计算由每个可更新曲面持有的 evaluator 执行，几何罚函数通过
`get_fairness_evaluator()` 借用 evaluator，并向其提供几何数据。

### 23.2.8 `OffsetShellPart`

旧来源：`codesign.geometry.CodesignGeometry`。V4 继续支持多层向内偏置节点、实体/壳单元、
二阶中间节点和偏置面集合；偏置曲面由 `source_surface` 布尔列表选择。

| 旧能力 | V4 方法 | 功能 |
|---|---|---|
| 偏置节点计算 | `compute_offset_nodes()` | 根据选定曲面的曲面法向、厚度和层数计算向内偏置节点；曲面索引从 `1` 开始 |
| 偏置单元 | `build_offset_elements()` | 建立 `C3D6/C3D15` 等实体或壳单元 |
| 集合注册 | `register_offset_sets()` | 按 `surface_{i}_offset` 注册选定曲面的偏置集合和实体/壳元素集合 |
| 初始构建 | `build_part()` | 生成实体、壳和边界 Part |
| 迭代刷新 | `reinitialize()` | 更新偏置节点、单元和预览缓存 |
| 设计更新 | `update_assembly()`、`apply_design_delta()` | 使用源边界曲面的元曲面控制点增量，并将变化传播到偏置网格 |
| 灵敏度回写 | `update_sensitivity_assembly()` | 更新偏置网格节点及二阶中间节点 |
| 预览 | `get_meshes()` | 读取边界和偏置壳预览网格 |

## 23.3 材料系统

本节的类顺序和注册式定义与[材料系统](06Materials.md)一致：
[`MaterialsParams`](06Materials.md#61-materialsparams) →
[`MaterialModels`](06Materials.md#62-materialmodels) →
[`MaterialParameters`](06Materials.md#63-materialparameters) →
[`BaseMaterialInterface`](06Materials.md#64-basematerialinterface) →
[`HomogeneousMaterial`](06Materials.md#65-homogeneousmaterial) →
[`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial)。材料对象始终携带
`part_name` 和 `element_name`；材料定义通过 `define_materials()` 建立注册表，单项通过
`add_material(interface, name)` 注册，运行时通过 `reinitialize(iteration, assembly)` 解析目标。

### 23.3.1 `MaterialsParams`

| 旧能力 | V4 方法 | 迁移动作 |
|---|---|---|
| `define_interface()` | `define_materials()` | 重命名 |
| `add_material_interface()` | `add_material(interface, name)` | 重命名，材料对象自身携带 `part_name` 和 `element_name` |
| `interfaces()` | `get_interfaces()` | 重命名 |
| `design_interfaces()` | `get_design_interfaces()` | 重命名 |
| `set_materials(fe)` | `assign_materials()` | 重命名，使用材料对象自身的 TorchFEA 引用将全部材料写入当前 `Assembly` |
| `initialize(geometry)` | `initialize()` + `reinitialize(iteration, assembly)` | 将材料解析拆分为静态结构初始化和当前 Assembly 的迭代刷新 |
| `get_parameters()` / `set_parameters()` | 同名 | 保留 |
| `get_design_values()` | `get_design_values()` | 保留 |
| `get_variables()` | `get_design_values()` | 合并为设计变量读取入口 |
| `update_variables()` | `apply_design_delta()` | 重命名，将材料设计增量正式写回材料接口 |
| `obtain_design_sensitivity_vars()` | `compute_design_sensitivity_variables()` | 重命名 |
| `modify_assembly()` | `update_sensitivity_assembly()` | 重命名 |
| `get_meshes()` | `get_meshes()` | 保留，读取材料场缓存 |
| `plot()` | `plot()` | 保留 |
| `save()` / `load()` | 同名 | 保留 |
| 旧材料绑定记录 | `BaseMaterialInterface.name`、`BaseMaterialInterface.part_name`、`BaseMaterialInterface.element_name` | 将材料名称和目标记录合并到材料对象 |

`Params` 包含 `GeometryParams`、`MaterialsParams` 和 `FEAParams` 三个子参数处理器。
`GeometryParams` 生成几何 Assembly，`MaterialsParams` 写入材料，`FEAParams` 创建 FEA
component 并写入同一个 Assembly；`Params` 统一调度这条处理流水线。`Controller` 将
`Params` 完成的 Assembly 交给 Solver，Solver 在 Assembly 上创建静力求解上下文。
`MaterialsParams` 是材料对象注册表和设计变量聚合器；每个材料对象自身保存材料名称、目标
`Part` 名称、元素类型名称和材料接口。实际元素解析发生在
`reinitialize(iteration, assembly)`，元素对象来源于当前 Assembly。
每个 `BaseMaterialInterface` 同时缓存 `_torchfea_Assembly` 和按实际本构类命名的
`_torchfea_<MaterialClass>`；`MaterialModels.create_material()` 负责创建对象，材料接口负责持有、分配和更新对象。
材料集合的 `get_parameters()`、`set_parameters()`、`build_design_delta()`、
`get_design_delta()`、`update_assembly()` 和 `apply_design_delta()` 来自 `Updatable`，
`MaterialsParams` 通过材料名称将这些协议方法转发到具体材料接口。

### 23.3.2 材料参数和材料接口

| 类 | V4 方法 | 功能 |
|---|---|---|
| [`MaterialModels`](06Materials.md#62-materialmodels) | 参数类命名空间、`create_material(parameters)` | 根据参数对象创建 TorchFEA 本构对象 |
| `MaterialParameters` | 参数 property、`material_class` | 保存本构定义；运行时本构对象由材料接口持有 |
| [`BaseMaterialInterface`](06Materials.md#64-basematerialinterface) | `initialize()`、`reinitialize(iteration, assembly)`、`build_material()`、`get_material()`、`assign_material()`、`get_design_values()`、`build_meshes()`、`get_meshes()`、`save()`、`load()` | 以 `name`、`part_name` 和 `element_name` 解析目标元素、按具体本构类建立 `_torchfea_<MaterialClass>`、写入 FEA 和提供预览 |
| [`HomogeneousMaterial`](06Materials.md#65-homogeneousmaterial) | 继承 `BaseMaterialInterface` | 将固定本构写入目标元素 |
| [`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial) | `get_control_points_list()`、`compute_material_ratio()`、`compute_penalty_factor()`、`get_parameters()`、`set_parameters()`、`build_design_delta()`、`get_design_delta()`、`update_assembly()`、`apply_design_delta()` | 保留 BSP 设计场、SIMP 惩罚、材料比例、元素写回、灵敏度和材料场预览 |

SIMP 专用运行时状态包括 `_control_points`、`_bsp_size`、`_element_map`、`_simp_field`、
`_material_penalty`、`_void_penalty_factor` 和 `_use_simp_penalty`。材料场预览由
`build_meshes()` 写入缓存，`get_meshes()` 读取缓存。

SIMP 元素模型 `Fgrad`、`Fskew`、`HuHu_LuLu` 以及 `C3D4/C3D10/C3D8/C3D20` 适配器作为
材料扩展协议保留，并在材料模型注册表中登记。

## 23.4 FEA、目标与求解器

本节的 FEA 类顺序和注册式定义与[FEA 组件](07Fea.md)一致：
[`FEAParams`](07Fea.md#71-feaparams) →
[`BaseFEAComponent`](07Fea.md#72-basefeacomponent) → FEA component 子类 →
[`LoadStep`](07Fea.md#715-loadstep)。Solver 的独立接口见 [08Solver.md](08Solver.md)。组件定义通过 `define_components()` /
`define_steps()` 建立注册表，单项分别通过 `add_component()` / `set_step_*()` 加入；
所有 component 在 `reinitialize(iteration, assembly)` 中解析当前运行时目标。

### 23.4.1 FEA component

`BaseFEAComponent` 的统一方法为：

| 方法 | 功能 |
|---|---|
| `build_fea()` | 建立并保存 `_torchfea_<ConcreteName>` 对应的 TorchFEA component |
| `get_fea_object()` | 读取已建立的 component |
| `update_fea(values)` | 更新当前工况值 |
| `initialize()` | 建立 FEA component 的静态运行结构 |
| `reinitialize(iteration, assembly)` | 解析当前 Assembly 的 Instance、surface、node set、element set 和 RP |
| `get_parameters()` / `set_parameters()` | 读取和写入可更新值 |
| `update_assembly(design_delta)` | 使用自身缓存的 TorchFEA component 和 Assembly 引用执行试探更新 |
| `get_meshes()` | 读取载荷、边界和接触的预览对象 |
| `save()` / `load()` | 保存和恢复组件状态 |

以下具体组件全部保留。每个类实现自己的目标属性、`num_values` 和内部对象构建辅助方法，
公共生命周期、构建、更新、预览和持久化接口由 `BaseFEAComponent` 提供：

[`Pressure`](07Fea.md#73-pressure)、
[`BodyForce`](07Fea.md#74-bodyforce)、
[`ConcentratedForce`](07Fea.md#75-concentratedforce)、
[`ConcentratedMoment`](07Fea.md#76-concentratedmoment)、
[`BoundaryCondition`](07Fea.md#77-boundarycondition)、
[`BoundaryConditionRP`](07Fea.md#78-boundaryconditionrp)、
[`Couple`](07Fea.md#79-couple)、
[`SpringToGround`](07Fea.md#710-springtoground)、
[`SpringBetweenRPs`](07Fea.md#711-springbetweenrps)、
[`PenaltyDoF`](07Fea.md#712-penaltydof)、
[`Contact`](07Fea.md#713-contact) 和
[`SelfContact`](07Fea.md#714-selfcontact)。

组件参数原样保留：压力面、体力元素、力/力矩参考点、边界 DOF、耦合目标、弹簧刚度和长度、
惩罚目标与系数、接触阈值以及接触起止参数。参考点、集中力和集中力矩的目标名称在初始化阶段
统一校验，刚度目标要求力、力矩和参考点属于同一参考点定义。
每个 FEA component 持有对应的 TorchFEA 对象字段：
`_torchfea_Pressure`、`_torchfea_BodyForce`、
`_torchfea_ConcentratedForce`、`_torchfea_ConcentratedMoment`、
`_torchfea_BoundaryCondition`、`_torchfea_BoundaryConditionRP`、
`_torchfea_Couple`、`_torchfea_SpringToGround`、
`_torchfea_SpringBetweenRPs`、`_torchfea_PenaltyDoF`、
`_torchfea_Contact` 和 `_torchfea_SelfContact`。
每个 component 同时缓存当前 `_torchfea_Assembly`；完成 `reinitialize(iteration, assembly)` 后，
`build_fea()`、`update_fea()` 和 `update_assembly(design_delta)` 均直接使用这些自身引用。

### 23.4.2 `FEAParams`、`LoadStep`

| 旧方法/能力 | V4 方法 | 功能 |
|---|---|---|
| `define_interface()` | `define_components()` | 用户注册 FEA component |
| `add_fea_interface()` | `add_component()` | 注册唯一名称的组件并保留最终名称 |
| `set_step_num()` | `set_num_steps()` | 创建工况行 |
| `set_step_params()` | `set_step_values()` | 设置工况组件值 |
| `create_fea()` | `build_components()` | 建立并保存各 FEA component 的 TorchFEA 对象 |
| - | `assign_components(assembly)` | 将已建立的 FEA component 写入当前 Assembly |
| `process_fea()` | `update_fea()` | 将当前工况值写入已有 FEA 对象 |
| `FEAParams.initialize(geometry)` | `FEAParams.initialize()` + `FEAParams.reinitialize(iteration, assembly)` | 将 FEA 解析拆分为静态结构初始化和当前 Assembly 的迭代刷新 |
| `num_load_steps` | `get_num_load_steps()` | 读取工况数量 |
| `get_parameters()` / `set_parameters()` | 同名 | 读取和写入工况设计值 |
| `get_meshes()` | 同名 | 读取全部 FEA component 预览 |
| `add_instance_from_inp()` | `INPPart` / `TorchFEAPart` | 模型导入归入几何系统 |
| `LoadStep.get_resolved_values()` | 同名 | 读取已校验的 Tensor 值向量 |

### 23.4.3 `Solver`

| 旧能力 | V4 方法 | 功能 |
|---|---|---|
| 静力求解器配置 | `build_solver()` / `get_solver()` | 创建并读取 `StaticImplicitSolver` |
| `solve()` | `solve(assembly)` | 接收当前 Assembly，求解全部工况并写入 `_results` |
| 求解结果返回值 | `get_results()` | 读取按 `step_index` 排序的结果 |
| `_solve_FEA()` | `_solve_task()` | worker 内部求解函数 |
| task 分组 | `get_task_index_list()` | 读取工况到 worker 的分组 |
| GPU 解析 | `get_available_gpus()` | 读取设备列表 |
| SIMP 的上一轮 GC 初值缓存 | `set_reuse_previous_solution()`、`get_reuse_previous_solution()`、`_previous_gc` | 合并到 Solver；当无几何设计变量时自动复用上一轮 GC |

### 23.4.4 `ObjectiveFunction`

| 旧方法 | V4 方法 | 功能 |
|---|---|---|
| `objective_function()` | `compute_objective()` | 计算当前标量目标 |
| `compute_multistep_objective()` | 同名 | 计算并聚合多工况目标 |
| `sensitivity_analysis()` | `compute_sensitivity()` | 计算并切分设计变量灵敏度 |
| `set_step()` | `update_step(step_index)` | 通过 ObjectiveFunction 持有的 Assembly 上下文更新对应工况的 work condition |
| `get_metrics(case_index)` | 同名 | 读取指定结果工况的已计算指标 |
| `get_fe_results(case_index)` | 同名 | 读取指定结果工况的 FEA 结果 |
| `get_mesh_case(case_index)` | `build_mesh_case(case_index)` + `get_mesh_case(case_index)` | 建立并读取指定结果工况的网格缓存 |
| `num_tasks` | `get_num_tasks()` | 读取任务数量 |
| `__getitem__()` | `get_task()` | 按名称或索引读取目标任务 |
| `plot()` | `plot_case()` | 绘制已建立的结果对象 |
| `save()` | `build_result_artifacts()`、`export_result_meshes()`、`save()` | 将网格、图片和记录分阶段建立、导出和保存 |

`ObjectiveFunction` 负责顶层目标、指标、Jacobian、结果工况读取、结果网格生成和全局灵敏度。
`ShapeDerivative` 与 `Sensitivity` 的 v3 职责统一迁移为各 updater 的
`LocalSensitivityObjective`，由局部灵敏度在 `reinitialize()` 中自动建立；`Fairness`、
`Distance`、`MinRadius`、`Cylinder`、`VolumeMaximization`、`VolFrac`、
`MinValue`、`MaxValue` 和 `VolFrac` 作为 `MaterialUpdater` 的局部约束注册，
`DensityFieldMinimize` 作为该 updater 的附加正则项注册。
Fairness 计算由曲面提供的 `BSPFairnessEvaluator` 或 `CPGEOFairnessEvaluator` 承担。

## 23.5 DesignRegistry、Updater 与运行时

### 23.5.1 `DesignRegistry`

| 能力 | V4 方法 | 功能 |
|---|---|---|
| 注册变量块 | `add_block()` | 注册一个 owner 的变量范围 |
| 冻结顺序 | `finalize()` | 按 geometry → material → load 和名称顺序确定 offsets |
| 读取完整变量 | `get_values()` | 读取已注册的完整设计向量 |
| 切分变量 | `split(values)` | 按 `DesignKey` 返回变量块 |
| 试探变量 | `build_trial_values()`、`get_trial_values()` | 建立和读取试探变量 |
| 试探回写 | `update_trial_values(full_values)` | 将试探值分发到各 owner；owner 使用自身缓存的 TorchFEA 引用完成更新 |
| 正式提交 | `apply_values()` | 将已验证的变化提交到 owner |

### 23.5.2 `BaseUpdater`、具体 Updater 与 `Updaters`

| 类 | 必须保留的方法 |
|---|---|
| `BaseUpdater` | `initialize()`、`reinitialize()`、`closure()`、`update()`、`get_change()`、`get_local_objective()`、`save()`、`load()`；维护 owner、变量块、固定 `LocalSensitivityObjective` 和优化器公共生命周期 |
| `BaseGeometryUpdater` | `get_owner()`、`initialize()`、`reinitialize()`、`closure()`、`update()`、`get_change()`；提供几何 updater 公共生命周期 |
| `BoundaryPartUpdater` | `set_equality_constraint()`、`get_equality_constraint()`、`add_constraint()`、`get_constraints()`、`get_local_objective()`、`initialize()`、`reinitialize()`、`closure()`、`update()`、`get_change()`；接收 BoundaryPart 局部灵敏度并建立固定线性目标，同时更新曲面控制点及本 updater 的 Fairness、Distance、MinRadius、Cylinder 和 VolumeMaximization 约束 |
| `OffsetShellPartUpdater` | `set_equality_constraint()`、`get_equality_constraint()`、`add_constraint()`、`get_constraints()`、`get_local_objective()`、`initialize()`、`reinitialize()`、`closure()`、`update()`、`get_change()`；接收源边界曲面局部灵敏度并建立固定线性目标，优化元曲面控制点并刷新偏置节点及本 updater 的 Fairness、InwardCurvatureRadius 和 OffsetSurfaceMinThickness 约束 |
| `MaterialUpdater` | `add_constraint()`、`get_constraints()`、`add_regularization()`、`get_regularization_terms()`、`get_local_objective()`、`initialize()`、`reinitialize()`、`closure()`、`update()`、`get_change()`；接收材料局部灵敏度并建立固定线性目标，管理本 updater 的 MinValue、MaxValue、VolFrac 约束、DensityFieldMinimize 正则项和 SIMP 步长设置 |
| `FEAUpdater` | `add_constraint()`、`get_constraints()`、`get_local_objective()`、`get_fea_component()`、`initialize()`、`reinitialize()`、`closure()`、`update()`、`get_change()`；接收 FEA component 局部灵敏度并建立固定线性目标，管理本 updater 的载荷局部约束 |
| `UpdaterEntry` | `name`、`target_kind`、`target_name`、`updater`、`validate()`；校验一个 owner 只能绑定一个 updater |
| `Updaters` | `define_updaters()`、`add_updater()`、`initialize()`、`reinitialize()`、`update()`、`get_changes()`、`save()`、`load()` |

优化器、LBFGS、回溯线搜索、步长缩放和收敛判断作为 `BaseUpdater` 的内部策略注册，
保留 `max_step_iter`、`max_step_length`、梯度缩放和线搜索配置。
v3 中 updater 的 `add_objective_function(ShapeDerivative/Sensitivity)` 迁移为
`LocalSensitivityObjective` 的固定生命周期：`ObjectiveFunction` 计算全局灵敏度，
`DesignRegistry` 切分变量块，updater 在 `reinitialize()` 中建立局部线性展开。
v3 的 `add_constraints()` 迁移为具体 updater 的 `add_constraint()`，只写入当前 updater
的局部约束注册表；v3 的 `apply_surface_constraints()` 迁移为几何 updater 自己的
`_equality_constraint` 和 `_apply_equality_constraint()`，约束逻辑直接保留在对应 updater 内部。

### 23.5.3 `Params`、`Controller`、`History` 与任务进程

| 类 | V4 责任和方法 |
|---|---|
| `Params` | `initialize()`、`reinitialize()`、`build_assembly()`、`get_assembly()`、`compute_design_sensitivity_variables()`、`update_sensitivity_assembly()`、`get_meshes()`、`save()`、`load()` |
| `Controller` | `initialize()`（一次性运行时初始化）、`initialize_path()`、`get_assembly()`、`start_optimization()`、`restart_optimization()`、`step()`（单次外层迭代）、`request_stop()`、`save()`、`load()`；内部 `_opt_loop()`、`_clear_cache()`、`_record_step()`、`_should_stop()`、设备迁移和 worker 管理 |
| `History` | `add_record()`、`get_records()`、`get_series(name)`、`get_result_paths()`、`save()`、`load()`；保留 objective、time、元素数、节点数、变形和 metrics 序列 |
| `TaskOptimization` | 创建任务进程、设置环境、加载任务脚本、启动/重启 Controller、转发结果目录和结束状态 |
| `OptimizationWorker` | 在子进程中执行 Controller，并将 stdout/stderr、异常和结果路径发送到 UI |

## 23.6 UI、Codegen 与 Observer

### 23.6.1 UI 数据模型

`ProblemDefinition`、`GeometryNode`、`PartNode`、`InstanceNode`、`MaterialNode`、`FEANode`、
`FEAComponentNode`、`LoadStepsNode`、`ObjectiveNode`、`UpdaterNode` 和 `SolverNode` 继续作为
定义层对象。每个节点统一提供 `build_definition()` 和 `get_definition()`，并将表单字段映射到
对应的 V4 定义对象。

| UI 能力 | 归属 |
|---|---|
| Part/Instance/曲面增删、复制、重命名 | `ProblemDefinition`、`GeometryNode`、`PartNode` |
| 模型目录扫描和集合选择 | `TorchFEAPart`、`TorchFEAModelSummary`、模型编辑器 |
| 载荷接口和工况级联更新 | `FEANode`、`FEAComponentNode`、`LoadStepsNode` |
| 删除接口后的工况/Jacobian 引用清理 | `ProblemDefinition` 校验与级联更新 |
| 材料元素族选择 | `MaterialNode` 从真实 `Part.elems` 读取 |
| 顶层目标代码槽 | `ObjectiveNode` |
| 几何等式约束和局部罚函数约束代码槽 | `UpdaterNode` |
| `.morph` 序列化 | `save_morph()`、`load_morph()` |
| 双语 UI、英文代码槽和模板参数对话框 | i18n、Codegen 和 snippet 系统 |

### 23.6.2 Codegen 与模板

| 类/函数 | V4 方法 | 功能 |
|---|---|---|
| `CodeGenerator` | `generate_source(problem)`、`generate_python(problem)` | 生成可执行任务源码 |
| `SchemeTemplate` | `build_root()`、`get_root()` | 建立并读取默认问题树 |
| `PartTemplate` | `create_part(data)` | 创建 Part 编辑节点 |
| `MaterialTemplate` | `build_material(data)`、`get_material()` | 建立并读取材料节点 |
| `UpdaterTemplate` | `create_updater(data)` | 创建 updater 节点 |
| `CodeSnippet` | `render(parameters)` | 渲染 instance、参考点、节点位移、参与力、应变能和变形梯度模板 |

生成顺序保持：Geometry → Materials → FEA components → Load steps → Objective → Solver →
Updaters → Controller。生成代码使用 V4 的 `build_*`、`get_*`、`update_*` 接口。

### 23.6.3 Launcher 与 Observer

| 类 | 必须保留的功能 |
|---|---|
| `Launcher` | 直接运行当前定义、运行生成 Python、从结果目录重启、设置工作目录和环境变量、终止进程组 |
| `OutputRedirector` | 捕获 stdout/stderr，清理 ANSI 控制符和不可见字符，将日志写入 UI 输出框 |
| `Observer` | 读取 History、指标、迭代结果、deformation STL 和结果目录变化 |
| `ResultViewer` | 加载并显示变形网格、结果曲面和观察数据 |

## 23.7 V4 实现顺序

1. 先实现 `BaseSurfaceInterface`、`CpBasedSurface`、BSP/CPGEO/STL 的映射缓存和独立
   `get_meshes()`，建立曲面单元测试。
2. 实现 `MeshBuilder`、`BoundaryPart`、导入 Part 和多 Part/Instance Assembly，验证集合、节点
   匹配和二阶节点映射。
3. 实现材料接口、SIMP 设计场、材料模型注册和材料灵敏度回写。
4. 实现 Geometry 的 `ReferencePoint`，再实现 FEA component、LoadStep、`FEAParams` 和 Solver。
5. 实现 Objective、Fairness evaluator、DesignRegistry 和 Updater，接通试探更新与正式提交。
6. 实现 Params、Controller、TaskOptimization、History 和结果导出。
7. 最后迁移 UI 数据模型、Codegen、Launcher、Observer 和现有任务脚本。

每个阶段都先完成对应类的“构造属性 → 运行时属性 → property → 外部接口 → 内部辅助函数”
表格，再实现代码和 `tests/morphopt/` 中一一对应的单元测试。
