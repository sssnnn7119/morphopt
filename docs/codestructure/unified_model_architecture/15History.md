# MorphOpt V4 History 运行记录

本文件定义独立的 `History` 运行记录对象。`History` 记录优化迭代产生的目标值、指标、
收敛信息、耗时和结果路径，由 `Controller` 持有并调度。返回[总入口](../unified_model_architecture_plan.md)。

## 文档导航与输入/输出摘要

本文说明历史记录的字段、读取接口、持久化接口和与 Controller 的协作关系。

### 目录

- [15. History](#15-history)
- [15.1 与 Controller 的协作](#151-与-controller-的协作)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | iteration、目标值、metrics、收敛信息、耗时和结果路径 |
| 输出 | 历史记录、指标序列、结果目录索引和持久化文件 |
| 主要读者 | Controller、ObjectiveFunction、Observer、结果导出和测试实现者 |
| 关联文档 | [Params、Controller 与主循环](13-14Runtime.md)、[目标函数](09Objective.md)、[UI 与 Codegen](16-17UiCodegen.md) |

## 15. `History`

`History` 与 `Params`、`Controller`、`ObjectiveFunction` 保持并列关系。它只负责保存和
读取运行记录，记录内容按照 iteration 顺序组织。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_result_root` | str 或 None | None | 结果文件的根目录配置 |
| `_metric_names` | tuple[str, ...] | () | 需要记录的指标名称 |

### 运行时属性（`__init__()` 声明，`initialize()` 填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_records` | list[dict[str, object]] | [] | 按 iteration 保存的历史记录 |
| `_result_paths` | dict[int, str] | {} | iteration 到结果目录的映射 |
| `_initialized` | bool | False | 初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `result_root` | str 或 None | 只读 | 内部维护 | 返回结果根目录 |
| `metric_names` | tuple[str, ...] | 只读 | 内部维护 | 返回指标名称 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_record(iteration, metrics)` | None | - | 向历史记录列表添加一次 iteration 记录 |
| `get_metrics()` | list[dict[str, object]] | - | 读取全部历史指标 |
| `get_records()` | tuple[Mapping[str, object], ...] | - | 读取历史记录 |
| `get_result_paths()` | Mapping[int, str] | - | 读取 iteration 到结果目录的映射 |
| `save(foldpath, iteration)` | None | `Persistable` | 写入当前历史记录和结果索引 |
| `load(foldpath, iteration)` | None | `Persistable` | 读取指定 iteration 的历史记录 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 当前类未定义专用内部辅助函数 |

## 15.1 与 `Controller` 的协作

单次外层迭代由 `Controller.step()` 完成目标计算、灵敏度计算和 updater 更新后，调用
`History.add_record(iteration, metrics)` 写入本次记录。`Controller._opt_loop()` 负责调度
连续的 `step()`，并在每次返回后调用保存和停止判断；`Controller.save()` 和
`Controller.load()` 统一调度 `History` 的持久化接口。

~~~text
Controller._opt_loop()
    → Controller.step()
    → ObjectiveFunction / Updaters 产生当前结果
    → History.add_record(iteration, metrics)
    → History.save(foldpath, iteration)
~~~
