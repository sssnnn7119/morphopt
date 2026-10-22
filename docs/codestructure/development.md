# 扩展与维护

[代码结构导览](README.md) · [模型](model.md) · [UI 应用](ui-application.md) · [结果分析](results.md)

## 目录

<!-- docs:toc depth=1 -->

- [1 功能归属](#section-功能归属)
- [2 新模型类型的实现路径](#section-新模型类型的实现路径)
- [3 参数与数值语义契约](#section-参数与数值语义契约)
- [4 可视化扩展契约](#section-可视化扩展契约)
- [5 现有检查工具与覆盖位置](#section-现有检查工具与覆盖位置)
- [6 命名、资源与文档维护](#section-命名资源与文档维护)

<!-- /docs:toc -->

<a id="section-功能归属"></a>

## 1 功能归属

| 变更 | 定义位置 | 接入位置 |
|---|---|---|
| 新模型字段 | `ui/model/node_types/` 与 `FieldSpec` | 字段服务、持久化、生成器和后端参数 |
| 新跨对象规则 | `ProblemDefinition` | 应用命令，树与卡片共用 |
| 新编辑工作流 | `ui/application/` | `DefinitionActions` 或专用页面 |
| 新方案 | `SchemeTemplate` 子类及 Python 注册表 | Quickstart 与方案工厂 |
| 新后端 Part | `BasePart` 子类 | 参数集合、UI 节点、预览与集合 provider |
| 新设计对象 | 可更新协议及具体子类 | 梯度布局、子优化器、保存和展示 |
| 新预览类型 | Part/Surface/Load visitor | 节点类注册及必要的渲染图元 |
| 新编辑页面 | widget | `route_editor()`、`EditorPages` 和刷新注册 |
| 新结果量 | `postprocess.fields.ResultField` | `RESULT_FIELDS` 与必要的云图分量 |
| 新导出格式 | `ResultExporter` | `EXPORTERS`，不复制物理提取逻辑 |
| 新运行模式 | `OptimizationRunSession` | 明确来源对象、进程状态和进度快照 |

领域身份由对象与稳定 key 表达，显示文字由展示层本地化。文件、进程、物理计算和渲染各自在所属层处理。

<a id="section-新模型类型的实现路径"></a>

## 2 新模型类型的实现路径

1. 在内核定义构造参数、生命周期与模型构建行为，明确缓存和几何可变性。
2. 可设计类型实现变量提取、灵敏度投影、写回与保存契约，确保展平顺序一致。
3. 在 UI 对应节点家族中声明具体类型和字段，并加入 `registry.py`。
4. 在应用层补充目标查询、动态选项及生成参数映射。
5. 注册节点类对应的预览 adapter 和必要的 `PartSetCatalog` provider。
6. 使用已有字段表单与集合动作；特殊交互通过路由和统一刷新接入。
7. 同步更新脚本/UI 接口参考和本目录中所属专题。

该路径用于确定实现责任，完整构造示例见[脚本模块参考](../scriptreference.md)，不在架构文档中复制另一套任务定义。

复用现有 Part 构建流程时，子类重写对应阶段方法，父类通过实例方法调用调度。需导出的封闭曲面可继承 `BaseSurface.prepare_geometry()`；已有 STEP 资产的 `BREPSurface` 直接使用原文件。曲面在 `load_geometry(part, context)` 中调用 CADPart 的对应载入方法，不持有源 CAD 操作历史。离散曲面通过 `is_discrete` 声明几何内核需求。类型特有的准备、组装和集合定义放在对应子类中，公共构建方法保持稳定。

<a id="section-参数与数值语义契约"></a>

## 3 参数与数值语义契约

| 配置 | 需保持一致的内容 |
|---|---|
| 字段 key | 节点、保存数据、生成调用与后端签名 |
| 材料模型 | `MaterialsParams.models` 参数类型与可见字段 |
| GPU 列表 | UI 配置到 `Solver.available_gpus` 的映射，空列表为 CPU |
| 实例位姿 | 三平移加三旋转向量，单位与排列一致 |
| 曲面尺寸 | `seed_size` 与体网格尺寸分别定义 |
| Fairness 阈值 | 曲率、第一基本形式及非正交度量，不作为控制点位移上限 |
| SIMP 初值 | 控制场 `f`、材料占比 `ρ` 与刚度比例分别定义 |
| 单元选择 | `Part.elems` 的块名，不由单元公式名猜测 |
| 圆柱包络 | 当前实现的 `bottom` 为 Z 下界，`height` 为 Z 上界 |

BSP 的 `maxC/maxR/maxFF` 和 CPGEO 的曲率参数通过 `Fairness` 求值，曲面工厂的大小写与字段映射应按实际签名核对。内部算法参数与 UI 标签不能仅因名称相似而视为等价。

<a id="section-可视化扩展契约"></a>

## 4 可视化扩展契约

预览注册使用节点 Python 类：`PartPreviewVisitor.register(NodeType, adapter)`，不是类型显示字符串。适配器准备网格与场景，不持有 widget、plotter 或 VTK actor。载荷图元由 renderer 分派绘制。

结果展示分别采用归档模型和物理场上下文，不从定义预览缓存取得求解模型。新增场量明确位置、单位、坐标系、张量约定和缺失值行为，导出器仅负责文件表示。

<a id="section-现有检查工具与覆盖位置"></a>

## 5 现有检查工具与覆盖位置

下表说明已有检查的职责；执行范围由实际变更内容确定。

| 工具或文件 | 覆盖内容 |
|---|---|
| [`tests/optcore/test_objfunc.py`](../../tests/optcore/test_objfunc.py) | 目标与结果保存行为 |
| [`tests/optcore/test_solver.py`](../../tests/optcore/test_solver.py) | 工况求解与初值处理 |
| [`tests/ui/test_model_persistence.py`](../../tests/ui/test_model_persistence.py) | 定义序列化与类型恢复 |
| [`tests/ui/test_application.py`](../../tests/ui/test_application.py) | 应用操作、引用与会话 |
| [`tests/ui/test_parameter_contracts.py`](../../tests/ui/test_parameter_contracts.py) | 节点、生成参数与后端签名对应 |
| [`tests/ui/test_custom_classes.py`](../../tests/ui/test_custom_classes.py) | 自定义类绑定与生成 |
| [`tests/ui/test_quickstart.py`](../../tests/ui/test_quickstart.py) | 起始定义与工况/目标组合 |
| [`tests/ui/test_refresh.py`](../../tests/ui/test_refresh.py) | 刷新合并与上下文 |
| [`tests/ui/test_finite_element.py`](../../tests/ui/test_finite_element.py) | 独立有限元、场量及导出 |
| [`tests/ui/test_viewer_lifecycle.py`](../../tests/ui/test_viewer_lifecycle.py) | 视口与对象生命周期 |
| [`utils/gradient_check.py`](../../src/morphopt/utils/gradient_check.py) | AD 与中心差分灵敏度比较 |

`morphopt.check_gradients()` 使用模型的同一变量写回与目标路径比较几何、材料梯度，涉及实际模型求解。`morphopt.get_controller()` 从归档重建控制器并加载状态，也会进入相应初始化流程；两者不是只读取文件名的轻量查询。

定义编辑的撤销、反序列化恢复、生成代码、首轮求解与长期优化分别覆盖不同契约。未执行的检查不作为实现已通过的依据。

<a id="section-命名资源与文档维护"></a>

## 6 命名、资源与文档维护

`Session` 表示有状态应用会话，`Library` 表示资源/文件入口，`Page/Editor/Viewer` 表示 Qt 展示角色。方法名称区分领域编辑、文件读写、会话绑定与显示刷新，避免长期业务对象使用含义不明的临时命名。

业务默认值与数值配置归 `constants.py`，外观与布局归 `ui/theme/`，应用文案归 `ui/locales/`。资源路径按包位置或明确的任务来源解析，不写入特定电脑的绝对路径或环境名。

代码结构文档以本目录 README 为唯一导航入口。公共边界变更更新系统架构；具体实现变更只在所属专题展开，其他专题使用链接。用户可见的参数与操作同步更新[四篇使用文档](../README.md)。

在仓库根目录执行 `python scripts/number_docs.py` 更新标题编号与目录。文件名采用主题名称，编号由标题层级生成，不以文件前缀维护另一套顺序。
