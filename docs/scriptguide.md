# MorphOpt 脚本快速开始

[UI 快速开始](UIguide.md) · [脚本模块与接口参考](scriptreference.md) · [UI 模块与接口参考](UIreference.md)

本文以单气腔软体结构为例，说明任务脚本的准备、优化启动、结果读取与继续计算。示例与 [UI 快速开始](UIguide.md) 采用相同的几何、载荷、材料和优化目标。各模块的扩展方法及完整接口约定见[脚本模块与接口参考](scriptreference.md)。

## 目录

<!-- docs:toc depth=1 -->

- [1 算例与运行条件](#section-算例与运行条件)
- [2 安装并启动算例](#section-安装并启动算例)
- [3 完整任务脚本](#section-完整任务脚本)
- [4 查看输出与设计变化](#section-查看输出与设计变化)
- [5 停止与继续计算](#continuation)
- [6 修改算例](#section-修改算例)

<!-- /docs:toc -->

<a id="section-算例与运行条件"></a>

## 1 算例与运行条件

| 项目 | 本例定义 |
|---|---|
| 几何 | 沿 Z 轴布置的圆柱结构，外半径 8、长度 80；内腔半径 4、长度 74，底端 Z 坐标为 3 |
| 部件与实例 | `part1` 与 `part1-1` |
| 边界条件 | 外表面底端固定 X、Y、Z 平移 |
| 载荷 | 内腔表面压力 `0.06`，一个载荷工况 |
| 末端响应 | `RP_1` 与顶端节点耦合，读取旋转向量的 Y 分量 `ry` |
| 材料 | `NeoHookeanLnJ`，`mu=0.482`、`kappa=4.8` |
| 设计变量 | 外边界与内腔的曲面控制点 |
| 优化目标 | 最大化有符号转角 `ry`，损失为 `-ry` |
| 几何控制 | xz 镜面对称、曲率正则化、最小距离与圆柱包络 |
| 计算设置 | CPU，一个有限元求解进程 |

本例采用 mm–N–MPa 一致单位制，`0.06 MPa` 对应 `60 kPa`；旋转向量采用 rad。MorphOpt 不执行自动单位换算，无需安装 Abaqus。脚本运行不打开 MorphOpt 界面；几何网格与离屏图像保存仍由相应的 Gmsh、VTK 运行环境提供支持。

![算例中部件、实例、材料与载荷的引用关系](images/ui-reference/diagrams/object-references.svg)

<a id="section-安装并启动算例"></a>

## 2 安装并启动算例

运行环境要求 Python 3.12 或更新版本。在选定的 Python 环境中安装：

```bash
python -m pip install morphopt
```

完整任务文件为 [bending_optimization.py](examples/bending_optimization.py)。在仓库根目录可直接执行：

```bash
python docs/examples/bending_optimization.py
```

独立使用时，将该文件保存到任务目录，在该目录执行 `python bending_optimization.py`。从源码运行时，在仓库根目录以 `python -m pip install -e .` 安装，再执行同一任务文件。

该任务使用 CPU 和一个求解进程，不要求配置 CUDA。首次迭代依次完成曲面初始化、体网格生成、非线性有限元求解、灵敏度计算与设计更新。首轮完成前尚无完整历史曲线；计算时间由网格规模、材料非线性和计算资源共同决定。

<a id="section-完整任务脚本"></a>

## 3 完整任务脚本

以下代码与随文档提供的任务文件一致，可整体保存为 `bending_optimization.py` 后运行。

```python
"""脚本与 UI 快速开始共用的气动弯曲优化算例。"""

import morphopt


class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder="./results/", opt_label="BendingExample")

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def reference_point_motion(self, step_index=0):
            morphopt.controller.params.feamodel.process_fea(
                self.fe, step_index=step_index
            )
            assembly = self.fe.assembly
            coordinates = self.fe_results[step_index].GC.to(assembly.device)
            reference_point = assembly.get_reference_point("RP_1")
            return assembly._GC2RGC(coordinates)[reference_point._RGC_index].reshape(-1)

        def objective_function(self):
            # 最小化 -ry，对应最大化绕全局 Y 轴的有符号转角。
            return -self.reference_point_motion()[4]

        def get_metrics(self):
            return [self.reference_point_motion()[4].detach().cpu().item()]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):
            class Actuator(morphopt.BoundaryPart):
                def define_instance(self):
                    self.add_instance(self.part_name, "part1-1", [0.0] * 6)

                def define_surfaces(self):
                    for radius, length, location, flip in [
                        (8.0, 80.0, [0.0, 0.0, 0.0], False),
                        (4.0, 74.0, [0.0, 0.0, 3.0], True),
                    ]:
                        surface = self.BSP.initialize_cylinder(
                            r0=radius,
                            length=length,
                            seed_size=1.0,
                            init_location=location,
                            flip=flip,
                            maxR=0.2,
                            maxC=1.0,
                            maxFF=0.2,
                            perturbation_L=10.0,
                        )
                        surface.is_updatable = True
                        surface.add_constraint(surface.mirror("xz"))
                        self.add_surface_interface(surface)

            def define_interface(self):
                self.add_interface(
                    self.Actuator(fea_seed_size=1.0, mesh_order=1), name="part1"
                )

        class FEAParams(morphopt.FEAParams):
            def define_interface(self):
                self.add_interface(
                    self.BoundaryCondition(
                        instance_name="part1-1",
                        set_nodes_name="surface_0_Bottom",
                        index_dof=[0, 1, 2],
                    ),
                    name="bc_1",
                )
                self.add_interface(
                    self.ReferencePoint(rp_location=[0.0, 0.0, 80.0]), name="RP_1"
                )
                self.add_interface(
                    self.Couple(
                        rp_name="RP_1",
                        instance_name="part1-1",
                        set_nodes_name="surface_0_Head",
                    ),
                    name="couple_1",
                )
                self.add_interface(
                    self.Pressure(
                        instance_name="part1-1", surface_name="surface_1_All"
                    ),
                    name="pressure_1",
                )

            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(0, "pressure_1", [0.06])

        class MaterialsParams(morphopt.MaterialsParams):
            def define_interface(self):
                self.add_interface(
                    self.HomogeneousMaterial(
                        material_parameters=self.models.NeoHookeanLnJParams(
                            mu=0.482, kappa=4.8
                        ),
                        density=1.08e-9,
                        part_name="part1",
                    ),
                    name="material_1",
                )

        def __init__(self):
            super().__init__(
                geometry=self.GeometryParams(),
                feamodel=self.FEAParams(),
                materials=self.MaterialsParams(),
            )

    class Solver(morphopt.Solver):
        def __init__(self, params):
            super().__init__(params=params, num_process=1, available_gpus=[])

    class Updater(morphopt.Updaters):
        def define_updater(self):
            self.add_geometry_updater(self.Shape(), name="part1")

        class Shape(morphopt.UpdaterBoundaryPart):
            def __init__(self):
                super().__init__(max_step_iter=50)

            def define_objective(self):
                self.add_objective_function(self.objectivefuncs.ShapeDerivative())
                self.add_constraints(self.objectivefuncs.Fairness())
                self.add_constraints(
                    self.objectivefuncs.Distance(
                        min_distance=[[2.5, 2.5], [2.5, 2.5]]
                    )
                )
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(
                        radius=10.0, height=80.0, bottom=0.0
                    )
                )


if __name__ == "__main__":
    morphopt.start_optimization(device="cpu", restart_per_iteration=20)
```

`ThisController` 为运行器加载的任务类名称。文件末尾的 `if __name__ == "__main__":` 限制启动入口，避免多进程导入脚本时重复启动任务。

各段代码按以下关系组成完整模型：

| 定义位置 | 本例中的内容 |
|---|---|
| `ThisController.__init__()` | 任务名称和结果根目录 |
| `ObjectiveFunction` | 从 `RP_1` 读取末端运动，返回损失并记录转角 |
| `Params.GeometryParams` | 注册 `part1`，声明实例、外边界与内腔 |
| `Params.FEAParams` | 注册固定条件、参考点、耦合和压力，再填写工况幅值 |
| `Params.MaterialsParams` | 将本构模型分配给 `part1` |
| `Params.__init__()` | 将三个参数集合传入框架 |
| `Solver` | 使用一个 CPU 求解进程 |
| `Updater` | 将几何更新器绑定到 `part1`，注册灵敏度与几何约束 |

参考点运动按名称从装配体中提取，分量顺序为 `[x, y, z, rx, ry, rz]`。示例的索引 `4` 对应 `ry`。提取过程与 UI 的参考点数据模板一致，使用当前后端的 `_GC2RGC` 与 `_RGC_index`；目标函数中的张量保留梯度，只有记录指标时转换为普通数值。

<a id="section-查看输出与设计变化"></a>

## 4 查看输出与设计变化

结果保存在任务脚本所在目录的 `results/BendingExample_T<时间戳>/`。相对输入路径和结果根目录均按任务脚本目录解析。

| 文件或目录 | 内容 |
|---|---|
| `log/history_record.csv` | 每轮损失、指标、计算时间和网格统计 |
| `log/morphopt.log` | 优化流程日志 |
| `log/torchfea.log` | 有限元求解日志 |
| `log/geometry/`、`log/materials/` | 各轮设计状态 |
| `log/geometryupdater/` | 几何更新器状态 |
| `log/femodel&results/` | 各轮有限元模型及工况结果 |
| `log/deformation/` | 工况变形图与表面文件 |
| `scripts/MAIN_SCRIPT_FOR_RESTART.py` | 继续计算使用的任务脚本快照 |

终端的 `Iteration`、`Loss` 与分阶段耗时反映当前优化进展。本例最小化 `-ry`，因此负损失与正转角可以同时出现。判断优化方向时，应同时读取损失与记录的 `ry`，并区分有符号转角、转角绝对值和欧拉角。

图形查看步骤如下：

1. 执行 `morphopt-ui`。
2. 选择 **文件 → 打开优化结果**，定位到包含 `log/` 和 `scripts/` 的具体任务目录。
3. 在 **优化过程** 中选择迭代，查看历史曲线、设计边界与工况变形。
4. 进入 **工况与计算结果**，查看该轮对应的位移、应力和应变。

该过程读取脚本运行产生的归档。任意 Python 任务不会反向转换为主定义页中可编辑的 `.morph` 模型树。界面操作见 [UI 快速开始](UIguide.md#optimization) 与 [UI 结果分析参考](UIreference.md#results)。

<a id="continuation"></a>

## 5 停止与继续计算

终端中按 Ctrl+C 中断当前任务。继续计算应选择已经完整保存模型、结果和设计状态的运行目录；被中断但尚未完成保存的迭代不作为恢复依据。

新建 `resume_optimization.py`，将下列运行目录替换为实际路径：

```python
from pathlib import Path
import morphopt

if __name__ == "__main__":
    run_folder = Path("results/BendingExample_T<时间戳>").resolve()
    morphopt.start_optimization(
        device="cpu",
        path_result=str(run_folder),
    )
```

运行 `python resume_optimization.py` 后，程序从该目录的任务快照和最近保存状态继续计算。`path_result` 指向单个运行目录；其父目录仅用于容纳多个运行。任务结构发生变化时应创建新运行，原始脚本的后续修改不会自动替换已有运行中的脚本快照。

`restart_per_iteration=20` 指定分段运行时的进程重启间隔，重启后继续同一任务。`max_step_iter=50` 限定每轮设计更新内部的子优化次数。两者均不是外层优化总轮数上限。

<a id="section-修改算例"></a>

## 6 修改算例

| 修改内容 | 修改位置 | 同步核查 |
|---|---|---|
| 圆柱与内腔尺寸 | `Actuator.define_surfaces()` | 内腔位置、壁厚、参考点位置与包络尺寸 |
| 压力幅值 | `FEAParams.define_steps()` 中的 `[0.06]` | 一致单位制及加压表面 |
| 材料参数 | `MaterialsParams.define_interface()` | 参数名称、本构模型及部件分配 |
| 运动方向 | `objective_function()` 的分量与符号 | 指标分量、最大化或最小化含义 |
| 网格疏密 | `fea_seed_size` | 首轮流程、求解稳定性与正式结果精度 |
| 更新控制 | `Shape.define_objective()` | 最小距离、曲率阈值和包络 |

`seed_size` 控制曲面控制网格，`fea_seed_size` 控制体有限元网格，两者独立。只增大体网格尺寸不会同时减少曲面设计变量。多工况、材料拓扑优化、CAD、接触和自定义更新器分别见[脚本模块与接口参考](scriptreference.md)。
