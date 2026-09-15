# MorphOpt V4 破坏性变更、移除清单与冻结契约

> 文档属性：维护性文档，跨主题生效。本文件记录 V3 到 V4 的**已确定破坏性变更**、**移除项
> 的替代方案**、**数据与结果契约**和**跨章冻结的数值契约**。本文件不定义新的类与方法；
> 类与方法以第 1–17 章为准，本文件只声明这些接口取代了什么、哪些旧入口不再存在。
>
> V4 不做兼容读取：旧结果目录、旧 `.morph` 文件、旧任务脚本和旧脚本工具都不保证可用。

返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

| 项目 | 内容 |
|---|---|
| 输入 | 第 1–17 章接口定义、第 18–23 章迁移与校验记录、跨章数值默认值、工具与脚本能力 |
| 输出 | 移除清单与替代方案、行为变更清单、结果与数据契约、冻结数值契约、工具归属 |
| 主要读者 | 全部 V4 实现者、测试编写者、任务脚本作者和文档维护者 |
| 关联文档 | [总入口](../unified_model_architecture_plan.md)、[架构总览](01-04Overview.md)、[校验与迁移](18-22ValidationMigration.md)、[功能基线](23FunctionInventory.md) |

### 目录

- [24.1 使用规则](#241-使用规则)
- [24.2 移除清单与替代方案](#242-移除清单与替代方案)
- [24.3 行为变更清单](#243-行为变更清单)
- [24.4 结果与持久化契约](#244-结果与持久化契约)
- [24.5 冻结数值契约](#245-冻结数值契约)
- [24.6 工具、脚本与打包归属](#246-工具脚本与打包归属)

## 24.1 使用规则

1. 第 1–17 章是接口的唯一权威。本文件中出现但未在第 1–17 章定义的名称，只用于说明
   被移除的旧入口，不得出现在 V4 代码或任务脚本中。
2. 24.2 的每个移除项都必须在同一行给出 V4 替代；没有替代的能力直接删除，不再保留。
3. 24.3 的行为变更对用户可见，任务脚本、示例、UI 生成代码和文档必须按新语义编写。
4. 24.4 与 24.5 是跨章冻结值。修改其中任意一项时，必须在同一提交内同步修改本文件、
   所属主题章和对应验收标准。
5. 本文件不记录迁移步骤。V4 只支持从第 1–17 章定义的任务文件重新开始运行。

## 24.2 移除清单与替代方案

### 24.2.1 几何与模型导入

| 移除的 V3 入口 | V4 替代 | 说明 |
|---|---|---|
| `FixedGeometry` | 无 | 整模型固定不再存在；固定模型一律通过 `INPPart` 或 `TorchFEAPart` 注册为具体 `Part` |
| `FixedGeometryINP(mesh_file, part_name)` | `INPPart` | INP 源 Assembly 只作为读取缓存，输出 Part 由定义对象显式声明 |
| `FixedGeometryTorchFEA(model_directory, model_filename)` | `TorchFEAPart` | 模型目录、文件名、源 Part 和实例选择全部显式声明 |
| `MeshGenerator` | `MeshBuilder` | 外部网格后端由 `BoundaryPart.build_part()` 编排，`MeshBuilder` 保持可替换 |
| `FixedSurface(vertices, faces)` | `STLSurface` | STL 几何统一使用 `STLSurface.from_stl()` / `from_mesh()` |
| `GeometryParams.add_surface()`、`num_surface`、`num_variables_list` | `BoundaryPart.define_surfaces()`、`add_surface()`、`get_parameters()` | 曲面注册和设计参数归属具体的边界 Part |
| `GeometryParams.update_variables()`、`get_variables()`、`obtain_design_sensitivity_vars()`、`modify_assembly()` | `Updatable` 的 `build_design_delta()`、`get_design_delta()`、`update_assembly()`、`apply_design_delta()` | 设计变量接口统一由协议定义 |
| `GeometryParams.apply_surface_constraints()`（空钩子） | 几何 updater 的 `_apply_equality_constraint()` | 等式投影改为 updater 持有的唯一约束 |
| `CodesignGeometry`、`CodesignFEAParams` | `OffsetShellPart` + 通用 `BoundaryPartUpdater` / `OffsetShellPartUpdater` / `MaterialUpdater` | codesign 不再是独立子系统，只是对象组合；不设 codesign 专属类、scheme 或章节 |
| `GeometryParams` 的 `mesh_order` 后处理分支 | `BoundaryPart` 构造属性 + `MeshBuilder` | 二阶转换由 Part 的 `build_part()` 统一完成 |
| `_iter_since_last_regenerate`、`_max_iter_before_regenerate`、`_nodes_last_regenerate`、`_max_nodes_change` | 无 | 增量重网格判据整体移除；网格每轮重建，见 24.3 |

### 24.2.2 材料

| 移除的 V3 入口 | V4 替代 | 说明 |
|---|---|---|
| `MaterialsParams.add_material_interface(interface, name)` | `add_material(interface, name)` | 材料对象自身携带 `part_name` 与 `element_name` |
| `MaterialsParams.interfaces()`、`design_interfaces()` | `get_interfaces()`、`get_design_interfaces()` | 命名统一为 `get_*` 只读访问 |
| `MaterialsParams.set_materials(fe)` | `build_materials()` + `assign_materials()` | 建立与写入分离 |
| `MaterialsParams.get_variables()`、`update_variables()`、`obtain_design_sensitivity_vars()`、`modify_assembly()` | `get_design_owners()` + `Updatable` 协议 | 材料场作为 owner 交给 `DesignRegistry` |
| `elementname=""` 通配含义 | 每个材料对象只覆盖一个 `element_name` | 需要覆盖多个元素族时注册多个材料对象 |
| `SIMP_BSPFieldMaterials` | `SIMPFieldMaterial` | 名称与模块路径统一 |
| `SIMPElementFgrad`、`SIMPElementFskew`、`SIMPElementHuHu_LuLu` | `SIMPElementPenalty(penalty_mode=...)` | 三种罚项合并为一个类，模式显式配置 |
| `get_material_ratio()`、`get_penalty_factor()` | `compute_material_ratio()`、`compute_penalty_factor()` | 纯计算语义 |
| `if_use_simppenalty` | `use_simp_penalty` | property 命名统一 |
| `p_order_interpolation()` 的"预留但未接入"状态 | `compute_power_interpolation()` + 显式插值配置 | 插值方式由材料配置选择，不保留死接口 |

### 24.2.3 FEA、Solver 与目标

| 移除的 V3 入口 | V4 替代 | 说明 |
|---|---|---|
| `ReferencePointInterface(rp_location)` | `ReferencePoint(name, position)` | 参考点归属几何层，FEA component 按名称引用 |
| `FEAParams.add_fea_interface()` | `add_component()` | 组件注册入口统一 |
| `FEAParams.set_step_num()`、`set_step_params()` | `set_num_steps()`、`set_step_values()` | 工况入口统一 |
| `FEAParams.create_fea()`、`process_fea()` | `build_components()`、`assign_components()`、`update_fea()` | 建立、挂接、更新分离 |
| `FEAParams.add_instance_from_inp()` | `INPPart` / `TorchFEAPart` + `InstanceDefinition` | 模型导入只走几何系统 |
| `FEAParams` 的 `get_variables()`、`update_variables()`、`get_parameters()`、`set_parameters()` | `LoadValueBlock` + `FEAUpdater` | 载荷设计变量由逐工况变量块承担 |
| `Solver.solve()` 的位置式结果顺序 | `Solver.solve(fea_controllers, jacobian_names, initial_gc_by_case)` + `get_results()` | 结果按 `step_index` 排序并校验 |
| `SIMPSolver` 及从磁盘结果恢复 GC | `Solver` 的 `_previous_gc_by_case`、`set_reuse_previous_solution()` | GC 复用归入 Solver 自身状态 |
| `ObjectiveFunction.__getitem__()` | `fe_results[case_index]`、`get_case_objective(case_index)` | 按结果类型显式读取 |
| `ObjectiveFunction.sensitivity_analysis(params)` | `SensitivityAnalyzer.build_sensitivities()` | 灵敏度分析独立成类 |
| `jacobian_needed` 可写 `list` | 只读 `jacobian_needed` property + `_jacobian_needed` 构造状态 | 在构造阶段一次性声明 |
| `metrics` 无名 `list[float]` | `metric_names` + 逐工况 `tuple[float, ...]` | 指标名称与顺序成为稳定契约 |
| `ObjectiveFunction.plot()` 直接弹窗 | `build_mesh_case()` + `get_mesh_case()` + Viewer | 目标只提供数据，绘制归 Viewer |

### 24.2.4 Updater、运行时与工具

| 移除的 V3 入口 | V4 替代 | 说明 |
|---|---|---|
| `Updaters(surfaces=, materials=, device=)` | `Updaters.define_updaters()` + `add_updater()` | 任意数量 updater，按 entry 注册 |
| `Updater.add_constraints()`、`add_objective_function()` | 具体 updater 的 `add_constraint()`、`add_regularization()` + 固定 `LocalSensitivityObjective` | 局部目标自动建立，不再手工注入 |
| `UpdaterLoads`（仅存在于注释） | `FEAUpdater` | 载荷更新成为一等能力 |
| `BaseObject`、`pathlog_required()` | 无 | 导出根目录由 `Controller` 与 `ObjectiveFunction.export_case_result()` 决定 |
| 模块级 `morphopt.controller` 全局 | 无 | 所有对象通过构造参数或 `initialize()` 注入 `Controller` 持有对象 |
| `enable_logging()` | `configure_logging(log_path, level, console)` | 日志配置归 `morphopt.logging` |
| `TaskOptimization`、`start_optimization()`、`debug_optimization()` | `TaskRunner.start()`、`TaskRunner.run_debug()` | 任务进程、退出码与续跑由 `TaskRunner` 统一管理 |
| `History.append()`、`history_objective` 等逐序列访问器 | `History.add_record()`、`get_records()`、`get_series(name)` | 记录与序列访问统一 |
| `check_gradients()` 打印文本报告 | `check_gradients(controller, options)` 返回 `GradientCheckReport` | 结构化报告用于 CI 门禁 |
| `get_controller()` | `load_controller(result_path, iteration=None)` | 从 checkpoint manifest 装载 |
| `Controller.dataqueue` | `Controller.data_queue` + `RuntimeEvent` | 结构化、版本化事件 |
| `Controller.restart_per_iteration` | `Controller.worker_restart_interval` + `checkpoint_interval` | 资源回收与持久化解耦 |

### 24.2.5 UI 与 Codegen

| 移除的 V3 入口 | V4 替代 | 说明 |
|---|---|---|
| `GeometryNode`、`SurfaceNode` | `GeometryNode` + `PartNode` + `ReferencePointNode` | Part 成为几何定义的一级节点 |
| `InterfaceNode` | `FEAComponentNode` | 节点命名与领域类对齐 |
| `StepsNode` | `LoadStepsNode` | 同上 |
| `scheme="codesign"` 及 `schemes/codesign.py` | 无 | codesign 不是 scheme；UI 只提供 `shapeopt` 与 `simp` 两个模板，其余由对象组合表达 |
| `UPDATER_CATALOG` 按 scheme 分组的约束项 | 按 `target_kind` 组织的 updater 项目录 | `InwardCurvatureRadius`、`OffsetSurfaceMinThickness` 等归入 `offset_shell_part` 目标 |
| `UpdaterNode` 的 `geometry` / `materials` 子字典 | `UpdaterNode.target_kind` + `target_name` + 局部项列表 | 与 `UpdaterEntry` 一对一模型一致 |
| `UpdaterNode.code` 原始代码逃生口 | 局部项结构化编辑 + 任务文件自由编辑 | UI 只生成结构化节点 |
| `TorchFEAModelSummary.part_for_instance()` | `TorchFEAModelSummary.generate_tree()` | 摘要以树结构提供 |
| UI 进程内 import 任务模块与构建 Assembly | 隔离预览进程 + `Workbench.build_preview()` | UI 进程不创建运行时对象 |
| `.morph` `version: 1` | `schema_version: 2` | 见 24.4.3；不提供 v1 读取 |
| i18n 语言码 `"zh"` / `"en"` | `zh_CN` / `en_US` | 持久化值不兼容，加载时回落到默认语言 |

## 24.3 行为变更清单

| 项目 | V3 行为 | V4 行为 | 影响面 |
|---|---|---|---|
| surface set 命名 | `surface_{i}_All`、`surface_0_Head`、`surface_0_Bottom` | `surface_{i}_all`、`surface_{i}_head`、`surface_{i}_bottom`、`surface_{i}_lateral` | 全部载荷集合选择器、示例与任务脚本 |
| 整体外表面归属 | `Instance.exterior_surface` 是普通属性 | 名称与内容统一由 `Part` 持有（默认 `extern`），`Instance.exterior_surface` 转发读写同一份值，与 torchfea 的 `Part.exterior_surface` / `Instance.exterior_surface` 行为一致 | 压力与边界条件目标 |
| 二阶转换 | 体积网格转二阶后再追加楔形带，楔形不进入 `mid_pt_idxmap` | 先建齐全部线性族（实体 + 楔形）再一次调用转换，映射同时覆盖 `C3D10` 与 `C3D15` | `mesh_order == 2` 的偏置壳算例 |
| 参数方向 `flip` | 构造参数；`flip=False` 时对 `u` 方向导数取负 | 运行时状态，由 `BoundaryPart.initialize()` 按曲面序号设置（第 0 个 `False`，其余 `True`）；`flip=True` 反向 `v` | 切向量、法向、Fairness、带符号曲率 |
| 生成型 Part 的元素名称 | 直接采用网格 INP 的 `elems` 键 | 构造函数必填 `element_name`，并校验生成结果中存在该元素族 | 材料目标、载荷目标 |
| 导入 Part 的元素名称 | 按源模型键顺序 | 按 `C3D4`、`C3D6`、`C3D8`、`C3D10`、`C3D15`、`C3D20` 排序，未列出类型按源顺序追加 | 材料覆盖与 `element_names` 长度校验 |
| 求解收敛容差 | `tol_error=1e-7` | `Solver.error_tolerance=1e-5` | 收敛速度与结果尾数 |
| 默认计算设备 | 有 GPU 时自动使用 CUDA | `Solver.device_names=()` 表示 CPU；CUDA 必须显式声明 | 运行环境与性能 |
| 非收敛处理 | 抛出 `ValueError` 中止运行 | 抛出求解错误并中止本次 `step()`；不返回部分结果 | 错误处理与重试 |
| 指标计算时机 | updater 提交之后 | `ObjectiveFunction.build_evaluation()` 之内，即设计提交之前 | 由设计变量派生的指标 |
| 设计变量初值 | `randn * 1e-6` | 全零增量（`requires_grad=True` 叶子） | 优化轨迹 |
| 载荷变量全局顺序 | step 优先 | category → 名称 → `case_index` | 变量顺序与诊断输出 |
| 结果目录与文件名 | `log/deformation/task_k_iter_n.*`、`log/femodel&results/*` | 逐迭代目录 + 逐工况制品（见 24.4.1） | Observer、后处理 |
| 任务脚本约定 | `scripts/MAIN_SCRIPT_FOR_RESTART.py` + `ThisController` | 任务文件路径记录在 checkpoint manifest | 续跑与 UI 装载 |
| UI 运行时对象 | UI 进程内创建 | 只在任务进程或隔离预览进程创建 | UI 稳定性 |
| 网格重建 | 每轮重建，但保留未生效的增量重网格状态字段 | 每轮重建，移除全部增量重网格状态与判据 | 几何迭代行为 |
| 设计变量布局 | 运行期可能因曲面细化改变控制点数量 | 布局在 `finalize()` 后冻结，变化即抛错 | CPGEO 重构、材料场分辨率 |

## 24.4 结果与持久化契约

### 24.4.1 运行目录

~~~text
<result_root>/<optimization_name>/
├── log/
│   ├── morphopt.log
│   └── torchfea.log
├── state/                      # 每 iteration 的对象状态与 checkpoint manifest
├── results/iter_<n>/           # 每 iteration 的制品目录，见 24.4.2
├── cache/
├── fea/
└── scripts/                    # 任务源码快照，用于 load_controller()
~~~

`<result_root>` 由 `Controller.result_root` 决定，默认 `.results`。UI 启动的任务把
`<result_root>` 设为运行根目录下的 `ui_runs/`。

### 24.4.2 逐工况制品

`results/iter_<n>/case_<i>/` 内容固定为：

| 文件 | 生产者 | 内容 |
|---|---|---|
| `model.npz` | `FEAController.save_model()` | 当前工况模型 |
| `result.npz` | `StaticResult.save()` | 平衡结果 |
| `jacobian.npz` | `ObjectiveFunction.export_case_result()` | 请求的响应矩阵 |
| `deformation.stl` | 同上 | 合并后的变形网格 |
| `preview.png` | 同上 | 统一离屏渲染预览 |
| `manifest.json` | 同上 | 见 24.4.3 |

所有文件必须通过先写临时文件再原子重命名的方式落盘。迭代目录在全部工况写出成功后才
视为完整。

### 24.4.3 manifest 字段

| 字段 | 含义 |
|---|---|
| `schema_version` | 制品与 checkpoint 结构版本，当前为 `2` |
| `iteration` | 迭代索引 |
| `case_index` | 工况索引 |
| `model_hash` | `FEAController.get_model_hash()` |
| `task_signature` | 任务文件路径、类路径与依赖版本摘要 |
| `design_signature` | 设计变量块 key、形状与顺序摘要 |
| `files` | 文件角色到相对路径的映射 |
| `complete` | 该 checkpoint 是否为完整 checkpoint |

`load()` 与 `load_controller()` 只接受 `complete=true` 且 `schema_version`、`task_signature`、
`design_signature` 与当前定义一致的 manifest；否则抛出装载错误。

## 24.5 冻结数值契约

以下数值是 V4 的默认契约。缺省实现必须使用这些值；用户显式配置时以配置为准。

### 24.5.1 求解与优化

| 项目 | 值 | 所属章节 |
|---|---|---|
| 单工况最大迭代次数 | `10000` | [Solver](08Solver.md) |
| 收敛误差容差 | `1e-5` | [Solver](08Solver.md) |
| 切线矩阵校验阈值 | `1e-12` | [目标函数](09Objective.md) |
| worker 数量 | `4` | [Solver](08Solver.md) |
| 内层优化迭代上限 | `20` | [Updater](11-12Updaters.md) |
| L-BFGS 曲率历史长度 | `10` | [Updater](11-12Updaters.md) |
| 回退线搜索初始步长 / 收缩比 / Armijo 系数 | `1.0` / `0.5` / `1e-4` | [Updater](11-12Updaters.md) |
| 步长相对下限 / 衰减 / 增长 | `0.1` / `0.5` / `1.5` | [Updater](11-12Updaters.md) |
| 外层迭代上限 / checkpoint 间隔 / 子进程回收间隔 | `100` / `1` / `20` | [运行时](13-14Runtime.md) |
| 设计增量初值 | 全零、`requires_grad=True` | [设计变量注册](10DesignRegistry.md) |

### 24.5.2 设计变量步长映射

所有 `update_assembly(design_delta)` 实现按同一饱和映射把局部设计增量写入模型：

~~~text
dx = (2 / pi) * atan(|x|) * sign(x) * step_limit
~~~

其中 `x` 为优化器给出的本步增量，`step_limit` 是逐变量的步长上限向量（长度等于该 owner
的变量数），由 updater 的 `_update_step_limits()` 按 24.5.1 的增长/衰减系数维护。该映射
保证单步变化幅度上界为 `step_limit`，且随增量增大进入饱和。

### 24.5.3 几何

| 项目 | 值 | 所属章节 |
|---|---|---|
| 曲面参数域裁剪 | `u, v ∈ [0, 1]` | [几何系统](05Geometry.md) |
| 节点匹配最大迭代 | BSP `10`、CPGEO `5` | [几何系统](05Geometry.md) |
| 节点匹配收敛容差 | `1e-2` | [几何系统](05Geometry.md) |
| 节点匹配批大小 | BSP `40960`、CPGEO `4096` | [几何系统](05Geometry.md) |
| 端点节点排除判据 | 与极值控制点的 `|z|` 差小于 `1e-5` | [几何系统](05Geometry.md) |
| 网格尺寸 | 最大 `fea_seed_size`，最小 `0.5 × fea_seed_size` | [几何系统](05Geometry.md) |
| 偏置层分布 | `alpha = layer / num_layers`，位移总量为厚度 | [几何系统](05Geometry.md) |
| BSP 采样比例 | `u`、`v` 各 `2 × 控制点跨度` | [几何系统](05Geometry.md) |
| CPGEO 影响半径点数 | `20` | [几何系统](05Geometry.md) |

### 24.5.4 材料

| 项目 | 值 | 所属章节 |
|---|---|---|
| 初始设计场值 | 控制点初值为用户给定的实数偏置，经 `sigmoid` 后成为材料比例；默认 `0.0` | [材料系统](06Materials.md) |
| 默认插值 | RAMP，指数 `material_penalty` 默认 `8` | [材料系统](06Materials.md) |
| 罚项开关 | `void_penalty_factor <= 0` 时 `use_simp_penalty=False`，元素族保持原生实现 | [材料系统](06Materials.md) |
| 罚项模式默认值 | `skew` | [材料系统](06Materials.md) |
| 材料比例下限 | `simp_ratio_min`，默认 `0.0` | [材料系统](06Materials.md) |
| 设计场持久化精度 | `float32` | [材料系统](06Materials.md) |
| 材料场预览标量 | `density = material_ratio × mumax` | [材料系统](06Materials.md) |

## 24.6 工具、脚本与打包归属

### 24.6.1 移除的仓库脚本

仓库根 `scripts/` 目录整体删除。原能力按下列方式进入包内 API：

| 原脚本 | 能力 | V4 归属 |
|---|---|---|
| `scripts/optimization/restartopt.py` | 从结果目录续跑 | `TaskRunner(restart_path=..., target_iteration=...)` 或 `Controller.restart_optimization()`；`load_controller()` 供外部工具使用 |
| `scripts/postprocess/readhistoryparams.py` | 重建优化器状态并检查参数 | `load_controller()` + `DesignRegistry.get_blocks()` |
| `scripts/postprocess/buildfe.py` | 重建 FEA 并改工况再求解 | `load_controller()` + `FEAParams.update_fea()` + `Solver.solve()` |
| `scripts/postprocess/plot_history_params.py`、`plot_history_surface.py` | 参数/曲面历史绘图 | `History.get_series()` + `load_controller()` 后的几何对象；绘图代码属于用户侧 |
| `scripts/postprocess/obj2gif.py`、`historydeformation.py` | 变形序列动画 | `History.get_result_paths()` + `ObjectiveFunction.export_case_result()` 产出的 `deformation.stl` |

### 24.6.2 包内工具模块

| 模块 | 内容 |
|---|---|
| `morphopt/__init__.py` | 导出 `Controller`、`Params`、`GeometryParams`、`MaterialsParams`、`FEAParams`、`Solver`、`ObjectiveFunction`、`Updaters`、`History`、`TaskRunner`、`configure_logging`、`check_gradients`、`load_controller`、`start_optimization` |
| `morphopt/logging.py` | `configure_logging()` |
| `morphopt/task.py` | `TaskRunner`、`start_optimization()` |
| `optcore/protocols.py` | `Initializable`、`Updatable`、`Visualizable`、`Persistable` |
| `utils/gradientCheck.py` | `check_gradients()`、`GradientCheckOptions`、`GradientCheckEntry`、`GradientCheckReport` |
| `utils/historyRead.py` | `load_controller()` |

### 24.6.3 打包

`pyproject.toml` 的包名保持 `morphopt`，包目录为 `src/morphopt`，控制台入口为
`morphopt-ui = "morphopt.ui:run_app"`。结果目录同时写入依赖快照（`morphopt`、`torchfea`、
`cpgeo`）到 `scripts/`，使结果目录可以独立复跑；`load_controller()` 优先使用快照，
manifest 的 `task_signature` 记录依赖版本用于校验。
