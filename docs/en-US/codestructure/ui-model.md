# UI domain model

[简体中文](../../zh-CN/codestructure/ui-model.md)

[Code structure overview](README.md)  ·  [UI Application Services](ui-application.md)  ·  [UI display and refresh mechanisms](ui-presentation.md)

## Contents

<!-- docs:toc depth=1 -->

- [1 Source code entry point](#section-源码入口)
- [2 Define the tree structure and navigation tree.](#section-定义树与导航树)
- [3 Types, fields, and registration](#section-类型字段与注册)
- [4 Object reference and name projection](#section-对象引用与名称投影)
- [5 Aggregation operations and structural invariants](#section-聚合操作与结构不变量)
- [6 `.morph` Boundaries and compatibility considerations](#section-morph-边界与兼容处理)
- [7 Interface projection for named operating conditions](#section-具名工况的接口投影)
- [8 Weight field and solver parameters](#section-分量字段与求解器参数)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 Source code entry point

| Path | Responsibility |
|---|---|
| [`ui/model/base_nodes.py`](../../../src/morphopt/ui/model/base_nodes.py) | Generic Node and Field Access Classes, as well as Base Classes for Node Families |
| [`ui/model/node_types/`](../../../src/morphopt/ui/model/node_types) | Specific nodes that can be made persistent. |
| [`ui/model/fields.py`](../../../src/morphopt/ui/model/fields.py) | Immutable field metadata: `FieldSpec` |
| [`ui/model/registry.py`](../../../src/morphopt/ui/model/registry.py) | Kind, polymorphic families, and menu type registration |
| [`ui/model/problem.py`](../../../src/morphopt/ui/model/problem.py) | `ProblemDefinition` Aggregation and cross-node operations |
| [`ui/model/configuration.py`](../../../src/morphopt/ui/model/configuration.py) | Creating objects with default configurations like updaters. |
| [`ui/model/loaders.py`](../../../src/morphopt/ui/model/loaders.py) | `.morph` file boundaries |
| [`ui/model/material_models.py`](../../../src/morphopt/ui/model/material_models.py) | Description of backend material models and visible parameters |

<a id="section-定义树与导航树"></a>

## 2 Define the tree structure and navigation tree.

`ProblemDefinition` is a definable aggregate root that includes problem tags, paths, devices, persistent node trees, auxiliary code, and custom classes.

```text
ProblemDefinition
├── root: ProblemNode
│   ├── GeometryNode → PartNode*
│   │   ├── instances: InstanceNode*
│   │   ├── surfaces: SurfaceNode*       Only boundary components
│   │   └── operations: CADOperationNode*Only CAD components
│   ├── LoadsNode → FEAComponentNode*
│   ├── StepsNode
│   ├── MaterialsNode → MaterialNode*
│   ├── ObjectiveNode
│   ├── SolverNode
│   └── UpdaterNode → geometry / materials Configuration list
├── helper_code / helper_variables / helper_functions
└── custom_classes / class_bindings
```

The asterisk indicates an ordered set. The node tree represents the model content. The Controller, Params, auxiliary code groups, and updater entries in the interface are represented by `presentation/navigation.py`. Temporary navigation nodes are not inserted into the persistent tree, and do not change the chapter structure of `.morph`.

`Node.children` provides a unified way of traversal. The actual sub-objects are stored by the explicit typed members of each container, such as `parts`, `instances`, `surfaces`, and `operations`. Leaf nodes do not accept any sub-nodes, while the root node maintains a unique standard structure.

<a id="section-类型字段与注册"></a>

## 3 Types, fields, and registration

| mechanism | agreement |
|---|---|
| `kind` | Stable types of nodes, used for routing and serialization purposes. |
| Specific Python classes | Specifies the type of elements, surfaces, materials, or loads involved in the analysis. |
| `fields` | Field metadata, which describes information such as the key, default value, editing type, and tags. |
| Typed properties | Save the actual field values and object references. |
| `NODE_TYPES` | Restores the node type corresponding to the unique kind. |
| `NODE_FAMILIES` | Restoring polymorphic types under the shared kind |

The specific fields are declared in `node_types/`, and the data type of the fields is provided by `model/fields.py`. Shared metadata is consumed by model nodes, dynamic forms, menus, and generators. Any changes to the enumeration values or default values of the fields should be checked against the backend parameter contract.

`Node.custom_class` Save the custom classes used for the selected nodes. The root-level configuration and sub-optimizers still use their respective binding positions. For detailed generation rules, please refer to [Custom class](ui-application.md#custom-classes) .

<a id="section-对象引用与名称投影"></a>

## 4 Object reference and name projection

Domain relationships stored in memory retain object references. These references are then persisted and transformed into meaningful names during code generation.

| relationships | Memory targets | Boundary name |
|---|---|---|
| Load → Instance/RP/Surface | Corresponding nodes | `instance_name`, `rp_name`, `surface_name`, etc. |
| Materials → Parts | Part node | `part_name` |
| Geometric Updater → Part | Target node in configuration | Target Part Name |
| Material Updater → Material Interface | Target node in configuration | Name of the target material |
| Objective/Jacobian → Load or RP | Corresponding references | The name used to generate the script |

`resolve_references()` Restore the object relationships based on the boundary names, and clear any invalid associations. Unresolved name and object references should be handled separately. It is not possible to restore references using the display titles with class names.

The UI Part has only one editable name, `assembly_name` is a derived value. `rename_part()` does not change the existing instance name; the instance is independently renamed using `rename_instance()`. The material andUpdater hold references to the Part object, and the Part’s name is read after the renaming.

<a id="section-聚合操作与结构不变量"></a>

## 5 Aggregation operations and structural invariants

| Operation category | Current entrance |
|---|---|
| Query | `parts()`、`surfaces()`、`fea_components()`、`material_nodes()`、`instance_names()` |
| Affiliation/relationship | `owner_of_surface()`、`owner_of_instance()`、`owner_of_cad_operation()` |
| Citation settings | `set_component_reference()`、`set_material_part()`、`set_*_updater_target()` |
| Object renaming | `rename_definition()`、`rename_part()`、`rename_instance()` |
| Structural Editing | `add/clone/remove/move` corresponds to Part, Instance, Surface, Load, Material, and CAD operations. |
| Curved Surface-related States | `align_surface_dependent_state()` |
| Persistence | `to_dict()`、`from_dict()` |

Check the validity of names for components, instances, materials, and loads within their respective ranges. Surface indices are locally numbered within the boundary of the Part they belong to. After adding or removing elements, the distance matrix and the surface indices of symmetric entries need to be adjusted accordingly. `is_updatable` is stored within the surface object and moves with the object. There is no need to synchronize it with the index synchronization list.

When deleting a target object, the reference and related configurations must be processed through aggregate operations. It is not possible to remove entries solely from the display list. The UI structure buttons and tree menu should call the same application commands or aggregate methods, without maintaining a separate set of associated tables.

<a id="section-morph-边界与兼容处理"></a>

## 6 `.morph` Boundaries and compatibility considerations

The current load case `ProblemDefinition.to_dict()` includes version 4: root nodes, task/device configurations, auxiliary definitions, and custom classes. The optimization objects and algorithms are defined by specific nodes and updaters, without storing a global solution identifier. `from_dict()` is responsible for restoring typed nodes and references, while `loaders.py` is in charge of file reading and writing.

The file import uses `loaders._DefinitionReader` to project the content onto the current schema: Fields can be retained, missing fields will use the default values of the current factory, and additional fields and unsupported entries will be ignored with the reason recorded. `ProblemLibrary.load(..., issues=...)` returns definitions and summary issues, and the window displays a warning with expandable details. If the format is not an object or the JSON syntax is invalid, a read error will still be reported. After import, the normal definition verification will continue.

This tolerance strategy applies only to the boundaries of external files. `Node.from_dict()`, internal snapshot restoration, and domain construction are strictly maintained, and incomplete data is not distributed across various controls or kernels. The importer does not restore the semantics of removed algorithms, and does not guarantee that ignored parameters will still have any effect. Saving again results in the current format.

The definition file only stores the declared content, excluding mesh caching, VTK actors, historical navigation states, or independent finite element results. The edit history is saved as a snapshot using the same serialization method, but the historical tree itself is not written to `.morph`.

The new fields need to cover both construction, read-write fields, serialization, and recovery paths. The new polymorphic type needs to be registered in the node registry, and its updatable capability, backend class, and applicable editors should be clearly defined. For the specific process, please refer to [Expansion and maintenance](development.md).

The named load cases are saved in the order of registration by `StepsNode.step_values`. The keys are unique strings. These are the names referenced by the objective, indicators, and solver task groups. The workspace objective records determine the ownership of the load cases. The application service checks for references and removes any load cases that have no references when the configuration changes or the objectives are deleted.

Current `.morph` The format version is 4. Load cases are stored using string keys. The examples in the repository have been updated synchronously. Files from older versions or other versions will be read according to the above import rules, and those parts that cannot be retained will be reported.

<a id="section-具名工况的接口投影"></a>

## 7 Interface projection for named operating conditions

`StepsNode.step_values` is the only source of data for the amplitude of the load case. `LoadCaseNode` only holds references to the `StepsNode` and the load case dictionary. It is displayed as `name [LoadCase]` in the navigation system. No second persistence node is registered. The name is resolved through the dictionary identity. After renaming, sorting, and re-generating the navigation, the same editing goal is maintained. `resolve_references()` updates the load case dictionary in place to prevent duplicate copies from being held by the card.

`LoadCaseNode.parameters()` obtains named scalar fields from the `value_fields` load cases. The field keys are in the form of `load_name.parameter_name`, and reading and writing are performed through `LoadCaseSession` to access the original parameter list. The data is shared among Tree, cards, and generated code. The file structure still consists of load case maps with string keys.

<a id="section-分量字段与求解器参数"></a>

## 8 Weight field and solver parameters

`FieldSpec.components` indicates the name of the list component, `item_type` indicates the type of list item. The nodes continue to maintain the original list, and the UI is controlled by `SequenceInput` for component editing. The load `value_fields` serves multiple purposes: it is used for load case cards, independent finite element load editing, and workspace input labels. This avoids the need to maintain the parameter order separately.

`PenaltyDoFNode.node_index` and `direction` are virtual fields derived from the solver’s degrees of freedom `s`. The instance uses `s=3*node_index+direction`, and the reference points represent six named degrees of freedom. `fields_for_node()` selects UI fields based on the current object. Persistence and code generation still only save `s`, avoiding duplicate states.
