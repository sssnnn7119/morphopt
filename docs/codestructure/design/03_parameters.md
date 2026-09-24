# 03. 参数集合

返回 [设计导览](../README.md)。

## 统一注册模型

源码目录：`optcore/modelparams/`。参数集合以 `interfaces: dict[str, object]` 保存自己拥有的接口。字典键是接口的公开名称，同时给出稳定注册顺序；接口对象保存业务状态，集合对象负责批量生命周期、持久化和设计变量拼接。

```text
Params
├── geometry: GeometryParams  ──► Part interfaces
├── feamodel: FEAParams       ──► FEA interfaces + load steps
└── materials: MaterialsParams──► Material interfaces
```

## `BaseParams`

源码：`baseparam.py`；继承 `ProtocalInitializable`、`ProtocalSavable`、`ProtocalVisualizable`。

| 属性 | 可见性 | 说明 |
|---|---|---|
| `interfaces` | 公开 | 名称到已拥有接口的有序字典。 |
| `num_interfaces` | 公开属性 | 已注册接口数量。 |

| 公开方法 | 职责 |
|---|---|
| `add_interface(interface, name=None)` | 注册接口并返回最终名称；完成唯一性检查。 |
| `define_interface()` | 用户覆写的声明钩子。 |
| `initialize()` | 调用一次 `define_interface()`，随后初始化所有已注册接口。 |
| `reinitialize(iteration)` | 向所有接口转发每轮刷新。 |
| `interface(name)` | 以注册名取得接口对象。 |
| `design_interfaces()` | 选出实现 `ProtocalUpdatable` 的接口。 |
| `obtain_design_sensitivity_vars(assembly)` | 按注册顺序拼接各可更新接口的设计值。 |
| `modify_assembly(values, assembly)` | 按变量块切分试探值并转发给各接口。 |
| `get_meshes()` / `plot(...)` | 聚合各接口的预览能力。 |
| `export_data(foldpath)` | 向各接口转发导出。 |
| `save(foldpath, iteration)` / `load(...)` | 向各接口转发持久化。 |

`add_interface()` 是集合内名称的唯一写入口。声明钩子在 `initialize()` 时运行一次，实例构造阶段保持轻量。集合转发采用接口对象而非接口名进行运行时调用；名称用于注册、持久化目录和脚本序列化。

## `Params`

源码：`params.py`；继承三个基础协议。它是一次分析模型的根参数对象。

| 属性 | 说明 |
|---|---|
| `geometry` | `GeometryParams`，提供 Part 和实例装配。 |
| `feamodel` | `FEAParams`，提供载荷、边界条件、接触和载荷步。 |
| `materials` | `MaterialsParams`，提供材料分配。 |

| 公开方法 | 职责 |
|---|---|
| `initialize()` / `reinitialize(iteration)` | 按 Geometry、FEA、Materials 顺序转发生命周期。 |
| `create_feamodel(path_result=None, pools=None)` | 生成 Assembly，创建 FEAController，设置材料并初始化。 |
| `obtain_design_sensitivity_vars(assembly)` | 返回每个设计集合的灵敏度输入。 |
| `modify_assembly(design_sensitivity_vars, assembly)` | 将设计试探值写到对应集合。 |
| `save/load/export_data` | 管理全部参数集合的持久化与导出。 |
| `get_meshes/plot` | 聚合模型预览。 |

`create_feamodel()` 是从声明参数进入数值后端的唯一组装点：先由 Geometry 生成 Assembly，再由 FEAParams 加载 FEA 定义，最后由 MaterialsParams 把材料赋给元素。

## `GeometryParams`

源码：`geometry.py`；继承 `BaseParams`。

| 公开成员 | 职责 |
|---|---|
| `instance_names()` | 汇总所有 Part 接口产生的 Assembly instance 名称。 |
| `generate(path_result, pools=None)` | 创建 `torchfea.Assembly`，依次调用每个 Part 接口的 `add_to_assembly()`。 |
| `export_data(foldpath)` | 导出几何接口数据。 |
| `pathlog_required()` | 声明 geometry 状态日志目录。 |

## `FEAParams`

源码：`feaparams.py`；继承 `BaseParams`。

| 状态 | 说明 |
|---|---|
| `interfaces` | 载荷、边界、接触、参考点等 FEA 接口。 |
| `fea_steps_params` | 每个载荷步的接口数值覆盖字典。 |
| `num_load_steps` | 载荷步数量。 |

| 公开方法 | 职责 |
|---|---|
| `define_steps()` | 用户声明载荷步的钩子。 |
| `set_step_num(num_steps)` | 设置载荷步数并建立步参数容器。 |
| `set_step_params(step, name, values)` | 设置某步对一个可数值控制 FEA 接口的值。 |
| `create_fea(assembly)` | 创建并填充 `torchfea.FEAController`。 |
| `process_fea(fe, step_index)` | 将给定载荷步的覆盖值应用到 FEA 对象。 |

## `MaterialsParams`

源码：`materials.py`；继承 `BaseParams`。

`set_materials(fe)` 按注册顺序调用每个材料接口的材料分配逻辑；`pathlog_required()` 为材料设计状态声明独立日志目录。材料类型与每种材料的参数模型见 [06 材料](06_materials.md)。

## 设计变量数据流

```text
可更新 Part / 材料接口
      │ obtain_design_sensitivity_vars(assembly)
      ▼
BaseParams.obtain_design_sensitivity_vars()  [注册顺序拼接]
      ▼
ObjectiveFunction.sensitivity_analysis()
      ▼
Updaters.update() [按目标接口变量数切片]
      ▼
ProtocalUpdatable.update_variables()
```

每个可更新接口必须让 `num_variables`、`get_parameters()`、灵敏度变量和 `update_variables()` 使用相同的展平顺序。该顺序同时是梯度切片契约和保存/重启状态的语义基础。
