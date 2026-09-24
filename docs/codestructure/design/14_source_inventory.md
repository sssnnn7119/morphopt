# 14. 源码清单

返回 [设计导览](../README.md)。本页按源码目录列出当前 Python 文件及其职责；类的属性和方法语义由对应模块页展开说明。

## 包根与运行入口

| 文件 | 主要公开对象 | 责任 |
|---|---|---|
| `__init__.py` | 顶层 `morphopt` API、`enable_logging` | 汇总稳定用户导入、包级日志和运行时全局 Controller 引用。 |
| `opt_runner.py` | `start_optimization`, `debug_optimization` | 正常/调试运行入口。 |
| `taskoptmization.py` | `TaskOptimization` | 子进程优化任务、动态脚本加载和重启执行。 |

## `optcore/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `protocal.py` | `ProtocalInitializable`, `ProtocalSavable`, `ProtocalVisualizable`, `ProtocalUpdatable` | 横切生命周期、持久化、可视化和设计变量协议。 |
| `controller.py` | `Controller` | 顶层优化生命周期、持久化、设备和进程池编排。 |
| `history.py` | `History` | 迭代历史记录、存取和属性视图。 |
| `solver.py` | `Solver` | 多载荷步 FEA 求解与 warm start。 |
| `objfunc.py` | `ObjectiveFunction` | 多步目标、自动微分灵敏度、结果可视化。 |
| `updaters.py` | `BaseUpdater`, `Updaters` | 局部设计子问题、梯度切片和设备作用域。 |

### `optcore/modelparams/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `baseparam.py` | `BaseParams` | 命名接口字典、批量协议转发、设计变量拼接。 |
| `params.py` | `Params` | Geometry、FEA、Materials 根组合与 FEA 建立。 |
| `geometry.py` | `GeometryParams` | Part 接口集合到 Assembly。 |
| `feaparams.py` | `FEAParams` | FEA 接口、载荷步和 FEAController 建立。 |
| `materials.py` | `MaterialsParams` | 材料接口集合与材料分配。 |

### `optcore/modelparams/partinterface/`

| 文件 | 主要类型/函数 | 责任 |
|---|---|---|
| `basepartinterface.py` | `BasePartInterface` | 一个 Part、多个 instance、位姿和 Assembly 添加。 |
| `inppartinterface.py` | `INPPartInterface` | 从 Abaqus `.inp` 导入固定 Part。 |
| `torchfeapartinterface.py` | `TorchFEAPartInterface`, `resolve_model_path`, `load_model_assembly` | 从 TorchFEA `.npz` 存档导入 Part/instances。 |
| `__init__.py` | Part API 导出 | 子包公共导入。 |

### `optcore/modelparams/materialinterface/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `basematerialinterface.py` | `BaseMaterialInterface` | Part/元素选择与材料接口公共状态。 |
| `homogeneousmaterial.py` | `HomogeneousMaterial` | 均质材料分配。 |
| `materialmodels.py` | `MaterialModels`、参数 dataclass | TorchFEA 本构模型的类型化参数。 |
| `__init__.py` | 材料 API 导出 | 子包公共导入。 |

### `optcore/modelparams/feainterface/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `basefeainterface.py` | `BaseFEAInterface` | 所有 FEA 声明的名称、数值覆盖与协议基类。 |
| `bodyforceinterface.py` | `BodyforceInterface` | 体力。 |
| `pressureinterface.py` | `PressureInterface` | 表面压力。 |
| `boundaryconditioninterface.py` | `BoundaryConditionInterface`, `BoundaryConditionRPInterface` | 节点/参考点自由度约束。 |
| `referencepointinterface.py` | `ReferencePointInterface` | 参考点。 |
| `pointinterface.py` | `ConcentratedForceInterface`, `ConcentratedMomentInterface` | 参考点集中力与力矩。 |
| `coupleinterface.py` | `CoupleInterface` | 节点集合到参考点的耦合。 |
| `contactinterface.py` | `ContactInterface`, `ContactSelfInterface` | 双面与自接触。 |
| `springinterface.py` | `SpringToGroundInterface`, `SpringBetweenRPsInterface`, `PenaltyDoFInterface` | 弹簧和自由度惩罚。 |
| `__init__.py` | FEA 接口 API 导出 | 子包公共导入。 |

## `shapeopt/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `__init__.py` | `BoundaryPartInterface`, `UpdaterBoundaryPart` | 形状扩展公开 API。 |
| `boundarypartinterface.py` | `BoundaryPartInterface` | 曲面边界、网格、Part 和形状设计变量。 |
| `meshgenerator.py` | `MeshGenerator` | 曲面文件到体网格/INP 的管线。 |
| `update_boundarypart.py` | `UpdaterBoundaryPart` | 一个边界 Part 的局部 L-BFGS 更新。 |

### `shapeopt/surfaceinterfaces/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `basesurfaceinterface.py` | `BaseSurfaceInterface`, `CpBasedSurfaceInterface`, `FixedSurface` | 曲面通用映射、控制点层和固定三角面。 |
| `bspsurfaceinterface.py` | `BspSurfaceInterface` | B-spline 曲面、STEP 与圆柱初始化。 |
| `cpgeosurfaceinterface.py` | `CPGEOSurfaceInterface` | CPGEO 曲面、STL、圆柱/球初始化。 |
| `__init__.py` | 曲面 API 导出 | 子包公共导入。 |

### `shapeopt/objectivefuncs/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `basefuncs.py` | `BaseObjective`, `BaseConstraints` | 形状局部目标/约束协议。 |
| `shapederivative.py` | `ShapeDerivative` | 形状梯度目标。 |
| `surfacefairness.py` | `Fairness` | 公平性约束。 |
| `distancesurface.py` | `Distance` | 曲面距离约束。 |
| `volumemaximization.py` | `VolumeMaximization` | 体积约束。 |
| `boundarys.py` | `MinRadius`, `Cylinder` | 边界半径与圆柱空间约束。 |
| `__init__.py` | 子包 API 导出 | 子包公共导入。 |

## `simp/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `__init__.py` | `SIMP_BSPFieldMaterials`, `UpdaterSIMPMaterial` | SIMP 扩展公开 API。 |
| `simpmaterial.py` | SIMP 材料/元素类型、`SIMP_BSPFieldMaterials` | B-spline 密度场到 SIMP 元素和材料。 |
| `update_simpmaterial.py` | `UpdaterSIMPMaterial` | 一个 SIMP 材料接口的局部 L-BFGS 更新。 |

### `simp/objectivefuncs/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `basefuncs.py` | `BaseObjective`, `BaseConstraints` | SIMP 局部目标/约束协议。 |
| `sensitivity.py` | `Sensitivity` | 灵敏度方向目标。 |
| `densityfield.py` | `DensityFieldMinimize` | 密度场最小化项。 |
| `volfrac.py` | `VolFrac` | 高斯点材料体积分数约束。 |
| `boundarys.py` | `MinValue`, `MaxValue` | 字段取值范围约束。 |
| `__init__.py` | 子包 API 导出 | 子包公共导入。 |

## `codesign/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `geometry.py` | `CodesignBoundaryPartInterface` | 偏置壳边界 Part。 |
| `geometryparams.py` | `GeometryParams` | 壳接口和厚度查询。 |
| `feaparams.py` | `CodesignFEAParams` | 壳相关 FEA 组装。 |
| `constraints.py` | `InwardCurvatureRadius`, `OffsetSurfaceMinThickness` | 协同设计形状约束。 |
| `params.py` | `Params` | 协同设计参数根类型。 |
| `__init__.py` | 子包入口 | 协同设计命名空间。 |

## `ui/`

| 目录/文件 | 责任 |
|---|---|
| `model/` | 类型化问题树、schema、`.morph`、TorchFEA 存档摘要。 |
| `application/` | 问题、结果和运行会话；编辑路由。 |
| `codegen/` | 问题树到 Python 的确定性生成。 |
| `schemes/` 与 `templates/` | 模板描述、代码片段和内置 `.morph/.npz` 资产。 |
| `widgets/` | 树、表单、专用编辑器、预览、结果页和运行对话框。 |
| `mainwindow.py` | `MainWindow`，应用页面编排。 |
| `workbench.py` | `Workbench`，优化定义编辑页。 |
| `observe_panel.py` | `ObserverPanel` 与运行控制。 |
| `i18n.py` | 翻译与 `LanguageSelector`。 |
| `app.py`、`launcher.py`、`__main__.py` | Qt 应用启动入口。 |

## `utils/`

| 文件 | 主要函数 | 责任 |
|---|---|---|
| `gradient_check.py` | `check_gradients` | 自动微分与中心差分灵敏度比较。 |
| `history_read.py` | `get_controller` | 从结果目录重建 Controller。 |
| `__init__.py` | 工具导出 | 顶层工具入口。 |
