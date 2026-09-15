# MorphOpt 统一模型架构设计文档

> 状态：V4 设计规范稿，按核心功能拆分，主题文档是实现的唯一接口依据。
>
> 本文件是总入口，具体设计放在 `unified_model_architecture/` 下的主题文档中。
> 实现阶段按这些接口执行，V4 使用新的接口体系。

编码、命名、文件组织和 Review 规则见[《MorphOpt V4 编码规范》](style.md)。

## 文档导航与输入/输出摘要

本文是 V4 文档总入口，提供主题文档阅读顺序、按任务查找表和全局维护规则；每个主题文件
在开头继续提供自己的章节目录与输入/输出摘要。

| 项目 | 内容 |
|---|---|
| 输入 | V4 架构主题文档、编码规范、迁移清单和待确认设计决策 |
| 输出 | 文档导航、接口权威关系、任务查找入口和跨文档维护规则 |
| 主要读者 | 全体 V4 开发者、review 者和后续接手项目的维护者 |

### 目录

- [阅读顺序](#阅读顺序)：规范性设计文档和维护性迁移文档
- [按任务查找](#按任务查找)：按功能定位主题文件
- [全局维护规则](#全局维护规则)：接口、方法语义、文档同步和 review 约束

## 阅读顺序

### 规范性设计文档

1. [总览、全局规则与生命周期（第 1–4 章）](unified_model_architecture/01-04Overview.md)
2. [几何系统与曲面导出（第 5 章）](unified_model_architecture/05Geometry.md)
3. [材料系统（第 6 章）](unified_model_architecture/06Materials.md)
4. [FEA 组件与载荷（第 7 章）](unified_model_architecture/07Fea.md)
5. [Solver（第 8 章）](unified_model_architecture/08Solver.md)
6. [目标函数（第 9 章）](unified_model_architecture/09Objective.md)
7. [设计变量注册与试探回写（第 10 章）](unified_model_architecture/10DesignRegistry.md)
8. [Updater 与联合更新（第 11–12 章）](unified_model_architecture/11-12Updaters.md)
9. [Params、Controller 与主循环（第 13–14 章）](unified_model_architecture/13-14Runtime.md)
10. [History 运行记录（第 15 章）](unified_model_architecture/15History.md)
11. [UI 数据模型与 Codegen（第 16–17 章）](unified_model_architecture/16-17UiCodegen.md)
### 维护性迁移文档

12. [校验、迁移、验收与实施顺序（第 18–22 章）](unified_model_architecture/18-22ValidationMigration.md)
13. [功能基线与类迁移清单（第 23 章）](unified_model_architecture/23FunctionInventory.md)
14. [破坏性变更、移除清单与冻结契约（第 24 章）](unified_model_architecture/24BreakingChanges.md)

第 1–17 章定义 V4 的最终类、属性、方法和调用关系；第 18–23 章记录实现校验、旧功能
映射、迁移阶段和验收状态。迁移文档引用设计文档中的接口，规范性接口完整定义在主题
设计文档中。

## 按任务查找

| 任务 | 文档 |
|---|---|
| 修改对象命名、属性权限、协议继承或生命周期 | [01-04Overview.md](unified_model_architecture/01-04Overview.md) |
| 修改 Part、Instance、BoundaryPart、曲面或 STP/STL 导出 | [05Geometry.md](unified_model_architecture/05Geometry.md) |
| 修改材料模型、材料分配或 SIMP 材料场 | [06Materials.md](unified_model_architecture/06Materials.md) |
| 修改载荷、边界条件或工况 | [07Fea.md](unified_model_architecture/07Fea.md) |
| 修改 Solver、StaticImplicitSolver 或求解流程 | [08Solver.md](unified_model_architecture/08Solver.md) |
| 修改 Assembly 级参考点 | [05Geometry.md](unified_model_architecture/05Geometry.md) |
| 修改目标函数、指标或 Jacobian | [09Objective.md](unified_model_architecture/09Objective.md) |
| 修改 History 和运行记录 | [15History.md](unified_model_architecture/15History.md) |
| 修改局部灵敏度目标、几何/材料/载荷约束和 Fairness | [11-12Updaters.md](unified_model_architecture/11-12Updaters.md) |
| 修改设计变量顺序、offsets、梯度切分或试探更新 | [10DesignRegistry.md](unified_model_architecture/10DesignRegistry.md) |
| 修改 BoundaryPart/OffsetShellPart/Material/FEA updater 或联合更新 | [11-12Updaters.md](unified_model_architecture/11-12Updaters.md) |
| 修改 Params、Controller 或主循环 | [13-14Runtime.md](unified_model_architecture/13-14Runtime.md) |
| 修改 UI 节点、编辑器、代码生成或任务文件 | [16-17UiCodegen.md](unified_model_architecture/16-17UiCodegen.md) |
| 修改校验规则、迁移范围、测试验收或实施阶段 | [18-22ValidationMigration.md](unified_model_architecture/18-22ValidationMigration.md) |
| 维护旧版功能到 V4 的映射 | [23FunctionInventory.md](unified_model_architecture/23FunctionInventory.md) |
| 查询移除项、行为变更、结果与数值契约 | [24BreakingChanges.md](unified_model_architecture/24BreakingChanges.md) |

## 全局维护规则

- 编码实现遵循[《MorphOpt V4 编码规范》](style.md)。
- 构造属性统一通过同名 `property` 对外访问；运行时状态保留为私有字段，使用
  `build_*`、`get_*`、`export_*`、生命周期或持久化方法访问。
- 每个类的设计说明固定按“构造属性、运行时属性、属性接口、外部接口方法、内部辅助函数”
  的顺序组织；内容为空的区块保留空表，并明确标注“空”或继承范围。
- 子类表格列本类新增或重写的成员；继承成员以继承范围说明，空表保留。
  已列出的重写接口通过“来源”列标注最上层父类或协议定义位置，本类新增接口使用 `-`。
- `get_*` 执行已有结果的缓存读取；`set_*` 修改已有属性或定义；`add_*` 向已有
  `list`/`dict` 注册单项；`build_*` 从定义状态建立运行时属性并写入内部状态，方法返回
  `None`，结果通过对应的 `get_*` 读取；`update_*` 更新已有运行时属性；`compute_*`
  执行纯计算并直接返回结果；`generate_*` 直接返回生成的代码、文本或临时结果；
  `assign_*` 把已有对象挂接到已有目标；
  `apply_*` 正式提交待写回的变化；`export_*` 必须在方法名中明确导出对象，接收目标地址并写出文件。
- `create_*` 仅用于一次性的定义对象或编辑节点工厂，并直接返回新对象；运行时对象
  统一由 `build_*` 建立，结果由 `get_*` 读取。
- 注册表使用只读映射 property 作为唯一事实来源；单项访问统一使用
  `registry[name]`。
- 一个文件聚焦一个核心功能，跨文件关系通过本入口和文档内链接维护。
- 共享术语、属性权限、方法顺序和生命周期约定集中维护在 `01-04Overview.md`。
- 修改一个主题时同步检查相关交叉引用、最终接口关系和验收标准。
- 新增或重命名方法时先更新所属主题设计文档，再同步[功能基线与类迁移清单](unified_model_architecture/23FunctionInventory.md)、
  测试和代码；迁移清单记录对应的旧接口和迁移状态，不定义新的公共接口。
- 设计主题文档与迁移文档发生表述差异时，以主题设计文档为准，迁移文档只更新映射和状态。
- 架构描述采用职责导向的正向表述，直接写清输入、输出、状态和调用时机。
- 新增接口时同时更新所属主题文件、总入口任务表和对应验收标准。
