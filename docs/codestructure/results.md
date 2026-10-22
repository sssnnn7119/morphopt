# 结果分析与导出

[代码结构导览](README.md) · [运行归档](runtime.md) · [UI 应用服务](ui-application.md) · [UI 展示](ui-presentation.md)

## 目录

<!-- docs:toc depth=1 -->

- [1 源码入口](#section-源码入口)
- [2 优化结果读取](#section-优化结果读取)
- [3 共享选择与页面生命周期](#selection)
- [4 私有模型与独立有限元](#section-私有模型与独立有限元)
- [5 分析结果快照](#section-分析结果快照)
- [6 场量计算与云图投影](#section-场量计算与云图投影)
- [7 物理量与格式注册](#section-物理量与格式注册)
- [8 CSV 与 NPZ 单文件导出](#section-csv-与-npz-单文件导出)
- [9 原生模型与全部结果导出](#section-原生模型与全部结果导出)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 源码入口

| 路径 | 主要对象与责任 |
|---|---|
| [`ui/application/results.py`](../../src/morphopt/ui/application/results.py) | `ResultSession`、`ResultSelection` 与已完成迭代查询 |
| [`ui/application/finite_element.py`](../../src/morphopt/ui/application/finite_element.py) | `IterationModel`、`FiniteElementSession`、`FiniteElementResult` |
| [`ui/application/result_fields.py`](../../src/morphopt/ui/application/result_fields.py) | `DisplayField`、`ResultContours` 与云图投影 |
| [`ui/fea_worker.py`](../../src/morphopt/ui/fea_worker.py) | 独立求解及导出工作进程 |
| [`ui/widgets/finite_element.py`](../../src/morphopt/ui/widgets/finite_element.py) | 结果/工况选择、载荷编辑、QProcess 与显示 |
| [`ui/widgets/observation_pages.py`](../../src/morphopt/ui/widgets/observation_pages.py) | 历史、设计与变形页面 |
| [`postprocess/fields.py`](../../src/morphopt/postprocess/fields.py) | 场量提供者、记录位置与组合表 |
| [`postprocess/exporters.py`](../../src/morphopt/postprocess/exporters.py) | CSV/NPZ 单文件导出 |
| [`postprocess/native.py`](../../src/morphopt/postprocess/native.py) | 原生 TorchFEA 模型与结果归档 |

<a id="section-优化结果读取"></a>

## 2 优化结果读取

`ResultSession` 绑定一个运行目录，持有读取该目录的控制器、历史与参数缓存。`load_iteration()` 和 `load_parameters()` 为所选迭代准备状态，`deformation_cases()` 与 `deformation_mesh()` 提供工况和变形数据。

| 读取内容 | 来源 |
|---|---|
| 控制器结构 | `scripts/MAIN_SCRIPT_FOR_RESTART.py` |
| 迭代损失与指标 | `log/history_record.csv` |
| 可更新几何与材料 | 参数接口保存状态 |
| 确切有限元模型 | `log/femodel&results/femodel_<iteration>.npz` |
| 工况解 | `result_<case>_iter_<iteration>.npz` |

观察页消费会话数据，不自行扫描和解析上述文件。设计参数展示与有限元归档展示是不同读取路径；有限元分析采用该轮保存的实际网格，不以当前参数重建的网格替代。

<a id="selection"></a>

## 3 共享选择与页面生命周期

`MainWindow` 用不可变 `ResultSelection(folder, iteration)` 协调观察页和有限元页。两处选择通过信号同步，目录与迭代是展示状态，FE 模型仍分别持有。

- 进入有限元分析时固定当前迭代，停止观察页的自动跟踪。
- 有限元任务运行时锁定共享迭代选择，后台优化可继续产生新归档。
- 新归档更新可选范围，不替换正在独立求解的快照。
- 切页保留运行、载荷修改和分析选择，不重新启动进程。
- 只有存在对应轮次模型时，才能建立该轮独立有限元工作区。

观察会话每次轮询后通过 `resultsUpdated` 通知主窗口重新检查所选目录和迭代的模型可用性；迭代编号未变化时，模型文件落盘也会更新有限元入口。新优化开始时清空旧的共享选择，首次选择新任务归档后，有限元页按该目录及迭代导入模型。

原工况名称与下拉框行号分开记录；原始结果和独立分析结果由显式来源对象区分。

<a id="section-私有模型与独立有限元"></a>

## 4 私有模型与独立有限元

```text
IterationModel(folder, iteration, case)
  → FiniteElementSession.select_result()
  → 读取确切模型、恢复工况、校验模型哈希
  → 私有载荷编辑 → solve_request()
  → QProcess 执行 fea_worker
  → accept_solution() 校验并保存独立快照
```

`FiniteElementSession` 不共享优化运行的可修改模型。`apply_loads()` 先校验全部编辑，再应用参数，并将旧解置为失效。界面保留原工况的启用状态，不额外提供一套启用开关。

`solve_request()` 将私有模型和请求写入会话工作目录；Qt 页面仅管理 QProcess 的事件、输出与状态。`fea_worker` 不创建 Qt 控件，完成独立的求解或导出操作。

`select_result()` 恢复解的 `work_conditions` 后校验模型哈希，未收敛的解不作为有效场结果。停止或失败保留已导入模型，不发布新的成功结果。

<a id="section-分析结果快照"></a>

## 5 分析结果快照

`FiniteElementResult` 保存稳定 key、来源目录/轮次/工况、模型路径、结果路径、分析编号、时间及日志。`accept_solution()` 校验成功解与模型，复制模型、解和日志后才追加到选择列表。

同一会话中的成功分析记录与原工况共同列出，按来源目录和迭代筛选。切换条目从其快照重建私有模型，继续编辑不会修改既有记录。

独立快照由 `TemporaryDirectory` 管理，不回写原优化归档，也不属于 `.morph`。会话关闭后工作目录清理，长期保存通过显式导出完成。

<a id="section-场量计算与云图投影"></a>

## 6 场量计算与云图投影

`postprocess.fields.FieldContext` 从已配对模型和解准备节点、参考点、单元块及高斯点上下文。云图与数据导出共享 `gauss_values()` 的物理计算。

| 物理量 | 约定 |
|---|---|
| 节点位移与坐标 | 装配体全局坐标轴 |
| RP 运动 | 解转换后的 RGC 块，六分量为平移与旋转向量 |
| RP 转角 | 全局轴角向量，单位 rad，不转换为欧拉角 |
| 应力 | Cauchy 应力，全局坐标轴 |
| 应变 | Green–Lagrange 张量应变，剪切为张量分量 |
| 应变能 | 高斯点能量密度、参考积分体积及积分能量 |

`ResultContours` 按解缓存物理量。应力、应变和能量密度先按参考积分体积求单元平均，再对相邻单元做节点平均。该投影用于云图，不是节点应力外推；导出保留逐高斯点值。

缺少支持数据的节点使用 NaN，无高斯点的模型只提供适用的位移等量。切换结果替换缓存，编辑载荷清除旧解与旧场量。相机、变形倍率和显示分量不改变物理结果。

<a id="section-物理量与格式注册"></a>

## 7 物理量与格式注册

| 抽象 | 责任 |
|---|---|
| `ResultLocation` | 节点、参考点或单元记录位置 |
| `ResultField`、`RESULT_FIELDS` | 量的稳定 key、描述、位置、提取器与可用性 |
| `ResultTable` | 列名与逐行记录 |
| `combined_table()` | 按稳定记录编号合并所选物理量 |
| `ResultExporter`、`EXPORTERS` | 写入指定格式的组合表 |

每次表格导出选择一种位置，多个物理量横向组合为一张表。单元位置的记录可携带积分点编号；混合单元中不支持高斯点量的记录保留空值，不能伪造积分点或零应力。

节点、单元及积分点编号从 1 开始，保留实例和单元块名称。参考点有独立编号和名称，每个 RP 一行，禁用 RP 不输出。

新增物理量注册 `ResultField`，新增文件格式实现 `ResultExporter`，两条扩展路径互不复制计算逻辑。UI 从注册表取得可选项。

<a id="section-csv-与-npz-单文件导出"></a>

## 8 CSV 与 NPZ 单文件导出

`export_results()` 检查收敛状态、模型哈希、记录位置与字段可用性，再生成组合表。

| 格式 | 文件内容 |
|---|---|
| CSV | UTF-8 BOM，首行为列名，随后为记录 |
| NPZ | 每列一个数组，`__metadata__` 保存来源、单位、坐标系和模型哈希等信息 |

物理提取与写入先在临时文件中完成，成功后发布目标文件。未允许覆盖时不替换已有文件；求值或写入失败清理本次临时产物。覆盖确认由展示层的共用保存对话框提供，数值服务通过 `overwrite` 接收明确的写入选项。

<a id="section-原生模型与全部结果导出"></a>

## 9 原生模型与全部结果导出

`native_export_request()` 固定所选迭代的原模型、全部原工况与会话内成功分析清单，`export_native_results()` 直接复制原生 NPZ。尚未求解的载荷编辑不进入该清单。

```text
<用户前缀>/
├── <前缀>_femodel.npz
├── <前缀>_case0.npz
├── <前缀>_analysis1.npz
└── <前缀>_manifest.json
```

一份迭代模型与各结果共用，结果各自保存 `work_conditions`。载入后先恢复所选结果的工况，再检查配对。目录重名时生成新编号目录；本次导出失败只清理本次新建目录。

原生模型通过 `torchfea.load_model()` 读取，解通过 `StaticResult.load()` 读取。原生归档、单表物理量导出和 CAD STEP 几何导出分别保留各自格式与数据范围。
