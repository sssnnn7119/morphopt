# 模块与接口参考配图

用于 [`docs/UIreference.md`](../../UIreference.md)。本目录包含 **40 张实际界面截图、4 张 SVG 说明图**，UI 快速开始的相关截图通过相对链接复用。

<a id="section-来源与内容"></a>

## 1 来源与内容

- 截图来自基于 PySide6 / Qt 的 MorphOpt 图形界面；安装与启动方式见UI 快速开始。
- 截图保留原始像素尺寸，支持放大查看。
- 截图没有重采样、锐化或替换文字。
- [示例定义](../../../examples/bending_actuator/bending_actuator.morph)提供圆柱边界、压力、RP、耦合、目标和优化器参数；[STL 示例](../../../docs/assets/ui_reference/reference-boundary.stl)来源于已保存第 36 轮的变形表面。
- Box、CAD、CPGEO、弹簧、接触、SIMP、曲面关联与自定义代码属于接口表单和预览演示。未把这些演示配置宣称为已求解或已优化算例。
- INP 演示使用 [`reference-box.inp`](../../../docs/assets/ui_reference/reference-box.inp)，包含当前导入器需要的显式集合、截面与占位 Neo-Hookean 材料。正式模型仍需复核材料分配并定义边界、载荷和目标。
- `cad/export-step-dialog.png` 展示真实 STEP 保存对话框及 STP 文件筛选，截图后取消保存。`geometry/cad-part.png` 已包含卡片顶部的“导出 STEP…”入口。
- 截图采用独立的示例定义与运行副本；可移植定义位于 `examples/bending_actuator/bending_actuator.morph`，结果目录使用相对路径。
- 新增[资产页截图](../ui/assets/geometry-assets.png)展示随文档提供的 STEP、STL 和 INP 文件，采用下述统一简体中文字体设置；来源、尺寸与实际字形记录在[资产页截图清单](../ui/assets/capture-manifest.json)。

<a id="section-统一简体中文字体"></a>

## 2 统一简体中文字体

所有截图在应用启动后明确使用系统已安装的 **Noto Sans CJK SC，10 pt**。普通、强调和标题分别使用这套字体对应的字重；不再仅指定缺少汉字的 Noto Sans 并依赖逐字回退。

| 内容 | 字体处理 |
|---|---|
| 表单、模型树、菜单和对话框 | Noto Sans CJK SC |
| 代码与输出 | 英文等宽字体 Hack；中文明确使用 Noto Sans CJK SC |
| Matplotlib 图表 | Noto Sans CJK SC |
| 三维标注 | 从系统 TTC 集合提取 SC 字体面供 VTK 使用，避免默认选择 JP 字体面 |
| SVG 说明图 | Noto Sans CJK SC |

旧图混用的原因有两处：Qt 将缺失汉字分别回退到 MS Gothic、微软雅黑等字体；VTK 读取 TTC 集合时也可能使用其中默认的日文字体面。两处均已在截图进程中明确指定简体中文版本。该处理不修改桌面的全局字体设置。

实际 glyph runs 检查覆盖普通、600、700 字重和界面控件字体；检查记录见 [统一字体记录](../font-policy.json)。标题与正文保留 UI 原本的字重层级，同一类文字不再因中文回退而混用字形。

资产页截图由 [`scripts/docs/capture_assets.py`](../../../scripts/docs/capture_assets.py)生成。共享的 `capture_fonts.py` 从系统字体中提取 SC 字体面，并检查界面控件实际采用的中文字体。该脚本需要 `fonttools`、`fontconfig` 和系统已安装的 Noto Sans CJK SC；字体设置仅作用于截图进程。

<a id="section-部件与实例命名"></a>

## 3 部件与实例命名

定义页中每个 Part 仅保留一个部件名称；实例名称在对应 Instance 卡片中单独定义。部件改名保持已有实例名称不变。材料卡片的“所属部件”或“设计部件”用于选择分配对象，导入卡片的源 Part 名称用于选择文件中的部件。相关截图已按这一界面更新。

<a id="section-文件分类与命名"></a>

## 4 文件分类与命名

图片使用 `模块/内容名称.png`，不使用序号或编号前缀。例如：

```text
geometry/box-part.png
cad/boolean-cut.png
loads/contact.png
materials/simp-material.png
objectives/jacobian-template-parameters.png
updaters/geometry/surface-relation.png
custom-code/method-override.png
diagrams/object-references.svg
```

[截图清单](capture-manifest.json) 的 file 字段记录相对本目录的分类路径；Markdown 与清单随文件移动同步更新。

<a id="section-下拉列表与参数窗口"></a>

## 5 下拉列表与参数窗口

Wayland 下脚本没有真实输入事件的 serial，程序弹出下拉列表会报告无法进行 grabbing popup。相应截图把 **实际 Qt 下拉控件的 grab 像素**按窗口位置合入主窗口抓图；模板参数对话框居中摆放，内容来自实际 QWidget。未绘制假的字段或菜单。相关图片在清单中带 `capture_note`。

<a id="section-svg-说明图"></a>

## 6 SVG 说明图

- `diagrams/object-references.svg`：部件、实例、RP、材料、接口与工况引用关系。
- `diagrams/optimization-cycle.svg`：FE 求解、主目标、设计梯度、内部更新与保存的关系。
- `diagrams/simp-pipeline.svg`：控制场 f、sigmoid 占比 ρ、RAMP 刚度比例 r 的区别。
- `diagrams/geometric-constraints.svg`：包络、径向下限、距离与曲率控制的含义。

SVG 是可编辑的文档图示，已渲染检查文字和布局，不属于计算结果。

<a id="section-接口清单"></a>

## 7 接口清单

[interface-catalog.json](interface-catalog.json) 从 UI 注册表及本构参数定义提取，保留 59 类对象、8 种本构和各字段的键、类型、初值、选项与帮助说明。当前 UI 帮助文字的复用并不保证语义完全相同，例如偏置约束的 `min_distance` 为标量；其参数定义以正文中的后端说明为准。
