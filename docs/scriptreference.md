# MorphOpt 脚本模块与接口参考

[脚本快速开始](scriptguide.md) · [UI 快速开始](UIguide.md) · [UI 模块与接口参考](UIreference.md)

本文按控制器、模型参数、几何、载荷工况、材料、目标函数、求解器和更新器说明脚本定义。各节包括模块职责、注册位置、主要接口、输入约定和扩展示例。完整可执行任务见 [bending_optimization.py](examples/bending_optimization.py)；本文中的局部代码用于替换或扩展该任务内的对应模块。

脚本与 UI 采用同一计算内核。UI 字段、模型树与预览的对应关系见 [UI 模块参考](UIreference.md)，具体类与参数以当前源码为准。

## 目录

<!-- docs:toc depth=2 -->

- [1 模块组织与执行阶段](#section-总体结构)
    - [1.1 任务类与对象关系](#section-任务类与对象关系)
    - [1.2 构造、初始化与每轮重初始化](#section-构造与初始化约定)
    - [1.3 名称、参数与单位约定](#section-名称参数与单位约定)
- [2 Controller 与启动入口](#controller)
    - [2.1 控制器定义](#section-控制器定义)
    - [2.2 启动与继续计算](#section-启动与继续计算)
- [3 Params 参数聚合](#section-params-定义)
- [4 GeometryParams：部件、曲面与实例](#geometry)
    - [4.1 部件注册与命名](#section-部件注册与命名)
    - [4.2 BoundaryPart 与边界曲面](#section-geometryparams-定义要点一个-part-接口)
    - [4.3 Instance 位姿与集合引用](#section-instance-位姿与集合引用)
    - [4.4 CAD 历史与 STEP 导出](#section-cad-历史与-step-导出)
    - [4.5 INP、Box 与自定义 Part](#section-inpbox-与自定义-part)
- [5 FEAParams：载荷、边界、连接与工况](#section-feaparams-定义要点)
    - [5.1 接口定义与工况幅值](#section-接口定义与工况幅值)
    - [5.2 十三类接口与参数顺序](#section-十三类接口与参数顺序)
    - [5.3 参考点、耦合与固定条件](#section-参考点耦合与固定条件)
    - [5.4 接触与弹簧](#section-接触与弹簧)
- [6 MaterialsParams：本构与材料设计场](#section-materialsparams-定义要点)
    - [6.1 均质材料分配](#section-均质材料分配)
    - [6.2 八种本构参数类型](#section-八种本构参数类型)
    - [6.3 SIMP 密度场材料](#section-simp-密度场材料)
- [7 ObjectiveFunction：损失与监测指标](#section-objectivefunction-定义)
    - [7.1 标量损失与优化方向](#section-标量损失与优化方向)
    - [7.2 按名称提取参考点响应](#section-按名称提取参考点响应)
    - [7.3 载荷雅可比](#section-载荷雅可比)
- [8 Solver：工况求解与计算资源](#section-solver-定义)
    - [8.1 CPU 与单进程配置](#section-cpu-与单进程配置)
    - [8.2 多工况调度与 GPU](#section-多工况调度与-gpu)
    - [8.3 初始解与几何变化](#section-初始解与几何变化)
- [9 Updaters：设计变量更新](#section-updater-定义)
    - [9.1 注册方法与目标绑定](#section-注册方法与目标绑定)
    - [9.2 几何更新器](#section-几何更新器)
    - [9.3 材料更新器](#section-材料更新器)
    - [9.4 自定义更新器类](#section-自定义更新器类)
- [10 Codesign：形状与材料协同更新](#section-codesign-模块定义)
- [11 自定义类与 UI 的对应关系](#custom-classes)
- [12 迭代、保存与继续计算](#section-迭代与重启机制)
- [13 输出归档与问题诊断](#section-输出与问题诊断)
    - [13.1 主要输出](#section-主要输出)
    - [13.2 配置诊断](#section-配置诊断)
- [14 源码与示例索引](#section-参考实现)

<!-- /docs:toc -->

<a id="section-总体结构"></a>

## 1 模块组织与执行阶段

<a id="section-任务类与对象关系"></a>

### 1.1 任务类与对象关系

任务文件以模块级 `ThisController` 类组织定义，运行器从该类创建控制器。控制器通过四个嵌套类创建运行对象：

| 定义类 | 控制器中的运行对象 | 职责 |
|---|---|---|
| `ThisController.Params` | `controller.params` | 几何、载荷、工况与材料定义 |
| `ThisController.ObjectiveFunction` | `controller.objfun` | 标量损失、监测指标与灵敏度计算 |
| `ThisController.Solver` | `controller.solver` | 多工况有限元求解与任务调度 |
| `ThisController.Updater` | `controller.updater` | 各设计对象的更新器集合 |

`Params` 又包含 `GeometryParams`、`FEAParams` 和 `MaterialsParams`。三类集合通过 `add_interface(interface, name=...)` 注册对象；几何与材料的注册名称同时参与更新器的目标解析。

![部件、实例、材料与载荷之间的引用关系](images/ui-reference/diagrams/object-references.svg)

材料分配至 Part 的单元块，载荷作用于 Instance 的节点集、表面集或参考点，工况指定各载荷接口的幅值。几何更新器绑定 Part 接口，材料更新器绑定材料接口。

<a id="section-构造与初始化约定"></a>

### 1.2 构造、初始化与每轮重初始化

| 阶段 | 主要方法 | 处理内容 |
|---|---|---|
| 构造 | `__init__()` | 保存配置、名称与数值，建立空集合 |
| 注册 | `define_interface()` | 注册 Part、FEA 或材料接口 |
| 几何声明 | `define_instance()`、`define_surfaces()`、`define_operations()` | 声明实例、边界曲面或 CAD 操作 |
| 工况声明 | `define_steps()` | 建立工况列表并填写幅值 |
| 更新器声明 | `define_updater()`、`define_objective()` | 注册子优化器及其目标项、约束项 |
| 初始化 | `initialize()` | 执行声明方法、解析更新目标、准备运行对象 |
| 每轮准备 | `reinitialize(iteration=...)` | 更新迭代状态与当前设计数据 |
| 模型构建 | `build_part()`、`create_feamodel()` | 生成网格与装配体，设置载荷和材料 |

集合构造完成时，其 `interfaces` 通常为空。单独访问已注册接口、读取曲面列表或加载保存状态前，应先执行相应集合的 `initialize()`。完整任务由控制器统一执行初始化，不在任务入口重复调用各声明方法。

`define_objective()` 在子优化器注册时执行；目标绑定发生在之后的初始化阶段。因此，构造函数和 `define_objective()` 声明配置时不读取尚未绑定的 `self.part` 或 `self.material`。自定义运行时准备放在 `initialize()` 中，并调用父类实现。

<a id="section-名称参数与单位约定"></a>

### 1.3 名称、参数与单位约定

- 通用任务模块继承顶层 `morphopt.Controller`、`Params`、`ObjectiveFunction`、`Solver` 和 `Updaters`。`shapeopt`、`simp` 与 `codesign` 提供具体的设计对象、目标项和更新器。
- 接口名称区分大小写。同一集合中的注册名称不得重复，显式名称有利于维护载荷、材料和更新器之间的引用。
- 几何接口注册名、装配体 Part 名、Instance 名和材料接口名具有不同含义。常规任务保持几何接口注册名与 Part 名一致；Instance 名单独声明。
- 工况、曲面和自由度索引从 `0` 开始。位姿采用 `[tx, ty, tz, rx, ry, rz]`，后三项为旋转向量，单位为 rad。
- 长度、力、应力和密度采用一致单位制。结果目录与相对输入路径按任务脚本所在目录解析。

<a id="controller"></a>

## 2 Controller 与启动入口

<a id="section-控制器定义"></a>

### 2.1 控制器定义

```python
class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(
            path_result_folder="./results/",
            opt_label="BendingExample",
        )
```

控制器中的 `Params`、`Solver`、`Updater` 和 `ObjectiveFunction` 嵌套类在同一 `ThisController` 内定义，完整结构见[快速开始任务](examples/bending_optimization.py)。

| 参数或属性 | 含义 |
|---|---|
| `path_result_folder` | 新运行的结果根目录 |
| `opt_label` | 任务标签，用于生成 `<任务名称>_T<时间戳>` 目录名 |
| `path_result` | 当前具体运行目录，启动后由框架设置 |
| `history` | 迭代损失、指标、耗时与网格统计 |
| `optdevice` | 控制器侧的计算设备，由运行入口设置 |

<a id="section-启动与继续计算"></a>

### 2.2 启动与继续计算

```python
if __name__ == "__main__":
    morphopt.start_optimization(device="cpu", restart_per_iteration=20)
```

| 入口参数 | 定义与使用条件 |
|---|---|
| `device` | 优化侧设备，默认 `"cpu"`；CUDA 任务显式使用 `"cuda:0"` 等设备名 |
| `restart_per_iteration` | 分段计算的进程重启间隔，重启后继续原运行 |
| `path_result` | 已有具体运行目录；省略时创建新运行 |
| `target_iteration` | 从指定保存状态继续；普通继续计算省略该项，读取最近状态 |

启动入口放在 `if __name__ == "__main__":` 内，避免多进程导入任务文件时重复执行。`start_optimization()` 启动后台计算进程，不打开图形界面。

继续计算示例见[脚本快速开始](scriptguide.md#continuation)。恢复过程加载运行目录内的 `scripts/MAIN_SCRIPT_FOR_RESTART.py` 及保存状态；修改原任务文件不会自动修改已有运行。

<a id="section-params-定义"></a>

## 3 Params 参数聚合

`Params` 接收几何、FEA 和材料三个集合。嵌套类名称用于组织代码，实际传入父类的对象确定模型配置。

```python
class Params(morphopt.Params):
    def __init__(self):
        super().__init__(
            geometry=self.GeometryParams(),
            feamodel=self.FEAParams(),
            materials=self.MaterialsParams(),
        )
```

该片段位于任务的 `Params` 类中，三个集合类按后续章节在同一类内定义。`Params` 的常用接口如下。

| 方法或属性 | 定义 |
|---|---|
| `geometry`、`feamodel`、`materials` | 三类参数集合的运行对象 |
| `initialize()` | 初始化三个集合 |
| `create_feamodel(path_result=None, pools=None)` | 从当前几何创建 FE 模型，设置材料并初始化模型 |
| `reinitialize(iteration)` | 准备本轮参数状态 |
| `save(foldpath, iteration)`、`load(foldpath, iteration)` | 保存或读取指定迭代的设计状态 |

三类集合均提供 `add_interface()`、`interfaces` 和 `interface(name)`。未指定注册名称时，集合生成 `<类名>_<序号>` 名称。`interface(name)` 在名称无效时报告已有候选对象。

<a id="geometry"></a>

## 4 GeometryParams：部件、曲面与实例

<a id="section-部件注册与命名"></a>

### 4.1 部件注册与命名

几何集合在 `define_interface()` 中注册 Part 接口：

```python
class GeometryParams(morphopt.GeometryParams):
    def define_interface(self):
        self.add_interface(
            morphopt.BoxPart(
                length=40.0, height=16.0, depth=8.0,
                mesh_size=2.0, mesh_order=1,
            ),
            name="block",
        )
```

上述对象的几何注册名和默认 Part 名均为 `block`。脚本基类默认创建一个同名、零位姿的 Instance；UI 通常显式声明 `part1-1` 等实例名。使用脚本时，载荷引用应与实际声明的 Instance 名一致。

| Part 类型 | 定义入口 | 设计特征 |
|---|---|---|
| `BoundaryPart` | `define_surfaces()` | 参数化闭合边界与形状设计变量 |
| `OffsetBoundaryPart` | `define_surfaces()`，加偏置参数 | 内腔偏置实体层与形状设计变量 |
| `BoxPart` | 长、宽、高与网格参数 | 结构化长方体，可承载 SIMP 材料场 |
| `CADPart` | `define_operations()` | CAD 操作历史与实体网格 |
| `INPPart` | INP 路径与源 Part 选择 | 已有网格及集合导入 |
| `BasePart` 子类 | `build_part()` | 自定义 TorchFEA Part 构建逻辑 |
| `FixedPart` 子类 | `build_part()` | 自定义固定几何，复用网格并直接访问其中的节点集、表面集合及单元集 |

<a id="section-geometryparams-定义要点一个-part-接口"></a>

### 4.2 BoundaryPart 与边界曲面

`BoundaryPart` 将曲面 `0` 作为外边界，后续曲面作为内腔边界。曲面登记顺序同时确定集合索引和设计变量顺序。

```python
class Actuator(morphopt.BoundaryPart):
    def define_surfaces(self):
        outer = self.BSP.initialize_cylinder(
            r0=8.0, length=80.0, seed_size=1.0,
            flip=False, maxR=0.2, maxC=1.0, maxFF=0.2,
        )
        outer.is_updatable = True
        outer.add_constraint(outer.mirror("xz"))
        self.add_surface_interface(outer)

        cavity = self.BSP.initialize_cylinder(
            r0=4.0, length=74.0, seed_size=1.0,
            init_location=[0.0, 0.0, 3.0], flip=True,
            maxR=0.2, maxC=1.0, maxFF=0.2,
        )
        cavity.is_updatable = True
        cavity.add_constraint(cavity.mirror("xz"))
        self.add_surface_interface(cavity)
```

该类定义在 `GeometryParams` 中后，通过 `self.add_interface(self.Actuator(fea_seed_size=1.0, mesh_order=1), name="part1")` 注册。

| 参数 | 定义 |
|---|---|
| `fea_seed_size` | Part 体有限元网格的目标尺寸 |
| `mesh_order` | 网格阶次，`1` 或 `2` |
| `exterior_surface` | 显示表面集合名，用于部件网格和变形结果的默认可视化；边界部件默认 `surface_0_All` |
| 曲面 `seed_size` | 曲面控制网格和初始采样尺度，与体网格尺寸独立 |
| `flip` | 曲面方向反转设置；外边界与内腔按实体法向约定配置 |
| `init_location` | 曲面初始位置 |
| `maxR`、`maxC`、`maxFF` | BSP 表面度量、曲率与非正交性的正则化阈值 |
| `perturbation_L` | 初始扰动长度参数，负值表示不施加该扰动 |

`maxR`、`maxC` 和 `maxFF` 通过更新器中的 `Fairness` 项参与正则化，不等同于控制点位移上限。几何变化还受更新步长、距离和包络条件共同控制。

<a id="section-曲面工厂"></a>

#### 4.2.1 曲面工厂

| 曲面 | 脚本入口 | 输入约定 |
|---|---|---|
| BSP 圆柱 | `self.BSP.initialize_cylinder(...)` | `r0`、`length`、`seed_size`、`flip`，可设置阶次、控制点对齐比例与初始位置 |
| CPGEO 圆柱 | `self.CPGEO.initialize_cylinder(...)` | `r0`、`length`、`seed_size`、`flip`、`init_location`、`maxC` 等 |
| CPGEO 球面 | `self.CPGEO.initialize_Sphere(...)` | `r0`、`seed_size`、`flip`、`init_location`、`MaxC` |
| 网格曲面 | `self.MeshSurface(vertices, faces)` 或 `self.MeshSurface.initialize_from_stl_file(path_stl)` | 顶点坐标与三角面连接关系；文件导入采用 STL；不提供设计变量 |
| BREP 曲面 | `self.BREPSurface(path_step, control_point_spacing=None)` | 精确曲面及其拓扑组成的封闭边界，当前以 STEP 保存；以同名 `.brep.json` 保存拓扑身份与集合；指定 face 转换为 NURBS 后可启用面内控制点优化 |

`BREPSurface` 和 `MeshSurface` 按几何表示分类。前者在剖分时使用精确 CAD 边界，后者使用离散三角网格。STEP 和 STL 分别是当前采用的资产文件格式。BREP 默认固定，选定 NURBS 面并启用更新后提供控制点设计变量；MeshSurface 保持固定。

`initialize_Sphere` 和其 `MaxC` 参数采用当前代码中的大小写。脚本名称与 UI 中的 `cpgeo_sphere` 类型标签不同。各曲面的参数说明与示意见 [UI 曲面参考](UIreference.md#surface_types-bsp-cylinder)。

<a id="brep-topology"></a>

##### 4.2.1.1 BREP 拓扑、集合与 NURBS 转换

`BREPSurface` 管理一个闭合壳体的精确几何、拓扑和命名集合。拓扑在首次访问时读取，读取过程不生成显示三角网格或有限元网格。

| 接口 | 定义 |
|---|---|
| `faces` | 面名称到 `BREPFace` 的映射；记录底层曲面类型、有序边界线环、参数范围和几何特征 |
| `edges` | 边名称到 `BREPEdge` 的映射；记录曲线类型、端点、关联面和参数范围 |
| `vertices` | 顶点名称到 `BREPVertex` 的映射；记录坐标与关联边 |
| `nurbs_faces` | NURBS 面名称到 `NURBSFace` 的映射；记录控制点、固定有理权重、各方向次数及节点矢量 |
| `convert_faces_to_nurbs(faces)` | 将指定的一个或多个逻辑面转换为 NURBS，重新组装闭合壳体并保留原始面名称 |
| `select_design_faces(faces)` | 从已有 NURBS 面中指定参与形状更新的面；启用更新前必须显式指定，不从资产推断 |
| `show(plotter=None)` | 交互查看面名称；单击几何面显示 `face_N` 并高亮整个面，单击空白处清除选择。传入已有 PyVista Plotter 时只配置场景，由调用者打开窗口 |
| `add_surface_set(name, faces)` | 注册一个或多个面的并集 |
| `add_node_set(name, entities)` | 注册面、边或顶点所包含节点的并集 |
| `evaluate_face(name, uv)` | 在底层曲面上求值，输入形状为 `(N, 2)`，返回 `(N, 3)` 坐标 |
| `contains_face_parameters(name, uv)` | 判断参数点是否位于裁剪后的有效面域，包括孔洞排除 |
| `evaluate_edge(name, parameters)` | 对边的三维曲线求值，返回 `(N, 3)` 坐标 |
| `edge_parameters_on_face(face, edge, parameters, which=0)` | 将边参数映射到关联面的 UV 坐标；周期接缝通过 `which` 选择分支 |
| `export_step(path)` | 导出当前几何及同名 `.brep.json`，不生成有限元网格 |
| `bind_mesh(part)` | 在有限元单元阶次处理完成后，逐面匹配最终节点的 UV；由 `BoundaryPart` 自动调用 |
| `map_face_nodes(name)` | 在缓存 UV 上计算指定面的有限元节点坐标，保留坐标对控制点的 PyTorch 计算图 |
| `is_updatable = True` | 将已选 NURBS 面的控制点纳入 `BoundaryPart` 设计变量；初始值为 `False` |

```python
class Body(morphopt.BoundaryPart):
    def define_surfaces(self) -> None:
        boundary = self.BREPSurface("morphopt_assets/body/surface_0.stp", control_point_spacing=0.8)
        boundary.convert_faces_to_nurbs(["face_0"])
        boundary.select_design_faces(["face_0"])
        boundary.is_updatable = True
        boundary.add_surface_set("loaded", ["face_0"])
        boundary.add_node_set("rim", ["edge_0"])
        boundary.export_step("geometry_output/body.stp")
        self.add_surface_interface(boundary)
```

示例中的 `face_0`、`edge_0` 应根据实际拓扑选择。第 0 个曲面的 `loaded` 面集在有限元模型中命名为 `surface_0_loaded`，对应节点集为 `surface_0_loaded_nodes`；`rim` 节点集命名为 `surface_0_rim`。各面另有 `surface_0_face_N` 及 `surface_0_face_N_nodes` 别名，各边和顶点自动生成 `surface_0_edge_N`、`surface_0_vertex_N` 节点集。原有 `face_N`、`face_N_nodes` 和 `surface_0_All` 集合继续保留。

曲面的 `evaluate_face()` 包含底层曲面在裁剪区域外的延拓值。积分或采样应使用 `contains_face_parameters()` 选择有效面域。

NURBS 转换由 TorchFEA 的 OCC 几何层执行。非平面曲面采用原生 `convertToNURBS`；平面构造精确的双线性 B 样条支撑面，并沿用原有外轮廓和孔洞。转换后重新组装壳体，后续预览、STEP 导出和体网格均使用该几何。拓扑身份通过几何特征映射保存；特征不能唯一识别或拓扑数量改变时，转换报告错误。

`.brep.json` 统一保存 `face_map`、`edge_map`、`vertex_map`、命名集合。STEP 几何及元数据应共同移动。读取导出结果时恢复这些定义。

**有限元节点参数匹配与可微映射**

每个 `NURBSFace` 从 OCC 精确几何读取控制点、权重和节点矢量。读取依赖 `cadquery-ocp>=8.0.1.1.0`；基函数及其一、二阶导数复用 `bspmap.Basis`，再按有理形式归一化。两个参数方向的次数可以不同，UV 保持 CAD 原生范围。周期支撑面在一个周期内展开为非周期表示，保留原有参数化。

`NURBSFace.match_coordinates(surf_node_idx, surf_nodes, initial_uv=None, batch_size=4096, tolerance=1e-9, max_iterations=40)` 采用 KD-tree 初值和分批 Newton 投影。提供 `initial_uv` 时直接使用该初值。匹配结果保存在 `surf_node_idx`、`surf_node_uv` 和 `projection_errors`。`map(uv, derivative=(0, 0))` 返回三维坐标；`derivative` 支持一、二阶纯导数及混合导数。UV 和有理权重在此映射中保持固定，控制点参与 PyTorch 自动微分。

`BoundaryPart` 在一阶或二阶网格构造完成后自动绑定 BREP 节点。孔洞边界、外轮廓及接缝上的节点先投影到对应 CAD 边，再转换到各面的参数域。二阶节点包含在匹配结果中，曲边中点由弦中点校正到 CAD 边上。每个面分别保存共享节点的 UV，并检查相邻面的重建位置是否一致。节点数量或编号在重新剖分后改变时，绑定结果重新生成。

```python
# body 已初始化，且至少一个 face 已转换为 NURBS。
mesh = body.build_part("work")
boundary = body.surface_interface(0)
face = boundary.nurbs_faces["face_0"]
parameters = face.get_surface_parameters().detach().clone().requires_grad_()
face.set_surface_parameters(parameters)
coordinates = boundary.map_face_nodes("face_0")
gradient, = torch.autograd.grad(coordinates.square().sum(), parameters)
```

节点 UV 及基函数模型属于运行期数据，不写入 `.morph` 或几何元数据。`BREPSurface` 默认固定。将 `is_updatable` 设为 `True` 后，选定 NURBS 面的控制点按面名称顺序纳入部件设计变量。构造参数 `control_point_spacing=0.8` 指定控制点的目标物理间距，单位与模型长度一致。沿两个参数方向分别采样等参数曲线，以各方向最长采样曲线的弧长除以间距，向上取整后加一，确定最小控制点数；通过精确插入节点实现加密。间距表示平均设计分辨率，不要求位于曲面外部的控制点彼此等距，也不构成局部间距上限。已有更密的控制网格保持原状。默认 `None` 保留原始网格。该配置属于任务定义，不写入资产元数据。网格绑定时，裁剪边、孔洞边和参数域边界所涉及的控制点被固定，其他控制点可由几何优化器更新。

每轮剖分前，当前控制点写入临时 STEP 实体，连同当前面映射一起载入 Gmsh。导出迭代曲面时也使用当前控制点；`.npz` 迭代归档保存各选定面的控制点。写回前检查原有裁剪边是否仍落在更新后的曲面上，修复实体并验证闭合性。会移动现有边界或使实体失效的更新报告错误。此接口支持固定边界的面内形状优化；边界移动及相邻未选面随动需要另外定义联动规则。

<a id="section-曲面对称与关联"></a>

#### 4.2.2 曲面对称与关联

```python
surface.add_constraint(surface.mirror("xz"))
surface.add_constraint(surface.mirror("xy", offset=40.0))
```

上述两个调用展示不同镜面配置，实际按模型选择登记。BSP 支持 xz 平面和指定偏移的 xy 平面；CPGEO 支持 xy、xz、yz 镜面和旋转对称，例如 `surface.rotate(axis="z", order=4)`。

跨曲面关联通过 `target.add_constraint(target.relate(source, pose=(tx, ty, tz, rx, ry, rz)))` 登记，两侧应采用同类曲面。该表达式中的六个分量替换为实际位姿数值。约束按登记顺序执行，多个约束的叠加应满足几何相容条件。

自定义曲面约束继承 `morphopt.BaseSurfaceConstraints`，实现 `apply(surface)` 与 `reinitialize(surface)`。Part 级跨曲面处理通过重写 `apply_surface_constraints()` 扩展。

<a id="section-instance-位姿与集合引用"></a>

### 4.3 Instance 位姿与集合引用

```python
class Frame(morphopt.INPPart):
    def define_instance(self):
        self.add_instance(self.part_name, "frame_left", [0, 0, 0, 0, 0, 0])
        self.add_instance(self.part_name, "frame_right", [0, 40, 0, 0, 0, 1.5708])
```

`define_instance()` 在所属 Part 中定义。每个实例名称在装配体内应唯一。六维位姿采用平移与旋转指数坐标，后三项不能按欧拉角解释。

| 引用对象 | 常见名称 | 使用接口 |
|---|---|---|
| 边界曲面完整表面 | `surface_0_All`、`surface_1_All` | 压力、接触 |
| BSP 外边界底端与顶端节点集 | `surface_0_Bottom`、`surface_0_Head` | 固定、耦合；CPGEO 和 BREP 不生成这些节点集 |
| Box 面节点集与表面集 | `nodes_xmin`、`surface_xmax` 等 | 固定、载荷 |
| CAD 最终面集合 | `face_N` 等 | 按实际几何检查后引用 |
| INP 集合 | 源文件中的集合名 | 按导入后有效名称引用 |

材料引用 `part_name`，载荷引用 `instance_name`。几何更新器绑定几何集合的注册名，材料更新器绑定材料集合的注册名。显式覆盖 Part 名时，各引用应分别核查。

<a id="section-cad-历史与-step-导出"></a>

### 4.4 CAD 历史与 STEP 导出

```python
import torchfea

class Housing(morphopt.CADPart):
    def define_operations(self):
        self.add_operation(torchfea.cad.Box("body", dx=40, dy=16, dz=8))
        self.add_operation(torchfea.cad.Cylinder(
            "bore", x=20, y=8, z=-1, dz=10, radius=3,
        ))
        self.add_operation(torchfea.cad.Cut(
            "housing", object_id="body", tool_id="bore",
        ))
```

`self.add_interface(self.Housing(mesh_size=2.0, mesh_order=1), name="housing")` 将嵌套的 `Housing` 类注册到几何集合。CAD 操作按历史顺序执行，每个操作使用有效 ID；后续操作只引用当前仍有效的对象。

| 类别 | `torchfea.cad` 操作类 |
|---|---|
| 基本体 | `Box`、`Wedge`、`Cylinder`、`Sphere`、`Cone`、`Torus` |
| 文件导入 | `StepImport` |
| 布尔运算 | `Fuse`、`Cut`、`Intersect` |
| 几何变换 | `Translate`、`Rotate`、`Dilate`、`Mirror` |

各操作参数及顺序引用示意见 [CAD 接口参考](UIreference.md#cad)。布尔操作改变几何拓扑后，面编号与相关载荷分配应重新核查。

<a id="section-cadpart-的-step-导出"></a>

#### 4.4.1 导出局部 CAD 实体

```python
housing = Housing(part_name="housing")
housing.initialize()
torchfea.cad.export_step(housing.operations, "housing.stp")
```

导出直接调用 `torchfea.cad.export_step()`，不要求预先生成有限元网格。结果包含当前 CAD 历史的最终实体与历史中的几何变换，坐标位于部件局部坐标系；Instance 位姿属于装配声明。扩展名可使用 `.stp` 或 `.step`。脚本调用直接写入目标路径；UI 的目录选择、文件命名和覆盖确认见 [STEP 导出流程](UIreference.md#cad-step-export)。

<a id="cad-to-boundary"></a>

#### 4.4.2 CADPart 转换为 BoundaryPart

`CADPart.to_boundary_part(asset_directory="morphopt_assets")` 将已初始化的单实体 CAD 部件转换为普通 `BoundaryPart`，按照封闭壳体导出 STEP 资产并创建 `BREPSurface`。外壳位于索引 0，内腔位于后续索引。转换保留部件名称、实例名称与位姿，以及网格尺寸和阶次。实例声明采用深拷贝；后续调用 `initialize()` 时保留已有声明。源 CAD 历史仅在转换期间使用，转换后的曲面读取 STEP 文件。

```python
class CavityPart(morphopt.CADPart):
    def define_operations(self):
        self.add_operation(torchfea.cad.Box("outer", dx=20, dy=20, dz=20))
        self.add_operation(torchfea.cad.Sphere(
            "cavity", x=10, y=10, z=10, radius=4,
        ))
        self.add_operation(torchfea.cad.Cut(
            "body", object_id="outer", tool_id="cavity",
        ))

cad = CavityPart(part_name="body", mesh_size=2, mesh_order=1)
cad.initialize()
boundary = cad.to_boundary_part(asset_directory="morphopt_assets")

# 两个接口分别对应长方体外壳与球形内腔。
outer = boundary.surface_interface(0)
cavity = boundary.surface_interface(1)
print(outer.face_names)
print(cavity.face_names)

# 在 GeometryParams.define_interface() 中注册转换后的部件：
# self.add_interface(boundary, name="body")
```

上例生成以下资产。每个 STEP 保存一个封闭壳体对应的独立实体；JSON 保存原始 `face_N` 的几何特征映射，重新导入时据此恢复面名称。

```text
morphopt_assets/body/
├── surface_0.stp
├── surface_0.brep.json
├── surface_1.stp
└── surface_1.brep.json
```

既有资产可直接通过 `self.BREPSurface("morphopt_assets/body/surface_0.stp")` 加入 `define_surfaces()`。STEP 与同名映射文件应一同移动。普通 STEP 未提供映射时，几何面由部件在剖分时统一分配 `face_N` 名称。

| 集合 | 转换后的含义 |
|---|---|
| `face_N` | 原 CAD 的第 N 个几何面，编号和几何归属保留 |
| `face_N_nodes` | 对应几何面上的有限元节点 |
| `surface_0_All` | 外壳所有面的表面集与同名节点集 |
| `surface_i_All`，i > 0 | 第 i 个内腔壳体的表面集与同名节点集 |

压力可引用 `实例名.face_N` 作用于原 CAD 面，也可引用 `实例名.surface_1_All` 作用于整个内腔。上例的默认实例名为 `body`，相应引用为 `body.face_N` 和 `body.surface_1_All`。

转换不生成三维有限元网格，不执行 B 样条或 CPGEO 拟合。曲面接口采用 `BREPSurface`，STEP 中的精确几何用于后续剖分，显示网格在预览时生成。转换结果默认固定；对所需 face 执行 NURBS 转换并设置 `is_updatable = True` 后，可优化该面的内部控制点。固定几何上的材料优化可独立配置。

每次转换要求 CAD 历史只包含一个最终实体。多个独立实体应分别定义为 CADPart。贯通孔的孔壁通常与外表面属于同一个封闭壳体，因此可能同属 `surface_0_All`；孔壁仍可通过原来的 `face_N` 单独选择。修改源 CAD 历史后应重新转换，并核查拓扑面编号。

<a id="section-inpbox-与自定义-part"></a>

### 4.5 INP、Box 与自定义 Part

```python
# 以下调用位于 GeometryParams.define_interface() 中。
self.add_interface(
    self.INPPart(mesh_file="model/frame.inp", inp_part_name="FRAME"),
    name="frame",
)
self.add_interface(
    self.BoxPart(length=40, height=16, depth=8, mesh_size=2, mesh_order=1),
    name="block",
)
```

`INPPart` 的 `inp_part_name` 选择源文件中的部件，`part_name` 表示当前装配体内的部件名，两者分别定义。只有一个源 Part 时可按导入器约定省略源选择。导入范围限于当前 MorphOpt/TorchFEA 支持的网格、集合、材料和截面内容，不执行完整 Abaqus 求解流程。占位材料与截面格式见[网格示例](examples/reference-box.inp)。

`BoxPart` 的默认单元块名为 `C3D8`，通过 `elementname="C3D8"` 选择该块。二阶网格使用 C3D20 单元，单元块名仍为 `C3D8`。

自定义固定几何继承 `morphopt.FixedPart`，重写 `build_part(path_result=None, pools=None)` 并返回 `torchfea.Part`；基类负责复用网格，并通过属性直接访问其中的集合。需要逐轮构建网格的通用几何继承 `morphopt.BasePart`。`define_instance()` 管理装配声明。几何或网格随优化变化时设置 `is_variable=True`；固定网格上的材料优化不要求将该标记设为 True。

<a id="section-feaparams-定义要点"></a>

## 5 FEAParams：载荷、边界、连接与工况

<a id="section-接口定义与工况幅值"></a>

### 5.1 接口定义与工况幅值

`define_interface()` 创建作用对象，`define_steps()` 配置工况参数。压力接口的构造确定实例和表面，压力数值由工况给定。

```python
class FEAParams(morphopt.FEAParams):
    def define_interface(self):
        self.add_interface(
            self.Pressure(instance_name="part1-1", surface_name="surface_1_All"),
            name="pressure_1",
        )

    def define_steps(self):
        self.add_step("load_case_1")
        self.add_step("load_case_2")
        self.set_step_params("load_case_1", "pressure_1", [0.04])
        self.set_step_params("load_case_2", "pressure_1", [0.06])
```

`add_step(name)` 按注册顺序建立具名工况，随后通过 `set_step_params(step_name, load_name, values)` 赋值。工况名称须非空且唯一，载荷名称必须已注册，参数列表长度与接口 `num_values` 一致。工况表示由当前接口共同定义的载荷条件，不等同于任意时间积分历程。

<a id="section-十三类接口与参数顺序"></a>

### 5.2 十三类接口与参数顺序

下表中的类型均由 `FEAParams` 类提供。构造参数确定拓扑或作用范围；最后一列为 `set_step_params()` 的数值列表。

| 接口类型 | 主要构造参数 | 每工况值与作用 |
|---|---|---|
| `Pressure` | `instance_name`、`surface_name` | `[p]`，表面压力 |
| `ConcentratedForce` | `rp_name` | `[Fx, Fy, Fz]`，参考点集中力 |
| `ConcentratedMoment` | `rp_name` | `[Mx, My, Mz]`，参考点集中力矩 |
| `BodyForce` | `element_name`、`instance_name` | `[fx, fy, fz]`，体力密度 |
| `SpringToGround` | `rp_name` | `[k, L0, Px, Py, Pz]`，参考点与固定点之间的轴向弹簧 |
| `SpringBetweenRPs` | `rp_name1`、`rp_name2` | `[k, L0]`，参考点间轴向弹簧 |
| `PenaltyDoF` | `obj_name`、`s`、`obj_type` | `[k, target]`，所选自由度的罚约束 |
| `BoundaryCondition` | `instance_name`、`set_nodes_name`、`index_dof` | 无工况数值，固定所选节点平移分量 |
| `ReferencePointBoundaryCondition` | `rp_name`、`index_dof` | 当前接口无工况数值，固定所选 RP 分量 |
| `ReferencePoint` | `rp_location` | 无工况数值，建立参考点 |
| `Couple` | `rp_name`、`instance_name`、`set_nodes_name` | 无工况数值，建立 RP 与节点集的运动耦合 |
| `Contact` | `instance_name1/2`、`surface_name1/2`，以及罚参数 | 无工况数值，两个表面之间的接触 |
| `SelfContact` | `instance_name`、`surface_name`，以及可选罚阈值 | 无工况数值，单一表面的自接触 |

`BodyForce` 和 `SelfContact` 为脚本类名，UI 中对应的标签分别为 `Bodyforce` 和 `ContactSelf`。`ReferencePointBoundaryCondition` 当前不通过 `set_step_params()` 接收非零位移；不能将外部求解器中的任意位移边界定义直接套用到该接口。

<a id="section-参考点耦合与固定条件"></a>

### 5.3 参考点、耦合与固定条件

```python
# 以下调用位于 FEAParams.define_interface() 中。
self.add_interface(self.ReferencePoint(rp_location=[0, 0, 80]), name="RP_1")
self.add_interface(
    self.Couple(rp_name="RP_1", instance_name="part1-1",
                set_nodes_name="surface_0_Head"),
    name="couple_1",
)
self.add_interface(
    self.BoundaryCondition(instance_name="part1-1",
                           set_nodes_name="surface_0_Bottom", index_dof=[0, 1, 2]),
    name="bc_1",
)
```

参考点的坐标仅定义位置，实体与 RP 之间的运动联系由 Couple 单独建立。RP 的六个分量采用 `[x, y, z, rx, ry, rz]`；实体节点边界通常选择 `[0, 1, 2]` 三个平移分量。

<a id="section-接触与弹簧"></a>

### 5.4 接触与弹簧

```python
# 以下调用位于 FEAParams.define_interface() 中。
self.add_interface(
    self.Contact(instance_name1="part1-1", surface_name1="surface_0_All",
                 instance_name2="frame", surface_name2="contact_face",
                 penalty_threshold_h=0.1),
    name="contact_1",
)
self.add_interface(self.SpringToGround(rp_name="RP_1"), name="spring_1")
```

该片段要求模型中已存在 `frame` 实例及其 `contact_face` 表面。弹簧在 `define_steps()` 中设置，如 `self.set_step_params("load_case_1", "spring_1", [1.0, 10.0, 0.0, 0.0, 90.0])`。罚参数、接触方向与弹簧初始长度应与几何尺度和一致单位制匹配。各接口的完整字段与图示见 [UI 载荷参考](UIreference.md#loads)。

<a id="section-materialsparams-定义要点"></a>

## 6 MaterialsParams：本构与材料设计场

<a id="section-均质材料分配"></a>

### 6.1 均质材料分配

```python
class MaterialsParams(morphopt.MaterialsParams):
    def define_interface(self):
        self.add_interface(
            self.HomogeneousMaterial(
                material_parameters=self.models.NeoHookeanLnJParams(
                    mu=0.482, kappa=4.8,
                ),
                density=1.08e-9,
                part_name="part1",
                elementname="",
            ),
            name="material_1",
        )
```

本构参数类型由 `MaterialsParams.models` 提供，参数对象的类型确定 TorchFEA 材料模型。当前入口为 `self.models`，不使用 `self.materialmodels`，也不另传 `material_model` 参数。

`part_name` 为装配体中的目标 Part 名。`elementname=""` 表示该 Part 的全部单元块；填写具体名称时选择 `Part.elems` 的实际键名。多个材料覆盖同一块时，分配顺序可能导致覆盖，应明确划分材料作用区域。

<a id="section-八种本构参数类型"></a>

### 6.2 八种本构参数类型

| 参数类型 | 传入参数 |
|---|---|
| `self.models.LinearElasticParams` | `E`、`nu` |
| `self.models.NeoHookeanParams` | `mu`、`kappa` |
| `self.models.NeoHookeanLnJParams` | `mu`、`kappa` |
| `self.models.MooneyRivlinParams` | `c10`、`c01`、`kappa` |
| `self.models.YeohParams` | `c1`、`c2`、`c3`、`kappa` |
| `self.models.GentParams` | `mu`、`Jm`、`kappa` |
| `self.models.ArrudaBoyceParams` | `mu`、`N`、`kappa` |
| `self.models.OgdenParams` | `mu`、`alpha`、`kappa` |

应力型参数使用模型的应力单位，`nu`、`Jm`、`N` 和 `alpha` 为无量纲量。不同本构模型的参数值应来自对应模型的材料标定，不能仅按字段数量互相替换。

<a id="section-simp-密度场材料"></a>

### 6.3 SIMP 密度场材料

```python
# 以下调用位于 MaterialsParams.define_interface() 中。
self.add_interface(
    morphopt.SIMP_BSPFieldMaterials(
        material_parameters=self.models.NeoHookeanLnJParams(mu=0.48, kappa=4.8),
        mumax=10.0, kappamax=100.0,
        simp_ratio_min=1e-7,
        bounding_box=[0, 40, 0, 16, 0, 8],
        simp_field_resolution=2.0, degree=2,
        initial_ratio=0.5, materialpenalty=8,
        density=1.08e-9,
        part_name="block", elementname="C3D8",
    ),
    name="solid",
)
```

该片段对应前述 Box 部件 `block`。材料更新器按材料接口名 `solid` 绑定，而非按 Part 名 `block` 绑定。

| 配置 | 定义 |
|---|---|
| `bounding_box` | `[xmin, xmax, ymin, ymax, zmin, zmax]`，设计场包围盒 |
| `simp_field_resolution`、`degree` | B 样条场的控制分辨率与阶次 |
| `initial_ratio` | 设计控制场的初值，非直接的材料体积分数 |
| `materialpenalty` | 当前 RAMP 插值参数 |
| `simp_ratio_min` | 刚度比例下限 |
| `mumax`、`kappamax`、`material_parameters` | 刚度尺度与基准本构参数，应按当前材料接口一并设置 |
| `voidpenalfactor` | 低密度区域的正则化配置 |

![SIMP 控制场、材料占比与刚度比例](images/ui-reference/diagrams/simp-pipeline.svg)

当前映射为 `ρ=sigmoid(f)`，再由 RAMP 将 `ρ` 转为刚度比例。`VolFrac` 约束体积加权的 `ρ`，`MinValue/MaxValue` 约束控制变量 `f`。例如 `initial_ratio=0.5` 对应 `ρ≈0.6225`，并非 50% 材料占比。设计场空间映射由材料接口内部维护，常规配置不重写内部插值函数。

<a id="section-objectivefunction-定义"></a>

## 7 ObjectiveFunction：损失与监测指标

<a id="section-标量损失与优化方向"></a>

### 7.1 标量损失与优化方向

`objective_function()` 返回保留计算图的标量 `torch.Tensor`。框架执行最小化，目标定义采用以下约定。

| 目标 | 损失表达式 |
|---|---|
| 最小化响应 `q` | `q` |
| 最大化有符号响应 `q` | `-q` |
| 匹配目标 `q_target` | `(q - q_target) ** 2` |
| 多工况匹配 | `sum(w_i * (q_i - target_i) ** 2)` |

目标函数不使用 `.item()`、NumPy 转换或 `.detach()` 切断梯度。多目标组合应同时考虑单位和典型量级；有符号转角最大化与转角绝对值最大化属于不同问题。

<a id="section-按名称提取参考点响应"></a>

### 7.2 按名称提取参考点响应

```python
class ObjectiveFunction(morphopt.ObjectiveFunction):
    def reference_point_motion(self, step_name="load_case_1"):
        morphopt.controller.params.feamodel.process_fea(self.fe, step_name=step_name)
        assembly = self.fe.assembly
        coordinates = self.fe_results[step_name].GC.to(assembly.device)
        reference_point = assembly.get_reference_point("RP_1")
        return assembly._GC2RGC(coordinates)[reference_point._RGC_index].reshape(-1)

    def objective_function(self):
        return -self.reference_point_motion()[4]

    def get_metrics(self):
        return [self.reference_point_motion()[4].detach().cpu().item()]
```

`fe_results[i]` 对应工况 `i`。`GC` 是全局广义坐标向量，不宜用向量尾部的固定偏移假定某个 RP 的位置；新增节点、RP 或约束后，该假定可能失效。上述提取方式与 UI 模板一致，使用当前 TorchFEA 后端的 `_GC2RGC` 和 `_RGC_index`。这些以下划线开头的成员属于后端内部接口，升级后端版本时应与同版本的数据模板一并核对。

`get_metrics()` 返回独立记录的响应列表，不产生优化驱动。指标数量与排列应在一个运行中保持一致。

<a id="section-载荷雅可比"></a>

### 7.3 载荷雅可比

位移或转角目标通常不需要额外声明 `jacobian_needed`。目标涉及载荷响应导数时，在构造函数中声明所需载荷名：

```python
class ObjectiveFunction(morphopt.ObjectiveFunction):
    def __init__(self):
        super().__init__()
        self.jacobian_needed = ["force_1", "moment_1"]
```

该片段扩展前述目标类的构造方法，两个载荷必须已在 `FEAParams` 中注册。结果通过 `self.fe_results[step_name].jacobian[load_name]` 访问，行对应全局广义坐标，列对应所选载荷的参数分量。提取某个 RP 的 6×6 力/力矩响应矩阵时，应按该 RP 的坐标区间选行，并按所声明的力和力矩载荷拼接，不能将任意全局矩阵直接视为末端响应。

节点位移、能量、应力应变及雅可比等数据提取示例可由 [UI 有限元数据模板](UIreference.md#section-十二个有限元数据代码模板) 查看和生成。工况切换后涉及当前载荷、接触或材料状态的量，应先按该工况更新模型状态。

<a id="section-solver-定义"></a>

## 8 Solver：工况求解与计算资源

<a id="section-cpu-与单进程配置"></a>

### 8.1 CPU 与单进程配置

```python
class Solver(morphopt.Solver):
    def __init__(self, params):
        super().__init__(params=params, num_process=1, available_gpus=[])
```

`num_process=1` 与 `available_gpus=[]` 对应默认的一个 CPU 求解进程。优化侧 `device` 与有限元侧 `available_gpus` 分别设置，CUDA 配置应同时核查两处。

<a id="section-多工况调度与-gpu"></a>

### 8.2 多工况调度与 GPU

```python
class Solver(morphopt.Solver):
    def __init__(self, params):
        super().__init__(
            params=params,
            num_process=2,
            available_gpus=["cuda:0", "cuda:1"],
            task_step_list=[["load_case_1", "load_case_2"], ["load_case_3"]],
        )
```

该示例要求三个已定义的工况及两张可用 GPU，任务 `[0, 1]` 表示在同一任务中顺序求解工况 0 和 1。任务组的数量与进程数并非同一概念；进程池调度各组任务。所有待求解工况应包含在配置中，GPU 并发数量应与模型显存占用匹配。

未配置 `task_step_list` 时，框架为每个工况建立一个任务。部分工况已分组时，其余工况按注册顺序各自建立任务。分组名称须有效且不重复，单进程仍可依次完成多个任务。

工况以字符串名称作为键，顺序由 `add_step()` 的注册顺序确定。结果通过 `self.fe_results["load_case_1"]` 访问。归档使用 `result_<工况名>_iter_<轮次>.npz`，`load_cases.json` 保存注册顺序。

工作空间目标在任务脚本中显式计算各边界高斯点工况的位移与载荷 Jacobian，并逐项加权求和。`samples` 表记录工况名称、高斯权重、边界方向符号与切向输入编号。每次循环设置当前工况，提取参考点的响应分量，并从 `result.jacobian[载荷名]` 中读取相应参数列；同一独立输入中的多个载荷参数，其 Jacobian 相加。

二维工作空间的单点积分项为 `motion[0] * tangent[1] - motion[1] * tangent[0]`，其中 `tangent` 为当前边界切向输入对应的位移 Jacobian。各点按 `integral += weight * orientation * integrand` 累加，面积为 `abs(integral) / 2`。该表达式对应驱动参数域的逆时针边界取向；绝对值在全部高斯点累加后计算。三维积分项在脚本中展开为位移与两列切向 Jacobian 的标量三重积，体积为 `abs(integral) / 3`；纯转动工作空间保留 `abs(integral) / 24` 的度量系数。目标值在积分结果上施加负号、目标权重及归一化尺度。 二维工况按第一输入下界、第一输入上界、第二输入下界、第二输入上界分组，正向切向 Jacobian 对应的边界系数依次为 `−、＋、＋、−`；每边两个高斯点时，排列为 `--++++--`。该系数规定载荷域的闭合边界取向，响应坐标中的正负方向由 Jacobian 本身给出。快速开始的工作空间指标使用同样的显式求和，返回未归一化的正值。


<a id="section-初始解与几何变化"></a>

### 8.3 初始解与几何变化

未显式传入 `U_guess` 时，仅当所有 Part 均为 `is_variable=False`，求解器才尝试读取最近保存结果作为初值。首轮或相应工况无保存结果时，初值为 `None`。固定网格的 SIMP 材料优化可以复用初值；变化网格的边界形状设计应保持相应标记。

`U_guess` 按全局工况顺序排列，再按任务组提取。例如任务 `[2, 0]` 接收 `[U_guess[2], U_guess[0]]`。任务内某工况的初值为 `None` 时，使用同一任务的上一工况结果；首工况使用模型初始坐标。任务分组因此也影响初始解的延续关系。

<a id="section-updater-定义"></a>

## 9 Updaters：设计变量更新

<a id="section-注册方法与目标绑定"></a>

### 9.1 注册方法与目标绑定

`Updaters` 管理多个独立子优化器。注册方法确定目标集合，名称确定集合中的设计对象。

| 注册方法 | 目标集合 | 绑定对象 | 梯度键 |
|---|---|---|---|
| `add_geometry_updater(updater, name=...)` | `params.geometry` | BoundaryPart 或其支持的子类 | `geometry` |
| `add_material_updater(updater, name=...)` | `params.materials` | SIMP 材料接口 | `materials` |

```python
class Updater(morphopt.Updaters):
    def define_updater(self):
        self.add_geometry_updater(self.Shape(), name="part1")
        self.add_geometry_updater(self.Shape(), name="part2")

    class Shape(morphopt.UpdaterBoundaryPart):
        def __init__(self, interface_name=None):
            super().__init__(interface_name=interface_name, max_step_iter=50)

        def define_objective(self):
            self.add_objective_function(self.objectivefuncs.ShapeDerivative())
            self.add_constraints(self.objectivefuncs.Fairness())
```

该片段要求模型中已定义两个可更新 Part。同一更新器类可以分别实例化并绑定不同目标，各自保存梯度切片和状态。注册名与目标名不同时，可使用 `self.add_geometry_updater(self.Shape(interface_name="part1"), name="arm")`；显式 `interface_name` 优先确定目标。

未指定名称且对应集合仅有一个兼容设计对象时，初始化可解析到该对象。多个候选对象的任务应显式指定目标。`update_kind` 与 `target_type` 由子优化器基类声明，注册方法和目标类型不匹配时报告错误。

<a id="section-几何更新器"></a>

### 9.2 几何更新器

```python
class Shape(morphopt.UpdaterBoundaryPart):
    def __init__(self):
        super().__init__(max_step_iter=50, max_step_length=0.2)

    def define_objective(self):
        self.add_objective_function(self.objectivefuncs.ShapeDerivative())
        self.add_constraints(self.objectivefuncs.Fairness())
        self.add_constraints(self.objectivefuncs.Distance(
            min_distance=[[2.5, 2.5], [2.5, 2.5]],
        ))
        self.add_constraints(self.objectivefuncs.boundarys.Cylinder(
            radius=10.0, height=80.0, bottom=0.0,
        ))
```

该配置对应两个曲面。基类 `BaseSurface.is_updatable` 默认值为 `False`；`BspSurface` 和 `CPGEOSurface` 默认值为 `True`，可在 `define_surfaces()` 中设置 `surface.is_updatable = False` 固定指定曲面。BREP 默认关闭，选定 NURBS 面后可启用面内控制点优化；网格曲面不提供设计变量。几何更新器直接读取曲面状态。`max_step_iter` 限定单次更新子问题内部迭代，`max_step_length` 配置最大更新步长；两者均不限制整个任务的外层轮数。

| 项目 | 注册位置 | 主要配置与适用范围 |
|---|---|---|
| `ShapeDerivative()` | `add_objective_function()` | 将主目标的结构灵敏度传入几何子问题 |
| `Fairness()` | `add_constraints()` | 使用曲面的曲率、度量等阈值抑制几何畸变 |
| `Distance(min_distance=...)` | `add_constraints()` | 曲面间最小距离，矩阵按曲面索引配置 |
| `boundarys.Cylinder(radius, height, bottom)` | `add_constraints()` | 圆柱包络 |
| `boundarys.MinRadius(radius)` | `add_constraints()` | 最小径向范围 |
| `VolumeMaximization(surf_idx, weight=...)` | `add_constraints()` | 指定 CPGEO 曲面的体积辅助目标 |

主目标在 `ObjectiveFunction` 中定义，`ShapeDerivative` 为更新子问题中的梯度项。只填写主目标而缺少相应更新器或灵敏度项，不能构成完整的形状更新配置。

<a id="section-材料更新器"></a>

### 9.3 材料更新器

```python
class Updater(morphopt.Updaters):
    def define_updater(self):
        self.add_material_updater(self.Density(), name="solid")

    class Density(morphopt.UpdaterSIMPMaterial):
        def __init__(self):
            super().__init__(max_step_iter=50, max_step_length=0.2)
            self.if_update = True

        def define_objective(self):
            self.add_objective_function(self.objectivefuncs.Sensitivity(
                normalize_gradient=False,
            ))
            self.add_constraints(self.objectivefuncs.VolFrac(
                volfrac_min=0.2, volfrac_max=0.5, elementname="C3D8",
            ))
```

该示例绑定前述 Box 部件上的 `solid` 材料。`VolFrac` 要求显式填写单元块名，且该块应属于材料的作用范围。

| 项目 | 注册位置 | 定义 |
|---|---|---|
| `Sensitivity(normalize_gradient=False)` | `add_objective_function()` | 传递主目标的材料灵敏度 |
| `DensityFieldMinimize(scale=...)` | `add_objective_function()` | 控制场辅助正则化项 |
| `VolFrac(volfrac_min, volfrac_max, elementname, penalty=...)` | `add_constraints()` | 体积加权材料占比范围 |
| `boundarys.MinValue(xmin=...)` | `add_constraints()` | 设计控制变量下界 |
| `boundarys.MaxValue(xmax=...)` | `add_constraints()` | 设计控制变量上界 |

`DensityFieldMinimize` 是弱辅助项，不能替代体积分数约束。上下界作用于设计控制变量，不直接代表 `ρ` 的上下限。

<a id="section-自定义更新器类"></a>

### 9.4 自定义更新器类

```python
class SmoothShape(morphopt.UpdaterBoundaryPart):
    def define_objective(self):
        self.add_objective_function(self.objectivefuncs.ShapeDerivative())
        self.add_constraints(self.objectivefuncs.Fairness())

class Updater(morphopt.Updaters):
    def define_updater(self):
        self.add_geometry_updater(SmoothShape(max_step_iter=80), name="part1")
```

脚本通过实例化具体子类选择实现。相同机制适用于 `UpdaterOffsetBoundaryPart` 和 `UpdaterSIMPMaterial`。自定义类保留父类的目标类型、初始化、梯度切片与状态保存约定；重写 `initialize()`、`update()` 或 `update_variables()` 时，应明确维持这些接口契约。

子优化器绑定后通过 `self.part` 或 `self.material` 访问目标，不保存整个参数集合。状态分别存入 `log/geometryupdater/<目标接口>/` 和 `log/materialupdater/<目标接口>/`。

<a id="section-codesign-模块定义"></a>

## 10 Codesign：形状与材料协同更新

协同设计仍采用公共 `Controller`、`Params`、`FEAParams`、`MaterialsParams`、`ObjectiveFunction`、`Solver` 和 `Updaters`。内腔偏置层由专用 Part 和几何更新器处理。

| 配置 | 类或接口 |
|---|---|
| 偏置部件 | `morphopt.OffsetBoundaryPart(shell_thickness=..., num_layers=...)` |
| 几何更新 | `morphopt.UpdaterOffsetBoundaryPart` |
| 材料更新 | `morphopt.UpdaterSIMPMaterial` |
| 内曲率控制 | `morphopt.codesign.InwardCurvatureRadius(...)` |
| 偏置间距控制 | `morphopt.codesign.OffsetSurfaceMinThickness(...)` |

`OffsetBoundaryPart` 至少包含一个内腔，沿内腔曲面法向构造偏置实体层。厚度、法向和局部曲率应相容，不能仅根据 STL 显示颜色判断方向。壳层仍属于同一 Part，不另建独立 FEAParams。

```python
class Updater(morphopt.Updaters):
    def define_updater(self):
        self.add_geometry_updater(self.Shape(), name="part1")
        self.add_material_updater(self.Density(), name="solid")

    class Shape(morphopt.UpdaterOffsetBoundaryPart):
        def define_objective(self):
            self.add_objective_function(self.objectivefuncs.ShapeDerivative())
            self.add_constraints(self.objectivefuncs.Fairness())
            self.add_constraints(morphopt.codesign.InwardCurvatureRadius())
            self.add_constraints(morphopt.codesign.OffsetSurfaceMinThickness())
```

该片段展示组合方式，`Density` 类采用前述材料更新器实现，几何目标必须为偏置部件，`solid` 必须为已注册的 SIMP 材料接口。材料分配应分别指定主体与偏置层的实际单元块；不能将普通均质层作为 SIMP 更新对象。网格阶次变化后的块名称与有效单元应按构建结果核查。

协同设计的理论、正则化与完整扩展流程见[协同优化文档](theory/codesign.md)。

<a id="custom-classes"></a>

## 11 自定义类与 UI 的对应关系

Python 任务通过继承和实例化选择实现。`ObjectiveFunction`、三个参数集合、`Solver`、`Updaters` 以及具体的几何或材料更新器均可由自定义类实现。控制器中保留约定的嵌套类入口即可，例如：

```python
class RotationObjective(morphopt.ObjectiveFunction):
    def objective_function(self):
        assembly = self.fe.assembly
        reference_point = assembly.get_reference_point("RP_1")
        coordinates = self.fe_results["load_case_1"].GC.to(assembly.device)
        motion = assembly._GC2RGC(coordinates)[reference_point._RGC_index]
        return -motion.reshape(-1)[4]

class ThisController(morphopt.Controller):
    class ObjectiveFunction(RotationObjective):
        pass
```

该片段演示目标类的继承入口。`pass` 表示继承已有实现，不代表一个可独立运行的完整任务。控制器的其他模块仍需定义。

UI 的“重写类”生成同类继承声明，再通过类选择框确定各模块或更新器采用的类。新建类与选择类属于两个步骤；仅编写类定义而没有绑定对象，不改变当前任务。界面入口见 [UI 自定义类参考](UIreference.md#custom-code)。

重写方法应保留父类所需的构造参数和生命周期调用。自定义模块级代码、辅助函数与数据文件应能随任务脚本被运行器重新导入；交互式会话中的临时变量不构成任务定义。

<a id="section-迭代与重启机制"></a>

## 12 迭代、保存与继续计算

![有限元分析、灵敏度与设计更新循环](images/ui-reference/diagrams/optimization-cycle.svg)

一轮计算依次执行参数与运行对象重初始化、有限元模型生成、多工况求解、目标灵敏度分析、几何或材料更新、历史记录和归档保存。工况数值、有限元模型和对应结果应按同一迭代配套读取。

| 参数或状态 | 定义 |
|---|---|
| `restart_per_iteration` | 进程分段重启间隔 |
| 子优化器 `max_step_iter` | 每轮更新内部的子问题迭代上限 |
| `history.iteration` | 当前运行的历史状态 |
| `target_iteration` | 继续计算选定的保存状态 |

`restart_per_iteration` 与 `max_step_iter` 均不是外层总轮数上限。继续计算使用最近完整保存的状态；修改几何拓扑、工况数量、指标结构或材料分配时，应重新建立运行，避免将不兼容定义与旧状态混合。

<a id="section-输出与问题诊断"></a>

## 13 输出归档与问题诊断

<a id="section-主要输出"></a>

### 13.1 主要输出

| 位置 | 内容 |
|---|---|
| `log/history_record.csv` | 每轮损失、指标、耗时与模型统计 |
| `log/geometry/`、`log/materials/` | 几何与材料设计状态 |
| `log/geometryupdater/`、`log/materialupdater/` | 按目标接口组织的更新器状态 |
| `log/femodel&results/femodel_<轮次>.npz` | 该轮求解使用的模型 |
| `log/femodel&results/result_<工况>_iter_<轮次>.npz` | 对应工况与轮次的有限元解 |
| `log/deformation/` | 变形图与表面几何 |
| `log/morphopt.log`、`log/torchfea.log` | 优化与有限元日志 |
| `cache/` | 中间网格等工作文件 |
| `scripts/MAIN_SCRIPT_FOR_RESTART.py` | 任务脚本快照 |

结果由 `morphopt-ui` 的 **文件 → 打开优化结果** 读取。独立有限元分析固定已选设计，调整工况后重新求解，不会自动更新优化任务的设计变量；操作和导出范围见 [UI 结果参考](UIreference.md#results)。

<a id="section-配置诊断"></a>

### 13.2 配置诊断

| 现象 | 核查项目 |
|---|---|
| 名称解析失败 | 集合注册名、Part 名、Instance 名、材料接口名分别核对 |
| `interfaces` 为空 | 是否尚未初始化，是否在构造阶段提前访问 |
| Part 有定义但装配体中无实例 | `define_instance()` 是否正确声明实例 |
| 压力为零 | 工况是否登记对应幅值，表面与具名工况引用是否正确 |
| 目标无法求导 | 是否使用 `.item()`、NumPy 或 `.detach()` 切断目标计算图 |
| 优化方向不符 | 最大化所需负号、分量与有符号响应定义 |
| 材料参数入口错误 | 当前入口为 `MaterialsParams.models` |
| 某对象不更新 | 更新器目标、类型、灵敏度项与曲面的 `is_updatable`；材料场检查其更新器的 `if_update` |
| 有限元不收敛 | 约束连接、载荷单位、材料参数、网格质量及更新幅度 |
| 雅可比缺少载荷项 | `jacobian_needed` 与已注册载荷名是否一致 |
| 材料占比与初值不符 | 是否区分控制场 `f`、占比 `ρ` 和刚度比例 |
| 结果无法与模型匹配 | 是否选取相同轮次的模型和结果 |

<a id="section-参考实现"></a>

## 14 源码与示例索引

| 内容 | 参考文件 |
|---|---|
| 入门形状优化 | [文档完整任务](examples/bending_optimization.py) |
| 固定 STEP 外边界与 BSP 内腔优化 | [完整定义与验证记录](examples/brep-bsp-cylinder.md) |
| 形状设计扩展 | [bendingactuator.py](../examples/bendingactuator.py) |
| SIMP 任务结构 | [gripper.py](../examples/gripper.py) |
| 控制器生命周期 | [controller.py](../src/morphopt/optcore/controller.py) |
| 任务入口 | [opt_runner.py](../src/morphopt/opt_runner.py) |
| 参数集合 | [modelparams](../src/morphopt/optcore/modelparams) |
| 目标与灵敏度 | [objfunc.py](../src/morphopt/optcore/objfunc.py) |
| 求解调度 | [solver.py](../src/morphopt/optcore/solver.py) |
| 更新器注册与绑定 | [updaters.py](../src/morphopt/optcore/updaters.py) |
| 几何更新 | [update_boundary_part.py](../src/morphopt/shapeopt/update_boundary_part.py) |
| 材料更新 | [update_simpmaterial.py](../src/morphopt/simp/update_simpmaterial.py) |
| UI 有限元数据模板 | [snippets.py](../src/morphopt/ui/schemes/snippets.py) |

文档章节编号与目录由 `python scripts/number_docs.py` 生成；编辑时可运行 `python scripts/number_docs.py --watch` 自动刷新。
