# 模块定义指南（how to define each module）

本文回答两个问题：

- 每个模块你应该怎么定义。
- 每个模块在优化流程里负责什么。

## 1. 总体思路

MorphOpt 的任务定义是“控制器驱动”的：

1. 你定义 `ThisController`。
2. 在控制器内定义四个模块：`ObjectiveFunction / Params / Solver / Updater`。
3. 通过 `morphopt.start_optimization(...)` 启动。

代码骨架（以 shapeopt 方案为例）：

```python
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='D:/Results', opt_label='MyTask')

    class ObjectiveFunction(morphopt.shapeopt.ObjectiveFunction):
        ...

    class Params(morphopt.shapeopt.Params):
        ...

    class Solver(morphopt.shapeopt.Solver):
        ...

    class Updater(morphopt.shapeopt.Updaters):
        ...
```

> **继承必须写完整的方案前缀**。不要用顶层裸名（`morphopt.ObjectiveFunction`、`morphopt.Materials`、`morphopt.UpdaterGeometries` 等在顶层并不存在）。三种方案（shapeopt / simp / codesign）的基类对照：

| 控制器内模块 | shapeopt（曲面形状） | simp（拓扑） | codesign（协同） |
|---|---|---|---|
| `ObjectiveFunction` | `morphopt.shapeopt.ObjectiveFunction` | `morphopt.simp.ObjectiveFunction` | `morphopt.codesign.ObjectiveFunction` |
| `Params` | `morphopt.shapeopt.Params` | `morphopt.simp.Params` | `morphopt.codesign.Params` |
| `GeometryParams` | `morphopt.shapeopt.GeometryParams` | `morphopt.simp.FixedGeometry` / `FixedGeometryINP` | `morphopt.codesign.CodesignGeometry` |
| `FEAParams` | `morphopt.shapeopt.FEAParams` | `morphopt.simp.FEAParams` | `morphopt.codesign.CodesignFEAParams` |
| `MaterialParams` | `morphopt.shapeopt.HomogeneousMaterial` | `morphopt.simp.SIMP_BSPFieldMaterials` | `morphopt.codesign.CodesignMaterials` |
| `Solver` | `morphopt.shapeopt.Solver` | `morphopt.simp.SIMPSolver` | `morphopt.codesign.Solver` |
| `Updater` | `morphopt.shapeopt.Updaters` | `morphopt.simp.Updaters` | `morphopt.codesign.Updaters` |
| 几何更新器（Updater 内层） | `morphopt.shapeopt.UpdaterGeometries` | — | `morphopt.codesign.UpdaterGeometries` |
| 材料更新器（Updater 内层） | — | `morphopt.simp.UpdaterMaterials` | `morphopt.codesign.UpdaterMaterials` |

（`—` 表示该方案不需要此类更新器：`shapeopt` 只挂几何更新器，`simp` 只挂材料更新器，`codesign` 两者都挂。）

## 2. ObjectiveFunction 怎么定义

功能：定义你的优化目标和监控指标。

最小实现要求：

- 在 `objective_function(self)` 返回标量 `torch.Tensor`。
- 如果目标依赖载荷雅可比，提前声明 `self.jacobian_needed = [...]`。

模板：

```python
class ObjectiveFunction(morphopt.shapeopt.ObjectiveFunction):  # simp/codesign 分别换成 morphopt.simp/codesign.ObjectiveFunction
    def __init__(self):
        super().__init__()
        self.jacobian_needed = ['force_1']

    def objective_function(self):
        # self.fe_results[i].GC 是第 i 个 load step 的位移自由度向量
        # self.fe_results[i].jacobian[...] 是对应雅可比
        return self.fe_results[0].GC.norm()

    def get_metrics(self):
        return [self.fe_results[0].GC[-1].item()]
```

实践建议：

- 多工况时把各工况目标统一放在 `objective_function` 里汇总。
- `get_metrics` 只放可视化指标，不参与梯度。

## 3. Params 怎么定义

`Params` 是三个子参数模块的聚合器：

- `GeometryParams`：几何定义与网格生成。
- `FEAParams`：载荷/边界/接触定义与工况幅值。
- `MaterialParams`：材料参数化与赋值。

模板：

```python
class Params(morphopt.shapeopt.Params):
    class GeometryParams(morphopt.shapeopt.GeometryParams):
        def __init__(self):
            super().__init__(fea_seed_size=1.0, mesh_order=1, reinitialize_per_iter=10)
            self.add_surface(self.BSP.initialize_cylinder(r0=10.0, length=50.0, seed_size=1.0))

    class FEAParams(morphopt.shapeopt.FEAParams):
        def define_interface(self):
            self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
            self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_0_All'), name='pressure_1')

        def define_steps(self):
            self.set_step_num(1)
            self.set_step_params(0, 'pressure_1', [0.06])

    class MaterialParams(morphopt.shapeopt.HomogeneousMaterial):
        def __init__(self):
            super().__init__(mu=0.48, kappa=4.8, density=1.08e-9)

    def __init__(self):
        super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())
```

### 3.1 GeometryParams 定义要点

功能：

- 维护曲面控制变量。
- 每次迭代生成新的网格 INP。
- 支持 `reinitialize` 做几何后处理。

你要做的事：

- 选择曲面类型（`BSP` 或 `CPGEO`）。
- `add_surface(...)` 注册所有参与几何的曲面。
- 需要时重写 `reinitialize(self, iteration)`。

### 3.2 FEAParams 定义要点

功能：

- 构建 FEA 接口集合。
- 管理多加载步参数。

你要做的事：

- 在 `define_interface()` 里注册所有接口。
- 在 `define_steps()` 里配置每步幅值。

常见接口：

- 压力：`PressureInterface`
- 接触：`ContactInterface`, `ContactSelfInterface`
- 力/力矩：`ConcentratedForceInterface`, `ConcentratedMomentInterface`
- 约束：`BoundaryConditionInterface`, `BoundaryConditionRPInterface`
- 耦合：`CoupleInterface`
- 参考点：`ReferencePointInterface`
- 体力：`BodyforceInterface`

### 3.3 MaterialParams 定义要点

功能：

- 把参数映射到材料本构。

两条路线：

1. 均质（shapeopt 用）：继承 `morphopt.shapeopt.HomogeneousMaterial`，直接给 `mu / kappa / density`。
2. 拓扑场（simp / codesign 用）：继承 `morphopt.simp.SIMP_BSPFieldMaterials`（codesign 里应继承 `morphopt.codesign.CodesignMaterials`）。

SIMP 场常见重写点：

- `_map_bsp_designfield(nodes)`：由 B 样条控制点场计算材料密度；可在里面加对称/旋转副本等自定义映射。
- `_map_bsp_designfield_with_spartial_derivative(nodes)`：配套的、输出含一阶空间导数的版本（灵敏度计算用）。

## 4. Solver 怎么定义

功能：调度多工况 FEA 求解。

通常只需设置并行参数：

```python
class Solver(morphopt.shapeopt.Solver):  # simp→morphopt.simp.SIMPSolver；codesign→morphopt.codesign.Solver
    def __init__(self, params: morphopt.shapeopt.Params):
        super().__init__(params=params, num_process=1)
```

你可以扩展：

- `task_index_list`：手动控制工况到进程的分配。
- `available_gpus`：多 GPU 场景下显式绑定。

## 5. Updater 怎么定义

功能：根据灵敏度更新设计变量。

`Updaters` 可以同时挂几何和材料更新器。

模板（以 codesign 为例——同时更新几何与材料）：

```python
class Updater(morphopt.codesign.Updaters):
    def __init__(self, params: morphopt.codesign.Params, *args, **kwargs):
        super().__init__(
            surfaces=self.UpdaterGeometries(params=params),
            materials=self.UpdaterMaterials(params=params),
            *args, **kwargs,
        )

    class UpdaterGeometries(morphopt.codesign.UpdaterGeometries):
        def __init__(self, params: morphopt.codesign.Params):
            super().__init__(params=params, max_step_iter=100)
            sd = self.objectivefuncs.ShapeDerivative()
            self.add_objective_function(sd)
            self.add_constraints(self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=sd))
            self.if_update = [True for _ in range(params.geometry.num_surface)]

    class UpdaterMaterials(morphopt.codesign.UpdaterMaterials):
        def __init__(self, params: morphopt.codesign.Params):
            super().__init__(params=params, max_step_iter=200, max_step_length=0.2)
            sens = self.objectivefuncs.Sensitivity(normalize_gradient=False)
            self.add_objective_function(sens)
            self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=0.001, threshold=0.0, p=2))
            self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=0.999, threshold=0.0, p=2))
            self.if_update = True
```

> 只做几何（shapeopt）：`Updater` 继承 `morphopt.shapeopt.Updaters`，只传 `surfaces=self.UpdaterGeometries(params=params)`（内层类继承 `morphopt.shapeopt.UpdaterGeometries`）。只做拓扑（simp）：`Updater` 继承 `morphopt.simp.Updaters`，只传 `materials=self.UpdaterMaterials(params=params)`（内层类继承 `morphopt.simp.UpdaterMaterials`）。

定义规则：

- 所有目标项用 `add_objective_function(...)`。
- 所有约束项用 `add_constraints(...)`。
- 通过 `if_update` 精细控制哪些变量被更新。

## 6. Codesign 模块怎么定义

如果你要做壳层偏移 + 材料协同设计，控制器内每个模块都用 codesign 前缀（见第 1 节对照表）：

- `ObjectiveFunction` → `morphopt.codesign.ObjectiveFunction`
- `Params` → `morphopt.codesign.Params`
  - `GeometryParams` → `morphopt.codesign.CodesignGeometry`
  - `FEAParams` → `morphopt.codesign.CodesignFEAParams`
  - `MaterialParams` → `morphopt.codesign.CodesignMaterials`
- `Solver` → `morphopt.codesign.Solver`
- `Updater` → `morphopt.codesign.Updaters`（内层 `UpdaterGeometries` / `UpdaterMaterials` 同样用 codesign 前缀）

codesign 里自定义 CPGEO 曲面类应继承 `morphopt.codesign.GeometryParams.CPGEO`；`MaterialParams` 常重写 `_map_bsp_designfield` 加入旋转对称副本。

几何约束可直接加：

- `morphopt.codesign.InwardCurvatureRadius(...)`
- `morphopt.codesign.OffsetSurfaceMinThickness(...)`

## 7. 迭代与重启机制

优化每次迭代主流程：

1. `params/solver/updater/objfun.reinitialize(...)`
2. 生成 FEA 模型
3. 多工况求解
4. 灵敏度分析
5. 更新几何/材料变量
6. 记录历史并保存快照

`restart_per_iteration` 控制多少步后自动退出并由外层任务进程继续，降低长时运行失败影响。

## 8. 输出与排错建议

输出目录核心子目录：

- `log/`：参数与历史。
- `cache/`：中间 INP。
- `fea/`：FEA 结果。
- `scripts/`：用于重启的脚本和依赖快照。

排错优先级：

1. 先检查 FEA 是否收敛。
2. 检查接口命名与 surface/set 是否一致。
3. 检查 `jacobian_needed` 是否覆盖目标函数所需项。
4. 检查约束权重与步长是否过激导致更新不稳定。

## 9. 参考实现

- shapeopt 完整示例：`examples/bendingactuator.py`
- simp 完整示例：`examples/gripper.py`
- 协同设计任务（壳偏移 + SIMP 材料）：`myjobs/codesign/`（如 `stiffness_twist_largemat.py`、`energy_contraction.py`）
- 目标函数与结果保存逻辑：`src/morphopt/optcore/objfunc.py`
- 几何 / 材料更新核心：`src/morphopt/shapeopt/update_geometry.py`、`src/morphopt/simp/update_material.py`
