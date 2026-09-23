# 模块参考（Module Reference）

本文基于 `src/morphopt` 最新代码，按包整理每个模块的定义方式与功能职责。

---

## 1. 包结构一览

```
src/morphopt/
  optcore/       <- 核心框架（Controller / Solver / Params / Updaters / ObjFunc / PartInterface）
  shapeopt/      <- 形状优化子包（BoundaryPartInterface / SurfaceInterface / UpdaterBoundaryPart）
  simp/          <- SIMP 拓扑优化子包
  codesign/      <- 壳层协同设计子包
  ui/            <- 图形界面（定义 + 观察）
  utils/         <- 工具函数
```

`optcore` 提供基类和基础设施，`shapeopt` / `simp` / `codesign` 在其上提供具体的参数化、目标和更新器实现。

---

## 2. 顶层包 `morphopt`

### 2.1 `__init__.py`

定义方式：统一导出核心类与入口函数，形成对外 API。

**主要导出：**

- 核心流程：`Controller`, `Params`, `Solver`, `Updaters`, `ObjectiveFunction`, `History`
- 参数模块：`FEAParams`, `MaterialsParams`, `GeometryParams`
- 几何接口：`BasePartInterface`, `INPPartInterface`, `TorchFEAPartInterface`
- 模型工具：`resolve_model_path`, `load_model_assembly`
- 运行入口：`start_optimization`, `debug_optimization`, `enable_logging`, `check_gradients`
- 子包：`morphopt.shapeopt`, `morphopt.simp`, `morphopt.codesign`, `morphopt.ui`

### 2.2 `opt_runner.py`

定义方式：函数式入口封装，内部通过多进程启动优化。

- `start_optimization(...)`：启动无界面优化主进程
- `debug_optimization(...)`：在当前进程调试运行

已有结果从主 UI 的观察页中打开：选择任务来源后选择已有结果目录。

### 2.3 `taskoptmization.py`

定义方式：`TaskOptimization` 类，提供类方法 `task_optimization` 和 `optmain`。

负责"可重启"优化循环管理，每次子进程运行结束后根据结果路径继续下一段迭代。

---

## 3. `optcore` — 优化核心

### 3.1 `controller.py` — Controller

定义方式：`Controller` 基类 + 四个内嵌占位类（`Params/Solver/Updater/ObjectiveFunction`）。

- 统一调度优化迭代：`initialize -> step -> record -> save`
- 管理结果目录、重启、历史记录、并行池
- 提供 `start_optimization` / `restart_optimization` 生命周期

扩展方式：用户定义 `class ThisController(morphopt.Controller)` 并在类内定义四大子模块。

### 3.2 `protocal.py` — 生命周期协议

- `ProtocalInitializable`：提供 `initialize()` / `reinitialize()` 生命周期钩子
- `ProtocalSavable`：提供 `save()` / `load()` / `pathlog_required()` 持久化钩子
- `ProtocalVisualizable`：提供 `get_meshes()` / `plot()` 可视化钩子
- `ProtocalUpdatable`：提供设计变量读取、更新和灵敏度装配钩子

参数类、求解器、更新器和目标函数按需组合这些协议，不再继承一个包含全部生命周期方法的统一基类。

### 3.3 `solver.py` — Solver

定义方式：`Solver` 类，依赖 `Params` 与 `FEAParams`。

- 进行多工况 FEA 求解
- 支持多进程分配工况并收集结果
- 自动把结果设备迁移回默认设备

### 3.4 `objfunc.py` — ObjectiveFunction

定义方式：`ObjectiveFunction` 基类。

- 管理多工况目标函数构建
- 统一执行目标值计算和灵敏度分析
- 提供默认 `save(...)` 导出变形图与网格

### 3.5 `history.py` — History

历史数据容器，存储并序列化迭代中的 objective、metrics、时间、网格规模、位移等。

### 3.6 `updaters.py` — BaseUpdater + Updaters + L-BFGS

定义方式：内嵌 `BaseUpdater(ProtocalInitializable, ProtocalSavable)` + `Optimizer` 子命名空间 + 聚合类 `Updaters`。

- `BaseUpdater`：单个子优化器的基类，提供 `closure()` / `update()` 流程。每个子优化器
  更新什么由**注册行**给出：`update_kind`（哪一类集合 / 梯度键，`geometry` /
  `materials`）由注册钩子钉下，interface 名就是 `add_*_updater(...)` 的 `name`
  （构造时的 `interface_name=` 优先）；`interface_name`
  给出最终名字
- `Optimizer.BaseOpt`：基类优化器，含回溯线搜索（Wolfe 条件）
- `Optimizer.LBFGS`：有限内存 BFGS，支持 `num_limit` / `tol_error`
- `Updaters(params=None, updaters=None, device=None)`：把子更新器维护成**字典**
  - `define_updater()`：唯一声明钩子（用户重写），里面按分类调用
    `add_geometry_updater(...)` / `add_material_updater(...)`，
    分别注册到 `params.geometry` / `params.materials`
  - `add_updater(updater, name=None, kind=None)`：底层注册接口；`kind` 会和子优化器声明的
    `update_kind` 核对（不一致或未指明分类直接报错）
  - `updaters`：按注册顺序保存所有子更新器；默认名取更新器的 `interface`，
    否则 `<类名>_<序号>`
  - `initialize()`：解析并绑定每个子更新器的目标（Part / 材料接口），名字写错、
    集合类型不符、或绑定到非模型集合都会在这里报错
  - `update(gradients)`：按目标切分 `gradients[update_kind]`，每个子更新器只拿到自己那一片
  - `save/load`：逐个保存，状态路径按目标名分目录

扩展方式：`shapeopt.UpdaterBoundaryPart`、`simp.UpdaterSIMPMaterial`、
`codesign.UpdaterBoundaryPart` / `codesign.UpdaterSIMPMaterial` 均继承自 `BaseUpdater`。

### 3.7 `modelparams/` — 参数模型

#### `params.py` — Params（聚合类）

定义方式：组合 `geometry + feamodel + materials`。

- 统一初始化、重初始化、保存/加载
- 创建 FEA 模型：几何生成 -> FEA 创建 -> 材料赋值
- 为灵敏度分析提供设计变量拆分与 assembly 修改逻辑

#### `baseparam.py` — BaseParams

所有参数类的基类，提供 `initialize()` / `reinitialize()` / `plot()` / `get_meshes()` /
`export_data()` 等默认接口。

集合统一通过 `interfaces: dict[str, object]` 保存命名接口，并负责装配、
拼接灵敏度变量、保存/加载和绘图。设计变量属于继承
`ProtocalUpdatable` 的接口，由子优化器持有并调用——
`Updaters.update()` → 子更新器 → `get_parameters()` / `update_variables(...)`。

#### `geometry.py` — GeometryParams（几何集合）

- `GeometryParams`：一个按名称保存的 **Part 接口字典**（`interfaces`），负责
  `generate()`（生成网格）、设计变量/灵敏度的拼接与 `modify_assembly()`；
  它本身没有曲面概念。
- `define_interface()`：子类在这里用 `add_interface(interface, name=...)`
  注册每个 Part；由 `initialize()` 调用（构造函数只建空字典，只在集合为空时登记），
  登记后可用 `interfaces[name]` 按名取回。
- `design_interfaces()`：可被更新的 Part（即继承 `ProtocalUpdatable` 的 Part）。
- 设计变量顺序 = Part 注册顺序；梯度拼接同序（几何更新器按 Part 切片）。

#### `partinterface/` — Part 接口（Part + Instance）

| 文件 | 类 | 用途 |
|------|-----|------|
| `basepartinterface.py` | `BasePartInterface` | 一个 Part 及其 Instance 集合；子类实现 `build_part()` |
| `partinterface/inppartinterface.py` | `INPPartInterface` | 从 Abaqus INP 读网格 |
| `partinterface/torchfeapartinterface.py` | `TorchFEAPartInterface` | 用 `torchfea.load_model` 读导出的模型目录 |

- Instance 声明：覆盖 Part 的 `define_instance()`，对每个实例调用
  `add_instance(part_name, instance_name, [tx, ty, tz, rx, ry, rz])`。
- 基类默认创建一个与 Part 同名、无位姿变化的 Instance；`rx/ry/rz` 是
  TorchFEA 的 rotation exponential coordinates（弧度）。
- `part_name` 默认取注册名（不再有 `final_model` 默认值）。
- 基类**不含任何曲面概念**：曲面的声明、访问与按曲面切分的步长由
  `BoundaryPartInterface` 负责（见 4.2）。

#### `feaparams.py` — FEAParams

定义方式：继承 `FEAParams`，重写 `define_interface()` 与 `define_steps()`；两者都由
`initialize()` 调用（构造函数只建空集合）。

- 把 INP 转成 `torchfea` 结构
- 创建并管理载荷接口对象
- 每个 load step 调用 `process_fea(...)` 应用当前幅值

#### `materialinterface/` — 材料赋值接口

材料接口的具体实现独立放在 `optcore/modelparams/materialinterface/`，由
`materials.py` 统一聚合。

- `basematerialinterface.py`：`BaseMaterialInterface`，一个 Part 上一个材料赋值接口；
  `elementname=""` 表示全部单元。
- `homogeneousmaterial.py`：`HomogeneousMaterial` 均质材料接口。
- `materialmodels.py`：TorchFEA 本构模型与对应参数对象的集中定义。

#### `materials.py` — MaterialsParams

- `HomogeneousMaterial`：均质材料；通过对应的参数对象（如
  `self.materialmodels.NeoHookeanLnJParams(...)`）选择 TorchFEA 本构模型，
  并传入 `density`
- `SIMP_BSPFieldMaterials`：SIMP 密度场材料，同样通过对应的参数对象选择
  本构模型；`NeoHookeanLnJParams` 是推荐的默认模型参数类型，SIMP 另外使用
  `mumax/kappamax` 做密度场插值。
- `MaterialsParams`：按注册顺序聚合多个接口，并提供 `set_materials()`、设计变量和灵敏度拼接。

各模型的参数类型挂在 `MaterialsParams.materialmodels` 上；在
`define_interface()` 中直接使用 `self.materialmodels.NeoHookeanLnJParams` 等
参数对象。参数对象的类名同时决定材料模型；可选的模型名为
`LinearElastic`、`NeoHookean`、`NeoHookeanLnJ`、`MooneyRivlin`、`Yeoh`、
`Gent`、`ArrudaBoyce` 和 `Ogden`。

#### `feainterface/` — FEA 接口（9 种）

| 文件 | 类 | 用途 |
|------|-----|------|
| `basefeainterface.py` | `BaseFEAInterface` | 接口基类 |
| `pressureinterface.py` | `PressureInterface` | 分布压力 |
| `pointinterface.py` | `ConcentratedForceInterface`, `ConcentratedMomentInterface` | 集中力/力矩 |
| `boundaryconditioninterface.py` | `BoundaryConditionInterface`, `BoundaryConditionRPInterface` | 边界约束 |
| `contactinterface.py` | `ContactInterface`, `ContactSelfInterface` | 接触条件 |
| `springinterface.py` | `SpringToGroundInterface`, `SpringBetweenRPsInterface` | 弹簧约束 |
| `coupleinterface.py` | `CoupleInterface` | 节点耦合 |
| `referencepointinterface.py` | `ReferencePointInterface` | 参考点（RP） |
| `bodyforceinterface.py` | `BodyforceInterface` | 体力 |

---

## 4. `shapeopt` — 形状优化子包

### 4.1 `geometryparams.py` — GeometryParams

定义方式：继承 `optcore.modelparams.geometry.GeometryParams`，在
`define_interface()` 里注册 Part 接口。

- 每个 Part 是一个 `BoundaryPartInterface`（shapeopt/codesign）或
  `INPPartInterface` / `TorchFEAPartInterface`（固定几何）
- 只有 `BoundaryPartInterface` 通过 `add_surface_interface(...)` 持有曲面（BSP / CPGEO）
- `generate()`：每个 Part 自建（导出曲面文件 -> Gmsh 体网格 / 读 INP），再按
  Instance 放置组装到同一个 `torchfea.Assembly`
- 在灵敏度分析中把几何变量映射回 assembly 节点
- 提供 `reinitialize()` 做几何后处理

`optcore` 的几何集合本身**不知道曲面**，与曲面有关的三件事由这一层补上：

- `add_interface()`：只负责把 Part 放入 `interfaces`；边界 Part 在自身
  `initialize()` 阶段声明曲面，避免注册和初始化之间再转发一次调用
- `load()`：通过统一的 interface 保存目录恢复设计状态

设计更新不走集合：`Updaters.update()` → 子更新器 → `part.update_variables(...)`，
步长、变量切分都由边界 Part 自己负责。

### 4.2 `boundarypartinterface.py` — BoundaryPartInterface

定义方式：继承 `BasePartInterface`，是**唯一持有曲面的 Part 接口**。

- `define_surfaces()`：子类在这里用 `self.add_surface_interface(...)` 按索引顺序
  声明本 Part 的曲面（`0` = 外表面，`1..` = 内腔）；由 Part 的
  `initialize()` 触发一次。若已用 `add_surface_interface()` 显式加过曲面，
  初始化时不会重复声明
- `surface_interfaces()` / `num_surface_interfaces`：曲面访问
- `apply_surface_constraints()`：几何等式约束钩子（对称/周期等），每次更新后调用
- `fea_seed_size` / `mesh_order`：体网格参数
- 嵌套别名：`BoundaryPartInterface` / `BoundaryPart`（`GeometryParams` 上也可用）

### 4.3 `update_boundarypart.py` — UpdaterBoundaryPart

定义方式：继承 `BaseUpdater`，**更新一个 GeometryParams 集合里的一个边界 Part**
（`update_kind="geometry"` 由基类/钩子给出，Part 名就是 `add_geometry_updater(...)` 的 `name`）。

- **空构造**：只收自己的旋钮（`max_step_iter` / `max_step_length`）和可选名字
  （`interface_name=`）；
  不持有 `Params`、也不持有 geometry 集合
- 目标 Part：初始化时由 `Updaters` 统一按名查找并做类型校验，再调用
  `bind_target(target)`；此后只保留那一个 Part → `part`
- 注册行的 `name`（`add_geometry_updater(self.Shape(), name='body')`）既是字典键也是 Part 名；
  需要覆盖注册名时用 `interface_name=`；只有一个边界 Part 时可省略
- 写错名字会在 `initialize()` 立即报错并列出可用名
- 目标 / 约束写在 `define_objective()`（由 updater 注册时调用一次，和 `define_interface()` 对称）：
  目标项用 `add_objective_function()`、约束项用 `add_constraints()`，分别存在
  `obj_funcs` / `constraints_funcs`；目标相关数据在运行时初始化阶段取得
- 目标/约束在求值时拿到本 Part 的曲面（无需显式传 `surfaces=`）
- 根据灵敏度构建子优化问题（L-BFGS）
- 处理步长控制、约束惩罚、变量更新；状态保存在 `log/geometryupdater/<interface>/`
- 属性：`part`（目标 Part）、`interface_name`（名字）、
  `surface_interfaces`、`max_step_iter`、`max_step_length`
- 多个几何更新器并列注册在 `Updaters` 中，按 Part 切分梯度

### 4.4 `surfaceinterfaces/`

| 文件 | 类 | 用途 |
|------|-----|------|
| `basesurfaceinterface.py` | `BaseSurfaceInterface` | 曲面接口基类 |
| `bspsurfaceinterface.py` | `BspSurfaceInterface`（别名 `BSP`） | B-spline 参数化曲面 |
| `cpgeosurfaceinterface.py` | `CPGEOSurfaceInterface`（别名 `CPGEO`） | CPGEO 参数化曲面 |

### 4.5 `objectivefuncs/`

| 文件 | 类 | 用途 |
|------|-----|------|
| `basefuncs.py` | `BaseObjectives`, `BaseConstraints` | 目标/约束基类 |
| `shapederivative.py` | `ShapeDerivative` | 形状导数（灵敏度驱动） |
| `surfacefairness.py` | `Fairness` | 曲面光顺性约束 |
| `distancesurface.py` | `Distance` | 曲面距离约束 |
| `boundarys.py` | `MinValue`, `MaxValue`, ... | 边界值约束 |

---

## 5. `simp` — SIMP 拓扑优化子包

### 5.1 `simpmaterial.py` — SIMP_BSPFieldMaterials

定义方式：继承 `BaseMaterialInterface`，B 样条控制点场 `_cps` 作为设计变量。

- `_map_bsp_designfield(nodes)`：高斯点上计算材料密度
- `get_material_ratio(designfield)`：RAMP 插值 + 材料惩罚
- `set_materials(fe)`：按参数对象对应的材料模型对密度场缩放刚度参数并赋值材料
- 自定义元素类：`SIMPElementFgrad` / `SIMPElementFskew` / `SIMPElementHuHu_LuLu`

**敏感度中的正则惩罚：**

- Fgrad：梯度惩罚（应变二阶梯度）
- Fskew：扭曲惩罚（反对称变形梯度）
- HuHu_LuLu：主伸长惩罚

### 5.2 `solver.py` — SIMPSolver

定义方式：继承 `Solver`，扩展 SIMP 特有的求解逻辑。

### 5.3 `update_simpmaterial.py` — UpdaterSIMPMaterial

定义方式：继承 `BaseUpdater`，**更新一个 MaterialsParams 集合里的一个材料接口**
（`update_kind="materials"` 由基类/钩子给出，接口名就是 `add_material_updater(...)` 的 `name`）。

- **空构造**：只收自己的旋钮（`max_step_iter` / `max_step_length`）和可选名字
  （`interface_name=`）；不持有 `Params`、也不持有 materials 集合
- 目标接口：初始化时由 `Updaters` 统一按名查找并做类型校验，再调用
  `bind_target(target)`；此后只保留那一个接口 → `material`
- 注册行的 `name`（`add_material_updater(self.Density(), name='solid')`）既是字典键也是接口名；
  需要两者不同（或没有注册名）时用 `interface_name=` 覆盖
- 省略名字时用唯一的可设计接口（SIMP 密度场），有多个则必须声明；名字指向非 SIMP
  接口时报 `TypeError`
- 目标 / 约束写在 `define_objective()`（由 updater 注册时调用一次）里，
  通过 `add_objective_function()` / `add_constraints()` 注册，分别存在 `obj_funcs` / `constraints_funcs`
- 面向 SIMP 控制点更新；状态保存在 `log/materialupdater/<interface>/`
- 多个材料更新器可以并列注册，每个负责自己的材料接口（梯度按接口切片）
- 自适应步长管理：`max_step_iter`, `max_step_length`, `_step_length_min_ratio`
- 约束：边界值约束（`MinValue` / `MaxValue`）

### 5.4 `objectivefuncs/`

| 文件 | 类 | 用途 |
|------|-----|------|
| `basefuncs.py` | `BaseObjectives`, `BaseConstraints` | 基类 |
| `sensitivity.py` | `Sensitivity` | 灵敏度目标 |
| `volfrac.py` | `VolumeFraction` / `ObjectiveVolumeFraction` | 体积分数约束/目标 |
| `densityfield.py` | `DensityField` | 密度场正则 |
| `boundarys.py` | `MinValue`, `MaxValue` | 边界值约束 |

---

## 6. `codesign` — 壳层协同设计子包

### 6.1 `geometry.py` — CodesignBoundaryPartInterface

定义方式：`CodesignBoundaryPartInterface(BoundaryPartInterface)`。

- 在生成边界 Part 的同时，为每个曲面生成一份偏置壳层（C3D6）
- 曲面参数中以 `surface_<i>_offset` 描述偏置量，支持壳层厚度与分层参数
  （`shell_thickness`, `num_layers`）
- codesign 的 `GeometryParams` 在其上增加 `shell_interfaces()`、
  `shell_thickness_at(surface_index)`、`shell_thickness`
- 内置 reinitialize 后的轻量形状平滑优化

### 6.2 `materials.py` + `materialinterface/` — 材料接口集合

材料定义由 `BaseMaterialInterface` 和 `MaterialsParams` 组成。

- 每个接口必须绑定非空 `part_name`。
- `elementname` 默认为空字符串；空值表示该 Part 的全部单元类型。
- `HomogeneousMaterial` 按 `material_parameters` 对象赋予均匀材料；参数对象
  的类型决定本构模型。
- `SIMP_BSPFieldMaterials` 赋予 B 样条密度场材料。
- 模型参数使用对应的参数对象，例如 `NeoHookeanParams`、
  `MooneyRivlinParams` 和 `YeohParams`；对象类型同时决定本构模型，
  并提供明确的参数字段提示。
- `MaterialsParams.add_interface(interface, name=...)` 注册接口，并自动
  聚合所有接口的设计变量、参数和装配修改操作。

codesign 不再有复合 `CodesignMaterials` 类；实体 SIMP 和 C3D6 壳材料是两个
独立的接口。

### 6.3 `feaparams.py` — CodesignFEAParams

定义方式：`CodesignFEAParams(FEAParams)`。

- 增加对 C3D6 壳单元初始化与质量检查
- 自动法向检测与偏移表面管理

### 6.4 `constraints.py`

- `InwardCurvatureRadius`：限制内向主曲率，降低偏移壳自交风险
- `OffsetSurfaceMinThickness`：在偏移面邻域点对上施加最小间距约束
- 两者都是**针对一个边界 Part** 的约束：只在构造时给调参项，Part 由几何更新器在
  `initialize()` 时交进来（`part_interface=`）；交进来的不是
  `CodesignBoundaryPartInterface` 会当场报错，构造时不接受几何集合

---

## 7. 典型扩展点

| 需求 | 扩展方式 |
|------|----------|
| 新几何接口 | 新增一个 `PartInterface` 子类，在 `define_interface()` 中注册 |
| 新 FEA 接口 | 新增 `feainterface` 子类，在 `define_interface()` 中调用 |
| 新目标/约束 | 新增 `objectivefuncs` 类，挂到对应更新器 |
| 新材料参数化 | 继承 `SIMP_BSPFieldMaterials`，重写 `_map_bsp_designfield` |
| 新优化类型 | 创建新的子包（如 `shapeopt` / `simp` 模式），继承 `BaseUpdater` |
