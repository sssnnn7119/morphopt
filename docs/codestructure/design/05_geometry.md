# 05. 几何

返回 [设计导览](../README.md)。

## 领域模型

几何层将一个或多个 Part 接口转化为 `torchfea.Assembly`。一个 Part 接口负责构建一个 `torchfea.Part`，并在同一接口内声明该 Part 的一个或多个 Instance。Instance 的名称和位姿属于几何声明，FEA 载荷以 instance 名称引用这些实体。

```text
GeometryParams.interfaces
  └── BasePartInterface
       ├── build_part() ──► torchfea.Part
       └── define_instance()
            └── (part_name, instance_name, [tx, ty, tz, rx, ry, rz])*
                    └── torchfea.Assembly.add_instance()
```

## `BasePartInterface`

源码：`optcore/modelparams/partinterface/basepartinterface.py`；继承 `BaseParams`。子类只需实现 `build_part()`；它们可以覆写 `define_instance()` 声明多个独立位姿。

| 属性 | 可见性 | 说明 |
|---|---|---|
| `cache_part` | 类属性 | 固定几何设为 `True`，允许复用已导入的 Part。 |
| `name` | 公开只读属性 | GeometryParams 中的注册名。 |
| `part_name` | 公开属性 | Assembly 内 Part 名；未显式设置时使用 `name`。setter 会清除 Part 缓存。 |
| `exterior_surface` | 公开 | Part 的外表面集合名，可为 `None`。 |
| `instance_names` | 公开只读属性 | 已声明 instance 名称列表。 |
| `_instance_definitions` | 私有 | `(part_name, instance_name, pose)` 列表。 |
| `_part` | 私有 | 固定 Part 的缓存。 |

| 公开方法 | 职责 |
|---|---|
| `define_instance()` | 声明默认 identity instance：Part 名与 instance 名相同，位姿为六个零。 |
| `add_instance(part_name, instance_name, translations_rotations)` | 添加一个 instance；位姿严格为 `[tx, ty, tz, rx, ry, rz]`。后三项为 TorchFEA 指数坐标旋转。 |
| `initialize()` | 清空旧定义，执行一次 `define_instance()`。 |
| `build_part(path_result=None, pools=None)` | 子类构建或导入 Part 的实现点。 |
| `get_part(...)` | 根据 `cache_part` 返回缓存或调用 `build_part()`。 |
| `add_to_assembly(assembly, ...)` | 添加 Part、外表面与全部已声明 instances。 |
| `generate(...)` | 创建只含当前 Part 接口的独立 Assembly，适用于局部预览。 |
| `workdir(path_result)` | 返回该接口的几何缓存工作目录。 |
| `pathlog_required()` | 返回 `['geometry']`。 |

`add_instance()` 校验 instance 名在一个 Part 接口中唯一，也校验每项位姿恰为六个浮点数。`add_to_assembly()` 再校验声明中的 `part_name` 与该接口实际生成的 Part 名一致，从而让跨 Part 的引用在装配时得到明确诊断。

## 多 Instance 位姿

```python
class Bracket(morphopt.TorchFEAPartInterface):
    def define_instance(self) -> None:
        self.add_instance(self.part_name, "left", [0, 0, 0, 0, 0, 0])
        self.add_instance(self.part_name, "right", [80, 0, 0, 0, 0, 3.14159])
```

几何接口名称、Part 名、instance 名是三个不同层级：接口名用于集合注册和保存路径，Part 名用于 `Assembly.get_part()` 与材料分配，instance 名用于载荷、接触和约束定位。UI 在内存中保存对象引用，生成脚本时将这些关系投影为上述名称。

## 固定网格 Part：`INPPartInterface`

源码：`inppartinterface.py`；继承 `BasePartInterface`，`cache_part=True`。

| 构造状态 | 说明 |
|---|---|
| `mesh_file` | Abaqus `.inp` 网格文件路径；构造时检查存在性。 |
| `inp_part_name` | 文件内 Part 名；为 `None` 时文件必须只有一个 Part。 |
| `part_name`、`exterior_surface` | 基类几何注册与外表面配置。 |

`build_part()` 通过 `torchfea.FEA_INP` 读取输入文件、选择文件内 Part，并将 `exterior_surface` 应用到导入结果。该类型适合固定网格几何和外部网格流程。

## TorchFEA 存档 Part：`TorchFEAPartInterface`

源码：`torchfeapartinterface.py`；继承 `BasePartInterface`，`cache_part=True`。

| 构造状态 | 说明 |
|---|---|
| `model_directory`、`model_filename` | TorchFEA `.npz` 存档位置；文件名为空时选择目录中最新存档。 |
| `model_path` | 已解析的绝对存档路径。 |
| `model_part_name` | 存档内选中的 Part 名。 |
| `_source_instances` | 存档中属于选中 Part 的 instance 位姿，用于复建。 |

| 公开成员 | 职责 |
|---|---|
| `define_instance()` | 复制选中 Part 的存档 instances；无来源 instance 时使用基类默认。 |
| `for_all_parts(directory, filename='')` | 为存档内每个 Part 创建一个接口。 |
| `build_part()` | 每次从存档加载并取出选中 Part。 |
| `resolve_model_path(...)` | 解析一个 `.npz` 文件。 |
| `load_model_assembly(...)` | 加载存档并规范到当前 Torch 默认设备，返回有效 Assembly。 |

导入的存档只提供 Part 和其放置；载荷、材料、求解器均由当前 MorphOpt 问题重新声明。这让同一几何资产能服务于多个优化问题。

## 几何构建与缓存

```text
Params.create_feamodel(path_result)
  └─ GeometryParams.generate(path_result, pools)
       ├─ Assembly()
       └─ 每个 PartInterface.add_to_assembly()
            ├─ get_part() / build_part()
            ├─ Assembly.add_part()
            └─ Assembly.add_instance() × n
```

固定 Part 把 `_part` 缓存在内存；可变边界 Part 每轮重建网格。`workdir()` 将每个接口的网格、STEP、INP 等中间产物放进其专属缓存目录，使多 Part 并行建模不会使用同名文件。

## 重命名契约

Part 接口重命名后，未显式设置的 `part_name` 随注册名更新；默认 instance 也在下一次 `initialize()` 中使用新 Part 名。显式 Part 名和自定义 instance 名保持为接口声明的一部分。UI 领域模型保存目标对象关系，并在序列化、代码生成和 Assembly 建立前将其投影为当前名称。
