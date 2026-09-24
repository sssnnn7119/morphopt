# 模块定义指南（how to define each module）

本文回答两个问题：

- 每个模块你应该怎么定义。
- 每个模块在优化流程里负责什么。

## 1. 总体思路

MorphOpt 的任务定义是“控制器驱动”的：

1. 你定义 `ThisController`。
2. 在控制器内定义四个模块：`ObjectiveFunction / Params / Solver / Updater`。
3. 通过 `morphopt.start_optimization(...)` 启动。

代码骨架：通用模块全部直接继承顶层 `morphopt`；按需组合具体接口与更新器。

```python
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='D:/Results', opt_label='MyTask')

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        ...

    class Params(morphopt.Params):
        ...

    class Solver(morphopt.Solver):
        ...

    class Updater(morphopt.Updaters):
        ...
```

> **通用基类只从顶层 `morphopt` 继承**。`shapeopt` 与 `simp` 不是优化问题
> 基类层级；它们只实现可组合的具体 Part / 材料接口和更新器。

### 1.1 通用约定：构造函数轻量，解析放在 `initialize()`

声明式方法（`define_interface()` / `define_steps()` / `define_surfaces()` / `define_updater()`）只负责**登记对象**；
构造函数只保存原始参数（名字、数值、配置），不查表、不建模型、不算尺寸：

| 模块 | 构造函数只做 | 解析/构建发生在 |
|---|---|---|
| `Params` 集合（geometry / feamodel / materials） | 建空集合 | `initialize()` → `define_interface()` / `define_steps()`（只在集合为空时登记一次，可重复调用） |
| Part 接口 | 存 `part_name` / 实例名 / 网格参数 | `define_surfaces()`（初始化时调用一次）、`build_part()`（生成网格时） |
| 几何优化器 | 存 `interface_name` 字符串 | 注册时 `define_objective()`；`initialize()` → 统一解析目标 + `bind_target(target)` |
| 材料接口（SIMP） | 存材料参数与场参数 | `initialize()` 建 B 样条设计场与控制点 |
| 材料优化器 | 存 `interface_name` 字符串 | 注册时 `define_objective()`；`initialize()` → 统一解析目标 + `bind_target(target)` |
| `Updaters` | 存 `params` / `device`，跑 `define_updater()` | `initialize()` 逐个绑定目标并算尺寸 |

两条配套约定：

- **`initialize()` 之前集合是空的**：要读接口（`interfaces`）或 Part 曲面
  （`part.surface_interfaces()`）
  或要 `load()` 的脚本，得自己先调一次 `initialize()`（或 `controller.initialize()`）。
- `define_objective()` 在 updater 注册时调用一次；`initialize()` 只负责目标绑定和运行时准备。

好处：`Params()` / `Updater()` 可以随时构造（UI 预览、模型对比都不需要真网格）；名字写错只在
`initialize()` 报错——那时控制器已持有完整模型，可以直接给出“可选项列表”。

| 类型 | 顶层基类 |
|---|---|
| 控制器模块 | `morphopt.ObjectiveFunction` / `Params` / `Solver` / `Updaters` |
| 参数集合 | `morphopt.GeometryParams` / `FEAParams` / `MaterialsParams` |
| 边界曲面 Part | `morphopt.BoundaryPartInterface` |
| SIMP 密度场材料 | `morphopt.SIMP_BSPFieldMaterials` |
| 几何更新器 | `morphopt.UpdaterBoundaryPart` |
| 材料更新器 | `morphopt.UpdaterSIMPMaterial` |

不使用的接口和更新器不注册即可；同一问题可以同时有多个 Part、多个 Instance 和多个材料更新器。

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
- `MaterialsParams`：材料接口集合；每个接口独立指定 Part 和可选单元类型。

模板：

```python
class Params(morphopt.Params):
    class GeometryParams(morphopt.GeometryParams):
        class Body(morphopt.BoundaryPartInterface):
            def define_surfaces(self):
                self.add_surface_interface(
                    self.BSP.initialize_cylinder(r0=10.0, length=50.0, seed_size=1.0, flip=False))

        def define_interface(self):
            self.add_interface(self.Body(fea_seed_size=1.0, mesh_order=1), name='body')

    class FEAParams(morphopt.FEAParams):
        def define_interface(self):
            self.add_interface(self.BoundaryConditionInterface(instance_name='body', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
            self.add_interface(self.PressureInterface(instance_name='body', surface_name='surface_0_All'), name='pressure_1')

        def define_steps(self):
            self.set_step_num(1)
            self.set_step_params(0, 'pressure_1', [0.06])

    class MaterialsParams(morphopt.MaterialsParams):
        def define_interface(self):
            self.add_interface(
                self.HomogeneousMaterial(
                    material_parameters=self.materialmodels.NeoHookeanLnJParams(
                        mu=0.48, kappa=4.8),
                    density=1.08e-9,
                    part_name="body", elementname=""),
                name="body")

    def __init__(self):
        super().__init__(geometry=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialsParams())
```

### 3.1 GeometryParams 定义要点：一个 Part 接口

几何是三层结构：

1. `GeometryParams`：按名称保存的 **Part 接口字典**（`interfaces`），本身不关心曲面。
2. `BasePartInterface`：一个 **Part + 若干 Instance**。子类
   - `INPPartInterface`：直接读 Abaqus INP 网格；
   - `TorchFEAPartInterface`：读 torchfea 导出的模型目录（`torchfea.load_model`）；
   - `BoundaryPartInterface`（shapeopt/codesign）：由参数化曲面生成网格，**只有它有曲面**。
3. `SurfaceInterface`：属于 `BoundaryPartInterface` 的单个曲面（BSP / CPGEO / …）。

一个 Part 的 Instance 在 Part 内部定义，不再通过 GeometryParams 传一组平行
配置。基类默认创建一个与 Part 同名、位姿不变的 Instance。需要多个 Instance
时，只需覆盖 `define_instance()`，用六维指数坐标
`[tx, ty, tz, rx, ry, rz]` 调用 `add_instance()`：

```python
class Frame(morphopt.INPPartInterface):
    def define_instance(self):
        self.add_instance(self.part_name, "frame_left", [0, 0, 0, 0, 0, 0])
        self.add_instance(self.part_name, "frame_right", [0, 40, 0, 0, 0, 1.5708])
```

`rx/ry/rz` 直接作为 TorchFEA 的 rotation exponential coordinates（弧度）
传入。Part 名字默认就是注册名（`add_interface(..., name='body')`）。

**曲面写在哪里**：曲面的声明放在 Part 类里（`define_surfaces`），与其它模块的
`define_interface()` 一致：Part 初始化时调用一次，顺序即曲面索引顺序。曲面工厂
（`BSP` / `CPGEO` / `FixedSurface`）由 `BoundaryPartInterface`
自带，子类里 `self.BSP.…` 直接可用。Part 特有的辅助方法直接定义在对应的
Part 子类中：

```python
class GeometryParams(morphopt.GeometryParams):

    class CPGEO_Symmetry(morphopt.BoundaryPartInterface.CPGEO):  # 模型级自定义曲面类
        ...

    class BoundaryPart(morphopt.BoundaryPartInterface):
        """可优化实体：曲面参数化，一个 Part 两个曲面（0 外表面、1 内腔）。"""

        def define_surfaces(self):
            self.add_surface_interface(self.BSP.initialize_cylinder(
                r0=8.0, length=80.0, seed_size=0.8, flip=False,
                maxR=0.2, maxC=1.5, maxFF=0.2, perturbation_L=10.0))
            self.add_surface_interface(self.BSP.initialize_cylinder(
                r0=4.0, length=74.0, seed_size=0.8, init_location=[0, 0, 3], flip=True,
                maxR=0.2, maxC=1.5, maxFF=0.2, perturbation_L=10.0))

        def apply_surface_constraints(self):
            """每次几何更新后的等式约束（对称/周期…）。"""
            self.apply_symmetry(self.surface_interfaces()[0])

        def apply_symmetry(self, surface):
            ...

    def define_interface(self):
        # 可优化实体
        self.add_interface(
            self.BoundaryPart(fea_seed_size=1.0, mesh_order=1), name='body')

        # 固定实体：直接读 INP，一个 Part 两个 Instance
        frame = self.Frame(mesh_file='model/frame.inp')
        self.add_interface(frame, name='frame')
```

其他要点：

- 只有 `BoundaryPartInterface` 的子类才能被几何优化器更新；它的
  `apply_surface_constraints()` 是几何等式约束钩子（如对称/周期）。
- 曲面顺序即设计变量顺序：先按 Part 注册顺序，再按曲面注册顺序；几何优化器
  按 Part 切分梯度。
- 每个曲面在实例下的集合名约定为 `surface_<i>_<标签>`，FEA 接口按实例名 +
  集合名引用（`instance_name='body', surface_name='surface_0_All'`）。
- 可以在 `define_interface` 里直接 `part.add_surface_interface(...)`（UI 导出
  的旧脚本、运行时重建的模型仍然支持）；初始化时检测到已有曲面后，
  `define_surfaces` 不会再执行。

### 3.2 FEAParams 定义要点

功能：

- 构建 FEA 接口集合。
- 管理多加载步参数。

你要做的事：

- 在 `define_interface()` 里注册所有接口。
- 在 `define_steps()` 里配置每步幅值。
- 这两个钩子由 `initialize()` 调用（构造函数只建空集合），所以 `Params` 还没
  `initialize()` 时 `interfaces` / `fea_steps_params` 都是空的。

常见接口：

- 压力：`PressureInterface`
- 接触：`ContactInterface`, `ContactSelfInterface`
- 力/力矩：`ConcentratedForceInterface`, `ConcentratedMomentInterface`
- 约束：`BoundaryConditionInterface`, `BoundaryConditionRPInterface`
- 耦合：`CoupleInterface`
- 参考点：`ReferencePointInterface`
- 体力：`BodyforceInterface`

### 3.3 MaterialsParams 定义要点

功能：

- 把参数映射到材料本构，并把所有材料接口的设计变量聚合给优化器。

两条路线：

1. 继承 `morphopt.MaterialsParams`。
2. 在 `define_interface()` 中调用 `add_interface(...)` 注册一个或多个接口。
3. 均质材料使用 `HomogeneousMaterial`；SIMP 材料使用 `SIMP_BSPFieldMaterials`。

`part_name` 不能为空；`elementname=""` 表示该 Part 的所有单元类型。一个
codesign 材料集合通常注册两个接口：实体单元上的 SIMP 接口和 `C3D6` 上的
`HomogeneousMaterial` 接口。材料接口的设计变量由 `MaterialsParams` 自动拼接，
因此 `simp` 和 `codesign` 的 `UpdaterSIMPMaterial` 不需要额外适配。

每个材料接口通过 `material_parameters` 的参数对象选择 TorchFEA 本构模型，
不再单独传入 `material_model`。当前可选参数类型为
`self.materialmodels.LinearElasticParams`、`NeoHookeanParams`、
`NeoHookeanLnJParams`、`MooneyRivlinParams`、`YeohParams`、`GentParams`、
`ArrudaBoyceParams` 和 `OgdenParams`；参数对象的类名同时决定材料模型。
这些参数类型由 `MaterialsParams.materialmodels` 提供，不需要从顶层
`morphopt` 导入。
模型所需的参数使用对应的参数类型传入，例如：

```python
self.HomogeneousMaterial(
    material_parameters=self.materialmodels.MooneyRivlinParams(
        c10=0.24, c01=0.12, kappa=4.8),
    density=1.08e-9,
    part_name="body")
```

SIMP 接口也使用相同的模型选择；例如 Yeoh 模型的参数通过对应类型传入：

```python
morphopt.SIMP_BSPFieldMaterials(
    material_parameters=self.materialmodels.YeohParams(
        c1=0.48, c2=0.0, c3=0.0, kappa=4.8),
    mumax=10.0, kappamax=100.0,
    simp_ratio_min=1e-7,
    bounding_box=[0, 20, 0, 10, 0, 5],
    simp_field_resolution=0.5, degree=2,
    density=1.08e-9,
    part_name="body")
```

SIMP 场常见重写点：

- SIMP 的 B 样条映射由材料接口内部统一完成；材料节点只配置设计域、分辨率、阶次和材料参数。
- 对称等式约束应作为材料更新器的约束项注册，不应修改内部映射函数。

## 4. Solver 怎么定义

功能：调度多工况 FEA 求解。

通常只需设置并行参数：

```python
class Solver(morphopt.Solver):
    def __init__(self, params: morphopt.Params):
        super().__init__(params=params, num_process=1)
```

你可以扩展：

- `task_index_list`：手动控制工况到进程的分配。
- `available_gpus`：多 GPU 场景下显式绑定。

## 5. Updater 怎么定义

功能：根据灵敏度更新设计变量。

`Updaters` 把子优化器维护成一个**字典**：所有子优化器行为一致（各自拥有一个更新
对象、只吃自己那一片梯度、各自保存状态）。声明在**一个钩子** `define_updater()` 里完成，
“更新的是几何还是材料还是载荷”由**用哪个 add 方法**说明，一眼可见、不用猜：

| 注册方法 | 更新的集合 | 梯度键 |
|---|---|---|
| `add_geometry_updater(updater, name=None)` | `params.geometry` | `geometry` |
| `add_material_updater(updater, name=None)` | `params.materials` | `materials` |

不带名字时默认命名为 `<类名>_<序号>`（`UpdaterBoundaryPart_0`、`UpdaterSIMPMaterial_1`…）。
每个子优化器**指向自己的更新对象**，而且“哪一类 params 的哪个 interface”完全由**注册那两行**说清楚：

- 更新哪一类集合（`"geometry"` / `"materials"`）：由**用的哪个注册方法**钉死
  （`add_geometry_updater` ⇒ `geometry`），也就是 `update_kind`（同时作为梯度键）；
- 该集合里的哪个 interface（几何 = Part 名，材料 = 材料接口名）：就是 `add_*_updater(...)` 的 **`name`**。

**核对关系是双向的**：`update_kind` 由所用基类继承（`UpdaterBoundaryPart` → `geometry`，
`UpdaterSIMPMaterial` → `materials`），注册时会校验“基类声明的种类”和“注册用的方法”是否一致——
把几何优化器塞进 `add_material_updater()` 会直接报错，不会默默地切错梯度。

**updater 类本身不写目标**，所以同一个类可以对不同对象分别优化不同的 Part；目标与目标函数分开声明：构造只给“自己的超参”，目标/约束写在 `define_objective()` 里（和 `define_interface()` 对称，由注册方法调用一次）：

```python
class Updater(morphopt.Updaters):
    def define_updater(self) -> None:
        # 同一个类，两个对象，各自优化自己的 Part
        self.add_geometry_updater(self.Shape(), name='body')
        self.add_geometry_updater(self.Shape(), name='leg')

    class Shape(morphopt.UpdaterBoundaryPart):
        def __init__(self, interface_name=None):
            super().__init__(interface_name=interface_name, max_step_iter=200)

        def define_objective(self) -> None:
            self.add_objective_function(self.objectivefuncs.ShapeDerivative())
            self.add_constraints(self.objectivefuncs.Fairness())
```

上面两个对象各自解析到 `params.geometry` 的 `body` / `leg`，梯度切片、状态目录
（`log/geometryupdater/<interface>/`）也各自分开。

如果注册名和 interface 名确实需要不同（例如字典键想叫 `arm` 而 Part 叫 `body`），
就在构造时显式给出，它会胜过注册名：

```python
self.add_geometry_updater(self.Shape(interface_name='body'), name='arm')
```

**“从哪个集合里找这个 interface”是明确的**：初始化时（`Updaters.initialize()`）每个
更新器只会收到**自己那一类集合**（`params.geometry` / `params.materials`），它在这个
集合里按名字取出自己的 interface，并且**只保留那一个
interface**（`self.part` / `self.material`），不再持有集合或 `params`：

```python
collection.interfaces['body']
collection.interface('solid')       # MaterialsParams.interface(name)
```

写错名字会在 `initialize()` 立即报错并列出可用名；没写名字、而该集合里只有
“唯一一个可设计的目标”时，也可以省略（自动采用唯一的那个）。

模板（codesign：两个 Part 各一个几何优化器，两个材料接口各一个材料优化器）：

```python
class Updater(morphopt.codesign.Updaters):
    def define_updater(self) -> None:
        self.add_geometry_updater(self.UpdaterBoundaryPart(), name='body')
        self.add_geometry_updater(self.UpdaterBoundaryPartFrame(), name='frame')
        self.add_material_updater(self.UpdaterSIMPMaterial(), name='solid')
        self.add_material_updater(self.UpdaterSIMPMaterialShell(), name='shell')

    def __init__(self, params: morphopt.codesign.Params):
        super().__init__(params=params, device='cuda:0')

    class UpdaterBoundaryPart(morphopt.codesign.UpdaterBoundaryPart):
        def __init__(self):
            super().__init__(max_step_iter=100)

        def define_objective(self) -> None:
            self.add_objective_function(self.objectivefuncs.ShapeDerivative())
            # 约束只作用于本更新器自己的 Part，因此不需要再传 surfaces
            self.add_constraints(self.objectivefuncs.Fairness())

    class UpdaterBoundaryPartFrame(morphopt.codesign.UpdaterBoundaryPart):
        def __init__(self):
            super().__init__(max_step_iter=80)

        def define_objective(self) -> None:
            self.add_objective_function(self.objectivefuncs.ShapeDerivative())
            self.add_constraints(self.objectivefuncs.Fairness())

    class UpdaterSIMPMaterial(morphopt.codesign.UpdaterSIMPMaterial):
        def __init__(self):
            super().__init__(max_step_iter=200, max_step_length=0.2)

        def define_objective(self) -> None:
            self.add_objective_function(self.objectivefuncs.Sensitivity(normalize_gradient=False))
            self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=0.001, threshold=0.0, p=2))
            self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=0.999, threshold=0.0, p=2))
            self.if_update = True

    class UpdaterSIMPMaterialShell(morphopt.codesign.UpdaterSIMPMaterial):
        def __init__(self):
            super().__init__(max_step_iter=100)

        def define_objective(self) -> None:
            self.add_objective_function(self.objectivefuncs.Sensitivity())
```

（上面 `define_updater()` 里的 `name='body'` / `name='frame'` 就是说“这个对象优化哪个 Part”；
两个几何类不同是因为它们的目保/约束不同——如果完全一样，完全可以只写一个类、注册两次。）

> 只做几何时只注册 `add_geometry_updater(...)`；只做拓扑时只注册
> `add_material_updater(...)`。两者都直接继承 `morphopt.Updaters`，不使用的
> 注册方法不写即可。

定义规则：

- **每个子优化器在注册时点名自己的目标**：`add_geometry_updater(self.Shape(), name='body')`
  （材料同理 `add_material_updater(..., name='solid')`）——这个 `name` 既是字典键，也是它拥有的 interface。
  需要覆盖注册名时，用 `interface_name=` 在构造时指定。
  完全没有名字时，如果该集合里只有唯一一个可设计目标，就自动用它。
- 构造函数只收自己的旋钮（`max_step_iter` / `max_step_length` / …）：**目标在
  `initialize()` 由集合交接、按名字解析**（controller 在循环前调用）。名字写错会在
  初始化时立即报错并列出可用名；updater 始终不持有 `params` 或集合。
- 目标 / 约束不是写在 `__init__` 里，而是写在 `define_objective()` 中（和
  `define_interface()` 对称，由注册方法调用一次）：所有目标项用
  `add_objective_function(...)`，所有约束项用 `add_constraints(...)`。
- 通过 `if_update` 精细控制哪些变量被更新（几何：长度 = 本 Part 的曲面数；材料：bool）。
- 子优化器彼此独立：梯度按各自目标切片（几何按 Part、材料按材料接口），状态分别
  保存在 `log/geometryupdater/<interface_name>/`、`log/materialupdater/<interface_name>/`。
- `add_geometry_updater` / `add_material_updater` 的 `name` 省略时按
  注册顺序自动编号（`<类名>_<序号>`）；同名会直接报错。
  已注册的子优化器直接保存在 `updaters` 字典中。
## 6. Codesign 模块怎么定义

如果你要做壳层偏移 + 材料协同设计，控制器内每个模块都用 codesign 前缀（见第 1 节对照表）：

- `ObjectiveFunction` → `morphopt.codesign.ObjectiveFunction`
- `Params` → `morphopt.codesign.Params`
  - `GeometryParams` → `morphopt.codesign.GeometryParams`
  - `FEAParams` → `morphopt.codesign.CodesignFEAParams`
  - `MaterialsParams` → `morphopt.codesign.MaterialsParams`
- `Solver` → `morphopt.codesign.Solver`
- `Updater` → `morphopt.codesign.Updaters`（内层 `UpdaterBoundaryPart` / `UpdaterSIMPMaterial` 同样用 codesign 前缀）

codesign 里自定义 CPGEO 曲面类应继承
`morphopt.codesign.CodesignBoundaryPartInterface.CPGEO`；
SIMP 材料的空间映射属于内核实现，不在 UI 的材料节点中编辑。

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
- 几何 / 材料更新核心：`src/morphopt/shapeopt/update_boundarypart.py`、`src/morphopt/simp/update_simpmaterial.py`
