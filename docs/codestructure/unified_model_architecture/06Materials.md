# MorphOpt V4 材料系统

本文件定义材料注册、材料参数、本构对象、材料分配、均匀材料和 SIMP 材料场。
材料对象携带 `name`、`part_name` 和 `element_name`，材料集合通过
`define_materials()` 与 `add_material(interface, name)` 完成注册。

## 文档导航与输入/输出摘要

本文从材料注册表开始，依次说明本构参数命名空间、具体参数类、材料接口和材料场实现。
材料层接收几何层当前迭代的 `torchfea.Assembly`，解析每个材料对象声明的 `Part` 与元素类型，
建立 TorchFEA 本构对象并写回 Assembly；同时提供设计变量、SIMP 材料比例和材料预览缓存。

| 项目 | 内容 |
|---|---|
| 输入 | `Assembly`、材料接口定义、`part_name`、`element_name`、本构参数和材料场参数 |
| 输出 | TorchFEA 材料对象、材料到元素的映射、设计变量、材料比例、预览网格和持久化结果 |
| 生命周期 | `define_materials()` → `add_material(interface, name)` → `initialize()` → `reinitialize(iteration, assembly)` → `build_materials()` → `assign_materials()` |
| 关联文档 | [总览与生命周期](01-04Overview.md)、[几何系统](05Geometry.md)、[FEA 组件](07Fea.md)、[Solver](08Solver.md)、[功能迁移清单](23FunctionInventory.md) |

## V3 功能基线

材料层以 v3 的运行行为作为迁移基线：保留 TorchFEA 本构参数、均匀材料写入、SIMP
材料场、RAMP 插值、惩罚因子、控制点更新、灵敏度试探回写、保存/加载和材料预览。
V4 的变化集中在对象职责、注册入口和迭代生命周期；这些功能通过新的
`BaseMaterialInterface`、`MaterialsParams` 和 `Assembly` 流程继续提供。

## 目录

- [6.1 `MaterialsParams`](#61-materialsparams)
- [6.2 `MaterialModels`](#62-materialmodels)
- [6.3 `MaterialParameters`](#63-materialparameters)
- [6.3.1 `LinearElasticParams`](#631-linearelasticparams)
- [6.3.2 `NeoHookeanParams`](#632-neohookeanparams)
- [6.3.3 `NeoHookeanLnJParams`](#633-neohookeanlnjparams)
- [6.3.4 `MooneyRivlinParams`](#634-mooneyrivlinparams)
- [6.3.5 `YeohParams`](#635-yeohparams)
- [6.3.6 `GentParams`](#636-gentparams)
- [6.3.7 `ArrudaBoyceParams`](#637-arrudaboyceparams)
- [6.3.8 `OgdenParams`](#638-ogdenparams)
- [6.4 `BaseMaterialInterface`](#64-basematerialinterface)
- [6.5 `HomogeneousMaterial`](#65-homogeneousmaterial)
- [6.6 `SIMPFieldMaterial`](#66-simpfieldmaterial)

## 6. 材料类定义

### 6.1 `MaterialsParams`

`MaterialsParams` 是材料对象注册表。用户在 `define_materials()` 中创建携带
`name`、`part_name` 和 `element_name` 的材料接口，并通过 `add_material(interface, name)` 注册；注册表维护材料名称和
`Part` 名称索引。

#### 定义属性（注册表由 `__init__()` 创建，`define_materials()` / `add_material(interface, name)` 填充）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_materials` | dict[str, `BaseMaterialInterface`] | `{}` | 材料名称到材料对象的注册表 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Assembly` | `torchfea.Assembly` 或 None | None | 当前 iteration 由 `reinitialize()` 绑定的 Assembly |
| `_part_elements` | dict[str, tuple[str, ...]] | `{}` | 按当前 `Assembly` 解析的元素名称缓存 |
| `_materials_by_part` | dict[str, tuple[str, ...]] | `{}` | 由注册表派生的 `Part` 到材料名称索引 |
| `_design_deltas` | dict[str, torch.Tensor] | `{}` | 各材料已建立的设计增量 |
| `_initialized` | bool | False | 生命周期状态 |

运行时状态通过生命周期方法和显式 `build_*`、`get_*`、`update_*` 方法访问。

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `materials` | Mapping[str, `BaseMaterialInterface`] | - | 只读 | 内部维护 | 返回材料注册表的只读视图；单项使用 `materials[name]` |
| `materialmodels` | type[`MaterialModels`] | - | 只读 | 内部维护 | 返回材料参数命名空间 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `define_materials()` | None | - | 用户创建并注册材料的扩展点 |
| `add_material(interface, name)` | None | - | 校验并注册一个携带 `part_name`、`element_name` 的材料对象，并写入注册名称 |
| `names_for_part(part_name)` | tuple[str, ...] | - | 读取指定 `Part` 已注册的材料名称 |
| `initialize()` | None | `Initializable` | 建立材料接口的静态运行结构 |
| `reinitialize(iteration, assembly)` | None | `Initializable` | 解析当前 iteration 的目标 `Part`、元素族和材料映射 |
| `build_materials()` | None | - | 为全部材料建立运行时本构对象和材料映射 |
| `assign_materials()` | None | - | 使用已缓存的 TorchFEA 引用将材料对象写入 `Assembly` |
| `get_parameters(name)` | list[torch.Tensor] | `Updatable` | 读取指定材料参数的 detached clone |
| `set_parameters(name, parameters)` | None | `Updatable` | 修改指定材料的已有参数 |
| `build_design_delta(name)` | None | `Updatable` | 为指定材料建立并保存设计增量 |
| `get_design_delta(name)` | torch.Tensor | `Updatable` | 读取已经建立的设计增量，不重新计算 |
| `update_assembly(name, design_delta)` | None | `Updatable` | 使用指定材料自身的 TorchFEA 引用更新试探状态 |
| `apply_design_delta(name, design_delta)` | None | `Updatable` | 提交指定材料的设计增量并更新材料定义 |
| `get_design_values()` | torch.Tensor | `Updatable` | 读取全部材料的带计算图设计值 |
| `get_variables()` | torch.Tensor | `Updatable` | 读取全部材料的优化变量 |
| `obtain_design_sensitivity_vars(assembly)` | torch.Tensor | `Updatable` | 读取材料灵敏度分析所需变量 |
| `modify_assembly(design_sensitivity_vars)` | None | `Updatable` | 使用已缓存的 TorchFEA 引用根据灵敏度变量更新已有 `Assembly` |
| `build_meshes()` | None | `Visualizable` | 为全部材料建立预览网格缓存 |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的材料预览网格 |
| `plot(plotter, meshes)` | object | `Visualizable` | 使用已有预览网格绘制材料场 |
| `save(foldpath, iteration)` | None | `Persistable` | 保存材料定义、设计变量和结果 |
| `load(foldpath, iteration)` | None | `Persistable` | 加载材料定义、设计变量和结果 |

#### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_rebuild_part_index()` | None | 根据材料注册表刷新 `Part` 索引 |
| `_validate_material()` | None | 校验材料名称、目标 `Part` 和元素族 |
| `_resolve_part_elements()` | None | 根据当前 `Assembly` 建立元素目标缓存 |

材料注册表是材料对象的唯一事实来源。`add_material(interface, name)` 只负责注册，单项材料通过
`materials[name]` 读取；`initialize()`、`reinitialize()`、`build_materials()` 和
`build_meshes()` 负责建立对应运行时状态。
### 6.2 `MaterialModels`

`MaterialModels` 是材料参数类的类型命名空间。它记录参数类到 TorchFEA 本构类的
对应关系，并由 `create_material()` 统一创建运行时本构对象。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | 类型命名空间不保存实例构造状态 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 类型命名空间不保存运行时对象 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `LinearElasticParams` 等参数类 | type[`MaterialParameters`] | 类命名空间 | 只读 | 内部维护 | 通过具体参数类构造材料参数对象 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `create_material(parameters)` | `torchfea.materials.Materials_Base` | - | 根据 `MaterialParameters` 创建并返回 TorchFEA 本构对象 |

#### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类型命名空间不设置内部实例方法 |

### 6.3 `MaterialParameters`

`MaterialParameters` 是所有本构参数对象的基类。参数对象只保存模型定义字段；
运行时本构由 `BaseMaterialInterface` 持有，并通过 `MaterialModels.create_material()` 创建。

#### 构造属性（`__init__()` 记录）

每个具体参数类声明本构模型所需字段。字段使用类型化构造参数记录，参数对象使用
只读属性向材料接口提供稳定定义。

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 参数对象不保存运行时本构对象 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.Materials_Base`] | 具体参数类 | 只读 | 内部维护 | 对应 TorchFEA 本构类 |
| 具体参数字段 | float 或 list[float] | 具体参数类 | 只读 | 通过替换参数对象修改 | 本构模型参数 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 具体材料接口通过 `MaterialModels.create_material()` 建立运行时本构 |

#### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_collect_parameters()` | dict[str, object] | 收集传递给 TorchFEA 本构构造函数的字段 |

#### 6.3.1 `LinearElasticParams`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `E` | float | 构造函数必填 | 杨氏模量 |
| `nu` | float | 构造函数必填 | 泊松比 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 不新增运行时属性 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.LinearElastic`] | `MaterialParameters` | 只读 | 内部维护 | 对应 TorchFEA 线弹性本构类 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 复用 `MaterialParameters` 的材料构建接口 |

##### 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 不新增内部辅助方法 |

#### 6.3.2 `NeoHookeanParams`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `mu` | float | 构造函数必填 | 剪切参数 |
| `kappa` | float | 构造函数必填 | 体积参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 不新增运行时属性 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.NeoHookean`] | `MaterialParameters` | 只读 | 内部维护 | 对应 TorchFEA Neo-Hookean 本构类 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 复用 `MaterialParameters` 的材料构建接口 |

##### 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 不新增内部辅助方法 |

#### 6.3.3 `NeoHookeanLnJParams`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `mu` | float | 构造函数必填 | 剪切参数 |
| `kappa` | float | 构造函数必填 | 体积参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 不新增运行时属性 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.NeoHookeanLnJ`] | `MaterialParameters` | 只读 | 内部维护 | 对应 TorchFEA `ln J` Neo-Hookean 本构类 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 复用 `MaterialParameters` 的材料构建接口 |

##### 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 不新增内部辅助方法 |

#### 6.3.4 `MooneyRivlinParams`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `c10` | float | 构造函数必填 | Mooney-Rivlin 参数 |
| `c01` | float | 构造函数必填 | Mooney-Rivlin 参数 |
| `kappa` | float | 构造函数必填 | 体积参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 不新增运行时属性 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.MooneyRivlin`] | `MaterialParameters` | 只读 | 内部维护 | 对应 TorchFEA Mooney-Rivlin 本构类 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 复用 `MaterialParameters` 的材料构建接口 |

##### 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 不新增内部辅助方法 |

#### 6.3.5 `YeohParams`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `c1` | float | 构造函数必填 | Yeoh 参数 |
| `c2` | float | 构造函数必填 | Yeoh 参数 |
| `c3` | float | 构造函数必填 | Yeoh 参数 |
| `kappa` | float | 构造函数必填 | 体积参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 不新增运行时属性 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.Yeoh`] | `MaterialParameters` | 只读 | 内部维护 | 对应 TorchFEA Yeoh 本构类 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 复用 `MaterialParameters` 的材料构建接口 |

##### 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 不新增内部辅助方法 |

#### 6.3.6 `GentParams`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `mu` | float | 构造函数必填 | 剪切参数 |
| `Jm` | float | 构造函数必填 | 极限链伸长参数 |
| `kappa` | float | 构造函数必填 | 体积参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 不新增运行时属性 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.Gent`] | `MaterialParameters` | 只读 | 内部维护 | 对应 TorchFEA Gent 本构类 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 复用 `MaterialParameters` 的材料构建接口 |

##### 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 不新增内部辅助方法 |

#### 6.3.7 `ArrudaBoyceParams`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `mu` | float | 构造函数必填 | 剪切参数 |
| `N` | float | 构造函数必填 | 链段数量参数 |
| `kappa` | float | 构造函数必填 | 体积参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 不新增运行时属性 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.ArrudaBoyce`] | `MaterialParameters` | 只读 | 内部维护 | 对应 TorchFEA Arruda-Boyce 本构类 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 复用 `MaterialParameters` 的材料构建接口 |

##### 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 不新增内部辅助方法 |

#### 6.3.8 `OgdenParams`

##### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `mu` | float 或 list[float] | 构造函数必填 | 剪切参数 |
| `alpha` | float 或 list[float] | 构造函数必填 | Ogden 指数参数 |
| `kappa` | float | 构造函数必填 | 体积参数 |

##### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 不新增运行时属性 |

##### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `material_class` | type[`torchfea.materials.Ogden`] | `MaterialParameters` | 只读 | 内部维护 | 对应 TorchFEA Ogden 本构类 |

##### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 复用 `MaterialParameters` 的材料构建接口 |

##### 内部辅助方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 不新增内部辅助方法 |

### 6.4 `BaseMaterialInterface`

`BaseMaterialInterface` 是材料接口基类，统一保存材料名称、目标 `Part`、目标元素族、
密度、本构参数和运行时材料对象。它显式继承 `Visualizable`、`Initializable`、
`Updatable` 和 `Persistable` 协议。
运行时本构对象统一写入 `_torchfea_<MaterialClass>`，其中 `<MaterialClass>` 是
实际 TorchFEA 本构类的 PascalCase 类名（例如 `LinearElastic`）；材料接口在
`reinitialize(iteration, assembly)` 中缓存 Assembly 到 `_torchfea_Assembly`，并缓存目标元素；后续 `assign_material()` 与
`update_assembly(design_delta)` 直接使用这些缓存。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_name` | str | 注册时写入 | 材料名称 |
| `_part_name` | str | 构造函数必填 | 目标 `Part` 名称 |
| `_element_name` | str | 构造函数必填 | 目标元素族名称；一个材料对象对应一个元素类型 |
| `_density` | float | 0.0 | 材料密度 |
| `_material_parameters` | `MaterialParameters` | 构造函数必填 | 本构参数对象 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_torchfea_Assembly` | `torchfea.Assembly` 或 None | None | `reinitialize()` 绑定的当前 Assembly |
| `_target_elements` | tuple[object, ...] | `()` | 当前 `Assembly` 中解析的目标元素 |
| `_torchfea_<MaterialClass>` | object 或 None | None | 已创建的具体 TorchFEA 材料对象；字段名中的 `<MaterialClass>` 取后端类名 |
| `_design_delta` | torch.Tensor 或 None | None | 当前材料设计增量 |
| `_meshes` | tuple[object, ...] | `()` | 已建立的材料预览网格 |
| `_initialized` | bool | False | 生命周期状态 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `name` | str | - | 只读 | 内部维护 | 返回材料注册名称 |
| `part_name` | str | - | 只读 | 内部维护 | 返回目标 `Part` 名称 |
| `element_name` | str | - | 只读 | 内部维护 | 返回目标元素族 |
| `density` | float | - | 只读 | 读写 | 返回或修改材料密度 |
| `material_parameters` | `MaterialParameters` | - | 只读 | 内部维护 | 返回本构参数对象 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `initialize()` | None | `Initializable` | 建立材料接口的静态运行结构 |
| `reinitialize(iteration, assembly)` | None | `Initializable` | 更新当前迭代的目标元素和映射 |
| `build_material()` | None | - | 创建运行时材料对象并写入 `_torchfea_<MaterialClass>` |
| `get_material()` | object | - | 读取已经创建的运行时材料对象 |
| `assign_material()` | None | - | 使用已缓存的目标元素和 Assembly 引用写入已创建材料 |
| `get_design_values()` | torch.Tensor | `Updatable` | 读取带计算图的当前设计值 |
| `get_parameters()` | list[torch.Tensor] | `Updatable` | 读取设计参数的 detached clone |
| `set_parameters(parameters)` | None | `Updatable` | 修改已有设计参数 |
| `build_design_delta()` | None | `Updatable` | 建立并保存设计增量 |
| `get_design_delta()` | torch.Tensor | `Updatable` | 读取已建立的设计增量 |
| `update_assembly(design_delta)` | None | `Updatable` | 使用自身的 TorchFEA 材料和 Assembly 引用更新试探材料状态 |
| `apply_design_delta(design_delta)` | None | `Updatable` | 提交材料设计增量 |
| `build_meshes()` | None | `Visualizable` | 建立材料预览网格并写入 `_meshes` |
| `get_meshes()` | list[object] | `Visualizable` | 读取已经建立的预览网格 |
| `plot(plotter, meshes)` | object | `Visualizable` | 使用已有网格绘制材料状态 |
| `save(foldpath, iteration)` | None | `Persistable` | 保存材料状态 |
| `load(foldpath, iteration)` | None | `Persistable` | 加载材料状态 |

#### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_resolve_target_elements(assembly)` | tuple[object, ...] | 解析指定 `Part` 中的目标元素族 |
| `_cache_target_elements()` | None | 保存当前目标元素缓存 |
| `_build_preview_mesh()` | None | 创建并保存材料预览网格 |

### 6.5 `HomogeneousMaterial`

`HomogeneousMaterial` 为目标元素族提供固定的均匀本构和密度。它继承
`BaseMaterialInterface` 的名称、目标、参数、生命周期、材料构建和预览接口。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| 空 | - | - | 直接使用 `BaseMaterialInterface` 的构造属性 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 直接使用 `BaseMaterialInterface` 的运行时状态 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| 空 | - | - | - | - | 直接使用 `BaseMaterialInterface` 的 property |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 直接使用 `BaseMaterialInterface` 的外部接口 |

#### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类型直接使用基类实现 |

### 6.6 `SIMPFieldMaterial`

`SIMPFieldMaterial` 使用三维 BSP 材料场，根据设计场计算材料比例，并将材料比例和
可选惩罚因子写入目标元素。它继承 `BaseMaterialInterface` 的材料注册、生命周期、
设计变量、预览和持久化接口。

#### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_mumax` | float | 构造函数必填 | 最大剪切材料参数 |
| `_kappamax` | float | 构造函数必填 | 最大体积材料参数 |
| `_initial_ratio` | float | 0.5 | 初始材料比例 |
| `_simp_ratio_min` | float | 构造函数必填 | 材料比例下限 |
| `_bounding_box` | tuple[float, ...] | 构造函数必填 | 三维材料场区域 |
| `_simp_field_resolution` | float | 构造函数必填 | 材料场采样分辨率 |
| `_degree` | int | 构造函数必填 | BSP 阶数 |
| `_void_penalty_factor` | float | 1e-2 | 空材料惩罚系数 |
| `_material_penalty` | int | 8 | 材料比例惩罚阶数 |

#### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_simp_field` | object 或 None | None | 三维 BSP 材料场后端 |
| `_control_points` | torch.Tensor 或 None | None | 当前材料场控制点 |
| `_bsp_size` | tuple[int, ...] 或 None | None | 材料场控制点尺寸 |
| `_element_map` | object 或 None | None | 材料场到元素积分点的映射缓存 |
| `_material_ratio` | torch.Tensor 或 None | None | 当前材料比例缓存 |
| `_penalty_factor` | torch.Tensor 或 None | None | 当前惩罚因子缓存 |

#### 属性接口（property）

| property | 类型 | 来源 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|---|
| `mumax` | float | - | 只读 | 内部维护 | 返回最大材料参数 |
| `kappamax` | float | - | 只读 | 内部维护 | 返回最大体积参数 |
| `initial_ratio` | float | - | 只读 | 内部维护 | 返回初始材料比例 |
| `simp_ratio_min` | float | - | 只读 | 内部维护 | 返回材料比例下限 |
| `bounding_box` | tuple[float, ...] | - | 只读 | 内部维护 | 返回材料场区域 |
| `simp_field_resolution` | float | - | 只读 | 内部维护 | 返回材料场分辨率 |
| `degree` | int | - | 只读 | 内部维护 | 返回 BSP 阶数 |
| `void_penalty_factor` | float | - | 只读 | 读写 | 返回或修改空材料惩罚系数 |
| `material_penalty` | int | - | 只读 | 读写 | 返回或修改材料比例惩罚阶数 |
| `use_simp_penalty` | bool | - | 只读 | 内部维护 | 返回当前 SIMP 惩罚开关 |

#### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `get_control_points_list()` | list[torch.Tensor] | - | 读取已经建立的材料场控制点 |
| `compute_material_ratio(design_field)` | torch.Tensor | - | 根据设计场计算材料比例 |
| `compute_penalty_factor(design_field)` | torch.Tensor | - | 根据设计场计算惩罚因子 |
| `get_parameters()` | list[torch.Tensor] | `Updatable` | 读取材料场控制点的 detached clone |
| `set_parameters(parameters)` | None | `Updatable` | 修改材料场控制点 |
| `build_design_delta()` | None | `Updatable` | 建立并保存材料场设计增量 |
| `get_design_delta()` | torch.Tensor | `Updatable` | 读取已经建立的材料场设计增量 |
| `update_assembly(design_delta)` | None | `Updatable` | 使用自身的 TorchFEA 材料和 Assembly 引用更新试探材料场 |
| `apply_design_delta(design_delta)` | None | `Updatable` | 提交材料场设计增量 |

#### 内部辅助方法

| 方法 | 返回值 | 作用 |
|---|---|---|
| `_get_indices_weight_for_nodes(nodes)` | tuple[torch.Tensor, torch.Tensor] | 建立节点到材料场控制点的映射 |
| `_map_design_field(nodes)` | torch.Tensor | 将材料场控制点映射到节点或积分点 |
| `_map_design_field_with_spatial_derivative(nodes)` | torch.Tensor | 计算带空间导数的材料场映射 |
| `_prepare_elements(elements)` | object | 根据惩罚配置准备元素适配器 |
| `_set_element_material(elements, nodes)` | None | 将当前材料场写入一个元素族 |

`compute_material_ratio()` 和 `compute_penalty_factor()` 是显式计算接口；材料比例、
惩罚因子和预览网格由 `reinitialize()`、`update_assembly()` 或 `build_meshes()` 写入，
`get_*` 方法只读取已经建立的结果。
