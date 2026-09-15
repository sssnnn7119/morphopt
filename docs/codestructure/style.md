# MorphOpt V4 编码规范

> 状态：V4 实现与 review 的正式规范。
>
> 本文规定代码命名、模块边界、对象生命周期、Tensor 使用、UI 分层、测试和文档格式。
> 架构细节以 V4 主题文档为准；本文件统一约束代码、测试和文档写法。

## 文档导航与输入/输出摘要

本文是 V4 的编码、测试、文档和 review 规范，约束标识符命名、模块组织、类生命周期、
Tensor/FEA 数据处理、UI 分层、错误日志、持久化、pytest 测试和文档维护方式。

### 目录

- [1. 基本原则](#1-基本原则)
- [2. 命名规则](#2-命名规则)
- [3–5. 模块、类型、类设计与生命周期](#3-文件和模块组织)
- [6–9. Tensor、UI、日志、持久化和生成文件](#6-tensor-autograd-和-fea-数据)
- [10. 测试规范](#10-测试规范)
- [11–12. 文档与 Review](#11-文档与-review-规范)
- [13. 工具链和质量门禁](#13-工具链和质量门禁)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | Python 模块、领域对象、Tensor/FEA 数据、UI/Codegen 文件和测试代码 |
| 输出 | 统一命名、模块边界、生命周期、测试目录、pytest 约定和 review 清单 |
| 主要读者 | V4 实现者、测试编写者、UI/Codegen 开发者和 review 者 |
| 关联文档 | [架构总入口](unified_model_architecture_plan.md)、[总览与生命周期](unified_model_architecture/01-04Overview.md) |

## 1. 基本原则

- 一个模块围绕一个清晰的职责组织代码。
- 一个类表达一个稳定的领域概念；一个公开方法完成一个完整动作。
- 数据流、生命周期和依赖关系通过显式参数表达。
- 运行时状态归属于对象实例；共享常量使用类级常量或模块常量。
- 公共接口先设计，再实现；属性、方法和协议保持命名稳定。
- 代码、变量、类名和日志字段使用英文；面向用户的 UI 文本通过 i18n 提供中英文。
- 复杂算法保留简短注释，注释说明原因、输入、输出和不变量。

## 2. 命名规则

### 2.1 文件名和模块名

| 对象 | 规则 | 示例 |
|---|---|---|
| Python 文件 | 简短小驼峰，优先单个英文单词 | `geometry.py`、`solver.py`、`codegen.py` |
| 多词文件 | 使用小驼峰，保持名称短小 | `designRegistry.py`、`torchfeaPart.py` |
| 包目录 | 小写单词，优先单个词语 | `geometry/`、`materials/`、`widgets/` |
| 测试文件 | 使用 `test` 前缀，主题部分采用小驼峰 | `testGeometry.py`、`testDesignRegistry.py` |
| 文档文件 | 小驼峰，优先单个词语 | `style.md`、`geometry.md` |

文件名表达模块职责；版本、临时状态和完成状态通过目录、字段或版本记录表达。

### 2.2 Python 标识符

| 标识符 | 规则 | 示例 |
|---|---|---|
| 变量 | `snake_case` | `design_delta`、`part_name` |
| 函数 | `snake_case` | `build_assembly()`、`get_meshes()` |
| 方法 | `snake_case` | `apply_design_delta()` |
| 类、协议、异常 | 大驼峰 `PascalCase` | `BoundaryPart`、`Initializable`、`ModelError` |
| 类型别名 | 大驼峰 | `SurfaceExportFormat`、`ElementMapping` |
| 常量 | 全大写下划线 | `DEFAULT_ELEMENT_NAME` |
| 私有成员 | 一个前导下划线；运行时后端对象按专用规则命名 | `_register_surface_sets()`、`_torchfea_Part` |
| 布尔量 | 使用正向 `is_`、`has_`、`can_`、`should_` 前缀 | `is_initialized`、`has_surface` |
| 集合 | 使用复数名词 | `parts`、`instances`、`load_steps` |
| 映射 | 使用 `_by_` 或 `_to_` 表达方向 | `materials_by_part`、`index_to_name` |

公共接口使用完整语义名称；领域通用缩写保留统一形式，例如 `FEA`、`STP`、`STL`、`UI`、
`GPU`、`SIMP`、`BSP` 和 `CPGEO`。名称的大小写在全库保持一致。

### 2.3 运行时后端对象命名

由几何、材料、参考点或 FEA component 创建并持有的 TorchFEA 对象，统一使用以下字段格式：

```text
_torchfea_<ConcreteName>
```

`<ConcreteName>` 使用具体后端对象的 PascalCase 名称，不使用实例业务名称。例如：

| 创建对象 | 私有字段 |
|---|---|
| `torchfea.Assembly` | `_torchfea_Assembly` |
| `torchfea.Part` | `_torchfea_Part` |
| `torchfea.Instance` | `_torchfea_Instance` |
| `torchfea.ReferencePoint` | `_torchfea_ReferencePoint` |
| 具体 TorchFEA 材料类（如 `LinearElastic`） | `_torchfea_LinearElastic` |
| `torchfea.loads.Pressure` | `_torchfea_Pressure` |
| `torchfea.solver.static.StaticImplicitSolver` | `_torchfea_StaticImplicitSolver` |

创建者在 `build_*()` 中写入该字段，读取者通过对应的 `get_*()` 获取。
同一对象的业务名称仍通过 `name`、`part_name` 或 `component_name` 保存，业务名称不拼接到
TorchFEA 后端字段名中。

### 2.4 名称语义

方法前缀按“读取已有结果、修改已有定义、建立运行时状态、更新运行时状态、文件 I/O”划分，
同一方法只承担一种前缀语义。方法表用“有/无”标记返回值和类属性更新：

| 前缀 | 语义 | 是否有返回值 | 是否更新类属性 | 典型示例 |
|---|---|---|---|---|
| `get_` | 读取已经存在的属性、缓存或计算结果 | 有 | 无 | `get_assembly()`、`get_geometry_values()`、`get_meshes()` |
| `set_` | 修改已经存在的构造属性或定义状态 | 无 | 有 | `set_parameters()`、`set_rotation()` |
| `add_` | 向已有 `list` 或 `dict` 注册一个单项 | 无 | 有 | `add_part()`、`add_material()` |
| `build_` | 从定义状态建立一个此前不存在的运行时属性 | 无 | 有 | `build_assembly()`、`build_fea()` |
| `update_` | 更新已经建立的运行时属性；对象使用自身缓存的 TorchFEA 引用和 Assembly | 无 | 有 | `update_assembly()`、`update_material_field()` |
| `assign_` | 将已经建立的对象或配置挂接到已有目标 | 无 | 有 | `assign_material()`、`assign_materials()` |
| `apply_` | 将待提交的变化正式写回已有定义或 owner | 无 | 有 | `apply_design_delta()`、updater 的 `_apply_equality_constraint()` |
| `compute_` | 重新计算一个结果 | 有 | 无 | `compute_jacobian()`、`compute_case_objective()` |
| `generate_` | 根据已有定义生成代码、文本或临时结果 | 有 | 无 | `generate_source()`、`generate_summary()` |
| `create_` | 创建一次性的定义对象或编辑节点工厂结果 | 有 | 无 | `create_part(data)`、`create_updater(data)` |
| `export_*` | 将已有定义或运行时结果写出为外部文件，方法名明确写出导出对象 | 有 | 无 | `export_surface(target_path)`、`export_model(file_path)` |

`get_` 与 `build_` 总是成对设计：`build_*` 完成建立并写入内部状态，`get_*` 只读取
该状态。读取前需要刷新结果时，调用者显式调用 `build_*` 或 `update_*`；刷新职责集中在
这些显式方法。构造阶段需要建立多个运行时字段时，使用 `initialize()` 或专用的
`build_*` 生命周期入口，完成后仍通过对应的 `get_*` 读取。

`compute_*` 用于需要重新计算且直接返回结果的纯计算；`generate_*` 用于根据定义生成代码、
文本或临时结果。两者都不替代运行时属性的 `build_*`/`update_*` 生命周期。

`initialize()`、`reinitialize()`、`apply_*`、`save()` 和 `load()` 是生命周期或协议名称，
按各自协议执行：它们显式改变对象状态，方法表中写明是否建立、刷新、提交或恢复状态。
运行时新对象统一使用 `build_*` 入口建立并写入内部状态。
- `*_name` 表示稳定名称，`*_path` 表示文件路径，`*_index` 表示整数索引。
- `*_names` 表示按稳定顺序排列的名称集合；Part 输出使用 `element_names`，材料接口的
  `element_name` 仍表示一个元素族选择。
- 同一概念使用同一个英文词；例如统一使用 `part_name`、`instance_name`、
  `element_name`、`surface_name` 和 `component_name`。

## 3. 文件和模块组织

推荐的依赖方向：

```text
ui
  → codegen / model
  → optcore
  → modelparams
  → torchfea / cpgeo / gmsh
```

- `modelparams` 保存问题定义和领域对象。
- `optcore` 管理设计变量、Updater、求解循环和结果历史。
- `ui` 负责编辑、预览、交互和任务源码生成。
- 外部库适配集中在领域边界模块中，核心对象直接依赖稳定的内部接口。
- 模块通过公开接口协作；跨模块访问运行时私有字段时增加明确的公开方法。
- `__init__.py` 只导出稳定公共接口，内部实现模块通过具体路径访问。
- 导入顺序固定为：标准库、第三方库、项目内部模块；各组之间保留空行。
- 使用绝对导入表达跨包依赖；同包局部导入保持短小清晰。
- 模块级副作用保持为零；资源初始化放入 `initialize()` 或明确的工厂函数。

## 4. 类型标注和数据结构

- 所有公开函数、公开方法和重要内部函数都写参数及返回值类型。
- `None` 作为明确的可选状态，使用 `T | None` 表达。
- 只读集合使用 `tuple`、`Mapping`、`Sequence` 或不可变视图；可变集合的所有权写在类文档中。
- 函数参数优先使用抽象类型，例如 `Mapping[str, object]`、`Sequence[float]` 和 `Path`。
- 默认参数使用 `None` 或不可变值；空列表、字典和集合在函数体内创建。
- `Any` 只用于外部库缺少类型信息的边界，并在注释中写明来源。
- 类型别名集中放在所属领域模块，名称采用大驼峰。
- `dataclass` 用于稳定的数据记录；拥有生命周期、缓存或后端对象的领域类使用普通类。
- property 只负责构造属性的稳定读取和受控写入；setter 执行类型、范围、名称和关联索引校验。
- 运行时缓存、后端句柄、初始化标志和求解状态通过明确的
  `build_*`、`get_*`、`export_*`、生命周期或持久化方法访问。
- `get_*` 读取已经建立且保持原状态的缓存结果。
- `build_*` 建立运行时属性并写入内部状态，方法返回 `None`；外部读取统一调用对应的
  `get_*`。`update_*` 修改已建立的运行时属性并写回内部状态。
- `set_*` 修改已有构造属性或定义状态；`add_*` 向已有 `list`/`dict` 注册一个单项。
- `export_*` 必须接收目标地址并写出文件；导出过程读取已有状态，模型建立由显式的
  `initialize()` 或 `build_*` 完成。
- 注册表使用只读 `Mapping` property 作为唯一事实来源；单项对象统一使用
  `registry[name]` 访问，不为同一映射重复定义 `get_<item>()`。

## 5. 类设计和生命周期

### 5.1 类职责

- 基类提供共享状态、稳定协议和生命周期骨架。
- 子类实现具体后端、参数和领域行为；子类专用字段放在子类中。
- 协议表达能力，注册表表达所有权，Controller 表达流程调度。
- 一个类的构造状态集中在属性接口中，运行时缓存和后端对象使用私有实例字段及显式方法。
- 继承用于“is-a”关系；可组合的策略、适配器和 evaluator 使用组合。

### 5.2 方法顺序

类内部按照以下顺序组织：

1. 类级常量和类型别名；
2. `__init__()`；
3. property；
4. 本类独有的外部接口方法；
5. 按 `Initializable`、`Updatable`、`Visualizable`、`Persistable` 排列的协议方法；
6. 内部辅助方法；
7. 私有静态方法和私有类方法。

外部接口方法先写本类独有方法，再写协议来源方法。内部辅助方法使用一个前导下划线，
并保持调用范围在本类内部。

设计文档中的每个类也按同一顺序列出五个接口区块：

1. 构造属性（类自身记录的定义字段）；
2. 运行时属性（`__init__()` 声明、由初始化或生命周期方法填充的状态）；
3. 属性接口（`property`）；
4. 外部接口方法（先本类独有方法，再按协议来源排序）；
5. 内部辅助函数。

某一区块内容为空时仍保留对应表格，并在表格中标注“空”。继承基类状态的子类在运行时
属性表中明确写出继承范围，直接继承的 `property`、外部接口方法和内部辅助函数分别保留空表。

子类表格列本类新增成员和本类重写的成员；继承属性、外部接口方法和内部辅助函数以空表
说明继承范围。表格中的“来源”列用于保留已列出的
重写接口来源：本类新增成员填写 `-`，重写的父类接口填写定义该接口的最上层父类名称，
协议直接定义的重写接口填写协议名称。

### 5.3 运行时生命周期

- `__init__()` 记录构造参数、注册关系和代码槽，建立 `None` 或空容器形式的运行时字段。
- `initialize()` 读取源数据、解析名称、构造后端对象、建立映射和分配运行时资源。
- `build_assembly()` 创建当前定义对应的新 `Assembly` 并写入内部状态；Controller 创建逐工况
  `FEAController`，`Solver.build_solvers()` 创建并挂接 `StaticImplicitSolver`，
  `Solver.solve(fea_controllers)` 处理逐工况求解。
- `reinitialize(iteration)` 刷新当前迭代缓存。
- `update_assembly()` 对已有模型执行试探更新并保留计算图；方法接收设计增量或当前值，
  对象使用自身缓存的 TorchFEA 后端引用。
- `apply_design_delta()` 将优化结果正式写回 owner。
- `save()` 和 `load()` 只处理对象自身负责的持久化状态。

生命周期方法保持幂等：重复调用 `initialize()` 时先刷新已有运行时缓存，再依据定义状态
重新建立对象。

## 6. Tensor、Autograd 和 FEA 数据

- Tensor 字段说明设备、dtype、形状、单位和梯度语义。
- 参数快照使用 `detach().clone()`；试探更新保留 autograd 计算图。
- `update_assembly()` 内部使用保持计算图的 Tensor 转换；NumPy 转换集中在预览、日志和文件边界。
- 设备迁移由明确的上下文或参数完成，领域对象内部保持 device 语义一致。
- 设备由 `Solver` 或运行配置显式注入，库模块读取统一设备上下文。
- 形状优化使用 `design_delta`、`control_points`、`surface_values` 等稳定术语。
- FEA component 的值向量、load step、Jacobian 和结果按 `step_index` 保持稳定顺序。
- 梯度切分使用 `DesignRegistry` 的 `DesignKey` 和 offsets，owner 只接收自己的变量块。
- 几何导出读取当前控制点、约束结果、方向状态和最新映射缓存。

## 7. UI、Codegen 和前后端边界

- UI Node 保存表单定义和用户输入；领域对象保存模型语义和运行时状态。
- UI 编辑器通过 property 和显式编辑方法修改 Node，领域对象私有字段由领域接口维护。
- Codegen 生成确定性的 Python 源码；相同定义产生稳定的导入顺序、名称和代码布局。
- UI 字符串使用 i18n；生成代码、领域变量、异常类型和日志字段使用英文。
- 长时间计算进入 worker 或任务进程；主线程负责交互、状态更新和结果展示。
- UI 信号使用 Qt 风格命名，参数类型明确；跨页面动作通过窗口级协调器传递。
- 预览调用 `get_meshes()`；曲面导出调用 `export_surface()`，Part 模型导出调用
  `export_model()`。
- UI 显示错误上下文和可执行修复提示，领域层抛出结构化异常。

## 8. 错误处理、日志和资源

- 为可恢复的输入错误、模型错误、求解错误和导出错误定义领域异常类型。
- 异常消息包含对象名称、操作、关键参数和修复方向。
- 捕获异常后补充上下文并重新抛出；保留原始异常链。
- 业务库使用 `logging`；命令行和 UI 负责最终展示格式。
- 调试信息使用 `debug`，运行进度使用 `info`，可恢复问题使用 `warning`，失败操作使用 `error`。
- 日志字段统一使用 `iteration`、`step_index`、`part_name`、`component_name` 和 `path`。
- 文件、进程池、GPU 上下文和 CAD 会话使用明确的创建与释放边界。
- 临时文件放在任务结果目录的 `cache/`，输出文件路径通过 `Path` 组合。

## 9. 持久化和生成文件

- 持久化字段使用稳定名称，临时对象通过可重建的标识和配置表达。
- 保存格式记录版本、对象类型和必要的 schema 信息。
- `load()` 在对象完成 `initialize()` 后执行，加载结果经过类型和维度校验。
- 生成脚本包含完整导入、定义注册、初始化入口和可运行的 main entry。
- 生成代码接收完整任务定义，任务文件具备 headless 独立运行能力。
- 导出的 STP/STL 文件使用明确后缀、稳定命名和任务结果目录。

## 10. 测试规范

- 项目使用 pytest 作为统一测试运行器，开发环境通过 `pip install -e ".[test]"` 安装。
- 每个核心功能建立对应的单元测试文件和测试模块；新增公开接口同步增加测试。
- 每个公开函数、公开方法和 property 都有至少一个直接行为测试；生命周期方法同时覆盖初始化和刷新路径。
- 单元测试覆盖名称校验、property、生命周期、设计变量排序和错误路径。
- 几何测试覆盖多 Part、多 Instance、曲面方向、曲面导出和 surface set。
- 材料测试覆盖参数类、材料分配、元素覆盖和 SIMP 场映射。
- FEA 测试覆盖组件目标、载荷工况、step index、Jacobian、收敛状态和结果结构。
- DesignRegistry 测试覆盖变量排序、offsets、梯度切分和 owner 回写。
- Updater 测试覆盖目标绑定、局部梯度、统一提交和多 updater 协同。
- UI 测试覆盖 Node 编辑、级联改名、双语文本、Codegen 和生成脚本。
- 测试数据放在 `tests/data/`，测试过程产生的文件写入临时目录。
- 测试名称描述行为和预期结果，例如 `test_geometry_export_stl()`。
- 每个修复增加回归测试；每个新增公共接口同步增加正向和错误路径测试。

### 10.1 测试目录镜像

`tests/` 与 `src/morphopt/` 保持一一对应的目录结构。源文件所在的包层级在测试目录中
完整复现，测试文件放在对应的镜像目录内：

```text
src/morphopt/
├── optcore/
│   └── controller.py
└── ui/
    └── app.py

tests/morphopt/
├── optcore/
│   └── testController.py
└── ui/
    └── testApp.py
```

文件映射规则如下：

| 源文件 | 测试文件 |
|---|---|
| `src/morphopt/optcore/controller.py` | `tests/morphopt/optcore/testController.py` |
| `src/morphopt/ui/app.py` | `tests/morphopt/ui/testApp.py` |
| `src/morphopt/optcore/modelparams/geometry.py` | `tests/morphopt/optcore/modelparams/testGeometry.py` |

每个源文件对应一个主要测试文件；跨模块行为测试放在涉及的顶层功能目录中，并在文件名
和测试标记中说明覆盖范围。V4 的测试统一放在 `tests/morphopt/`，旧版代码只作为架构
和功能参考。

### 10.2 pytest 配置

项目配置位于 `pyproject.toml` 的 `[tool.pytest.ini_options]`：

```toml
testpaths = ["tests"]
python_files = ["test*.py"]
python_classes = ["Test*", "*Tests"]
python_functions = ["test_*"]
```

常用命令：

```bash
python -m pytest
python -m pytest tests/morphopt/optcore/modelparams/testGeometry.py -q
python -m pytest -m unit
python -m pytest -m "not slow"
```

测试标记统一使用 `unit`、`integration` 和 `slow`。纯函数、参数对象、映射和属性测试
使用 `unit`；跨模块 Assembly/FEA 测试使用 `integration`；需要 CAD、GPU、完整 UI 或
长时间求解的测试使用 `slow`。

### 10.3 功能测试文件建议

| 功能 | 测试文件建议 | 重点 |
|---|---|---|
| Geometry / Part | `tests/morphopt/optcore/modelparams/testGeometry.py` | Part、Instance、曲面、集合、STP/STL |
| Materials | `tests/morphopt/optcore/modelparams/testMaterials.py` | 参数类、材料分配、SIMP |
| FEA / Solver | `tests/morphopt/optcore/modelparams/testFeaparams.py`、`tests/morphopt/optcore/testSolver.py` | 组件、工况、求解结果 |
| Objective | `tests/morphopt/optcore/testObjfunc.py` | 目标、指标、Jacobian、History |
| DesignRegistry | `tests/morphopt/optcore/testDesignRegistry.py` | offsets、梯度和试探回写 |
| Updaters | `tests/morphopt/optcore/testUpdaters.py` | owner 绑定和联合更新 |
| UI / Codegen | `tests/morphopt/ui/testProblemDefinition.py` | Node、编辑器、源码生成 |

测试函数使用 `test_<行为>_<预期结果>()` 的 `snake_case`，fixture 使用名词或
`<对象>_fixture`，共享 fixture 放在 `tests/conftest.py`。

### 10.4 测试隔离

- 使用 `tmp_path` 管理临时文件和结果目录。
- 使用 fixture 构造最小模型，测试之间共享只读输入数据。
- 使用 `monkeypatch` 替换外部 CAD、GPU、进程池和文件系统边界。
- 使用 `caplog` 检查关键日志字段和 iteration/step_index 上下文。
- 外部求解器、真实 CAD 导出和完整 UI 流程通过 `integration` 或 `slow` 标记管理。
- 单元测试保持确定性；随机数据固定 seed，设备测试明确 CPU 或 CUDA 条件。

## 11. 文档与 Review 规范

- 一个 Markdown 文件聚焦一个核心主题；总入口只维护阅读顺序和交叉索引。
- 架构描述直接写职责、输入、输出、状态和调用时机。
- 接口表统一列出类型、默认值、读写权限、来源和作用。
- 示例代码保持可运行，变量名称与正式接口一致。
- 术语首次出现时给出中文说明和英文标识，后续使用统一英文标识。
- 修改接口时同步更新架构文档、编码规范、Codegen、测试和迁移清单。
- Review 优先检查公共接口、依赖方向、生命周期、梯度语义、资源释放和错误上下文。

## 12. Review 清单

- [ ] 文件名简短、小驼峰，并优先使用单个词语。
- [ ] 变量、函数和方法使用 `snake_case`。
- [ ] 类型、协议和异常使用大驼峰。
- [ ] 公开接口具有完整类型标注和明确返回值。
- [ ] `__init__()`、`initialize()`、`build_assembly()`、`update_assembly()` 的职责清晰。
- [ ] Tensor 的 device、dtype、形状和梯度语义明确。
- [ ] UI、Codegen、领域对象和外部后端之间保持边界。
- [ ] 异常包含上下文，日志字段统一，资源释放路径完整。
- [ ] 新增接口已有对应测试、文档和迁移记录。

## 13. 工具链和质量门禁

V4 使用一套可重复执行的质量门禁：

| 工具 | 用途 | 最低通过条件 |
|---|---|---|
| `ruff format` | Python 格式化 | `ruff format --check src tests` 通过 |
| `ruff check` | 导入、风格和常见错误检查 | `ruff check src tests` 通过 |
| `mypy` | 公共接口和领域数据静态类型检查 | `mypy src/morphopt` 通过；外部无类型库集中配置边界豁免 |
| `pytest` | 单元、集成和慢速测试 | `pytest -m "not slow"` 通过；发布前执行完整测试集 |
| `coverage` | 测试覆盖统计 | 核心领域模块分支覆盖率不低于 90%，新增代码保持或提高覆盖率 |
| `build` | wheel 与 sdist 构建 | 两种分发包均可构建并在干净环境导入 |

`pyproject.toml` 集中保存工具配置。持续集成按“格式检查 → 静态检查 → 单元测试 →
集成测试 → 构建验证”的顺序执行。CAD、GPU 和 Qt 测试使用显式 marker；具备对应运行环境
的发布任务执行这些测试。

提交信息使用祈使语气描述一个完整变更；接口变更在提交正文列出迁移范围。发布版本遵循
语义化版本，V4 的公开接口在同一大版本内保持稳定。性能基准覆盖 Assembly 构建、单步求解、
灵敏度计算和 updater 闭包；基准结果记录模型规模、设备和 dtype。
