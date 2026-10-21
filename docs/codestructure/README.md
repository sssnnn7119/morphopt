# MorphOpt 代码结构

本文档集面向维护与扩展 MorphOpt 的开发者，说明当前源码的模块边界、对象所有权、调用顺序与持久化约定。任务编写和界面操作分别见[脚本模块参考](../scriptreference.md)与 [UI 模块参考](../UIreference.md)。

<a id="section-模块化设计原则"></a>

## 1 模块化设计原则

MorphOpt 按职责组织模块，通过明确的输入、输出和状态所有权连接各模块。整体设计包含三个层次的分离。

| 设计层次 | 模块划分 | 协作关系 |
|---|---|---|
| 软件整体 | UI 与数值内核分离 | UI 编辑定义并生成运行脚本；脚本和 UI 共用同一套数值内核 |
| 数值内核 | 模型、求解、目标与灵敏度、设计更新分离 | `Controller` 调度各阶段；模型、有限元结果、分类梯度和设计状态构成阶段接口 |
| UI 内部 | 业务数据与显示分离 | 领域模型与应用会话维护定义和操作；导航、场景与控件显示这些状态的投影 |

模型类型、数值算法和界面布局分别在对应模块内扩展。共享协议约定对象的生命周期与设计变量接口；每个组件保存其所属状态，跨组件操作由相应的协调对象组织。[系统架构](architecture.md#modularity)以三张图说明这些边界及其源码对应关系。

<a id="section-专题导航"></a>

## 2 专题导航

| 文档 | 内容归属 |
|---|---|
| [系统架构](architecture.md) | 模块化设计理念、三层职责分离、架构图、接口契约与状态边界 |
| [运行时与进程](runtime.md) | 任务启动、控制器初始化、单轮计算、进程重启与运行归档 |
| [模型与参数集合](model.md) | 共享协议、Part/Instance、载荷工况、材料分配与模型构建 |
| [灵敏度与设计更新](optimization.md) | 变量布局、目标梯度、更新器绑定、形状、SIMP 与偏置扩展 |
| [UI 领域模型](ui-model.md) | 类型化节点、对象引用、结构操作、名称与 `.morph` 序列化 |
| [UI 应用服务](ui-application.md) | 编辑会话、操作历史、Quickstart、代码生成、自定义类与优化运行会话 |
| [UI 展示与刷新](ui-presentation.md) | 窗口、编辑器、导航投影、刷新调度、预览渲染、主题与本地化 |
| [结果分析与导出](results.md) | 结果读取、共享迭代选择、独立有限元、物理场与文件导出 |
| [扩展与维护](development.md) | 新类型和功能的实现位置、参数契约、现有检查工具与文档维护 |

每个主题在上表对应的文档中集中说明。系统架构保留总体关系，专题文档说明内部实现；源码路径在相关专题的“源码入口”中列出。

<a id="section-阅读路径"></a>

## 3 阅读路径

- 内核维护：系统架构 → 运行时 → 模型与参数集合 → 灵敏度与设计更新。
- UI 编辑功能：系统架构 → UI 领域模型 → UI 应用服务 → UI 展示与刷新。
- 结果与后处理：运行时 → 结果分析与导出 → UI 展示与刷新中的结果页面组合。
- 新功能开发：先确定状态所属层，再查阅对应专题与扩展位置。

<a id="section-按变更定位"></a>

## 4 按变更定位

| 变更内容 | 主要实现位置 | 文档 |
|---|---|---|
| 求解调度、工作进程、重启 | `opt_runner.py`、`taskoptmization.py`、`optcore/controller.py`、`solver.py` | [运行时](runtime.md) |
| Part、载荷、本构与装配 | `optcore/modelparams/` | [模型](model.md) |
| 曲面、密度场、梯度与局部优化 | `shapeopt/`、`simp/`、`codesign/`、`optcore/updaters.py` | [设计更新](optimization.md) |
| 字段、引用、增删排序与改名 | `ui/model/`、`ui/application/editing.py` | [UI 领域模型](ui-model.md) |
| 历史、脚本生成、类选择、任务来源 | `ui/application/`、`ui/codegen/`、`ui/schemes/` | [UI 应用服务](ui-application.md) |
| 控件、树、卡片、刷新与预览 | `ui/widgets/`、`ui/presentation/`、`ui/visualization/`、`ui/refresh.py` | [UI 展示](ui-presentation.md) |
| 独立求解、场量与数据导出 | `ui/application/finite_element.py`、`result_fields.py`、`ui/fea_worker.py`、`postprocess/` | [结果分析](results.md) |

<a id="section-文档组织约定"></a>

## 5 文档组织约定

文件名按主题命名，不承载章节序号。各篇标题编号与目录由仓库根目录的 `python scripts/number_docs.py` 生成，编辑时可使用 `--watch`。

API 参数表与可执行示例集中于使用文档；本目录说明实现边界、调用关系和状态约束。结构调整时更新相关专题、当前导航及源码中的文档引用，避免并存多份同一层的架构说明。
