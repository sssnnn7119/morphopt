# MorphOpt

MorphOpt 是一个面向软体结构/形态设计的优化框架，核心能力是把几何参数化、有限元分析（FEA）、多工况目标函数和设计变量更新整合到同一条可重启优化流水线中。

项目当前采用 `src` 布局，核心 Python 包在 `src/morphopt`，示例脚本在 `examples`，测试脚本在 `tests`。

## 目录

- 项目特性
- 环境与安装
- 项目结构（最新）
- 运行方式
- 如何定义一个优化任务
- 结果输出结构
- 依赖说明
- 文档导航

## 项目特性

- 基于 PyTorch/torchfea 的可微分优化流程。
- 支持多加载步（multistep）与并行求解。
- 支持几何变量与材料变量（SIMP 场）联合优化。
- 支持基于 `cpgeo`/`bspmap` 的曲面与材料场参数化。
- 提供 `codesign` 子模块用于壳层偏移、壳体体网格和相关约束。
- 内置结果监控 UI（PyQt6 + PyVista + Matplotlib）。

## 环境与安装

### Python 版本

- `>=3.12`（来自 `pyproject.toml`）

### 安装

```powershell
# 1) 创建虚拟环境（示例）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) 安装项目（开发模式）
pip install -e .
```

如果你希望使用 GPU，请安装与本机 CUDA 匹配的 PyTorch 版本。

## 项目结构（最新）

```text
MorphOpt/
  pyproject.toml
  README.md
  docs/
  examples/
    basic/
    codesign/
    locomotion/
    rigidflexible/
    tmech2025contact/
    tro2025workspace/
  scripts/
  src/
    morphopt/
      __init__.py
      opt_runner.py
      taskoptmization.py
      taskui.py
      codesign/
      optcore/
  tests/
```

## 运行方式

### 1) 直接运行示例脚本

```powershell
python examples/codesign/twist.py
```

### 2) 在脚本内部调用统一入口

脚本中通常通过以下入口启动：

```python
import morphopt

morphopt.start_optimization(device='cpu', restart_per_iteration=20)
```

常用入口函数：

- `morphopt.start_optimization(...)`：启动优化并可选择是否显示 GUI。
- `morphopt.debug_optimization(...)`：在当前进程中调试运行。
- `morphopt.view_optimization_result(path_result=...)`：加载历史结果并查看。

## 如何定义一个优化任务

推荐模式是在一个脚本里定义 `ThisController`，并在其中嵌套定义四类模块：

1. `ObjectiveFunction`
2. `Params`
3. `Solver`
4. `Updater`

最小结构如下：

```python
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='D:/Results', opt_label='Demo')

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()
            self.jacobian_needed = []

        def objective_function(self):
            return self.fe_results[0].GC.norm()

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):
            def __init__(self):
                super().__init__(fea_seed_size=1.0)
                self.add_surface(self.BSP.initialize_cylinder(r0=8.0, length=40.0, seed_size=1.0))

        class FEAParams(morphopt.FEAParams):
            def define_interface(self):
                pass

            def define_steps(self):
                self.set_step_num(1)

        class MaterialParams(morphopt.Materials):
            def __init__(self):
                super().__init__(mu=0.48, kappa=4.8, density=1.08e-9)

        def __init__(self):
            super().__init__(
                surfaces=self.GeometryParams(),
                feamodel=self.FEAParams(),
                materials=self.MaterialParams(),
            )

    class Solver(morphopt.MorphSolver):
        def __init__(self, params):
            super().__init__(params=params, num_process=1)

    class Updater(morphopt.Updaters):
        def __init__(self, params):
            super().__init__(
                surfaces=self.UpdaterGeometries(params=params),
                materials=self.UpdaterMaterials(params=params),
            )
```

更完整参考：`examples/codesign/twist.py`。

## 结果输出结构

优化运行会在 `path_result_folder` 下创建一个时间戳目录，包含：

- `cache/`：中间文件（如临时 INP）。
- `fea/`：FEA 相关输出。
- `log/`：历史数据与迭代快照。
- `scripts/`：用于重启的主脚本副本和依赖包快照。

`ObjectiveFunction.save(...)` 默认会输出变形图片和网格文件（当前实现支持 `.stl/.obj` 等常见格式）。

## 依赖说明

来自 `pyproject.toml` 的核心依赖：

- `torch>=2.0.0`
- `torchvision>=0.15.1`
- `numpy>=2.0.0`
- `scipy>=1.17.1`
- `torchfea>=1.0.8`
- `cpgeo>=1.0.5`
- `bspmap>=1.0.0`
- `gmsh>=4.15.0`
- `pyvista>=0.47.1`
- `vtk>=9.6.1`
- `pyvistaqt>=0.11.3`
- `pyqt6>=6.11.0`
- `trimesh>=4.11.5`
- `pypardiso>=0.4.7`
- `tabulate>=0.9.0`
- `imageio>=2.37.3`
- `networkx>=3.6.1`

## 文档导航

- `docs/README.md`：文档首页与索引。
- `docs/module_reference.md`：按包说明每个模块的职责与入口。
- `docs/module_definition_guide.md`：逐步说明“每类模块如何定义”。

如果你正在新增任务，建议先读 `docs/module_definition_guide.md`，再参考 `examples/codesign/twist.py` 落地实现。
