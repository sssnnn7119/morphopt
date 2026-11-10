# UI 文档配图

配图按模块存放，文件采用描述内容的英文小写名称，不使用序号前缀。

| 目录 | 内容 |
|---|---|
| `ui/` | 快速开始的定义、优化历史和事后有限元截图 |
| `ui-reference/` | 其他接口、策略、外观和资产操作的截图及说明图 |
| `current-capture-manifest.json` | 当前分支重采图片的来源、像素尺寸、定义摘要与字体记录 |

<a id="section-当前截图"></a>

## 1 当前截图

当前分支的截图由 [`capture_ui.py`](../../scripts/docs/capture_ui.py) 从实际运行的 PySide6 界面生成，包括分量输入、具名工况、节点方向约束、工作空间、CPU 进程配置、几何策略、字体设置、优化日志、单曲面控制网格及导出窗口。截图保留 `QWidget.grab()` 的原始像素，不替换文字或重采样。

历史和三维结果图片来自当前 [bending_actuator.py](../../examples/bending_actuator/bending_actuator.py) 在 CPU 上完成的两轮计算，主目标为 `(ry-2)**2`。定义窗口中的 CPGEO、PenaltyDoF、弹簧和 Ogden 等额外配置只说明接口，不表示它们已完成优化。已有事后有限元图片保留原分析记录，来源与当前两轮计算分别说明。

截图使用独立的临时偏好目录，不修改用户的字体或主题设置。西文字体和字号采用应用启动时的系统默认；已安装 `Noto Sans CJK SC` 时，中文明确选择这一系统简体字体，通过实际 glyph runs 检查。VTK 使用同一字体集合中的 SC 面，避免默认选择日文字体面。字体选择通过软件自身的 `FontManager` 应用，不逐控件覆盖。

<a id="section-重新采集"></a>

## 2 重新采集

在已安装项目的 Python 环境中，于仓库根目录运行：

```bash
python scripts/docs/capture_ui.py --result /path/to/completed/run
```

`--result` 指向当前弯曲算例的完整运行目录；省略时只采集定义和设置窗口。脚本不启动优化，不改写源 `.morph`，导出窗口截图后取消。真实三维视口需要可用的 Qt 图形会话和 OpenGL；无桌面时，Qt offscreen 后端还需要相应的图形支持，不能把黑色视口作为正常图片收录。

[`capture_assets.py`](../../scripts/docs/capture_assets.py) 单独采集多类型资产页。资产演示文件位于 [`docs/assets/ui_reference/`](../assets/ui_reference/)，仅作为文档的导入与显示样本；完整可运行算例位于 [`examples/`](../../examples/README.md)。

<a id="section-分类"></a>

## 3 分类

`geometry`、`cad`、`loads`、`materials`、`objectives`、`solver`、`updaters`、`custom-code`、`assets`、`optimization`、`finite-element`、`appearance` 和 `workspace` 分别对应几何、建模、载荷、材料、目标、求解、更新、代码、资产、结果、外观和通用菜单。`diagrams` 为解释对象关系的说明图，不属于计算结果。模块结构与数据流在 Markdown 中采用 Mermaid 表达。
