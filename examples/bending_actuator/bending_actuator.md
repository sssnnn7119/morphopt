# 圆柱弯曲驱动器

本例对圆柱形弹性体施加内压，并使顶部参考点旋转向量的 Y 分量逼近 2 rad。Python 脚本和 `.morph` 文件描述同一项优化，部件、载荷、材料、工况和目标均采用对应名称。

## 文件

- [bending_actuator.py](bending_actuator.py)：可直接运行的任务脚本。
- [bending_actuator.morph](bending_actuator.morph)：可在 MorphOpt UI 中打开和编辑的定义。

## 模型定义

外圆柱半径为 8 mm、长度为 80 mm；内腔半径为 4 mm、长度为 74 mm，内腔底端位于 Z=3 mm。模型使用 Neo-Hookean 材料，底端固定，顶端与参考点耦合，内腔承受 0.06 MPa 压力。主目标为 `(ry - 2) ** 2`，用户指标 `0` 记录 `ry`，自动指标 `objective_0` 记录该目标的加权贡献。几何更新器采用 `QuadraticShapeDerivative(memory_size=10)`、`Fairness(max_curvature=1)`、2.5 mm 最小间距及半径 10 mm、高度 80 mm 的圆柱包络。

步长策略为 `FixedStepLength`，最大控制点位移上限为 0.5 mm，子问题最多迭代 50 次。`AdaptiveShapeWeights` 的初始/最终距离放宽比例为 0.05/0，目标相对变化阈值为 0.01，每次收紧量为 0.001，罚值增长触发倍数为 2。阈值和系数仅在外层迭代之间调整，并在单次子优化中保持固定。

脚本默认使用 CPU 和一个有限元求解进程，重启周期为 20。

## 运行

在已安装 MorphOpt 的 Python 环境中，从仓库根目录执行：

```bash
python examples/bending_actuator/bending_actuator.py
```

运行结果保存在脚本所在目录的 `.results/`。UI 运行方式为打开 `bending_actuator.morph` 后选择“开始优化”。
