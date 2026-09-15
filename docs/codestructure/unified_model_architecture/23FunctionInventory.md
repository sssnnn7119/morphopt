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
| `get_geometry_values()` | `BoundaryPart.get_geometry_values()` | 迁移 | 从具体边界 Part 读取已缓存的 `r`、`rdu`、`rdu2` |
| `get_control_points_list()` | `BoundaryPart.get_control_points_list()` | 迁移 | 从具体边界 Part 读取曲面控制点快照 |
| `get_points_weight()` | `BoundaryPart.get_points_weight()` | 迁移 | 从具体边界 Part 读取按曲面排列的积分权重 |
| `get_penalty_fairness()` | `surface.fairness_evaluator.compute_fairness(...)` | 拆分 | 具体 geometry updater 借用目标曲面的 evaluator 计算 Fairness 约束值 |
| `get_parameters()` / `set_parameters()` | `BoundaryPart.get_parameters()` / `BoundaryPart.set_parameters()` | 迁移 | 由具体可更新 Part 维护自己的设计参数 |
| `get_variables()` | `BoundaryPart.get_parameters()` | 合并 | 当前值由 owner 读取；全局设计增量由 `DesignRegistry.get_design_delta()` 读取 |
| `update_variables()` | `BoundaryPart.update_assembly()` / `BoundaryPart.apply_design_delta()` | 拆分 | 分别完成保留计算图的试探更新和通过校验后的正式提交 |
| `apply_surface_constraints()` | `BoundaryPartUpdater` / `OffsetShellPartUpdater` 的 `_apply_equality_constraint()` | 迁移 | 等式投影接收 owner 和试探参数，返回投影后的新 Tensor，再由 registry 统一提交 |
| `generate()` | `build_assembly()` | 重命名 | GeometryParams 统一装配生成型和导入型 Part、集合、实例与参考点 |
| 无统一旧入口 | `build_meshes()` | 新增 | 通过 `Visualizable` 建立全部 Part 的预览网格缓存 |
| `get_meshes()` | `get_meshes()` | 保留 | 读取全部 Part 的预览网格缓存 |
| `plot()` | `plot()` | 保留 | 将已缓存网格加入 PyVista 画布 |
| `save()` / `load()` | 同名 | 保留 | 保存和恢复几何设计、曲面映射和迭代状态 |
| 设计 owner 收集 | `get_design_owners()` | 新增 | 按稳定 Part 顺序向 `DesignRegistry` 提供可更新 owner |
| `_regenerate()` | `BoundaryPart.build_part()` + `MeshBuilder` | 拆分 | Part 调度导出、剖分、INP 读取、集合注册和节点匹配；`MeshBuilder` 执行网格后端步骤 |
| `_export_data()` | `export_surfaces(directory)` | 重命名 | 按曲面能力导出 STP 或 STL 文件 |

几何管理器记录 Part、Instance 和参考点注册表；具体 `BoundaryPart` 记录 `_geometry_values`、
`_points_weight`、`_preview_meshes`、`_surface_node_index`、`_surface_node_parameters`、
`_iter_since_last_regenerate`、`_nodes_last_regenerate` 等运行时状态。这些状态支撑只读读取、
重网格判据和可微节点回写。二阶单元的边中点映射使用 TorchFEA `Part` 的
`mid_pt_idxmap_torch` 作为唯一来源，`BoundaryPart` 不再维护重复副本。

### 23.2.2 `ReferencePoint`

参考点属于几何层的 Assembly 定义，由 `GeometryParams` 注册并在 Assembly 构建阶段创建。
FEA component 通过参考点名称使用它。

| 旧方法或能力 | V4 方法 | 迁移动作 | 功能契约 |
|---|---|---|---|
| 参考点注册 | `define_reference_points()`、`add_reference_point()` | 新增 | 在 GeometryParams 中按名称注册 Assembly 级参考点 |
| 参考点建立 | `build_reference_point(assembly)` | 迁移 | 在指定 Assembly 中建立并保存 TorchFEA 参考点 |
| 参考点读取 | `get_fea_reference_point()` | `get_reference_point()` | 重命名并读取已经建立的 TorchFEA 参考点 |
| 参考点校验 | `_validate_position()` | 迁移 | 校验名称唯一性和三维坐标 |

### 23.2.3 `MeshBuilder`

旧来源：`shapeopt.geometryparams.MeshGenerator`。该类保持外部网格后端的独立性，
`BoundaryPart` 只调用它构建 Part。

| 旧方法 | V4 方法 | 迁移动作 | 功能 |
|---|---|---|---|
| `scan_directory()` | `set_surface_paths(paths)` + `_scan_surface_paths()` | 拆分 | 写入、排序并校验曲面文件 |
| `load_and_process_files()` | `build_volume()` | 合并 | 导入曲面、缝合封闭壳并建立体 |
| `construct_volume()` | `build_volume()` | 重命名 | 根据曲面构造体域 |
| `generate_mesh()` | `build_mesh()` | 重命名 | 按网格尺寸生成体网格 |
| `_generate_abaqus_surface_payload()` | `_build_surface_payload()` | 重命名 | 生成面集合和节点集合数据 |
| `export()` | `export_inp(target_path)` | 重命名 | 将已经建立的网格写入 Abaqus INP |
| `finalize()` | `finalize()` | 保留 | 释放 CAD/Gmsh 会话和临时实体 |
| `run()` | `BoundaryPart.build_part()` | 迁移 | Part 编排曲面导出、`build_volume()`、`build_mesh()`、`export_inp()` 和 Part 装载 |

### 23.2.4 `BasePartDefinition` 与 `InstanceDefinition`

| 类 | V4 外部接口 | 功能 |
|---|---|---|
| `BasePartDefinition` | `initialize()`、`build_part()`、`get_part()`、`build_meshes()`、`get_meshes()`、`save()`、`load()` | 维护 Part 名称、元素名称、外表面、Instance 定义、TorchFEA Part 和预览缓存 |
| `InstanceDefinition` | `validate()`、`build_instance(part)`、`get_instance()` | 维护 Instance 名称、平移、旋转和 Assembly 运行时实例 |
| `GeometryParams` | `build_assembly()`、`get_assembly()` | 将多个 Part 和 Instance 装配到同一个 Assembly |

可更新 Part 在 `BasePartDefinition` 的契约基础上实现 `Updatable`。
`BasePartDefinition.build_part()` 建立并保存 TorchFEA `Part`；
`GeometryParams.build_assembly()` 负责装配全部 Part 和 Instance。`INPPart` 与
`TorchFEAPart` 缓存只读源 Assembly，从中提取一个选定 Part，并通过相同的
`build_part()` / `get_part()` 接口参加装配。

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
| 可微回写 | `update_assembly(design_delta)` | 将试探控制点映射为当前 Assembly 节点并保留自动微分图 |

曲面集合注册、外表面合并和重网格状态归属 `BoundaryPart` 或 `MeshBuilder`；二阶单元
中间节点映射归属 TorchFEA `Part`，载荷层只读取生成后的集合和模型状态。

### 23.2.6 导入 Part

| 类/服务 | V4 方法 | 功能 |
|---|---|---|
| `INPPart` | `initialize()`、`get_source_assembly()`、`build_part()`、`get_part()`、`build_meshes()`、`get_meshes()` | 读取 INP 源 Assembly，选择一个源 Part，按统一元素类型顺序解析 `element_names`，提取集合和实例并生成固定预览 |
| `TorchFEAPart` | `initialize()`、`get_model_summary()`、`get_source_assembly()`、`build_part()`、`get_part()`、`build_meshes()`、`get_meshes()` | 扫描模型目录，选择一个源 Part，解析 `element_names`，提取集合和选定实例；多个定义可链接同一模型的不同 Part |
| `TorchFEAModelSummary` | `generate_tree()` | 为 UI 树、材料目标和 FEA 目标选择器生成只读层级摘要 |

导入模型中的 Part、Instance、surface set、node set 和 element set 都作为后续材料、载荷、边界和
目标定义的可选项。每个导入定义以唯一输出 `part_name` 注册；多个 Part 由多个定义对象组合。
导入流程从用户配置读取外表面名称和集合名称。

### 23.2.7 曲面接口功能基线

| 类 | 必须提供或重写的方法 | 运行时缓存 |
|---|---|---|
| `BaseSurfaceInterface` | `initialize()`、`reinitialize()`、`update_geometry()`、`get_geometry_values()`、`get_surface_parameters()`、`set_surface_parameters()`、`get_points_weight()`、`match_coordinates()`、`build_meshes()`、`get_meshes()`、`get_export_formats()`、`export_surface()`、`save()`、`load()` | 节点索引、节点参数、几何值、权重、方向状态和预览网格 |
| `CpBasedSurface` | `build_preload()`、`get_preload_data()`、`set_preload_data()`、`get_control_points_list()`、`update_backend()` | 控制点、参数映射权重、索引、面拓扑和 `r/rdu/rdu2` |
| `BSPSurface` | `map()`、`compute_normals()`、`initialize()`、`build_preload()`、`update_backend()`、`match_coordinates()`、`build_meshes()`、`get_meshes()`、`export_surface()` | BSP 后端、UV 映射、预览网格；导出格式为 STP |
| `CPGEOSurface` | `map()`、`compute_normals()`、`initialize()`、`reinitialize()`、`build_preload()`、`update_backend()`、`match_coordinates()`、`build_meshes()`、`get_meshes()`、`export_surface()` | CPGEO 后端、knot/拓扑、重构状态、预览网格；导出格式为 STL |
| `STLSurface` | `initialize()`、`reinitialize()`、`get_surface_points()`、`build_meshes()`、`get_meshes()`、`export_surface()` | STL 顶点、面连接和预览网格；导出格式为 STL |

`BSPSurface.get_meshes()` 读取 BSP 预览缓存，`CPGEOSurface.get_meshes()` 读取 CPGEO knot/拓扑
预览缓存，`STLSurface.get_meshes()` 读取 STL 三角网格缓存。具体曲面的小节必须保留这三项声明。

曲面几何值通过 `build_preload()` 和 `update_geometry()` 建立、更新缓存；
`get_geometry_values()`、`get_points_weight()` 和 `get_meshes()` 只读取对应缓存。
Fairness 计算由每个可更新曲面持有的 evaluator 执行，几何罚函数通过
`fairness_evaluator` property 借用 evaluator，并向其提供几何数据。

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
| 可微回写 | `update_assembly(design_delta)` | 更新偏置网格节点及二阶中间节点，并保留源控制点到节点的自动微分图 |
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
| 设计材料查询 | `get_design_owners()` | 新增，按稳定材料顺序向 `DesignRegistry` 提供 `SIMPFieldMaterial` owner |
| `get_meshes()` | `get_meshes()` | 保留，读取材料场缓存 |
| `plot()` | `plot()` | 保留 |
| `save()` / `load()` | 同名 | 保留 |
| 旧材料绑定记录 | `BaseMaterialInterface.name`、`BaseMaterialInterface.part_name`、`BaseMaterialInterface.element_name` | 将材料名称和目标记录合并到材料对象 |

`Params` 包含 `GeometryParams`、`MaterialsParams` 和 `FEAParams` 三个子参数处理器。
`GeometryParams` 生成几何 Assembly，`MaterialsParams` 写入材料，`FEAParams` 创建 FEA
component 并写入同一个 Assembly；`Params` 统一调度这条处理流水线。`Controller` 将
`Params` 完成的 Assembly 交给 Solver，Solver 在 Assembly 上创建静力求解上下文。
`MaterialsParams` 是材料对象注册表和分配处理器；每个材料对象自身保存材料名称、目标
`Part` 名称、元素类型名称和材料接口。实际元素解析发生在
`reinitialize(iteration, assembly)`，元素对象来源于当前 Assembly。
每个 `BaseMaterialInterface` 同时缓存 `_torchfea_Assembly` 和按实际本构类命名的
`_torchfea_<MaterialClass>`；`MaterialModels.create_material()` 负责创建对象，材料接口负责持有、分配和更新对象。
固定材料实现材料分配和预览契约；`SIMPFieldMaterial` 额外实现 `Updatable` 的
`get_parameters()`、`set_parameters()`、`build_design_delta()`、`get_design_delta()`、
`update_assembly()` 和 `apply_design_delta()`。`DesignRegistry` 直接注册这些具体 owner。

### 23.3.2 材料参数和材料接口

| 类 | V4 方法 | 功能 |
|---|---|---|
| [`MaterialModels`](06Materials.md#62-materialmodels) | 参数类命名空间、`create_material(parameters)` | 根据参数对象创建 TorchFEA 本构对象 |
| `MaterialParameters` | 参数 property、`material_class` | 保存本构定义；运行时本构对象由材料接口持有 |
| [`BaseMaterialInterface`](06Materials.md#64-basematerialinterface) | `initialize()`、`reinitialize(iteration, assembly)`、`build_material()`、`get_material()`、`assign_material()`、`build_meshes()`、`get_meshes()`、`save()`、`load()` | 以 `name`、`part_name` 和 `element_name` 解析目标元素、按具体本构类建立 `_torchfea_<MaterialClass>`、写入 FEA 和提供预览 |
| [`HomogeneousMaterial`](06Materials.md#65-homogeneousmaterial) | 继承 `BaseMaterialInterface` | 将固定本构写入目标元素 |
| [`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial) | `get_control_points_list()`、`compute_material_ratio()`、`compute_penalty_factor()`、`get_parameters()`、`set_parameters()`、`build_design_delta()`、`get_design_delta()`、`update_assembly()`、`apply_design_delta()` | 保留 BSP 设计场、SIMP 惩罚、材料比例、元素写回、灵敏度和材料场预览 |

SIMP 专用运行时状态包括 `_control_points`、`_bsp_size`、`_element_map`、`_simp_field`、
`_material_penalty`、`_void_penalty_factor` 和 `_use_simp_penalty`。材料场预览由
`build_meshes()` 写入缓存，`get_meshes()` 读取缓存。

`SIMPScaledMaterial` 负责连续材料缩放；`SIMPElementPenalty` 通过 `f_grad`、`f_skew`、
`huhu_lulu` 三种模式覆盖 V3 的低层惩罚路径；`SIMPElementC3D4`、`SIMPElementC3D8`、
`SIMPElementC3D10`、`SIMPElementC3D20` 保留各单元族调用签名。`compute_ramp_interpolation()`
和 `compute_power_interpolation()` 是无状态纯函数，并由材料模型注册表按配置选用。

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
| `assign_fea()` | 按 component 类型将对象挂接到 Assembly 的 load、boundary 或 constraint 注册表 |
| `update_fea(values)` | 更新当前工况值 |
| `initialize()` | 建立 FEA component 的静态运行结构 |
| `reinitialize(iteration, assembly)` | 解析当前 Assembly 的 Instance、surface、node set、element set 和 RP |
| `default_values` property | 读取和写入组件的默认工况值 |
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
`build_fea()` 和 `update_fea(values)` 直接使用这些自身引用。逐工况可更新值由
`LoadValueBlock` 实现 `Updatable`，组件定义和工况设计变量保持唯一所有权。

### 23.4.2 `FEAParams`、`LoadStep`

| 旧方法/能力 | V4 方法 | 功能 |
|---|---|---|
| `define_interface()` | `define_components()` | 用户注册 FEA component |
| `add_fea_interface()` | `add_component()` | 注册唯一名称的组件并保留最终名称 |
| `set_step_num()` | `set_num_steps()` | 创建工况行 |
| `set_step_params()` | `set_step_values()` | 设置工况组件值 |
| `create_fea()` | `build_components()` | 建立并保存各 FEA component 的 TorchFEA 对象 |
| - | `assign_components()` | 使用已绑定的当前 Assembly 将全部 FEA component 写入模型 |
| `process_fea()` | `update_fea()` | 将当前工况值写入已有 FEA 对象 |
| 单一可变 FEA 模型逐工况求解 | `build_case_assemblies()` / `get_case_assemblies()` | 基于共享几何/材料状态建立逐工况 Assembly 和 component 运行副本 |
| `FEAParams.initialize(geometry)` | `FEAParams.initialize()` + `FEAParams.reinitialize(iteration, assembly)` | 将 FEA 解析拆分为静态结构初始化和当前 Assembly 的迭代刷新 |
| `num_load_steps` | `get_num_load_steps()` | 读取工况数量 |
| 工况设计变量 | `get_design_owners()` | 为每个可更新的“组件 × 工况”返回唯一 `LoadValueBlock` |
| `get_meshes()` | 同名 | 读取全部 FEA component 预览 |
| `add_instance_from_inp()` | `INPPart` / `TorchFEAPart` | 模型导入归入几何系统 |
| `LoadStep.get_resolved_values()` | 同名 | 读取已校验的 Tensor 值向量 |

`LoadValueBlock` 的 `DesignKey` 包含 component 名称和 `case_index`；它从 `LoadStep` 读取基准值，
绑定所属工况的独立 component，通过 `update_fea(values)` 完成试探更新，并在正式提交后只更新
对应工况行。共享几何/材料先写入基础 Assembly，逐工况副本随后建立，各 load block 最后写入
自己的工况副本。

### 23.4.3 `Solver`

| 旧能力 | V4 方法 | 功能 |
|---|---|---|
| 静力求解器配置 | `build_solvers(fea_controllers)` / `get_solver(case_index)` | 为逐工况 `FEAController` 创建、挂接并读取 `StaticImplicitSolver` |
| `solve()` | `solve(fea_controllers, jacobian_names, initial_gc_by_case)` | 接收逐工况 `FEAController`，完成静力平衡和请求的载荷 Jacobian，并写入 `_results` |
| 求解结果返回值 | `get_results()` | 读取按 `step_index` 排序的结果 |
| `_solve_FEA()` | `_solve_task()` | worker 内部求解函数 |
| task 分组 | `get_task_groups()` | 读取工况到 worker 的稳定分组 |
| GPU 解析 | `get_devices()` | 读取已经解析的 worker 设备列表 |
| SIMP 的上一轮 GC 初值缓存 | `set_reuse_previous_solution()`、`reuse_previous_solution`、`_previous_gc_by_case` | 合并到 Solver；Controller 根据几何 owner 数量设置复用开关 |

### 23.4.4 `ObjectiveFunction`

| 旧方法 | V4 方法 | 功能 |
|---|---|---|
| `objective_function()` | `compute_case_objective(case_index, assembly, result)` | 将单工况目标明确为显式上下文的纯计算扩展点 |
| `compute_multistep_objective()` | `compute_multistep_objective(case_objectives)` | 纯计算并聚合多工况目标 |
| `sensitivity_analysis()` | `SensitivityAnalyzer.build_sensitivities()` / `get_sensitivities()` | 使用隐式/伴随方程建立并读取设计变量总灵敏度 |
| `get_metrics(case_index)` | 同名 | 读取指定结果工况的已计算指标 |
| `get_fe_results(case_index)` | 同名 | 读取指定结果工况的 FEA 结果 |
| `get_mesh_case(case_index)` | `build_mesh_case(case_index)` + `get_mesh_case(case_index)` | 建立并读取指定结果工况的网格缓存 |
| `num_tasks` | `get_num_cases()` | 读取已经完成评估的工况数量 |
| `__getitem__()` | `get_fe_results(case_index)` / `get_case_objective(case_index)` | 按明确结果类型读取指定工况数据 |
| `plot()` | `build_mesh_case(case_index)` + `get_mesh_case(case_index)` | 建立结果网格并交由 Viewer 绘制 |
| `save()` | `save(folder_path, iteration)` + `export_case_result(target_path, case_index)` | 保存目标和指标状态，并导出原生模型、原生结果、Jacobian、变形 STL、预览 PNG 与 manifest |

`ObjectiveFunction` 负责顶层目标、指标、Jacobian 请求、结果工况读取和结果网格生成；
`SensitivityAnalyzer` 负责跨工况静力平衡的隐式/伴随总灵敏度，并按 `DesignKey` 保存结果。
`ShapeDerivative` 与 `Sensitivity` 的 V3 职责统一迁移为各 updater 的
`LocalSensitivityObjective`，由局部灵敏度在 `reinitialize()` 中自动建立；`Fairness`、
`Distance`、`MinRadius`、`Cylinder` 和 `VolumeMaximization` 归属 `BoundaryPartUpdater`；
`InwardCurvatureRadius` 和 `OffsetSurfaceMinThickness` 归属 `OffsetShellPartUpdater`；
`MinValue`、`MaxValue` 和 `VolFrac` 归属 `MaterialUpdater`，`DensityFieldMinimize` 作为
该 updater 的附加正则项。
Fairness 计算由曲面提供的 `BSPFairnessEvaluator` 或 `CPGEOFairnessEvaluator` 承担。

## 23.5 DesignRegistry、Updater 与运行时

### 23.5.1 `DesignRegistry`

| 能力 | V4 方法 | 功能 |
|---|---|---|
| 注册变量块 | `add_block()` | 注册一个 owner 的变量范围 |
| 冻结顺序 | `finalize()` | 按 geometry → material → load 和名称顺序确定 offsets |
| 建立完整设计增量 | `build_design_delta()` | 聚合各 owner 已建立的局部增量并保存全局向量 |
| 读取完整设计增量 | `get_design_delta()` | 读取已经建立的全局设计增量 |
| 读取变量块 | `get_blocks()`、`get_block_range(key)`、`get_owner(key)` | 按 `DesignKey` 读取稳定切片和 owner |
| 试探回写 | `update_assembly(design_delta, categories)` | 按 geometry/material 与 load 两阶段将增量切片分发到已绑定 owner，并保留计算图 |
| 正式提交 | `apply_design_delta(design_delta)` | 在事务边界内校验并正式提交各 owner 的变化 |

### 23.5.2 `BaseUpdater`、具体 Updater 与 `Updaters`

| 类 | 必须保留的方法 |
|---|---|
| `BaseUpdater` | `initialize()`、`reinitialize()`、`compute_terms()`、`closure()`、`update()`、`get_change()`、`get_local_objective()`、`save()`、`load()`；维护 owner、变量块、固定 `LocalSensitivityObjective` 和优化器公共生命周期 |
| `BaseGeometryUpdater` | `initialize()`、`reinitialize()`、`compute_terms()`、`closure()`、`update()`、`get_change()`；提供几何 updater 公共生命周期 |
| `BoundaryPartUpdater` | `set_equality_constraint()`、`get_equality_constraint()`、`add_constraint()`、`constraints`、`initialize()`、`reinitialize()`、`compute_terms()`、`closure()`、`update()`、`get_change()`；接收 `BoundaryPart` 局部灵敏度并建立固定线性目标，同时管理 Fairness、Distance、MinRadius、Cylinder 和 VolumeMaximization 约束 |
| `OffsetShellPartUpdater` | `set_equality_constraint()`、`get_equality_constraint()`、`add_constraint()`、`constraints`、`initialize()`、`reinitialize()`、`compute_terms()`、`closure()`、`update()`、`get_change()`；接收源边界曲面局部灵敏度并建立固定线性目标，同时管理 Fairness、InwardCurvatureRadius 和 OffsetSurfaceMinThickness 约束 |
| `MaterialUpdater` | `add_constraint()`、`constraints`、`add_regularization()`、`regularization_terms`、`initialize()`、`reinitialize()`、`compute_terms()`、`closure()`、`update()`、`get_change()`；接收材料局部灵敏度并建立固定线性目标，管理 MinValue、MaxValue、VolFrac、DensityFieldMinimize 和 SIMP 步长设置 |
| `FEAUpdater` | `add_constraint()`、`constraints`、`initialize()`、`reinitialize()`、`compute_terms()`、`closure()`、`update()`、`get_change()`；绑定一个 `LoadValueBlock`，接收对应工况载荷灵敏度并管理该变量块的局部约束 |
| `UpdaterEntry` | `name`、`target_kind`、`target_name`、`updater`、`validate()`；校验一个 owner 只能绑定一个 updater |
| `Updaters` | `define_updaters()`、`add_updater()`、`initialize()`、`reinitialize()`、`update()`、`get_changes()`、`save()`、`load()` |

`BaseOptimizer`、`LBFGSOptimizer`、`BacktrackingLineSearch` 和 `OptimizerResult` 构成独立优化器协议；
`BaseUpdater` 组合优化器，并保留 `max_step_iter`、`max_step_length`、逐变量自适应步长、梯度缩放、
回退线搜索和收敛配置。V3 中 updater 的 `add_objective_function(ShapeDerivative/Sensitivity)` 迁移为
`LocalSensitivityObjective` 的固定生命周期：`ObjectiveFunction` 计算全局灵敏度，
`DesignRegistry` 切分变量块，updater 在 `reinitialize()` 中建立局部线性展开。
V3 的 `add_constraints()` 迁移为具体 updater 的 `add_constraint()`，只写入当前 updater
的局部约束注册表；V3 的 `apply_surface_constraints()` 迁移为几何 updater 自己的
`_equality_constraint` 和 `_apply_equality_constraint()`。等式投影返回新 Tensor，registry 在
整个试探更新通过后统一提交；任一 owner 校验失败时恢复全部 owner 的提交前状态。

### 23.5.3 `Params`、`Controller`、`History` 与任务进程

| 类 | V4 责任和方法 |
|---|---|
| `Params` | `initialize()`、`reinitialize()`、`build_assembly()`、`get_assembly()`、`get_geometry()`、`get_materials()`、`get_fea()`、`build_meshes()`、`get_meshes()`、`export_problem_data()`、`save()`、`load()` |
| `Controller` | `initialize()`（一次性运行时初始化）、`initialize_path()`、`get_assembly()`、`start_optimization()`、`restart_optimization()`、`step()`（单次外层迭代）、`request_stop()`、`save()`、`load()`；内部 `_opt_loop()`、`_clear_runtime_cache()`、`_update_trial_assemblies()`、`_build_history_record()`、`_should_stop()`、设备迁移和 worker 管理 |
| `History` | `add_record()`、`get_records()`、`get_series(name)`、`get_result_paths()`、`save()`、`load()`；保留 objective、time、元素数、节点数、变形和 metrics 序列 |
| `SensitivityAnalyzer` | `initialize()`、`reinitialize()`、`build_sensitivities()`、`get_sensitivities()`；使用逐工况残差、切线刚度和请求 Jacobian 建立总导数 |
| `TaskRunner` | `start()`、`run_debug()`、`request_stop()`、`wait()`、`get_result_path()`；创建任务进程、设置环境、加载任务脚本、启动/重启 Controller，并通过 `RuntimeEvent` 转发状态 |

## 23.6 UI、Codegen 与 Observer

### 23.6.1 UI 数据模型

`ProblemDefinition`、`GeometryNode`、`PartNode`、`InstanceNode`、`MaterialNode`、`FEANode`、
`FEAComponentNode`、`LoadStepsNode`、`ObjectiveNode`、`UpdaterNode` 和 `SolverNode` 继续作为
定义层对象。每个节点保存可序列化字段，通过 `validate()` 校验并通过 `generate_data()` 生成
Codegen 输入；运行时 V4 对象只在生成任务进程和隔离预览进程中创建。

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
| `CodeGenerator` | `generate_source(problem)`、`export_source(problem, target_path)` | 生成或导出可执行任务源码 |
| `SchemeTemplate` | `create_problem()`、`create_part()`、`create_fea_component()`、`create_material()`、`create_updater()` | 创建默认问题树和各类编辑节点 |
| `SnippetDefinition` / `SnippetCatalog` | `render(parameters)`、`add_snippet()`、`get_for_slot()` | 渲染并按代码槽组织 instance、参考点、节点位移、参与力、应变能和变形梯度模板 |

生成顺序保持：Geometry → Materials → FEA components → Load steps → Objective → Solver →
Updaters → Controller。生成代码使用 V4 的 `build_*`、`get_*`、`update_*` 接口。

### 23.6.3 Launcher 与 Observer

| 类 | 必须保留的功能 |
|---|---|
| `TaskLauncher` | 运行生成 Python、设置工作目录和环境变量、流式转发输出并终止进程树 |
| `OptimizationConsole` | 增量清理 ANSI 样式、光标移动和覆写行，将规范化文本写入 UI 输出框并保留原始日志 |
| `ObserverPanel` | 读取 History、指标、迭代结果、deformation STL 和结果目录变化 |
| `Viewer` | 加载并显示初始模型、集合高亮、变形网格、结果曲面和观察数据 |

## 23.7 V4 实现顺序

1. 先实现 `BaseSurfaceInterface`、`CpBasedSurface`、BSP/CPGEO/STL 的映射缓存和独立
   `get_meshes()`，建立曲面单元测试。
2. 实现 `MeshBuilder`、`BoundaryPart`、导入 Part 和多 Part/Instance Assembly，验证集合、节点
   匹配和二阶节点映射。
3. 实现材料接口、SIMP 设计场、材料模型注册和材料灵敏度回写。
4. 实现 Geometry 的 `ReferencePoint`，再实现 FEA component、LoadStep、`FEAParams` 和 Solver。
5. 实现 Objective、Fairness evaluator、DesignRegistry 和 Updater，接通试探更新与正式提交。
6. 实现 Params、Controller、任务运行器、History 和结果导出。
7. 最后迁移 UI 数据模型、Codegen、TaskLauncher、ObserverPanel、Viewer 和现有任务脚本。

每个阶段都先完成对应类的“构造属性 → 运行时属性 → property → 外部接口 → 内部辅助函数”
表格，再实现代码和 `tests/morphopt/` 中一一对应的单元测试。
