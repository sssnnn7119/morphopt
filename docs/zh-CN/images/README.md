# UI 文档截图

[English](../../en-US/images/README.md)

在已安装 MorphOpt 及其 UI 依赖的 Python 环境中，从仓库根目录运行以下命令。默认在独立的虚拟显示中依次采集简体中文和英文界面。Linux 可使用 Xvfb（含 xvfb-run 与 xauth），或使用 KWin 的虚拟显示后端（含 Xwayland 与 dbus-run-session）。

```bash
python scripts/docs/capture_ui.py
```

脚本打开实际窗口并操作控件。定义页覆盖几何、实例、载荷工况、材料、目标、求解器、更新器、自定义类和资产。其余场景包括快速开始、模型问题、外观、剖视、漫游、优化观察、历史导出和事后有限元。全部图片按相同的模块和文件名编排。[中文截图](gallery.md) · [English screenshots](../../en-US/images/gallery.md)

终端显示当前截图路径。两种语言共用一次弯曲算例求解，按顺序创建和释放各自的 Qt、VTK 窗口。在已有归档的情况下，指定 `--result` 可直接从界面采集开始。单语言采集进一步减少渲染和导出开销。

```bash
python scripts/docs/capture_ui.py --language zh-CN
python scripts/docs/capture_ui.py --language en-US --result /path/to/bending-run
```

调试时可添加 `--visible` 在当前桌面观察采集，也可在 Windows 图形会话使用此选项。关闭采集主窗口会取消当前批次。

<a id="section-结果页的数据来源"></a>

## 1 结果页的数据来源

- 弯曲驱动器使用仓库中的优化定义，在临时目录以 CPU 完成两轮计算。历史设计、控制点网格、加载变形和 GIF 预览均读取该次运行的归档。[弯曲驱动器算例](../../../examples/bending_actuator/bending_actuator.morph)
- 事后有限元使用归档模型的副本，将 `load_case_1` 的 `pressure_1` 从 0.06 MPa 改为 0.04 MPa，重新求解并采集位移场。
- SIMP 采用快速开始的拓扑优化算例，有限元网格尺寸设为 4。采集程序在首个检查点写入后记录运行状态、材料密度场及导出选项。
- 资产页展示 STEP、STL 和 INP 三类文件。[资产样本](import-samples.md)

已有同一弯曲算例的完整归档时，可指定 `--result` 复用计算结果。该目录须包含至少两轮已保存的模型、解和历史记录。独立的 SIMP 计算和事后有限元重算仍由脚本执行。

```bash
python scripts/docs/capture_ui.py --result /path/to/bending-run
```

<a id="section-输出与核查"></a>

## 2 输出与核查

截图先写入临时目录。脚本核对两篇 UI 指南引用的 PNG 是否均由本次采集生成，并在双语采集时核对两种语言的图片集合。每种语言的 `images/ui-quickstart/` 保存操作教程截图，`images/ui-reference/` 保存各模块的接口截图。两套文档使用相同的相对路径。窗口及弹出菜单保留 Qt 抓取的原始像素。[快速开始](../ui-quickstart.md) · [模块与接口参考](../ui-reference.md)

[采集清单](current-capture-manifest.json)记录图片路径、来源、像素尺寸、设备像素比和实际中文字体。[接口目录](ui-reference/interface-catalog.json)由 UI 注册表生成。更新界面后，新增截图场景应同时接入该入口，以便下一次统一采集。
