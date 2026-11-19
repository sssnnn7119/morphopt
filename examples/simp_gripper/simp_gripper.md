# 多位置接触 SIMP 夹爪

本例在四个圆柱位置建立接触工况，对夹爪执行 SIMP 密度优化。脚本和 UI 定义对应同一模型，包括几何、接触集合、载荷、目标函数和材料更新设置。

## 文件

- [simp_gripper.py](simp_gripper.py)：可直接运行的优化任务脚本。
- [simp_gripper.morph](simp_gripper.morph)：可在 MorphOpt UI 中打开和编辑的定义。

## 模型定义

夹爪主体按 X 坐标划分设计域与实体支撑域，另创建四个刚性圆柱接触体。每个工况驱动一个圆柱闭合，其余圆柱保持初始位置。目标函数汇总各工况下夹爪的接触响应；SIMP 更新器施加材料密度边界和体积分数约束。网格、命名集合和目标函数通过定义中的自定义类与辅助代码实现。

## 运行

在已安装 MorphOpt、TorchFEA 和 CAD 依赖的 Python 环境中，从仓库根目录执行：

```bash
python examples/simp_gripper/simp_gripper.py
```

UI 中打开 `simp_gripper.morph` 后可查看相同的工况和优化设置。

## 更新与工况配置

材料更新目标 `Sensitivity()` 使用原始有限元材料灵敏度。更新策略 `FixedUpdate(value=1)` 对各罚项采用单位系数，最大更新步长为 1，单次子优化最多迭代 100 次。求解器默认使用一个 CPU 进程。
