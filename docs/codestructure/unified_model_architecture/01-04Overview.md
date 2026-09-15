
# MorphOpt 统一模型架构设计文档

本文件定义全局目标、命名、属性权限、协议、生命周期和文档维护规范。返回[总入口](../unified_model_architecture_plan.md)。

> 状态：完整设计稿，当前进入接口规划阶段。
>
> 本文只定义最终对象模型、实例属性、方法、调用关系、数据流和模块边界。
> 实现阶段按本文接口执行，V4 使用新的接口体系。

## 文档导航与输入/输出摘要

本文是 V4 的全局架构基线，统一说明对象边界、命名语义、属性权限、协议继承、生命周期、
调用关系和文档维护规则。后续主题文档沿用本文件定义的术语、方法前缀和状态分层。

### 目录

- [1. 设计目标](#1-设计目标)
- [2. 总体规则](#2-总体规则)：名称、属性、方法、事实来源、生命周期与文档表达
- [3. 核心类清单](#3-核心类清单)：对象职责、协议和显式继承关系
- [4. 生命周期和数据流](#4-生命周期和数据流)：初始化、迭代、Assembly 获取和任务定义

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | V4 领域对象、方法命名需求、运行时状态边界、TorchFEA Assembly 数据流 |
| 输出 | 统一的类职责、属性权限、方法语义、协议关系、生命周期和调用顺序 |
| 主要读者 | 核心对象实现者、UI/Codegen 实现者、测试编写者和代码 review 者 |
| 关联文档 | [编码规范](../style.md)、[几何系统](05Geometry.md)、[材料系统](06Materials.md)、[运行时](13-14Runtime.md)、[History](15History.md) |

## 1. 设计目标

MorphOpt 统一使用一个模型定义空间：

~~~text
Params
├── GeometryParams
│   └── Parts + Instances + ReferencePoints
├── MaterialsParams
│   └── MaterialInterface(part_name, element_name)
└── FEAParams
    └── FEA component + LoadStep definitions

Params.build_assembly()
    → GeometryParams 生成几何
    → MaterialsParams 写入材料
    → FEAParams 创建并写入 component
    → torchfea.Assembly
        ↓
    Controller 建立逐工况 FEAController
        ↓
    Solver 挂接 StaticImplicitSolver 并求解
        ↓
    StaticResult[step]
        ↓
    ObjectiveFunction + SensitivityAnalyzer + DesignRegistry
        ↓
    Updaters
        registered updater entries
~~~

`Params` 是问题级参数容器，包含 `GeometryParams`、`MaterialsParams` 和 `FEAParams`。
三大 Params 分别维护几何、材料和 FEA 定义，并由 `Params` 按固定顺序协调运行。
`Params.build_assembly()` 建立当前 `torchfea.Assembly`：几何参数生成模型，材料参数写入材料，
FEAParams 创建 component 并写入同一个 Assembly。`Controller` 用逐工况 Assembly 创建
`torchfea.FEAController`；Solver 为每个控制器创建并挂接 `StaticImplicitSolver`，随后执行求解。

`Assembly` 是 `Params.build_assembly()` 生成并由 `Params._torchfea_Assembly` 保存的运行时
模型。`FEAParams` 维护 FEA component 和 load step 定义，在当前 Assembly 建立后创建 component，
并通过 `assign_components()` 将 component 写入该 Assembly。最终对象关系固定为：`Params`
包含三大 Params，三大 Params 共同加工一个 Assembly，Controller 组合逐工况
`FEAController`，Solver 为控制器提供静力求解器并执行求解。

用户可以自由组合：

- `BoundaryPart`、`INPPart`、`TorchFEAPart` 和 `OffsetShellPart`；
- 一个 `Part` 的多个 `Instance` 和独立变换；
- `HomogeneousMaterial`、`SIMPFieldMaterial` 以及未来的材料场接口；
- 多个几何 `Part` 和多个材料对象；
- 固定 FEA、纯几何优化、纯材料优化和几何/材料联合优化；
- 载荷设计变量和 `FEAUpdater`；
- 任务定义对象的构造函数只记录构造状态，运行时对象统一在 `initialize()` 阶段建立。

shapeopt、simp 和 codesign 作为 UI 模板和示例组合，底层模型统一使用通用架构。

## 2. 总体规则

### 2.1 名称体系

| 名称 | 所属对象 | 使用位置 |
|---|---|---|
| `part_name` | `Part` 实例属性 | Geometry、Materials、`BoundaryPartUpdater`、`OffsetShellPartUpdater` |
| `instance_name` | `Instance` 实例属性 | FEA component、结果显示 |
| `element_names`（`Part`） | `BasePartDefinition` 输出属性 | 当前 `Part.elems` 的元素名称集合；具体定义按元素族数量建立 |
| `element_name`（`BoundaryPart`） | `BoundaryPart` 构造属性 | 单一生成元素族的名称，构造时必填 |
| `element_names`（导入 `Part`） | `INPPart`、`TorchFEAPart` 构造属性 | 与源模型元素族一一对应的名称列表；省略时直接采用元素类型名称 |
| `solid_element_name` | `OffsetShellPart` 构造属性 | 偏置壳实体部分的元素名称，构造时必填 |
| `shell_element_name` | `OffsetShellPart` 构造属性 | 偏置壳壳部分的元素名称，构造时必填 |
| `source_surface` | `OffsetShellPart` 构造属性 | 与曲面顺序对应的布尔列表；第 0 项为 `False`，第 1 项及以后选择向内偏置曲面 |
| `part_name`、`element_name`（材料） | `BaseMaterialInterface` 构造属性 | 联合定位一个 `Part` 中的一种元素类型 |
| `material_name` | `MaterialsParams.materials` | `MaterialUpdater` |
| `fea_component_name` | `FEAParams` | load steps 和 Jacobian |
| `updater_name` | `UpdaterEntry` | 日志和 UI |

`BoundaryPart` 的 `element_name` 在构造时显式提供并形成单元素集合。导入 `Part` 的
`element_names` 是可选列表，长度必须等于源模型的元素族数量；省略时直接使用源元素类型名。
导入元素类型按以下顺序排列并与自定义名称逐项对应：
`C3D4`、`C3D6`、`C3D8`、`C3D10`、`C3D15`、`C3D20`。未列入该顺序的元素类型按源模型
顺序追加。省略自定义名称时，也按照该顺序生成元素名称列表。
`OffsetShellPart` 同时
构造实体和壳两组元素，因此分别使用必填的 `solid_element_name` 和
`shell_element_name`，两个名称保持不同。`source_surface` 的长度等于边界曲面数量，
索引 `0` 固定为 `False`，索引 `1` 及以后控制向内偏置；生成的曲面集合命名为
`surface_{i}_offset`。材料对象的 `part_name` 和 `element_name` 在构造时成对提供，
精确定位一个 `Part` 中的一种元素类型；需要覆盖多个元素类型时，为每一种元素类型注册
独立的材料对象。

### 2.2 属性和所有权

每个 `Part`、材料接口、FEA component 和 updater 都是独立的实例对象。运行时状态
写入对象实例属性；ClassVar 用于类型级常量，`Part` 名称、控制点、梯度和当前缓存
均由各自实例独立维护。

类级属性只定义类型级常量，例如材料参数类的 material_class。

每个类的状态分为三栏，文档中的属性表按以下规则书写：

| 属性栏 | 存储形式 | 用途 | 对外访问规则 |
|---|---|---|---|
| 构造属性 | 私有实例属性，例如 `_part_name`、`_element_name`、`_element_names` | 保存用户在 `__init__()` 中给出的定义、注册关系和构造参数 | 通过同名 `property` 读取 |
| 运行时状态 | 私有实例属性，例如 `_torchfea_Assembly`、`_mesh`、`_optimizer` | 保存 `initialize()`、`build_part()`、`build_assembly()` 和求解过程中产生的缓存 | 通过明确的 `build_*`、`get_*`、`export_*`、生命周期或持久化方法访问 |
| 属性接口（property） | `@property` 及必要的 setter | 提供稳定的对外观察和受控修改入口 | 每一项明确标注读权限和写权限 |

构造属性和运行时状态栏中的名称使用实际私有字段名，并以 `_` 开头。属性接口栏
使用对外名称，例如 `_part_name` 对应 `part_name`；每个构造属性都以同名
`property` 对外提供读取，允许写入的字段再提供受控 setter。字典、列表和可变 Tensor
通过 property 返回只读视图、只读副本或 detached clone。定义状态通过 `add_part()`、
`add_material()`、`add_updater()` 等公开方法修改。运行时状态只保留在对象内部，外部
通过 `build_*`、`get_*`、`export_*`、生命周期方法或持久化方法获取和维护，运行时状态
不出现在属性接口表中。

属性接口表的权限使用以下含义：

| 权限 | 含义 |
|---|---|
| 只读 | property 提供读取，状态由对象内部维护 |
| 读写 | 可以读取和赋值；setter 负责校验并维护相关索引 |
| 内部维护 | 构造属性由对象生命周期或专用公开方法维护；运行时状态通过显式方法访问 |

方法表也分为两类：

| 方法栏 | 命名规则 | 调用者 | 说明 |
|---|---|---|---|
| 外部接口方法 | 公开方法名 | 其他对象、任务定义类、updater、UI、求解器或后处理 | 组成类的稳定调用接口；协议方法也放在这里，并保留协议来源列 |
| 内部辅助函数 | 一个前导 `_` | 仅本类内部 | 完成拆分、缓存、格式转换和后端对象创建等辅助工作，调用范围限定在本类 |

每个类的方法部分固定包含“外部接口方法”和“内部辅助函数”两张表。内部辅助函数表处于
空表状态时，在第二张表中写“空”。外部接口表先列来源为 `-` 的本类独有方法，
再按 `Initializable`、`Updatable`、`Visualizable`、`Persistable` 的顺序列出协议方法；
同一协议内保持协议定义的方法顺序。方法的可见性由名称确定。

每个类的完整接口说明固定按“构造属性、运行时属性、属性接口、外部接口方法、内部辅助
函数”的顺序组织。某一区块内容为空时保留对应表格并标注“空”；子类直接继承基类状态时，
在对应表格中明确标注继承范围或“空”。

子类表格只列本类新增或重写的成员；未重写的继承属性、外部接口方法和内部辅助函数不
重复列出，空表保留并说明继承范围。已列出的重写接口保留“来源”列：本类新增接口使用
`-`，父类重写接口标注定义该接口的最上层父类，协议直接定义的重写接口标注协议名称。

### 2.3 方法前缀语义

公共方法的前缀直接表达状态边界和调用成本。方法表用“有/无”标记返回值和类属性更新，
调用者据此组合生命周期步骤：

| 前缀 | 语义 | 是否有返回值 | 是否更新类属性 | 调用示例 |
|---|---|---|---|---|
| `get_` | 读取已经存在的属性、缓存或结果 | 有 | 无 | `get_assembly()`、`get_geometry_values()`、`get_meshes()` |
| `set_` | 修改已经存在的构造属性或定义状态 | 无 | 有 | `set_parameters()`、`set_rotation()` |
| `add_` | 向已有 `list` 或 `dict` 注册单个定义项 | 无 | 有 | `add_part()`、`add_material()` |
| `build_` | 从定义状态建立此前不存在的运行时属性 | 无 | 有 | `build_assembly()`、`build_fea()` |
| `update_` | 更新已经建立的运行时属性 | 无 | 有 | `update_assembly()`、`update_material_field()` |
| `assign_` | 将已经建立的对象挂接到已有目标 | 无 | 有 | `assign_material()`、`assign_materials()` |
| `apply_` | 将待提交的变化正式写回已有定义或 owner | 无 | 有 | `apply_design_delta()`、updater 的 `_apply_equality_constraint()` |
| `compute_` | 重新计算一个结果 | 有 | 无 | `compute_jacobian()`、`compute_case_objective()` |
| `generate_` | 根据已有定义生成代码、文本或临时结果 | 有 | 无 | `generate_source()`、`generate_summary()` |
| `create_` | 创建一次性的定义对象或编辑节点工厂结果 | 有 | 无 | `create_part(data)`、`create_updater(data)` |
| `export_*` | 将已有定义或运行时结果写入外部文件，方法名明确写出导出对象 | 有 | 无 | `export_surface(target_path)`、`export_model(file_path)` |

`get_` 与 `build_` 成对使用：`build_*` 完成建立并写入内部状态，`get_*` 只读取该状态。
读取前需要刷新时，调用者显式调用 `build_*` 或 `update_*`。`initialize()`、
`reinitialize()`、`apply_*`、`save()` 和 `load()` 是生命周期或协议方法，方法表说明它们
具体建立、刷新、提交或恢复的状态。运行时新属性统一使用 `build_*` 建立；`create_*`
作为其他语义方法时遵循所属协议，运行时属性建立入口统一使用 `build_*`。

`compute_*` 用于需要重新计算且直接返回结果的纯计算；`generate_*` 用于根据定义生成代码、
文本或临时结果并直接返回；`create_*` 仅用于不进入运行时生命周期的一次性定义对象或
编辑节点工厂。三者都不替代运行时属性的 `build_*`/`update_*` 生命周期。

设计变量接口遵循同一规则：`build_design_delta()` 创建并保存新的设计增量，
`get_design_delta()` 读取已有设计增量；`set_parameters()` 写入已有参数快照，
`update_assembly(design_delta)` 更新已有 `Assembly`；对象直接使用自身缓存的
TorchFEA 引用。`apply_design_delta()` 正式提交更新。

### 2.4 事实来源

| 数据 | 唯一事实来源 |
|---|---|
| `Part` 注册关系 | `GeometryParams.parts` |
| `ReferencePoint` 注册关系 | `GeometryParams.reference_points` |
| 材料注册关系 | `MaterialsParams.materials` |
| FEA component | `FEAParams.fea_components` |
| 设计变量顺序 | `DesignRegistry.get_blocks()`：先 geometry，再 material，最后 load；各类别内部按目标名称字典序 |
| updater 目标绑定 | `Updaters` 的 entry 字典 |

索引和摘要由上述事实来源生成，运行时关系集中维护在上述事实来源中。

### 2.5 定义数据和运行时对象

定义对象记录“如何构造”的状态：名称、路径、参数、目标名称、`Instance` 变换、
材料参数、优化配置和用户代码槽。构造函数记录这些状态，完整构造由生命周期方法完成；
定义对象可以在 `Assembly`、TorchFEA 材料对象、GPU Tensor、进程池
和 UI widget 的运行时环境建立前完成。

运行时对象和派生缓存只在 `initialize()`、`build_part()`、`build_assembly()` 或
`build_solvers()` 中
建立。运行时字段使用实例属性维护；例如 `_torchfea_Assembly`、
`_torchfea_Part`、`_control_points`、元素映射、
FEA 缓存和 worker pool 均属于运行时对象。

每个类的属性表明确分为三组。构造属性由 `__init__()` 接收并写入私有字段，用于
注册、引用和记录构造方式；运行时状态也在 `__init__()` 中显式声明为私有字段，但
初始值统一为 `None`、空容器或 `False`，由 `initialize()` 填充或替换；属性接口栏
只列构造属性的同名 property、读权限和写权限。运行时结果通过显式生命周期、构建、
读取、导出或持久化方法访问。对象定义可以直接查看，重计算由显式生命周期方法触发，
内部状态通过公开方法维护。

### 2.6 构造记录和初始化结果

所有主要类遵循同一条边界：

| 阶段 | 工作内容 | 结果 |
|---|---|---|
| `__init__()` | 只写入构造状态、创建空的 dict/list、记录用户定义顺序和代码槽 | 轻量定义对象 |
| `initialize()` | 读取源文件、解析跨对象名称、建立反向引用、创建缓存、分配运行时 Tensor、构造 TorchFEA 对象、完成完整校验 | 完整构造后的运行时对象 |
| `build_part()` / `build_assembly()` | 根据当前设计变量生成本迭代 `Part`、`Assembly` 和材料状态并写入内部状态 | 方法返回 `None`；结果通过对应的 `get_*` 读取 |
| `build_solvers(fea_controllers)` | 由 `Solver` 根据求解配置为每个 `FEAController` 创建并挂接 `StaticImplicitSolver` | 方法返回 `None`；结果通过 `get_solver(case_index)` 读取 |
| `reinitialize()` | 清理或刷新当前迭代缓存，准备下一次求解 | 下一迭代的运行时状态 |

`Params` 持有的三大 Params 采用注册式定义入口。`GeometryParams.__init__()`、`MaterialsParams.__init__()`
和 `FEAParams.__init__()` 只创建空注册表；对象第一次执行 `initialize()` 时调用对应的
`define_*()` 扩展点。用户在
`define_parts()`、`define_reference_points()`、`define_materials()`、`define_components()` 和
`define_steps()` 中通过 `add_part()`、`add_reference_point()`、`add_material()`、
`add_component()` 和 `set_step_*()` 注册对象与配置。
各 `define_*()` 方法中创建领域定义对象并注册，注册顺序成为用户定义顺序。

单个 `Part`、材料接口和 FEA component 的参数在各自的 `define_*()` 注册方法调用中提供。
运行时对象和后端模型统一延迟到生命周期阶段建立。以下工作统一延迟到
`initialize()`：INP 或 TorchFEA 文件读取、网格和曲面构建、`Part`/`Instance` 解析、
材料元素映射、GPU 数据分配、进程池创建、FEA 模型创建、设计变量注册和 updater
目标绑定。`initialize()` 必须可重复调用；重复调用先清理旧的运行时缓存，再根据
定义状态重新建立它们。

任务类中的 `define_parts()`、`define_reference_points()`、`define_materials()`、
`define_components()` 和 `define_updaters()` 负责注册定义对象和记录参数；源文件读取、
`Assembly` 访问、求解器创建、
Tensor 场分配和优化器创建由 `initialize()` 及后续生命周期方法完成。

集合级 Params 的注册表属于“定义属性”：`__init__()` 创建空容器，`define_*()` 和
`add_*()` 填充用户定义内容。单个 `Part`、材料接口和 FEA component 的标量配置属于
对象自身的构造属性；两类属性在文档表格中分别标记。

用户任务采用以下注册式结构：

~~~python
class TaskGeometry(GeometryParams):
    def define_parts(self):
        self.add_part(BoundaryPart(...))

    def define_reference_points(self):
        self.add_reference_point(ReferencePoint(name="load_point", position=(0.0, 0.0, 1.0)))


class TaskMaterials(MaterialsParams):
    def define_materials(self):
        self.add_material(
            HomogeneousMaterial(part_name="body", element_name="C3D4", ...),
            name="body_material",
        )


class TaskFEA(FEAParams):
    def define_components(self):
        self.add_component(Pressure(...), name="pressure")
~~~

`Params` 在创建三个子系统时触发这些定义入口；注册顺序成为各集合的用户定义顺序。

### 2.7 文档表述规范

架构文档统一采用正向、职责导向的表述方式：

- 直接说明对象负责的工作、输入、输出和生命周期阶段；
- 约束写成“必须显式提供”“长度大于零”“保持唯一”“通过校验”等可执行规则；
- 状态值、空集合和可选字段直接写明其含义与后续处理；
- 接口差异通过职责、来源和调用时机说明，方法表保持与实现顺序一致；
- 设计决策、迁移范围和验收标准使用同一套正向术语。

## 3. 核心类清单

| 模块 | 类 | 一条对象表示什么 |
|---|---|---|
| 基础设施 | `Visualizable` | 可视化对象的 `build_meshes()`、`get_meshes()` 协议 |
| 基础设施 | `Initializable` | 延迟建立运行时对象和缓存的生命周期协议 |
| 基础设施 | `Persistable` | 迭代状态和历史数据的 `save()` / `load()` 协议 |
| 基础设施 | `Updatable` | 可优化对象的增量读取、Assembly 试探更新和正式提交协议 |
| 总参数 | `Params` | 一个完整 FEA/优化问题 |
| 几何 | `GeometryParams` | `Part` 集合和当前 `Assembly` |
| 几何 | `BasePartDefinition` | 一个 `Part` 的公共状态和生命周期 |
| 几何 | `InstanceDefinition` | 一个 `Instance` 的名称和变换 |
| 几何 | `ReferencePoint` | Assembly 级参考点定义和 TorchFEA 参考点缓存 |
| 几何 | `BoundaryPart` | 由边界曲面生成的 `Part` |
| 几何 | `INPPart` | 从 INP 源 Assembly 提取一个 Part 的几何定义 |
| 几何 | `TorchFEAPart` | 从 TorchFEA 源 Assembly 提取一个 Part 的几何定义 |
| 几何 | `OffsetShellPart` | 由边界 `Part` 生成偏置壳的 `Part` |
| 几何 | `BaseSurfaceInterface` / 具体曲面类 | 一个可注册到 `Part` 的曲面定义 |
| 材料 | `MaterialsParams` | Assembly 材料解析、分配集合和覆盖校验 |
| 材料 | `MaterialModels` | 本构参数类命名空间 |
| 材料 | `MaterialParameters` | 一个 TorchFEA 本构的类型化参数记录 |
| 材料 | `BaseMaterialInterface` | 材料接口公共生命周期 |
| 材料 | `HomogeneousMaterial` | 固定均匀材料接口 |
| 材料 | `SIMPFieldMaterial` | SIMP/BSP 材料场接口 |
| FEA | `FEAParams` | Assembly 目标解析、FEA component 和 load step |
| FEA | `LoadStep` | 工况值和 step 顺序 |
| FEA | `LoadValueBlock` | 一个 component 在一个工况中的可更新参数块 |
| FEA | `BaseFEAComponent` | 载荷/边界/接触公共生命周期 |
| 求解 | `Solver` | 逐工况静力求解器创建、挂接与多进程 FEA 求解 |
| 目标 | `ObjectiveFunction` | 顶层目标、指标、Jacobian 请求和结果网格 |
| 灵敏度 | `SensitivityAnalyzer` | 多工况静力平衡的隐式/伴随总导数 |
| 历史 | `History` | 迭代目标、指标和时间记录 |
| 变量 | `DesignKey` | 一个变量块的稳定名称 |
| 变量 | `DesignBlock` | 变量块的范围和拥有者 |
| 变量 | `DesignRegistry` | 变量注册、切分、Assembly 试探更新和正式提交 |
| 更新 | `BaseUpdater` | 一块变量的更新策略 |
| 更新 | `BaseOptimizer` / `LBFGSOptimizer` | updater 局部优化和回退线搜索 |
| 更新 | `BaseGeometryUpdater` | 几何 updater 的公共生命周期 |
| 更新 | `BoundaryPartUpdater` | 一个 `BoundaryPart` 的更新策略 |
| 更新 | `OffsetShellPartUpdater` | 一个 `OffsetShellPart` 的更新策略 |
| 更新 | `MaterialUpdater` | 一个材料接口的更新策略 |
| 更新 | `FEAUpdater` | 一个 FEA component 的更新策略 |
| 更新 | `Updaters` | 任意数量 updater 的注册和调度 |
| 运行 | `Controller` | 初始化、求解和迭代循环 |

### 3.1 协议和显式继承关系

协议分为共同生命周期协议和可更新能力协议。所有需要运行时管理的对象按职责继承
`Visualizable`、`Initializable`、`Persistable`；有设计变量的具体对象再继承
`Updatable`。`build_part()`、`build_assembly()`、`assign_material()` 和 `build_fea()` 是四个
领域基类自身集中定义抽象核心方法，协议集中定义跨领域约定。
协议集中定义在 `optcore/protocols.py`。

协议规定方法集合，运行时属性由实现类在 `__init__()` 中显式声明并维护。

方法命名统一区分可调用接口和内部实现：供其他对象、任务定义类、updater、UI 或
后处理调用的方法采用公开方法名；只服务于本类内部流程的辅助方法使用一个前导
下划线，例如 `_register_surface_sets()`、`_create_bsp_model()`。方法表中带有前导
下划线的方法归入本类内部调用范围。

#### 共同协议

| 协议 | 必需方法 | 继承者 |
|---|---|---|
| `Visualizable` | `build_meshes()`、`get_meshes()` | `BasePartDefinition`、`BaseMaterialInterface`、`BaseFEAComponent` 和各具体曲面 |
| `Initializable` | `initialize()`、`reinitialize(iteration, **context)` | 所有需要建立或刷新运行时状态的定义基类和管理类 |
| `Persistable` | `save(folder_path, iteration)`、`load(folder_path, iteration)` | 需要保存迭代状态或读取历史数据的对象 |
| `Updatable` | `get_parameters()`、`set_parameters()`、`build_design_delta()`、`get_design_delta()`、`update_assembly()`、`apply_design_delta()` | 有设计变量的具体 Part、材料场和 `LoadValueBlock` |

三个领域基类采用显式继承：

| 基类 | 继承的协议 | 领域职责 |
|---|---|---|
| `BasePartDefinition` | `Visualizable`、`Initializable`、`Persistable` | 记录生成型 Part 定义、生成 TorchFEA Part、提供几何预览 |
| `BaseMaterialInterface` | `Visualizable`、`Initializable`、`Persistable` | 记录材料定义、写入元素材料、提供材料预览 |
| `BaseFEAComponent` | `Visualizable`、`Initializable`、`Persistable` | 记录载荷定义、创建 FEA 对象并提供载荷预览 |

`INPPart` 与 `TorchFEAPart` 采用固定导入模型生命周期：它们缓存只读源 Assembly，从中提取
一个指定 Part 及其选定实例，并通过 `build_part()` / `get_part()` 参加统一装配。
`BoundaryPart` 和 `OffsetShellPart` 使用相同接口建立和读取生成型 Part。多个导入 Part 由
多个定义对象表示，可以共享同一源模型路径和读取缓存。

三个参数集合和总参数对象显式继承 `Visualizable`、`Initializable`、`Persistable`，负责记录定义
状态、聚合预览并向 Registry 提供具体设计 owner：

| 类 | 继承的协议 |
|---|---|
| `Params` | `Visualizable`、`Initializable`、`Persistable` |
| `GeometryParams` | `Visualizable`、`Initializable`、`Persistable` |
| `MaterialsParams` | `Visualizable`、`Initializable`、`Persistable` |
| `FEAParams` | `Visualizable`、`Initializable`、`Persistable` |

其他具有完整运行时建立阶段的管理类也显式继承 `Initializable`：

| 类 | 继承的协议 |
|---|---|
| `Controller` | `Initializable`、`Persistable` |
| `Solver` | `Initializable`、`Persistable` |
| `ObjectiveFunction` | `Initializable`、`Persistable` |
| `SensitivityAnalyzer` | `Initializable` |
| `DesignRegistry` | `Initializable`、`Persistable` |
| `BaseUpdater` | `Initializable`、`Persistable` |
| `Updaters` | `Initializable`、`Persistable` |
| `History` | `Initializable`、`Persistable` |

#### 可更新对象

`Updatable` 是跨几何、材料和 FEA 的可选公共协议。它表示对象拥有一块可被
`DesignRegistry` 管理的设计变量，并且能够接收变量更新。具体可更新类根据自身职责
显式继承该协议；固定定义类保持稳定状态：

| 类 | 是否继承 `Updatable` | 状态 |
|---|---|---|
| `GeometryParams` | 否 | 通过 `get_design_owners()` 提供具体 Part |
| `MaterialsParams` | 否 | 通过 `get_design_owners()` 提供具体材料场 |
| `BoundaryPart` | 是 | 几何变量可更新 |
| `OffsetShellPart` | 是 | 偏置几何可更新 |
| `SIMPFieldMaterial` | 是 | 材料场可更新 |
| `LoadValueBlock` | 是 | 一个 component 的一个工况参数可更新 |
| `INPPart` | 否 | 固定导入几何 |
| `TorchFEAPart` | 否 | 固定导入几何 |
| `HomogeneousMaterial` | 否 | 固定均匀材料 |
| `BaseFEAComponent` | 否 | component 的工况参数由 `LoadStep` 和 `LoadValueBlock` 管理 |

`GeometryParams.get_design_owners()`、`MaterialsParams.get_design_owners()` 和
`FEAParams.get_design_owners()` 为 Registry 提供具体 owner；Registry 按 owner 建立独立变量块。

`Updatable` 定义两组方法：

| 方法 | 来源 | 作用 |
|---|---|---|
| `get_parameters()` | - | 读取 owner 的内部参数，返回 detached clone |
| `set_parameters(parameters)` | - | 将参数快照以 detached clone 写回 owner 的内部状态 |
| `build_design_delta()` | - | 创建全 0 的设计增量 Tensor，保留 autograd，并写入 owner 的运行时状态；方法返回 `None` |
| `get_design_delta()` | - | 读取已经由 `build_design_delta()` 建立的设计增量 Tensor；不重新分配或重计算 |
| `update_assembly(design_delta)` | - | 使用对象自身缓存的 TorchFEA 引用，将设计增量映射到已有 `Assembly`，保留计算图并用于试探计算 |
| `apply_design_delta(design_delta)` | - | 将优化器输出的设计增量映射并正式写回 owner 状态 |

固定定义对象保持稳定状态并参与模型构建与求解；具有设计变量的对象实现 `Updatable`
并注册到 `DesignRegistry`。对象的可更新能力由类型接口表达，运行时缓存由初始化和
迭代生命周期维护。

`Initializable` 定义统一的 `initialize()` 和 `reinitialize(iteration, **context)` 生命周期入口。
领域基类在其中调用自己的初始化步骤，参数集合在其中初始化下属对象并建立跨对象引用，
再通过 `reinitialize()` 刷新当前 iteration 的运行时状态。几何处理器在
`reinitialize(iteration)` 中生成当前 Assembly，材料和 FEA 处理器在
`reinitialize(iteration, assembly)` 中解析该 Assembly；上下文参数由领域接口显式声明。

`Persistable` 定义统一的迭代状态和历史数据 I/O 入口。`save()` 写入当前对象负责的
状态或结果，`load()` 从指定 iteration 读取数据。每个类明确自己的字段和文件内容，
恢复过程由对象自身的持久化实现完成。

### 3.2 协议调用关系

`Params` 统一协调三个子参数处理器的核心方法。几何子参数处理器创建 Assembly，材料和 FEA
子参数处理器在 `reinitialize()` 阶段绑定当前 Assembly，后续通过各自持有的 TorchFEA 对象
完成加工。Assembly 的归属仍然是 Params；下面的协议图展示的是三个子处理器在 Params 调度下
对同一个 Assembly 的加工顺序：

~~~text
GeometryParams
    → build_part() / build_assembly()
    → get_assembly()
    → assembly

MaterialsParams
    → reinitialize(iteration, assembly)
    → BaseMaterialInterface.build_material()
    → BaseMaterialInterface.assign_material()

FEAParams
    → reinitialize(iteration, assembly)
    → BaseFEAComponent.build_fea()
    → assign_components()
    → build_case_assemblies()
    → DesignRegistry.update_assembly(delta, {"load"})
    → get_case_assemblies()

Solver
    → build_solvers(fea_controllers)
    → solve(fea_controllers)
    → get_results()
~~~

`MaterialsParams` 和 `FEAParams` 的 `reinitialize()` 接收当前 `Assembly` 并建立目标缓存；
完成绑定后，材料接口和 FEA component 通过自身的 TorchFEA 对象引用进行构建、分配和更新。
`FEAParams.assign_components()` 将基础 FEA component 写入已绑定 Assembly。Controller 先将
geometry/material 试探值写入基础 Assembly；`FEAParams.build_case_assemblies()` 再为每个
工况建立独立 Assembly 和 component 运行副本并绑定 `LoadValueBlock`；Registry 最后将 load
试探值写入各自工况副本。Controller 用这些 Assembly 创建逐工况 `FEAController`，Solver
创建并挂接对应静力求解器。
每个处理器可以单独测试：提供一个符合 TorchFEA 结构的 `Assembly` 完成绑定，再验证各自
对象的运行时结果。

可视化先调用 `Visualizable.build_meshes()` 建立当前缓存，再调用
`Visualizable.get_meshes()` 读取预览对象。可更新对象统一由 `Updatable` 交给
`DesignRegistry` 管理，用户定义类通过显式继承表达自己的可变能力。固定对象只参与
构建和可视化。

`get_parameters()` 和 `set_parameters()` 用于保存、恢复以及子优化过程中的状态切换；
它们始终使用 detached clone。设计优化先调用 `build_design_delta()` 建立设计增量，
再用 `get_design_delta()` 读取已有变量，随后使用 `update_assembly()` 执行已有模型的
可微试探更新，最后调用 `apply_design_delta()` 正式提交。生成型 `Part` 通过
`build_part()` 创建 TorchFEA `Part`，`GeometryParams.build_assembly()` 负责装配
`Part` 和 `Instance` 并写入内部状态。`INPPart` 与 `TorchFEAPart` 在内部读取源 Assembly，
通过统一的 `build_part()` 建立输出 Part。建立方法均返回 `None`，Part 通过 `get_part()` 读取。

## 4. 生命周期和数据流

### 4.1 各类的构造/初始化契约

下表是所有核心类的统一生命周期约定。表中的“记录”表示只写入定义字段；“建立”
表示可以读取外部数据并创建运行时对象。

| 类 | `__init__()` 只记录 | `initialize()` 建立 |
|---|---|---|
| `Controller` | 参数对象、求解器配置、路径和运行选项 | `Params`、`Solver`、`ObjectiveFunction`、`Updaters` 的完整运行时关系 |
| `Params` | Geometry、Materials、FEA 的处理器工厂 | 三个子系统的引用；当前 `Assembly` 由 `build_assembly()` 建立 |
| `GeometryParams` | `parts`、`reference_points` 注册表和用户定义顺序 | 所有 `Part`、`Instance`、ReferencePoint、源数据缓存、元素名称校验和名称索引 |
| `BasePartDefinition` | `part_name`、必填元素名称集合、`exterior_surface`、`Instance` 定义和源参数 | `Part` 拓扑、节点、元素、曲面和运行时缓存 |
| `InstanceDefinition` | 名称、平移、旋转 | 变换矩阵和 `Assembly` `Instance` 注册信息 |
| `ReferencePoint` | 名称和三维坐标 | 名称与坐标校验；TorchFEA 参考点由 `build_reference_point()` 建立 |
| `BoundaryPart` | 曲面定义、必填 `element_name`、边界参数、网格参数和代码槽 | 曲面对象、几何网格和几何映射缓存 |
| `BaseSurfaceInterface` / 具体曲面类 | 曲面参数、控制点和代码槽 | 曲面对象、采样点和几何数据缓存 |
| `INPPart` | 输出 `part_name`、INP 路径、源 Part、可选 `element_names` 和实例选择 | INP 源 Assembly、一个输出 Part 和实例定义 |
| `TorchFEAPart` | 输出 `part_name`、模型目录、文件名、源 Part、可选 `element_names` 和实例选择 | 模型摘要、源 Assembly、一个输出 Part 和实例定义 |
| `OffsetShellPart` | 源 `Part` 名称、必填 `solid_element_name`、`shell_element_name`、`source_surface`、偏置厚度、层数和操作记录 | 源边界、向内偏置节点/元素和 `surface_{i}_offset` 曲面 |
| `MaterialsParams` | 材料对象注册表和按 `Part` 的索引 | 从 `Assembly` 解析 `Part`/element 目标、覆盖校验和材料接口绑定 |
| `MaterialParameters` | 本构参数字段 | 由 `MaterialsParams` 校验，并在材料创建阶段生成 TorchFEA 本构 |
| `BaseMaterialInterface` | `part_name`、`element_name`、`density` 和公共配置 | 目标元素缓存及接口运行时状态 |
| `HomogeneousMaterial` | 均匀本构参数对象 | 创建并写入均匀 TorchFEA 材料 |
| `SIMPFieldMaterial` | BSP 参数、初始设计场和材料场配置 | 控制点 Tensor、材料场映射和元素写回缓存 |
| `FEAParams` | FEA component 和 load step 定义 | `Assembly` 目标解析、基础组件引用、逐工况 Assembly 与组件副本 |
| `LoadStep` | 工况值和 step 顺序 | step 索引和组件值向量 |
| `BaseFEAComponent` | 目标名称、初始值和公共选项 | 目标集合缓存和 TorchFEA 组件上下文 |
| 具体 FEA component | 自身参数、目标 `Instance`/Surface/Set 名称 | 具体 TorchFEA 载荷、边界或接触对象 |
| `Solver` | 进程、设备、任务组和求解选项 | task groups、设备上下文和逐工况 TorchFEA 求解器 |
| `ObjectiveFunction` | 指标名称、工况权重和 Jacobian 名称 | 静态引用校验；每轮逐工况 `FEAController` 和结果上下文由 `reinitialize()` 绑定 |
| `SensitivityAnalyzer` | 数值容差 | 绑定 Objective、Registry、FEA 工况集合和试探模型更新入口，建立多工况总灵敏度 |
| `LocalSensitivityObjective` | updater 局部线性目标协议 | 各 updater 根据顶层目标分发的局部灵敏度建立的运行时目标 |
| updater 内部约束回调 | 对应 updater 的局部约束参数 | 对应 updater 的不等式/罚函数和等式投影计算上下文 |
| `History` | 结果根目录和指标名称 | 结果目录、schema 和当前历史缓存 |
| `DesignKey` | 类别和目标稳定名称 | 直接作为稳定标识使用 |
| `DesignBlock` | `key`、`owner` 和变量范围记录 | 由 `DesignRegistry` `finalize()` 后确定 `offsets` |
| `DesignRegistry` | 空的变量块列表和注册规则 | 收集所有 `owner`、计算 `offsets`、冻结变量顺序并建立完整设计增量 |
| `BaseUpdater` | 优化器、步长和灵敏度缩放配置 | 绑定 owner、接收局部灵敏度、建立 `LocalSensitivityObjective` 和创建优化器状态 |
| `BaseGeometryUpdater` | 几何更新公共配置 | 提供几何 updater 的公共生命周期 |
| `BoundaryPartUpdater` | `BoundaryPart` 目标、固定局部灵敏度目标和本 updater 的等式/局部约束回调 | 解析一个 `BoundaryPart` 并准备边界几何优化器 |
| `OffsetShellPartUpdater` | `OffsetShellPart` 目标、固定局部灵敏度目标和本 updater 的等式/局部约束回调 | 解析一个 `OffsetShellPart` 并准备偏置几何优化器 |
| `MaterialUpdater` | 材料目标、固定局部灵敏度目标、本 updater 的局部约束回调和材料正则项 | 解析目标材料并准备材料优化器 |
| `FEAUpdater` | component 名称、工况索引和本 updater 的局部约束回调 | 解析 `LoadValueBlock` 并准备载荷优化器 |
| `UpdaterEntry` | updater 名称、目标名称和 updater 对象 | 由 `Updaters` 绑定真实 owner |
| `Updaters` | updater entry 注册表 | 目标解析、变量注册和 updater 调度关系；每个 owner 唯一绑定一个 updater |
| UI `ProblemDefinition` | 编辑树和节点定义 | 生成可运行的 `Params` 定义或加载定义状态 |
| UI 各类 Node | 表单字段、类型标签和代码槽 | 解析字段并生成对应定义对象 |
| `CodeGenerator` | 模板和代码槽配置 | 载入模板资源并生成任务 Python 源码 |

### 4.2 `Controller` 初始化

~~~text
Controller.initialize()
    1. 取得当前 Python 任务定义
    2. Params.initialize()
       2.1 GeometryParams.initialize()
       2.2 MaterialsParams.initialize()
       2.3 FEAParams.initialize()
    3. Solver.initialize(num_steps)
    4. DesignRegistry.initialize(params)
       4.1 收集 geometry、material 和 FEA 设计变量
       4.2 finalize 并冻结变量顺序
       4.3 owner.build_design_delta()
       4.4 建立完整设计向量
    5. 根据 DesignRegistry.has_geometry_variables() 设置 GC 复用策略
    6. ObjectiveFunction.initialize(FEAParams)
    7. SensitivityAnalyzer.initialize(ObjectiveFunction, DesignRegistry, FEAParams, trial_updater)
    8. Updaters.initialize(params, registry)
    9. History.initialize()
    10. 创建 worker pool 并标记 Controller 已初始化
~~~

`Controller.__init__()` 和任务定义类的构造过程产生声明对象。`Controller.initialize()`
建立静态运行时关系和资源；`step()` 按当前 iteration 建立 Assembly、求解结果和灵敏度，
`_opt_loop()` 接续记录和调度优化迭代。

### 4.3 一次外层迭代

~~~text
Controller._opt_loop()
    ├─ Controller._clear_runtime_cache()
    ├─ Controller.step(iteration)
    │   ├─ Params.reinitialize(iteration)
    │   ├─ Params.build_assembly()
    │   ├─ DesignRegistry.reinitialize(iteration)
    │   ├─ DesignRegistry.build_design_delta()
    │   ├─ Controller._update_trial_assemblies(delta)
    │   │   ├─ DesignRegistry.update_assembly(delta, {"geometry", "material"})
    │   │   ├─ FEAParams.build_case_assemblies()
    │   │   └─ DesignRegistry.update_assembly(delta, {"load"})
    │   ├─ case_assemblies = FEAParams.get_case_assemblies()
    │   ├─ Controller.build_fea_controllers()
    │   ├─ Solver.reinitialize(iteration)
    │   ├─ Solver.build_solvers(fea_controllers)
    │   ├─ Solver.solve(fea_controllers, jacobian_names)
    │   ├─ ObjectiveFunction.reinitialize(iteration, fea_controllers, results)
    │   ├─ ObjectiveFunction.build_evaluation()
    │   ├─ SensitivityAnalyzer.build_sensitivities()
    │   ├─ Updaters.reinitialize(iteration, local_gradients)
    │   └─ Updaters.update()
    ├─ ObjectiveFunction.export_case_result(...) × num_cases
    ├─ History.add_record(HistoryRecord)
    ├─ Controller.save(...)
    └─ 检查停止、收敛和重启条件
~~~

### 4.4 `Assembly` 的获取

`GeometryParams` 使用两个显式方法：

| 方法 | 返回值 | 来源 | 行为 |
|---|---|---|---|
| `build_assembly(path_result, pools)` | `None` | - | 按当前 `Part` 状态构建本轮 `Assembly`，写入内部的当前 `Assembly` |
| `get_assembly()` | `torchfea.Assembly` | - | 读取最近一次 `build_assembly()` 生成并保持原状态的 `Assembly` |

`build_assembly()` 更新 `GeometryParams` 内部的当前 `Assembly`，返回值为 `None`。
`get_assembly()` 在当前迭代尚未生成 `Assembly` 时抛出 `RuntimeError`。

### 4.5 用户代码与任务定义

Python 任务文件是任务定义的唯一来源。用户自定义的 `Part`、曲面、updater 约束、目标
函数、材料场、FEA component 和 updater 都在任务文件或可导入模块中定义，运行时从
任务文件重新创建对象并调用 `initialize()`。

UI 中的代码槽记录为源码文本，`CodeGenerator` 将源码写入生成的 Python 任务文件。
用户手写的类和方法直接保留在自己的模块中。方法、闭包、lambda 和局部类属于任务
代码的一部分；运行时模型输入由任务文件和外部数据共同构成。

任务的可重复运行依赖任务 Python 文件、外部输入文件、依赖版本和运行配置。迭代过程
只记录日志、指标和结果文件；新的运行从任务定义文件重新开始。
