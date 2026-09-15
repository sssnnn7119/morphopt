# MorphOpt V4 目标函数

本文件定义顶层目标、展示指标、结果工况、Jacobian 选择、结果网格和全局灵敏度边界。
返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

`ObjectiveFunction` 接收逐工况 `FEAController` 和按 `step_index` 排序的 `StaticResult`，建立一次
目标评估缓存；`SensitivityAnalyzer` 使用静力平衡方程、切线刚度和载荷 Jacobian 建立总灵敏度。
Controller 读取标量目标、指标和全局灵敏度，并把灵敏度按 `DesignRegistry` 的变量块交给
updater。用户任务通过重写纯计算钩子定义具体目标和指标。

### 目录

- [9.1 `ObjectiveFunction`](#91-objectivefunction)
- [9.2 评估、Jacobian 与灵敏度流程](#92-评估jacobian-与灵敏度流程)
- [9.3 `SensitivityAnalyzer`](#93-sensitivityanalyzer)
- [9.4 V3 目标与约束功能归属](#94-v3-目标与约束功能归属)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 逐工况 `FEAController`、`StaticResult`、目标与指标代码、Jacobian 组件名称、设计变量注册表 |
| 输出 | 标量目标、逐工况指标、逐工况结果、结果网格、原生结果制品和按 `DesignKey` 切分的灵敏度 |
| 主要读者 | Objective、Controller、Updater、Codegen、Observer 和测试实现者 |
| 关联文档 | [FEA 组件](07Fea.md)、[Solver](08Solver.md)、[设计变量](10DesignRegistry.md)、[Updater](11-12Updaters.md)、[History](15History.md) |

## 9.1 `ObjectiveFunction`

`ObjectiveFunction` 实现 `Initializable` 和 `Persistable`。`initialize()` 校验静态定义；
`reinitialize()` 绑定一次迭代的 Assembly 和结果；`build_evaluation()` 建立可重复读取的
目标与指标缓存。`compute_*` 钩子保持纯计算语义。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_jacobian_needed` | tuple[str, ...] | `()` | 需要 Solver 保存 Jacobian 的参数化 FEA component 名称 |
| `_metric_names` | tuple[str, ...] | `()` | `compute_case_metrics()` 返回值的稳定名称和顺序 |
| `_case_weights` | tuple[float, ...] 或 None | None | 多工况加权系数；省略时每个工况权重为 1 |

### 运行时属性（`__init__()` 声明，生命周期方法填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_iteration` | int 或 None | None | 当前评估所属迭代 |
| `_fea_controllers` | Mapping[int, `torchfea.FEAController`] | `{}` | 当前结果对应的逐工况 TorchFEA 控制器 |
| `_fe_results` | tuple[`StaticResult`, ...] | `()` | 按 `step_index` 排序的当前工况结果 |
| `_case_objectives` | tuple[torch.Tensor, ...] | `()` | 已建立的逐工况标量目标 |
| `_objective` | torch.Tensor 或 None | None | 已建立的多工况标量目标 |
| `_metrics_by_case` | tuple[tuple[float, ...], ...] | `()` | 已建立的逐工况展示指标 |
| `_mesh_cases` | dict[int, tuple[object, ...]] | `{}` | 已建立的逐工况结果网格 |
| `_initialized` | bool | False | 静态定义校验状态 |

### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `jacobian_needed` | tuple[str, ...] | - | 只读 | 内部维护 | 返回 Jacobian 组件名称 |
| `metric_names` | tuple[str, ...] | - | 只读 | 内部维护 | 返回指标名称 |
| `case_weights` | tuple[float, ...] 或 None | - | 只读 | 内部维护 | 返回工况权重 |
| `fe_results` | tuple[`StaticResult`, ...] | - | 只读 | 内部维护 | 返回按 `step_index` 排序的当前工况结果元组 |

`fe_results` 是任务代码、UI 动态补全和 Codegen 共同依赖的稳定读取面：
`fe_results[case_index].GC`、`fe_results[case_index].jacobian[component_name]` 必须始终可用。
按工况读取结果用 `fe_results[case_index]`，工况数量用 `len(fe_results)`，因此不再提供
`get_fe_results()` 与 `get_num_cases()`。

### 外部接口方法

本类独有的读取方法只访问已建立缓存；纯计算钩子可由任务子类重写。

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `build_evaluation()` | None | - | 使用当前逐工况控制器和结果建立目标及指标缓存 |
| `build_mesh_case(case_index)` | None | - | 使用指定工况结果建立并缓存可视化网格 |
| `export_case_result(target_path, case_index)` | pathlib.Path | - | 将指定工况的原生模型、原生结果、Jacobian、变形网格、预览图和 manifest 导出到目标目录 |
| `get_objective()` | torch.Tensor | - | 读取已经建立的总目标 |
| `get_case_objective(case_index)` | torch.Tensor | - | 读取已经建立的逐工况目标 |
| `get_metrics(case_index)` | tuple[float, ...] | - | 读取指定工况已经建立的指标 |
| `get_mesh_case(case_index)` | tuple[object, ...] | - | 读取指定工况已经建立的结果网格 |
| `compute_case_objective(case_index, assembly, result)` | torch.Tensor | - | 由任务子类纯计算一个工况的标量目标 |
| `compute_multistep_objective(case_objectives)` | torch.Tensor | - | 按 `case_weights` 纯计算多工况聚合目标 |
| `compute_case_metrics(case_index, assembly, result)` | tuple[float, ...] | - | 由任务子类纯计算一个工况的展示指标 |
| `compute_objective(case_assemblies, fe_results)` | torch.Tensor | - | 使用显式逐工况 Assembly 上下文纯计算多工况总目标，供灵敏度分析复用 |
| `initialize(fea_params)` | None | `Initializable` | 校验组件引用、指标定义、工况权重和 Jacobian 请求 |
| `reinitialize(iteration, fea_controllers, fe_results)` | None | `Initializable` | 绑定当前逐工况控制器与结果并清空上一轮评估和网格缓存 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存本轮目标、指标、结果制品索引和 Jacobian 请求 |
| `load(folder_path, iteration)` | None | `Persistable` | 恢复指定迭代的目标、指标和结果制品索引 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_validate_case_index(case_index)` | None | 校验工况索引范围 |
| `_validate_scalar_objective(value, case_index)` | None | 校验目标为有限标量 Tensor |
| `_validate_metrics(values, case_index)` | None | 校验指标数量、顺序和有限性 |
| `_validate_jacobian_requests(fea_params)` | None | 校验名称存在、组件具有参数并参与至少一个工况 |
| `_build_result_mesh(assembly, result)` | tuple[object, ...] | 从对应工况 Assembly 和结果构造变形后网格、标量和向量数据 |
| `_write_case_manifest(target_path, case_index, files)` | None | 写入模型哈希、迭代、工况、文件角色、相对路径和 schema 版本 |

## 9.2 评估、Jacobian 与灵敏度流程

一次结果评估按以下顺序执行：

```text
objective.reinitialize(iteration, fea_controllers, results)
objective.build_evaluation()
objective_value = objective.get_objective()
metrics = [objective.get_metrics(i) for i in range(num_steps)]
sensitivity.reinitialize(iteration, results)
sensitivity.build_sensitivities()
sensitivities = sensitivity.get_sensitivities()
```

`build_evaluation()` 对每个 `case_index` 调用 `compute_case_objective()` 和
`compute_case_metrics()`，然后调用 `compute_multistep_objective()`。目标缓存用于输出、历史和
局部目标基准值；展示指标转换为 detached Python 浮点数。总灵敏度由
`SensitivityAnalyzer` 在可微试探 Assembly 上重新建立目标上下文，并通过隐式/伴随方程计算。

`jacobian_needed` 中的每个名称引用 `FEAParams.fea_components` 中一个 `num_values > 0` 的
component。Solver 在对应工况求解时把该组件的 Jacobian 写入
`StaticResult.jacobian[component_name]`。刚度模板同时选择集中力、集中力矩和参考点；
初始化校验三者引用同一个 `reference_point`。参考点广义自由度区间使用
`Assembly._RGC_list_indexStart[reference_point._RGC_index]` 的起止索引取得，形成该参考点的
`6 × 6` 位移—转角响应 Jacobian；参考点在装配阶段声明 6 个广义自由度需求。`Assembly` 同时
维护 `_GC_list_indexStart` 与 `_RGC_list_indexStart`，Jacobian 行索引必须使用约束广义自由度
`RGC`（对象的 `_RGC_index`），不使用 `GC`。

`build_mesh_case(case_index)` 读取对应控制器的 Assembly，再将结果 `GC` 转为实例节点
位移、变形后坐标、单元标量和载荷显示数据。Observer 使用 `get_mesh_case()` 读取缓存，
共享 [UI 文档](16-17UiCodegen.md) 定义的 Viewer 风格、色图和相机约定。

`export_case_result()` 建立稳定的工况制品目录：`model.npz` 由
`FEAController.save_model()` 写出，`result.npz` 由 `StaticResult.save()` 写出，
`jacobian.npz` 保存请求的响应矩阵，`deformation.stl` 保存合并后的变形网格，
`preview.png` 使用统一离屏 Viewer 风格渲染，`manifest.json` 记录全部文件及
`FEAController.get_model_hash()`。导出前校验 `StaticResult.model_hash` 与当前模型哈希一致；
Observer 按 manifest 装载模型与结果。

## 9.3 `SensitivityAnalyzer`

`SensitivityAnalyzer` 只做四件事：拼接全局设计变量、把设计变量写回基座 Assembly、调用 TorchFEA 的
多工况伴随函数、按变量块切分并保存结果。伴随方程本身完全由
`StaticImplicitSolver.get_jacobian_sensitivity_multistep()` 提供，morphopt 不实现第二份伴随推导。
基座 Assembly 是几何与材料状态的共享载体，逐工况 work condition 由库函数按结果自带的
`work_conditions` 逐个恢复。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | 本类没有构造属性 |

### 运行时属性（`__init__()` 声明，生命周期方法填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_objective` | `ObjectiveFunction` 或 None | None | 已绑定顶层目标 |
| `_registry` | `DesignRegistry` 或 None | None | 已绑定设计变量注册表 |
| `_solver` | `StaticImplicitSolver` 或 None | None | 绑定基座 Assembly 的静力求解器，由 `Solver.get_sensitivity_solver()` 提供 |
| `_design_vars` | torch.Tensor 或 None | None | 本次分析使用的全局设计变量叶子 |
| `_iteration` | int 或 None | None | 当前分析迭代 |
| `_fe_results` | tuple[`StaticResult`, ...] | `()` | 当前平衡结果的 detached 引用 |
| `_sensitivities` | dict[`DesignKey`, torch.Tensor] | `{}` | 已建立的 detached 局部总灵敏度 |
| `_initialized` | bool | False | 绑定状态 |

### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| 空 | - | - | - | - | 运行时状态通过 `get_sensitivities()` 读取 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `build_sensitivities()` | None | - | 建立当前多工况目标对全局设计增量的总导数并保存分块结果 |
| `get_sensitivities()` | Mapping[`DesignKey`, torch.Tensor] | - | 读取已经建立的局部总灵敏度 |
| `initialize(objective, registry, solver)` | None | `Initializable` | 绑定目标、注册表和基座求解器 |
| `reinitialize(iteration, fe_results)` | None | `Initializable` | 绑定当前平衡结果并清空上一轮灵敏度缓存 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_build_design_vars()` | torch.Tensor | 按 `DesignBlock` 顺序拼接各 owner 的设计增量并建立 `requires_grad` 叶子 |
| `_apply_design_vars(assembly, design_vars)` | None | 按 `DesignBlock` 切片写回各 owner 的试探状态，等价于 V3 的 `params.modify_assembly()` |
| `_split_gradients(gradient)` | Mapping[`DesignKey`, torch.Tensor] | 按 `DesignBlock` 切分梯度并 detach |

`build_sensitivities()` 的固定流程为：

```text
1. design_vars = _build_design_vars()
2. registry.update_assembly(design_vars, categories={"geometry", "material"})
3. gradient = solver.get_jacobian_sensitivity_multistep(
       fe_results=list(fe_results),
       design_vars=design_vars,
       load_names=list(objective.jacobian_needed),
       apply_func=_apply_design_vars,
       compute_objective_funcs=objective.compute_objective)
4. sensitivities = _split_gradients(gradient)
5. 恢复零试探状态并清空 `_design_vars`
```

库函数与 morphopt 的职责边界固定如下，实现时不得重复实现对方的工作：

| 项目 | 归属 |
|---|---|
| 设计变量写入 Assembly、逐工况恢复 work condition、因子分解切线、建立 GC/Jacobian 梯度叶子、伴随求解与向量—Jacobian 积 | `StaticImplicitSolver.get_jacobian_sensitivity_multistep()` |
| 多工况目标建立 | `ObjectiveFunction.compute_objective(case_assemblies, fe_results)`，作为 `compute_objective_funcs` 传入 |
| 设计变量到模型状态的映射 | `_apply_design_vars()`，与 `DesignRegistry.update_assembly()` 使用同一套切片规则 |
| 梯度切分、detach、缓存与试探状态恢复 | `SensitivityAnalyzer` |

库函数会**就地替换**每个 `StaticResult` 的 `GC` 与 `jacobian` 为带梯度的副本，因此
`SensitivityAnalyzer` 在调用前保存 detached 结果引用、调用后恢复，避免梯度状态泄漏到
下一轮迭代或结果导出。未参与当前目标计算的变量块得到同形状零梯度；所有返回块与
`DesignRegistry` 的 device、dtype、形状和稳定顺序一致。

#### 9.3.1 计算图生命周期

计算图的建立范围只有一处，规则如下：

| 阶段 | 图状态 |
|---|---|
| `build_part()`、`build_case_assemblies()`、`update_trial_models()` | 全部在 detached 状态执行；只建立当前迭代的模型状态，不保留跨迭代计算图 |
| `SensitivityAnalyzer.build_sensitivities()` | 唯一把计算图延伸到 FEA 的阶段：全局设计叶子 → 基座 Assembly → 逐工况 work condition 与因子分解 → `StaticResult.GC`/`jacobian` 梯度叶子 → 多工况目标 → 伴随求解 |
| `build_sensitivities()` 返回前 | 恢复库函数替换过的 `GC`/`jacobian` 引用、释放稀疏分解，只保留 detached 的 `DesignKey → Tensor` 局部梯度 |
| updater `closure()` | 只在参数空间求值：输入为 owner 的局部参数张量，输出为固定线性目标与局部约束；**不建立、不引用任何 FEA 计算图** |

因此任一时刻最多存在一张跨越 FEA 的计算图，其生命周期严格限制在
`build_sensitivities()` 调用内部；updater 的多次试探求值（L-BFGS 与回退线搜索）不会
持有求解结果，也不会延长该图的生命周期。

## 9.4 V3 目标与约束功能归属

V3 中的目标与约束按职责归入以下位置：

| V3 能力 | V4 归属 | 计算内容 |
|---|---|---|
| `ShapeDerivative` | 各 updater 的 `LocalSensitivityObjective`（几何 updater 在 `reinitialize()` 中建立） | 顶层灵敏度经 `DesignRegistry` 切分后在 updater 内建立固定线性展开；`ObjectiveFunction.compute_case_objective()` 只保留用户自定义全局物理目标的模板 |
| `VolumeMaximization` | `ObjectiveFunction` 模板 | 当前实体体积的负值或用户指定符号 |
| `DensityFieldMinimize` | `MaterialUpdater` 局部项 | SIMP 密度场线性正则项 |
| `Sensitivity` | `MaterialUpdater` 局部项 | 材料设计灵敏度线性展开 |
| `MinRadius`、`Cylinder`、`Distance`、`Fairness` | `BoundaryPartUpdater` / `OffsetShellPartUpdater` | 对应可更新几何实体的局部罚函数约束 |
| `MinValue`、`MaxValue`、`VolFrac` | `MaterialUpdater` | 密度下界、上界和体积分数约束 |

顶层目标定义全局物理目标和展示指标；每个 updater 使用 Controller 分发的局部灵敏度
建立固定线性目标，并在自己的 closure 中计算所属局部约束。
