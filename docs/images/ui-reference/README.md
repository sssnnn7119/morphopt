# 模块与接口参考配图

本目录服务 [UI 模块参考](../../UIreference.md)。模块图片与快速开始共用，不复制同一张图。当前分支重采的图片以[当前截图清单](../current-capture-manifest.json)为准；其余已有图片保留原有采集记录。

<a id="section-来源与边界"></a>

## 1 来源与边界

- 当前定义图片来自仓库对应的 `.morph` 文件，历史图片来自当前弯曲脚本的两轮 CPU 计算。
- Box、CAD、CPGEO、弹簧、接触、SIMP 和自定义类图片说明接口参数或几何预览，不能据此推定已收敛。
- STEP/STL/INP 文档样本位于[资产说明](../../assets/ui_reference/README.md)。文件导入后的材料分配、载荷及边界需另行核查。
- 对话框图片取自实际 Qt 窗口；导出操作在截图后取消，不生成用户文件。

<a id="section-字体与原始像素"></a>

## 2 字体与原始像素

新采图片通过应用的字体管理器采用系统西文字体和字号，并明确选择已安装的简体中文字体。当前采集的汉字实际字形均来自 Noto Sans CJK SC；三维标注选用同一集合中的 SC 字体面。偏好写入临时目录，用户桌面设置保持不变。具体角色和实际字体见当前截图清单，早期截图的字体记录见[原采集记录](../font-policy.json)。

图片保留原始像素，支持放大查看，不通过图像编辑替换控件内容。重新采集方式与运行环境见[配图维护说明](../README.md)。

<a id="section-命名和接口清单"></a>

## 3 命名和接口清单

图片使用 `模块/内容名称.png`，例如 `loads/penalty-node-direction.png`、`objectives/workspace-objective.png` 和 `appearance/font-settings.png`。

[interface-catalog.json](interface-catalog.json) 由当前 UI 注册表生成，包含部件、曲面、14 种 CAD 操作、13 类载荷与连接、材料、更新目标、约束和策略，以及 8 种本构参数定义。静态字段记录包含分量名称、项类型、默认值、选项及帮助；依对象类型变化的字段投影见正文，例如实例 PenaltyDoF 从 s 派生节点与方向。载荷另记录 `value_fields`，与工况和独立有限元编辑共用。

<a id="section-说明图"></a>

## 4 说明图

`diagrams/object-references.svg`、`optimization-cycle.svg`、`simp-pipeline.svg` 和 `geometric-constraints.svg` 分别解释对象引用、优化循环、材料映射和几何约束。这些图示不是有限元结果；实现细节以当前模块参考和源码为准。
