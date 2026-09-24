# 06. 材料

返回 [设计导览](../README.md)。

## 领域边界

材料层把一个参数化材料模型分配给某个 Part 的一个或多个元素族。`MaterialsParams` 统一注册材料接口并在 FEA 初始化前调用 `set_materials(fe)`；材料接口通过 `part_name` 与几何 Part 关联，而不通过 instance 名关联。

```text
MaterialsParams.interfaces
  └── BaseMaterialInterface
       ├── target_elements(assembly)
       └── set_materials(fea)
              └── elements.set_materials(torchfea material)
```

## `BaseMaterialInterface`

源码：`optcore/modelparams/materialinterface/basematerialinterface.py`；继承 `BaseParams`。

| 属性 | 可见性 | 说明 |
|---|---|---|
| `part_name` | 公开 | 目标 Assembly Part 名，构造时要求非空。 |
| `elementname` | 公开 | 目标元素族名；空字符串表示 Part 内全部元素族。 |
| `material_parameters` | 公开 | `MaterialModels.MaterialParameters` 的冻结 dataclass。 |
| `density` / `_density` | 公开属性/私有存储 | 质量密度。 |
| `name` / `_name` | 公开属性/私有存储 | MaterialsParams 分配的注册名。 |

| 公开方法 | 职责 |
|---|---|
| `target_elements(assembly)` | 解析目标 Part 和元素族，返回 `(name, elements)` 列表。 |
| `set_materials(fe)` | 子类将材料分配到目标元素的实现点。 |
| `get_design_values()` | 可设计材料提供活跃设计值；均质材料返回空 Tensor。 |

材料接口也继承 `BaseParams` 的标准持久化、可视化和接口容器行为。均质材料不注册子接口；SIMP 材料将其设计场状态保存在自身属性中，详见 [08 SIMP 材料优化](08_simp.md)。

## `HomogeneousMaterial`

源码：`homogeneousmaterial.py`；继承 `BaseMaterialInterface`。

`set_materials(fe)` 针对 `target_elements(fe.assembly)` 中的每个元素族执行以下操作：清除已有材料，调用 `MaterialModels.create_material(material_parameters)` 生成 TorchFEA 材料，并设置元素密度。`HomogeneousMaterial` 表达固定材料分配，设计变量数量为零；SIMP 材料在 [08 SIMP 材料优化](08_simp.md) 中提供可更新实现。

## `MaterialModels`

源码：`materialmodels.py`。`MaterialModels` 是参数类型命名空间；嵌套的冻结 dataclass 把所需的本构参数与对应 TorchFEA 材料类绑定。

| 参数类型 | 字段 | TorchFEA 材料 |
|---|---|---|
| `LinearElasticParams` | `E`, `nu` | `LinearElastic` |
| `NeoHookeanParams` | `mu`, `kappa` | `NeoHookean` |
| `NeoHookeanLnJParams` | `mu`, `kappa` | `NeoHookeanLnJ` |
| `MooneyRivlinParams` | `c10`, `c01`, `kappa` | `MooneyRivlin` |
| `YeohParams` | `c1`, `c2`, `c3`, `kappa` | `Yeoh` |
| `GentParams` | `mu`, `Jm`, `kappa` | `Gent` |
| `ArrudaBoyceParams` | `mu`, `N`, `kappa` | `ArrudaBoyce` |
| `OgdenParams` | `mu`, `alpha`, `kappa` | `Ogden` |

共同基类 `MaterialParameters` 以 `material_class` 这个 `ClassVar` 指向后端本构类型。`create_material(material_parameters)` 利用 dataclass 字段构造相应的 TorchFEA 材料，因此参数对象是声明式、可序列化且不可变的。

## 分配顺序与覆盖范围

```text
Params.create_feamodel()
  ├─ geometry.generate()          → Assembly
  ├─ feamodel.create_fea(Assembly)→ FEAController
  └─ materials.set_materials(FEAController)
       └─ 每个材料接口按注册顺序分配
```

材料接口的注册顺序表达元素材料的覆盖顺序。针对同一元素族的多个接口，后注册接口会在该元素族上执行后一次分配；一个问题应采用清晰的元素分区或明确的覆盖意图。运行时材料接口以 `part_name` 字符串定位 Assembly Part；UI 领域模型保存目标 Part 对象关系，并在重命名或生成 Python 时同步得到当前字符串。

## 新材料接口的实现检查表

1. 继承 `BaseMaterialInterface`，构造函数接收目标 Part、元素选择、材料参数和密度，并调用 `super().__init__()`。
2. 实现 `set_materials(fe)`；以 `target_elements(fe.assembly)` 获取所有目标元素。
3. 若材料可设计，同时实现 `ProtocalUpdatable`，使设计变量顺序、材料投影、灵敏度变量和保存状态保持一致。
4. 在用户 `MaterialsParams.define_interface()` 中用 `add_interface()` 注册，供 UI 模型和运行时使用同一名称。
