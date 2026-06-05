# MorphOpt

**v3.1.5** — 面向软体结构/形态设计的可微分优化框架。

MorphOpt 将 **B-spline 几何参数化**、**SIMP 材料场**、**torchfea 有限元分析**、**多工况目标函数**和**设计变量更新**整合为一条可重启、可微分、可并行的优化流水线。核心包按优化类型拆分为三个子包：`shapeopt`（形状优化）、`simp`（SIMP 拓扑优化）、`codesign`（壳层协同设计）。

## 目录

- [项目特性](#项目特性)
- [架构概览](#架构概览)
- [安装](#安装)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [如何定义一个优化任务](#如何定义一个优化任务)
- [结果输出结构](#结果输出结构)
- [任务示例索引](#任务示例索引)
- [监控 UI](#监控-ui)
- [核心依赖](#核心依赖)
- [文档导航](#文档导航)

---

## 项目特性

- **可微分优化** — 基于 PyTorch 自动微分，几何/材料灵敏度端到端传播
- **双参数化引擎** — B-spline 曲面（`cpgeo`）+ SIMP 材料场（`bspmap`）
- **SIMP 拓扑优化** — 体素密度场，支持 RAMP 插值与梯度/扭曲惩罚
- **壳层 co-design** — 偏移曲面、多层壳单元、壳-体协同优化
- **多工况并行** — 多加载步 + 多任务并行求解（CPU / GPU）
- **自动重启** — 定时重启 Python 进程，避免内存泄漏
- **可视化** — PyQt6 + PyVista 3D 实时监控 UI

---

## 架构概览

```
Controller（优化主循环）
 |- Params（参数集合）
 |   |- BaseGeometry    -- 固定几何 / INP 导入
 |   |- FEAParams       -- 载荷 / 边界 / 接触定义
 |   |- HomogeneousMaterial -- 均质材料
 |- Solver       -- 多工况 FEA 求解
 |- ObjectiveFunction -- 目标函数 + 灵敏度分析
 |- Updaters（变量更新）
     |- BaseUpdater -- L-BFGS + 线搜索基类
```

**子包扩展：**

| 子包 | 几何 | 材料 | 更新器 |
|------|------|------|--------|
| `shapeopt` | `GeometryParams`（BSP 曲面） | -- | `UpdaterGeometries` |
| `simp` | -- | `SIMP_BSPFieldMaterials` | `UpdaterMaterials` |
| `codesign` | `CodesignGeometry`（偏移壳） | `CodesignMaterials` | 复用 shapeopt + simp |

**数据流（单次迭代）：**

```
Params.create_feamodel() -> Assembly
    |
Solver.solve(assembly) -> FEA Results
    |
ObjectiveFunction(FEA Results) -> Objective + Sensitivity
    |
Updaters.update(sensitivity) -> 新设计变量
    |
Params.reinitialize() -> 下一轮
```

---

## 安装

### 环境要求

- Python >= 3.12
- CUDA-compatible PyTorch（可选，GPU 加速）

### 安装步骤

```bash
git clone <repo-url>
cd morphopt
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

如需 GPU 支持，请安装匹配本机 CUDA 版本的 PyTorch。

---

## 快速开始

### 运行入门示例

```bash
# 形状优化
python examples/basic/shapeoptimization.py

# SIMP 拓扑优化
python examples/basic/simp.py
```

### 查看历史结果

```python
import morphopt
morphopt.view_optimization_result(path_result='path/to/result/folder')
```

### 编程入口

```python
import morphopt

# 启动优化（新进程）
morphopt.start_optimization(device='cpu', restart_per_iteration=20)

# 调试模式（当前进程，方便断点）
morphopt.debug_optimization(device='cpu')
```

---

## 如何定义一个优化任务

推荐在任务脚本中定义 `ThisController`，内嵌四个子类。

形状优化模板：

```python
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='./Results', opt_label='Demo')

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def objective_function(self):
            return self.fe_results[0].GC.norm()

    class Params(morphopt.Params):
        class GeometryParams(morphopt.shapeopt.GeometryParams):
            def __init__(self):
                super().__init__(fea_seed_size=1.0)
                self.add_surface(
                    self.BSP.initialize_cylinder(r0=8.0, length=40.0, seed_size=1.0)
                )

        class FEAParams(morphopt.shapeopt.FEAParams):
            def define_steps(self):
                self.set_step_num(1)

        class MaterialParams(morphopt.shapeopt.HomogeneousMaterial):
            def __init__(self):
                super().__init__(mu=0.48, kappa=4.8, density=1.08e-9)

        def __init__(self):
            super().__init__(
                geometry=self.GeometryParams(),
                feamodel=self.FEAParams(),
                materials=self.MaterialParams(),
            )

    class Solver(morphopt.shapeopt.Solver):
        def __init__(self, params):
            super().__init__(params=params, num_process=1)

    class Updater(morphopt.shapeopt.Updaters):
        def __init__(self, params):
            super().__init__(
                geometry=morphopt.shapeopt.UpdaterGeometries(params=params),
            )
```

详细指南见 `docs/module_definition_guide.md`，完整参考见 `examples/` 下的任务脚本。

---

## 结果输出结构

优化运行会在 `path_result_folder` 下创建时间戳目录：

```
EXAMPLE_T20260603_152535/
  cache/         # 临时文件（GMSH .brep/.inp 等）
  fea/           # FEA 中间结果
  log/           # 历史数据与迭代快照
    params/         # 迭代快照图片
    materials/      # 密度场快照
    deformation/    # 变形 STL
    <history files>
  scripts/       # 主脚本 + 依赖包快照（用于重启）
```

---

## 监控 UI

优化运行时可通过 `morphopt.start_optimization(enable_ui=True)` 启动 PyQt6 监控界面：

- **左侧表格** -- 迭代历史（目标值、时间、单元数、节点数）
- **右侧曲线** -- 目标函数 vs 迭代次数
- **下方 3D 视图** -- 几何表面 + 变形网格（可通过滑块切换迭代步）
- **暗色主题** -- 降低长时间观测的视觉疲劳

> Linux 下需使用 XCB 平台（`QT_QPA_PLATFORM=xcb`）以保证 VTK OpenGL 渲染兼容。

---

## 核心依赖

| 包 | 用途 |
|----|------|
| PyTorch 2.9.1 | 自动微分 + 张量计算 |
| torchfea >= 1.0.13 | 可微分有限元分析 |
| GMSH >= 4.15 | 网格生成 |
| cpgeo >= 1.0.12 | B-spline 曲面参数化 |
| bspmap >= 1.0.3 | B-spline 材料场映射 |
| PyVista >= 0.47 | 3D 可视化 |
| PyQt6 | GUI 界面 |
| PyPardiso | 稀疏线性求解器 |

完整依赖见 `pyproject.toml`。

---

## 文档导航

- `docs/module_definition_guide.md` -- 逐步教程：从零定义一个新的优化任务
- `docs/module_reference.md` -- 模块级 API 参考
- `docs/theory/` -- 学术论文与方法论

建议阅读顺序：**定义指南 -> 参考示例 -> 模块参考 -> 理论**。

---

## 引用

如果您在研究中使用了 MorphOpt，请引用以下论文：

- TRO 2023 -- Morphology Design
- TRO 2026 -- Jacobian-based Optimization
- TMECH 2026 -- Contact-aware Design
