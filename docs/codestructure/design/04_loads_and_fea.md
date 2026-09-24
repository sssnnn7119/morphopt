# 04. 载荷与 FEA

返回 [设计导览](../README.md)。

## 领域边界

载荷接口位于 `optcore/modelparams/feainterface/`。每个接口将高层声明映射到一个或多个 TorchFEA 对象；`FEAParams` 负责这些接口的注册、初始化和载荷步覆盖值。接口使用 Part 或 Instance 对象的名称定位到 Assembly，这些名称由 Geometry 生成阶段提供。

```text
FEAParams
 ├── BaseFEAInterface* ──► torchfea.Assembly 的载荷/约束对象
 └── fea_steps_params  ──► 每步数值覆盖
```

## `BaseFEAInterface`

源码：`basefeainterface.py`；继承 `ProtocalInitializable`、`ProtocalSavable`、`ProtocalVisualizable`。

| 属性 | 说明 |
|---|---|
| `_name` / `name` | 接口注册名。 |
| `_values` | 参与载荷步覆盖的一维数值列表。 |
| `num_values` | `_values` 的标量数量。 |

| 公开方法 | 职责 |
|---|---|
| `modify_fea(fea)` | 由子类把自身定义写入 FEAController。 |
| `apply_fea_value(values)` | 更新当前数值量；数值型子类可覆写。 |
| `initialize/reinitialize/save/load/get_meshes/plot` | 可选协议钩子，默认实现支持无状态接口。 |

接口名称由 `FEAParams.add_interface()` 赋值。`_values` 只表达随载荷步变化的标量；拓扑、集合名、实例名等结构性引用由子类属性保留。

## 边界、体力与压力

| 类 | 关键公开状态 | `num_values` | FEA 作用 |
|---|---|---:|---|
| `BodyforceInterface` | `instance_name`, `element_name`, `force_density` | 3 | 向指定 instance 的元素集合施加体力密度。 |
| `PressureInterface` | `instance_name`, `surface_name`, `pressure` | 1 | 向实例表面施加压力。 |
| `BoundaryConditionInterface` | `instance_name`, `set_nodes_name`, `index_dof` | 0 | 固定节点集合中的自由度。 |
| `BoundaryConditionRPInterface` | `rp_name`, `index_dof` | 0 | 固定参考点自由度。 |

`force_density`、`pressure` 的 setter 与 `apply_fea_value()` 保持一致，因此 `FEAParams.process_fea()` 能在不同载荷步覆盖它们。

## 参考点、集中载荷与弹簧

| 类 | 关键公开状态 | `num_values` | FEA 作用 |
|---|---|---:|---|
| `ReferencePointInterface` | `rp_location` | 0 | 在 Assembly 中注册参考点。 |
| `ConcentratedForceInterface` | `rp_name`, `force` | 3 | 向参考点施加集中力。 |
| `ConcentratedMomentInterface` | `rp_name`, `moment` | 3 | 向参考点施加集中力矩。 |
| `SpringToGroundInterface` | `rp_name`, `k`, `rest_length`, `point` | 5 | 参考点到固定空间点的弹簧。 |
| `SpringBetweenRPsInterface` | `rp_name1`, `rp_name2`, `k`, `rest_length` | 2 | 两参考点之间的弹簧。 |
| `PenaltyDoFInterface` | `obj_name`, `obj_type`, `s`, `k`, `target` | 2 | 对对象某一自由度添加惩罚约束。 |

参考点应先于引用它的集中载荷、耦合或弹簧注册。此顺序由用户的 `FEAParams.define_interface()` 表达，`create_fea()` 按注册顺序执行。

## 耦合与接触

| 类 | 关键公开状态 | FEA 作用 |
|---|---|---|
| `CoupleInterface` | `rp_name`, `instance_name`, `set_nodes_name` | 将 instance 上的节点集合耦合到参考点。 |
| `ContactInterface` | `instance_name1`, `surface_name1`, `instance_name2`, `surface_name2`, `penalty_threshold_h`, `penalty_start_f`, `penalty_end_f` | 两个实例表面之间的罚函数接触。 |
| `ContactSelfInterface` | `instance_name`, `surface_name`, `penalty_threshold_h` | 同一实例表面的自接触。 |

接触接口直接保存 Assembly 中的 instance 和 surface 名称；Part 的多 instance 使用场景中，载荷必须显式选择目标 instance。

## 载荷步流程

```text
用户 define_steps()
  ├─ set_step_num(n)
  └─ set_step_params(step, interface_name, values)

Params.create_feamodel()
  └─ FEAParams.create_fea(assembly)
       ├─ 所有接口 modify_fea(fea)
       └─ 每个求解步骤 process_fea(fea, step_index)
            └─ 数值接口 apply_fea_value(values)
```

一个载荷步只覆盖其明确设置的接口数值；结构定义本身在初始化阶段保持稳定。新增可步控载荷时，实现 `_values`、`num_values`、`apply_fea_value()` 和 `modify_fea()` 即可纳入这条通用流程。
