# 二维工作空间目标

本例通过两个独立压力载荷参数生成工作空间采样工况，优化参考点在 XZ 平面内的可达面积。每个高斯点对应一个载荷工况；目标函数在任务脚本中显式累加各工况的位移、载荷雅可比和积分权重。

## 文件

- [workspace_objective.py](workspace_objective.py)：由 UI 定义生成的标准 MorphOpt 任务脚本。
- [workspace_objective.morph](workspace_objective.morph)：可在 UI 中编辑的完整定义。

## 定义内容

模型包含三张边界曲面、两个压力载荷和一个顶部参考点。工作空间目标选择两个独立的压力参数，并按二维高斯积分规则生成八个工况。求解器按工况注册顺序分配任务；目标函数读取每个工况的参考点位移和相应载荷雅可比，并完成加权积分。

## 运行

在已安装 MorphOpt 的 Python 环境中，从仓库根目录执行：

```bash
python examples/workspace_objective/workspace_objective.py
```

也可在 UI 中打开 `workspace_objective.morph`。生成的工况名称以 `workspace_1_case_` 开头。
