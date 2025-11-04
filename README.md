# 项目说明与使用指南

本仓库提供基于形状优化的工作流，集成了表面参数化、有限元（FEA）求解、载荷管理与目标函数组合。你可以复用示例快速搭建新任务，或扩展接口以支持更多场景。

目录：
- 安装与环境
- 项目结构
- 快速开始（运行示例）
- 如何定义一个优化问题（标准化工作流）
- 目标与更新器（Objective/Updater）
- 载荷接口一览（Pressure/Contact/Point）
- 日志与历史（History）
- GPU 与精度设置
- 性能建议
- 故障排查（FAQ）
- 贡献与许可证

## 安装与环境

前置条件：
- Python 3.10+（建议使用 conda 环境）
- Windows（已在 Windows+PowerShell 下验证），Linux 也可按需适配

安装依赖：
```powershell
# 可选：创建虚拟环境
conda create -n MorphOpt python=3.10 -y; conda activate MorphOpt

# 安装 Python 依赖
pip install -r requirements.txt
```

若使用 GPU，请确保已安装匹配的 PyTorch CUDA 版本。

## 项目结构

参考主要目录：
- `Jobs/`：示例与具体任务脚本（建议以 `Jobs/examples/displacement.py` 为模板）。
- `MorphOpt/`：核心库，包括参数、接口、求解器、更新器等。
- `Tests/`：简单的可视化/单元测试脚本。

你可以在工作区面板查看完整结构。

## 快速开始（运行示例）

运行位移示例（displacement）：
```powershell
python Jobs/examples/displacement.py
```

运行其他示例（如接触/抓取/运动学等），进入对应子目录执行相应脚本。

## 如何定义一个优化问题（标准化工作流）

下面介绍如何在本仓库中定义一个新的优化任务。请参考并对照示例脚本 `Jobs/examples/displacement.py`。

### 总体结构

每个任务脚本遵循统一结构：

1) 定义目标函数 ObjectiveFunction
- 继承自 `GLOBAL.ObjectiveFunction`，实现 `get_objective(self)`，并设置 `GLOBAL.obj_fun = ObjectiveFunction()`。

2) 定义参数容器 Params(_Params)
- 内含三个子类：
  - `SurfaceParams(_SurfacesParams)`：构建可优化的几何曲面（使用 `self.BSP.*` 初始化几何）。
  - `LoadParams(_LoadsParams)`：定义“所有需要的载荷接口”和“每个加载步的幅值参数”。
  - `MaterialParams(_Materials)`：设置材料参数（如 `mu`, `kappa`, `density`）。

3) 定义 Generator、Solver、Updater 与 Controller
- `Generator(_Generator)`：生成网格/中间数据（可设置 `seed_size`, `mesh_order` 等）。
- `Solver(_MorphSolver)`：负责调用 FEA；内部会一次性将所有载荷添加到 FEA 中，并在每个加载步切换载荷“幅值”，无需重复初始化模型。
- `Updater(_Updaters)`：包含 `UpdaterSurfaces(_UpdaterSurfaces)`，在其中添加/组合优化目标项（如形状导数、平滑、边界约束等）。
- `Controller(_Controller)`：组织整个优化循环。

4) 在 `__main__` 中初始化路径与历史、实例化各组件并执行 `controller.opt_loop()`。

### 曲面定义 SurfaceParams

在 `SurfaceParams` 中：
- 使用 `self.BSP.*` 工具函数构建一个或多个初始曲面，并通过 `self.add_surface(...)` 注册。
- 通过 `self.if_update = [...]` 指定哪些曲面参与更新。

示例（略化）：
```python
class SurfaceParams(_SurfacesParams):
    def __init__(self):
        super().__init__(max_step_length=[0.4, 0.4])
        self.add_surface(self.BSP.initialize_cylinder(r0=8., length=80., seed_size=1.0,
                                                      symmetric=[1, [1]], flip=False,
                                                      maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=12.))
        self.add_surface(self.BSP.initialize_cylinder(r0=4., length=74., seed_size=1.0,
                                                      symmetric=[1, [1]], init_location=[0, 0, 3],
                                                      flip=True, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=12.))
        self.if_update = [True, True]
```

### 载荷定义 LoadParams（关键：一次定义，分步调幅）

新的载荷定义方式遵循两个阶段：
- 阶段 A：注册“载荷接口”（仅定义类型/关联对象，不写死幅值）。
- 阶段 B：设置“步数”和“每个步的幅值”。求解时，FEA 只创建一次载荷对象，各步仅切换幅值，避免频繁重建/初始化。

LoadParams 提供以下方法：
- `add_load_interface(load_interface, name: str | None) -> str`
  - 注册一个载荷接口，返回其唯一名称（若未提供 name 会自动生成）。
- `set_step_num(num_steps: int)`
  - 设置加载步数量，并初始化各步的参数字典。
- `set_step_params(step_index: int, load_name: str, values: list[float])`
  - 为某个加载步的某个载荷设置幅值（如压力标量，力/力矩三分量等）。

常用载荷接口（均在 `MorphOpt/modelparams/loads/LoadInterface/` 下）：
- `PressureInterface(instance_name='final_model', surface_name='...')`
  - 幅值参数：`[pressure]`（单个浮点数）。
- `ConcentratedForceInterface(rp_name: str)`
  - 幅值参数：`[Fx, Fy, Fz]`（三个浮点数）。
  - 注意：类成员变量只存 Python list[float]，不使用 torch；仅在参数导出时转为张量。
- `ConcentratedMomentInterface(rp_name: str)`
  - 幅值参数：`[Mx, My, Mz]`。
- `ContactInterface(instance_name1, surface_name1, instance_name2, surface_name2, ...)`
  - 接触约束，一般不需要幅值；只需注册接口即可。
- `ContactSelfInterface(instance_name, surface_name, ...)`
  - 自接触约束，同样通常无幅值参数。

示例（等价于 `Jobs/examples/displacement.py` 的写法）：
```python
class LoadParams(_LoadsParams):
    def __init__(self):
        super().__init__()
        # A. 注册载荷接口（只定义对象，不写死幅值）
        self.add_load_interface(
            self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'),
            name='pressure_1'
        )

        # B. 定义步数与每步幅值
        self.set_step_num(1)
        self.set_step_params(0, 'pressure_1', [0.06])
```

Solver 会在 solve 时：
- 一次性用 `get_loads_fea()` 将全部载荷添加到 FEA。
- 每个步调用 `process_fea(fea, step_index)` 应用当前步的幅值；模型不需要每步重建、仅切换数值，效率更高。

### 材料参数 MaterialParams

示例：
```python
class MaterialParams(_Materials):
    def __init__(self):
        super().__init__(mu=0.482, kappa=4.8, density=1.08e-9)
```

### 生成器与求解器

- `Generator(_Generator)`：根据曲面生成中间数据；常见参数有 `seed_size`、`mesh_order` 等。
- `Solver(_MorphSolver)`：无需手动管理每步载荷添加/删除；内部已经采用“预定义载荷 + 分步调幅”的机制。

## 目标与更新器（Objective/Updater）

在 `Updater(_Updaters).UpdaterSurfaces(_UpdaterSurfaces)` 中：
- 创建形状导数（如 `ShapeDerivativeDirect(reset_per_iter=5)`）并注册：
  - `self.add_objective_function(shape_derivative)`
- 可叠加其它目标/正则（如 `Fairness`, `Distance`, `boundarys.Cylinder` 等）。

常见用法：
- 目标函数统一通过 `self.add_objective_function(...)` 注册。
- 多目标时，可通过权重在对应目标构造参数中体现。

## 载荷接口一览（Pressure/Contact/Point）

位置：`MorphOpt/modelparams/loads/LoadInterface/`

- PressureInterface：面压力，单一标量幅值。
- ContactInterface：外部接触；一般无幅值。
- ContactSelfInterface：自接触；一般无幅值。
- ConcentratedForceInterface：集中力，基于参考点名 `rp_name`，幅值为 `[Fx,Fy,Fz]`。
- ConcentratedMomentInterface：集中力矩，`rp_name`，幅值为 `[Mx,My,Mz]`。

注意：接口类内部仅存 Python list[float]；参数导出阶段再转为张量，便于优化器统一打包。

## 日志与历史（History）

- `initializer.initialize_path(...)` 会创建输出目录结构（如 `Results/`）。
- `initializer.initialize_history()` 管理迭代历史（`GLOBAL.History`）。
- 你可以在 `Jobs/...` 的脚本中设置任务名与输出路径，以便归档每次试验结果。

## GPU 与精度设置

- 默认使用 `torch.float64`；可在入口脚本中通过 `torch.set_default_dtype` 调整。
- 若可用 GPU，则内部会选择合适设备；也可在脚本中手动设置或屏蔽 CUDA（调试时可启用 `CUDA_LAUNCH_BLOCKING=1`）。

## 性能建议

- 预先“注册所有载荷”，并仅在步间切换幅值（已在 `LoadParams`/`Solver` 内实现）。
- 合理设置网格密度与曲面参数，避免过大规模导致 FEA 迭代缓慢。
- 多步求解时，确保每步仅修改必要的幅值，减少 FE 内部对象的重复构建。

## 故障排查（FAQ）

- 载荷无效/不生效？
  - 确认已通过 `add_load_interface` 注册；对有幅值的载荷在每个步都正确调用了 `set_step_params`。
- 接触相关错误？
  - 检查实例名与表面名是否与 INP/几何一致；必要时在 `Solver.init_FEA` 中自定义接触参数。
- GPU/精度导致的数值不稳定？
  - 可改回 CPU 或降低步长；确保所有张量 dtype 一致为 float64。

## 贡献与许可证

- 欢迎通过 PR/Issue 贡献新的载荷接口、目标函数或示例任务。
- 许可证与版权信息请参考仓库根目录中的相关文件（若缺失，请在提交 PR 时补充）。

---

更多参考：
- 示例：`Jobs/examples/displacement.py`
- 接触/集中载荷用法：`Jobs/locomotion/front.py`、`Jobs/ral2025contact/*`
- 载荷接口实现：`MorphOpt/modelparams/loads/LoadInterface/`
