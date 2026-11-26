# UI display and refresh mechanisms

[简体中文](../../zh-CN/codestructure/ui-presentation.md)

[Code structure overview](README.md)  ·  [Domain Model](ui-model.md)  ·  [Application services](ui-application.md)  ·  [Result analysis](results.md)

The UI is organized according to the principle of separating business data from display. Domain objects and application sessions store definitions, references, and operation states. The display projection preparation navigation, source code, assets, and scenario data are presented. Controls and renderers manage interactive and display resources. [UI data flow and hierarchical display structure](architecture.md#section-业务数据展示投影与显示资源) specifies the connection relationships between various layers. This page explains the specific methods of access for refreshing and rendering.

## Contents

<!-- docs:toc depth=1 -->

- [1 Source code entry point](#section-源码入口)
- [2 Combination of windows and pages](#section-窗口与页面组合)
- [3 Navigation projection and title](#section-导航投影与标题)
- [4 Editor Route and Sharing Controls](#section-编辑器路由与共享控件)
- [5 Unified changes and refreshes](#refresh)
- [6 Display of document history and access to related materials](#section-文档历史的展示接入)
- [7 Define the boundaries for previewing and rendering.](#preview)
- [8 The display boundaries of the observation pages](#section-观察页的展示边界)
- [9 Themes, localization, and platform resources](#section-主题本地化与平台资源)
- [10 Current result view with log tracking enabled](#section-当前结果视图与日志跟随)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 Source code entry point

| Path | Responsibility |
|---|---|
| [`ui/app.py`](../../../src/morphopt/ui/app.py)、[`mainwindow.py`](../../../src/morphopt/ui/mainwindow.py) | Qt applications and window-level layout techniques |
| [`ui/workbench.py`](../../../src/morphopt/ui/workbench.py) | Define the combination of workspace and refresh components. |
| [`ui/observe_panel.py`](../../../src/morphopt/ui/observe_panel.py) | Optimized observation pages and control functions. |
| [`ui/refresh.py`](../../../src/morphopt/ui/refresh.py) | Refreshing protocols, context information, and merging schedules |
| [`ui/widgets/`](../../../src/morphopt/ui/widgets) | Editors, trees, viewports, pages, and dialog boxes |
| [`ui/presentation/`](../../../src/morphopt/ui/presentation) | Navigation, titles, historical tables, and operation history projections |
| [`ui/visualization/`](../../../src/morphopt/ui/visualization) | Geometry, load data, and scene data preparation |
| [`ui/theme/`](../../../src/morphopt/ui/theme)、[`ui/i18n.py`](../../../src/morphopt/ui/i18n.py) | Topics, language settings, and subscription notifications |

<a id="section-窗口与页面组合"></a>

## 2 Combination of windows and pages

```text
MainWindow
├── Workbench：Definition
│   ├── ModelTree / EditHistoryPanel
│   ├── EditorPages → Current editor
│   ├── PreviewViewer → PreviewRenderer
│   └── GeneratedSourceView / AssetBrowser
└── Optimization progress
    ├── ObserverControls + ObserverPanel
    │   ├── MetricsPage
    │   ├── UpdatableStructurePage
    │   └── DeformationCasePage
    └── FiniteElementPage
```

`MainWindow` manages the definition of file paths, menus, page transitions, and result directories/iteration selections. `Workbench` combines the definition of sessions and edits components. The observation page and finite element page continue to retain their sessions, and page transitions do not re-create tasks.

The File menu provides unified access to definitions, scripts, running results, and export options. The Settings menu allows for the management of language and themes. The Start Optimization button and the Analysis menu use the same interface for verification. `Ctrl+S` Saves the current definitions, regardless of changes in the source of the results page.

The result view shares only the directory and iteration choices, and does not share the modifiable FE models. This status and locking rules are detailed in [Result selection](results.md#selection).

<a id="section-导航投影与标题"></a>

## 3 Navigation projection and title

`DefinitionNavigation` projects the domain objects into a model tree structure. `ParamsTreeNode`, `UpdaterTreeNode`, and auxiliary code groups are merely used as navigation handles. `UpdaterItemTreeNode` directly associates entries with configurations, allowing the original entries to be located even after sorting.

The tree, cards, and menu titles are generated uniformly through `presentation/labels.py`: object display shows `name [ClassName]`, while the type menu displays the function name and class name. After selecting a custom class, the actual class name is displayed. Grouping does not attach fictional backend class names, and the update capability is determined by node metadata.

The drop-down list saves the displayed titles and the original values or object references in `itemData`. The displayed text does not participate in the business name resolution. The editor focus allows the tree to silently follow the current card, and page scrolling is only triggered by active navigation.

<a id="section-编辑器路由与共享控件"></a>

## 4 Editor Route and Sharing Controls

`application/editor_routing.py` determines the type of editor for the node. `EditorPages` is responsible for adding editors to the page, binding routes, and handling connection changes. The workbench does not maintain separate signal paths for each page.

| Component | Demonstrating responsibility |
|---|---|
| `PropertyEditor`、`ParamForm` | Node title and shared schema field form |
| `DefinitionManagerEditor` | Collection cards for components and sub-items, loads, operating conditions, or additional definitions. |
| `CollectionHeader`、`ItemActions` | Buttons for adding, moving up, moving down, and deleting entries |
| `DefinitionActions` | The tree menu shares the same structural elements, dialog boxes, and notifications as the card interface. |
| `LoadCaseEditor`、`SolverEditor` | Reuse Collection Editor’s operating condition interface page, as well as information for each process-specific device and ordered set of operating conditions. |
| `SequenceInput` | Draw fixed-length lists or variable-length lists based on metadata. Support for referencing entire constants as well. |
| `UpdaterEditor` | Sub-goals, symmetry, and ordered cards for penalty functions |
| `ObjectiveEditor` | Selection of targets, metrics, and Jacobian matrices |
| `ModelClassSelector` | Root-level configuration, objective function, and selection of the appropriate sub-optimizer. |
| `CodeEditor`、`HelperCodeEditor`、`CustomClassEditor` | Code input, method bodies, and auxiliary definitions |
| `GeneratedSourceView` | Synchronously define the corresponding read-only Python code. |

`ParamForm` Directly binds the read/write interface of the typed node, or binds the parameter dictionary held by the associated service. It does not copy the field values that require bidirectional maintenance. When the structure, schema, or target changes, the form needs to be recreated. Try to preserve the focus, scrolling, and code editing history when updating regular fields and refreshing dynamic options.

For the `PropertyEditor(compact=True)` embedded in the card, a layout with the minimum size constraint is used directly, without nesting independent scrolling areas. The outer collection page is responsible for scrolling, and the height of the layout is recalculated when the target type or font is changed. For the `ParamForm` list fields, `SequenceInput` is uniformly used, and the names of the components are provided by the schema. The global scroll bar filter transfers the scrolling actions from the input control to the page, preventing accidental changes to the values during scrolling.

Parameter selection and business verification are provided by the application service. The control handles input events and rendering, without calculating material allocations, updater targets, or set names on its own.

<a id="refresh"></a>

## 5 Unified changes and refreshes

```text
Field Editing / Tree Menu / Collection Actions
  → Execute commands or perform operations in the ProblemDefinition domain.
  → changed(node)
  → Workbench Synchronize and edit snapshots.
  → RefreshCoordinator Merge changes
  → A RefreshContext instance.
  → Refresh the UI of each registered component (context).
```

The structural operations can be submitted immediately through `refresh_now(node)`; the continuous field inputs are merged through `request(node)`. Both paths lead to the same scheduler.

| `RefreshContext` content | Function/Role |
|---|---|
| `problem` | The definitions for this round have been established in sync. |
| `selected` | Current navigation object |
| `changed_nodes` | The objects that will be affected by the merger, including the deleted nodes. |
| `full` | Full refresh triggered by unknown sources |
| `restoring` | Editorial history has been restored, with all appropriate view states preserved. |

`RefreshCoordinator` Component-based, called in order of registration `Refreshable.refresh_ui()` Delete notifications and retain the source node. Complete refresh requests from unknown sources will not be overwritten by subsequent local notifications. Component failure records are reported with complete exceptions, while other independent components continue to be refreshed.

The tree, the current editor, code generation, and preview all operate within the same context. The component does not call the private methods of other widgets to maintain model consistency, nor does it perform domain synchronization repeatedly. New components are registered in `Workbench._register_refreshables()`, and the dedicated editing page is connected through `EditorPages`.

The load scenario is updated only when the load or load case changes. When the geometry, auxiliary expressions, or other geometry-related configurations change, the corresponding geometry and load must be recreated. Regular refreshes retain the selected items, expanded states, load cases, and cameras. When the model or view is replaced, the initialization should be done according to the new context.

<a id="section-文档历史的展示接入"></a>

## 6 Display of document history and access to related materials

`EditHistoryPanel` displays the branch history, and can be restored by requesting the stable step ID. The historical content and branch algorithm are managed by [EditHistory](ui-application.md#section-编辑历史与恢复).

Submit the input before recovery and cancel the previous refresh. After recovery, rebind the objects and forms uniformly. `RefreshContext.restoring` ensures that the recovery process retains the camera, load case, and appropriate scrolling position; it is not possible to continue referencing the node objects from before recovery.

The text control prioritizes local undo operations, while document undo operations handle the overall definition. The shortcuts in the code editor only apply to the current code control. The delayed layout callback is managed by the associated QObject, and no further operations are performed on old controls after the page is destroyed.

<a id="preview"></a>

## 7 Define the boundaries for previewing and rendering.

```text
ProblemDefinition + DefinitionValues
  → PreviewGeometry
      ├── PartPreviewVisitor / SurfacePreviewVisitor → PreviewScene
      └── LoadPreviewVisitor                        → LoadScene
  → PreviewRenderer → PyVista / VTK actors
```

`PartPreviewAdapter` provides `preview()`, `surface()`, and the optional `model_part()`. Prepare the initial geometry, load application surface, and model required for set queries. The adapter is registered as **Python classes for PartNode**. It is searched based on inheritance relationships, not based on display strings.

Boundary, Box, CAD, and INP each have their own adapters. Viewports are not stacked according to type in the modeling branches. The collection provider for `PartSetCatalog` is also registered by node type. `PreviewGeometry.build()` first binds the current definitions with resources, and then performs collection and load queries.

In Part views, local coordinates are used; in assembly views, Instance poses are applied. CAD displays all triangles as a single surface mesh, and assigns the `face_N` number to the cell data; all topological edges are combined into a single line mesh. Loads and node sets are queried to extract the specified `face_N` from the surface mesh, without creating actors for each topological surface or edge. Single Part preview fails due to scene errors, and no alternative optimized geometry is generated.

CAD preview uses TorchFEA to replay the OCC operation history, and then OpenCASCADE is used to natively triangulate the display surfaces and topological edges, without invoking the Gmsh mesh generation interface. The edges directly reference the triangulated boundary nodes of the corresponding surfaces. The display surfaces and edges are matched with the original Gmsh topological identifiers based on area or length, centroid, and moment of inertia. This approach retains the trimmed boundary of the periodic surfaces and the `face_N` selection relationships; Gmsh continues to handle the modeling history and topological queries, while the finite element mesh is still generated independently by Gmsh. The preview layer converts any anomalies at the bottom layer into `RuntimeError`, with the interface recording the preview errors for the corresponding components.

Before generating the solid mesh, TorchFEA uses OCC to split closed cyclic surfaces, ensuring that the trimmed cyclic boundaries are suitable for Gmsh subdivision. The splitting only affects the subdivision topology and does not change the geometric shape. The mesh data of surfaces, edges, vertices, and solids are mapped back to their original entities based on their source, thus ensuring consistency between the UI's `face_N` representation, node sets, and load references.

Each Part adapter provides `MeshFaces` in the base grid of `MeshItem.faces`, recording the names of components, instances, display cell groups, and corresponding surface collections. `PreviewRenderer` uses the `vtkCellPicker` that identifies the clicked cells, highlighting the selected groups with a single temporary actor, and passes `FaceSelection` to `PreviewViewer` to display the names of copyable surfaces. CAD, Box, Boundary, OffsetBoundary, and INP share this process; load elements, topological edges, and selected highlights do not participate in the selection process, and mouse dragging does not trigger selection. The permanent surface number labels have been removed.

The Qt viewport obtains the local coordinates of the control through the event filter, and then converts them into VTK pixel coordinates based on the actual rendering window size. The vertical axis is also flipped. The displayed grid retains the original cell IDs. The picked results are mapped back to `MeshFaces` using these IDs, allowing the rendering pipeline to adjust the order of cells. The slice slider calls `PreviewRenderer.set_section()` to update the shared `vtkPlane`. The geometry mapper and the selected highlight share the same clipping plane. Moving the plane does not re-create the CAD file, nor does it modify the model definition or the original grid. The picking process follows the same clipping range.

Scene data can include PyVista meshes, labels, and load elements, but does not possess a plotter or VTK actor. `PreviewRenderer` is responsible for creating, replacing, and cleaning up actors; new loads can register visitors and return existing elements, and new elements are extended at the renderer's dispatch entry point.

The dimensions of the load symbols are calculated based on the scenario and the typical width of the components. The displayed dimensions are separated from the physical values. The annotation templates are provided by language resources, including target instances, collections, or reference points. `ui/visualization/rendering.py` manages the viewport background, lighting, transparency, orientation axes and result rendering. These settings are reapplied after a scene rebuild.

<a id="section-观察页的展示边界"></a>

## 8 The display boundaries of the observation pages

`MetricsPage` The consumption history table projection and curve data allow selection of column widths by title, with horizontal scrolling and inter-row background colors provided. `LogsPage` The log files are read in increments through `ResultLogReader`. The reading state and scrolling anchor points are managed by services and controls. `UpdatableStructurePage` The Part surface or material field is displayed based on the loaded updateable interfaces. `DeformationCasePage` The deformed mesh for the selected load case is displayed. Updateable objects are presented through their own loading/plotting protocols, and branches are not copied based on the scheme name.

The reading of result files and parameter loading are performed in `ResultSession`. After the loading is successful, the old viewports will be cleared. The result pages can be hidden to preserve the polling and task status. Unnecessary VTK redraws can be paused. For details on field interpretation, independent finite element analysis, and export processes, please refer to [Results](results.md).

<a id="section-主题本地化与平台资源"></a>

## 9 Themes, localization, and platform resources

`widgets/history_export.py` provides a unified export window for optimization history. GIFs, updatable components, and Abaqus INP are displayed in separate tabs, all using the same working process and file selector. `widgets/labels.py` centrally manages tags that can be truncated and supports result tags that allow copying paths. Object titles, form option names, and visual object names are generated by `presentation/labels.py`. Numerical analysis is handled by `application/values.py`, while the values of form controls are processed by `widgets/param_form.py`.

Languages and themes can be selected through the main window menu. The configuration saved during startup is restored by `app.py`.

`widgets/viewport.py` is a three-dimensional viewport that is shared among the preview, asset, and result pages. This control holds the QtInteractor, preset perspective selection, and adaptation window buttons; the camera is retained during scene replacement. Hiding the viewport delays rendering and appearance updates, while displaying the latest requests from post-processing. `theme/visualization.py` saves application-level projection and lighting parameters and sends change signals; `widgets/visualization_settings.py` maintains independent drafts and previews, and notifies the business viewport only after the application is completed. `visualization/rendering.py` These settings are passed to the shared drawing function without Qt, with lighting adjustments maintaining the proportions between lights, without modifying scalar color mappings or marking elements without lighting.

`ThemePalette` Combines Qt, code, charts, preview, PyVista, and layout styles; `theme/themes/` Registers complete themes; `theme/styles/*.qss` Manages the state of shared controls; `theme/fonts.py` Manages the font settings and notification changes for each text category. Font settings are saved independently of color themes. The appearance is refreshed when themes are switched, while the display state of the camera and other elements is retained.

`constants.py` saves the default business values, operating restrictions, and numerical configurations. The window size, spacing, and column ratio are managed by `LayoutStyle`. The application display text uses the stable keys of `locales/zh-CN.json` and `en-US.json`. The domain identity still uses the original names and enumeration values.

The selection of files and directories is uniformly managed by `widgets/file_dialogs.py`. The import of STEP, mesh, and engineering files, as well as the selection of result directories and export files, all use the same interface. The icons for navigation buttons are designed according to the current theme, and the labels use the current language resources. The new file selection function should call `choose_open_file()`, `choose_directory()`, or `choose_save_file()`.

`application_icon.py` manages application icons and platform identities, while `assets/morphopt.svg` handles shared icon resources. Windows assigns a process application ID before creating an application, while Linux uses running window icons. Platform packaging resources and running window resources are managed separately. Language and theme selection do not affect the definition of problems, and do not affect the document editing history.

<a id="section-当前结果视图与日志跟随"></a>

## 10 Current result view with log tracking enabled

`ObserverPanel.options` Paving indicators, logs, updatable components, and named load cases. `UpdatableStructurePage` Reuse `postprocess.visualization.design_view_options()` and `add_design_component()` to generate all surface, single surface, and control grid views; the UI does not require duplicate implementation for geometric drawing. The visibility of the iteration toolbar is controlled by the 3D view, while the indicators and log pages have hidden sliders and historical exports.

Log reading is independent of completed iterations, and can be displayed before the first complete save. `ResultLogReader` holds the file location and the UTF-8 incremental decoding status. `LogsPage` holds the reading anchor points; when scrolling up, selecting text, or dragging the scroll bar, it does not automatically jump to the bottom. You can continue reading after restoring to the bottom.

Fonts, colors, control sizes, and global 3D materials are all centralized in `ui/theme/`. `FontSettingsDialog` saves the drafts for each font role. The preview does not trigger any global updates; when the application is applied or confirmed, all data is submitted to `FontManager`. The model tree, titles, text, code, and charts are subscribed to changes based on roles. Font selections are not overridden by local hardcoding of controls.

Define a preview with the current `ProblemDefinition` as the cache boundary. Generate input signatures based on geometric fields and expression dependencies. Cache the meshes of various parts, surface displays, and CAD surface records. If the loads, materials, targets, or options are refreshed, the geometry that has not changed will not be re-sparcified. This cache is independent of the finite element mesh cache of the FixedPart, and it is not cached based on whether the geometry is involved in optimization or not.
