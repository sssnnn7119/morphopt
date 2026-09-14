
# MorphOpt 统一模型架构设计文档

> 状态：完整设计稿，当前只规划，不修改现有实现。
>
> 本文只定义最终对象模型、实例属性、方法、调用关系、数据流和模块边界。
> 实现阶段按本文接口执行，不增加旧 API 兼容层。

## 1. 设计目标

MorphOpt 统一使用一个模型定义空间：

~~~text
GeometryParams
    Parts + Instances
        ↓
    torchfea.Assembly
        ↓
MaterialsParams
    Part / element_name → MaterialInterface
        ↓
FEAParams
    loads + boundary conditions + contacts + load steps
        ↓
Solver
    StaticResult[step]
        ↓
ObjectiveFunction + DesignRegistry
        ↓
Updaters
    registered updater entries
~~~

用户可以自由组合：

- `BoundaryPart`、`INPPart`、`TorchFEAUIPart` 和 `OffsetShellPart`；
- 一个 `Part` 的多个 `Instance` 和独立变换；
- `HomogeneousMaterial`、`SIMPFieldMaterial` 以及未来的材料场接口；
- 多个几何 `Part` 和多个材料分配；
- 固定 FEA、纯几何优化、纯材料优化和几何/材料联合优化；
- 未来的载荷设计变量和 `FEAUpdater`。
- 任务定义对象的构造函数只记录构造状态，运行时对象统一在 `initialize()` 阶段建立；

shapeopt、simp 和 codesign 只作为 UI 模板和示例组合，不再作为底层模型分支。

## 2. 总体规则

### 2.1 名称体系

| 名称 | 所属对象 | 使用位置 |
|---|---|---|
| part_name | `Part` 实例属性 | Geometry、Materials、`GeometryUpdater` |
| instance_name | `Instance` 实例属性 | FEA component、结果显示 |
| element_name（普通 Part） | `BasePartDefinition` 构造属性 | 普通 `Part` 生成或导入的元素名称，构造时必填 |
| solid_element_name | `OffsetShellPart` 构造属性 | 偏置壳实体部分的元素名称，构造时必填 |
| shell_element_name | `OffsetShellPart` 构造属性 | 偏置壳壳部分的元素名称，构造时必填 |
| element_name（材料） | `BaseMaterialInterface` 构造属性 | 选择目标 `Part.elems`；空字符串表示全选 |
| material_name | `MaterialAssignment` | `MaterialUpdater` |
| fea_component_name | `FEAParams` | load steps 和 Jacobian |
| updater_name | `UpdaterEntry` | 日志和 UI |

普通 `Part` 的 `element_name` 构造时必填，不允许默认值。`OffsetShellPart` 同时
构造实体和壳两组元素，因此分别使用必填的 `solid_element_name` 和
`shell_element_name`，两个名称必须不同。材料接口的 `element_name` 可以为空，
空字符串表示目标 `Part` 的全部 `elems`。UI 的材料全选项代码值为空字符串。

### 2.2 属性和所有权

每个 `Part`、材料接口、FEA component 和 updater 都是独立的实例对象。运行时状态
写入对象实例属性，不使用 ClassVar 共享 `Part` 名称、控制点、梯度或当前缓存。

类级属性只定义类型级常量，例如材料参数类的 material_class。

每个类的状态分为三栏，文档中的属性表按以下规则书写：

| 属性栏 | 存储形式 | 用途 | 对外访问规则 |
|---|---|---|---|
| 构造属性 | 私有实例属性，例如 `_part_name`、`_element_name` | 保存用户在 `__init__()` 中给出的定义、注册关系和构造参数 | 不直接暴露；需要使用时通过同名 `property` 读取 |
| 运行时属性 | 私有实例属性，例如 `_assembly`、`_mesh`、`_optimizer` | 保存 `initialize()`、`build_assembly()` 和求解过程中产生的缓存 | 不直接暴露；只通过明确的只读 `property` 或公开方法读取 |
| 属性接口（property） | `@property` 及必要的 setter | 提供稳定的对外观察和受控修改入口 | 每一项明确标注读权限和写权限 |

构造属性和运行时属性栏中的名称使用实际私有字段名，并以 `_` 开头。属性接口栏
使用对外名称，例如 `_part_name` 对应 `part_name`。字典、列表和可变 Tensor 通过
property 返回只读视图、不可变副本或 detached clone，不能让调用方绕过注册方法直接
修改内部状态。需要改变定义状态时调用 `add_part()`、`add_material()`、
`add_updater()` 等公开方法；需要改变运行时状态时调用 `set_parameters()`、
`apply_design_delta()`、`reinitialize()` 等公开方法。

属性接口表的权限使用以下含义：

| 权限 | 含义 |
|---|---|
| 只读 | 可以读取 property，不能通过 property 赋值 |
| 读写 | 可以读取和赋值；setter 负责校验并维护相关索引 |
| 不提供 | 不暴露该内部状态；通过公开方法取得结果 |

方法表也分为两类：

| 方法栏 | 命名规则 | 调用者 | 说明 |
|---|---|---|---|
| 外部接口方法 | 不使用前导 `_` | 其他对象、任务定义类、updater、UI、求解器或后处理 | 组成类的稳定调用接口；协议方法也放在这里，并保留协议来源列 |
| 内部辅助函数 | 使用一个前导 `_` | 仅本类内部 | 完成拆分、缓存、格式转换和后端对象创建等辅助工作，不作为跨对象接口 |

每个类的方法部分固定包含“外部接口方法”和“内部辅助函数”两张表。某一类没有
内部辅助函数时，在第二张表中写“无”。方法的可见性由名称确定，不通过调用方约定。

### 2.3 事实来源

| 数据 | 唯一事实来源 |
|---|---|
| `Part` 注册关系 | `GeometryParams.parts` |
| 材料注册关系 | `MaterialsParams.materials` |
| FEA component | `FEAParams.fea_components` |
| 设计变量顺序 | `DesignRegistry.blocks`：先 geometry，再 material，最后 load；各类别内部按目标名称字典序 |
| updater 目标绑定 | `Updaters` 的 entry 字典 |

索引和摘要由上述事实来源生成，运行时不维护第二份可编辑关系。

### 2.4 定义数据和运行时对象

定义对象记录“如何构造”的状态：名称、路径、参数、目标名称、`Instance` 变换、
材料参数、优化配置和用户代码槽。构造函数只写入这些状态，不执行完整构造。它们
可以在没有 `Assembly`、`FEAController`、
TorchFEA 材料对象、GPU Tensor、进程池和 UI widget 的情况下创建。

运行时对象和派生缓存只在 `initialize()`、`build_assembly()` 或 `create_feamodel()` 中
建立。运行时字段使用实例属性维护；例如 `_assembly`、`_part`、`_cps`、元素映射、
FEA 缓存和 worker pool 都不是任务定义本身。

每个类的属性表明确分为三组。构造属性由 `__init__()` 接收并写入私有字段，用于
注册、引用和记录构造方式；运行时属性也在 `__init__()` 中显式声明为私有字段，但
初始值统一为 `None`、空容器或 `False`，由 `initialize()` 填充或替换；属性接口栏
列出真正对外的 property、读权限和写权限。这样可以在不执行重计算的情况下完整查看
对象定义，同时避免外部直接改写内部状态。

### 2.5 构造记录和初始化结果

所有主要类遵循同一条边界：

| 阶段 | 允许的工作 | 结果 |
|---|---|---|
| `__init__()` | 只写入构造状态、创建空的 dict/list、记录用户定义顺序和代码槽 | 轻量定义对象 |
| `initialize()` | 读取源文件、解析跨对象名称、建立反向引用、创建缓存、分配运行时 Tensor、构造 TorchFEA 对象、完成完整校验 | 完整构造后的运行时对象 |
| `build_assembly()` / `create_feamodel()` | 根据当前设计变量生成本迭代 `Assembly`、材料和 FEA 模型 | 当前迭代模型 |
| `reinitialize()` | 清理或刷新当前迭代缓存，准备下一次求解 | 下一迭代的运行时状态 |

构造函数只做廉价的字段类型和局部值检查。以下工作统一延迟到
`initialize()`：INP 或 TorchFEA 文件读取、网格和曲面构建、`Part`/`Instance` 解析、
材料元素映射、GPU 数据分配、进程池创建、FEA 模型创建、设计变量注册和 updater
目标绑定。`initialize()` 必须可重复调用；重复调用先清理旧的运行时缓存，再根据
定义状态重新建立它们。

任务类中的 `define_parts()`、`define_materials()`、`define_fea_components()` 和
`define_updaters()` 可以在构造阶段被调用，但这些函数只能注册定义对象和记录
参数。它们不读取源文件、不访问 `Assembly`，也不创建求解器、Tensor 场或优化器。

## 3. 核心类清单

| 模块 | 类 | 一条对象表示什么 |
|---|---|---|
| 基础设施 | `Visualizable` | 可视化对象的 `get_meshes()` 协议 |
| 基础设施 | `Initializable` | 延迟建立运行时对象和缓存的生命周期协议 |
| 基础设施 | `Persistable` | 迭代状态和历史数据的 `save()` / `load()` 协议 |
| 基础设施 | `Updatable` | 可优化对象的增量读取、Assembly 试探更新和正式提交协议 |
| 总参数 | `Params` | 一个完整 FEA/优化问题 |
| 几何 | `GeometryParams` | `Part` 集合和当前 `Assembly` |
| 几何 | `BasePartDefinition` | 一个 `Part` 的公共状态和生命周期 |
| 几何 | `InstanceDefinition` | 一个 `Instance` 的名称和变换 |
| 几何 | `BoundaryPart` | 由边界曲面生成的 `Part` |
| 几何 | `INPPart` | 从 INP 导入的 `Part` |
| 几何 | `TorchFEAUIPart` | 从 TorchFEA UI 导入的 `Part` |
| 几何 | `OffsetShellPart` | 由边界 `Part` 生成偏置壳的 `Part` |
| 几何 | `BaseSurfaceInterface` / 具体曲面类 | 一个可注册到 `Part` 的曲面定义 |
| 材料 | `MaterialsParams` | 材料分配集合和覆盖校验 |
| 材料 | `MaterialAssignment` | 材料名称、目标 `Part` 和接口 |
| 材料 | `MaterialModels` | 本构参数类命名空间 |
| 材料 | `BaseMaterialInterface` | 材料接口公共生命周期 |
| 材料 | `HomogeneousMaterial` | 固定均匀材料接口 |
| 材料 | `SIMPFieldMaterial` | SIMP/BSP 材料场接口 |
| FEA | `FEAParams` | FEA component 和 load step |
| FEA | `LoadStep` / `ReferencePoint` | 工况和参考点定义 |
| FEA | `BaseFEAComponent` | 载荷/边界/接触公共生命周期 |
| 求解 | `Solver` | 多工况、多进程 FEA 求解 |
| 目标 | `ObjectiveFunction` | 目标、指标和灵敏度 |
| 历史 | `History` | 迭代目标、指标和时间记录 |
| 变量 | `DesignKey` | 一个变量块的稳定名称 |
| 变量 | `DesignBlock` | 变量块的范围和拥有者 |
| 变量 | `DesignRegistry` | 变量注册、切分、Assembly 试探更新和正式提交 |
| 更新 | `BaseUpdater` | 一块变量的更新策略 |
| 更新 | `GeometryUpdater` | 一个 `Part` 的更新策略 |
| 更新 | `MaterialUpdater` | 一个材料接口的更新策略 |
| 更新 | `FEAUpdater` | 一个 FEA component 的更新策略 |
| 更新 | `Updaters` | 任意数量 updater 的注册和调度 |
| 运行 | `Controller` | 初始化、求解和迭代循环 |

### 3.1 协议和显式继承关系

协议分为共同生命周期协议和可更新能力协议。所有需要运行时管理的对象按职责继承
`Visualizable`、`Initializable`、`Persistable`；有设计变量的具体对象再继承
`Updatable`。`build_assembly()`、`assign_material()` 和 `create_fea()` 是三个
领域基类自身的抽象核心方法，不再单独建立协议。
协议集中定义在 `optcore/protocols.py`。

协议本身只规定方法，不保存对象状态；协议对应的运行时属性由实现类在
`__init__()` 中显式声明。

方法命名统一区分可调用接口和内部实现：供其他对象、任务定义类、updater、UI 或
后处理调用的方法不使用前导下划线；只服务于本类内部流程的辅助方法使用一个前导
下划线，例如 `_register_surface_sets()`、`_create_bsp_model()`。方法表中带有前导
下划线的方法不作为跨对象调用接口。

#### 共同协议

| 协议 | 必需方法 | 继承者 |
|---|---|---|
| `Visualizable` | `get_meshes()` | `BasePartDefinition`、`BaseMaterialInterface`、`BaseFEAComponent` |
| `Initializable` | `initialize()`、`reinitialize(iteration)` | 所有需要建立或刷新运行时状态的定义基类和管理类 |
| `Persistable` | `save(foldpath, iteration)`、`load(foldpath, iteration)` | 需要保存迭代状态或读取历史数据的对象 |
| `Updatable` | `get_parameters()`、`set_parameters()`、`get_design_delta()`、`update_assembly()`、`apply_design_delta()` | 有设计变量的具体几何、材料或 FEA component |

三个领域基类采用显式继承：

| 基类 | 继承的协议 | 领域职责 |
|---|---|---|
| `BasePartDefinition` | `Visualizable`、`Initializable`、`Persistable` | 记录 Part 定义、生成 TorchFEA Part、提供几何预览 |
| `BaseMaterialInterface` | `Visualizable`、`Initializable`、`Persistable` | 记录材料定义、写入元素材料、提供材料预览 |
| `BaseFEAComponent` | `Visualizable`、`Initializable`、`Persistable` | 记录载荷定义、创建 FEA 对象、提供载荷预览 |

三个参数集合和总参数对象也显式继承 `Visualizable`、`Initializable`、`Persistable`，负责记录定义
状态并聚合下属对象的预览结果。`GeometryParams` 另外继承 `Updatable`，提供几何
设计增量的集合级委托接口；`Params`、`MaterialsParams` 和 `FEAParams` 不继承
`Updatable`：

| 类 | 继承的协议 |
|---|---|
| `Params` | `Visualizable`、`Initializable`、`Persistable` |
| `GeometryParams` | `Visualizable`、`Initializable`、`Persistable`、`Updatable` |
| `MaterialsParams` | `Visualizable`、`Initializable`、`Persistable` |
| `FEAParams` | `Visualizable`、`Initializable`、`Persistable` |

其他具有完整运行时建立阶段的管理类也显式继承 `Initializable`：

| 类 | 继承的协议 |
|---|---|
| `Controller` | `Initializable`、`Persistable` |
| `Solver` | `Initializable`、`Persistable` |
| `ObjectiveFunction` | `Initializable`、`Persistable` |
| `DesignRegistry` | `Initializable`、`Persistable` |
| `BaseUpdater` | `Initializable`、`Persistable` |
| `Updaters` | `Initializable`、`Persistable` |
| `History` | `Persistable` |

#### 可更新对象

`Updatable` 是跨几何、材料和 FEA 的可选公共协议。它表示对象拥有一块可被
`DesignRegistry` 管理的设计变量，并且能够接收变量更新。三个领域基类不继承
`Updatable`，由具体类根据自身是否可变显式继承：

| 类 | 是否继承 `Updatable` | 状态 |
|---|---|---|
| `GeometryParams` | 是 | 几何集合级增量委托 |
| `BoundaryPart` | 是 | 几何变量可更新 |
| `OffsetShellPart` | 是 | 偏置几何可更新 |
| `SIMPFieldMaterial` | 是 | 材料场可更新 |
| 可设计的具体 FEA component | 是 | 载荷或边界参数可更新 |
| `INPPart` | 否 | 固定导入几何 |
| `TorchFEAUIPart` | 否 | 固定导入几何 |
| `HomogeneousMaterial` | 否 | 固定均匀材料 |
| 固定载荷组件 | 否 | 固定载荷、边界或接触 |

`GeometryParams` 的 `Updatable` 实现是集合级委托接口：可以把整个几何集合视为一个
设计块，也可以由 `DesignRegistry` 直接注册各个可更新 `Part`，此时集合方法只负责
按 `part_name` 分发调用，不重复注册子对象。

`Updatable` 定义两组方法：

| 方法 | 来源 | 作用 |
|---|---|---|
| `get_parameters()` | - | 直接导出 owner 的内部参数，返回 detached clone |
| `set_parameters(parameters)` | - | 将参数快照以 detached clone 写回 owner 的内部状态 |
| `get_design_delta()` | - | 返回全 0 的设计增量 Tensor，保留 autograd，作为子优化问题的变量 |
| `update_assembly(assembly, design_delta)` | - | 将设计增量映射到已有 `Assembly`，保留计算图并用于试探计算 |
| `apply_design_delta(design_delta)` | - | 将优化器输出的设计增量映射并正式写回 owner 状态 |

没有设计变量的对象不继承 `Updatable`，也不进入 `DesignRegistry`。因此“不可更新”
不是特殊的空实现，而是类型层面的明确状态。这里的不可更新表示优化循环不向该
对象写入变量；对象仍然可以在初始化和迭代阶段维护自己的运行时缓存。

`Initializable` 定义统一的 `initialize()` 和 `reinitialize(iteration)` 生命周期入口。
领域基类在其中调用自己的初始化步骤，参数集合在其中初始化下属对象并建立跨对象引用，
再通过 `reinitialize()` 刷新当前 iteration 的运行时状态。具体实现可以根据领域需要
接收初始化上下文，但初始化职责和调用时机统一由该协议表达。

`Persistable` 定义统一的迭代状态和历史数据 I/O 入口。`save()` 写入当前对象负责的
状态或结果，`load()` 从指定 iteration 读取数据。每个类明确自己的字段和文件内容，
不通过一个通用恢复器重建用户类、用户方法或闭包。

### 3.2 协议调用关系

三个管理器直接调用领域基类的核心方法：

~~~text
GeometryParams
    → BasePartDefinition.build_assembly()

MaterialsParams
    → BaseMaterialInterface.assign_material()

FEAParams
    → BaseFEAComponent.create_fea()
~~~

可视化统一调用 `Visualizable.get_meshes()`。可更新对象统一由 `Updatable` 交给
`DesignRegistry` 管理，用户定义类通过显式继承表达自己的可变能力。固定对象只参与
构建和可视化。

`get_parameters()` 和 `set_parameters()` 用于保存、恢复以及子优化过程中的状态切换；
它们始终使用 detached clone。设计优化始终使用 `get_design_delta()`、
`update_assembly()` 和 `apply_design_delta()`。`build_assembly()` 只负责根据当前定义
创建新的 TorchFEA `Part` 或 `Assembly`，不属于 `Updatable` 协议，也不替代
`update_assembly()` 的已有模型试探更新。

## 4. 生命周期和数据流

### 4.1 各类的构造/初始化契约

下表是所有核心类的统一生命周期约定。表中的“记录”表示只写入定义字段；“建立”
表示可以读取外部数据并创建运行时对象。

| 类 | `__init__()` 只记录 | `initialize()` 建立 |
|---|---|---|
| `Controller` | 参数对象、求解器配置、路径和运行选项 | `Params`、`Solver`、`ObjectiveFunction`、`Updaters` 的完整运行时关系 |
| `Params` | Geometry、Materials、FEA 的定义对象 | 三个子系统的引用、初始 `Assembly`、初始 `FEAController` |
| `GeometryParams` | `parts` 注册表和用户定义顺序 | 所有 `Part`、`Instance`、源数据缓存、元素名称校验和名称索引 |
| `BasePartDefinition` | `part_name`、必填元素名称集合、`exterior_surface`、`Instance` 定义和源参数 | `Part` 拓扑、节点、元素、曲面和运行时缓存 |
| `InstanceDefinition` | 名称、平移、旋转 | 变换矩阵和 `Assembly` `Instance` 注册信息 |
| `BoundaryPart` | 曲面定义、必填 `element_name`、边界参数、网格参数和代码槽 | 曲面对象、几何网格和边界约束缓存 |
| `BaseSurfaceInterface` / 具体曲面类 | 曲面参数、控制点和代码槽 | 曲面对象、采样点和约束缓存 |
| `INPPart` | INP 路径、源 `Part` 名称、必填 `element_name` 和导入选项 | INP 解析结果、节点、元素、集合和曲面 |
| `TorchFEAUIPart` | UI 导出文件路径、源 `Part` 名称、必填 `element_name` 和导入选项 | 导出模型、`Part` 数据和可用集合 |
| `OffsetShellPart` | 源 `Part` 名称、必填 `solid_element_name`、`shell_element_name`、偏置厚度、层数、方向和操作记录 | 源边界、偏置节点/元素和偏置曲面 |
| `MaterialsParams` | 材料分配记录和按 `Part` 的索引 | `Part`/element 目标解析、覆盖校验和材料接口绑定 |
| `MaterialAssignment` | 材料名称、目标 `Part` 名称和材料接口 | 目标 `Part`、元素族和运行时材料写入位置 |
| `MaterialParameters` | 本构参数字段 | 由 `MaterialsParams` 校验，并在材料创建阶段生成 TorchFEA 本构 |
| `BaseMaterialInterface` | `element_name`、`density` 和公共配置 | 目标元素缓存及接口运行时状态 |
| `HomogeneousMaterial` | 均匀本构参数对象 | 创建并写入均匀 TorchFEA 材料 |
| `SIMPFieldMaterial` | BSP 参数、初始设计场和材料场配置 | 控制点 Tensor、材料场映射和元素写回缓存 |
| `FEAParams` | FEA component、`ReferencePoint` 和 load step 定义 | `Assembly` 目标解析、组件引用和工况索引 |
| `LoadStep` / `ReferencePoint` | 工况值、step 顺序和参考点位置 | step 索引、自由度和 `Assembly` 引用 |
| `BaseFEAComponent` | 目标名称、初始值和公共选项 | 目标集合缓存和 TorchFEA 组件上下文 |
| 具体 FEA component | 自身参数、目标 `Instance`/Surface/Set 名称 | 具体 TorchFEA 载荷、边界或接触对象 |
| `Solver` | 进程、设备、任务组和求解选项 | task groups、设备上下文和 worker 资源 |
| `ObjectiveFunction` | 目标代码、指标代码和 Jacobian 名称 | FEA 引用、指标引用和灵敏度上下文 |
| `GeometryObjective/Constraint` | 几何目标和约束参数 | 目标数据和约束计算上下文 |
| `MaterialObjective/Constraint` | 材料目标和约束参数 | 材料场目标和约束计算上下文 |
| `LoadObjective/Constraint` | 载荷目标和约束参数 | 载荷变量目标和约束计算上下文 |
| `History` | 历史记录配置和已记录数值 | 当前运行的历史缓存 |
| `DesignKey` | 类别和目标稳定名称 | 不需要独立初始化 |
| `DesignBlock` | key、owner 和变量范围记录 | 由 `DesignRegistry` finalize 后确定 offsets |
| `DesignRegistry` | 空的变量块列表和注册规则 | 收集所有 owner、计算 offsets、冻结变量顺序 |
| `BaseUpdater` | 优化器参数、局部目标、约束和目标名称 | 绑定 owner、创建优化器状态和局部变量块 |
| `GeometryUpdater` | `Part` 目标名称和几何更新配置 | 解析目标 `Part` 并准备几何优化器 |
| `MaterialUpdater` | 材料目标名称和材料更新配置 | 解析目标材料并准备材料优化器 |
| `FEAUpdater` | FEA component 目标名称和载荷更新配置 | 解析目标组件并准备载荷优化器 |
| `UpdaterEntry` | updater 名称、目标名称和 updater 对象 | 由 `Updaters` 绑定真实 owner |
| `Updaters` | updater entry 注册表 | 目标解析、变量注册和 updater 调度关系；允许多个同类 updater |
| UI `ProblemDefinition` | 编辑树和节点定义 | 生成可运行的 `Params` 定义或加载定义状态 |
| UI 各类 Node | 表单字段、类型标签和代码槽 | 解析字段并生成对应定义对象 |
| `CodeGenerator` | 模板和代码槽配置 | 载入模板资源并生成任务 Python 源码 |

### 4.2 `Controller` 初始化

~~~text
Controller.initialize()
    1. 取得当前 Python 任务定义
    2. Params.initialize()
       2.1 GeometryParams.initialize()
       2.2 MaterialsParams.initialize(geometry)
       2.3 FEAParams.initialize(geometry)
       2.4 生成初始 Assembly 和 FEAController
    3. DesignRegistry.initialize(params)
       3.1 收集 geometry 变量并按 part_name 排序
       3.2 收集 material 变量并按 material_name 排序
       3.3 收集 load 变量并按 fea_component_name 排序
       3.4 finalize 并计算完整 offsets
    4. Updaters.initialize(params, registry)
    5. Solver.initialize(num_steps)
    6. ObjectiveFunction.initialize()
    7. 校验完整模型并标记 Controller 已初始化
~~~

`Controller.__init__()` 和任务定义类的构造过程只产生第 1 步所需的声明对象。
真正的文件读取、模型创建和资源申请集中在 `Controller.initialize()` 触发的链路
中。任务定义文件直接进入同一条初始化链路。

### 4.3 一次外层迭代

~~~text
Params.reinitialize(iteration)
    ↓
Params.create_feamodel(path_result, pools)
    Part → Instance → Assembly → Materials → FEAController
    ↓
Solver.solve(fe)
    ↓
ObjectiveFunction.compute_multistep_objective(results, assembly)
    ↓
ObjectiveFunction.sensitivity_analysis(registry)
    ↓
Updaters.reinitialize(iteration, gradients)
    ↓
changes = Updaters.update()
    ↓
记录 History 和当前 iteration 结果
    ↓
Controller.save(foldpath, iteration)
~~~

### 4.4 `Assembly` 的获取

`GeometryParams` 使用两个显式方法：

| 方法 | 返回值 | 来源 | 行为 |
|---|---|---|---|
| build_assembly(path_result, pools) | `torchfea.Assembly` | - | 按当前 `Part` 状态构建本轮 `Assembly` |
| get_assembly() | `torchfea.Assembly` | - | 读取最近一次 `build_assembly()` 生成的 `Assembly` |

`build_assembly()` 更新 `GeometryParams` 内部的当前 `Assembly`。`get_assembly()` 在
当前迭代尚未生成 `Assembly` 时抛出 RuntimeError。

### 4.5 用户代码与任务定义

Python 任务文件是任务定义的唯一来源。用户自定义的 `Part`、曲面、曲面约束、目标
函数、材料场、FEA component 和 updater 都在任务文件或可导入模块中定义，运行时从
任务文件重新创建对象并调用 `initialize()`。

UI 中的代码槽记录为源码文本，`CodeGenerator` 将源码写入生成的 Python 任务文件。
用户手写的类和方法直接保留在自己的模块中。方法、闭包、lambda 和局部类不作为
独立的任务状态文件，也不作为运行时模型的输入。

任务的可重复运行依赖任务 Python 文件、外部输入文件、依赖版本和运行配置。迭代过程
只记录日志、指标和结果文件；新的运行从任务定义文件重新开始。

## 5. 几何类定义

### 5.1 `GeometryParams`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_parts` | dict[str, `BasePartDefinition`] | {} | 按注册顺序记录 `Part` |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _assembly | `torchfea.Assembly` 或 None | None | 最近生成的 `Assembly` |
| _element_names | dict[str, tuple[str, ...]] | {} | `part_name` 到已校验元素名称集合的派生索引 |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `parts` | Mapping[str, `BasePartDefinition`] | 只读 | 不提供 | 返回注册表的只读视图 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| define_parts() | None | - | 用户注册 `Part` 的扩展点 |
| add_part(part) | None | - | 使用 part.part_name 注册 `Part`，并校验元素名称集合非空 |
| get_part(part_name) | `BasePartDefinition` | - | 按名称取得 `Part` |
| build_assembly(path_result, pools) | `torchfea.Assembly` | - | 构建所有 `Part` 和 `Instance` |
| get_assembly() | `torchfea.Assembly` | - | 读取最近生成的 `Assembly` |
| initialize() | None | `Initializable` | 初始化并校验所有 `Part`、元素名称集合和 `Instance` |
| reinitialize(iteration) | None | `Initializable` | 调用每个 `Part` 的迭代刷新 |
| get_parameters() | list[torch.Tensor] | `Updatable` | 导出所有几何参数的 detached clone |
| set_parameters(parameters) | None | `Updatable` | 导入所有几何参数的 detached clone |
| get_design_delta() | torch.Tensor | `Updatable` | 按 `part_name` 字典序拼接几何设计增量 |
| update_assembly(assembly, design_delta) | None | `Updatable` | 将增量分发给各个可更新 `Part`，保留计算图 |
| apply_design_delta(design_delta) | None | `Updatable` | 将增量分发给各个可更新 `Part` 并正式提交 |
| get_meshes() | list[object] | `Visualizable` | 收集所有 `Part` 的预览网格 |
| save(foldpath, iteration) | None | `Persistable` | 保存几何状态和相关结果 |
| load(foldpath, iteration) | None | `Persistable` | 加载几何状态和相关结果 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

add_part 只接收 `Part` 对象，名称来源只有 part.part_name。
`GeometryParams.update_assembly()` 和 `GeometryParams.apply_design_delta()` 是
集合级委托方法：它们按 `part_name` 字典序切分完整增量，分别调用各 `Part` 的
`update_assembly()` 或 `apply_design_delta()`。`GeometryParams.build_assembly()` 负责
创建新的 `Assembly`，不参与已有模型的可微更新。

### 5.2 `BasePartDefinition`

这是所有 `Part` 类型的共同基类，显式继承 `Visualizable`、`Initializable` 和
`Persistable`，维护一个 `Part` 的实例属性和生命周期。`build_assembly()` 是该基类
定义的抽象核心方法，由具体 `Part` 类型实现。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_name` | str | 构造函数必填 | `Part` 唯一名称 |
| `_element_names` | tuple[str, ...] | 构造函数必填 | 当前 `Part` 生成或导入的元素名称集合；至少一个 |
| `_exterior_surface` | str | `'extern'` | `Part` 级外表面集合名称；由具体 `Part` 定义 |
| `_instances` | dict[str, `InstanceDefinition`] | {} | `Instance` 定义集合 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _part | `torchfea.Part` 或 None | None | 最近生成的 TorchFEA `Part` |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `part_name` | str | 只读 | 不提供 | 返回稳定的 `Part` 名称 |
| `element_names` | tuple[str, ...] | 只读 | 不提供 | 返回已声明的元素名称集合 |
| `exterior_surface` | str | 只读 | 读写 | setter 校验并更新整体 surface set 名称 |
| `instances` | Mapping[str, `InstanceDefinition`] | 只读 | 不提供 | 返回 `Instance` 的只读视图 |
| `part` | `torchfea.Part` 或 None | 只读 | 不提供 | 返回最近构建的 TorchFEA `Part` |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

构造属性和运行时属性都属于每个 `Part` 实例，不使用 ClassVar；运行时属性在构造
阶段先声明初始值，再由 `initialize()` 填充。

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| build_assembly(path_result, pools) | `torchfea.Part` | - | 创建当前 `Part` |
| get_parameters() | list[torch.Tensor] | - | 导出当前几何参数的 detached clone |
| set_parameters(parameters) | None | - | 导入几何参数的 detached clone |
| initialize() | None | `Initializable` | 初始化源数据、拓扑和缓存，并校验 element_names |
| reinitialize(iteration) | None | `Initializable` | 准备当前迭代数据 |
| get_meshes() | list[object] | `Visualizable` | 返回预览网格 |
| save(foldpath, iteration) | None | `Persistable` | 保存当前几何状态 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的几何状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 具体 Part 的内部辅助函数在具体子类中定义 |

`build_assembly()` 生成一个 TorchFEA `Part`；`GeometryParams.build_assembly()` 负责将 `Part` 和
Instances 放入 `Assembly`。需要参与形状优化的具体 `Part` 通过 `Updatable` 提供
Assembly 试探更新和正式提交方法；固定导入 `Part` 只实现构建和可视化。

`BasePartDefinition.element_names` 是该 `Part` 输出的 `elems` 名称集合。普通具体
`Part` 的构造函数接收一个必填 `element_name` 并形成单元素集合；
`OffsetShellPart` 接收必填的 `solid_element_name` 和 `shell_element_name` 并形成
两元素集合。`initialize()` 校验生成或导入结果中存在对应元素。
材料接口使用自己的 `element_name` 选择这些 `elems`；材料接口的空字符串仍表示
全选，不影响 `Part` 的必填规则。

对于 `INPPart` 和 `TorchFEAUIPart`，构造函数传入的 `element_name` 是该导入定义
对外暴露的元素名称；`initialize()` 负责检查源模型中的元素并完成名称映射。对于
`BoundaryPart`，它是新建元素集合在 `Part.elems` 中使用的名称；对于
`OffsetShellPart`，则分别使用 `solid_element_name` 和 `shell_element_name`。

### 5.3 `InstanceDefinition`

`InstanceDefinition` 是一个不可变数据对象。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | 必填 | `Assembly` 全局唯一名称 |
| `_translation` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 平移向量 |
| `_rotation` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 旋转向量 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

无运行时缓存。`InstanceDefinition` 只保存名称和变换，
`to_torchfea_instance()` 调用时创建 TorchFEA 对象。

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 不提供 | 返回实例名称 |
| `translation` | tuple[float, float, float] | 只读 | 不提供 | 返回平移向量 |
| `rotation` | tuple[float, float, float] | 只读 | 不提供 | 返回旋转向量 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| validate() | None | - | 校验名称和变换维度 |
| to_torchfea_instance(part) | `torchfea.Instance` | - | 创建 TorchFEA `Instance` |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

一个 `Part` 可以定义任意多个 `Instance`。所有 `Instance` 共享 `Part` 的网格和设计
变量。没有显式 `Instance` 时，创建一个与 part_name 同名的零变换 `Instance`。

### 5.4 `BoundaryPart`

`BoundaryPart` 由有序边界曲面集合生成可网格化的 TorchFEA `Part`，是形状优化的
基础类型，并显式继承 `Updatable`。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_name` | str | final_model | 形状优化默认名称 |
| `_element_name` | str | 构造函数必填 | 生成的单一 `Part.elems` 名称 |
| `_exterior_surface` | str | `'extern'` | `Part` 级整体外表面集合名称；该名称定义包含所有曲面全集面的集合 |
| `_instances` | dict[str, `InstanceDefinition`] | {} | `Instance` 集合 |
| `_surfaces` | list[`BaseSurfaceInterface`] | [] | 有序曲面集合 |
| `_fea_seed_size` | float | 由网格器确定 | 网格种子尺寸 |
| `_mesh_order` | int | 由网格器确定 | 网格阶数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _control_points | list[torch.Tensor] | [] | 曲面控制点 |
| _surface_sets | dict[str, object] | {} | 自动生成的各类 surface set 缓存 |
| _mesh | object 或 None | None | 当前网格缓存 |
| _part | `torchfea.Part` 或 None | None | 最近生成的 TorchFEA `Part` |
| _initialized | bool | False | 初始化状态 |

`BoundaryPart.initialize()` 按 `_surfaces` 的稳定顺序设置每个曲面的运行时参数方向，
然后再建立曲面后端和几何缓存。第一个曲面是参数方向基准，`flip=False`；从第二个
曲面开始统一使用 `flip=True`。`flip` 不由用户在曲面构造函数中单独指定，也不属于
持久化的构造参数。

| 曲面在 `_surfaces` 中的索引 | 初始化后的 `flip` | 约定 |
|---:|---:|---|
| `0` | `False` | 保持曲面原始的 `v` 参数方向 |
| `1, 2, ...` | `True` | 将曲面的 `v` 参数方向反向 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `surfaces` | tuple[`BaseSurfaceInterface`, ...] | 只读 | 不提供 | 返回有序曲面定义 |
| `surface_sets` | Mapping[str, object] | 只读 | 不提供 | 返回 surface set 的只读摘要 |
| `control_points` | tuple[torch.Tensor, ...] | 只读 | 不提供 | 返回控制点 detached clone |
| `mesh` | object 或 None | 只读 | 不提供 | 返回当前网格预览缓存 |
| `part_name` | str | 只读 | 不提供 | 返回形状优化 `Part` 名称 |
| `element_name` | str | 只读 | 不提供 | 返回生成的元素名称 |
| `fea_seed_size` | float | 只读 | 不提供 | 返回网格种子尺寸 |
| `mesh_order` | int | 只读 | 不提供 | 返回网格阶数 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| define_surfaces() | None | - | 用户按顺序注册曲面 |
| add_surface(surface) | None | - | 添加一个曲面接口 |
| apply_surface_constraints() | None | - | 应用局部等式/投影约束 |
| get_geometry_values() | torch.Tensor | - | 返回几何变量 |
| get_points_weight() | torch.Tensor | - | 返回控制点权重 |
| get_control_points_list() | list[torch.Tensor] | - | 返回控制点张量 |
| build_assembly(path_result, pools) | `torchfea.Part` | - | 生成网格和 TorchFEA `Part` |
| initialize() | None | `Initializable` | 按曲面序号设置 `flip`（第 0 个为 `False`，其余为 `True`），再初始化曲面和几何缓存 |
| reinitialize(iteration) | None | `Initializable` | 应用变量并准备重网格 |
| get_parameters() | list[torch.Tensor] | `Updatable` | 导出几何参数的 detached clone |
| set_parameters(parameters) | None | `Updatable` | 导入几何参数的 detached clone |
| get_design_delta() | torch.Tensor | `Updatable` | 返回全 0 的几何设计增量 |
| update_assembly(assembly, design_delta) | None | `Updatable` | 将试探增量映射到节点并保留计算图 |
| apply_design_delta(design_delta) | None | `Updatable` | 通过几何映射正式写回控制点 |
| get_meshes() | list[object] | `Visualizable` | 返回几何预览 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_register_surface_sets(part)` | None | 按曲面类型注册 surface set，并按 `exterior_surface` 命名整体外表面集合 |

任务文件在自己的 `GeometryParams` 内定义 `BoundaryPart` 子类。子类实现
define_surfaces 和 apply_surface_constraints，曲面类型使用 BSP、CPGEO、
STL 等命名空间访问。

每个 `BSPSurface` 在 `BoundaryPart` 中按其在 `surfaces` 列表中的索引 `i` 自动注册
四个 surface set：

| 名称 | 内容 |
|---|---|
| `surface_{i}_head` | BSP 顶部端面 |
| `surface_{i}_bottom` | BSP 底部端面 |
| `surface_{i}_lateral` | BSP 侧面 |
| `surface_{i}_all` | 顶面、底面和侧面的合集 |

`i` 使用曲面在 `BoundaryPart.surfaces` 中的稳定顺序，从 `0` 开始。上述名称属于
`Part` 的 surface set 注册表，供 FEA 载荷、边界条件、曲面约束和 UI 选择使用。
`_register_surface_sets(part)` 在网格生成后完成节点/面集合登记，并将
`surface_{i}_all` 组装为该 BSP 的三个局部面的合集。

每个 `CPGEOSurface` 只注册一个 `surface_{i}_all`，其内容是该 CPGEO 曲面的全部
三角面。CPGEO 不注册 `head`、`bottom` 或 `lateral` 面。

在上述集合之外，`BoundaryPart` 还注册一个整体 surface set。该集合的名称由
`exterior_surface` 定义，默认名称为 `extern`：

| 名称 | 内容 |
|---|---|
| `exterior_surface` 的值 | 所有曲面的 `surface_0_all + surface_1_all + ...` 合集 |

`BoundaryPart.exterior_surface` 是整体外表面 surface set 的定义名称，默认值为
`extern`。因此，`part.exterior_surface` 对应所有曲面登记的 `surface_{i}_all` 合集，
而不是某一个曲面的全集面。用户输入其他名称时，整体集合就使用该名称创建，
并同步写入 `part.exterior_surface`。该字段不引用固定的 `extern`，也不复制曲面数据。

### 5.4.1 曲面接口和具体曲面类型

本小节定义可以注册到 `BoundaryPart` 的曲面接口，以及各类曲面的专用参数和运行时
数据。曲面接口只负责几何数据、控制点、导数、权重和曲面网格；Fairness、曲率和
距离等约束由对应的 Geometry updater/evaluator 负责。

#### `BaseSurfaceInterface` 和具体曲面类

曲面对象也遵循构造属性和运行时属性的分离。具体曲面类只增加自己的参数字段，
公共缓存由基类维护。

曲面输出的 `SurfaceGeometryData` 是一次运行时计算结果，包含 `r`、`rdu`、`rdu2`
和 `weights`。它不属于构造状态，也不作为独立设计变量注册；`BoundaryPart` 统一
收集曲面控制点并向 `DesignRegistry` 提供几何设计变量。`evaluate_geometry()` 返回前
必须先应用当前运行时 `flip`，不能把方向修正留给调用方。

##### 构造属性（`__init__()` 记录）

曲面构造函数不接收 `flip`。曲面参数、控制点、采样尺寸、几何阈值和初始化方式由
具体曲面类型自己的构造属性记录；曲面方向属于 `initialize()` 阶段的运行时状态。

曲面名称由 `BoundaryPart` 根据曲面在 `surfaces` 中的索引统一生成。曲面方程、
控制点、采样尺寸、几何阈值和初始化方式由具体曲面类型自己的构造属性记录。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_flip` | bool | False | 当前 `v` 参数方向是否反向；由 `BoundaryPart.initialize()` 按曲面序号统一设置 |
| `_surf_node_idx` | `numpy.ndarray` 或 None | None | 曲面节点在 FEA 网格节点中的索引 |
| `_surf_node_uv` | `numpy.ndarray` 或 None | None | FEA 曲面节点对应的参数坐标 |
| _initialized | bool | False | 初始化状态 |

##### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `flip` | bool | 只读 | 不提供 | 返回当前运行时的 `v` 参数方向标志；不是独立的法向量开关 |
| `surf_node_idx` | `numpy.ndarray` 或 None | 只读 | 不提供 | 返回曲面节点索引的只读副本 |
| `surf_node_uv` | `numpy.ndarray` 或 None | 只读 | 不提供 | 返回节点参数坐标的只读副本 |
| `geometry_data` | `SurfaceGeometryData` 或 None | 只读 | 不提供 | 返回当前曲面几何数据 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| initialize() | None | `Initializable` | 根据具体曲面属性创建后端对象，并建立必要的参数映射与运行时几何缓存 |
| reinitialize(iteration) | None | `Initializable` | 刷新当前迭代的曲面数据 |
| build_surface() | object | - | 创建后端曲面对象 |
| evaluate_geometry() | `SurfaceGeometryData` | - | 返回当前曲面的点、导数和积分权重 |
| get_meshes() | list[object] | `Visualizable` | 返回曲面预览 |
| apply_constraints() | None | - | 应用曲面自身的约束或投影规则 |

`flip=True` 表示沿曲面参数域的 `v` 方向反向，而不是只把最终法向量乘以 `-1`。
对于任意参数导数 `r_{u^a v^b} = ∂^{a+b}r/(∂u^a∂v^b)`，反向规则统一为
`r_{u^a v^b} -> (-1)^b r_{u^a v^b}`。因此 `r_v`、`r_uv` 以及含奇数次 `v`
导数的项取反；`r_vv`、`r_uvv` 以及含偶数次 `v` 导数的项保持不变。当前一、
二阶几何数据中，`r_u` 和 `r_uu` 不变，`r_v` 与 `r_uv` 取反，`r_vv` 不变。
法向量由变换后的切向导数重新计算，不能把 `flip` 实现成单独的法向量后处理。
在当前张量布局中，`rdu[..., 0]` 和 `rdu[..., 1]` 分别表示 `r_u` 和 `r_v`；
`rdu2[..., 0, 1]`、`rdu2[..., 1, 0]` 表示 `r_uv`，`rdu2[..., 1, 1]` 表示
`r_vv`。应用 `flip` 时必须同步变换这些分量。

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

#### `CpBasedSurface` 共享状态

`BSPSurface` 和 `CPGEOSurface` 都使用控制点映射到采样点，因此共享以下运行时
属性。具体曲面的构造属性仍由各自的具体定义类记录。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _cps | `torch.Tensor` 或 None | None | 当前控制点张量 |
| _preload_data | `PreLoadData` 或 None | None | 参数点到控制点的映射缓存：参数坐标、零/一/二阶权重、控制点索引和面拓扑；供几何值快速求值 |

##### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `control_points` | torch.Tensor 或 None | 只读 | 不提供 | 返回控制点 detached clone |
| `preload_data` | `PreLoadData` 或 None | 只读 | 不提供 | 返回几何评估缓存的只读视图 |

`PreLoadData` 是控制点曲面的映射缓存，不是最终的几何结果。它包含 `uv`、
`cp_weights`、`cp_weights_du`、`cp_weights_dv`、
`cp_weights_du2`、`cp_weights_dudv`、`cp_weights_dv2`、`indices` 和 `faces`。
这些数据由 `initialize()` 或 `reinitialize()` 建立；`get_r()`、`get_rdu()` 和
`get_rdu2()` 只需使用缓存权重/索引对当前控制点做映射，就能快速得到点坐标和各阶
导数。控制点变化时通常复用这份参数映射缓存，不重复计算参数基函数权重；只有采样
网格或后端拓扑变化时才重建缓存。`_surf_node_uv` 仅表示 FEA 网格节点的参数坐标，
不替代 `PreLoadData`。

#### `BSPSurface`

`BSPSurface` 是 B-spline 曲面的共同类型，使用控制点和参数域定义连续曲面。
具体几何形状通过专门的定义类记录；例如圆柱使用 `BSPCylinderSurface`。

##### 本类型构造属性

`BSPSurface` 继承基类的运行时 `flip`，并使用 `CpBasedSurface` 的控制点和 preload
运行时状态。形状参数放在具体 BSP 定义中；几何导数按基类规定的 `v` 方向规则变换。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _model | object 或 None | None | BSP 后端对象 |
| `_rr_compensation` | `torch.Tensor` 或 None | None | Fairness 曲率项的补偿系数 |
| _preload_size | tuple[int, int] 或 None | None | preload UV 网格尺寸 |
| _geometry_data | `SurfaceGeometryData` 或 None | None | 当前点、导数和权重 |
| _mesh | object 或 None | None | 当前可视化网格 |
| _initialized | bool | False | 初始化状态 |

##### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `control_points` | torch.Tensor 或 None | 只读 | 不提供 | 返回 BSP 控制点 detached clone |
| `num_variables` | int | 只读 | 不提供 | 返回 BSP 设计变量数量 |
| `geometry_data` | `SurfaceGeometryData` 或 None | 只读 | 不提供 | 返回当前 BSP 几何数据 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| initialize() | None | `Initializable` | 创建 BSP 后端，并建立 UV 参数点到控制点的映射缓存 |
| reinitialize(iteration) | None | `Initializable` | 刷新当前控制点对应的几何数据 |
| evaluate_geometry() | `SurfaceGeometryData` | - | 计算点、一阶导数、二阶导数和权重 |
| get_control_points_list() | list[torch.Tensor] | - | 返回 BSP 控制点 |
| get_points_weight() | torch.Tensor | - | 返回 BSP 采样点权重 |
| update_geometry(design_delta) | None | - | 由 `BoundaryPart` 调用，用试探增量生成可微几何数据 |
| build_surface() | object | - | 生成 BSP 曲面对象 |
| get_meshes() | list[object] | `Visualizable` | 返回 BSP 曲面网格 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

`BSPSurface` 使用 `BSPFairnessEvaluator` 计算 Fairness。
控制点的参数快照、设计增量和正式提交由所属 `BoundaryPart` 统一完成。

##### `BSPCylinderSurface`

`BSPCylinderSurface` 对应现有 `initialize_cylinder()` 的构造逻辑。构造函数只记录
圆柱定义和 Fairness 参数；`initialize()` 再根据这些属性创建初始控制点、B-spline
basis、BSP 后端对象和 preload 数据。

###### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_radius` | float | 构造函数必填 | 圆柱半径，对应现有 `r0` |
| `_length` | float | 构造函数必填 | 圆柱长度 |
| `_seed_size` | float | 构造函数必填 | 初始网格和 preload 尺寸 |
| `_num_u_ratio` | int | 1 | 圆周方向控制点数量比例 |
| `_num_v_ratio` | int | 1 | 轴向控制点数量比例 |
| `_degree` | int | 3 | B-spline 阶数 |
| `_init_location` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 圆柱初始位置 |
| `_max_r` | float | 0.2 | 二阶导数/曲率变化阈值 |
| `_max_c` | float | 1.0 | 曲率阈值 |
| `_max_ff` | float | 0.2 | Fairness factor 阈值 |
| `_perturbation_length` | float 或 None | None | 初始半径扰动周期；None 表示不扰动 |

`flip` 只由 `BaseSurfaceInterface` 保存为运行时状态，圆柱定义直接继承该属性。

###### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `radius` | float | 只读 | 不提供 | 圆柱半径 |
| `length` | float | 只读 | 不提供 | 圆柱长度 |
| `seed_size` | float | 只读 | 不提供 | 初始网格和 preload 尺寸 |
| `num_u_ratio` | int | 只读 | 不提供 | 圆周方向比例 |
| `num_v_ratio` | int | 只读 | 不提供 | 轴向比例 |
| `degree` | int | 只读 | 不提供 | B-spline 阶数 |
| `init_location` | tuple[float, float, float] | 只读 | 不提供 | 初始位置 |
| `max_r` | float | 只读 | 不提供 | 二阶导数/曲率变化阈值 |
| `max_c` | float | 只读 | 不提供 | 曲率阈值 |
| `max_ff` | float | 只读 | 不提供 | Fairness factor 阈值 |
| `perturbation_length` | float 或 None | 只读 | 不提供 | 初始半径扰动周期 |

###### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| initialize() | None | `Initializable` | 依据圆柱参数生成控制点、basis、BSP 模型和 preload 数据 |

###### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_create_initial_control_points()` | `torch.Tensor` | 按半径、长度、比例和扰动参数生成控制点 |
| `_create_bsp_model()` | object | 创建圆周方向周期、轴向方向夹持的 B-spline 模型 |

#### `CPGEOSurface`

`CPGEOSurface` 使用 CPGEO 控制网格和三角形拓扑定义曲面，同样支持形状优化，
但其几何导数、采样点和 Fairness 计算方式独立于 BSP。具体形状通过
`CPGEOCylinderSurface` 或 `CPGEOSphereSurface` 等定义类记录。

##### 本类型构造属性

`CPGEOSurface` 继承基类的运行时 `flip`，并使用 `CpBasedSurface` 的控制点和 preload
运行时状态。控制点和三角形拓扑由具体形状定义在 `initialize()` 中生成，几何导数
按基类规定的 `v` 方向规则变换。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _model | object 或 None | None | CPGEO 后端对象 |
| _knots | `torch.Tensor` 或 None | None | CPGEO 采样或 knot 点 |
| _cp_faces | `numpy.ndarray` 或 None | None | 当前控制网格拓扑 |
| _num_knots | int 或 None | None | 当前 knot 点数量 |
| _is_first_initialize | bool | True | 首次初始化标记，用于决定是否重建 CPGEO |
| _output_rsphere | `numpy.ndarray` 或 None | None | 输出/可视化用球面参数点 |
| _output_cpfaces | `numpy.ndarray` 或 None | None | 输出/可视化用控制面拓扑 |
| _geometry_data | `SurfaceGeometryData` 或 None | None | 当前点、导数和权重 |
| _mesh | object 或 None | None | 当前可视化网格 |
| _initialized | bool | False | 初始化状态 |

##### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `control_points` | torch.Tensor 或 None | 只读 | 不提供 | 返回 CPGEO 控制点 detached clone |
| `cp_faces` | `numpy.ndarray` 或 None | 只读 | 不提供 | 返回控制网格拓扑只读副本 |
| `geometry_data` | `SurfaceGeometryData` 或 None | 只读 | 不提供 | 返回当前 CPGEO 几何数据 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| initialize() | None | `Initializable` | 建立 CPGEO 模型和初始参数映射缓存 |
| reinitialize(iteration) | None | `Initializable` | 根据重构质量刷新采样和导数缓存 |
| evaluate_geometry() | `SurfaceGeometryData` | - | 计算 CPGEO 几何数据 |
| get_control_points_list() | list[torch.Tensor] | - | 返回 CPGEO 控制点 |
| get_points_weight() | torch.Tensor | - | 返回 CPGEO 采样点权重 |
| update_geometry(design_delta) | None | - | 由 `BoundaryPart` 调用，用试探增量生成可微几何数据 |
| build_surface() | object | - | 生成 CPGEO 曲面对象 |
| get_meshes() | list[object] | `Visualizable` | 返回 CPGEO 曲面网格 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

`CPGEOSurface` 使用 `CPGEOFairnessEvaluator` 计算 Fairness。
控制点的参数快照、设计增量和正式提交由所属 `BoundaryPart` 统一完成。

##### `CPGEOCylinderSurface`

`CPGEOCylinderSurface` 对应现有 `CPGEO.initialize_cylinder()` 的构造逻辑。构造函数
记录圆柱网格定义，`initialize()` 再生成三角形控制网格并创建 CPGEO 后端对象。

###### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_radius` | float | 构造函数必填 | 圆柱半径，对应现有 `r0` |
| `_length` | float | 构造函数必填 | 圆柱长度 |
| `_seed_size` | float | 构造函数必填 | 圆周和轴向网格尺寸 |
| `_num_u_ratio` | int | 1 | 圆周方向网格数量比例 |
| `_num_v_ratio` | int | 1 | 轴向网格数量比例 |
| `_init_location` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 圆柱初始位置 |
| `_perturbation_length` | float 或 None | None | 初始半径扰动周期；None 表示不扰动 |
| `_max_c` | float | 1.0 | CPGEO Fairness 的曲率阈值 |

`flip` 由 `BaseSurfaceInterface` 统一记录；圆柱的参数导数和由其计算出的法向量
均按 `v` 方向反向规则处理，不单独对法向量做后处理。

###### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `radius` | float | 只读 | 不提供 | 圆柱半径 |
| `length` | float | 只读 | 不提供 | 圆柱长度 |
| `seed_size` | float | 只读 | 不提供 | 初始尺寸 |
| `num_u_ratio` | int | 只读 | 不提供 | 圆周方向比例 |
| `num_v_ratio` | int | 只读 | 不提供 | 轴向比例 |
| `init_location` | tuple[float, float, float] | 只读 | 不提供 | 初始位置 |
| `perturbation_length` | float 或 None | 只读 | 不提供 | 初始半径扰动周期 |
| `max_c` | float | 只读 | 不提供 | Fairness 曲率阈值 |

###### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| initialize() | None | `Initializable` | 生成圆柱顶点/三角面并创建 CPGEO 模型 |

###### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_create_cylinder_mesh()` | tuple[`numpy.ndarray`, `numpy.ndarray`] | 生成圆柱顶点和三角形拓扑 |

##### `CPGEOSphereSurface`

`CPGEOSphereSurface` 对应现有 `CPGEO.initialize_Sphere()` 的构造逻辑，使用
Fibonacci 分布生成球面点，再由球面三角剖分得到控制面。

###### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_radius` | float | 构造函数必填 | 球面半径 |
| `_seed_size` | float | 构造函数必填 | 初始点数量和采样尺寸 |
| `_init_location` | tuple[float, float, float] | (0.0, 0.0, 0.0) | 球面中心位置 |
| `_max_c` | float | 1.0 | CPGEO Fairness 的曲率阈值 |

`flip` 由 `BaseSurfaceInterface` 统一记录为运行时参数方向状态。

###### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `radius` | float | 只读 | 不提供 | 球面半径 |
| `seed_size` | float | 只读 | 不提供 | 初始尺寸 |
| `init_location` | tuple[float, float, float] | 只读 | 不提供 | 球面中心位置 |
| `max_c` | float | 只读 | 不提供 | Fairness 曲率阈值 |

###### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| initialize() | None | `Initializable` | 生成球面点、三角拓扑并创建 CPGEO 模型 |

###### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_create_sphere_mesh()` | tuple[`numpy.ndarray`, `numpy.ndarray`] | 生成球面顶点和三角形拓扑 |

#### `STLSurface`

`STLSurface` 从 STL 三角网格读取固定曲面，只参与几何构建、集合注册和可视化。

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_stl_path` | str | 构造函数必填 | STL 文件路径 |
| `_scale` | float | 1.0 | 导入缩放比例 |

`flip` 由 `BaseSurfaceInterface` 统一记录为运行时参数方向状态。`STLSurface` 没有
参数导数，因此不执行 `r_{u^a v^b}` 变换；导入网格的三角形方向由 STL 后端的网格
方向规则处理。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _vertices | `numpy.ndarray` 或 None | None | 导入后的顶点坐标 |
| _faces | `numpy.ndarray` 或 None | None | 导入后的三角形拓扑 |
| _mesh | object 或 None | None | STL 网格缓存 |
| _initialized | bool | False | 初始化状态 |

##### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `stl_path` | str | 只读 | 不提供 | STL 源文件路径 |
| `scale` | float | 只读 | 不提供 | 导入缩放比例 |
| `vertices` | `numpy.ndarray` 或 None | 只读 | 不提供 | 返回导入顶点只读副本 |
| `faces` | `numpy.ndarray` 或 None | 只读 | 不提供 | 返回三角拓扑只读副本 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| initialize() | None | `Initializable` | 读取 STL 并建立网格缓存 |
| reinitialize(iteration) | None | `Initializable` | 刷新当前网格引用 |
| build_surface() | object | - | 创建固定三角网格曲面 |
| get_surface_points() | `torch.Tensor` | - | 返回 STL 顶点或采样点 |
| get_meshes() | list[object] | `Visualizable` | 返回 STL 网格 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

`STLSurface` 不继承 `Updatable`，不提供设计增量，也不创建 Fairness evaluator。
`SurfaceGeometryData` 中需要一阶或二阶导数的字段对 STL 保持为空；BSP 和 CPGEO
的 Fairness 约束不使用 STL 作为计算对象。

### 5.5 `INPPart`

`INPPart` 从外部 INP 文件读取一个源 `Part`，转换为统一的 `Part` 定义。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_name` | str | 必填 | MorphOpt 目标 `Part` 名称 |
| `_element_name` | str | 构造函数必填 | 导入后使用的单一 `Part.elems` 名称 |
| `_inp_path` | str | 必填 | INP 文件路径 |
| `_source_part_name` | str | 必填 | INP 内部源 `Part` 名称 |
| `_exterior_surface` | str | `'extern'` | 外表面集合名称 |
| `_instances` | dict[str, `InstanceDefinition`] | {} | `Instance` 集合 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _source_part | `torchfea.Part` 或 None | None | 导入缓存 |
| _part | `torchfea.Part` 或 None | None | 最近生成的 TorchFEA `Part` |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `part_name` | str | 只读 | 不提供 | 返回目标 `Part` 名称 |
| `element_name` | str | 只读 | 不提供 | 返回导入后的元素名称 |
| `inp_path` | str | 只读 | 不提供 | 返回 INP 源文件路径 |
| `source_part_name` | str | 只读 | 不提供 | 返回源模型中的 `Part` 名称 |
| `exterior_surface` | str | 只读 | 读写 | 读写整体外表面集合名称 |
| `instances` | Mapping[str, `InstanceDefinition`] | 只读 | 不提供 | 返回 `Instance` 只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| build_assembly(path_result, pools) | `torchfea.Part` | - | 读取并复制源 `Part` |
| initialize() | None | `Initializable` | 检查路径、源 `Part` 和 element_name |
| get_meshes() | list[object] | `Visualizable` | 返回导入网格 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

几何导入逻辑归属于 `INPPart`，`FEAParams` 处理生成后的 `Assembly`。

### 5.6 `TorchFEAUIPart`

`TorchFEAUIPart` 读取 TorchFEA UI 导出的模型文件，提取一个源 `Part` 并按本地
`Instance` 定义加入 `Assembly`。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_name` | str | 必填 | MorphOpt 目标 `Part` 名称 |
| `_element_name` | str | 构造函数必填 | 导入后使用的单一 `Part.elems` 名称 |
| `_model_directory` | str | 必填 | 导出目录 |
| `_model_filename` | str | 必填 | 导出模型文件名 |
| `_source_part_name` | str | 必填 | 导出模型中的源 `Part` 名称 |
| `_exterior_surface` | str | `'extern'` | 外表面集合名称 |
| `_instances` | dict[str, `InstanceDefinition`] | {} | `Instance` 集合 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _model_summary | TorchFEAModelSummary 或 None | None | 模型摘要缓存 |
| _part | `torchfea.Part` 或 None | None | 最近生成的 TorchFEA `Part` |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `part_name` | str | 只读 | 不提供 | 返回目标 `Part` 名称 |
| `element_name` | str | 只读 | 不提供 | 返回导入后的元素名称 |
| `model_directory` | str | 只读 | 不提供 | 返回模型目录 |
| `model_filename` | str | 只读 | 不提供 | 返回模型文件名 |
| `source_part_name` | str | 只读 | 不提供 | 返回源模型中的 `Part` 名称 |
| `exterior_surface` | str | 只读 | 读写 | 读写整体外表面集合名称 |
| `instances` | Mapping[str, `InstanceDefinition`] | 只读 | 不提供 | 返回 `Instance` 只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| resolve_model_path() | str | - | 解析模型文件路径 |
| inspect_model() | TorchFEAModelSummary | - | 获取 Parts、Instances 和集合名称 |
| build_assembly(path_result, pools) | `torchfea.Part` | - | 复制指定源 `Part` |
| initialize() | None | `Initializable` | 检查模型文件、源 `Part` 和 element_name |
| get_meshes() | list[object] | `Visualizable` | 返回导入模型预览 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

第一版使用导出模型文件作为 TorchFEA UI 的边界。模型摘要为 UI 提供 `Part`、
`Instance`、surface set、node set、element set 和 element_name 选项。

### 5.7 `OffsetShellPart`

`OffsetShellPart` 继承 `BoundaryPart` 的曲面能力，并负责从源曲面同时生成实体元素
和壳元素。实体元素通常使用 `C3D4`，壳元素通常使用 `C3D6`，两者在
`Part.elems` 中使用不同名称。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_part_name` | str | 构造函数确定 | 偏置壳 `Part` 名称 |
| `_solid_element_name` | str | 构造函数必填 | 实体部分的 `Part.elems` 名称，例如 `C3D4` |
| `_shell_element_name` | str | 构造函数必填 | 壳部分的 `Part.elems` 名称，例如 `C3D6` |
| `_exterior_surface` | str | `'extern'` | 整体外表面集合名称；继承 `BoundaryPart` 的定义 |
| `_source_surface` | str | 必填 | 偏置源曲面 |
| `_thickness` | float | 必填 | 壳层厚度 |
| `_num_layers` | int | 必填 | 偏置层数 |
| `_direction` | str | 必填 | inward 或 outward |
| `_surfaces` | list[`BaseSurfaceInterface`] | [] | 源边界曲面 |
| `_instances` | dict[str, `InstanceDefinition`] | {} | `Instance` 集合 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _offset_nodes | torch.Tensor 或 None | None | 偏置节点缓存 |
| _offset_elements | object 或 None | None | 偏置元素缓存 |
| _part | `torchfea.Part` 或 None | None | 最近生成的 TorchFEA `Part` |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `solid_element_name` | str | 只读 | 不提供 | 返回实体元素名称 |
| `shell_element_name` | str | 只读 | 不提供 | 返回壳元素名称 |
| `part_name` | str | 只读 | 不提供 | 返回偏置壳 `Part` 名称 |
| `exterior_surface` | str | 只读 | 读写 | 返回或修改整体外表面集合名称 |
| `surfaces` | tuple[`BaseSurfaceInterface`, ...] | 只读 | 不提供 | 返回源边界曲面 |
| `source_surface` | str | 只读 | 不提供 | 返回偏置源曲面名称 |
| `thickness` | float | 只读 | 不提供 | 返回壳层厚度 |
| `num_layers` | int | 只读 | 不提供 | 返回偏置层数 |
| `direction` | str | 只读 | 不提供 | 返回偏置方向 |
| `offset_nodes` | torch.Tensor 或 None | 只读 | 不提供 | 返回偏置节点缓存的 detached clone |
| `offset_elements` | object 或 None | 只读 | 不提供 | 返回偏置元素缓存摘要 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| define_surfaces() | None | - | 定义源边界曲面 |
| build_assembly(path_result, pools) | `torchfea.Part` | - | 生成实体节点/元素和偏置壳元素 |
| initialize() | None | `Initializable` | 初始化边界和偏置缓存 |
| reinitialize(iteration) | None | `Initializable` | 根据源边界刷新偏置数据 |
| get_parameters() | list[torch.Tensor] | `Updatable` | 导出偏置几何参数的 detached clone |
| set_parameters(parameters) | None | `Updatable` | 导入偏置几何参数的 detached clone |
| get_design_delta() | torch.Tensor | `Updatable` | 返回全 0 的偏置几何设计增量 |
| update_assembly(assembly, design_delta) | None | `Updatable` | 将偏置增量映射到节点、元素和表面并保留计算图 |
| apply_design_delta(design_delta) | None | `Updatable` | 将偏置几何设计增量正式写回 |
| get_meshes() | list[object] | `Visualizable` | 返回边界和偏置壳预览 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

偏置壳的属性和更新方法集中在 `OffsetShellPart` 中。`BoundaryPart` 保留曲面定义
和边界几何能力。

## 6. 材料类定义

### 6.1 `MaterialsParams`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_materials` | dict[str, `MaterialAssignment`] | {} | 材料名称到分配记录 |
| `_materials_by_part` | dict[str, tuple[str, ...]] | {} | `Part` 到材料名称的索引 |
| `_materialmodels` | type[`MaterialModels`] | 类内命名空间 | 参数类访问入口 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 初始化状态 |
| _geometry | `GeometryParams` 或 None | None | 初始化后绑定的几何定义 |
| _part_elements | dict[str, tuple[str, ...]] | {} | 初始化后解析的 `Part` 元素名称 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `materials` | Mapping[str, `MaterialAssignment`] | 只读 | 不提供 | 返回材料注册表的只读视图 |
| `materials_by_part` | Mapping[str, tuple[str, ...]] | 只读 | 不提供 | 返回 `Part` 到材料名称的只读索引 |
| `materialmodels` | type[`MaterialModels`] | 只读 | 不提供 | 返回材料参数命名空间 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| define_materials() | None | - | 用户注册材料的扩展点 |
| add_material(part_name, interface, name) | None | - | 绑定材料接口到 `Part` |
| get_material(name) | `MaterialAssignment` | - | 获取材料分配记录 |
| names_for_part(part_name) | tuple[str, ...] | - | 获取某 `Part` 的材料名称 |
| assign_materials(assembly) | None | - | 将全部材料写入 `Assembly` |
| get_parameters(name) | torch.Tensor | - | 导出材料参数的 detached clone |
| set_parameters(name, parameters) | None | - | 导入材料参数的 detached clone |
| get_design_delta(name) | torch.Tensor | - | 返回指定材料的全 0 设计增量 |
| update_assembly(name, assembly, design_delta) | None | - | 将材料增量写入已有 `Assembly` 并保留计算图 |
| apply_design_delta(name, design_delta) | None | - | 将材料设计增量正式写回材料接口 |
| initialize(geometry) | None | `Initializable` | 校验 `Part`、Elems 和覆盖范围 |
| get_meshes() | list[object] | `Visualizable` | 收集材料场预览 |
| save(foldpath, iteration) | None | `Persistable` | 保存材料状态和相关结果 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的材料状态和结果 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

part_name 只出现在 add_material 的绑定关系中。材料接口自身记录 element_name、
density、本构参数和设计状态。

### 6.2 `MaterialAssignment`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_name` | str | 全局唯一材料名称 |
| `_part_name` | str | 目标 `Part` |
| `_interface` | `BaseMaterialInterface` | 材料接口 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

无运行时缓存。目标元素名称由 `target_element_names()` 按当前 `Assembly` 即时解析。

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 不提供 | 返回材料注册名称 |
| `part_name` | str | 只读 | 不提供 | 返回目标 `Part` 名称 |
| `interface` | `BaseMaterialInterface` | 只读 | 不提供 | 返回材料接口 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| target_element_names(assembly) | tuple[str, ...] | - | 解析目标元素族 |
| validate(assembly) | None | - | 校验 `Part` 和元素范围 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

### 6.3 `MaterialModels`

`MaterialModels` 是 `MaterialsParams` 内部的材料参数命名空间。参数类名称直接
表达本构模型，参数对象携带对应 TorchFEA 材料类。

#### `MaterialModels` 属性

`MaterialModels` 是类型命名空间，不创建运行时实例。它的类属性是各个参数类名称，
例如 `NeoHookeanParams` 和 `OgdenParams`；这些类属性只用于代码提示和构造参数对象，
没有实例级运行时缓存。

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `NeoHookeanParams` 等参数类 | type[`MaterialParameters`] | 只读 | 不提供 | 类内命名空间成员，通过构造函数创建参数对象 |

#### `MaterialParameters`

##### 构造属性（`__init__()` 记录）

每个参数类只记录其本构模型要求的必填字段，例如 `mu`、`kappa`、`E`、`nu` 或
`alpha`。字段名称和类型由具体参数类声明，所有参数值由用户在构造时提供；内部
存储字段使用 `_mu`、`_kappa`、`_E` 等私有名称。

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

无运行时缓存。`MaterialParameters` 是轻量的本构参数值对象，
`create_material()` 调用时直接读取这些字段。

##### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `material_class` | type[`Materials_Base`] | 只读 | 不提供 | 对应 TorchFEA 本构类 |
| 本构参数字段（如 `mu`、`kappa`） | float 或 list[float] | 只读 | 不提供 | 对应私有字段的只读 property；通过新建参数对象替换 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| create_material() | `Materials_Base` | - | 从当前参数字段创建本构对象 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

#### 参数类

| 参数类 | 必填字段 | TorchFEA 类 |
|---|---|---|
| LinearElasticParams | E: float, nu: float | LinearElastic |
| NeoHookeanParams | mu: float, kappa: float | NeoHookean |
| NeoHookeanLnJParams | mu: float, kappa: float | NeoHookeanLnJ |
| MooneyRivlinParams | c10: float, c01: float, kappa: float | MooneyRivlin |
| YeohParams | c1: float, c2: float, c3: float, kappa: float | Yeoh |
| GentParams | mu: float, Jm: float, kappa: float | Gent |
| ArrudaBoyceParams | mu: float, N: float, kappa: float | ArrudaBoyce |
| OgdenParams | mu: float, alpha: float 或 list[float], kappa: float | Ogden |

规则：

- 参数字段全部必填；
- NeoHookeanLnJParams 是默认材料模型类型；
- 参数值没有默认值；
- create_material 只读取当前参数对象字段；
- 新增 TorchFEA 本构时增加对应参数类；
- UI 根据参数类字段生成编辑项和代码提示。

### 6.4 `BaseMaterialInterface`

`BaseMaterialInterface` 显式继承 `Visualizable`、`Initializable` 和 `Persistable`。
`assign_material()` 是该基类定义的抽象核心方法，由具体材料类型实现。所有材料
接口都可以记录定义状态、写入材料并提供预览对象。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_element_name` | str | "" | 元素族；空字符串表示全部 |
| `_density` | float | 0.0 | 标量密度 |
| `_material_parameters` | `MaterialParameters` | 必填 | 本构参数对象；参数类型确定材料模型 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 初始化状态 |
| _target_elements | list[object] | [] | 解析后的目标元素族 |
| _material | object 或 None | None | 当前 TorchFEA 材料对象 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `element_name` | str | 只读 | 不提供 | 返回目标元素族；空字符串表示全选 |
| `density` | float | 只读 | 不提供 | 返回材料密度 |
| `material_parameters` | `MaterialParameters` | 只读 | 不提供 | 返回本构参数的只读对象 |
| `material` | object 或 None | 只读 | 不提供 | 返回当前 TorchFEA 材料对象 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 默认行为 | 作用 |
|---|---|---|---|---|
| assign_material(part_name, assembly) | None | - | 抽象 | 写入当前材料 |
| initialize(part_name, assembly) | None | `Initializable` | 空操作 | 建立目标元素缓存 |
| get_meshes() | list[object] | `Visualizable` | 抽象 | 返回材料预览 |
| save(foldpath, iteration) | None | `Persistable` | 空操作 | 保存材料状态 |
| load(foldpath, iteration) | None | `Persistable` | 空操作 | 加载材料状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

基类提供材料接口共有的目标选择和生命周期。材料本构创建、材料场映射和场
变量专用方法由具体接口实现。可更新材料接口另外实现 `get_parameters()`、
`set_parameters()`、`get_design_delta()`、`update_assembly()` 和
`apply_design_delta()`；固定材料接口只提供参数快照和材料构建。

### 6.5 `HomogeneousMaterial`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_element_name` | str | "" | 目标元素族 |
| `_density` | float | 0.0 | 标量密度 |
| `_material_parameters` | `MaterialParameters` | 必填 | 本构参数对象 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 初始化状态 |
| _target_elements | list[object] | [] | 解析后的目标元素族 |
| _material | object 或 None | None | 当前 TorchFEA 材料对象 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `element_name` | str | 只读 | 不提供 | 返回目标元素族 |
| `density` | float | 只读 | 不提供 | 返回材料密度 |
| `material_parameters` | `MaterialParameters` | 只读 | 不提供 | 返回本构参数对象 |
| `material` | object 或 None | 只读 | 不提供 | 返回当前 TorchFEA 材料对象 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| assign_material(part_name, assembly) | None | - | 创建本构并写入目标元素 |
| get_meshes() | list[object] | `Visualizable` | 返回均匀材料的可视化对象 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

均匀材料不包含材料参数默认值，也不生成材料设计变量。

### 6.6 `SIMPFieldMaterial`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_element_name` | str | SIMP 作用的元素族 |
| `_density` | float | 基础密度 |
| `_material_parameters` | `MaterialParameters` | 基准本构参数 |
| `_mumax` | float | 最大材料参数 |
| `_kappamax` | float | 最大体积参数 |
| `_initial_ratio` | float | 初始材料比例 |
| `_simp_ratio_min` | float | 材料比例下限 |
| `_bounding_box` | tuple[float, ...] | BSP 设计区域 |
| `_simp_field_resolution` | float | 场采样分辨率 |
| `_degree` | int | BSP 阶数 |
| `_voidpenalfactor` | float | 空材料惩罚 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _cps | torch.Tensor 或 None | None | 初始化后分配的 BSP 控制点 |
| _bsp_size | tuple[int, ...] 或 None | None | 初始化后确定的控制点尺寸 |
| _initialized | bool | False | 初始化状态 |
| _target_elements | list[object] | [] | 解析后的目标元素族 |
| _element_map | object 或 None | None | 设计场到元素/积分点的映射缓存 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `element_name` | str | 只读 | 不提供 | 返回目标元素族 |
| `density` | float | 只读 | 不提供 | 返回基础密度 |
| `material_parameters` | `MaterialParameters` | 只读 | 不提供 | 返回基准本构参数 |
| `control_points` | torch.Tensor 或 None | 只读 | 不提供 | 返回 SIMP 控制点 detached clone |
| `material_ratio` | torch.Tensor 或 None | 只读 | 不提供 | 返回当前材料比例场 detached clone |
| `mumax` | float | 只读 | 不提供 | 返回最大材料参数 |
| `kappamax` | float | 只读 | 不提供 | 返回最大体积参数 |
| `initial_ratio` | float | 只读 | 不提供 | 返回初始材料比例 |
| `simp_ratio_min` | float | 只读 | 不提供 | 返回材料比例下限 |
| `bounding_box` | tuple[float, ...] | 只读 | 不提供 | 返回 BSP 设计区域 |
| `simp_field_resolution` | float | 只读 | 不提供 | 返回场采样分辨率 |
| `degree` | int | 只读 | 不提供 | 返回 BSP 阶数 |
| `voidpenalfactor` | float | 只读 | 不提供 | 返回空材料惩罚 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| get_control_points_list() | list[torch.Tensor] | - | 返回 BSP 控制点 |
| get_points_weight() | torch.Tensor | - | 返回材料点权重 |
| get_material_ratio(design_field) | torch.Tensor | - | 设计场转材料比例 |
| assign_material(part_name, assembly) | None | - | 安装 SIMP 材料行为和当前场 |
| initialize(part_name, assembly) | None | `Initializable` | 建立材料场和元素映射 |
| get_parameters() | torch.Tensor | `Updatable` | 导出 BSP 控制点的 detached clone |
| set_parameters(parameters) | None | `Updatable` | 导入 BSP 控制点的 detached clone |
| get_design_delta() | torch.Tensor | `Updatable` | 返回全 0 的 BSP 设计增量 |
| update_assembly(assembly, design_delta) | None | `Updatable` | 将试探增量映射到材料场并保留计算图 |
| apply_design_delta(design_delta) | None | `Updatable` | 将材料场设计增量正式写回控制点 |
| get_meshes() | list[object] | `Visualizable` | 返回材料比例预览 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

get_control_points_list、材料场映射、材料场预览和 `VolFrac` 所需数据只属于
`SIMPFieldMaterial`。

`SIMPFieldMaterial` 显式继承 `Updatable`；`HomogeneousMaterial` 只继承材料
领域的共同协议，不实现设计变量方法。

## 7. FEA 类定义

### 7.1 `BaseFEAComponent`

`BaseFEAComponent` 显式继承 `Visualizable`、`Initializable` 和 `Persistable`。
`create_fea()` 是该基类定义的抽象核心方法，由具体 FEA component 实现。所有载荷、
边界和接触组件都可以记录定义状态、创建 FEA 对象并提供可视化对象。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_instance_name` | str | 目标 `Instance` |
| _values | list[float] | 当前组件值 |
| _name | str | 注册后的 FEA component 名称 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _fea_object | object 或 None | None | 已创建的 TorchFEA 对象 |
| _target | object 或 None | None | 解析后的 `Instance`、Surface 或 Set |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 不提供 | 返回 FEA component 名称 |
| `instance_name` | str | 只读 | 不提供 | 返回目标 `Instance` |
| `values` | tuple[float, ...] | 只读 | 不提供 | 返回当前组件值的不可变副本 |
| `num_values` | int | 只读 | 不提供 | 返回值向量长度 |
| `fea_object` | object 或 None | 只读 | 不提供 | 返回已创建的 TorchFEA 对象 |
| `target` | object 或 None | 只读 | 不提供 | 返回已解析目标摘要 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| create_fea(assembly) | object | - | 创建并注册 TorchFEA FEA 对象 |
| process_fea(assembly, values) | None | - | 更新已有 FEA 对象的当前值 |
| get_initial_values() | list[float] | - | 返回 load step 初始值 |
| get_parameters() | torch.Tensor | - | 导出当前载荷参数的 detached clone |
| set_parameters(parameters) | None | - | 导入载荷参数的 detached clone |
| initialize(assembly) | None | `Initializable` | 解析目标 `Instance`、Surface、Set 和运行时上下文 |
| get_meshes() | list[object] | `Visualizable` | 返回载荷、边界或接触的可视化对象 |
| save(foldpath, iteration) | None | `Persistable` | 保存组件状态和结果引用 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的组件状态和结果引用 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

create_fea 在 `FEAController` 创建时执行一次，process_fea 在每个 load step 求解
前执行。

### 7.2 FEA component 子类

所有具体组件只记录自己的目标名称、参数和值维度。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_component_name` | str | 注册到 `FEAParams` 的稳定名称 |
| `_target_names` | str 或 tuple[str, ...] | `Instance`、surface set、node set、element set 或参考点名称 |
| `_component_parameters` | dict[str, object] | 组件专用配置，例如方向、DOF、刚度或接触参数 |
| `_initial_values` | list[float] | 初始载荷、位移或约束值 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

具体组件直接继承 `BaseFEAComponent` 的 `_fea_object`、`_target` 和 `_initialized`。
需要额外缓存的组件在自己的构造函数中声明对应的 `None` 或空容器，再由
`initialize()` 填充。

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `component_name` | str | 只读 | 不提供 | 返回注册名称 |
| `target_names` | str 或 tuple[str, ...] | 只读 | 不提供 | 返回目标名称 |
| `component_parameters` | Mapping[str, object] | 只读 | 不提供 | 返回组件配置只读视图 |
| `initial_values` | tuple[float, ...] | 只读 | 不提供 | 返回初始值 |

| 类 | 目标属性 | 值含义 |
|---|---|---|
| `Pressure` | instance_name, surface_name | 压力标量 |
| `BodyForce` | instance_name, element_name | 三方向体力密度 |
| `ConcentratedForce` | reference_point_name | 三方向集中力 |
| `ConcentratedMoment` | reference_point_name | 三方向集中力矩 |
| `BoundaryCondition` | instance_name, node_set_name | 节点 DOF 约束 |
| `BoundaryConditionRP` | reference_point_name | RP DOF 约束 |
| `Couple` | `Instance` 集合和 RP | 耦合 DOF |
| `ReferencePoint` | RP 名称和位置 | 参考点定义 |
| `SpringToGround` | RP 和 DOF | 对地弹簧 |
| `SpringBetweenRPs` | 两个 RP 和 DOF | RP 间弹簧 |
| `PenaltyDoF` | `Instance`/节点和 DOF | 惩罚 DOF |
| `Contact` | 两个 `Instance` surface | 接触参数 |
| `SelfContact` | 一个 `Instance` surface | 自接触参数 |

每个子类实现 `num_values`、`create_fea`、`process_fea` 和 `get_meshes`。需要进行载荷
优化的具体组件另外显式继承 `Updatable`，实现设计增量读取、Assembly 试探更新和正式
提交。可更新组件的参数快照使用 `get_parameters()` 和 `set_parameters()`；固定组件
不实现这些设计增量方法。可更新组件的方法为 `get_design_delta()`、
`update_assembly(assembly, design_delta)` 和 `apply_design_delta(design_delta)`。

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| create_fea(assembly) | object | - | 创建具体 FEA component |
| process_fea(assembly, values) | None | - | 更新具体 component 的当前值 |
| get_meshes() | list[object] | `Visualizable` | 返回具体 component 的可视化对象 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 具体 component 的内部辅助函数由各子类自行声明 |

### 7.3 `FEAParams`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_fea_components` | dict[str, `BaseFEAComponent`] | {} | FEA component 注册表 |
| `_reference_points` | dict[str, `ReferencePoint`] | {} | 参考点注册表 |
| `_load_steps` | list[dict[str, list[float]]] | [] | 工况矩阵 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 初始化状态 |
| _assembly | `torchfea.Assembly` 或 None | None | 初始化后绑定的当前 `Assembly` |
| _fea_controller | `torchfea.FEAController` 或 None | None | 最近创建的 FEA 控制器 |
| _component_targets | dict[str, object] | {} | 组件名称到解析目标的索引 |
| _resolved_steps | list[`LoadStep`] | [] | 校验后的 load step 对象 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `fea_components` | Mapping[str, `BaseFEAComponent`] | 只读 | 不提供 | 返回 FEA component 注册表只读视图 |
| `reference_points` | Mapping[str, `ReferencePoint`] | 只读 | 不提供 | 返回参考点注册表只读视图 |
| `load_steps` | tuple[`LoadStep`, ...] | 只读 | 不提供 | 返回工况定义的不可变视图 |
| `fea_controller` | `torchfea.FEAController` 或 None | 只读 | 不提供 | 返回最近创建的 FEA 控制器 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| define_components() | None | - | 用户注册 FEA component |
| define_steps() | None | - | 用户定义 load step |
| add_component(component, name) | None | - | 注册唯一名称的 FEA component |
| get_component(name) | `BaseFEAComponent` | - | 按名称取得 FEA component |
| set_step_num(num_steps) | None | - | 创建 step 行 |
| set_step_params(step_index, name, values) | None | - | 设置一个 step 的组件值 |
| create_fea(assembly) | `torchfea.FEAController` | - | 创建 `FEAController` 并安装对象 |
| process_fea(fe, step_index) | None | - | 应用一个 load step |
| get_parameters() | list[torch.Tensor] | - | 返回 load step 参数 |
| initialize(geometry) | None | `Initializable` | 校验 `Instance`、集合和 step 维度 |
| get_meshes() | list[object] | `Visualizable` | 收集所有载荷、边界和接触的预览对象 |
| save(foldpath, iteration) | None | `Persistable` | 保存 FEA component 状态和结果 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的 FEA component 状态和结果 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

### 7.4 Load step

#### `LoadStep` 属性

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_step_index` | int | 必填 | 工况序号 |
| `_component_values` | dict[str, list[float]] | {} | 组件名称到本工况值向量的映射 |

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _resolved_values | dict[str, torch.Tensor] | {} | 校验并转换后的值向量 |
| _initialized | bool | False | 初始化状态 |

##### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `step_index` | int | 只读 | 不提供 | 返回工况序号 |
| `component_values` | Mapping[str, tuple[float, ...]] | 只读 | 不提供 | 返回组件值的不可变视图 |
| `resolved_values` | Mapping[str, torch.Tensor] | 只读 | 不提供 | 返回校验后的值向量只读视图 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 无 | - | - | `LoadStep` 通过属性提供工况数据，不提供独立方法 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

#### `ReferencePoint` 属性

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | 必填 | 参考点名称 |
| `_position` | tuple[float, float, float] | 必填 | 参考点坐标 |

##### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _fea_reference_point | object 或 None | None | TorchFEA 参考点对象 |
| _initialized | bool | False | 初始化状态 |

##### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 不提供 | 返回参考点名称 |
| `position` | tuple[float, float, float] | 只读 | 不提供 | 返回参考点坐标 |
| `fea_reference_point` | object 或 None | 只读 | 不提供 | 返回已创建的 TorchFEA 参考点 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 无 | - | - | `ReferencePoint` 通过属性提供定义数据，不提供独立方法 |

##### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

每个 load step 必须包含全部 FEA component 名称，值向量长度必须等于对应组件
的 num_values。

~~~text
fea_components:
    pressure_1 → Pressure, num_values = 1
    bc_fix     → BoundaryCondition, num_values = 3

load_steps:
    step 0: pressure_1 = [0.00], bc_fix = [1.0, 1.0, 1.0]
    step 1: pressure_1 = [0.06], bc_fix = [1.0, 1.0, 1.0]
~~~

`FEAParams` 处理生成后的 `Assembly`。几何导入属于 `INPPart` 或 `TorchFEAUIPart`，材料
分配属于 `MaterialsParams`。

## 8. `Solver`

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_params` | `Params` | 构造函数传入 | 获取 `FEAParams` 和运行配置 |
| `_num_process` | int | 4 | worker 数量 |
| `_gpu_names` | list[str] | [] | 用户指定的 GPU 名称；空列表表示使用 CPU |

### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_task_index_list` | list[list[int]] | [] | 初始化阶段按 step 生成的 worker 分组 |
| `_available_gpus` | list[str] | [] | 初始化阶段解析后的可用 GPU 列表 |
| _pool | object 或 None | None | `Controller` 管理的 worker pool |
| _initialized | bool | False | 初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `params` | `Params` | 只读 | 不提供 | 返回模型参数 |
| `num_process` | int | 只读 | 不提供 | 返回 worker 数量 |
| `gpu_names` | tuple[str, ...] | 只读 | 不提供 | 返回设备配置 |
| `task_index_list` | tuple[tuple[int, ...], ...] | 只读 | 不提供 | 返回 worker 分组 |
| `available_gpus` | tuple[str, ...] | 只读 | 不提供 | 返回解析后的设备列表 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| solve(fe, U_guess) | list[`StaticResult`] | - | 求解全部 load steps |
| initialize(num_steps) | None | `Initializable` | 创建并校验 task groups |
| reinitialize(iteration) | None | `Initializable` | 更新 solver 迭代状态 |
| save(foldpath, iteration) | None | `Persistable` | 保存求解器状态和 worker 配置 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的求解器状态 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_solve_task(fe, task_indices, U_guess)` | list[`StaticResult`] | 求解一个任务组 |

`Solver` 设置 worker 设备、调用 `FEAParams.process_fea`、连续求解任务组、收集结果、
检查收敛并按 step index 排序。`Solver` 不拥有设计变量，也不调用 updater。

## 9. `ObjectiveFunction`

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_jacobian_needed` | list[str] | [] | Jacobian 所需接口名称 |

### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_fe` | `torchfea.FEAController` 或 None | None | 当前 FEA 模型 |
| `_fe_results` | list[`StaticResult`] | [] | 当前工况结果的记录容器 |
| `_metrics` | list[float] | [] | 当前展示指标 |
| _initialized | bool | False | 初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `jacobian_needed` | tuple[str, ...] | 只读 | 不提供 | 返回 Jacobian 所需接口名称 |
| `fe` | `torchfea.FEAController` 或 None | 只读 | 不提供 | 返回当前 FEA 模型 |
| `fe_results` | tuple[`StaticResult`, ...] | 只读 | 不提供 | 返回当前工况结果的只读视图 |
| `metrics` | tuple[float, ...] | 只读 | 不提供 | 返回当前展示指标 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| objective_function() | torch.Tensor | - | 计算一个标量目标 |
| get_metrics() | list[float] | - | 返回展示指标 |
| set_step(step_index) | None | - | 切换 `Assembly` work condition |
| compute_multistep_objective(fe_results, assembly) | torch.Tensor | - | 聚合多工况目标 |
| sensitivity_analysis(registry) | dict[`DesignKey`, torch.Tensor] | - | 计算并切分灵敏度 |
| get_mesh_case(case_index) | list[object] | - | 返回工况结果网格 |
| initialize() | None | `Initializable` | 校验目标和 Jacobian 引用 |
| save(foldpath, iteration) | None | `Persistable` | 保存目标值、指标和结果引用 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的历史结果 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

objective_function 读取当前 FEA 结果和 `Assembly`，返回标量 Tensor。目标函数
负责多工况求和、平均、最大值或加权聚合。metrics 只服务历史和 UI 展示。

jacobian_needed 中的名称来自 `FEAParams`。集中力和集中力矩使用同一 reference
point 时，初始化阶段校验目标一致。

### 9.1 `History`

`History` 记录每个 iteration 的目标值、metrics、收敛信息和耗时，供优化过程和
后处理读取。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_result_root` | str 或 None | None | 结果文件的根目录配置 |
| `_metric_names` | tuple[str, ...] | () | 需要记录的指标名称 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_records` | list[dict[str, object]] | [] | 按 iteration 保存的历史记录 |
| `_result_paths` | dict[int, str] | {} | iteration 到结果目录的映射 |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `result_root` | str 或 None | 只读 | 不提供 | 返回结果根目录 |
| `metric_names` | tuple[str, ...] | 只读 | 不提供 | 返回指标名称 |
| `records` | tuple[Mapping[str, object], ...] | 只读 | 不提供 | 返回历史记录只读视图 |
| `result_paths` | Mapping[int, str] | 只读 | 不提供 | 返回结果路径只读视图 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| append(iteration, metrics) | None | - | 添加一次 iteration 记录 |
| get_metrics() | list[dict[str, object]] | - | 返回全部历史指标 |
| save(foldpath, iteration) | None | `Persistable` | 写入当前历史记录和结果索引 |
| load(foldpath, iteration) | None | `Persistable` | 读取指定 iteration 的历史记录 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

### 9.2 目标和约束对象

`GeometryObjective`、`GeometryConstraint`、`MaterialObjective`、
`MaterialConstraint`、`LoadObjective` 和 `LoadConstraint` 都是局部计算对象，分别由
对应的 updater 注册。

Fairness 的具体计算采用约束侧的曲面类型策略，只提供
`BSPFairnessEvaluator` 和 `CPGEOFairnessEvaluator`。`STLSurface` 不创建
Fairness evaluator，也不参与 Fairness 惩罚计算。曲面类只提供所需的几何数据，
Fairness 公式保存在对应 evaluator 中。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_name` | str | 局部目标或约束名称 |
| `_target_name` | str | 目标 `Part`、材料接口或 FEA component 名称 |
| `_parameters` | dict[str, object] | 阈值、权重、方向和其他计算参数 |
| `_code` | str 或 None | 用户自定义计算代码；没有代码时为 None |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _owner | object 或 None | None | 初始化后绑定的目标对象 |
| _context | object 或 None | None | 当前 Assembly、材料场或结果上下文 |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 不提供 | 返回目标项名称 |
| `target_name` | str | 只读 | 不提供 | 返回目标对象名称 |
| `parameters` | Mapping[str, object] | 只读 | 不提供 | 返回阈值、权重和方向等配置 |
| `code` | str 或 None | 只读 | 不提供 | 返回用户代码槽文本 |
| `owner` | object 或 None | 只读 | 不提供 | 返回初始化后绑定对象 |
| `context` | object 或 None | 只读 | 不提供 | 返回当前计算上下文摘要 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| initialize(owner) | None | `Initializable` | 绑定目标并建立计算上下文 |
| evaluate(values) | torch.Tensor | - | 计算局部目标或约束值 |
| reinitialize(iteration) | None | `Initializable` | 刷新当前迭代上下文 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

## 10. `DesignRegistry`

### 10.1 `DesignKey`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_category` | Literal["geometry", "material", "load"] | 变量类别 |
| `_target` | str | `Part`、材料或 FEA component 名称 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

无运行时缓存。`DesignKey` 是只读的稳定标识对象。

`DesignKey` 组合值唯一标识一个变量拥有者，例如 geometry/body 或
material/body_solid。

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `category` | Literal["geometry", "material", "load"] | 只读 | 不提供 | 返回变量类别 |
| `target` | str | 只读 | 不提供 | 返回变量拥有者名称 |

### 10.2 `DesignBlock`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_key` | `DesignKey` | 变量块名称 |
| `_owner` | `Updatable` | 可更新的 `GeometryParams`、`Part`、材料接口或 FEA component |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_start` | int | 0 | finalize 后的拼接向量起点 |
| `_stop` | int | 0 | finalize 后的拼接向量终点 |
| `_size` | int | 0 | finalize 后的变量块长度 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `key` | `DesignKey` | 只读 | 不提供 | 返回变量块标识 |
| `owner` | `Updatable` | 只读 | 不提供 | 返回变量块拥有者 |
| `start` | int | 只读 | 不提供 | 返回拼接起点 |
| `stop` | int | 只读 | 不提供 | 返回拼接终点 |
| `size` | int | 只读 | 不提供 | 返回变量块长度 |

### 10.3 `DesignRegistry` 属性

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_blocks` | tuple[`DesignBlock`, ...] | () | 按类别和目标名称排序后冻结的变量块顺序 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _owners | dict[`DesignKey`, object] | {} | 变量块拥有者 |
| _finalized | bool | False | 注册表冻结状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `blocks` | tuple[`DesignBlock`, ...] | 只读 | 不提供 | 返回固定顺序的变量块 |
| `finalized` | bool | 只读 | 不提供 | 返回注册表冻结状态 |

### 10.4 `DesignRegistry` 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| register(category, target, owner, design_delta) | None | - | 使用 owner 的设计增量注册非空变量块 |
| finalize() | None | - | 按类别和名称排序，固定顺序并计算 offsets |
| values() | torch.Tensor | - | 拼接所有 owner 的设计增量 |
| split(full_values) | dict[`DesignKey`, torch.Tensor] | - | 按 offsets 切分向量 |
| apply_trial_values(assembly, full_values) | None | - | 向各 owner 分发试探增量并更新 `Assembly` |
| update_owners(changes) | None | - | 调用各 `Updatable` owner 的 `apply_design_delta()` 提交变化 |
| block(key) | `DesignBlock` | - | 获取一个变量块 |
| clear() | None | - | 清空注册表 |
| initialize(params) | None | `Initializable` | 从 Geometry、Materials、FEA 收集变量并调用 finalize |
| save(foldpath, iteration) | None | `Persistable` | 保存变量块、设计变量和 offsets |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的设计变量状态 |

### 10.4 `DesignRegistry` 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类的变量切分和提交逻辑全部通过外部接口完成 |

变量顺序由 `finalize()` 唯一确定，与各对象的注册调用顺序无关。排序规则为：

1. 类别顺序固定为 `geometry`、`material`、`load`；
2. 每个类别内部按目标稳定名称的字典序排序：几何使用 `part_name`，材料使用
   `material_name`，载荷使用 `fea_component_name`；
3. 同一目标存在多个变量块时，再按完整 `DesignKey` 的字典序排序；
4. 排序后的 `blocks` 顺序同时决定完整设计变量、完整灵敏度和所有 `offsets`。

排序键为：

| 类别 | 排序键 |
|---|---|
| geometry | `(0, part_name)` |
| material | `(1, material_name)` |
| load | `(2, fea_component_name)` |

固定 `Part`、均匀材料和固定载荷不产生变量块。一个 `DesignKey` 只注册一次。

### 10.5 设计增量表示

`get_design_delta()` 返回 owner 的设计增量空间。初始化时该 Tensor 为全 0、
`requires_grad=True`，并保留 autograd，供对应 updater 的子优化问题直接使用。
`apply_design_delta()` 接收优化器输出的增量，按 owner 的映射规则正式更新内部状态，
例如几何控制点使用 `atan` 限制单步变化。

| Owner | 设计增量 |
|---|---|---|
| `BoundaryPart` | 曲面控制点增量 |
| `SIMPFieldMaterial` | BSP 控制点增量 |
| 固定 `Part` | 空 Tensor |
| `HomogeneousMaterial` | 空 Tensor |

### 10.6 试探回写

~~~text
TorchFEA full trial vector
    → DesignRegistry.apply_trial_values()
        → BoundaryPart.update_assembly()
        → SIMPFieldMaterial.update_assembly()
        → future FEA component update_assembly()
    → TorchFEA 重新计算能量、残量或目标
~~~

试探过程使用已有 `Assembly`，不重新调用 `build_assembly()`。各 owner 的
`update_assembly()` 只修改自己拥有的 `Part`、元素或 FEA 对象，并保留设计增量到
TorchFEA 计算的计算图；registry 保持 block offsets 不变。

## 11. `Updater` 类定义

### 11.1 `BaseUpdater`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_owner` | `Updatable` 或 None | None | 绑定的可更新变量拥有者 |
| `_variable_key` | `DesignKey` 或 None | None | 绑定的变量块 |
| `_optimizer_name` | str | "" | 优化器类型名称 |
| `_optimizer_options` | dict[str, object] | {} | 优化器构造参数 |
| `_objectives` | dict[str, object] | {} | 局部目标项 |
| `_constraints` | dict[str, object] | {} | 局部罚函数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_optimizer` | `BaseOptimizer` 或 None | None | 初始化后创建的优化算法状态 |
| `_gradient` | torch.Tensor 或 None | None | 当前局部梯度 |
| `_last_change` | torch.Tensor 或 None | None | 最近变化 |
| _initialized | bool | False | 初始化状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `owner` | `Updatable` 或 None | 只读 | 不提供 | 返回绑定的变量拥有者 |
| `variable_key` | `DesignKey` 或 None | 只读 | 不提供 | 返回变量块标识 |
| `optimizer_name` | str | 只读 | 不提供 | 返回优化器名称 |
| `objectives` | Mapping[str, object] | 只读 | 不提供 | 返回局部目标只读视图 |
| `constraints` | Mapping[str, object] | 只读 | 不提供 | 返回局部约束只读视图 |
| `gradient` | torch.Tensor 或 None | 只读 | 不提供 | 返回最近梯度 detached clone |
| `last_change` | torch.Tensor 或 None | 只读 | 不提供 | 返回最近变化 detached clone |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| bind(key, owner) | None | - | 绑定一个变量拥有者 |
| closure(values, return_list) | torch.Tensor 或 list[torch.Tensor] | - | 计算局部目标 |
| update() | torch.Tensor | - | 计算变量变化 |
| initialize() | None | `Initializable` | 初始化优化器和局部目标 |
| reinitialize(iteration, gradient) | None | `Initializable` | 接收本地梯度 |
| save(foldpath, iteration) | None | `Persistable` | 保存优化器和局部 updater 状态 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的 updater 状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

`BaseUpdater` 只处理一块变量并计算局部变化。局部目标和罚函数只读取绑定 owner 的
数据；变化的正式提交由 `Updaters.update()` 统一完成。

### 11.2 `GeometryUpdater`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_part` | `Updatable` | 唯一目标、可更新的 `Part` |
| `_objectives` | dict[str, GeometryObjective] | 形状目标 |
| `_constraints` | dict[str, GeometryConstraint] | 几何罚函数 |
| `_equality_constraint` | SurfaceConstraint 或 None | 可选等式/投影约束 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 初始化状态；其余运行时字段继承自 `BaseUpdater` |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `part` | `Updatable` | 只读 | 不提供 | 返回唯一几何目标 |
| `objectives` | Mapping[str, GeometryObjective] | 只读 | 不提供 | 返回形状目标只读视图 |
| `constraints` | Mapping[str, GeometryConstraint] | 只读 | 不提供 | 返回几何约束只读视图 |
| `equality_constraint` | SurfaceConstraint 或 None | 只读 | 不提供 | 返回等式/投影约束 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| closure(values, return_list) | Tensor 或 list[Tensor] | - | 计算局部形状目标 |
| update() | torch.Tensor | - | 计算几何变化 |
| initialize() | None | `Initializable` | 初始化 `Part` 局部优化器 |
| reinitialize(iteration, gradient) | None | `Initializable` | 接收 `Part` 几何梯度 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

Fairness、Distance、Cylinder 等属于 `GeometryUpdater` 的罚函数。
MirrorSymmetry 等式约束调用 `BoundaryPart.apply_surface_constraints`。

### 11.3 `MaterialUpdater`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_material` | `Updatable` | 唯一目标、可更新的材料接口 |
| `_objectives` | dict[str, MaterialObjective] | 材料目标 |
| `_constraints` | dict[str, MaterialConstraint] | 材料罚函数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 初始化状态；其余运行时字段继承自 `BaseUpdater` |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `material` | `Updatable` | 只读 | 不提供 | 返回唯一材料目标 |
| `objectives` | Mapping[str, MaterialObjective] | 只读 | 不提供 | 返回材料目标只读视图 |
| `constraints` | Mapping[str, MaterialConstraint] | 只读 | 不提供 | 返回材料约束只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| closure(values, return_list) | Tensor 或 list[Tensor] | - | 计算材料目标和约束 |
| update() | torch.Tensor | - | 计算材料变化 |
| initialize() | None | `Initializable` | 初始化材料优化器 |
| reinitialize(iteration, gradient) | None | `Initializable` | 接收材料梯度 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

`VolFrac` 绑定一个 `SIMPFieldMaterial` 和明确的 element_name。均匀材料没有设计
变量，因此不创建 `MaterialUpdater`。

### 11.4 `FEAUpdater`

第一版提供扩展位置，后续绑定一个 FEA component。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_fea_component` | `Updatable` | 唯一目标、可更新的 FEA component |
| `_objectives` | dict[str, object] | 载荷目标 |
| `_constraints` | dict[str, object] | 载荷约束 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 初始化状态；其余运行时字段继承自 `BaseUpdater` |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `fea_component` | `Updatable` | 只读 | 不提供 | 返回唯一 FEA 目标 |
| `objectives` | Mapping[str, object] | 只读 | 不提供 | 返回载荷目标只读视图 |
| `constraints` | Mapping[str, object] | 只读 | 不提供 | 返回载荷约束只读视图 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| update() | torch.Tensor | - | 计算载荷变化 |
| initialize() | None | `Initializable` | 初始化载荷优化器 |
| reinitialize(iteration, gradient) | None | `Initializable` | 接收载荷梯度 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

### 11.5 `UpdaterEntry`

`UpdaterEntry` 是一个 updater 注册项，不按几何、材料或 FEA 拆成固定数量的容器。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_name` | str | updater 名称 |
| `_target_kind` | str | 目标类别，例如 `geometry`、`material`、`load` 或用户扩展类别 |
| `_target_name` | str | 目标对象的稳定名称；几何目标使用 `part_name` |
| `_updater` | `BaseUpdater` | 更新策略对象，可以是内置 updater 或用户自定义子类 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

无独立运行时缓存。目标 owner 和变量块由其中的 updater 在 `Updaters.initialize()`
中绑定；updater 自身的运行时属性见 `BaseUpdater`。

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `name` | str | 只读 | 不提供 | 返回 updater 名称 |
| `target_kind` | str | 只读 | 不提供 | 返回目标类别 |
| `target_name` | str | 只读 | 不提供 | 返回目标名称 |
| `updater` | `BaseUpdater` | 只读 | 不提供 | 返回更新策略对象 |

### 11.6 `Updaters`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_entries` | dict[str, `UpdaterEntry`] | {} | 所有 updater 的注册项；同一类别允许多个 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 绑定状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `entries` | Mapping[str, `UpdaterEntry`] | 只读 | 不提供 | 返回 updater 注册项只读视图 |
| `initialized` | bool | 只读 | 不提供 | 返回绑定状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| define_updaters() | None | - | 用户注册任意数量和类型的 updater |
| add_updater(target_kind, target_name, updater, name) | None | - | 注册一个 updater，并明确其目标 |
| update() | dict[`DesignKey`, torch.Tensor] | - | 计算所有局部变化并一次性提交 |
| initialize(params, registry) | None | `Initializable` | 解析目标、绑定 owner、注册变量 |
| reinitialize(iteration, gradients) | None | `Initializable` | 分发局部梯度 |
| save(foldpath, iteration) | None | `Persistable` | 保存全部 updater 状态 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的全部 updater 状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

`Updaters` 是可变长度的 updater 集合。一个问题可以注册两个或更多几何 updater，
也可以只注册材料 updater、只注册载荷 updater，或混合注册任意数量的内置 updater
和用户自定义 `BaseUpdater` 子类。每个 `UpdaterEntry` 都保存明确的目标类别和目标
名称，因此多个 updater 可以分别绑定不同 `Part`、材料接口或 FEA component。

`Updaters.update()` 按注册项逐个调用 updater 的 `update()`，分别得到方向和步长形成的
局部变化；随后将所有变化按 `DesignKey` 汇总，并调用
`DesignRegistry.update_owners(changes)` 一次性写回所有 owner。几何、材料、载荷和
其他已注册 updater 在同一个外层迭代中完成同步更新。更新结果作为字典返回，供日志
和历史记录使用。没有对应 updater 的对象保持当前状态并继续参加 FEA。

## 12. Geometry、Material 和 Load 的联合更新

一个问题可以使用以下模式：

| 注册项 | 运行模式 |
|---|---|
| 无 updater | 固定模型 FEA |
| `GeometryUpdater` × N | 多个几何目标的联合优化 |
| `MaterialUpdater` × N | 多个材料目标的联合优化 |
| `FEAUpdater` × N | 多个载荷或边界目标的联合优化 |
| 任意组合 | 几何、材料、载荷和其他目标的联合优化 |

联合优化的单次更新顺序：

1. 生成当前 `Assembly`；
2. 赋予全部材料；
3. 创建 `FEAController`；
4. 求解全部 load steps；
5. 计算物理目标；
6. 计算一次完整灵敏度；
7. `DesignRegistry` 切分梯度；
8. 各 updater 计算局部变化；
9. 所有 updater 成功后统一提交；
10. 记录当前 iteration 结果并进入下一 iteration。

任意 updater 失败时，当前 iteration 记录错误并停止提交。

## 13. `Params`

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_geometry` | `GeometryParams` | 几何定义 |
| `_materials` | `MaterialsParams` | 材料定义 |
| `_feamodel` | `FEAParams` | FEA 定义 |

### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| _initialized | bool | False | 初始化状态 |
| _assembly | `torchfea.Assembly` 或 None | None | 最近一次生成的 `Assembly` |
| _fea_controller | `torchfea.FEAController` 或 None | None | 最近一次生成的 FEA 控制器 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `geometry` | `GeometryParams` | 只读 | 不提供 | 返回几何定义 |
| `materials` | `MaterialsParams` | 只读 | 不提供 | 返回材料定义 |
| `feamodel` | `FEAParams` | 只读 | 不提供 | 返回 FEA 定义 |
| `fea_controller` | `torchfea.FEAController` 或 None | 只读 | 不提供 | 返回最近创建的 FEA 控制器 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| create_feamodel(path_result, pools) | `torchfea.FEAController` | - | 生成完整 FEA 模型 |
| export_data(filepath) | None | - | 导出用户可读数据 |
| initialize() | None | `Initializable` | 初始化三个子系统 |
| reinitialize(iteration) | None | `Initializable` | 刷新当前 iteration |
| get_meshes() | list[object] | `Visualizable` | 收集几何和材料预览 |
| save(foldpath, iteration) | None | `Persistable` | 保存三个子系统的当前状态 |
| load(foldpath, iteration) | None | `Persistable` | 加载指定 iteration 的三个子系统状态 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类没有独立内部辅助函数 |

create_feamodel 的固定顺序：

~~~text
geometry.build_assembly()
    → materials.assign_materials(assembly)
    → feamodel.create_fea(assembly)
    → fe.initialize()
~~~

材料写入发生在 FEA 初始化之前。

## 14. `Controller`

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_params` | `Params` | 模型参数 |
| `_path_result` | str | 当前结果目录 |
| `_optdevice` | str | 优化设备 |

### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_solver` | `Solver` 或 None | None | 初始化后创建的 FEA 求解器 |
| `_objfun` | `ObjectiveFunction` 或 None | None | 初始化后绑定的目标和灵敏度对象 |
| `_registry` | `DesignRegistry` 或 None | None | 初始化后完成的变量注册表 |
| `_updater` | `Updaters` 或 None | None | 初始化后完成的更新策略集合 |
| `_history` | `History` 或 None | None | 当前运行的历史记录对象 |
| `_pools` | object 或 None | None | 初始化后创建的 worker pool |
| _initialized | bool | False | 初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `params` | `Params` | 只读 | 不提供 | 返回模型参数 |
| `path_result` | str | 只读 | 不提供 | 返回当前结果目录 |
| `optdevice` | str | 只读 | 不提供 | 返回优化设备 |
| `solver` | `Solver` 或 None | 只读 | 不提供 | 返回求解器 |
| `objfun` | `ObjectiveFunction` 或 None | 只读 | 不提供 | 返回目标函数 |
| `registry` | `DesignRegistry` 或 None | 只读 | 不提供 | 返回设计变量注册表 |
| `updater` | `Updaters` 或 None | 只读 | 不提供 | 返回更新器集合 |
| `history` | `History` 或 None | 只读 | 不提供 | 返回历史记录 |
| `pools` | object 或 None | 只读 | 不提供 | 返回 worker pool 摘要 |
| `initialized` | bool | 只读 | 不提供 | 返回初始化状态 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| start_optimization(main_filepath) | None | - | 从 iteration 0 开始 |
| restart_optimization(path_result, target_iteration) | None | - | 从指定 iteration 继续优化 |
| initialize() | None | `Initializable` | 创建和初始化全部对象 |
| save(foldpath, iteration) | None | `Persistable` | 调度 Params、DesignRegistry、Updaters 和 History 保存状态 |
| load(foldpath, iteration) | None | `Persistable` | 在任务初始化后加载指定 iteration 的状态和历史 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_initialize_path(main_filepath)` | None | 创建结果、日志和脚本目录 |
| `_opt_loop()` | None | 循环执行 step |
| `_step()` | tuple[torch.Tensor, float, float, float, float, float] | 完成一次外层迭代 |
| `_clear_cache()` | None | 清理 FEA 和 worker 缓存 |

### `_step()` 调用顺序

~~~text
1. params.reinitialize(iteration)
2. params.create_feamodel(...)
3. solver.solve(fe)
4. objfun.compute_multistep_objective(...)
5. objfun.sensitivity_analysis(registry)
6. updater.reinitialize(iteration, gradients)
7. changes = updater.update()
8. 记录 params / updater / objective / history 的运行指标
~~~

## 15. codesign 组合

codesign 使用统一对象：

~~~text
GeometryParams
└── OffsetShellPart: chamber
    ├── Instance: chamber
    └── source_surface / thickness / layers / direction

MaterialsParams
├── MaterialAssignment: solid
│   └── chamber / C3D4 → SIMPFieldMaterial
└── MaterialAssignment: shell
    └── chamber / C3D6 → HomogeneousMaterial

Updaters
├── GeometryUpdater → chamber
└── MaterialUpdater → solid
~~~

`FEAParams` 使用 instance_name 和 surface set 定义压力、边界条件、参考点和接触。
codesign 不创建独立 `Params` 或联合 updater 类型。

## 16. UI 数据模型

UI 节点记录定义数据，核心运行时对象在生成任务时创建。

### 16.1 UI 类清单

| 类 | 实例属性重点 | 方法重点 |
|---|---|---|
| `ProblemDefinition` | geometry、materials、fea、solver、objective、updaters | 结构编辑、级联改名、校验、Python 源码生成 |
| `GeometryNode` | `Part` 集合、公共参数 | `Part` 注册和 `part_name` 字典序显示 |
| `PartNode` | name、type、element_name 或实体/壳元素名称、外表面、源数据 | 创建对应 `Part` |
| `InstanceNode` | name、translation、rotation | 创建/修改 `Instance` |
| `MaterialNode` | name、part_name、element_name、接口类型、参数 | 创建 `MaterialAssignment` |
| `FEANode` | FEA component 集合、ReferencePoint 集合和 load steps | 创建 `FEAParams` |
| `FEAComponentNode` | name、type、目标名称、值 | 创建 FEA component |
| `LoadStepsNode` | step 数量、值矩阵 | 编辑 load steps |
| `ObjectiveNode` | objective code、metrics code、Jacobian | 编辑目标代码槽 |
| `UpdaterNode` | name、target_kind、target_name、updater 类型、目标项 | 创建 `UpdaterEntry`；根据 updater 类型显示相应编辑字段 |
| `SolverNode` | process、devices、task groups | 创建 `Solver` 配置 |

### 16.1.1 `ProblemDefinition` 属性

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
| _node_index | dict[str, object] | {} | 节点名称索引 |
| _validation_errors | list[str] | [] | 当前定义校验错误 |
| _generated_params | `Params` 或 None | None | 生成源码或预览时创建的参数对象 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `geometry` | `GeometryNode` | 只读 | 读写 | 通过节点编辑方法替换几何树 |
| `materials` | tuple[`MaterialNode`, ...] | 只读 | 读写 | 通过 `add_material()` 等方法维护 |
| `fea` | `FEANode` | 只读 | 读写 | 通过 FEA 编辑方法维护 |
| `solver` | `SolverNode` | 只读 | 读写 | 通过 solver 编辑方法维护 |
| `objective` | `ObjectiveNode` | 只读 | 读写 | 通过目标编辑方法维护 |
| `updaters` | tuple[`UpdaterNode`, ...] | 只读 | 读写 | 通过 `add_updater()` 等方法维护 |
| `validation_errors` | tuple[str, ...] | 只读 | 不提供 | 返回最近一次校验结果 |

### 16.1.2 UI Node 属性

#### 构造属性（`__init__()` 记录）

下面的名称是 UI 表单使用的 property 名称；Node 的 `__init__()` 实际写入对应的
私有字段，例如 `name` 写入 `_name`，集合写入 `_parts` 或 `_components`。

| 类 | 构造属性 |
|---|---|
| `GeometryNode` | `parts`：`PartNode` 集合 |
| `PartNode` | `name`、`part_type`、普通 Part 的必填 `element_name` 或 OffsetShellPart 的两个元素名称、`exterior_surface`、源数据和 `instances` |
| `InstanceNode` | `name`、`translation`、`rotation` |
| `MaterialNode` | `name`、`part_name`、`element_name`、接口类型和材料参数 |
| `FEANode` | FEA component 集合、ReferencePoint 集合和 load steps |
| `FEAComponentNode` | `name`、组件类型、目标名称、初始值和组件参数 |
| `LoadStepsNode` | step 数量和组件值矩阵 |
| `ObjectiveNode` | objective code、metrics code 和 Jacobian 名称 |
| `UpdaterNode` | `name`、`target_kind`、`target_name`、updater 类型和目标项 |
| `SolverNode` | process、GPU devices 和 task groups |

#### 运行时属性（`__init__()` 声明，生成或校验时填充）

各 Node 统一声明以下运行时属性：`_definition`（初始为 None，用于缓存对应的
MorphOpt 定义对象）、`_validation_errors`（初始为空列表）和 `_initialized`
（初始为 False）。`build_definition()` 或 `ProblemDefinition.generate_python()`
时填充 `_definition`；表单编辑只修改构造属性。

#### 属性接口（property）

各 Node 的表单字段都通过 property 暴露。名称、类型、路径、目标名称、参数和数值
字段均为“可读、可写”，setter 执行类型转换和局部校验；派生的 `_definition`、
`_validation_errors` 和 `_initialized` 为“只读、不提供写入”。集合字段返回 tuple 或
只读视图，元素增删统一使用 `ProblemDefinition` 的 `add_*()`、`remove_*()` 方法。

#### 外部接口方法

| 类 | 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|---|
| `GeometryNode` | build_definition() | `GeometryParams` | - | 创建几何定义 |
| `PartNode` | build_definition() | `BasePartDefinition` | - | 创建对应 Part 定义 |
| `InstanceNode` | build_definition() | `InstanceDefinition` | - | 创建 Instance 定义 |
| `MaterialNode` | build_definition() | `MaterialAssignment` | - | 创建材料分配 |
| `FEANode` | build_definition() | `FEAParams` | - | 创建 FEA 定义 |
| `FEAComponentNode` | build_definition() | `BaseFEAComponent` | - | 创建 FEA component |
| `LoadStepsNode` | build_definition() | `tuple[LoadStep, ...]` | - | 创建 load step 定义 |
| `ObjectiveNode` | build_definition() | `ObjectiveFunction` | - | 创建目标定义 |
| `UpdaterNode` | build_definition() | `UpdaterEntry` | - | 创建 updater 注册项 |
| `SolverNode` | build_definition() | `Solver` | - | 创建 solver 配置 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | Node 的字段转换和校验通过外部 `build_definition()` 接口完成 |

### 16.2 `ProblemDefinition` 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| add_part(part_node) | None | - | 添加 `Part` |
| remove_part(part_name) | None | - | 删除 `Part` 和相关引用 |
| add_instance(part_name, instance_node) | None | - | 添加 `Instance` |
| remove_instance(part_name, instance_name) | None | - | 删除 `Instance` |
| add_material(material_node) | None | - | 添加材料 |
| remove_material(material_name) | None | - | 删除材料和 updater 引用 |
| add_fea_component(component_node) | None | - | 添加 FEA component |
| rename_fea_component(old, new) | None | - | 级联更新 load steps 和 Jacobian |
| add_updater(updater_node) | None | - | 添加任意类型的 updater，并保存目标类别和目标名称 |
| validate() | None | - | 执行完整定义校验 |
| generate_python() | str | - | 生成可直接运行的任务定义源码 |

### 16.2 `ProblemDefinition` 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | 本类的级联维护和校验通过外部接口完成 |

### 16.3 `Part` 编辑器

| `Part` 类型 | 编辑属性 |
|---|---|
| `BoundaryPart` | element_name、曲面顺序、外表面、网格参数、曲面代码、约束代码 |
| `INPPart` | element_name、INP 路径、源 `Part`、外表面、Instances |
| `TorchFEAUIPart` | element_name、模型目录、文件名、源 `Part`、外表面、Instances |
| `OffsetShellPart` | `solid_element_name`、`shell_element_name`、`BoundaryPart` 属性、源曲面、厚度、层数、方向 |

`Instance` 编辑器只编辑名称、translation 和 rotation。外表面由 `Part` 编辑器编辑。
`BoundaryPart` 的外表面选项包含每个 BSP 自动生成的
`surface_{i}_head`、`surface_{i}_bottom`、`surface_{i}_lateral` 和
`surface_{i}_all`，每个 CPGEO 自动生成的 `surface_{i}_all`，以及由
`exterior_surface` 命名的整体集合；默认名称为 `extern`。用户修改名称时，生成的
整体外表面集合同步使用新名称。

### 16.4 材料编辑器

材料编辑器按以下顺序提供选项：

1. 选择 part_name；
2. 从目标 `Part` 的 elems 选择 element_name；
3. 选择全选或具体元素族；
4. 选择 `HomogeneousMaterial` 或 `SIMPFieldMaterial`；
5. 选择参数类并填写全部参数；
6. 填写接口类型的附加字段。

全选的代码值为 ""。元素选项来自真实 `Part` 的 elems。形状优化页面显示几何
变量和几何约束；密度场、材料场和 `VolFrac` 只在 `SIMPFieldMaterial` 页面显示。

### 16.5 FEA 编辑器

| 编辑内容 | 目标选择 |
|---|---|
| Pressure/Contact | `Instance` + surface set |
| BoundaryCondition/Couple | `Instance` + node set |
| Bodyforce | `Instance` + element_name |
| `ReferencePoint` | RP 名称和位置 |
| ConcentratedForce/Moment | Reference point |
| Load step | FEA component 名称和 step 值 |

rename_fea_component 级联更新 load step、Jacobian 和代码槽引用。

### 16.6 Updater 编辑器

~~~text
Geometry updater: chamber_shape → Part: chamber
Geometry updater: shell_shape → Part: shell
Material updater: solid_density → Material: solid (chamber / C3D4)
FEA updater: pressure_shape → FEA component: pressure_1
Custom updater: custom_name → custom target: custom_target
~~~

`UpdaterNode` 的目标选项由 `target_kind` 决定：几何目标来自 Geometry Parts，材料目标
来自 Materials，载荷目标来自可设计 FEA components，用户扩展目标来自对应扩展注册表。
编辑器允许添加任意数量的 updater，同一种类可以有多个目标。

## 17. Codegen 和任务定义文件

### 17.1 Codegen 类

| 类/方法 | 实例属性 | 方法 | 来源 |
|---|---|---|---|
| `CodeGenerator` | 当前 `ProblemDefinition` | generate_source(problem) -> str | - |
| `SchemeTemplate` | 模板名称、标签、默认节点 | build_root() -> `ProblemDefinition` | - |
| `PartTemplate` | `Part` 类型和字段定义 | create_part(data) -> `PartNode` | - |
| `MaterialTemplate` | 材料接口和参数类 | create_material(data) -> `MaterialNode` | - |
| `UpdaterTemplate` | updater 类型和字段 | create_updater(data) -> UpdaterNode | - |

#### 构造属性（`__init__()` 记录）

下面列出的是模板对象的 property 名称；实际构造状态写入同名的私有字段。

| 类 | 属性 | 说明 |
|---|---|---|
| `CodeGenerator` | `problem`、模板目录、输出配置 | 当前 UI 定义和生成规则 |
| `SchemeTemplate` | `name`、标签、默认节点工厂 | 一套 UI 初始结构 |
| `PartTemplate` | `part_type`、必填字段定义 | 一种 `Part` 的代码模板；普通 Part 包含必填 `element_name`，OffsetShellPart 包含两个元素名称 |
| `MaterialTemplate` | 接口类型、参数类、默认字段 | 一种材料接口的代码模板 |
| `UpdaterTemplate` | updater 类型、目标类别、字段定义 | 一种 updater 的代码模板 |

#### 运行时属性（`__init__()` 声明，生成时填充）

| 类 | 属性 | 初始值 | 说明 |
|---|---|---|---|
| `CodeGenerator` | `_template_cache`、`_generated_source` | `{}`、None | 模板和最近生成源码缓存 |
| `SchemeTemplate`、各类模板 | `_field_schema` | None | 初始化后解析的字段描述 |

#### 属性接口（property）

| 类 | property | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `CodeGenerator` | `problem` | 只读 | 不提供 | 返回当前 UI 定义 |
| `CodeGenerator` | `generated_source` | 只读 | 不提供 | 返回最近生成源码 |
| `SchemeTemplate` | `name`、`label` | 只读 | 不提供 | 返回模板标识 |
| `PartTemplate`、`MaterialTemplate`、`UpdaterTemplate` | `field_schema` | 只读 | 不提供 | 返回字段定义只读视图 |

Codegen 对象只缓存模板解析和最近生成结果，不创建 TorchFEA 模型；模型构造仍由
生成的 Python 任务文件和 `initialize()` 完成。

#### 外部接口方法

| 类 | 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|---|
| `CodeGenerator` | generate_source(problem) | str | - | 生成任务定义源码 |
| `SchemeTemplate` | build_root() | `ProblemDefinition` | - | 创建 UI 初始节点树 |
| `PartTemplate` | create_part(data) | `PartNode` | - | 创建 Part 编辑节点 |
| `MaterialTemplate` | create_material(data) | `MaterialNode` | - | 创建材料编辑节点 |
| `UpdaterTemplate` | create_updater(data) | `UpdaterNode` | - | 创建 updater 编辑节点 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 无 | - | Codegen 模板转换通过上述外部接口完成 |

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
- 普通 `PartNode` 生成显式的 `element_name` 参数；`OffsetShellPart` 生成显式的
  `solid_element_name` 和 `shell_element_name` 参数，空字符串和省略都不是合法值；
- 一个 `Part` 下的每个 `InstanceNode` 生成一个 `InstanceDefinition`；
- 一个 `MaterialNode` 生成一次 add_material；
- 参数类直接表达材料模型；
- 全选生成 element_name=""；
- 一个 updater node 生成一个目标绑定；
- 局部代码槽写回对应 `Part`、`ObjectiveFunction` 或 updater 子类。

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

运行结果与任务定义分开管理。结果文件服务于日志和 UI 展示，不能替代任务文件，
也不负责恢复用户自定义类和方法。

### 17.4 状态保存和历史读取

`Persistable` 是显式的文件 I/O 协议，不负责通用对象恢复。实现该协议的对象只
保存自己负责的数据：

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

## 18. 校验规则

### 18.1 Geometry

- part_name 非空且唯一；
- 普通 `Part` 的 `element_name` 非空且由构造函数显式传入；
- `OffsetShellPart` 的 `solid_element_name` 和 `shell_element_name` 都非空、彼此不同，
  且由构造函数显式传入；
- instance_name 非空且在整个 `Assembly` 中唯一；
- 每个 `Part` 至少有一个 `Instance`；
- exterior_surface 存在于目标 `Part`；
- translation 和 rotation 都包含三个浮点分量；
- `Part` 构建后包含与其元素名称集合对应的有效元素和必要集合。

### 18.2 Materials

- material_name 非空且唯一；
- 材料目标 `Part` 存在；
- element_name 为空或精确存在于目标 `Part` 的 elems；
- 一个 `Part` 的每个元素族恰好被一个材料分配覆盖；
- 材料范围不重叠；
- 均匀材料参数对象必填；
- SIMP 参数、控制点和元素映射维度一致。

### 18.3 FEA

- FEA component 名称唯一；
- `Instance`、surface、node set、element set 和 RP 都存在；
- 每个 load step 包含全部 FEA component；
- 值向量长度等于 num_values；
- Jacobian 名称引用已注册 FEA component；
- task groups 完整覆盖 step，索引不重复、不越界。

### 18.4 `Updaters`

- 每个 `UpdaterEntry` 的 `target_kind` 和 `target_name` 都能解析到真实目标；
- 内置 updater 的目标类型与 `target_kind` 匹配；
- 每个 updater 目标具有非空设计变量；
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
    │   ├── torchfeauipart.py
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
| shapeopt.update_geometry | `GeometryUpdater` |
| simp.simpmaterial | `SIMPFieldMaterial` |
| simp.update_material | `MaterialUpdater` |
| codesign.geometry | `OffsetShellPart` |
| FEA 中的 INP 导入 | `INPPart` |
| 固定 TorchFEA `Assembly` | `TorchFEAUIPart` |
| `Params` 三大变量分块 | `DesignRegistry` |

迁移后删除旧的 shapeopt/simp/codesign 聚合更新器、重复材料包装类和旧字段。
旧类名不通过兼容导出继续存在。

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
- `INPPart` 和 `TorchFEAUIPart` 导入指定源 `Part`；
- 每个 BSP 曲面自动生成 `surface_{i}_head`、`surface_{i}_bottom`、
  `surface_{i}_lateral` 和 `surface_{i}_all` 四个 surface set；
- 每个 CPGEO 曲面只生成 `surface_{i}_all`，不生成顶面、底面和侧面集合；
- `BoundaryPart.exterior_surface` 默认值为 `extern`，其集合内容为
  `surface_0_all + surface_1_all + ...`；用户自定义名称后，整体集合使用该名称；
- `OffsetShellPart` 生成并更新偏置节点、元素和表面；
- `get_assembly()` 返回最近一次 `build_assembly()` 的结果。

### 20.2 Materials

- 每个参数类创建正确的 TorchFEA 本构类；
- 缺少材料参数时立即报错；
- `HomogeneousMaterial` 覆盖目标元素族；
- 空 element_name 覆盖全部元素族；
- 材料覆盖重叠或缺失时初始化失败；
- SIMP 控制点、材料场、材料比例和元素写回一致；
- SIMP 专属方法只出现在 `SIMPFieldMaterial`。

### 20.3 FEA、`Solver` 和 Objective

- FEA component 的目标名称解析正确；
- create_fea 一次性创建对象，process_fea 更新工况值；
- 多工况结果按 step index 返回；
- CPU/GPU 结果结构一致；
- 不收敛结果带正确 step index；
- `ObjectiveFunction` 返回标量目标；
- metrics 不进入设计变量梯度；
- Jacobian 引用错误时初始化失败。

### 20.4 `DesignRegistry` 和 Updater

- geometry、material 和联合变量 offsets 正确；
- 无论注册调用顺序如何，完整变量顺序始终为 geometry → material → load；
- 每个类别内部按目标名称字典序排列，新增或删除其他类别变量不会改变同类别内的名称顺序；
- `values()` 和 `split()` 使用同一排序结果；
- trial design delta 通过 `update_assembly()` 回写到正确的 `Part`、材料接口或 FEA component；
- updater 梯度不串块；
- 一个变量不能绑定两个 updater；
- 任一 updater 失败时不提交其他 updater 的变化；
- 无 updater 的 owner 保持固定并参与 FEA。

### 20.5 UI 和运行结果

- UI 创建 `BoundaryPart`、`INPPart`、`TorchFEAUIPart` 和 `OffsetShellPart`；
- 一个 `Part` 创建多个 `Instance`；
- 材料元素选择来自真实 `Part.elems`；
- UI 全选和生成代码都使用空字符串；
- UI 支持添加任意数量的 updater，并允许多个同类 updater 同时存在；
- Python 源码能够重建类型、属性、名称、代码槽和初始 Tensor 状态；
- 构造阶段不读取 INP、不创建 `Assembly`、不启动 UI 或 worker pool；
- `initialize()` 后所有源数据、运行时缓存、FEA 对象和 updater 绑定完整可用；
- 每次运行从任务文件建立一致的初始设计变量、材料场和 updater 状态；
- 生成脚本可以独立 headless 运行。

### 20.6 状态恢复和后处理

- `Persistable.save()` 为每个 iteration 写入对应对象负责的状态和结果；
- 任务文件初始化完成后，`Persistable.load()` 能恢复设计变量、optimizer memory 和历史指标；
- `Controller.restart_optimization()` 按任务文件、`initialize()`、状态加载的顺序继续优化；
- 后处理可以直接读取 `History` 和结果文件，不创建优化器；
- 用户自定义曲面、约束和目标方法仍由任务 Python 文件提供。

## 21. 实施顺序

### 阶段 1：`Part` 和 `Assembly`

建立 partinterface 和 feacomponent，实现 `BasePartDefinition`、`InstanceDefinition`、`BoundaryPart`、
`INPPart`、`TorchFEAUIPart` 和 `OffsetShellPart`，重写 `GeometryParams`。

### 阶段 2：材料系统

重写 `MaterialModels`、`MaterialsParams`、`HomogeneousMaterial` 和
`SIMPFieldMaterial`，完成 `Part`/Elems 覆盖校验。

### 阶段 3：FEA 和 `Params`

统一 FEA component、load steps、`Params.create_feamodel` 和 FEA 名称校验，
将几何导入逻辑迁移到对应 `Part`。

### 阶段 4：`DesignRegistry` 和 Updater

实现变量注册、切分和试探回写，将现有几何 updater、材料 updater 改为单目标
绑定，接通 `ObjectiveFunction` 灵敏度。

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
GeometryParams.add_part(part)
MaterialsParams.add_material(part_name, interface, material_name)
FEAParams.add_component(component, fea_component_name)
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

GeometryUpdater body_shape
    target = Part body

MaterialUpdater body_density
    target = Material body_solid
~~~

几何、材料、载荷和更新策略通过名称组合成一个 FEA/优化问题。shapeopt、simp
和 codesign 的差别只在于注册的对象组合。

## 待确认

当前只保留两个外部行为待确认：

1. `TorchFEAUIPart` 第一版读取导出的 TorchFEA 模型文件，不在优化进程启动 GUI；
2. 材料覆盖强制要求每个 `Part` 的每个 elems 都恰好被一个材料分配覆盖。

其余类属性、方法、调用顺序、名称规则和模块边界作为实现约束。
