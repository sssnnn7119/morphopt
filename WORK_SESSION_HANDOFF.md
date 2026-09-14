# MorphOpt 工作交接记录

日期：2026-09-13
项目：`morphopt`  适用分支：当前工作区

这份文件用于明天换电脑后恢复本次设计讨论和开发上下文。它记录的是本次会话中已经确定的架构、命名、文档修改和后续实施方向。

## 零、V4 重构边界（2026-09-14）

当前项目进入 MorphOpt 大版本 4 的重新设计阶段。原有代码整体视为 MorphOpt
V3，旧代码已经移动到 `src/morphopt3`，仅作为功能、算法、输入输出和运行行为的
只读参考；V4 不承担旧接口兼容义务。

V4 的工作目录是当前空的 `src/morphopt` 目录。后续实现必须在这里从新的模块边界和对象
模型开始编程，允许删除、重命名、拆分和合并旧类，允许破坏性修改所有旧调用方式。
迁移时保留的是 V3 已验证的功能语义，而不是旧目录结构或旧 API 形状。

本阶段设计文档仍在继续完善。在用户确认最终设计前，不提前大规模迁移实现；任何
暂时性代码都不能反过来限制架构设计。开始实施后，优先建立 V4 的基础协议、对象模型、
生命周期和测试骨架，再按设计文档迁移 V3 的功能。

### V4 工作原则

- `morphopt3` 只用于查阅和行为对照，不作为 V4 的运行时依赖；
- V4 不提供兼容层、旧类名别名或旧目录转发；
- 功能迁移以 V3 的实际行为、示例和测试为依据，接口以 V4 设计文档为唯一依据；
- TorchFEA 是外部有限元后端，MorphOpt V4 负责统一的任务定义、设计变量、优化调度和 UI/Codegen 边界；
- 任何新实现都要明确区分定义状态、初始化后的运行时状态和优化迭代状态；
- 设计文档未确认的内容先记录为待决策项，不通过代码猜测并固化。

### V4 后续启动检查

正式编码前应确认：

1. V3 是否完整保留在 `src/morphopt3`，V4 的 `src/morphopt` 是否只保留新实现所需的空工程文件；
2. V4 的目录结构、公共协议和核心类名是否已在设计文档中冻结；
3. TorchFEA 的导入边界、模型保存/恢复边界以及 `Part`/`Instance`/Assembly 所有权是否已确定；
4. 破坏性迁移的验收测试是否已经根据 V3 功能建立，而不是直接复制 V3 的内部测试实现。

## 一、当前核心目标

将 `shapeopt`、`simp` 和 `codesign` 统一到一个自由组合的模型架构中：

- 几何、材料、载荷/边界条件分别由独立定义对象维护；
- 一个优化问题可以同时包含几何优化和材料优化；
- 所有可更新对象都通过 updater 注册和调度；
- 一个 `Part` 可以定义多个 `Instance`；
- 几何、材料、载荷之间不再使用固定的三大类 updater 数量，而是允许注册任意数量、任意目标类型的 updater；
- 构造函数只记录定义状态，`initialize()` 才执行文件读取、网格生成、对象绑定、缓存建立和其他重计算；
- 不考虑兼容性，允许大幅删改旧接口，以获得更简单的代码结构。

## 二、已经确定的总体架构

### 1. 几何

`GeometryParams` 维护一个按 `part_name` 索引的 `Part` 字典，并负责生成一个总的 `Assembly`。

几何定义基类为 `BasePartDefinition`，具体类型包括：

- `BoundaryPart`：由有序边界曲面生成网格；
- `INPPart`：从 INP 文件导入；
- `TorchFEAUIPart`：从 TorchFEA UI 定义或导入；
- `OffsetShellPart`：由实体几何生成偏置壳。

每个 `Part`：

- 构造函数必须传入元素名称；普通 Part 使用必填 `element_name`；
- `OffsetShellPart` 必须分别传入 `solid_element_name` 和 `shell_element_name`，因为实体和壳不能共用元素名称；
- `exterior_surface` 默认值为 `'extern'`；
- 可以维护多个 `Instance`；没有显式 Instance 时默认创建一个与 `part_name` 同名、零变换的 Instance；
- `Part` 的公共构造属性使用 `_` 前缀，外部需要访问的内容用 property 暴露。

构造和运行时分离：

```text
Part.__init__()       只记录名称、元素名、曲面定义、Instance 和参数
Part.initialize()     读取源数据、创建曲面/网格、建立运行时缓存
GeometryParams.build_assembly()
                      构建所有 Part、Instance 和总 Assembly
GeometryParams.update_assembly()
                      在已有 Assembly 上进行保留计算图的试探更新
```

### 2. 曲面

`BaseSurfaceInterface` 是曲面定义基类，具体类型为：

- `BSPSurface`；
- `CPGEOSurface`；
- `STLSurface`。

曲面类型的具体构造参数由子类自己定义，不能把所有参数放在基类的通用 `parameters` 字典中。`flip` 定义在基类，因为它决定曲面法向量朝外还是朝内。

形状类型：

- `BSPCylinderSurface`：圆柱半径、长度、seed size、比例、阶数、初始位置、曲率和 fairness 参数等；
- `CPGEOCylinderSurface`：圆柱网格和 CPGEO 参数；
- `CPGEOSphereSurface`：球面半径、采样尺寸和初始位置等；
- `STLSurface`：STL 路径和缩放比例。

曲面集合规则：

- BSP 曲面自动注册 `surface_{i}_head`、`surface_{i}_bottom`、`surface_{i}_lateral`、`surface_{i}_all`；
- CPGEO 只注册 `surface_{i}_all`；
- STL 只有整体曲面集合；
- `BoundaryPart.exterior_surface` 默认是 `'extern'`，它对应所有曲面 `surface_{i}_all` 的全集；
- 如果用户修改 `exterior_surface`，整体集合使用用户定义的名称；
- `register_surface_sets()` 属于内部辅助逻辑，统一使用 `_register_surface_sets()`。

Fairness、曲率和距离约束归属于 `GeometryUpdater` 的约束对象。不同曲面类型使用不同 evaluator：

- BSP 使用 `BSPFairnessEvaluator`；
- CPGEO 使用 `CPGEOFairnessEvaluator`；
- STL 不提供 Fairness evaluator。

曲面只提供几何数据、控制点、导数和权重；约束计算由 updater/evaluator 读取这些数据完成。

### 3. 材料

`MaterialsParams` 维护材料分配集合。每条 `MaterialAssignment` 明确绑定：

```text
材料名称 → part_name → element_name → 材料接口
```

材料的 `element_name`：

- 空字符串表示选择该 Part 的全部元素族；
- 非空字符串必须精确匹配 `Part.elems` 中的元素名称；
- UI 中保留一个“全选”选项，代码值就是空字符串；
- UI 模型树命名必须明确反映 `part` 和 `elem`。

材料接口基类为 `BaseMaterialInterface`，主要实现：

- `HomogeneousMaterial`：均匀材料，没有设计变量；
- `SIMPFieldMaterial`：SIMP/BSP 材料场，提供材料设计变量和材料场可视化。

材料密度放在基类，默认值为 `0.0`。材料参数不能有默认值，构造时必须显式提供。

材料模型参数类直接表达模型类型，例如：

- `LinearElasticParams`；
- `NeoHookeanParams`；
- `NeoHookeanLnJParams`；
- `MooneyRivlinParams`；
- `YeohParams`；
- `GentParams`；
- `ArrudaBoyceParams`；
- `OgdenParams`。

材料参数对象自身已经包含对应材料模型的意义，因此用户不再重复传入 `material_model` 字符串。默认材料模型为 `NeoHookeanLnJ`，但参数字段仍然必须显式提供。

材料模型命名空间放在 `MaterialsParams` 内部，通过类似下面的形式访问：

```python
self.materialmodels.NeoHookeanLnJParams(mu=..., kappa=...)
```

不要在 `morphopt` 顶层暴露材料模型，也不要使用同名别名赋值或重复的 `HomogeneousMaterial = HomogeneousMaterial` 风格导出。

### 4. FEA、载荷和边界

原来的 `FEAInterface` 命名不够明确，统一使用与有限元载荷、边界和分析组件相关的 `FEAComponent` 命名：

- `BaseFEAComponent`；
- 具体载荷、边界、接触、参考点和弹簧组件；
- `FEAParams` 维护组件、参考点和 load steps。

`build_assembly()`、`assign_material()` 和 `create_fea()` 直接作为三个领域基类/领域对象的核心功能，不再额外拆成 `PartBuilder`、`MaterialAssigner`、`FEAComponentBuilder` 三个独立协议。

### 5. DesignRegistry

`DesignRegistry` 管理所有设计变量块。设计变量顺序固定为：

1. 几何；
2. 材料；
3. 载荷。

每一类内部按目标名称字典序排序。`DesignKey` 标识变量块，`DesignBlock` 保存变量范围和 owner。

核心方法职责：

- `get_parameters()` / `set_parameters()`：直接导出/导入内部参数，使用 detached clone；
- `get_design_delta()`：返回全 0、保留 autograd 的增量变量；
- `update_assembly()`：把增量写入已有 Assembly，保留计算图，供试探计算；
- `apply_design_delta()`：把优化结果正式写回 owner；
- `DesignRegistry.values()`：按固定顺序拼接增量；
- `DesignRegistry.split()`：按同一顺序切分增量或梯度。

`obtain_design_sensitivity_vars()` 不再保留。

### 6. Updaters

不预设只有 `GeometryUpdater`、`MaterialUpdater`、`FEAUpdater` 三种。可以存在：

- 多个几何 updater；
- 多个材料 updater；
- 多个载荷 updater；
- 用户自定义目标类型的 updater。

使用 `UpdaterEntry` 保存：

```text
updater_name + target_kind + target_name + updater_object
```

`Updaters.update()` 一次完成局部更新量计算和统一提交，不再拆成先 `update()`、后 `update_variables(changes)` 两步。所有 updater 成功后，才由 `DesignRegistry` 统一写回。

同一个优化问题只要注册对应 updater，就可以自由组合几何优化、材料优化和载荷优化；没有 updater 的对象保持固定但仍参与 FEA。

## 三、统一生命周期和可见性规则

### 1. 协议

保留显式继承，方便阅读和类型检查：

- `Visualizable`：提供 `get_meshes()`；
- `Initializable`：提供 `initialize()` 和 `reinitialize(iteration)`；
- `Persistable`：提供 `save()` 和 `load()`，用于优化过程恢复与后处理历史读取；
- `Updatable`：提供参数快照、设计增量、Assembly 试探更新和正式提交。

三个领域基类显式继承共同协议：

```text
BasePartDefinition       → Visualizable, Initializable, Persistable
BaseMaterialInterface    → Visualizable, Initializable, Persistable
BaseFEAComponent         → Visualizable, Initializable, Persistable
```

### 2. 构造和初始化

所有类分为两种属性：

1. 构造函数记录的属性：用户定义、注册关系和参数，使用 `_` 前缀；
2. `initialize()` 生成的属性：网格、缓存、TorchFEA 对象、解析引用和运行时状态，也在构造函数中先声明为 `None`、空列表或空字典。

对外暴露的内容通过 property 提供，并在文档中明确读权限和写权限。构造属性和运行时属性不直接暴露，防止外部绕过注册流程修改内部状态。

### 3. 方法命名和方法表

每个类的方法分成两张表，顺序固定为：

1. 外部接口方法：不使用前导 `_`，供其他对象、任务定义类、updater、UI、求解器和后处理调用；
2. 内部辅助函数：使用一个前导 `_`，只服务于本类内部流程。

协议方法也放在外部接口表中，并增加“来源”列。没有内部辅助函数的类在第二张表中明确写“无”。

## 四、当前设计文档修改状态

主要设计文档：

[`docs/codestructure/unified_model_architecture_plan.md`](docs/codestructure/unified_model_architecture_plan.md)

该文档已经包含：

- 统一几何、材料、FEA、目标、变量和 updater 架构；
- 每个主要类的构造属性、运行时属性和 property 三类说明；
- property 的读写权限；
- 外部接口方法和内部辅助函数两张表；
- 协议来源列；
- 多 Instance、OffsetShellPart 双元素名、BSP/CPGEO/STL 曲面规则；
- 材料的 part/element 选择和 UI 全选空字符串规则；
- DesignRegistry 排序和统一更新流程；
- UI 数据模型、Codegen、迁移范围和验收标准。

最近一次检查结果：

```text
外部接口方法表：38
内部辅助函数表：38
Markdown 空白检查：通过
```

## 五、当前工作区状态

最后一次检查得到：

```text
?? docs/codestructure/unified_model_architecture_plan.md
?? src/morphopt/codesign/
```

`src/morphopt/codesign/` 是此前已有的用户工作内容，本次没有修改。设计文档目前是未跟踪文件，换电脑时需要一并复制或提交。

## 六、明天建议的实施顺序

1. 先阅读本文件和 `unified_model_architecture_plan.md`；
2. 盘点现有 `src/morphopt`、`examples`、`myjobs`、`tests` 和 UI 代码，标出旧接口；
3. 先建立 `optcore/protocols.py` 和新的 `partinterface`、`materialinterface`、`feacomponent` 目录结构；
4. 实现轻量构造函数和统一 `initialize()` 生命周期；
5. 迁移 `GeometryParams`、Part/Instance 和 `build_assembly()`；
6. 迁移材料分配、SIMP 材料场和材料模型参数；
7. 迁移 FEA component、load step 和 solver；
8. 实现 `DesignRegistry` 的几何 → 材料 → 载荷排序；
9. 实现任意数量 updater 的注册、梯度分发、一次性更新和提交；
10. 修改 `Params`、`Controller`、Objective/Constraint、examples、myjobs、tests 和 UI；
11. 最后删除旧兼容层和重复聚合更新器，运行全量测试。

## 七、编码偏好

- 不考虑旧接口兼容性，优先简化结构；
- 所有新函数显式标注参数和返回值类型；
- 内部方法统一使用 `_` 前缀；
- 对外状态优先使用只读 property；
- 不把曲面专用参数塞进基类通用字典；
- 不为材料参数设置默认值；
- `part_name` 和普通 Part 的 `element_name` 按最终架构的必填规则处理；
- UI、examples、myjobs、tests 和文档必须同步迁移；
- 代码示例和文档中的类名、方法名使用 Markdown 代码格式。

## 八、会话结束点

本次最后完成的工作是：把设计文档中各类的方法统一拆成“外部接口方法”和“内部辅助函数”两张表，并检查两类表数量一致。下一步应开始按照设计文档改造实际 Python 代码，而不是继续扩展设计文档。
