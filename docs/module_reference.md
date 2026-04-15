# 模块参考（module reference）

本文基于当前项目代码（`src/morphopt`）整理模块定义方式与功能职责。

## 1. 顶层包 `morphopt`

### 1.1 `src/morphopt/__init__.py`

定义方式：统一导出核心类与入口函数，形成对外 API。

主要导出：

- 核心流程：`Controller`, `Params`, `MorphSolver`, `Updaters`, `ObjectiveFunction`, `History`。
- 参数模块：`GeometryParams`, `FEAParams`, `Materials`, `SIMPMaterials`。
- 更新器：`UpdaterGeometries`, `UpdaterMaterials`。
- 运行入口：`start_optimization`, `debug_optimization`, `view_optimization_result`。
- 协同设计子包：`codesign`。

功能：

- 作为项目公共入口，减少业务脚本中的导入复杂度。

### 1.2 `src/morphopt/opt_runner.py`

定义方式：函数式入口封装，内部通过多进程启动优化和 UI。

功能：

- `start_optimization(...)`：启动优化主进程，可选 GUI。
- `debug_optimization(...)`：在当前进程便于调试。
- `view_optimization_result(...)`：读取历史结果并启动可视化监控。

### 1.3 `src/morphopt/taskoptmization.py`

定义方式：`TaskOptimization` 类，提供类方法 `task_optimization` 和 `optmain`。

功能：

- 负责“可重启”优化循环管理。
- 每次子进程运行结束后，根据结果路径继续下一段迭代。

### 1.4 `src/morphopt/taskui.py`

定义方式：PyQt6 界面组件 + 监控线程。

功能：

- 实时显示历史曲线、表格和 PyVista 网格。
- 从消息队列读取当前迭代并刷新视图。

## 2. `optcore` 核心优化流程

### 2.1 `src/morphopt/optcore/controller.py`

定义方式：`Controller` 基类 + 四个内嵌占位类（`Params/Solver/Updater/ObjectiveFunction`）。

功能：

- 统一调度优化迭代：`initialize -> step -> record -> save`。
- 管理结果目录、重启、历史记录、并行池。
- 提供 `start_optimization` / `restart_optimization` 生命周期。

扩展方式：

- 用户通过 `class ThisController(morphopt.Controller)` 并在类内定义四大子模块来定制任务。

### 2.2 `src/morphopt/optcore/baseobject.py`

定义方式：基础对象类（被参数、求解器、更新器、目标函数继承）。

功能：

- 提供统一初始化、重初始化、保存/加载接口风格。

### 2.3 `src/morphopt/optcore/history.py`

定义方式：历史数据容器类。

功能：

- 存储并序列化迭代中的 objective、metrics、时间、网格规模、位移等。

### 2.4 `src/morphopt/optcore/solver.py`

定义方式：`MorphSolver` 类，依赖 `Params` 与 `FEAParams`。

功能：

- 进行多工况 FEA 求解。
- 支持多进程分配工况并收集结果。
- 自动把结果设备迁移回默认设备。

### 2.5 `src/morphopt/optcore/objfunc.py`

定义方式：`ObjectiveFunction` 基类。

功能：

- 管理多工况目标函数构建。
- 统一执行目标值计算和灵敏度分析。
- 提供默认 `save(...)` 导出变形图与网格。

## 3. `modelparams` 参数系统

### 3.1 `src/morphopt/optcore/modelparams/params.py`

定义方式：`Params` 聚合类，组合 `geometry + feamodel + materials`。

功能：

- 统一初始化、重初始化、保存/加载。
- 创建 FEA 模型：几何生成 -> FEA 创建 -> 材料赋值。
- 为灵敏度分析提供设计变量拆分与 assembly 修改逻辑。

### 3.2 几何参数 `geometry`

关键文件：

- `src/morphopt/optcore/modelparams/geometry/geometryparams.py`
- `src/morphopt/optcore/modelparams/geometry/geometryinterfaces/*.py`

定义方式：

- `GeometryParams` 持有 `surface_list`。
- 每个 surface 来自接口类（BSP 或 CPGEO），通过 `add_surface(...)` 注册。

功能：

- 参数化曲面维护与重初始化。
- 导出曲面文件并调用 Gmsh 生成体网格。
- 在灵敏度分析中把几何变量映射回 assembly 节点。

### 3.3 FEA 参数 `feamodel`

关键文件：

- `src/morphopt/optcore/modelparams/feamodel/feaparams.py`
- `src/morphopt/optcore/modelparams/feamodel/feainterface/*.py`

定义方式：

- 继承 `FEAParams`，重写 `define_interface()` 与 `define_steps()`。
- 通过 `add_fea_interface(...)` 注册压力/接触/力/约束/RP 等接口。

功能：

- 把 INP 转成 `torchfea` 结构。
- 创建并管理载荷接口对象。
- 每个 load step 调用 `process_fea(...)` 应用当前幅值。

### 3.4 材料参数 `materials`

关键文件：

- `src/morphopt/optcore/modelparams/materials/homogeneousmaterial.py`
- `src/morphopt/optcore/modelparams/materials/simpmaterial.py`

定义方式：

- 均质材料：直接设定 `mu/kappa/density`。
- SIMP 材料：B 样条控制点场 `_cps` 作为设计变量。

功能：

- 在 FEA 元素高斯点上计算材料参数并赋值。
- 提供材料变量更新、保存加载、体渲染可视化。

## 4. `updaters` 变量更新系统

### 4.1 `src/morphopt/optcore/updaters/updaters.py`

定义方式：`Updaters` 聚合类，可同时挂载几何和材料更新器。

功能：

- 统一调度 `initialize / update / update_variables / save / load`。

### 4.2 几何更新 `updaters/geometry`

关键文件：

- `src/morphopt/optcore/updaters/geometry/update_geometry.py`
- `src/morphopt/optcore/updaters/geometry/objectivefuncs/*.py`

定义方式：

- `UpdaterGeometries` 持有 `obj_funcs` 与 `constraints_funcs`。
- 通过 `add_objective_function` 和 `add_constraints` 注册条目。

功能：

- 根据灵敏度构建子优化问题（LBFGS）。
- 处理步长控制、约束惩罚、变量更新。

常见目标与约束：

- `ShapeDerivative`, `Fairness`, `Distance`, `boundarys.*`。

### 4.3 材料更新 `updaters/materials`

关键文件：

- `src/morphopt/optcore/updaters/materials/update_material.py`
- `src/morphopt/optcore/updaters/materials/objectivefuncs/*.py`

定义方式：

- 与几何更新器同构，面向 SIMP 控制点更新。

功能：

- 支持敏感度目标、材料分布正则和边界约束。

## 5. `codesign` 协同设计子包

### 5.1 `src/morphopt/codesign/geometry.py`

定义方式：`CodesignGeometry(GeometryParams)` 扩展。

功能：

- 支持壳层厚度与分层参数（`thickness`, `num_layers`）。
- 在几何重建后生成 C3D6 壳体体单元。
- 用目标偏移点 + 线性插层构建 offset 层节点。
- 内置 reinitialize 后的轻量形状平滑优化。

### 5.2 `src/morphopt/codesign/material.py`

定义方式：`CodesignMaterials(SIMPMaterials)` 扩展。

功能：

- 在 C3D4 上用 SIMP 分布材料。
- 在 C3D6 壳单元上单独赋予壳材料参数。

### 5.3 `src/morphopt/codesign/feaparams.py`

定义方式：`CodesignFEAParams(FEAParams)` 扩展。

功能：

- 增加对 C3D6 壳单元初始化与质量检查。
- 当壳单元高斯权重异常时给出诊断错误。

### 5.4 `src/morphopt/codesign/constraints.py`

定义方式：继承几何更新约束基类 `BaseConstraints`。

功能：

- `InwardCurvatureRadius`：限制内向主曲率，降低偏移壳自交风险。
- `OffsetSurfaceMinThickness`：在偏移面邻域点对上施加最小间距约束。

## 6. 示例与测试

### 6.1 `examples/`

定义方式：每个脚本通常定义 `ThisController`。

功能：

- 展示任务配置模板和参数组合方式。
- `examples/codesign/twist.py` 是当前最完整的协同设计示例。

### 6.2 `tests/`

功能：

- 提供偏差对比、壳层偏移等验证脚本，用于回归检查。

## 7. 典型扩展点

- 新几何接口：新增 `geometryinterfaces` 实现并在 `GeometryParams` 中注册。
- 新 FEA 接口：新增 `feainterface` 子类并在 `define_interface()` 中调用。
- 新目标/约束：新增 `objectivefuncs` 或 `codesign/constraints` 类并挂到 updater。
- 新材料参数化：继承 `SIMPMaterials` 并重写 `get_ratio`、`set_materials`。
