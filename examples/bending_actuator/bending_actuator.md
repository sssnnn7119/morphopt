# 圆柱弯曲驱动器

本例对圆柱形弹性体施加内压，并最大化顶部参考点绕 Y 轴的转角。Python 脚本和 `.morph` 文件描述同一项优化，部件、载荷、材料、工况和目标均采用对应名称。

## 文件

- [bending_actuator.py](bending_actuator.py)：可直接运行的任务脚本。
- [bending_actuator.morph](bending_actuator.morph)：可在 MorphOpt UI 中打开和编辑的定义。

## 模型定义

外圆柱半径为 8 mm、长度为 80 mm；内腔半径为 4 mm、长度为 74 mm，内腔底端位于 Z=3 mm。模型使用 Neo-Hookean 材料，底端固定，顶端与参考点耦合，内腔承受 0.06 MPa 压力。几何更新器使用形状灵敏度、平滑性、最小间距和圆柱包络约束。

## 运行

在已安装 MorphOpt 的 Python 环境中，从仓库根目录执行：

```bash
python examples/bending_actuator/bending_actuator.py
```

运行结果保存在工作目录下的 `.results/`。UI 运行方式为打开 `bending_actuator.morph` 后选择“开始优化”。
