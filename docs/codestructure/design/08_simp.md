# 08. SIMP 材料优化

返回 [设计导览](../README.md)。

## 能力组成

SIMP 模块将 B-spline 标量场投影到有限元节点或高斯点，得到元素材料比例与惩罚因子。`SIMP_BSPFieldMaterials` 同时是材料分配接口和可更新设计接口；`UpdaterSIMPMaterial` 以其控制点为局部 L-BFGS 变量。

```text
SIMP_BSPFieldMaterials : BaseMaterialInterface + ProtocalUpdatable
 ├── B-spline design field (control points)
 ├── map field → element density / SIMP penalty
 └── set SIMP elements and materials on one Part
                    ▲
                    │
           UpdaterSIMPMaterial
```

## SIMP 后端元素与材料

源码：`simp/simpmaterial.py`。

| 类 | 继承/用途 |
|---|---|
| `SIMPScaledMaterial` | `torchfea.materials.Materials_Base`；将基准材料能量与刚度按密度因子缩放。 |
| `SIMPElementFgrad` | `torchfea.elements.Element_3D`；基于形变梯度的 SIMP 单元基础。 |
| `SIMPElementFskew` | `Element_3D`；维护 `penalfactor` 并提供 SIMP 惩罚能量。 |
| `SIMPElementHuHu_LuLu` | `Element_3D`；HuHu/LuLu 形式的实现。 |
| `SIMPElementC3D4/C3D10/C3D8/C3D20` | 对应 TorchFEA 体单元与 `SIMPElementFskew` 的组合。 |

这些类由材料接口内部选择和替换元素类型，用户侧通常只配置材料设计场和更新器。

## `SIMP_BSPFieldMaterials`

源码：`simp/simpmaterial.py`；继承 `BaseMaterialInterface`、`ProtocalUpdatable`。

| 状态 | 说明 |
|---|---|
| `_mumax`、`_kappamax` | 实体材料的剪切与体积模量上限。 |
| `_simp_ratio_min` | 最小材料比例。 |
| `_bounding_box` | B-spline 设计场定义域。 |
| `_simp_field_resolution`、`_degree`、`_bsp_size` | 设计场离散精度与 B-spline 阶数。 |
| `_initial_ratio`、`_initial_field` | 初始材料比例与可选初始场。 |
| `voidpenalfactor`、`materialpenalty` | 空洞与实体的 SIMP 惩罚配置。 |
| `_field_bsp` | 构建后的 B-spline 场。 |
| `_cps` | 当前可优化控制点 Tensor。 |
| `simp_field` | 公开只读 B-spline 场属性。 |
| `if_use_simppenalty` | 公开只读开关，表达惩罚机制是否生效。 |

| 公开方法 | 职责 |
|---|---|
| `initialize/reinitialize` | 建立/刷新设计场控制点。 |
| `get_control_points_list()` | 以列表形式提供控制点。 |
| `num_variables`、`get_parameters/set_parameters/get_variables` | 实现可更新协议的参数面。 |
| `get_design_values()` | 返回活跃材料控制点。 |
| `update_variables(x_change, max_step_length=None)` | 施加受步长控制的更新。 |
| `get_material_ratio(designfield)` | 将设计场转成材料比例。 |
| `get_penalty_factor(designfield)` | 计算对应惩罚因子。 |
| `set_materials(fe)` | 为目标元素准备 SIMP 元素、映射字段并设置材料。 |
| `obtain_design_sensitivity_vars/modify_assembly` | 接入全局自动微分。 |
| `save/load` | 持久化/恢复 B-spline 控制点和配置。 |
| `get_meshes/plot` | 显示密度场及关联网格。 |

`_map_bsp_designfield()` 与 `_map_bsp_designfield_with_spartial_derivative()` 是内部投影实现：前者在给定空间位置计算 B-spline 标量场，后者同时给出空间导数。它们是材料投影的数值内核，更新器通过控制点与设计场约束间接控制该映射。

## `UpdaterSIMPMaterial`

源码：`simp/update_simpmaterial.py`；继承 `BaseUpdater`。

| 公开属性 | 说明 |
|---|---|
| `material` | 已绑定的 `SIMP_BSPFieldMaterials`。 |
| `num_variables` | 目标材料的控制点变量数。 |
| `pathlog_required()` | 声明材料更新器状态目录。 |

构造参数保存初始/最大控制点变化、步长增减规则、停止阈值和 `if_update` 开关；私有状态保存当前步长、前次更新量和 L-BFGS 对象。

| 公开方法 | 职责 |
|---|---|
| `initialize()` | 绑定目标，建立材料局部目标、约束和优化器。 |
| `reinitialize(gradient)` | 接收本材料接口梯度，刷新控制点、约束缓存和本轮目标。 |
| `closure(x, return_list=False)` | 返回局部材料子问题的值。 |
| `update()` | 执行局部 L-BFGS，输出控制点改变量。 |
| `update_variables(dx)` | 写回材料控制点。 |
| `save/load` | 保存/恢复局部步长状态。 |

## SIMP 目标与约束

源码目录：`simp/objectivefuncs/`。

| 抽象 | 参数面 |
|---|---|
| `BaseObjective` | `initialize(gradient, cps0)`，`__call__(cps)`。 |
| `BaseConstraints` | `initialize(cps0, sensitivity=None)`，`__call__(cps)`。 |

| 具体类 | 职责 |
|---|---|
| `Sensitivity` | 以归一化可选的灵敏度方向构造局部目标。 |
| `DensityFieldMinimize` | 对密度设计场添加最小化项。 |
| `VolFrac` | 在指定 Part/元素上计算高斯点体积分数约束。 |
| `MinValue` / `MaxValue` | 约束控制点或设计场范围。 |

`VolFrac.initialize()` 取得目标元素的高斯点和权重；该过程在 Updater 的目标设备上与 Part 节点和元素 Tensor 一起执行，保证材料局部问题的所有 Tensor 位于同一设备。
