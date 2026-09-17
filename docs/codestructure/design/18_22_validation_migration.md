# MorphOpt V4 校验、迁移与验收

> 文档属性：维护性迁移文档。本文件记录校验、验收和旧版迁移状态，不定义 V4 公共接口；接口以第 1–17 章主题设计文档为准。

本文件记录校验规则、模块迁移、测试验收、实施阶段和主题设计文档之间的接口关系。返回[总入口](../design.md)。

## 文档导航与输入/输出摘要

本文是维护性文档，负责把主题设计转换为校验规则、模块迁移任务、测试验收标准和实施顺序，
并记录 V3 功能到 V4 类与方法的落点。公共接口仍以第 1–17 章主题文档为准。

### 目录

- [18. 校验规则](#18-校验规则)
- [19. 模块结构和迁移范围](#19-模块结构和迁移范围)
- [20. 测试验收标准](#20-测试验收标准)
- [21. 实施顺序](#21-实施顺序)
- [22. 最终接口关系](#22-最终接口关系)
- [22.1 已确定的外部边界](#221-已确定的外部边界)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 第 1–17 章主题接口、V3 功能基线、模块路径、测试目标和迁移约束 |
| 输出 | 校验清单、目标目录、迁移映射、验收标准、实施阶段和已确定边界 |
| 主要读者 | V4 实施者、测试编写者、迁移 review 者和项目维护者 |
| 关联文档 | [架构总览](01_04_overview.md)、[功能基线](23_function_inventory.md)、[总入口](../design.md) |

## 18. 校验规则

### 18.1 Geometry

- `part_name` 长度大于零且唯一；
- `BoundaryPart` 的 `element_name` 长度大于零且由构造函数显式传入；
- `INPPart` 和 `TorchFEAPart` 按 `C3D4`、`C3D6`、`C3D8`、`C3D10`、`C3D15`、`C3D20` 排列源元素类型，未列入的类型按源顺序追加；`element_names` 省略时采用排序后的源元素类型名称，显式提供时长度必须等于源元素族数量，名称长度大于零且保持唯一；
- `OffsetShellPart` 的 `solid_element_name` 和 `shell_element_name` 均显式提供长度大于零的值，彼此不同，
  且由构造函数显式传入；
- `OffsetShellPart.source_surface` 是与边界曲面数量相同、每项均为 `bool` 的列表，第 `0` 项必须为 `False`，
  第 `1` 项及以后控制对应曲面的向内偏置；偏置集合名称遵循 `surface_{i}_offset`；
- `OffsetShellPart` 的 `solid_element_name` 指向体积网格产生的元素族（`C3D4`，`mesh_order == 2` 时为
  `C3D10`），`shell_element_name` 指向楔形单元族（`C3D6`/`C3D15`）；两族名称不同，且都存在于
  当前 `Part.elems`；
- 偏置楔形单元在每个相邻层之间生成，第 0 层复用源曲面节点，层间位移按
  `alpha = layer / num_layers` 分配总厚度；
- 任一批楔形单元的高斯权重最小值为负时初始化失败（抛出断言错误），用于阻止内外翻转的偏置网格
  进入求解；
- `mesh_order == 2` 时先建立体积网格与全部楔形带，再对两族一次调用
  `convert_linear_to_quadratic_elements()`，使 `mid_pt_idxmap_torch` 同时覆盖 `C3D10` 与
  `C3D15`；转换保留材料绑定，并自动把中点加入既有节点集合；
- `instance_name` 长度大于零且在整个 `Assembly` 中唯一；
- 每个 `Part` 至少有一个 `Instance`；
- `exterior_surface` 名称在目标 `Part` 中存在；同一 `Part` 的多个 `Instance` 声明相同名称；
- `translation` 和 `rotation` 都包含三个浮点分量；
- `ReferencePoint.name` 长度大于零且在 `Assembly` 中唯一；
- `ReferencePoint.position` 包含三个有限浮点分量；
- `Part` 构建后包含与其元素名称集合对应的有效元素和必要集合。

### 18.2 Materials

- 材料实现顺序与[材料系统](06_materials.md)一致：
  [`MaterialsParams`](06_materials.md#61-materialsparams) →
  [`MaterialModels`](06_materials.md#62-materialmodels) →
  [`BaseMaterialInterface`](06_materials.md#64-basematerialinterface) →
  [`HomogeneousMaterial`](06_materials.md#65-homogeneousmaterial) →
  [`SIMPFieldMaterial`](06_materials.md#66-simpfieldmaterial)。
- `material_name` 长度大于零且唯一；
- 每个 [`BaseMaterialInterface`](06_materials.md#64-basematerialinterface) 对象都携带
  `part_name` 和 `element_name`，且两者长度大于零；
- 材料刷新接收当前 `Assembly` 并解析目标 `Part`；
- `element_name` 精确存在于当前 `Assembly` 目标 `Part` 的 `elems`；
- 一个 `Part` 的每个可变形元素族恰好由一个材料对象覆盖；刚体和显式标记为
  `requires_material=False` 的辅助元素族由 Part 元数据声明豁免；
- 材料范围彼此独立；
- 均匀材料参数对象必填；
- SIMP 参数、控制点和元素映射维度一致；
- `define_materials()` 只建立材料定义，`add_material(interface, name)` 注册单个材料；
- `initialize()` 建立静态材料结构，`reinitialize(iteration, assembly)` 解析当前
  `Assembly` 的目标元素和映射。

### 18.3 FEA

- FEA component 顺序与[FEA 组件](07_fea.md)一致：
  [`FEAParams`](07_fea.md#71-feaparams) →
  [`BaseFEAComponent`](07_fea.md#72-basefeacomponent) →
  [`Pressure`](07_fea.md#73-pressure)、
  [`BodyForce`](07_fea.md#74-bodyforce)、
  [`ConcentratedForce`](07_fea.md#75-concentratedforce)、
  [`ConcentratedMoment`](07_fea.md#76-concentratedmoment)、
  [`BoundaryCondition`](07_fea.md#77-boundarycondition)、
  [`BoundaryConditionRP`](07_fea.md#78-boundaryconditionrp)、
  [`Couple`](07_fea.md#79-couple)、
  [`SpringToGround`](07_fea.md#710-springtoground)、
  [`SpringBetweenRPs`](07_fea.md#711-springbetweenrps)、
  [`PenaltyDoF`](07_fea.md#712-penaltydof)、
  [`Contact`](07_fea.md#713-contact)、
  [`SelfContact`](07_fea.md#714-selfcontact) →
  [`LoadStep`](07_fea.md#715-loadstep)。Solver 的定义与执行见 [08_solver.md](08_solver.md)。
- FEA component 名称唯一；
- `Instance`、surface、node set、element set 和几何层 RP 都存在；
- 每个 load step 包含全部 FEA component；
- 值向量长度等于 `num_values`；
- Jacobian 名称引用已注册 FEA component；
- 参数化 component 的每个工况建立一个唯一 `LoadValueBlock` 和带 `case_index` 的 `DesignKey`；
- 每个工况建立独立 Assembly 和 component 运行副本，任一工况更新保持其他工况值与运行对象不变；
- `task_groups` 完整覆盖 step，索引保持唯一并处于有效范围；
- `define_components()` / `define_steps()` 只建立定义阶段注册表；
  `add_component()` 和 `set_step_*()` 分别注册 component 与工况值；
- 每个 component 的 `reinitialize(iteration, assembly)` 都使用同一个当前
  `Assembly` 解析运行时目标。

### 18.4 `Updaters`

- 每个 `UpdaterEntry` 的 `target_kind` 和 `target_name` 都能解析到真实目标；
- 内置 updater 的目标类型与 `target_kind` 匹配；
- `boundary_part` 只接受 `BoundaryPartUpdater`，`offset_shell_part` 只接受
  `OffsetShellPartUpdater`；
- 同一个 `(target_kind, target_name, case_index)` 只能注册一个 updater；geometry/material
  目标的 `case_index` 为 None；
- `BoundaryPartUpdater` 与 `BoundaryPart` 类型匹配，`OffsetShellPartUpdater` 与
  `OffsetShellPart` 类型匹配；
- 两个不同 `BoundaryPart` 可以分别注册两个独立的 `BoundaryPartUpdater`，变量块、局部
  目标和优化器状态彼此隔离；
- 每个 updater 目标具有长度大于零的设计变量；
- `OffsetShellPart` 的设计变量长度与源边界曲面的元曲面控制点一致，
  `DesignRegistry` 只登记这组控制点变量；偏置节点、单元和偏置曲面由固定算法派生；
- 一个 `DesignKey` 只绑定一个 updater；
- updater 梯度长度等于 owner 变量长度；
- 所有已注册 updater 的变化成功后统一提交。

## 19. 模块结构和迁移范围

### 19.1 目标目录

~~~text
src/morphopt/
├── __init__.py
├── logging.py
├── task.py
├── _torch.py
├── optcore/
│   ├── __init__.py
│   ├── controller.py
│   ├── protocols.py
│   ├── design_registry.py
│   ├── objective.py
│   ├── sensitivity.py
│   ├── solver.py
│   ├── history.py
│   └── modelparams/
│       ├── __init__.py
│       ├── params.py
│       ├── geometry.py
│       ├── reference.py
│       ├── materials.py
│       ├── fea.py
│       ├── parts/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── boundary.py
│       │   ├── inp.py
│       │   ├── torchfea.py
│       │   ├── offset.py
│       │   ├── instance.py
│       │   └── mesh.py
│       ├── surfaces/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── cpbased.py
│       │   ├── preload.py
│       │   ├── bsp.py
│       │   ├── cpgeo.py
│       │   ├── stl.py
│       │   └── fairness.py
│       ├── material/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── models.py
│       │   ├── parameters.py
│       │   ├── homogeneous.py
│       │   ├── simp.py
│       │   ├── elements.py
│       │   └── interpolation.py
│       └── components/
│           ├── __init__.py
│           ├── base.py
│           ├── loads.py
│           ├── boundaries.py
│           ├── interactions.py
│           ├── springs.py
│           └── steps.py
│   ├── updaters/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── optimizers.py
│   │   ├── geometry.py
│   │   ├── material.py
│   │   ├── fea.py
│   │   └── terms.py
├── utils/
│   ├── __init__.py
│   ├── gradient_check.py
│   └── history_read.py
└── ui/
    ├── __init__.py
    ├── __main__.py
    ├── app.py
    ├── mainwindow.py
    ├── workbench.py
    ├── launcher.py
    ├── i18n.py
    ├── model/
    │   ├── __init__.py
    │   ├── problem.py
    │   ├── nodes.py
    │   ├── schemas.py
    │   └── loaders.py
    ├── schemes/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── shapeopt.py
    │   └── simp.py
    ├── codegen/
    │   ├── __init__.py
    │   ├── generator.py
    │   └── snippets.py
    └── widgets/
        ├── __init__.py
        ├── tree.py
        ├── editor.py
        ├── param_form.py
        ├── code_editor.py
        ├── completion.py
        ├── snippet_dialog.py
        ├── model_editor.py
        ├── step_matrix.py
        ├── objective_editor.py
        ├── solver_editor.py
        ├── updater_editor.py
        ├── viewer.py
        ├── console.py
        ├── observer.py
        ├── observation_pages.py
        └── values.py

tests/morphopt/
├── testInit.py
├── testLogging.py
├── testTask.py
├── optcore/
│   ├── testInit.py
│   ├── testController.py
│   ├── testProtocols.py
│   ├── testDesignRegistry.py
│   ├── testObjective.py
│   ├── testSensitivity.py
│   ├── testSolver.py
│   ├── testHistory.py
│   └── modelparams/
│       ├── testInit.py
│       ├── testParams.py
│       ├── testGeometry.py
│       ├── testMaterials.py
│       ├── testFea.py
│       ├── parts/
│       │   ├── testInit.py
│       │   ├── testBase.py
│       │   ├── testBoundary.py
│       │   ├── testInp.py
│       │   ├── testTorchfea.py
│       │   ├── testOffset.py
│       │   ├── testInstance.py
│       │   └── testMesh.py
│       ├── surfaces/
│       │   ├── testInit.py
│       │   ├── testBase.py
│       │   ├── testCpBased.py
│       │   ├── testPreload.py
│       │   ├── testBsp.py
│       │   ├── testCpgeo.py
│       │   ├── testStl.py
│       │   └── testFairness.py
│       ├── material/
│       │   ├── testInit.py
│       │   ├── testBase.py
│       │   ├── testModels.py
│       │   ├── testParameters.py
│       │   ├── testHomogeneous.py
│       │   ├── testSimp.py
│       │   ├── testElements.py
│       │   └── testInterpolation.py
│       └── components/
│           ├── testInit.py
│           ├── testBase.py
│           ├── testLoads.py
│           ├── testBoundaries.py
│           ├── testInteractions.py
│           ├── testSprings.py
│           └── testSteps.py
│   ├── updaters/
│   │   ├── testInit.py
│   │   ├── testBase.py
│   │   ├── testOptimizers.py
│   │   ├── testGeometry.py
│   │   ├── testMaterial.py
│   │   ├── testFea.py
│   │   └── testTerms.py
├── utils/
│   ├── testInit.py
│   ├── testGradientCheck.py
│   └── testHistoryRead.py
└── ui/
    ├── testInit.py
    ├── testMain.py
    ├── testApp.py
    ├── testMainwindow.py
    ├── testWorkbench.py
    ├── testLauncher.py
    ├── testI18n.py
    ├── model/
    │   ├── testInit.py
    │   ├── testProblem.py
    │   ├── testNodes.py
    │   ├── testSchemas.py
    │   └── testLoaders.py
    ├── schemes/
    │   ├── testInit.py
    │   ├── testBase.py
    │   ├── testShapeopt.py
    │   └── testSimp.py
    ├── codegen/
    │   ├── testInit.py
    │   ├── testGenerator.py
    │   └── testSnippets.py
    └── widgets/
        ├── testInit.py
        ├── testTree.py
        ├── testEditor.py
        ├── testParamForm.py
        ├── testCodeEditor.py
        ├── testCompletion.py
        ├── testSnippetDialog.py
        ├── testModelEditor.py
        ├── testStepMatrix.py
        ├── testObjectiveEditor.py
        ├── testSolverEditor.py
        ├── testUpdaterEditor.py
        ├── testViewer.py
        ├── testConsole.py
        ├── testObserver.py
        └── testObservationPages.py
~~~

每个 `src/morphopt/**/*.py` 都有路径对应的 `tests/morphopt/**/test<Name>.py`；上表完整展示
初始 V4 文件级映射。新增源文件时，同一提交在镜像目录增加对应测试文件。跨模块集成测试
放在 `tests/integration/`，测试数据放在 `tests/data/`；这两个目录补充文件级单元测试，
共同构成验收测试集。

### 19.2 旧能力迁移

| 旧位置 | 新位置 |
|---|---|
| shapeopt.geometryparams | partinterface.boundarypart + `GeometryParams` |
| shapeopt.update_geometry | `BoundaryPartUpdater`、`OffsetShellPartUpdater` |
| simp.simpmaterial | [`SIMPFieldMaterial`](06_materials.md#66-simpfieldmaterial) |
| simp.update_material | `MaterialUpdater` |
| codesign.geometry | `OffsetShellPart` |
| FEA 中的 INP 导入 | `INPPart` |
| 固定 TorchFEA `Assembly` | `TorchFEAPart` |
| `Params` 三大变量分块 | `DesignRegistry` |

迁移后使用新的 shapeopt/simp/codesign 聚合方式、材料接口和字段命名；V4 采用新的
类名和模块路径。

### 19.3 改写与删除文件

V4 不保留兼容入口，下列内容按新接口整体改写或删除，不提供旧文件读取：

| 内容 | 处理 |
|---|---|
| `examples/bendingactuator.py`、`examples/gripper.py` | 改写为 `define_parts()` / `define_materials()` / `define_components()` / `define_updaters()` 注册式任务 |
| `myjobs/` 中全部任务 | 同上；旧结果目录不复用 |
| `tests/` 中几何、材料、灵敏度、运行结果与 UI 测试 | 按 §19.1 的测试镜像重建，不保留旧路径 |
| UI model、schemas、codegen、`Part`/Material/FEA/Updater editor | 按第 16–17 章重写 |
| `docs/module_definition_guide.md`、`docs/module_reference.md`、`docs/UI_usage.md` | 按 V4 接口重写 |
| `docs/theory/morphdesign.md`、`docs/theory/codesign.md` | 更新公式与对象命名；codesign 不再作为独立子系统描述 |
| 仓库根 `scripts/` 目录 | 删除；能力并入 `TaskRunner`、`load_controller()`、`check_gradients()` 和 `History`，见[破坏性变更](24_breaking_changes.md) |
| 仓库根 `clearpyc.py` | 删除 |
| `docs/codestructure/ui_code_design.md` | 不属于 V4 文档体系，删除该引用 |
| `pyproject.toml` | 包目录改为 `src/morphopt`，保留 `morphopt-ui` 入口 |

公共 API 的移除项、行为变更、结果契约与冻结数值契约集中记录在
[第 24 章](24_breaking_changes.md)。

## 20. 测试验收标准

### 20.1 Geometry 和 `Assembly`

- `BoundaryPart` 生成有效 `Part` 和默认同名 `Instance`；
- 一个 `Part` 生成多个不同变换的 `Instance`；
- 多个 `Part` 进入同一个 `Assembly`；
- 多个 `Instance` 共享同一 `Part` 的设计变量；
- `INPPart` 缓存 INP 源 Assembly，并通过统一 Part 接口提取一个指定源 Part 及选定实例；
- `TorchFEAPart` 缓存 TorchFEA 源 Assembly，并通过统一 Part 接口提取一个指定源 Part 及选定实例；
- 同一模型的多个 Part 通过多个 `TorchFEAPart` 定义进入同一目标 Assembly，源模型读取缓存可共享；
- 源模型参考点摘要包含名称和三维全局坐标；选中的参考点转换为独立 Geometry
  `ReferencePoint` 定义，同名同坐标项复用，同名异坐标项校验失败；
- 导入 `Part` 的 `element_names` 与统一排序后的源元素族逐项对应；省略自定义名称时使用排序后的源元素类型名称；
- 每个 BSP 曲面自动生成 `surface_{i}_head`、`surface_{i}_bottom`、
  `surface_{i}_lateral` 和 `surface_{i}_all` 四个 surface set；
- 每个 CPGEO 曲面生成 `surface_{i}_all` 全部三角面集合；
- 整体外表面 surface set 的名称由 `Instance.exterior_surface` 指定（默认 `extern`），内容为
  该 `Part` 全部曲面的 `surface_0_all + surface_1_all + ...` 合集；用户自定义名称后，
  集合使用该名称注册，`Instance` 与 `Part` 名称不一致时校验失败；
- `BSPSurface.get_meshes()`、`CPGEOSurface.get_meshes()` 和 `STLSurface.get_meshes()` 分别返回
  本类已经建立的预览网格；`build_meshes()` 建立缓存并返回 `None`；
- `OffsetShellPart` 生成并更新偏置节点、元素和表面；二阶单元节点更新使用 TorchFEA
  `Part.mid_pt_idxmap_torch`；
- `OffsetShellPart` 仅对 `source_surface[i] is True` 且 `i >= 1` 的曲面生成向内偏置，
  并注册 `surface_{i}_offset` 集合；
- `get_assembly()` 读取最近一次 `build_assembly()` 保存的结果。
- BSP、CPGEO 和 STL 曲面分别执行 `build_meshes()` 并由各自的 `get_meshes()` 读取预览缓存；
  预览数据与几何值、积分权重和节点映射使用同一迭代状态。

### 20.2 Materials

- [`MaterialModels`](06_materials.md#62-materialmodels) 中的每个参数类创建正确的 TorchFEA 本构类；
- 缺少材料参数时立即报错；
- [`HomogeneousMaterial`](06_materials.md#65-homogeneousmaterial) 覆盖目标元素族；
- 每个材料对象只覆盖其声明的一个 `element_name` 元素族；
- 材料覆盖重叠或缺失时初始化失败；
- SIMP 控制点、材料场、材料比例和元素写回一致；
- `SIMPFieldMaterial.save()` 保存可恢复的控制点/BSP 状态和 density 直方图，加载后重新建立的
  材料比例、罚因子和预览标量与保存前一致；
- RAMP 与幂次插值保持 autograd；三种二阶位移罚项和 C3D4/C3D8/C3D10/C3D20
  适配器的能量、力、切线通过有限差分与 V3 基准验证；
- SIMP 专属方法只出现在 [`SIMPFieldMaterial`](06_materials.md#66-simpfieldmaterial)；
- 材料对象保留 `part_name`、`element_name`，并在
  `reinitialize(iteration, assembly)` 中解析目标元素；
- `BaseMaterialInterface` 建立并持有 `_torchfea_<MaterialClass>`，`assign_material()` 和
  `update_assembly(design_delta)` 使用自身缓存的目标元素与 Assembly；
- `MaterialsParams` 通过 `define_materials()` 和 `add_material(interface, name)` 完成注册。

### 20.3 FEA、`Solver` 和 Objective

- FEA component 的目标名称解析正确；
- 每个 FEA component 的 `build_fea()` 一次性创建并保存对应的
  `_torchfea_<ConcreteName>`，`update_fea()` 更新工况值；
- 多工况结果按 `step_index` 返回；
- Controller 为全部工况创建共享 `FEAController`，其 `assembly` 来自 `FEAParams`，其
  `solver` 来自 `Solver.build_solvers()`；
- CPU/GPU 结果结构一致；
- 收敛状态取自库结果 `converged`；morphopt 在结果上附加的 `step_index` 与工况索引一致；
- `ObjectiveFunction` 返回标量目标；
- `build_evaluation()` 建立逐工况目标、总目标和指标，所有 `get_*()` 只读取缓存；
- `metrics` 作为展示量，与设计变量梯度计算分离；
- Jacobian 引用错误时初始化失败。
- `SensitivityAnalyzer` 在顺序与 spawn 求解结果上建立一致的隐式总灵敏度；
- 几何、材料和逐工况 load 变量的伴随梯度分别通过中心差分校验；
- 跨工况目标的总梯度包含各工况位移项、显式设计项和 Jacobian 响应项；
- 同一 component 在不同工况的 `LoadValueBlock` 梯度只写入各自 `DesignKey`；
- 刚度模板使用参考点 `_GC_list_indexStart` 的 6 个广义自由度，并拒绝 force、moment、
  reference point 目标不一致的组合；
- Solver 的顺序/debug 与 spawn 多进程路径返回相同工况顺序和结果 schema；
- 同一任务组的后一工况复用前一工况收敛 `GC`，自由度维度变化时使用该工况自身初值；
- 几何变量为空时复用上轮 GC，存在几何变量时采用默认初值，显式设置覆盖自动策略。

### 20.4 `DesignRegistry` 和 Updater

- geometry、material 和联合变量 `offsets` 正确；
- 注册调用顺序变化时，完整变量顺序仍按 geometry → material → load 固定；
- 每个类别内部按目标名称字典序排列，同类别内的名称顺序保持稳定；
- `get_design_delta()` 和 `compute_block_values()` 使用同一排序结果；
- trial design delta 通过 `DesignRegistry.update_assembly()` 和不带 `Assembly` 参数的
  `update_assembly(design_delta)` 回写到正确的 `Part`、材料接口或 FEA component；
- updater 梯度按变量块独立传递；
- 每个可更新 owner 绑定一个 updater，每个变量块只属于该 updater；
- 全部 updater 成功后统一提交变化；
- 未绑定 updater 的 `owner` 保持固定并参与 FEA。
- L-BFGS 二循环、Armijo 回退、closure 求值上限、正曲率历史筛选和各终止原因均有单元测试；
- 几何与材料逐变量步长按相邻变化方向增长/衰减，并保持上下界；
- 任一 owner 提交失败时，所有 owner 参数和当前 Assembly 恢复至提交前快照；
- Boundary 和 Offset updater 的等式投影返回同形 Tensor，且镜面对称模板保留 autograd。

### 20.5 UI 和运行结果

- UI 创建 `BoundaryPart`、`INPPart`、`TorchFEAPart` 和 `OffsetShellPart` 对应的定义节点；
- 一个 `Part` 创建多个 `Instance`；
- 材料元素选择来自真实 `Part.elems`；
- UI 材料节点同时记录 `part_name` 和 `element_name`，生成代码时传入材料对象构造函数；
- UI 支持为不同目标添加任意数量的 updater；同类 updater 可以同时存在，但一个目标实体只保留一个；
- Python 源码能够重建类型、属性、名称、代码槽和初始 Tensor 状态；源码生成使用
  `generate_source()` 直接返回文本；
- 构造阶段仅记录定义；INP 读取、`Assembly`、UI 和 worker pool 在初始化/运行阶段建立；
- `initialize()` 后所有源数据、运行时缓存、FEA 对象和 updater 绑定完整可用；
- 每次运行从任务文件建立一致的初始设计变量、材料场和 updater 状态；
- 生成脚本可以独立 headless 运行。
- 主窗口只包含一个工作台入口，定义、运行输出和结果观察在工作台模式内切换；
- 动态补全覆盖全部 `fe_results[case_index]`、Tensor 方法、实例、参考点和集合名称；
- 代码片段在当前/最近光标插入，参数弹窗生成节点位移、参与力、完整高斯点张量、末端六向
  平移/转动、参考点刚度和镜面对称投影代码；
- 控制台增量处理 ANSI 颜色、光标移动、清行和回车覆盖，原始日志与可读显示同时保留；
- TorchFEA 模型摘要以树/表展示，选择集合时三维视图高亮，预览与变形图共享 Viewer 风格；
- i18n 覆盖所有用户可见标签、帮助、校验和状态文本，生成 Python 标识符保持英文。

### 20.6 状态恢复和后处理

- `Persistable.save()` 为每个 iteration 写入对应对象负责的状态和结果；
- 每个工况导出 `model.npz`、`result.npz`、`jacobian.npz`、`deformation.stl`、
  `preview.png` 和 `manifest.json`，模型哈希与结果哈希一致；
- 任务文件初始化完成后，`Persistable.load()` 能恢复设计变量、optimizer memory 和历史指标；
- `Controller.restart_optimization()` 按任务文件、`initialize()`、状态加载的顺序继续优化；
- 标准任务达到 `worker_restart_interval` 后写入完整 checkpoint 并以受控状态退出，
  `TaskRunner` 回收子进程并从同一结果目录续跑；求解失败以失败状态结束；
- 后处理直接读取 `History` 和结果文件，优化器由 Controller 与 Updaters 管理；
- 用户自定义曲面、约束和目标方法仍由任务 Python 文件提供。

### 20.7 运行时、持久化与新能力

- 结构化事件覆盖全部 7 种类型，载荷字段与[运行时](13_14_runtime.md)定义一致，`schema_version`
  校验失败的事件被拒绝并记录；
- 任一工况在迭代上限内未收敛时任务以失败状态结束，不产生部分结果，也不写入灵敏度；
- 设备边界保持独立：`Solver.device_names` 只配置 FEA 求解设备，空元组时由 Solver 使用
  CPU；`Controller.device` 只配置控制器编排设备，`Controller.updater_device` 只配置
  Updater 局部优化设备；`Controller.change_device()` 不改变 Solver 或 Updater；
- checkpoint 完整性按"manifest 最后写入"判定：写 checkpoint 中途终止时该次 checkpoint
  不存在，恢复回退到最近一个完整 checkpoint；
- `checkpoint_interval > 1` 时恢复从最近完整 checkpoint 的下一 iteration 继续，且不重复
  求解已完成迭代；
- 子进程被 SIGKILL 或 OOM 终止时不自动续跑，任务结束并保留已有完整 checkpoint；
- `restart_requested` 事件触发 `TaskRunner` 在同一结果目录续跑；正常完成、停止或失败事件不触发续跑；
- `load()` 在 `schema_version`、任务签名或设计变量签名不一致时抛出装载错误，不静默续跑；
- UI 进程不 import 任何运行时执行模块；预览在隔离进程中完成，失败或超时不影响主界面；
- 控制台正确增量处理 ANSI 颜色、光标移动、清行和回车覆盖，原始日志写入
  `log/morphopt.log` 且与显示文本一致；
- `check_gradients()` 返回结构化报告，相同抽样与种子产生稳定结果，可作为 CI 门禁；
- `load_controller()` 只接受完整 checkpoint，并在任务签名一致时重建运行时对象；
- 生成的任务文件冒烟测试：`shapeopt`/`simp` 两个内置 scheme 生成源码后 import、构造
  `Params` 并调用 `initialize()` 成功，作为 UI schema 与运行时 API 的一致性门禁；
- [冻结数值契约](24_breaking_changes.md)中的每一项至少有一条默认值断言测试。

## 21. 实施顺序

### 阶段 0：契约冻结与骨架

确认第 1–17 章接口与[第 24 章](24_breaking_changes.md)的移除清单、冻结数值契约一致；
建立 `src/morphopt` 与 `tests/morphopt` 的镜像骨架，以及跨章一致性检查脚本（类名、
方法名、文件名在主题章、§18–23 与 §24 中的引用一致）。

### 阶段 1：`Part` 和 `Assembly`

建立 partinterface 和 feacomponent，实现 `BasePartDefinition`、`InstanceDefinition`、`BoundaryPart`、
`INPPart`、`TorchFEAPart` 和 `OffsetShellPart`，重写 `GeometryParams`。

### 阶段 2：材料系统

按[材料系统](06_materials.md)顺序重写 [`MaterialsParams`](06_materials.md#61-materialsparams)、
[`MaterialModels`](06_materials.md#62-materialmodels)、
[`MaterialParameters`](06_materials.md#63-materialparameters)、
[`BaseMaterialInterface`](06_materials.md#64-basematerialinterface)、
[`HomogeneousMaterial`](06_materials.md#65-homogeneousmaterial) 和
[`SIMPFieldMaterial`](06_materials.md#66-simpfieldmaterial)，完成 `Part`/Elems 覆盖校验。

### 阶段 3：FEA 和 `Params`

按[FEA 组件](07_fea.md)顺序统一 `BaseFEAComponent`、具体 FEA component、
`FEAParams`、`LoadStep`、`LoadValueBlock`、`FEAParams.build_components()` 和 FEA 名称校验；按[几何系统](05_geometry.md)
顺序实现 `ReferencePoint` 注册与 Assembly 构建，使用 `FEAParams.assign_components()`
完成 FEA component 写入，再由 `Controller` 将 Assembly 交给 Solver。

### 阶段 4：`DesignRegistry` 和 Updater

实现变量注册、切分和试探回写，将几何、材料和 FEA updater 统一为单 owner 绑定，
并将几何更新细分为 `BoundaryPartUpdater` 与 `OffsetShellPartUpdater`，接通
`SensitivityAnalyzer` 的隐式总灵敏度。

### 阶段 5：`Controller`、`Solver` 与联合优化

按本文生命周期接通主循环、运行结果记录和联合优化，用 `OffsetShellPart`、
`OffsetShellPartUpdater` 和 `MaterialUpdater` 的对象组合表达偏置壳问题。

### 阶段 6：UI 和 Codegen

重写 UI 数据树和 schema，再改编辑器、模型树、预览和 Python 任务源码生成。
三种模板只生成统一对象组合。

### 阶段 7：全量迁移和清理

迁移 examples、myjobs、tests 和全部文档，删除旧聚合层和旧字段，运行编译、
单元、FEA、梯度、UI 和代表性优化测试。

## 22. 最终接口关系

最终用户需要表达四类关系：

~~~text
GeometryParams.define_parts() → add_part(part)
MaterialsParams.define_materials() → add_material(interface, material_name)
FEAParams.define_components() → add_component(component, fea_component_name)
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

BoundaryPartUpdater body_shape
    target = BoundaryPart body

OffsetShellPartUpdater shell_shape
    target = OffsetShellPart shell

MaterialUpdater body_density
    target = Material body_solid
~~~

几何、材料、载荷和更新策略通过名称组合成一个 FEA/优化问题。shapeopt、simp
和 codesign 的差别只在于注册的对象组合。

## 22.1 已确定的外部边界

1. `TorchFEAPart` 接收输出 `part_name`、模型目录、文件名、一个源 Part 名称和可选实例列表，
   缓存源 Assembly，并把该源 Part 及其实例提取到统一几何装配流程。
2. 每个可变形元素族由一个材料对象覆盖；刚体或辅助元素族通过
   `requires_material=False` 元数据进入显式豁免清单。
3. TorchFEA 模型导入保留 Part、Instance、Surface、NodeSet、ElementSet 和 ElementType，
   并清理载荷、边界、接触、求解器和历史结果；这些分析定义由 MorphOpt FEA 层重新建立。
4. STP 导入和 CAD 建模由 torchfea-ui 完成。MorphOpt UI 启动 torchfea-ui 时监控用户选择的
   导出目录，刷新模型文件清单，并将导出模型建立为 `TorchFEAPart` 链接。
5. `morphopt3` 只作为功能基线读取；V4 实现、测试和打包路径统一使用 `src/morphopt`。
