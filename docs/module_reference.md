# 模块参考（Module Reference）

本文基于 `src/morphopt` 最新代码，按包整理每个模块的定义方式与功能职责。

---

## 1. 包结构一览

```
src/morphopt/
  optcore/       <- 核心框架（Controller / Solver / Params / Updaters / ObjFunc）
  shapeopt/      <- 形状优化子包
  simp/          <- SIMP 拓扑优化子包
  codesign/      <- 壳层协同设计子包
```

`optcore` 提供基类和基础设施，`shapeopt` / `simp` / `codesign` 在其上提供具体的参数化、目标和更新器实现。

---

## 2. 顶层包 `morphopt`

### 2.1 `__init__.py`

定义方式：统一导出核心类与入口函数，形成对外 API。

**主要导出：**

- 核心流程：`Controller`, `Params`, `Solver`, `Updaters`, `ObjectiveFunction`, `History`
- 参数模块：`FEAParams`, `HomogeneousMaterial`, `FixedGeometryINP`, `FixedGeometryNodeElement`
- 运行入口：`start_optimization`, `debug_optimization`
- 子包：`morphopt.shapeopt`, `morphopt.simp`, `morphopt.codesign`

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

### 3.2 `baseobject.py` — BaseObject

基础对象类，提供统一 `initialize()` / `reinitialize()` / `save()` / `load()` 接口风格。所有参数类、求解器、更新器、目标函数均继承自此类。

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

### 3.6 `updaters.py` — BaseUpdater + L-BFGS

定义方式：内嵌 `BaseUpdater(BaseObject)` + `Optimizer` 子命名空间。

- `BaseUpdater`：更新器基类，提供 `closure()` / `update()` 流程
- `Optimizer.BaseOpt`：基类优化器，含回溯线搜索（Wolfe 条件）
- `Optimizer.LBFGS`：有限内存 BFGS，支持 `num_limit` / `tol_error`

扩展方式：`shapeopt.UpdaterGeometries` 和 `simp.UpdaterMaterials` 均继承自 `BaseUpdater`。

### 3.7 `modelparams/` — 参数模型

#### `params.py` — Params（聚合类）

定义方式：组合 `geometry + feamodel + materials`。

- 统一初始化、重初始化、保存/加载
- 创建 FEA 模型：几何生成 -> FEA 创建 -> 材料赋值
- 为灵敏度分析提供设计变量拆分与 assembly 修改逻辑

#### `baseparam.py` — BaseParams

所有参数类的基类，提供 `get_variables()` / `update_variables()` / `get_parameters()` / `set_parameters()` / `plot()` 等默认接口。

#### `geometry.py` — BaseGeometry / FixedGeometryINP / FixedGeometryNodeElement

- `BaseGeometry`：几何基类，定义 `generate()` / `get_meshes()` 接口
- `FixedGeometryINP`：从 INP 文件导入固定的几何模型
- `FixedGeometryNodeElement`：从节点/单元数组构造固定几何

#### `feaparams.py` — FEAParams

定义方式：继承 `FEAParams`，重写 `define_interface()` 与 `define_steps()`。

- 把 INP 转成 `torchfea` 结构
- 创建并管理载荷接口对象
- 每个 load step 调用 `process_fea(...)` 应用当前幅值

#### `materials.py` — HomogeneousMaterial / BaseMaterials

- `HomogeneousMaterial`：均质材料，设定 `mu/kappa/density`
- `BaseMaterials`：材料基类，提供 `set_materials()` / `obtain_design_sensitivity_vars()` 等接口

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

定义方式：继承 `BaseParams`，持有 `surface_list`。

- 每个 surface 来自接口类（BSP 或 CPGEO），通过 `add_surface(...)` 注册
- `generate()`：导出曲面文件 -> 调用 Gmsh 生成体网格
- 在灵敏度分析中把几何变量映射回 assembly 节点
- 提供 `reinitialize()` 做几何后处理

### 4.2 `update_geometry.py` — UpdaterGeometries

定义方式：继承 `BaseUpdater`。

- 持有 `obj_funcs` 与 `constraints_funcs`，通过 `add_objective_function()` 和 `add_constraints()` 注册
- 根据灵敏度构建子优化问题（L-BFGS）
- 处理步长控制、约束惩罚、变量更新
- 属性：`max_step_iter`, `max_step_length`, `reset_sensitivity_scaler_per_iter`

### 4.3 `geometryinterfaces/`

| 文件 | 类 | 用途 |
|------|-----|------|
| `basesurfaceinterface.py` | `BaseSurfaceInterface` | 曲面接口基类 |
| `bspsurfaceinterface.py` | `BSPSurfaceInterface` | B-spline 参数化曲面 |
| `cpgeosurfaceinterface.py` | `CPGEOSurfaceInterface` | CPGEO 参数化曲面 |

### 4.4 `objectivefuncs/`

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

定义方式：继承 `BaseParams`，B 样条控制点场 `_cps` 作为设计变量。

- `_map_bsp_designfield(nodes)`：高斯点上计算材料密度
- `get_material_ratio(designfield)`：RAMP 插值 + 材料惩罚
- `set_materials(fe)`：在 FEA 元素上赋值 NeoHookean 材料
- 自定义元素类：`SIMPElementFgrad` / `SIMPElementFskew` / `SIMPElementHuHu_LuLu`

**敏感度中的正则惩罚：**

- Fgrad：梯度惩罚（应变二阶梯度）
- Fskew：扭曲惩罚（反对称变形梯度）
- HuHu_LuLu：主伸长惩罚

### 5.2 `solver.py` — SIMPSolver

定义方式：继承 `Solver`，扩展 SIMP 特有的求解逻辑。

### 5.3 `update_material.py` — UpdaterMaterials

定义方式：继承 `BaseUpdater`。

- 面向 SIMP 控制点更新
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

### 6.1 `geometry.py` — CodesignGeometry

定义方式：`CodesignGeometry(BaseParams)`。

- 支持壳层厚度与分层参数（`thickness`, `num_layers`）
- 在几何重建后生成 C3D6 壳体体单元
- 用目标偏移点 + 线性插层构建 offset 层节点
- 内置 reinitialize 后的轻量形状平滑优化

### 6.2 `material.py` — CodesignMaterials

定义方式：`CodesignMaterials(BaseParams)`。

- 分别设定壳层与体芯材料参数（`shell_mu`, `shell_kappa` 等）
- 在 C3D6 壳单元上单独赋予壳材料参数

### 6.3 `feaparams.py` — CodesignFEAParams

定义方式：`CodesignFEAParams(FEAParams)`。

- 增加对 C3D6 壳单元初始化与质量检查
- 自动法向检测与偏移表面管理

### 6.4 `constraints.py`

- `InwardCurvatureRadius`：限制内向主曲率，降低偏移壳自交风险
- `OffsetSurfaceMinThickness`：在偏移面邻域点对上施加最小间距约束

---

## 7. 典型扩展点

| 需求 | 扩展方式 |
|------|----------|
| 新几何接口 | 新增 `geometryinterfaces` 实现，在 `GeometryParams` 中注册 |
| 新 FEA 接口 | 新增 `feainterface` 子类，在 `define_interface()` 中调用 |
| 新目标/约束 | 新增 `objectivefuncs` 类，挂到对应更新器 |
| 新材料参数化 | 继承 `SIMP_BSPFieldMaterials`，重写 `_map_bsp_designfield` |
| 新优化类型 | 创建新的子包（如 `shapeopt` / `simp` 模式），继承 `BaseUpdater` |
