# MorphOpt V4 校验、迁移与验收

> 文档属性：维护性迁移文档。本文件记录校验、验收和旧版迁移状态，不定义 V4 公共接口；接口以第 1–17 章主题设计文档为准。

本文件记录校验规则、模块迁移、测试验收、实施阶段和主题设计文档之间的接口关系。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文是维护性文档，负责把主题设计转换为校验规则、模块迁移任务、测试验收标准和实施顺序，
并记录 V3 功能到 V4 类与方法的落点。公共接口仍以第 1–17 章主题文档为准。

### 目录

- [18. 校验规则](#18-校验规则)
- [19. 模块结构和迁移范围](#19-模块结构和迁移范围)
- [20. 测试验收标准](#20-测试验收标准)
- [21. 实施顺序](#21-实施顺序)
- [22. 最终接口关系](#22-最终接口关系)
- [待确认](#待确认)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 第 1–17 章主题接口、V3 功能基线、模块路径、测试目标和迁移约束 |
| 输出 | 校验清单、目标目录、迁移映射、验收标准、实施阶段和待确认事项 |
| 主要读者 | V4 实施者、测试编写者、迁移 review 者和项目维护者 |
| 关联文档 | [架构总览](01-04Overview.md)、[功能基线](23FunctionInventory.md)、[总入口](../unified_model_architecture_plan.md) |

## 18. 校验规则

### 18.1 Geometry

- `part_name` 长度大于零且唯一；
- `BoundaryPart` 的 `element_name` 长度大于零且由构造函数显式传入；
- `INPPart` 和 `TorchFEAPart` 按 `C3D4`、`C3D6`、`C3D8`、`C3D10`、`C3D15`、`C3D20` 排列源元素类型，未列入的类型按源顺序追加；`element_names` 省略时采用排序后的源元素类型名称，显式提供时长度必须等于源元素族数量，名称长度大于零且保持唯一；
- `OffsetShellPart` 的 `solid_element_name` 和 `shell_element_name` 均显式提供长度大于零的值，彼此不同，
  且由构造函数显式传入；
- `OffsetShellPart.source_surface` 是与边界曲面数量相同、每项均为 `bool` 的列表，第 `0` 项必须为 `False`，
  第 `1` 项及以后控制对应曲面的向内偏置；偏置集合名称遵循 `surface_{i}_offset`；
- `instance_name` 长度大于零且在整个 `Assembly` 中唯一；
- 每个 `Part` 至少有一个 `Instance`；
- `exterior_surface` 存在于目标 `Part`；
- `translation` 和 `rotation` 都包含三个浮点分量；
- `ReferencePoint.name` 长度大于零且在 `Assembly` 中唯一；
- `ReferencePoint.position` 包含三个有限浮点分量；
- `Part` 构建后包含与其元素名称集合对应的有效元素和必要集合。

### 18.2 Materials

- 材料实现顺序与[材料系统](06Materials.md)一致：
  [`MaterialsParams`](06Materials.md#61-materialsparams) →
  [`MaterialModels`](06Materials.md#62-materialmodels) →
  [`BaseMaterialInterface`](06Materials.md#64-basematerialinterface) →
  [`HomogeneousMaterial`](06Materials.md#65-homogeneousmaterial) →
  [`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial)。
- `material_name` 长度大于零且唯一；
- 每个 [`BaseMaterialInterface`](06Materials.md#64-basematerialinterface) 对象都携带
  `part_name` 和 `element_name`，且两者长度大于零；
- 材料刷新接收当前 `Assembly` 并解析目标 `Part`；
- `element_name` 精确存在于当前 `Assembly` 目标 `Part` 的 `elems`；
- 一个 `Part` 的每个元素族恰好由一个材料对象覆盖；
- 材料范围彼此独立；
- 均匀材料参数对象必填；
- SIMP 参数、控制点和元素映射维度一致；
- `define_materials()` 只建立材料定义，`add_material(interface, name)` 注册单个材料；
- `initialize()` 建立静态材料结构，`reinitialize(iteration, assembly)` 解析当前
  `Assembly` 的目标元素和映射。

### 18.3 FEA

- FEA component 顺序与[FEA 组件](07Fea.md)一致：
  [`FEAParams`](07Fea.md#71-feaparams) →
  [`BaseFEAComponent`](07Fea.md#72-basefeacomponent) →
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
  [`Contact`](07Fea.md#713-contact)、
  [`SelfContact`](07Fea.md#714-selfcontact) →
  [`LoadStep`](07Fea.md#715-loadstep)。Solver 的定义与执行见 [08Solver.md](08Solver.md)。
- FEA component 名称唯一；
- `Instance`、surface、node set、element set 和几何层 RP 都存在；
- 每个 load step 包含全部 FEA component；
- 值向量长度等于 `num_values`；
- Jacobian 名称引用已注册 FEA component；
- `task_groups` 完整覆盖 step，索引保持唯一并处于有效范围；
- `define_components()` / `define_steps()` 只建立定义阶段注册表；
  `add_component()` 和 `set_step_*()` 分别注册 component 与工况值；
- 每个 component 的 `reinitialize(iteration, assembly)` 都使用同一个当前
  `Assembly` 解析运行时目标。

### 18.4 `Updaters`

- 每个 `UpdaterEntry` 的 `target_kind` 和 `target_name` 都能解析到真实目标；
- 内置 updater 的目标类型与 `target_kind` 匹配；
- `boundary_part` 只接受 `BoundaryPartUpdater`，`offset_shell_part` 只接受
  `OffsetShellPartUpdater`；
- 同一个 `(target_kind, target_name)` 只能注册一个 updater；
- `BoundaryPartUpdater` 与 `BoundaryPart` 类型匹配，`OffsetShellPartUpdater` 与
  `OffsetShellPart` 类型匹配；
- 两个不同 `BoundaryPart` 可以分别注册两个独立的 `BoundaryPartUpdater`，变量块、局部
  目标和优化器状态彼此隔离；
- 每个 updater 目标具有长度大于零的设计变量；
- `OffsetShellPart` 的设计变量长度与源边界曲面的元曲面控制点一致，
  `DesignRegistry` 只登记这组控制点变量；偏置节点、单元和偏置曲面由固定算法派生；
- 一个 `DesignKey` 只绑定一个 updater；
- updater 梯度长度等于 owner 变量长度；
- 所有已注册 updater 的变化成功后统一提交。

## 19. 模块结构和迁移范围

### 19.1 目标目录

~~~text
src/morphopt/optcore/
    ├── controller.py
    ├── protocols.py
    ├── designregistry.py
    ├── objfunc.py
    ├── solver.py
    ├── updaters.py
└── modelparams/
    ├── params.py
    ├── geometry.py
    ├── materials.py
    ├── feaparams.py
    ├── partinterface/
    │   ├── basepartinterface.py
    │   ├── boundarypart.py
    │   ├── inppart.py
    │   ├── torchfeapart.py
    │   ├── offsetshellpart.py
    │   └── instancedefinition.py
    ├── materialinterface/
    │   ├── basematerialinterface.py
    │   ├── homogeneousmaterial.py
    │   ├── simpfieldmaterial.py
    │   └── materialmodels.py
    └── feacomponent/
        ├── basefeacomponent.py
        └── concrete components...
~~~

### 19.2 旧能力迁移

| 旧位置 | 新位置 |
|---|---|
| shapeopt.geometryparams | partinterface.boundarypart + `GeometryParams` |
| shapeopt.update_geometry | `BoundaryPartUpdater`、`OffsetShellPartUpdater` |
| simp.simpmaterial | [`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial) |
| simp.update_material | `MaterialUpdater` |
| codesign.geometry | `OffsetShellPart` |
| FEA 中的 INP 导入 | `INPPart` |
| 固定 TorchFEA `Assembly` | `TorchFEAPart` |
| `Params` 三大变量分块 | `DesignRegistry` |

迁移后使用新的 shapeopt/simp/codesign 聚合方式、材料接口和字段命名；V4 采用新的
类名和模块路径。

### 19.3 同步迁移文件

- examples/bendingactuator.py；
- examples/gripper.py；
- codesign 示例；
- myjobs/ 中全部任务；
- tests/ 中几何、材料、灵敏度、运行结果和 UI 测试；
- UI model、schemas、codegen、`Part`/Material/FEA/Updater editor；
- docs/module_definition_guide.md；
- docs/module_reference.md；
- docs/UI_usage.md；
- docs/codestructure/ui_code_design.md；
- docs/theory/morphdesign.md；
- docs/theory/codesign.md。

## 20. 测试验收标准

### 20.1 Geometry 和 `Assembly`

- `BoundaryPart` 生成有效 `Part` 和默认同名 `Instance`；
- 一个 `Part` 生成多个不同变换的 `Instance`；
- 多个 `Part` 进入同一个 `Assembly`；
- 多个 `Instance` 共享同一 `Part` 的设计变量；
- `INPPart` 直接建立并缓存指定源 `Part` 对应的不可变 `Assembly`；
- `TorchFEAPart` 直接建立并缓存模型中的多个 `Part` 和 `Instance` 组成的不可变 `Assembly`；
- 导入 `Part` 的 `element_names` 与统一排序后的源元素族逐项对应；省略自定义名称时使用排序后的源元素类型名称；
- 每个 BSP 曲面自动生成 `surface_{i}_head`、`surface_{i}_bottom`、
  `surface_{i}_lateral` 和 `surface_{i}_all` 四个 surface set；
- 每个 CPGEO 曲面生成 `surface_{i}_all` 全部三角面集合；
- `BoundaryPart.exterior_surface` 默认值为 `extern`，其集合内容为
  `surface_0_all + surface_1_all + ...`；用户自定义名称后，整体集合使用该名称；
- `BSPSurface.get_meshes()`、`CPGEOSurface.get_meshes()` 和 `STLSurface.get_meshes()` 分别返回
  本类已经建立的预览网格；`build_meshes()` 建立缓存并返回 `None`；
- `OffsetShellPart` 生成并更新偏置节点、元素和表面；二阶单元节点更新使用 TorchFEA
  `Part.mid_pt_idxmap_torch`；
- `OffsetShellPart` 仅对 `source_surface[i] is True` 且 `i >= 1` 的曲面生成向内偏置，
  并注册 `surface_{i}_offset` 集合；
- `get_assembly()` 读取最近一次 `build_assembly()` 保存的结果。
- BSP、CPGEO 和 STL 曲面分别执行 `build_meshes()` 并由各自的 `get_meshes()` 读取预览缓存；
  预览数据与几何值、积分权重和节点映射使用同一迭代状态。

### 20.2 Materials

- [`MaterialModels`](06Materials.md#62-materialmodels) 中的每个参数类创建正确的 TorchFEA 本构类；
- 缺少材料参数时立即报错；
- [`HomogeneousMaterial`](06Materials.md#65-homogeneousmaterial) 覆盖目标元素族；
- 每个材料对象只覆盖其声明的一个 `element_name` 元素族；
- 材料覆盖重叠或缺失时初始化失败；
- SIMP 控制点、材料场、材料比例和元素写回一致；
- SIMP 专属方法只出现在 [`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial)；
- 材料对象保留 `part_name`、`element_name`，并在
  `reinitialize(iteration, assembly)` 中解析目标元素；
- `BaseMaterialInterface` 建立并持有 `_torchfea_<MaterialClass>`，`assign_material()` 和
  `update_assembly(design_delta)` 使用自身缓存的目标元素与 Assembly；
- `MaterialsParams` 通过 `define_materials()` 和 `add_material(interface, name)` 完成注册。

### 20.3 FEA、`Solver` 和 Objective

- FEA component 的目标名称解析正确；
- 每个 FEA component 的 `build_fea()` 一次性创建并保存对应的
  `_torchfea_<ConcreteName>`，`update_fea()` 更新工况值；
- 多工况结果按 `step_index` 返回；
- CPU/GPU 结果结构一致；
- 收敛状态与未收敛状态均带正确 `step_index`；
- `ObjectiveFunction` 返回标量目标；
- `metrics` 作为展示量，与设计变量梯度计算分离；
- Jacobian 引用错误时初始化失败。

### 20.4 `DesignRegistry` 和 Updater

- geometry、material 和联合变量 `offsets` 正确；
- 注册调用顺序变化时，完整变量顺序仍按 geometry → material → load 固定；
- 每个类别内部按目标名称字典序排列，同类别内的名称顺序保持稳定；
- `get_values()` 和 `split()` 使用同一排序结果；
- trial design delta 通过 `update_trial_values()` 和不带 `Assembly` 参数的
  `update_assembly(design_delta)` 回写到正确的 `Part`、材料接口或 FEA component；
- updater 梯度按变量块独立传递；
- 每个可更新 owner 绑定一个 updater，每个变量块只属于该 updater；
- 全部 updater 成功后统一提交变化；
- 未绑定 updater 的 `owner` 保持固定并参与 FEA。

### 20.5 UI 和运行结果

- UI 创建 `BoundaryPart`、`INPPart`、`TorchFEAPart` 和 `OffsetShellPart` 对应的定义节点；
- 一个 `Part` 创建多个 `Instance`；
- 材料元素选择来自真实 `Part.elems`；
- UI 材料节点同时记录 `part_name` 和 `element_name`，生成代码时传入材料对象构造函数；
- UI 支持为不同目标添加任意数量的 updater；同类 updater 可以同时存在，但一个目标实体只保留一个；
- Python 源码能够重建类型、属性、名称、代码槽和初始 Tensor 状态；源码生成使用
  `generate_python()` / `generate_source()` 直接返回文本，不把文本生成误作为运行时对象建立；
- 构造阶段仅记录定义；INP 读取、`Assembly`、UI 和 worker pool 在初始化/运行阶段建立；
- `initialize()` 后所有源数据、运行时缓存、FEA 对象和 updater 绑定完整可用；
- 每次运行从任务文件建立一致的初始设计变量、材料场和 updater 状态；
- 生成脚本可以独立 headless 运行。

### 20.6 状态恢复和后处理

- `Persistable.save()` 为每个 iteration 写入对应对象负责的状态和结果；
- 任务文件初始化完成后，`Persistable.load()` 能恢复设计变量、optimizer memory 和历史指标；
- `Controller.restart_optimization()` 按任务文件、`initialize()`、状态加载的顺序继续优化；
- 后处理直接读取 `History` 和结果文件，优化器由 Controller 与 Updaters 管理；
- 用户自定义曲面、约束和目标方法仍由任务 Python 文件提供。

## 21. 实施顺序

### 阶段 1：`Part` 和 `Assembly`

建立 partinterface 和 feacomponent，实现 `BasePartDefinition`、`InstanceDefinition`、`BoundaryPart`、
`INPPart`、`TorchFEAPart` 和 `OffsetShellPart`，重写 `GeometryParams`。

### 阶段 2：材料系统

按[材料系统](06Materials.md)顺序重写 [`MaterialsParams`](06Materials.md#61-materialsparams)、
[`MaterialModels`](06Materials.md#62-materialmodels)、
[`MaterialParameters`](06Materials.md#63-materialparameters)、
[`BaseMaterialInterface`](06Materials.md#64-basematerialinterface)、
[`HomogeneousMaterial`](06Materials.md#65-homogeneousmaterial) 和
[`SIMPFieldMaterial`](06Materials.md#66-simpfieldmaterial)，完成 `Part`/Elems 覆盖校验。

### 阶段 3：FEA 和 `Params`

按[FEA 组件](07Fea.md)顺序统一 `BaseFEAComponent`、具体 FEA component、
`FEAParams`、`LoadStep`、`FEAParams.build_components()` 和 FEA 名称校验；按[几何系统](05Geometry.md)
顺序实现 `ReferencePoint` 注册与 Assembly 构建，使用 `FEAParams.assign_components(assembly)`
完成 FEA component 写入，再由 `Controller` 将 Assembly 交给 Solver。

### 阶段 4：`DesignRegistry` 和 Updater

实现变量注册、切分和试探回写，将几何、材料和 FEA updater 统一为单 owner 绑定，
并将几何更新细分为 `BoundaryPartUpdater` 与 `OffsetShellPartUpdater`，接通
`ObjectiveFunction` 灵敏度。

### 阶段 5：`Controller`、`Solver` 和 codesign

按本文生命周期接通主循环、运行结果记录和联合优化，用 `OffsetShellPart` 迁移
codesign。

### 阶段 6：UI 和 Codegen

重写 UI 数据树和 schema，再改编辑器、模型树、预览和 Python 任务源码生成。
三种模板只生成统一对象组合。

### 阶段 7：全量迁移和清理

迁移 examples、myjobs、tests 和全部文档，删除旧聚合层和旧字段，运行编译、
单元、FEA、梯度、UI 和代表性优化测试。

## 22. 最终接口关系

最终用户需要表达四类关系：

~~~text
GeometryParams.define_parts() → add_part(part)
MaterialsParams.define_materials() → add_material(interface, material_name)
FEAParams.define_components() → add_component(component, fea_component_name)
Updaters.add_updater(target_kind, target_name, updater, updater_name)
~~~

一个完整问题的关系结构：

~~~text
Part body
    Instance body
    Instance body_mirror

Material body_solid
    target = body / C3D4
    interface = SIMPFieldMaterial

Material body_shell
    target = body / C3D6
    interface = HomogeneousMaterial

BoundaryPartUpdater body_shape
    target = BoundaryPart body

OffsetShellPartUpdater shell_shape
    target = OffsetShellPart shell

MaterialUpdater body_density
    target = Material body_solid
~~~

几何、材料、载荷和更新策略通过名称组合成一个 FEA/优化问题。shapeopt、simp
和 codesign 的差别只在于注册的对象组合。

## 待确认

当前只保留两个外部行为待确认：

1. `TorchFEAPart` 第一版读取 TorchFEA 模型文件，模型目录通过任务定义传入；
2. 材料覆盖强制要求每个 `Part` 的每个 `elems` 都恰好由一个材料对象覆盖。

其余类属性、方法、调用顺序、名称规则和模块边界作为实现约束。
