# 09. 协同设计扩展

返回 [设计导览](../README.md)。

<a id="section-定位"></a>

## 1 定位

`codesign` 只提供内腔偏置 Part、对应的几何更新器和偏置约束。
参数集合、目标函数、FEA、求解器和更新器集合统一使用 `optcore`，
通过顶层 `morphopt` 导出；材料定义和更新直接复用 `simp`。

```text
OffsetBoundaryPart ──extends──► BoundaryPart
UpdaterOffsetBoundaryPart   ──extends──► UpdaterBoundaryPart
偏置约束                   ──extends──► shape BaseConstraints
```

<a id="section-offsetboundarypart"></a>

## 2 `OffsetBoundaryPart`

源码：`codesign/offset_boundary_part.py`。

- 第 0 个曲面是外边界，第 1 个及之后的曲面是内腔。
- `shell_thickness` 为正的偏置厚度，`num_layers` 为至少 1 的层数。
- 在内腔曲面三角网格上沿参数曲面法向构建 `C3D6` 楔形层，和实体共用基面节点。
- 偏置基面节点沿用曲面的节点顺序，保证位置和解析法向一一对应。
- `surface_<index>_offset` 表面及同名节点集对应最内层偏置面，可用于压力加载。
- `mesh_order=2` 时，由父类统一将实体与楔形元转换为二次单元并共享中间节点。
  元素集合名仍保留 `C3D6`，实际元素类型为 `C3D15`；材料接口按集合名选择。
- `build_part()` 检查偏置层的高斯权重，非有限或非正值直接报错。
- `modify_assembly()` 从当前曲面变量计算偏置节点，保留位置及法向的自动微分链。

不再定义 codesign 专用 Params、GeometryParams 或 FEAParams，也不依赖全局控制器查找 Part。

<a id="section-updateroffsetboundarypart"></a>

## 3 `UpdaterOffsetBoundaryPart`

源码：`codesign/update_offset_boundary_part.py`。

复用 `UpdaterBoundaryPart` 的更新、步长和状态保存流程，`target_type` 限定为
`OffsetBoundaryPart`。更新器在构造时不持有模型，注册时通过名称指定
目标，初始化时由 `morphopt.Updaters` 交接一个 Part。

```python
class Updater(morphopt.Updaters):
    def define_updater(self):
        self.add_geometry_updater(self.Offset(), name="body")
        self.add_material_updater(self.Density(), name="solid")

    class Offset(morphopt.UpdaterOffsetBoundaryPart):
        def define_objective(self):
            self.add_objective_function(self.objectivefuncs.ShapeDerivative())
            self.add_constraints(self.objectivefuncs.Fairness())
            self.add_constraints(self.objectivefuncs.InwardCurvatureRadius())
            self.add_constraints(self.objectivefuncs.OffsetSurfaceMinThickness())
            self.if_update = [False, True]

    class Density(morphopt.UpdaterSIMPMaterial):
        def define_objective(self):
            self.add_objective_function(self.objectivefuncs.Sensitivity())
```

<a id="section-偏置约束"></a>

## 4 偏置约束

源码：`codesign/constraints.py`。

| 类 | 作用 |
|---|---|
| `InwardCurvatureRadius` | 限制内侧主曲率，减小偏置局部自交。 |
| `OffsetSurfaceMinThickness` | 对偏置面上的邻近点对施加最小间距约束。 |

两者在 `initialize(..., part_interface=...)` 时从更新器绑定的偏置 Part
读取厚度，并在当前曲面位置和导数上计算约束。既可通过
`UpdaterOffsetBoundaryPart.objectivefuncs` 使用，也可从 `morphopt.codesign` 直接导入。
