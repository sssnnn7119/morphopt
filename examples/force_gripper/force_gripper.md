# 多步恒力夹爪

本例使用对称半模型、刚性圆柱和多步接触求解，优化夹爪在工作行程内的接触力，使其接近指定目标值。模型单位为 mm、N 和 MPa。脚本与 UI 定义包含相同的几何、边界条件、工况、目标和 SIMP 更新设置。

## 文件

- [force_gripper.py](force_gripper.py)：可直接运行的优化任务脚本。
- [force_gripper.morph](force_gripper.morph)：可在 MorphOpt UI 中打开和编辑的定义。

## 模型定义

夹爪设计域采用 SIMP 密度参数化，根部、对称面和接触面分别定义边界集合。刚性圆柱按给定位移逐步闭合。12 个工况按闭合位移从小到大的顺序放在同一个进程组中，依次求解并沿用上一步结果。目标函数对工作行程内的归一化力误差作梯形积分，并施加体积分数约束。

## 运行

在已安装 MorphOpt、TorchFEA 和 CAD 依赖的 Python 环境中，从仓库根目录执行：

```bash
python examples/force_gripper/force_gripper.py
```

脚本和 `.morph` 定义均默认使用一个 CPU 求解进程。UI 中打开 `force_gripper.morph` 可检查进程组及工况顺序。
