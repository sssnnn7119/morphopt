# 00. 系统总览

返回 [设计导览](../README.md)。

## 目标与边界

MorphOpt 是一个以 TorchFEA 为数值后端的可微结构优化框架。用户在一个 `Controller` 子类中组合几何、FEA、材料、求解器和若干局部更新器；内核负责装配、求解、伴随/自动微分灵敏度、更新、快照和重启。UI 只编辑同一份声明式问题树并生成这个用户脚本。

`shapeopt` 提供可组合的边界 Part 与形状更新器，`simp` 提供 SIMP 材料与材料更新器。两类扩展都通过顶层 `morphopt` 的通用参数集合、运行时和协议组合到同一个优化问题中。

## 分层与允许依赖

```text
用户脚本 / 生成的 ThisController
              │
              ▼
Controller ─ Params ─ Solver ─ ObjectiveFunction ─ Updaters
              │                  │                    │
              ▼                  ▼                    ▼
       Geometry / FEA / Materials  TorchFEA Assembly   目标 Part 或材料接口
              │
              ├── shapeopt: BoundaryPartInterface / UpdaterBoundaryPart
              ├── simp: SIMP_BSPFieldMaterials / UpdaterSIMPMaterial
              └── codesign: 可选偏置壳扩展

UI: .morph ProblemDefinition → codegen → 用户脚本 → 同一运行时
```

依赖规则：

- `optcore` 不依赖 UI，也不按 shape/SIMP 分支。
- `shapeopt`、`simp` 依赖 `optcore`，只增加具体接口或更新器。
- `codesign` 依赖 shapeopt/SIMP，提供偏置壳协同设计的扩展能力；UI 当前将其作为预留能力。
- `ui/model` 不依赖 Qt；`ui/application` 不创建 widget；`ui/widgets` 不启动优化进程。

## 核心对象关系

```text
Controller
├── Params
│   ├── GeometryParams ──► BasePartInterface* ──► torchfea.Part + Instance*
│   ├── FEAParams      ──► BaseFEAInterface*
│   └── MaterialsParams──► BaseMaterialInterface*
├── Solver             ──► torchfea.FEAController results
├── ObjectiveFunction  ──► objective / gradients
├── Updaters           ──► BaseUpdater* ──► one designable interface each
└── History
```

星号表示有序的命名字典。名字在内核集合中是注册键；UI 内部则保留对象引用，只有保存 `.morph` 和生成 Python 时才投影为字符串。

## 一次优化迭代

```text
Controller.step()
  1. params / solver / updater / objective.reinitialize(iteration)
  2. geometry.generate() → Assembly
  3. feamodel.create_fea() + materials.set_materials() → FEAController.initialize()
  4. solver.solve() → 每个载荷步的 StaticResult
  5. objective.sensitivity_analysis(params) → {geometry, feamodel, materials}
  6. updaters.update(gradients) → 各局部 L-BFGS 子问题
  7. updaters.update_variables() → 写回 Part / SIMP 控制点
  8. objective.objective_function() → 本轮 loss
  9. History、Params、Updater、FEA 模型和结果快照保存
```

`geometry` 和 `materials` 的梯度按已注册的可更新接口顺序拼接；`Updaters` 按目标接口的变量数切片。接口注册顺序因此构成稳定的设计变量布局，并在一次优化过程中保持不变。

## 生命周期约定

| 阶段 | 责任 | 不变量 |
|---|---|---|
| 构造 | 保存声明参数；创建空容器 | 不建网格、不查运行时 Assembly、不创建昂贵缓存 |
| `initialize()` | 调用 `define_*` 钩子、绑定目标、创建首次状态 | 声明从空集合写入一次；名字和目标类型在此校验 |
| `reinitialize(iteration)` | 刷新当前迭代的曲面/载荷/材料状态 | 不重复注册接口 |
| `create_feamodel()` | 每轮构建 Assembly、FEA 和材料分配 | FEA 初始化前所有引用已解析 |
| `save/load()` | 保存设计状态与局部更新器状态 | 路径由各对象的 `pathlog_required()` 定义 |

## 命名、路径与持久化

- 一个 Geometry、FEA 或 Materials 集合拥有 `interfaces: dict[str, object]`；注册键即接口名。
- 一个 Part 接口可声明多个 Instance；默认 Instance 与 Part 同名，位姿为 `[0, 0, 0, 0, 0, 0]`。
- 结果目录由 `Controller.initialize_path()` 创建；`cache/` 是中间网格/几何工作区，`log/` 是可重启状态，其中 `femodel&results/` 存每轮匹配的 FEA 模型和结果。
- UI 的 `.morph` 是可编辑源格式；导出的 Python 是单向产物，不从 Python 回读业务模型。

## 设计原则

1. 一个状态只能有一个所有者。

2. 跨对象规则集中在聚合对象（内核集合或 `ProblemDefinition`），不散落在视图。

3. 每个设计对象由对应的 `BaseUpdater` 作为局部优化目标；全局 `Params` 负责统一注册与装配。

4. 运行时 Tensor 的设备切换覆盖一个 updater 的完整子问题，并在完成后恢复原设备。

5. 公开 API 使用 `morphopt.*`；子包是实现归属，而非另一层通用继承体系。
