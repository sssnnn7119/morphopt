# 09. 协同设计扩展

返回 [设计导览](../README.md)。

## 定位

`src/morphopt/codesign/` 提供以边界形状为基础的偏置壳协同设计组件。它复用核心参数、FEA 与形状更新器约定，并扩展边界 Part 的网格后处理、壳层 FEA 组装以及几何厚度约束。

```text
CodesignBoundaryPartInterface ──extends──► BoundaryPartInterface
CodesignFEAParams              ──extends──► FEAParams
codesign.GeometryParams        ──extends──► core GeometryParams
codesign constraints           ──extends──► shape BaseConstraints
```

## `CodesignBoundaryPartInterface`

源码：`codesign/geometry.py`；继承 `BoundaryPartInterface`。

| 属性 | 说明 |
|---|---|
| `shell_thickness` | 壳层偏置厚度。 |
| `num_layers` | 由实体边界构造的壳层层数。 |
| `_node_idx`、`_tri_local`、`_shell_elem_offset` | 壳网格节点、三角面局部索引和元素编号的运行时缓存。 |

| 方法 | 职责 |
|---|---|
| `_compute_normals(base_nodes)` | 计算偏置方向。 |
| `_compute_offset_targets(base_nodes)` | 得到各层目标偏置位置。 |
| `_postprocess_part(part)` | 在基类网格产物上添加壳信息。 |
| `_build_shell_c3d6(part)` | 构造 C3D6 壳/楔形单元。 |
| `modify_assembly(values, assembly)` | 将形状试探值同步到实体和偏置壳层。 |

它沿用父类的曲面、网格生成和形状更新协议，并在生成 Part 后扩展实体元素集合。

## `codesign.GeometryParams`

源码：`codesign/geometryparams.py`；继承核心 `GeometryParams`。

| 公开成员 | 职责 |
|---|---|
| `shell_interfaces` | 筛选当前几何集合中的 `CodesignBoundaryPartInterface`。 |
| `shell_thickness_at(surface_index)` | 查询指定界面的壳厚度。 |
| `shell_thickness` | 汇总当前壳接口的厚度信息。 |

## `CodesignFEAParams`

源码：`codesign/feaparams.py`；继承 `FEAParams`。

`shell_interfaces` 从 Assembly/几何上下文识别壳相关接口；`create_fea(assembly)` 在普通 FEA 组装过程上加入壳层所需的 FEA 配置。

## 协同设计约束

源码：`codesign/constraints.py`。

| 类 | 父类 | 作用 |
|---|---|---|
| `InwardCurvatureRadius` | shape `BaseConstraints` | 对选定曲面评估内侧主曲率半径。 |
| `OffsetSurfaceMinThickness` | shape `BaseConstraints` | 在曲面偏置后计算最小间距/厚度。 |

两者在 `initialize(..., part_interface=...)` 时获取边界 Part、曲面选择、初始点和导数；`__call__()` 在形状更新的当前控制点上返回约束值。`_selected_surface_ids()` 将默认或显式选项规范为目标曲面索引。

## `codesign.Params`

源码：`codesign/params.py`。这是当前协同设计参数根的轻量类型标记，直接继承核心 `Params`。协同设计特有行为由 Geometry、FEA 和约束组件承载，因而能够与核心运行时、Solver、ObjectiveFunction 和 Updaters 直接组合。
