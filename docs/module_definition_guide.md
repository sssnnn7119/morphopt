# 模块定义指南（how to define each module）

本文回答两个问题：

- 每个模块你应该怎么定义。
- 每个模块在优化流程里负责什么。

## 1. 总体思路

MorphOpt 的任务定义是“控制器驱动”的：

1. 你定义 `ThisController`。
2. 在控制器内定义四个模块：`ObjectiveFunction / Params / Solver / Updater`。
3. 通过 `morphopt.start_optimization(...)` 启动。

代码骨架：

```python
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='D:/Results', opt_label='MyTask')

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        ...

    class Params(morphopt.Params):
        ...

    class Solver(morphopt.MorphSolver):
        ...

    class Updater(morphopt.Updaters):
        ...
```

## 2. ObjectiveFunction 怎么定义

功能：定义你的优化目标和监控指标。

最小实现要求：

- 在 `objective_function(self)` 返回标量 `torch.Tensor`。
- 如果目标依赖载荷雅可比，提前声明 `self.jacobian_needed = [...]`。

模板：

```python
class ObjectiveFunction(morphopt.ObjectiveFunction):
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
class Params(morphopt.Params):
    class GeometryParams(morphopt.GeometryParams):
        def __init__(self):
            super().__init__(fea_seed_size=1.0, fea_mesh_order=1, reinitialize_per_iter=10)
            self.add_surface(self.BSP.initialize_cylinder(r0=10.0, length=50.0, seed_size=1.0))

    class FEAParams(morphopt.FEAParams):
        def define_interface(self):
            self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
            self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_0_All'), name='pressure_1')

        def define_steps(self):
            self.set_step_num(1)
            self.set_step_params(0, 'pressure_1', [0.06])

    class MaterialParams(morphopt.Materials):
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

1. 均质：继承 `morphopt.Materials`。
2. 拓扑场：继承 `morphopt.SIMPMaterials`。

SIMP 场常见重写点：

- `get_ratio(nodes)`：可加入对称性或自定义映射。
- `set_materials(fe)`：指定哪些单元使用该材料。

## 4. Solver 怎么定义

功能：调度多工况 FEA 求解。

通常只需设置并行参数：

```python
class Solver(morphopt.MorphSolver):
    def __init__(self, params):
        super().__init__(params=params, num_process=1)
```

你可以扩展：

- `task_index_list`：手动控制工况到进程的分配。
- `available_gpus`：多 GPU 场景下显式绑定。

## 5. Updater 怎么定义

功能：根据灵敏度更新设计变量。

`Updaters` 可以同时挂几何和材料更新器。

模板：

```python
class Updater(morphopt.Updaters):
    def __init__(self, params):
        super().__init__(
            surfaces=self.UpdaterGeometries(params=params),
            materials=self.UpdaterMaterials(params=params),
        )

    class UpdaterGeometries(morphopt.UpdaterGeometries):
        def __init__(self, params):
            super().__init__(params=params, max_step_iter=100)
            sd = self.objectivefuncs.ShapeDerivative()
            self.add_objective_function(sd)
            self.add_constraints(self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=sd))
            self.if_update = [True for _ in range(params.geometry.num_surface)]

    class UpdaterMaterials(morphopt.UpdaterMaterials):
        def __init__(self, params):
            super().__init__(params=params, max_step_iter=200, max_step_length=0.2)
            sens = self.objectivefuncs.Sensitivity(normalize_gradient=False)
            self.add_objective_function(sens)
            self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=0.001, threshold=0.0, p=2))
            self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=0.999, threshold=0.0, p=2))
            self.if_update = True
```

定义规则：

- 所有目标项用 `add_objective_function(...)`。
- 所有约束项用 `add_constraints(...)`。
- 通过 `if_update` 精细控制哪些变量被更新。

## 6. Codesign 模块怎么定义

如果你要做壳层偏移 + 材料协同设计，建议：

- `GeometryParams` 继承 `morphopt.codesign.CodesignGeometry`。
- `FEAParams` 继承 `morphopt.codesign.CodesignFEAParams`。
- `MaterialParams` 继承 `morphopt.codesign.CodesignMaterials`。

几何约束可直接加：

- `morphopt.codesign.InwardCurvatureRadius(...)`
- `morphopt.codesign.OffsetSurfaceMinThickness(...)`

## 7. 迭代与重启机制

优化每次迭代主流程：

1. `params/sovler/updater/objfun.reinitialize(...)`
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

- 完整协同设计示例：`examples/codesign/twist.py`
- 目标函数保存逻辑：`src/morphopt/optcore/objfunc.py`
- 几何与材料更新核心：`src/morphopt/optcore/updaters/`
