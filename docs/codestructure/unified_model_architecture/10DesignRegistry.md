# MorphOpt V4 设计变量注册

本文件定义 `DesignKey`、`DesignBlock`、变量排序、`offsets`、梯度切分和试探回写。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文定义设计变量的唯一注册、排序和切分机制。`DesignKey` 标识变量拥有者，`DesignBlock`
记录变量范围，`DesignRegistry` 冻结全局顺序并负责设计向量、梯度和 Assembly 试探更新之间
的映射。

### 目录

- [10. DesignRegistry](#10-designregistry)
- [10.1 DesignKey](#101-designkey)
- [10.2 DesignBlock](#102-designblock)
- [10.3 DesignRegistry](#103-designregistry)
- [10.4 设计增量表示](#104-设计增量表示)
- [10.5 试探回写](#105-试探回写)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 可更新 owner、`DesignKey`、参数长度、变量注册顺序、设计增量和梯度 |
| 输出 | 冻结后的变量块、全局 offsets、拼接设计向量、切分梯度和试探 Assembly 更新 |
| 主要读者 | Updater、优化器、Controller、可更新几何/材料/FEA 对象和测试实现者 |
| 关联文档 | [总览与生命周期](01-04Overview.md)、[Updater](11-12Updaters.md)、[运行时](13-14Runtime.md) |

## 10. `DesignRegistry`

### 10.1 `DesignKey`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_category` | Literal["geometry", "material", "load"] | 变量类别 |
| `_target` | str | `Part`、材料或 FEA component 名称 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

`DesignKey` 是只读的稳定标识对象，运行时直接作为变量注册和索引依据。

`DesignKey` 组合值唯一标识一个变量拥有者，例如 `geometry/body` 或
`material/body_solid`。

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 稳定标识不增加独立运行时状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `category` | Literal["geometry", "material", "load"] | 只读 | 无 | 读取变量类别 |
| `target` | str | 只读 | 无 | 读取变量拥有者名称 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 稳定标识不提供独立外部方法 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

### 10.2 `DesignBlock`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 说明 |
|---|---|---|
| `_key` | `DesignKey` | 变量块名称 |
| `_owner` | `Updatable` | 可更新的 `GeometryParams`、`Part`、材料接口或 FEA component |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_start` | int | 0 | `finalize()` 后的拼接向量起点 |
| `_stop` | int | 0 | `finalize()` 后的拼接向量终点 |
| `_size` | int | 0 | `finalize()` 后的变量块长度 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `key` | `DesignKey` | 只读 | 内部维护 | 返回变量块标识 |
| `owner` | `Updatable` | 只读 | 内部维护 | 返回变量块拥有者 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 变量块通过 `DesignRegistry` 统一管理 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

### 10.3 `DesignRegistry`

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_blocks` | tuple[`DesignBlock`, ...] | () | 按类别和目标名称排序后冻结的变量块顺序 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_owners` | dict[`DesignKey`, object] | {} | 变量块拥有者 |
| `_finalized` | bool | False | 注册表冻结状态 |

#### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `blocks` | tuple[`DesignBlock`, ...] | 只读 | 内部维护 | 返回固定顺序的变量块 |
| `owners` | Mapping[`DesignKey`, object] | 只读 | 内部维护 | 返回变量块拥有者只读视图 |
| `finalized` | bool | 只读 | 内部维护 | 返回注册表冻结状态 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `register(category, target, owner, design_delta)` | None | - | 使用 owner 的设计增量注册长度大于零的变量块 |
| `finalize()` | None | - | 按类别和名称排序，固定顺序并计算 `offsets` |
| `build_values()` | None | - | 按固定顺序建立并保存完整设计增量 |
| `update_values()` | None | - | 根据 owner 的已有设计增量更新完整设计增量 |
| `get_values()` | torch.Tensor | - | 读取按固定顺序拼接的设计增量 |
| `split(full_values)` | dict[`DesignKey`, torch.Tensor] | - | 按 `offsets` 切分设计向量或顶层目标灵敏度向量 |
| `get_blocks()` | tuple[`DesignBlock`, ...] | - | 读取 `finalize()` 后固定顺序的变量块 |
| `has_geometry_variables()` | bool | - | 检查已冻结变量块中是否存在 `geometry` 类别 |
| `update_trial_values(full_values)` | None | - | 向各 owner 分发试探增量；各 owner 使用自身缓存的 TorchFEA 引用更新 `Assembly` |
| `update_owners(changes)` | None | - | 调用各 `Updatable` owner 的 `apply_design_delta()` 提交变化 |
| `get_block(key)` | `DesignBlock` | - | 读取一个变量块 |
| `get_block_range(key)` | tuple[int, int] | - | 读取变量块在完整向量中的起止位置 |
| `clear()` | None | - | 清空注册表 |
| `initialize(params)` | None | `Initializable` | 从 Geometry、Materials、FEA 收集变量并调用 `finalize()` |
| `save(foldpath, iteration)` | None | `Persistable` | 保存变量块、设计变量和 `offsets` |
| `load(foldpath, iteration)` | None | `Persistable` | 加载指定 iteration 的设计变量状态 |

#### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 本类的变量切分和提交逻辑全部通过外部接口完成 |

变量顺序由 `finalize()` 唯一确定，独立于各对象的注册调用顺序。排序规则为：

1. 类别顺序固定为 `geometry`、`material`、`load`；
2. 每个类别内部按目标稳定名称的字典序排序：几何使用 `part_name`，材料使用
   `material_name`，载荷使用 `fea_component_name`；
3. 同一目标存在多个变量块时，再按完整 `DesignKey` 的字典序排序；
4. `get_blocks()` 返回的排序顺序同时决定完整设计变量、完整灵敏度和所有 `offsets`。

排序键为：

| 类别 | 排序键 |
|---|---|
| geometry | `(0, part_name)` |
| material | `(1, material_name)` |
| load | `(2, fea_component_name)` |

固定 `Part`、均匀材料和固定载荷保持固定状态；设计变量块由可更新 owner 产生。
每个可更新 owner 只绑定一个 updater，并且一个 `DesignKey` 只注册一次。

### 10.4 设计增量表示

`build_design_delta()` 为每个 owner 建立全 0、`requires_grad=True` 的设计增量空间；
`get_design_delta()` 读取已经建立的 Tensor，并保留 autograd，供对应 updater 的子优化
问题直接使用。
`apply_design_delta()` 接收优化器输出的增量，按 owner 的映射规则正式更新内部状态，
例如几何控制点使用 `atan` 限制单步变化。

| Owner | 设计增量 |
|---|---|
| `BoundaryPart` | 曲面控制点增量 |
| `OffsetShellPart` | 源边界曲面的元曲面控制点增量；偏置节点、单元和偏置曲面由固定算法派生 |
| `SIMPFieldMaterial` | BSP 控制点增量 |
| 固定 `Part` | 空 Tensor |
| `HomogeneousMaterial` | 空 Tensor |

### 10.5 试探回写

~~~text
TorchFEA full trial vector
    → DesignRegistry.update_trial_values()
        → BoundaryPartUpdater → BoundaryPart.update_assembly()
        → OffsetShellPartUpdater → OffsetShellPart.update_assembly()
        → SIMPFieldMaterial.update_assembly()
        → future FEA component update_assembly()
    → TorchFEA 重新计算能量、残量或目标
~~~

试探过程复用已有 `Assembly`。各 owner 的
`update_assembly(design_delta)` 接收设计增量，使用对象自身缓存的 `Part`、元素或 FEA 对象
完成更新，并保留设计增量到 TorchFEA 计算的计算图；registry 保持 block `offsets` 稳定。
