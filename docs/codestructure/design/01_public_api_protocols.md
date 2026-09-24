# 01. 顶层 API 与协议

返回 [设计导览](../README.md)。

## 顶层 `morphopt` 命名空间

`src/morphopt/__init__.py` 是用户脚本唯一要求的公共导入面。

| 分类 | 公开对象 | 实现归属 |
|---|---|---|
| 运行时 | `Controller`, `History`, `Solver`, `ObjectiveFunction`, `Updaters` | `optcore` |
| 参数集合 | `Params`, `GeometryParams`, `FEAParams`, `MaterialsParams` | `optcore.modelparams` |
| 几何 | `BasePartInterface`, `INPPartInterface`, `TorchFEAPartInterface` | `optcore.modelparams.partinterface` |
| 材料 | `HomogeneousMaterial` | `optcore.modelparams.materialinterface` |
| 形状扩展 | `BoundaryPartInterface`, `UpdaterBoundaryPart` | `shapeopt` |
| SIMP 扩展 | `SIMP_BSPFieldMaterials`, `UpdaterSIMPMaterial` | `simp` |
| 运行工具 | `start_optimization`, `debug_optimization`, `check_gradients`, `get_controller` | runner / utils |
| 路径工具 | `resolve_model_path`, `load_model_assembly` | Part 导入接口 |

`shapeopt.__all__` 导出边界 Part 和形状更新器；`simp.__all__` 导出 SIMP 材料和材料更新器。`Params`、`Solver`、`ObjectiveFunction` 和 `Updaters` 始终从顶层 `morphopt` 导入。

## 协议继承图

```text
ProtocalInitializable ─┬─ BaseParams ───────────┬─ GeometryParams / FEAParams / MaterialsParams
                       │                         ├─ BasePartInterface
                       │                         └─ BaseMaterialInterface
                       ├─ BaseFEAInterface
                       ├─ Solver / ObjectiveFunction / BaseUpdater / Updaters / History
                       └─ Controller orchestration (非协议子类)

ProtocalSavable ───────┘
ProtocalVisualizable ──► BaseParams / BaseFEAInterface / Surface 接口
ProtocalUpdatable ─────► BoundaryPartInterface / SIMP_BSPFieldMaterials
```

类名中的 `Protocal` 是当前公开拼写；新增代码沿用该拼写，使协议名称保持单一、稳定。

## `ProtocalInitializable`

源码：`optcore/protocal.py`。

| 公开方法 | 语义 |
|---|---|
| `initialize(*args, **kwargs)` | 优化开始前建立声明或运行时状态；默认空实现。 |
| `reinitialize(iteration, *args, **kwargs)` | 每轮开始前刷新状态；默认空实现。 |

该协议允许没有特殊初始化的类不覆写空方法。定义构造函数的多继承类必须 cooperative：调用 `super().__init__()`，以保证协议链和其他父类都有机会初始化。

## `ProtocalSavable`

| 公开方法 | 语义 |
|---|---|
| `save(foldpath, iteration)` | 保存自身状态；默认空实现。 |
| `load(foldpath, iteration)` | 恢复自身状态；默认空实现。 |
| `pathlog_required()` | 返回需要的 `log/` 子目录；默认 `[]`。 |
| `save_directory(foldpath, name=None)` | 用第一个 log 子目录创建并返回命名空间目录。 |

`save_directory()` 是所有会写入命名状态的对象的统一路径工具；调用者必须覆写 `pathlog_required()`，否则会显式报错。

## `ProtocalVisualizable`

| 公开方法 | 语义 |
|---|---|
| `get_meshes()` | 返回该对象贡献的 `pyvista.DataSet` 列表；默认空列表。 |
| `plot(plotter=None, meshes=None)` | 向 PyVista plotter 添加自身；默认只保证返回 plotter。 |

预览是可选能力。拥有几何数据的接口返回相应网格；其余 FEA 接口保留默认空列表。

## `ProtocalUpdatable`

该协议定义“能作为一个局部优化器目标”的最小面：

| 公开属性或方法 | 语义 |
|---|---|
| `num_variables` | 标量设计变量数。 |
| `get_parameters()` / `set_parameters(values)` | 获取与恢复参数张量列表。 |
| `get_variables()` | 产生局部优化器的初始微扰变量；协议提供默认实现。 |
| `update_variables(x_change, max_step_length=None)` | 应用一次受步长约束的设计更新。 |
| `obtain_design_sensitivity_vars(assembly)` | 提供灵敏度分析使用的活跃设计值。 |
| `modify_assembly(design_sensitivity_vars, assembly)` | 把试探设计值投影到当前 Assembly。 |

`BaseParams.design_interfaces()` 只选择实现此协议的接口。形状 Part 与 SIMP 材料共享这个抽象；载荷和均质材料不被误纳入设计变量拼接。
