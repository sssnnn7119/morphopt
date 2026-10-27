# MorphOpt 优化算例

每个算例都放在独立目录中，并配有同名的 `.py` 运行脚本、`.morph` UI 定义和 `.md` 说明文档。需要外部几何文件的算例将文件统一放在本目录下的 `assets/` 子目录。

| 算例 | Python 脚本 | UI 定义 | 说明 |
|---|---|---|---|
| 弯曲驱动器 | [`.py`](bending_actuator/bending_actuator.py) | [`.morph`](bending_actuator/bending_actuator.morph) | [打开说明](bending_actuator/bending_actuator.md) · 圆柱内腔加压与弯曲转角优化。 |
| 工作空间 | [`.py`](workspace_objective/workspace_objective.py) | [`.morph`](workspace_objective/workspace_objective.morph) | [打开说明](workspace_objective/workspace_objective.md) · 多载荷高斯点工况与二维工作空间目标。 |
| 混合圆柱 | [`.py`](hybrid_cylinder/hybrid_cylinder.py) | [`.morph`](hybrid_cylinder/hybrid_cylinder.morph) | [打开说明](hybrid_cylinder/hybrid_cylinder.md) · 固定 STEP 外边界与可更新 BSP 内腔。 |
| STEP 单面 | [`.py`](step_face/step_face.py) | [`.morph`](step_face/step_face.morph) | [打开说明](step_face/step_face.md) · 选择 STEP 圆柱的指定面并转换为 NURBS 设计面。 |
| SIMP 夹爪 | [`.py`](simp_gripper/simp_gripper.py) | [`.morph`](simp_gripper/simp_gripper.morph) | [打开说明](simp_gripper/simp_gripper.md) · 四个接触位置下的密度优化。 |
| 恒力夹爪 | [`.py`](force_gripper/force_gripper.py) | [`.morph`](force_gripper/force_gripper.morph) | [打开说明](force_gripper/force_gripper.md) · 多步接触与力—位移目标。 |

从仓库根目录运行 Python 脚本，例如：

```bash
python examples/bending_actuator/bending_actuator.py
```

在 UI 中打开对应的 `.morph` 文件可查看或修改定义。几何资产分别保存在需要它们的算例目录中的 `assets/`。UI 文档使用的共享导入文件位于 [`docs/assets/ui_reference/`](../docs/assets/ui_reference/)；仓库不再维护 `docs/examples/` 的副本。
