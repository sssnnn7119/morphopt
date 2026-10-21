# 模型与参数集合

[代码结构导览](README.md) · [运行时](runtime.md) · [设计更新](optimization.md)

## 目录

<!-- docs:toc depth=1 -->

- [1 源码入口](#section-源码入口)
- [2 共享协议与组件层级](#protocols)
- [3 集合注册与生命周期](#section-集合注册与生命周期)
- [4 Params 的模型组装边界](#section-params-的模型组装边界)
- [5 Part、Instance 与几何缓存](#section-partinstance-与几何缓存)
- [6 FEA 接口与工况覆盖](#section-fea-接口与工况覆盖)
- [7 材料分配与参数类型](#section-材料分配与参数类型)
- [8 内核命名与 UI 命名的边界](#section-内核命名与-ui-命名的边界)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 源码入口

| 路径 | 主要对象 |
|---|---|
| [`optcore/protocal.py`](../../src/morphopt/optcore/protocal.py) | 初始化、保存、可视化与可更新协议 |
| [`optcore/modelparams/base_model_component.py`](../../src/morphopt/optcore/modelparams/base_model_component.py) | 单个模型组件的共同基类 |
| [`optcore/modelparams/baseparam.py`](../../src/morphopt/optcore/modelparams/baseparam.py) | 命名接口集合 `BaseParams` |
| [`optcore/modelparams/params.py`](../../src/morphopt/optcore/modelparams/params.py) | 聚合参数与 FE 模型组装 |
| [`geometry.py`](../../src/morphopt/optcore/modelparams/geometry.py)、[`parts/`](../../src/morphopt/optcore/modelparams/parts) | 几何集合与基础 Part |
| [`feaparams.py`](../../src/morphopt/optcore/modelparams/feaparams.py)、[`fea/`](../../src/morphopt/optcore/modelparams/fea) | 载荷、边界、连接与工况 |
| [`materialsparams.py`](../../src/morphopt/optcore/modelparams/materialsparams.py)、[`materials/`](../../src/morphopt/optcore/modelparams/materials) | 材料接口、分配与本构参数类型 |

<a id="protocols"></a>

## 2 共享协议与组件层级

源码中的 `Protocal*` 是以抽象基类表达的接口契约，名称保留现有拼写。

| 协议 | 主要方法 | 实现责任 |
|---|---|---|
| `ProtocalInitializable` | `initialize()`、`reinitialize()` | 初次准备与每轮状态更新 |
| `ProtocalSavable` | `save()`、`load()`、`pathlog_required()`、`save_directory()` | 状态持久化与命名目录 |
| `ProtocalVisualizable` | `get_meshes()`、`plot()` | 网格输出与绘图钩子 |
| `ProtocalUpdatable` | `num_variables`、参数访问、`update_variables()`、灵敏度变量提取与写回 | 可设计对象的变量契约 |

`BaseModelComponent` 组合初始化、保存和可视化能力，表示单个模型接口；`BaseParams` 维护多个具名接口。可更新几何与材料额外实现 `ProtocalUpdatable`，不由集合基类为所有对象隐式增加设计变量。

`ProtocalUpdatable.get_variables()` 提供局部优化初始扰动向量，不能将其简单解释为当前几何坐标。设计参数、灵敏度输入和局部变量之间的映射见[设计更新](optimization.md)。

<a id="section-集合注册与生命周期"></a>

## 3 集合注册与生命周期

`BaseParams.interfaces` 按注册顺序保存 `name → interface`。`add_interface()` 检查空名与重名，并为未命名对象生成 `<类名>_<序号>`；`interface(name)` 提供带候选名称的查询错误。

| 方法 | 责任 |
|---|---|
| `define_interface()` | 子类声明接口 |
| `initialize()` | 集合为空时执行声明，再初始化各接口 |
| `reinitialize(iteration)` | 将本轮准备传给现有接口 |
| `design_interfaces()` | 筛选实现可更新协议的接口 |
| `obtain_design_sensitivity_vars(assembly)` | 按设计接口顺序拼接灵敏度输入 |
| `save/load()` | 将状态操作分发到各接口 |

构造参数集合后尚不能假定其声明已执行。相同对象的重复初始化不应重复注册接口；结构变化与每轮重初始化分别处理。注册顺序进入变量布局与状态文件语义，优化运行中应保持稳定。

<a id="section-params-的模型组装边界"></a>

## 4 Params 的模型组装边界

```text
Params.create_feamodel()
├── GeometryParams.generate() → torchfea.Assembly
│   └── 每个 Part 接口 add_to_assembly()
├── FEAParams.create_fea(assembly) → FEAController + 载荷/边界/求解器
├── MaterialsParams.set_materials(fe)
└── fe.initialize()
```

`Params` 同时持有 `geometry`、`feamodel` 与 `materials`，但几何、载荷和材料各自保留接口集合。`create_feamodel()` 是声明模型进入当前有限元状态的组装点；上层控制器不逐个解释 Part、载荷和本构类型。

<a id="section-partinstance-与几何缓存"></a>

## 5 Part、Instance 与几何缓存

一个 `BasePart` 接口构建一个 `torchfea.Part`，并声明该部件的一个或多个 Instance。

| 成员 | 责任 |
|---|---|
| `name` | 几何集合注册名 |
| `part_name` | 装配体 Part 名，未显式设置时取注册名 |
| `define_instance()`、`add_instance()` | 声明实例名与六维位姿 |
| `build_part(path_result, pools)` | 具体几何构建或导入 |
| `get_part()` | 按缓存策略获取 Part |
| `add_to_assembly()` | 添加 Part、外表面和已声明实例 |
| `cache_part` | 控制固定几何是否复用 `_part` |
| `is_variable` | 标识几何或网格是否可能随优化变化 |
| `workdir()` | 分配该接口的几何工作目录 |

脚本基类默认声明一个与 Part 同名的零位姿实例；显式 `define_instance()` 可使用独立名称。位姿为 `[tx, ty, tz, rx, ry, rz]`，旋转采用指数坐标。载荷引用实例，材料引用 Part，局部更新器引用集合中的接口。

| 类型 | 实现位置 | 构建特点 |
|---|---|---|
| `BoxPart` | `parts/box_part.py` | 结构化长方体，单元块 `design` 及坐标面集合 |
| `CADPart` | `parts/cad_part.py` | 有序 `torchfea.cad` 操作历史及网格化 |
| `INPPart` | `parts/inp_part.py` | 从支持的 INP 内容选择并导入 Part |
| `BoundaryPart` | `shapeopt/boundary_part.py` | 参数化外边界与内腔，具体设计实现见[形状更新](optimization.md#shape) |
| `OffsetBoundaryPart` | `codesign/offset_boundary_part.py` | 在内腔边界构造偏置实体层 |

CAD 的 `define_operations()` 与有限元 `build_part()` 分离。STEP 导出直接使用 `torchfea.cad.export_step(operations, path)`，保存局部 CAD 实体，不要求生成体网格；UI 的操作解析见[应用服务](ui-application.md#cad)。

<a id="section-fea-接口与工况覆盖"></a>

## 6 FEA 接口与工况覆盖

`BaseFEAComponent` 保存名称和数值参数，`num_values` 定义每个工况需要的参数数量。

| 接口阶段 | 方法 | 责任 |
|---|---|---|
| 建模 | `modify_fea(fe, name)` | 向模型添加载荷、边界或连接对象 |
| 工况应用 | `apply_fea_value(fe, name)` | 将当前数值覆盖传给已创建对象 |
| 工况配置 | `FEAParams.set_step_num()`、`set_step_params()` | 建立工况表并填写接口幅值 |
| 求解前 | `FEAParams.process_fea(fe, step_index)` | 应用指定工况 |

压力、集中力/力矩、体力、弹簧与自由度罚项具有数值列表；固定条件、RP、耦合与接触不通过相同列表接收幅值。当前 `ReferencePointBoundaryCondition.num_values` 为零，不能据外部求解器的功能推断其支持任意非零位移工况。

`FEAParams.reinitialize()` 对接口与工况键进行规范排序。集合类型共享注册机制，不表示每类对象的执行顺序与数值含义完全一致。完整构造参数和十三类接口见[脚本 FEA 参考](../scriptreference.md#section-feaparams-定义要点)。

<a id="section-材料分配与参数类型"></a>

## 7 材料分配与参数类型

`MaterialsParams.set_materials()` 按注册顺序执行各材料接口的分配。`BaseMaterial` 用 `part_name` 与可选 `elementname` 确定目标，`target_elements()` 解析 `Part.elems` 中的实际单元块。

- `elementname=""` 选择该 Part 的全部单元块。
- 具体名称是块键，不必等于单元公式名；例如 Box 的块键为 `design`。
- 多个材料覆盖同一块时，应检查分配顺序与最终材料状态。

`HomogeneousMaterial` 不提供材料设计变量；`SIMP_BSPFieldMaterials` 同时提供材料分配和可更新设计场。两者共享类型化的 `MaterialModels` 参数对象，集合通过 `MaterialsParams.models` 暴露入口。

`models.py` 定义八种本构参数 dataclass，并将其映射到 TorchFEA 材料类。接口接收 `material_parameters`，而非同时维护独立的模型名和数值数组。SIMP 的映射、占比与更新责任见[材料设计](optimization.md#simp)。

<a id="section-内核命名与-ui-命名的边界"></a>

## 8 内核命名与 UI 命名的边界

内核 Part 支持显式装配名；UI 的 Part 节点仅保留一个可编辑名称，`assembly_name` 为派生值。UI 的实例名称单独管理，Part 改名不修改已有 Instance 名。

UI 通过对象引用维护载荷、材料和更新目标，保存及生成代码时才投影为内核名称。该规则属于 [UI 领域模型](ui-model.md)，不通过修改内核默认实例工厂来实现。
