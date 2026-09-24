# MorphOpt 代码结构设计

这组文档以当前 `src/morphopt/` 源码为准，面向实现、扩展和重构 MorphOpt 的开发者，描述系统的对象边界、继承关系、状态所有权和运行数据流。

## 导览

| 页面 | 覆盖范围 |
|---|---|
| [00 总览](design/00_overview.md) | 分层、总生命周期、依赖方向、名称与持久化边界 |
| [01 公共 API 与协议](design/01_public_api_protocols.md) | `morphopt` 顶层 API、四个 `Protocal*` 协议 |
| [02 运行时内核](design/02_runtime.md) | `Controller`、`History`、`Solver`、`ObjectiveFunction`、进程入口 |
| [03 参数集合](design/03_parameters.md) | `Params`、`BaseParams`、几何/FEA/材料集合 |
| [04 载荷与 FEA](design/04_loads_and_fea.md) | 载荷、边界、接触、参考点、弹簧和载荷步 |
| [05 几何](design/05_geometry.md) | Part、Instance、导入模型、装配体与几何持久化 |
| [06 材料](design/06_materials.md) | 均质材料、材料模型与材料分配 |
| [07 形状优化](design/07_shape_optimization.md) | `BoundaryPartInterface`、曲面、网格和形状更新器 |
| [08 SIMP 材料优化](design/08_simp.md) | 密度场材料、材料更新器和 SIMP 目标/约束 |
| [09 协同设计扩展](design/09_codesign.md) | 偏置壳 Part、壳 FEA 和协同约束 |
| [10 UI 领域模型](design/10_ui_domain.md) | `.morph`、类型化任务树、引用与不变量 |
| [11 UI 应用、模板与代码生成](design/11_ui_application_codegen.md) | 会话、模板、生成 Python、运行和结果读取 |
| [12 UI 展示层](design/12_ui_presentation.md) | Workbench、观察页、widgets 与依赖规则 |
| [13 工具、测试与变更准则](design/13_utilities_testing.md) | 调试入口、有限差分检查、测试职责和扩展检查表 |
| [14 源码清单](design/14_source_inventory.md) | 每个源码文件的归属、主要类型与依赖边界 |

已有的 [UI 架构规范](ui.md) 保留为 UI 实现约束；第 09–11 页把它放入整个内核的上下文中。

## 阅读路线

新开发者先读 00 → 01 → 02 → 03，再按工作内容进入 04–09 或 10–12。修改公共接口、生命周期或持久化格式时，同步更新 00、对应模块页和 14。
