# 07. 形状优化

返回 [设计导览](../README.md)。

## 能力组成

形状优化由一个可更新的边界 Part、若干曲面接口、网格生成器和一个局部形状更新器组成。`BoundaryPartInterface` 把曲面控制变量映射为闭合边界、体网格和 TorchFEA Part；`UpdaterBoundaryPart` 在该 Part 的控制点空间内建立 L-BFGS 子问题。

```text
BoundaryPartInterface : BasePartInterface + ProtocalUpdatable
 ├── BaseSurfaceInterface*
 ├── MeshGenerator → STEP/STL → Abaqus INP → torchfea.Part
 └── sensitivity / control points → UpdaterBoundaryPart
```

## `BoundaryPartInterface`

源码：`shapeopt/boundarypartinterface.py`；继承 `BasePartInterface`、`ProtocalUpdatable`。

| 属性 | 可见性 | 说明 |
|---|---|---|
| `fea_seed_size` | 公开 | 目标体网格尺寸。 |
| `mesh_order` | 公开 | 网格单元阶次。 |
| `surfaceinterfaces` | 公开 | 该 Part 的曲面接口列表；索引定义曲面编号。 |
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
| `apply_surface_constraints()` | 用户在曲面层组合几何约束的钩子。 |
| `build_part(...)` | 输出曲面、调用体网格流程、装入 Part。 |
| `get_parameters/set_parameters/update_variables` | 获取、恢复、更新控制点张量。 |
| `get_geometry_values()` | 收集每张曲面的点、一次和二次导数。 |
| `get_control_points_list()` | 返回可更新曲面的控制点列表。 |
| `get_penalty_fairness/get_points_weight` | 向形状约束提供曲面公平性与积分权重。 |
| `obtain_design_sensitivity_vars/modify_assembly` | 连接全局自动微分分析。 |
| `save/load` | 保存/恢复每张曲面设计状态。 |
| `get_meshes/plot` | 以曲面为单位提供可视化。 |

曲面索引在每个 `BoundaryPartInterface` 内独立使用：`0` 通常是外表面，后续索引可表示腔体或其他边界。多个边界 Part 各自从零开始计数，形成清晰的 Part 局部编号空间。

## 曲面接口层

源码目录：`shapeopt/surfaceinterfaces/`。

```text
BaseSurfaceInterface
├── CpBasedSurfaceInterface
│   ├── BspSurfaceInterface
│   └── CPGEOSurfaceInterface
└── FixedSurface
```

### `BaseSurfaceInterface`

它继承初始化、保存和可视化协议，提供所有曲面的通用几何面：`map(uv)`、`get_normals(uv)`、`synchronize()`、`output_data()`、`get_surface_parameters()`、`set_surface_parameters()`、`get_geometry_values()`、`get_penalty_fairness()`、`get_points_weight()`、`get_mesh()`、`get_meshes()`、`plot()`。

`num_variables` 默认是零；固定面因此自然参与网格与展示，而控制变量拼接只选择可更新曲面。`barrier_function()` 提供曲面约束使用的统一平滑障碍项。

### `CpBasedSurfaceInterface`

控制点曲面的公共层，保存控制点、预加载投影数据和导数计算缓存。`control_points` 是公开属性；`get_surface_parameters()`、`set_surface_parameters()`、`update_variables()` 和 `num_variables` 使其参与 Part 的可更新变量块。`pre_load()`、`get_preloaddata()`、`get_r()`、`get_rdu()`、`get_rdu2()` 支持网格节点与参数面之间的快速映射。

### 具体曲面

| 类 | 几何来源 | 公开构造/操作 |
|---|---|---|
| `BspSurfaceInterface` | `bspmap.BSP` 曲面 | `initialize_cylinder()`；映射、法线、STEP 输出、保存/恢复、预加载和控制点更新。 |
| `CPGEOSurfaceInterface` | `cpgeo.CPGEO` 曲面 | `initialize_cylinder()`、`initialize_Sphere()`；重建检查、重初始化、STL 输出、保存/恢复。 |
| `FixedSurface` | 顶点与三角面 | `initialize_from_stl_file()`、`output_stl_file()`、`output_data()`、`get_mesh()`。 |

`BspSurfaceInterface` 和 `CPGEOSurfaceInterface` 都给出曲面公平性数据及点权重；它们分别将控制点更新同步回 B-spline 或 CPGEO 后端。`FixedSurface` 的 `num_variables=0`，适合作为固定外形或边界的一部分。

## `MeshGenerator`

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

每个 `BoundaryPartInterface` 使用 `workdir()` 获取独立缓存目录。曲面文件、STEP/STL、网格和 `TopOptRun.inp` 因而按 Part 隔离，适用于多实体并行网格生成。

## `UpdaterBoundaryPart`

源码：`shapeopt/update_boundarypart.py`；继承 `BaseUpdater`。

| 公开属性 | 说明 |
|---|---|
| `part` | 已绑定的 `BoundaryPartInterface`。 |
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

## 形状目标与约束

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
