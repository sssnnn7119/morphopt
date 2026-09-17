# MorphOpt V4 History 运行记录

本文件定义独立的迭代记录、序列读取和日志持久化。返回[总入口](../design.md)。

## 文档导航与输入/输出摘要

`HistoryRecord` 保存一次完整迭代的不可变摘要；`History` 是这些记录的唯一事实来源。
Controller 在 `step()` 成功完成后追加记录并写入运行目录的 `logs/`，Observer 和重启流程
解析同一份日志数据。模型 checkpoint 只保存恢复计算所需的状态，不复制历史记录。

### 目录

- [15.1 `HistoryRecord`](#151-historyrecord)
- [15.2 `History`](#152-history)
- [15.3 与 Controller 和 Observer 的协作](#153-与-controller-和-observer-的协作)

### 输入与输出

| 项目 | 内容 |
|---|---|
| 输入 | 目标、逐工况指标、阶段耗时、网格规模、最大变形、收敛状态、结果路径和 updater 摘要 |
| 输出 | 有序迭代记录、命名序列、重启索引以及 `logs/history.json`/`logs/history.csv` 历史文件 |
| 主要读者 | Controller、ObjectiveFunction、Observer、结果导出和测试实现者 |
| 关联文档 | [运行时](13_14_runtime.md)、[目标函数](09_objective.md)、[UI 与 Codegen](16_17_ui_codegen.md) |

## 15.1 `HistoryRecord`

`HistoryRecord` 是冻结 `dataclass`，记录一次已提交迭代。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_iteration` | int | - | 从 0 开始的迭代索引 |
| `_objective` | float | - | detached 标量目标 |
| `_metrics_by_case` | tuple[tuple[float, ...], ...] | - | 按工况和指标名称排列的展示指标 |
| `_phase_times` | Mapping[str, float] | - | geometry、FEA、objective、sensitivity、update、total 阶段耗时 |
| `_num_elements` | int | - | 当前 Assembly 单元总数 |
| `_num_nodes` | int | - | 当前 Assembly 节点总数 |
| `_maximum_deformation` | float | - | 所有工况节点位移范数最大值；由 `Controller._build_history_record()` 在导出本轮结果网格时取各工况变形后节点的位移范数最大值 |
| `_converged_by_case` | tuple[bool, ...] | - | 各工况收敛状态；取自各工况 `StaticResult` 的收敛标记 |
| `_result_path` | pathlib.Path | - | 本轮结果目录 |
| `_updater_summary` | Mapping[str, Mapping[str, float]] | `{}` | 各 updater 的步长、约束值和内层迭代摘要；取自各 updater 的优化器结果、步长上限向量与约束标量 |

### 运行时属性

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| 空 | - | - | 冻结记录仅保存构造状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `iteration` | int | 只读 | 内部维护 | 返回迭代索引 |
| `objective` | float | 只读 | 内部维护 | 返回目标值 |
| `metrics_by_case` | tuple[tuple[float, ...], ...] | 只读 | 内部维护 | 返回逐工况指标 |
| `phase_times` | Mapping[str, float] | 只读 | 内部维护 | 返回不可变耗时映射 |
| `num_elements` | int | 只读 | 内部维护 | 返回单元数量 |
| `num_nodes` | int | 只读 | 内部维护 | 返回节点数量 |
| `maximum_deformation` | float | 只读 | 内部维护 | 返回最大变形 |
| `converged_by_case` | tuple[bool, ...] | 只读 | 内部维护 | 返回工况收敛状态 |
| `result_path` | pathlib.Path | 只读 | 内部维护 | 返回结果目录 |
| `updater_summary` | Mapping[str, Mapping[str, float]] | 只读 | 内部维护 | 返回 updater 摘要的只读视图 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| 空 | - | - | 记录通过 property 读取 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| 空 | - | 冻结记录不定义内部辅助函数 |

## 15.2 `History`

`History` 实现 `Initializable` 和 `Persistable`，并维护连续、唯一的迭代序列；文件始终位于
运行目录的 `logs/`，不写入 checkpoint。

### 构造属性（`__init__()` 记录）

| 属性 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `_result_root` | pathlib.Path | - | 任务结果根目录 |
| `_metric_names` | tuple[str, ...] | `()` | 指标名称及稳定顺序 |

### 运行时属性（`__init__()` 声明，生命周期方法填充）

| 属性 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `_records` | list[`HistoryRecord`] | `[]` | 按 iteration 连续保存的记录 |
| `_record_by_iteration` | dict[int, `HistoryRecord`] | `{}` | 由 `_records` 同步维护的查找索引 |
| `_initialized` | bool | False | 目录和 schema 初始化状态 |

### 属性接口（property）

| property | 类型 | 读权限 | 写权限 | 说明 |
|---|---|---|---|---|
| `result_root` | pathlib.Path | 只读 | 内部维护 | 返回结果根目录 |
| `metric_names` | tuple[str, ...] | 只读 | 内部维护 | 返回指标名称 |
| `log_directory` | pathlib.Path | 只读 | 内部维护 | 返回 `<run_root>/logs` 历史日志目录 |

### 外部接口方法

| 方法 | 返回值 | 来源 | 作用 |
|---|---|---|---|
| `add_record(record)` | None | - | 校验迭代连续性后追加一条记录并更新索引 |
| `get_records()` | tuple[`HistoryRecord`, ...] | - | 读取全部记录 |
| `get_record(iteration)` | `HistoryRecord` | - | 按迭代索引读取一条记录 |
| `get_current_iteration()` | int 或 None | - | 读取最近完成的迭代；空历史返回 `None` |
| `get_series(name, case_index=None)` | tuple[float, ...] | - | 读取 objective、time、规模、变形或命名 metric 序列 |
| `get_result_paths()` | tuple[pathlib.Path, ...] | - | 按记录顺序读取结果目录 |
| `initialize()` | None | `Initializable` | 清空内存记录并标记 History 可用；结果目录由 Controller 创建 |
| `save(folder_path, iteration)` | None | `Persistable` | 原子写入 `logs/history.json` 与 `logs/history.csv`，`iteration` 仅用于调用方语义 |
| `load(folder_path, iteration)` | None | `Persistable` | 解析 `logs/history.json` 中截至指定 iteration 的记录并重建查找索引 |

### 内部辅助函数

| 函数 | 返回值 | 作用 |
|---|---|---|
| `_validate_record(record)` | None | 校验索引连续性、指标形状、有限值和结果路径 |
| `_serialize_record(record)` | dict[str, JsonValue] | 转换为版本化日志数据 |
| `_deserialize_record(data)` | `HistoryRecord` | 校验 schema 并恢复冻结记录 |
| `_write_atomic(path, data)` | None | 经同目录临时文件和替换完成原子写入 |
| `_write_csv_atomic(path)` | None | 经同目录临时文件和替换完成 CSV 写入 |

`get_series()` 支持以下稳定名称：`objective`、`total_time`、`num_elements`、`num_nodes`、
`maximum_deformation`，以及 `metric_names` 中的名称。metric 序列必须提供 `case_index`；
其余序列省略该参数。`_record_by_iteration` 是 `_records` 的派生索引，每次加载和追加都由
同一个内部入口同步维护。

## 15.3 与 `Controller` 和 Observer 的协作

```text
Controller._opt_loop()
    → step_result = Controller.step()
    → record = Controller._build_history_record(step_result)
    → History.add_record(record)
    → History.save(run_path)  # logs/history.json + logs/history.csv
    → Controller.save(iteration)
```

重启流程先解析运行目录 `logs/` 下的 `History`，以 `get_current_iteration() + 1` 作为下一次迭代。
Controller 在一次 `step()` 完整成功后提交记录；异常记录写入运行日志和任务状态文件。Observer 使用
`get_records()` 绘制总览曲线，使用 `get_series()` 绘制单个指标，并通过
`HistoryRecord.result_path` 定位每轮保存的模型与结果。
