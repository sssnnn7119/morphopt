# MorphOpt Docs

本文档覆盖 MorphOpt v3.1.5 的模块定义方式和优化任务开发流程。

项目按功能拆分为三个子包：

- `shapeopt`：形状优化（BSP 曲面参数化）
- `simp`：SIMP 拓扑优化（材料场）
- `codesign`：壳层协同设计

核心框架位于 `optcore`，被三个子包共享。

## 文档索引

- [UI_usage.md](UI_usage.md)
  - MorphOpt 图形界面（定义 + 观察，单窗口）的安装启动与完整使用流程。

- [module_reference.md](module_reference.md)
  - 覆盖 `src/morphopt` 下主要模块。
  - 说明每个模块怎么定义、负责什么、常见扩展点在哪里。

- [module_definition_guide.md](module_definition_guide.md)
  - 从零定义 `ThisController` 的完整流程。
  - 包含 `ObjectiveFunction / Params / Solver / Updater` 的模板和注意事项。

## 推荐阅读路径

1. 想用图形界面：先看 `UI_usage.md`，掌握定义 + 观察工作流。
2. 手写任务：先看 `module_definition_guide.md`，建立任务定义全流程。
3. 再看 `module_reference.md`，按需定位某个子模块的实现细节。
4. 最后对照 `myjobs/` 下的任务脚本完成实现。
