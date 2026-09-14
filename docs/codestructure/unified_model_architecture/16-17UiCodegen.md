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
| `_generated_params` | `Params` 或 None | None | 生成源码或预览时创建的参数对象 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `geometry` | `GeometryNode` | 只读 | 读写 | 通过节点编辑方法替换几何树 |
| `materials` | tuple[`MaterialNode`, ...] | 只读 | 读写 | 通过 `add_material()` 等方法维护 |
| `fea` | `FEANode` | 只读 | 读写 | 通过 FEA 编辑方法维护 |
| `solver` | `SolverNode` | 只读 | 读写 | 通过 solver 编辑方法维护 |
| `objective` | `ObjectiveNode` | 只读 | 读写 | 通过目标编辑方法维护 |
| `updaters` | tuple[`UpdaterNode`, ...] | 只读 | 读写 | 通过 `add_updater()` 等方法维护 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_part(part_node)` | None | - | 添加 `Part` |
| `remove_part(part_name)` | None | - | 删除 `Part` 和相关引用 |
| `add_instance(part_name, instance_node)` | None | - | 添加 `Instance` |
| `remove_instance(part_name, instance_name)` | None | - | 删除 `Instance` |
| `add_material(material_node)` | None | - | 添加材料 |
| `remove_material(material_name)` | None | - | 删除材料和 updater 引用 |
| `add_fea_component(component_node)` | None | - | 添加 FEA component |
| `rename_fea_component(old, new)` | None | - | 级联更新 load steps 和 Jacobian |
| `add_updater(updater_node)` | None | - | 添加任意类型的 updater，并保存目标类别和目标名称 |
| `validate()` | None | - | 执行完整定义校验 |
| `get_validation_errors()` | tuple[str, ...] | - | 读取最近一次定义校验结果 |
| `generate_python()` | str | - | 生成可直接运行的任务定义源码 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 本类的级联维护和校验通过外部接口完成 |

### 16.1.2 UI Node 属性

#### 构造属性（`__init__()` 记录）

下面的名称是 UI 表单使用的 property 名称；Node 的 `__init__()` 实际写入对应的
私有字段，例如 `name` 写入 `_name`，集合写入 `_parts` 或 `_components`。

| 类 | 构造属性 |
|---|---|
| `GeometryNode` | `parts`：`PartNode` 集合、`reference_points`：`ReferencePointNode` 集合 |
| `PartNode` | `name`、`part_type`、BoundaryPart 的必填 `element_name`、导入 Part 的可选 `element_names` 或 OffsetShellPart 的两个元素名称与 `source_surface`、`exterior_surface`、源数据和 `instances` |
| `InstanceNode` | `name`、`translation`、`rotation` |
| `ReferencePointNode` | `name`、`position` |
| `MaterialNode` | `name`、`part_name`、`element_name`、接口类型和材料参数 |
| `FEANode` | FEA component 集合和 load steps |
| `FEAComponentNode` | `name`、组件类型、目标名称、初始值和组件参数 |
| `LoadStepsNode` | step 数量和组件值矩阵 |
| `ObjectiveNode` | objective code、metrics code 和 Jacobian 名称 |
| `UpdaterNode` | `name`、`target_kind`、`target_name`、updater 类型、`local_constraints`、材料 `regularization_terms` 和几何 `equality_constraint` |
| `SolverNode` | process、GPU devices、task groups 和 `reuse_previous_solution`（`None`/bool） |

#### 运行时属性（`__init__()` 声明，生成或校验时填充）

各 Node 统一声明以下运行时属性：`_definition`（初始为 None，用于缓存对应的
MorphOpt 定义对象）、`_validation_errors`（初始为列表）和 `_initialized`
（初始为 False）。`build_definition()` 时填充 `_definition`；
`ProblemDefinition.generate_python()` 直接生成源码并返回，不改变节点的构造属性；表单编辑只修改构造属性。

#### 属性接口（property）

各 Node 的表单字段都通过 property 暴露。名称、类型、路径、目标名称、参数和数值
字段均为“可读、可写”，setter 执行类型转换和局部校验；派生的 `_definition`、
`_validation_errors` 和 `_initialized` 保留为运行时内部状态，不提供 property 接口。
集合字段返回 tuple 或只读视图，元素增删统一使用 `ProblemDefinition` 的
`add_*()`、`remove_*()` 方法。

#### 外部接口方法

| 类 | 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|---|
| `GeometryNode` | `build_definition()` | None | - | 创建并保存几何定义 |
| `GeometryNode` | `get_definition()` | `GeometryParams` | - | 读取已经创建的几何定义 |
| `PartNode` | `build_definition()` | None | - | 创建并保存对应 Part 定义 |
| `PartNode` | `get_definition()` | `BasePartDefinition` | - | 读取已经创建的 Part 定义 |
| `InstanceNode` | `build_definition()` | None | - | 创建并保存 Instance 定义 |
| `InstanceNode` | `get_definition()` | `InstanceDefinition` | - | 读取已经创建的 Instance 定义 |
| `MaterialNode` | `build_definition()` | None | - | 创建并保存材料接口 |
| `MaterialNode` | `get_definition()` | `BaseMaterialInterface` | - | 读取已经创建的材料接口 |
| `FEANode` | `build_definition()` | None | - | 创建并保存 FEA 定义 |
| `FEANode` | `get_definition()` | `FEAParams` | - | 读取已经创建的 FEA 定义 |
| `FEAComponentNode` | `build_definition()` | None | - | 创建并保存 FEA component |
| `FEAComponentNode` | `get_definition()` | `BaseFEAComponent` | - | 读取已经创建的 FEA component |
| `LoadStepsNode` | `build_definition()` | None | - | 创建并保存 load step 定义 |
| `LoadStepsNode` | `get_definition()` | `tuple[LoadStep, ...]` | - | 读取已经创建的 load step 定义 |
| `ObjectiveNode` | `build_definition()` | None | - | 创建并保存目标定义 |
| `ObjectiveNode` | `get_definition()` | `ObjectiveFunction` | - | 读取已经创建的目标定义 |
| `UpdaterNode` | `build_definition()` | None | - | 创建并保存 updater 注册项 |
| `UpdaterNode` | `get_definition()` | `UpdaterEntry` | - | 读取已经创建的 updater 注册项 |
| `SolverNode` | `build_definition()` | None | - | 创建并保存 solver 配置 |
| `SolverNode` | `get_definition()` | `Solver` | - | 读取已经创建的 solver 配置 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | Node 的字段转换和校验通过外部 `build_definition()` 接口完成 |

### 16.2 `Part` 编辑器

| `Part` 类型 | 编辑属性 |
|---|---|
| `BoundaryPart` | element_name、曲面顺序、外表面、网格参数、曲面代码、约束代码 |
| `INPPart` | 可选 element_names、INP 路径、源 `Part`、外表面、Instances |
| `TorchFEAPart` | 可选 element_names、模型目录、文件名、源 `Part`、模型集合摘要和 Instances |
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
| `load` | 可更新 FEA component 名称 | `FEAUpdater` |

Updater 编辑器按目标类型显示固定局部灵敏度目标和可配置约束：

| updater | 局部目标（固定） | 局部约束（可配置） | 额外约束入口 |
|---|---|---|---|
| `BoundaryPartUpdater` | `LocalSensitivityObjective`（由顶层灵敏度自动建立） | updater 内的 `Fairness`、`Distance`、`MinRadius`、`Cylinder`、`VolumeMaximization` 回调 | updater 内的唯一等式投影回调 |
| `OffsetShellPartUpdater` | `LocalSensitivityObjective`（由顶层灵敏度自动建立） | updater 内的偏置 `Fairness`、`InwardCurvatureRadius`、`OffsetSurfaceMinThickness` 回调 | updater 内的唯一等式投影回调 |
| `MaterialUpdater` | `LocalSensitivityObjective`（由顶层灵敏度自动建立） | updater 内的 `MinValue`、`MaxValue`、`VolFrac` | `DensityFieldMinimize` 附加正则项 |
| `FEAUpdater` | `LocalSensitivityObjective`（由顶层灵敏度自动建立） | `FEAUpdater` 自己定义的局部约束回调 | 无 |

局部灵敏度目标不提供编辑字段，也不生成 `add_objective()` 调用；编辑器维护对应 updater
的 `local_constraints`、材料 `regularization_terms` 和几何 updater 的唯一 `equality_constraint`，并按 updater
类型校验约束参数和可用模板。等式约束代码字段保存对应 updater 的投影方法体，代码生成器
直接将方法体写入该 updater 的 `_apply_equality_constraint()` 或其回调，由 updater 回调承载投影逻辑。

## 17. Codegen 和任务定义文件

### 17.1 Codegen 类

| 类/方法 | 实例属性 | 方法 | 来源 |
|---|---|---|---|
| `CodeGenerator` | 当前 `ProblemDefinition` | `generate_source(problem)` -> str | - |
| `SchemeTemplate` | 模板名称、标签、默认节点 | `build_root()` -> None；`get_root()` -> `ProblemDefinition` | - |
| `PartTemplate` | `Part` 类型和字段定义 | `create_part(data)` -> `PartNode` | - |
| `MaterialTemplate` | 材料接口和参数类 | `build_material(data)` -> None；`get_material()` -> `MaterialNode` | - |
| `UpdaterTemplate` | updater 类型和字段 | `create_updater(data)` -> `UpdaterNode` | - |

#### 构造属性（`__init__()` 记录）

下面列出的是模板对象的 property 名称；实际构造状态写入同名的私有字段。

| 类 | 属性 | 说明 |
|---|---|---|
| `CodeGenerator` | `problem`、模板目录、输出配置 | 当前 UI 定义和生成规则 |
| `SchemeTemplate` | `name`、标签、默认节点工厂 | 一套 UI 初始结构 |
| `PartTemplate` | `part_type`、必填字段定义 | 一种 `Part` 的代码模板；BoundaryPart 包含必填 `element_name`，导入 Part 包含可选 `element_names`，OffsetShellPart 包含两个元素名称和 `source_surface` |
| `MaterialTemplate` | 接口类型、参数类、默认字段 | 一种材料接口的代码模板 |
| `UpdaterTemplate` | updater 类型、目标类别、字段定义 | 一种 updater 的代码模板 |

#### 运行时属性（`__init__()` 声明，生成时填充）

| 类 | 属性 | 初始值 | 说明 |
|---|---|---|---|
| `CodeGenerator` | `_template_cache` | `{}` | 模板解析缓存 |
| `SchemeTemplate`、各类模板 | `_field_schema` | None | 初始化后解析的字段描述 |

#### 属性接口（property）

| 类 | property | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `CodeGenerator` | `problem` | 只读 | 内部维护 | 返回当前 UI 定义 |
| `SchemeTemplate` | `name`、`label` | 只读 | 内部维护 | 返回模板标识 |
| `PartTemplate`、`MaterialTemplate`、`UpdaterTemplate` | `field_schema` | 只读 | 内部维护 | 返回字段定义只读视图 |

Codegen 对象缓存模板解析；`generate_source()` 直接返回生成源码，不依赖运行时属性。
TorchFEA 模型由生成的 Python 任务文件和 `initialize()` 构造。

#### 外部接口方法

| 类 | 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|---|
| `CodeGenerator` | `generate_source(problem)` | str | - | 生成任务定义源码 |
| `SchemeTemplate` | `build_root()` | None | - | 创建并保存 UI 初始节点树 |
| `SchemeTemplate` | `get_root()` | `ProblemDefinition` | - | 读取已经创建的 UI 初始节点树 |
| `PartTemplate` | `create_part(data)` | `PartNode` | - | 创建 Part 编辑节点 |
| `MaterialTemplate` | `build_material(data)` | None | - | 创建并保存材料编辑节点 |
| `MaterialTemplate` | `get_material()` | `MaterialNode` | - | 读取已经创建的材料编辑节点 |
| `UpdaterTemplate` | `create_updater(data)` | `UpdaterNode` | - | 创建 updater 编辑节点 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | Codegen 模板转换通过上述外部接口完成 |

### 17.2 生成顺序

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
  updater 的唯一等式约束生成该 updater 的 `set_equality_constraint()` 或内部投影回调；局部灵敏度目标由
  `Controller` 分发梯度后自动建立，不写入任务文件，也不写入顶层 `ObjectiveFunction`。

### 17.3 Python 任务定义和运行结果

Python 任务文件直接表达用户的构造记录、用户自定义类和用户自定义方法，是任务
定义的唯一来源。UI 编辑树通过 `generate_python()` 生成同样的任务文件。

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

### 17.4 状态保存和历史读取

`Persistable` 是显式的文件 I/O 协议。实现该协议的对象保存自己负责的数据：

| 对象 | `save()` 内容 | `load()` 内容 |
|---|---|---|
| `Params`、`GeometryParams` | 当前几何、材料、FEA 数值状态 | 指定 iteration 的模型数值状态 |
| `DesignRegistry` | 变量块、offsets 和当前完整变量 | 指定 iteration 的设计变量 |
| `Solver` | solver 配置和运行元数据 | 指定 iteration 的 solver 状态 |
| `ObjectiveFunction`、`History` | 目标值、metrics、收敛信息和结果路径 | 历史数据和结果索引 |
| `BaseUpdater`、`Updaters` | optimizer memory 和 updater 状态 | 指定 iteration 的 updater 状态 |

`Controller.save()` 按固定顺序调用上述对象的 `save()`；`Controller.load()` 只在
任务文件已经完成 `initialize()` 后调用各对象的 `load()`。用户自定义曲面、约束和
目标函数的方法仍然来自当前任务文件，状态文件只提供这些方法所需的数值状态。
