# 14. 源码清单

返回 [设计导览](../README.md)。本页按源码目录列出当前 Python 文件及其职责；类的属性和方法语义由对应模块页展开说明。

<a id="section-包根与运行入口"></a>

## 1 包根与运行入口

| 文件 | 主要公开对象 | 责任 |
|---|---|---|
| `__init__.py` | 顶层 `morphopt` API、`enable_logging` | 汇总稳定用户导入、包级日志和运行时全局 Controller 引用。 |
| `opt_runner.py` | `start_optimization`, `debug_optimization` | 正常/调试运行入口。 |
| `taskoptmization.py` | `TaskOptimization` | 子进程优化任务、动态脚本加载和重启执行。 |

<a id="section-optcore"></a>

## 2 `optcore/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `protocal.py` | `ProtocalInitializable`, `ProtocalSavable`, `ProtocalVisualizable`, `ProtocalUpdatable` | 横切生命周期、持久化、可视化和设计变量协议。 |
| `controller.py` | `Controller` | 顶层优化生命周期、持久化、设备和进程池编排。 |
| `history.py` | `History` | 迭代历史记录、存取和属性视图。 |
| `solver.py` | `Solver` | 多载荷步 FEA 求解与 warm start。 |
| `objfunc.py` | `ObjectiveFunction` | 多步目标、自动微分灵敏度、结果可视化。 |
| `updaters.py` | `BaseUpdater`, `Updaters` | 局部设计子问题、梯度切片和设备作用域。 |
| `quadrature.py` | `actuation_boundary_gauss_points` | 驱动参数域边界上的二维边和三维面高斯求积。 |

<a id="section-optcoremodelparams"></a>

### 2.1 `optcore/modelparams/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `baseparam.py` | `BaseParams` | 命名组件字典、批量协议转发、设计变量拼接。 |
| `base_model_component.py` | `BaseModelComponent` | 单个几何、FEA、材料和曲面定义共享的初始化、持久化与可视化协议。 |
| `params.py` | `Params` | Geometry、FEA、Materials 根组合与 FEA 建立。 |
| `geometry.py` | `GeometryParams` | Part 接口集合到 Assembly。 |
| `feaparams.py` | `FEAParams` | FEA 接口、载荷步和 FEAController 建立。 |
| `materialsparams.py` | `MaterialsParams` | 材料接口集合与材料分配。 |

<a id="section-optcoremodelparamsparts"></a>

### 2.2 `optcore/modelparams/parts/`

| 文件 | 主要类型/函数 | 责任 |
|---|---|---|
| `base_part.py` | `BasePart` | 一个 Part、多个 instance、位姿和 Assembly 添加。 |
| `box_part.py` | `BoxPart` | 结构化长方体网格及坐标面节点/表面集合。 |
| `cad_part.py` | `CADPart` | 调用 TorchFEA CAD 操作历史生成 Part 和网格。 |
| `inp_part.py` | `INPPart` | 从 Abaqus `.inp` 导入固定 Part。 |
| `__init__.py` | Part API 导出 | 子包公共导入。 |

<a id="section-optcoremodelparamsmaterials"></a>

### 2.3 `optcore/modelparams/materials/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `base_material.py` | `BaseMaterial` | Part/元素选择与材料接口公共状态。 |
| `homogeneous_material.py` | `HomogeneousMaterial` | 均质材料分配。 |
| `models.py` | `MaterialModels`、参数 dataclass | TorchFEA 本构模型的类型化参数。 |
| `__init__.py` | 材料 API 导出 | 子包公共导入。 |

<a id="section-optcoremodelparamsfea"></a>

### 2.4 `optcore/modelparams/fea/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `base_component.py` | `BaseFEAComponent` | 所有 FEA 声明的名称、数值覆盖与协议基类。 |
| `body_force.py` | `BodyForce` | 体力。 |
| `pressure.py` | `Pressure` | 表面压力。 |
| `boundary_condition.py` | `BoundaryCondition`, `ReferencePointBoundaryCondition` | 节点/参考点自由度约束。 |
| `reference_point.py` | `ReferencePoint` | 参考点。 |
| `point_load.py` | `ConcentratedForce`, `ConcentratedMoment` | 参考点集中力与力矩。 |
| `couple.py` | `Couple` | 节点集合到参考点的耦合。 |
| `contact.py` | `Contact`, `SelfContact` | 双面与自接触。 |
| `spring.py` | `SpringToGround`, `SpringBetweenRPs`, `PenaltyDoF` | 弹簧和自由度惩罚。 |
| `__init__.py` | FEA 接口 API 导出 | 子包公共导入。 |

<a id="section-shapeopt"></a>

## 3 `shapeopt/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `__init__.py` | `BoundaryPart`, `UpdaterBoundaryPart` | 形状扩展公开 API。 |
| `boundary_part.py` | `BoundaryPart` | 曲面边界、网格、Part 和形状设计变量。 |
| `meshgenerator.py` | `MeshGenerator` | 曲面文件到体网格/INP 的管线。 |
| `update_boundary_part.py` | `UpdaterBoundaryPart` | 一个边界 Part 的局部 L-BFGS 更新。 |

<a id="section-shapeoptsurfaces"></a>

### 3.1 `shapeopt/surfaces/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `base_surface.py` | `BaseSurface`, `ControlPointSurface`, `FixedSurface` | 曲面通用映射、控制点层和固定三角面。 |
| `bsp_surface.py` | `BspSurface` | B-spline 曲面、STEP 与圆柱初始化。 |
| `cpgeo_surface.py` | `CPGEOSurface` | CPGEO 曲面、STL、圆柱/球初始化。 |
| `__init__.py` | 曲面 API 导出 | 子包公共导入。 |

<a id="section-shapeoptobjectivefuncs"></a>

### 3.2 `shapeopt/objectivefuncs/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `basefuncs.py` | `BaseObjective`, `BaseConstraints` | 形状局部目标/约束协议。 |
| `shapederivative.py` | `ShapeDerivative` | 形状梯度目标。 |
| `surfacefairness.py` | `Fairness` | 公平性约束。 |
| `distancesurface.py` | `Distance` | 曲面距离约束。 |
| `volumemaximization.py` | `VolumeMaximization` | 体积约束。 |
| `boundarys.py` | `MinRadius`, `Cylinder` | 边界半径与圆柱空间约束。 |
| `__init__.py` | 子包 API 导出 | 子包公共导入。 |

<a id="section-simp"></a>

## 4 `simp/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `__init__.py` | `SIMP_BSPFieldMaterials`, `UpdaterSIMPMaterial` | SIMP 扩展公开 API。 |
| `simpmaterial.py` | SIMP 材料/元素类型、`SIMP_BSPFieldMaterials` | B-spline 密度场到 SIMP 元素和材料。 |
| `update_simpmaterial.py` | `UpdaterSIMPMaterial` | 一个 SIMP 材料接口的局部 L-BFGS 更新。 |

<a id="section-simpobjectivefuncs"></a>

### 4.1 `simp/objectivefuncs/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `basefuncs.py` | `BaseObjective`, `BaseConstraints` | SIMP 局部目标/约束协议。 |
| `sensitivity.py` | `Sensitivity` | 灵敏度方向目标。 |
| `densityfield.py` | `DensityFieldMinimize` | 密度场最小化项。 |
| `volfrac.py` | `VolFrac` | 高斯点材料体积分数约束。 |
| `boundarys.py` | `MinValue`, `MaxValue` | 字段取值范围约束。 |
| `__init__.py` | 子包 API 导出 | 子包公共导入。 |

<a id="section-codesign"></a>

## 5 `codesign/`

| 文件 | 主要类型 | 责任 |
|---|---|---|
| `offset_boundary_part.py` | `OffsetBoundaryPart` | 内腔偏置层构建、网格检查及可微节点更新。 |
| `update_offset_boundary_part.py` | `UpdaterOffsetBoundaryPart` | 复用形状更新流程，仅绑定偏置 Part。 |
| `constraints.py` | `InwardCurvatureRadius`, `OffsetSurfaceMinThickness` | 偏置层的曲率和间距约束。 |
| `__init__.py` | 子包入口 | 只导出偏置专用组件。 |

<a id="section-ui"></a>

## 6 `ui/`

| 目录/文件 | 责任 |
|---|---|
| `model/` | 类型化问题树、schema、`.morph`、TorchFEA 存档摘要。 |
| `model/chamberlayout.py` | `ChamberLayer`, `CavitySpec`, `LayeredChambers` | Quickstart 专用气腔层排布、配置校验和初始预览。 |
| `model/base_nodes.py`、`model/node_types/`、`model/registry.py` | 通用节点家族、具体持久化节点及其显式注册。 |
| `model/problem.py` | 问题聚合的跨节点规则与编辑操作。 |
| `application/` | 问题、编辑、字段/集合查询、结果和运行用例。 |
| `presentation/` | 无 Qt 的导航、标题与结果表格投影。 |
| `visualization/` | Part/Surface/载荷 visitor 与场景数据。 |
| `codegen/` | 问题树到 Python 的确定性生成。 |
| `schemes/` | Python 定义的方案策略与代码片段。 |
| `widgets/` | 树、表单、专用编辑器、预览、结果页和运行对话框。 |
| `mainwindow.py` | `MainWindow`，应用页面编排。 |
| `workbench.py` | `Workbench`，优化定义编辑页。 |
| `observe_panel.py` | `ObserverPanel` 与运行控制。 |
| `i18n.py`、`locales/` | 无 Qt 的 key 查询、本地化订阅与语言资源。 |
| `widgets/definition_actions.py`、`editor_pages.py` | 共用操作；编辑页生命周期与信号注册。 |
| `widgets/param_form.py`、`editor.py` | 共用字段渲染器与节点页组合。 |
| `widgets/updater_editor.py` | 统一目标/罚函数/对称约束卡片管理器。 |
| `application/cad.py` | CAD 节点到 TorchFEA 操作的转换、BREP 预览与 STEP 几何导出。 |
| `widgets/file_dialogs.py` | 保存窗口、文件类型筛选与覆盖确认；由 STEP 和结果导出共用。 |
| `application/editing.py`、`updaters.py` | 节点、工况、任务、自定义类和优化器有序项的编辑规则。 |
| `application/runs.py`、`results.py` | 运行来源、进度与输出；结果参数、History 和网格读取。 |
| `widgets/preview_renderer.py`、`viewer.py` | 场景渲染与视口控件。 |
| `widgets/language_selector.py` | 语言选择器与 Qt 设置存储。 |
| `app.py`、`launcher.py`、`__main__.py` | Qt 应用启动入口。 |

<a id="section-utils"></a>

## 7 `utils/`

| 文件 | 主要函数 | 责任 |
|---|---|---|
| `gradient_check.py` | `check_gradients` | 自动微分与中心差分灵敏度比较。 |
| `history_read.py` | `get_controller` | 从结果目录重建 Controller。 |
| `__init__.py` | 工具导出 | 顶层工具入口。 |
