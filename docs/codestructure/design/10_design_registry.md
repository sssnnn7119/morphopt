# MorphOpt V4 设计变量注册

本文件定义 `DesignKey`、`DesignBlock`、全局设计增量、稳定排序、切分、试探更新和提交。
返回[总入口](../design.md)。

## 文档导航与输入/输出摘要

`DesignRegistry` 是设计变量顺序和 offset 的唯一事实来源。owner 保存自身参数和局部设计
增量；Registry 将各局部增量拼接成一个带梯度的全局 Tensor，并在全局 Tensor、局部梯度、
Assembly 试探状态和正式参数提交之间完成映射。

### 目录

- [10.1 `DesignKey`](#101-designkey)
- [10.2 `DesignBlock`](#102-designblock)
- [10.3 `DesignRegistry`](#103-designregistry)
- [10.4 排序与设计增量](#104-排序与设计增量)
- [10.5 试探与提交事务](#105-试探与提交事务)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | `Updatable` owner、稳定 key、局部设计增量、全局试探增量和提交变化 |
| 输出 | 冻结变量块、offset、全局设计增量、局部切片和更新后的 owner/Assembly |
| 主要读者 | Controller、Objective、Updater、可更新几何/材料/载荷对象和测试实现者 |
| 关联文档 | [总览](01_04_overview.md)、[FEA](07_fea.md)、[Updater](11_12_updaters.md)、[运行时](13_14_runtime.md) |

## 10.1 `DesignKey`

`DesignKey` 是冻结 `dataclass`。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_category` | Literal["geometry", "material", "load"] | - | 变量类别 |
| `_target_name` | str | - | Part、材料或 FEA component 稳定名称 |
| `_case_index` | int 或 None | None | load 变量所属工况；geometry/material 使用 None |

### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结标识仅保存构造状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `category` | Literal["geometry", "material", "load"] | 只读 | 内部维护 | 返回变量类别 |
| `target_name` | str | 只读 | 内部维护 | 返回目标名称 |
| `case_index` | int 或 None | 只读 | 内部维护 | 返回工况索引 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 标识通过 property 读取 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结标识不定义辅助函数 |

geometry/material key 的形式为 `geometry/body`、`material/body_solid`；load key 的形式为
`load/push@case=1`。`case_index` 使同一 component 在不同工况中的参数拥有独立变量块。

## 10.2 `DesignBlock`

`DesignBlock` 保存一个 owner 及其冻结后的向量区间。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_key` | `DesignKey` | - | 变量块稳定标识 |
| `_owner` | `Updatable` | - | 局部参数和增量的拥有者 |

### 运行时属性（`__init__()` 声明，`finalize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_start` | int 或 None | None | 全局向量起点 |
| `_stop` | int 或 None | None | 全局向量终点 |
| `_size` | int 或 None | None | 展平局部设计增量长度 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `key` | `DesignKey` | 只读 | 内部维护 | 返回稳定标识 |
| `owner` | `Updatable` | 只读 | 内部维护 | 返回 owner |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `finalize(start, design_delta)` | None | - | 保存全局区间、局部形状和长度 |
| `get_range()` | tuple[int, int] | - | 读取已冻结起止位置 |
| `compute_local_values(full_values)` | torch.Tensor | - | 纯切片并按 owner 设计增量的形状恢复局部张量 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 本类切片逻辑由外部接口完整表达 |

## 10.3 `DesignRegistry`

`DesignRegistry` 实现 `Initializable` 和 `Persistable`。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | Registry 的内容由 `initialize(params)` 收集 |

### 运行时属性（`__init__()` 声明，生命周期方法填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_pending_blocks` | dict[`DesignKey`, `DesignBlock`] | `{}` | 冻结前注册区 |
| `_blocks` | tuple[`DesignBlock`, ...] | `()` | 已冻结变量块 |
| `_block_by_key` | dict[`DesignKey`, `DesignBlock`] | `{}` | 从 `_blocks` 派生的查找索引 |
| `_design_delta` | torch.Tensor 或 None | None | 已建立的全局零基准设计增量 |
| `_iteration` | int 或 None | None | 当前设计增量所属迭代 |
| `_finalized` | bool | False | 排序与 offset 完成状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| 空 | - | - | - | 运行时注册状态通过 `get_*()` 读取 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_block(key, owner)` | None | - | 向冻结前注册区加入一个非空 `Updatable` owner |
| `finalize()` | None | - | 稳定排序变量块、建立查找索引并冻结注册表 |
| `build_design_delta()` | None | - | 调用 owner 建立局部零增量并拼接全局叶子 Tensor |
| `get_design_delta()` | torch.Tensor | - | 读取当前全局设计增量 |
| `get_blocks()` | tuple[`DesignBlock`, ...] | - | 读取已冻结变量块 |
| `get_block_range(key)` | tuple[int, int] | - | 读取一个 key 的全局区间 |
| `get_owner(key)` | `Updatable` | - | 读取一个 key 的 owner |
| `has_geometry_variables()` | bool | - | 读取 geometry 类别是否包含变量块 |
| `compute_block_values(full_values)` | dict[`DesignKey`, torch.Tensor] | - | 纯切分全局向量并恢复各局部形状 |
| `update_assembly(full_design_delta, categories=None)` | None | - | 仅在灵敏度分析图构建阶段切分试探增量并更新当前 Assembly 的 owner |
| `apply_design_delta(changes)` | None | - | 校验全部变化后按冻结顺序正式提交 owner 参数 |
| `initialize(params)` | None | `Initializable` | 收集三类 owner、调用 `finalize()` 并建立初始设计增量 |
| `reinitialize(iteration)` | None | `Initializable` | 记录当前迭代并清空上一轮全局设计增量 |
| `save(folder_path, iteration)` | None | `Persistable` | 保存 key、区间、形状、owner 签名和已提交参数摘要 |
| `load(folder_path, iteration)` | None | `Persistable` | 对照当前定义校验签名并恢复注册状态 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_collect_geometry_owners(params)` | None | 注册 `BoundaryPart` 和 `OffsetShellPart` |
| `_collect_material_owners(params)` | None | 注册 `SIMPFieldMaterial` |
| `_collect_load_owners(params)` | None | 注册 `FEAParams.get_design_owners()` 返回的逐工况参数块 |
| `_sort_key(key)` | tuple[int, str, int] | 生成类别、名称和工况索引排序键 |
| `_validate_full_values(values)` | None | 校验长度、device、dtype 和有限性 |
| `_validate_layout()` | None | 校验各 owner 的变量数与冻结的 `DesignBlock` 形状、长度一致；不一致抛出 `DesignLayoutError` |
| `_snapshot_parameters()` | dict[`DesignKey`, torch.Tensor] | 获取事务回滚所需参数快照 |
| `_restore_parameters(snapshots)` | None | 在提交失败时恢复全部 owner |

## 10.4 排序与设计增量

排序键固定为：

| 类别 | 排序键 |
|---|---|
| geometry | `(0, part_name)` |
| material | `(1, material_name)` |
| load | `(2, component_name, case_index)` |

一个 `DesignKey` 注册一次；长度为零的 owner 由收集阶段跳过。`finalize()` 只建立顺序和
offset。`build_design_delta()` 每个外层迭代重新调用 owner 的 `build_design_delta()`，把
局部增量展平、拼接并建立一个 `requires_grad=True` 的全局叶子 Tensor，再用它的视图更新
owner 局部增量。这样目标对全局变量求导时只有一条明确计算图。

| Owner | 局部设计增量 |
|---|---|
| `BoundaryPart` | 可更新曲面控制点增量 |
| `OffsetShellPart` | 元曲面控制点增量；偏置几何由固定算法派生 |
| `SIMPFieldMaterial` | 密度场 BSP 控制点增量 |
| `LoadValueBlock` | 一个 component 在一个 `case_index` 的参数增量 |

### 10.4.1 变量布局冻结

`finalize()` 之后，变量块集合、顺序、offset、局部形状与长度在整个运行期内**不可变**。
设计布局属于定义状态，`build_design_delta()`、`update_assembly()` 和
`apply_design_delta()` 都只按冻结布局切分，不重新计算布局。

| 规则 | 内容 |
|---|---|
| 冻结时机 | `DesignRegistry.initialize(params)` 调用 `finalize()` 后立即冻结 |
| 布局校验 | 每次 `build_design_delta()` 与 `update_assembly()` 入口校验各 owner 的变量数与 `DesignBlock.get_size()` 一致；不一致抛出 `DesignLayoutError` |
| 形状变化 | 任何 owner 的变量数量变化都视为定义变更，必须重新运行 `initialize()` 并重新 `finalize()`；V4 不支持运行期在线重排 |
| 几何约束 | 曲面控制点数量、BSP 材料场分辨率与 `degree`、包围盒、工况数量在运行期内固定 |
| CPGEO 重构 | 后端重构只允许发生在 `initialize()` 阶段，见[几何系统](05_geometry.md) |
| 跨运行校验 | `save()` 写入 `design_signature`（key、形状、顺序摘要），`load()` 校验不一致时拒绝装载 |
| 需要改变布局时 | 结束当前运行，修改任务定义后从 iteration 0 重新开始 |

## 10.5 试探与提交事务

```text
当前 Assembly（由 Params.build_assembly() 创建）
    → Controller 建立共享 FEAController，Solver 完成多工况平衡求解
    → SensitivityAnalyzer.build_sensitivities()
    → DesignRegistry.update_assembly(design_vars)（仅构建灵敏度计算图）
    → Updaters 计算 proposed changes
    → DesignRegistry.apply_design_delta(changes)
    → 下一轮 Params.build_assembly() 使用已提交参数创建新 Assembly
```

`update_assembly()` 只修改当前 Assembly 中 owner 已绑定的运行时引用并保留 autograd 图，
owner 的已提交参数保持不变。它由 `SensitivityAnalyzer` 在灵敏度计算图阶段调用；优化
模型由 `Params.build_assembly()` 根据已提交定义创建。`FEAParams.build_case_assemblies()` 绑定当前新 Assembly 的
全部 `LoadStep` 工作条件，每个 load owner 通过 `(component_name, case_index)` 标识工况值。

`apply_design_delta()` 先检查 key 集合、形状、device、dtype、有限性和 owner 约束，再获取
所有参数快照；全部 owner 成功后完成事务，任一提交异常时恢复全部快照并重新建立当前
Assembly。updater closure 使用 owner 的局部参数和约束状态进行试探；需要重新求解完整目标的
梯度检查和诊断统一执行上述两段 Assembly 更新流程。
