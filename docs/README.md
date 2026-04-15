# MorphOpt Docs

本目录提供两类文档：

- 模块参考：按包/文件说明定义方式与职责。
- 定义指南：按开发流程说明如何扩展新的优化任务。

## 文档索引

- [module_reference.md](module_reference.md)
  - 覆盖 `src/morphopt` 下主要模块。
  - 说明每个模块怎么定义、负责什么、常见扩展点在哪里。

- [module_definition_guide.md](module_definition_guide.md)
  - 从零定义 `ThisController` 的完整流程。
  - 包含 `ObjectiveFunction / Params / Solver / Updater` 的模板和注意事项。

## 推荐阅读路径

1. 先看 `module_definition_guide.md`，建立任务定义全流程。
2. 再看 `module_reference.md`，按需定位某个子模块的实现细节。
3. 最后对照 `examples/codesign/twist.py` 完成脚本实现。
