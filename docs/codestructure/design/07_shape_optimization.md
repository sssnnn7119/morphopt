# 07. 形状优化

返回 [设计导览](../README.md)。

<a id="section-能力组成"></a>

## 1 能力组成

形状优化由一个可更新的边界 Part、若干曲面接口、网格生成器和一个局部形状更新器组成。`BoundaryPart` 把曲面控制变量映射为闭合边界、体网格和 TorchFEA Part；`UpdaterBoundaryPart` 在该 Part 的控制点空间内建立 L-BFGS 子问题。

```text
BoundaryPart : BasePart + ProtocalUpdatable
 ├── BaseSurface*
 ├── MeshGenerator → STEP/STL → Abaqus INP → torchfea.Part
 └── sensitivity / control points → UpdaterBoundaryPart
```

<a id="section-boundarypart"></a>

## 2 `BoundaryPart`

源码：`shapeopt/boundary_part.py`；继承 `BasePart`、`ProtocalUpdatable`。

| 属性 | 可见性 | 说明 |
|---|---|---|
| `fea_seed_size` | 公开 | 目标体网格尺寸。 |
| `mesh_order` | 公开 | 网格单元阶次。 |
| `surfaces` | 公开 | 该 Part 的曲面接口列表；索引定义曲面编号。 |
| `_surfaces_defined` | 私有 | 曲面声明已完成标记。 |
| `num_surface_interfaces` | 公开属性 | 当前曲面数量。 |
| `num_variables` | 公开属性 | 所有可更新曲面的控制变量总数。 |

| 公开方法 | 职责 |
|---|---|
| `define_surfaces()` | 用户声明曲面的钩子。 |
| `add_surface_interface(surface)` | 以顺序注册一张边界曲面。 |
| `surface_interfaces()` / `surface_interface(index)` | 获取全部或单个曲面。 |
| `initialize()` | 构建曲面声明、初始化曲面与基类 instances。 |
| `reinitialize(iteration)` | 刷新每张曲面当前几何。 |
| `apply_surface_constraints()` | 可选的 Part 级钩子，在曲面自身约束之后运行，供跨曲面扩展逻辑使用。 |
| `build_part(...)` | 输出曲面、调用体网格流程、装入 Part。 |
| `get_parameters/set_parameters/update_variables` | 获取、恢复、更新控制点张量。 |
| `get_geometry_values()` | 收集每张曲面的点、一次和二次导数。 |
| `get_control_points_list()` | 返回可更新曲面的控制点列表。 |
| `get_penalty_fairness/get_points_weight` | 向形状约束提供曲面公平性与积分权重。 |
| `obtain_design_sensitivity_vars/modify_assembly` | 连接全局自动微分分析。 |
| `save/load` | 保存/恢复每张曲面设计状态。 |
| `get_meshes/plot` | 以曲面为单位提供可视化。 |

曲面索引在每个 `BoundaryPart` 内独立使用：`0` 通常是外表面，后续索引可表示腔体或其他边界。多个边界 Part 各自从零开始计数，形成清晰的 Part 局部编号空间。

<a id="section-曲面接口层"></a>

## 3 曲面接口层

源码目录：`shapeopt/surfaces/`。

```text
BaseSurface
├── ControlPointSurface
│   ├── BspSurface
│   └── CPGEOSurface
└── FixedSurface
```

<a id="section-basesurface"></a>

### 3.1 `BaseSurface`

它继承初始化、保存和可视化协议，提供所有曲面的通用几何面：`map(uv)`、`get_normals(uv)`、`synchronize()`、`output_data()`、`get_surface_parameters()`、`set_surface_parameters()`、`get_geometry_values()`、`get_penalty_fairness()`、`get_points_weight()`、`get_mesh()`、`get_meshes()`、`plot()`。

`num_variables` 默认是零；固定面因此自然参与网格与展示，而控制变量拼接只选择可更新曲面。`barrier_function()` 提供曲面约束使用的统一平滑障碍项。

每张曲面还维护一个按注册顺序执行的 `constraints` 列表。`mirror` 和 `relate` 属性直接引用
对应的约束类，通过 `surface.add_constraint(surface.mirror(...))` 等方式显式登记。BSP 目前只
支持 xz 平面和 `z=offset` 的 xy 平面对称；其他 BSP 对称方式暂不支持。CPGEO 还支持 `rotate`。
约束由 `add_constraint()` 按调用顺序维护。自定义约束继承 `BaseSurfaceConstraints`，
实现 `apply(surface)` 和 `reinitialize(surface)`。Part 更新或重建时自动调用对应钩子；
所有约束均按列表顺序逐个执行。

<a id="section-controlpointsurface"></a>

### 3.2 `ControlPointSurface`

控制点曲面的公共层，保存控制点、预加载投影数据和导数计算缓存。`control_points` 是公开属性；`get_surface_parameters()`、`set_surface_parameters()`、`update_variables()` 和 `num_variables` 使其参与 Part 的可更新变量块。`surface.relate(other, pose)` 创建后端专属的跨曲面关系约束，将源曲面的几何复制到目标曲面；两侧必须使用同一曲面类型（BSP 对 BSP、CPGEO 对 CPGEO），并通过 `add_constraint(...)` 登记。`pose` 与 Instance 一致，为 `[tx, ty, tz, rx, ry, rz]`，后三项是旋转向量（弧度）。`pre_load()`、`get_preloaddata()`、`get_r()`、`get_rdu()`、`get_rdu2()` 支持网格节点与参数面之间的快速映射。

<a id="section-具体曲面"></a>

### 3.3 具体曲面

| 类 | 几何来源 | 公开构造/操作 |
|---|---|---|
| `BspSurface` | `bspmap.BSP` 曲面 | `initialize_cylinder()`、xz/xy 平面 `mirror()`；映射、法线、STEP 输出、保存/恢复、预加载和控制点更新。 |
| `CPGEOSurface` | `cpgeo.CPGEO` 曲面 | `initialize_cylinder()`、`initialize_Sphere()`、`mirror()`、`rotate()`；重建检查、重初始化、STL 输出、保存/恢复。 |
| `FixedSurface` | 顶点与三角面 | `initialize_from_stl_file()`、`output_stl_file()`、`output_data()`、`get_mesh()`。 |

`BspSurface` 和 `CPGEOSurface` 都给出曲面公平性数据及点权重；它们分别将控制点更新同步回 B-spline 或 CPGEO 后端。`FixedSurface` 的 `num_variables=0`，适合作为固定外形或边界的一部分。

<a id="section-meshgenerator"></a>

## 4 `MeshGenerator`

源码：`shapeopt/meshgenerator.py`。该类封装 OCC/Gmsh 到 Abaqus 输入文件的几何网格管线。

| 方法 | 职责 |
|---|---|
| `scan_directory(directory)` | 找出当前 Part 工作目录下的曲面文件。 |
| `load_and_process_files()` | 导入并整理曲面拓扑。 |
| `construct_volume()` | 从闭合边界构造体。 |
| `generate_mesh(dim=3)` | 生成二维或三维网格。 |
| `export(...)` | 写出 `.inp`、表面集合和相关网格数据。 |
| `finalize()` | 释放 Gmsh/OCC 会话。 |
| `run(...)` | 执行完整流程，并在完成或异常时收尾。 |

每个 `BoundaryPart` 使用 `workdir()` 获取独立缓存目录。曲面文件、STEP/STL、网格和 `TopOptRun.inp` 因而按 Part 隔离，适用于多实体并行网格生成。

<a id="section-updaterboundarypart"></a>

## 5 `UpdaterBoundaryPart`

源码：`shapeopt/update_boundary_part.py`；继承 `BaseUpdater`。

| 公开属性 | 说明 |
|---|---|
| `part` | 已绑定的 `BoundaryPart`。 |
| `surface_interfaces` | 目标 Part 的曲面列表。 |
| `pathlog_required()` | 声明形状更新器状态目录。 |

构造参数保存最大控制点位移、最大半径/公平性变化、初始步长以及增减阈值等局部优化策略。运行时私有状态保存每张曲面的步长、目标/约束缓存和 L-BFGS 实例。

| 公开方法 | 职责 |
|---|---|
| `initialize()` | 绑定目标、声明子问题并建立初始优化器。 |
| `reinitialize(gradient)` | 接收当前 Part 的梯度，刷新曲面几何、目标和约束。 |
| `closure(x, return_list=False)` | 计算当前局部设计变量的目标与约束项。 |
| `update()` | 执行局部 L-BFGS 并返回设计变量改变量。 |
| `update_variables(dx)` | 将改变量施加到 Part 曲面。 |
| `save/load` | 保存/恢复步长和局部更新状态。 |

它使用 `ShapeDerivative` 作为灵敏度目标，并可组合 `Fairness`、`Distance`、`VolumeMaximization`、`MinRadius`、`Cylinder` 等约束。

<a id="section-形状目标与约束"></a>

## 6 形状目标与约束

源码目录：`shapeopt/objectivefuncs/`。

| 抽象 | 运行签名 | 作用 |
|---|---|---|
| `BaseObjective` | `initialize(gradient, r0, rdu0, rdu20, if_update)`，`__call__(r, rdu, rdu2)` | 局部形状目标。 |
| `BaseConstraints` | `initialize(r0, rdu0, rdu20, sensitivity, weights, if_update)`，`__call__(...)` | 局部形状约束。 |

| 具体类 | 作用 |
|---|---|
| `ShapeDerivative` | 将 FEA 形状梯度插值到曲面变量，形成更新目标。 |
| `Fairness` | 控制曲面公平性惩罚。 |
| `Distance` | 控制指定曲面之间的最小距离。 |
| `VolumeMaximization` | 以体积为优化约束量。 |
| `MinRadius` | 约束最小曲率半径。 |
| `Cylinder` | 约束曲面相对指定圆柱的空间范围。 |

这些项由 `UpdaterBoundaryPart` 拥有并初始化，因此同一个边界 Part 的所有局部目标、步长和约束以同一控制点向量为作用域。
