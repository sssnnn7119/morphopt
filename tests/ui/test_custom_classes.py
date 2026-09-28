from __future__ import annotations

import ast
import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from morphopt.ui.application import (
    EditorKind,
    ProblemLibrary,
    ProblemSession,
    route_editor,
)
from morphopt.ui.codegen.custom_classes import class_catalog, framework_class_catalog
from morphopt.ui.model.problem import (
    CustomClassNode,
    MethodOverrideNode,
    ProblemDefinition,
)


def customize(problem, base, name, method=None, body=None, bind=True):
    targets = class_catalog(problem)
    spec = targets.get(base)
    expression = spec.base_expression if spec else base
    custom = CustomClassNode(name=name, params={"base_class": expression})
    if method:
        method_spec = framework_class_catalog(problem)[expression].methods[method]
        custom.add_child(
            MethodOverrideNode(
                name=method,
                params={"body": body if body is not None else method_spec.body},
            )
        )
    problem.custom_classes.append(custom)
    if bind and spec:
        if base == "ThisController.ObjectiveFunction":
            problem.objective.custom_class = name
        elif spec.inherited:
            if ".FEAParams." in base:
                for node in problem.interfaces():
                    if node.interface_type + "Interface" == base.rsplit(".", 1)[-1]:
                        node.custom_class = name
            elif ".MaterialsParams." in base:
                for node in problem.material_nodes():
                    if node.material_type == base.rsplit(".", 1)[-1]:
                        node.custom_class = name
        else:
            problem.class_bindings[base] = name
    return custom


def load_classes(problem):
    namespace = {"__name__": "custom_class_test"}
    exec(ProblemSession(problem).source(), namespace)
    return namespace["ThisController"]


def test_custom_classes_round_trip(tmp_path):
    problem = ProblemLibrary.create("shapeopt")
    custom = customize(
        problem,
        "ThisController.ObjectiveFunction",
        "MyObjective",
        "get_metrics",
        "return {'custom_metric': 7}",
    )
    path = ProblemLibrary.save(problem, tmp_path / "custom.morph")
    loaded = ProblemLibrary.load(path)
    assert loaded.custom_classes[0].to_dict() == custom.to_dict()
    assert isinstance(loaded.custom_classes[0], CustomClassNode)
    assert isinstance(loaded.custom_classes[0].children[0], MethodOverrideNode)
    assert loaded.class_bindings == problem.class_bindings
    assert load_classes(loaded).ObjectiveFunction().get_metrics() == {
        "custom_metric": 7
    }


def test_helper_entries_round_trip_and_use_from_override(tmp_path):
    problem = ProblemLibrary.create("shapeopt")
    from morphopt.ui.model.problem import HelperFunctionNode, HelperVariableNode

    problem.helper_code = "import torch"
    problem.helper_variables = [
        HelperVariableNode(name="target_force", params={"value": "3.0"}),
    ]
    problem.helper_functions = [HelperFunctionNode(
        name="force_error",
        params={"parameters": "force", "body": "return torch.square(force - target_force)"},
    )]
    customize(
        problem,
        "ThisController.ObjectiveFunction",
        "MyObjective",
        "get_metrics",
        "return {'error': force_error(torch.tensor(4.0)).item()}",
    )
    path = ProblemLibrary.save(problem, tmp_path / "with_helpers.morph")
    loaded = ProblemLibrary.load(path)
    assert loaded.helper_code == problem.helper_code
    assert [node.value for node in loaded.helper_variables] == [node.value for node in problem.helper_variables]
    assert [node.body for node in loaded.helper_functions] == [node.body for node in problem.helper_functions]
    source = ProblemSession(loaded).source()
    assert source.index("def force_error") < source.index("class MyObjective")
    assert source.index("class MyObjective") < source.index("class ThisController")
    assert load_classes(loaded).ObjectiveFunction().get_metrics() == {"error": 1.0}


def test_invalid_helper_function_is_rejected_before_run():
    problem = ProblemLibrary.create("shapeopt")
    from morphopt.ui.model.problem import HelperFunctionNode

    problem.helper_functions = [HelperFunctionNode(name="broken", params={"parameters": "(", "body": "pass"})]
    with pytest.raises(ValueError, match="Invalid helper code"):
        ProblemSession(problem).validate_for_run()


def test_custom_classes_are_top_level_and_only_selected_class_is_used():
    problem = ProblemLibrary.create("shapeopt")
    first = customize(
        problem,
        "morphopt.Solver",
        "FirstSolver",
        "reinitialize",
        "return 'first'",
        bind=False,
    )
    second = customize(
        problem,
        "morphopt.Solver",
        "SecondSolver",
        "reinitialize",
        "return 'second'",
        bind=False,
    )
    source = ProblemSession(problem).source()
    tree = ast.parse(source)
    assert {node.name for node in tree.body if isinstance(node, ast.ClassDef)} == {
        "FirstSolver",
        "SecondSolver",
        "ThisController",
    }
    import morphopt

    assert load_classes(problem).Solver.__bases__ == (morphopt.Solver,)
    for custom, expected in [(first, "first"), (second, "second")]:
        problem.class_bindings["ThisController.Solver"] = custom.name
        source = ProblemSession(problem).source()
        assert f"class Solver({custom.name}):" in source
        assert f"Solver = {custom.name}" not in source
        assert load_classes(problem).Solver(None).reinitialize(0) == expected
    problem.class_bindings.clear()
    assert load_classes(problem).Solver.__bases__ == (morphopt.Solver,)


def test_selected_constructor_receives_ui_options_and_hooks_take_priority():
    problem = ProblemLibrary.create("shapeopt")
    problem.solver.num_process = 3
    customize(
        problem,
        "ThisController.Solver",
        "MySolver",
        "__init__",
        "super().__init__(params, num_process, available_gpus, task_index_list)\nself.custom_init = True",
    )
    customize(
        problem,
        "ThisController.Params.GeometryParams",
        "MyGeometry",
        "define_interface",
        "return 'custom geometry'",
    )
    controller = load_classes(problem)
    solver = controller.Solver(None)
    assert solver.num_process == 3 and solver.custom_init
    assert controller.Params.GeometryParams().define_interface() == "custom geometry"


@pytest.mark.parametrize(
    "bindings",
    [
        {"ThisController.Solver": "Missing"},
        {"ThisController.Solver": "MyObjective"},
        {"Missing.Node": "MyObjective"},
    ],
)
def test_missing_or_incompatible_class_selection_is_rejected(bindings):
    problem = ProblemLibrary.create("shapeopt")
    customize(problem, "morphopt.ObjectiveFunction", "MyObjective", bind=False)
    problem.class_bindings = bindings
    with pytest.raises(ValueError):
        ProblemSession(problem).validate_for_run()


def test_part_class_names_use_interface_types_and_old_paths_are_rejected():
    problem = ProblemLibrary.create("shapeopt")
    catalog = class_catalog(problem)
    assert "ThisController.Params.GeometryParams.BoundaryPartInterface" in catalog
    assert "ThisController.Params.GeometryParams.BoundaryPart0" not in catalog
    problem.custom_classes.append(
        CustomClassNode(
            name="MyBoundary",
            params={"base_class": "ThisController.Params.GeometryParams.BoundaryPart0"},
        )
    )
    with pytest.raises(ValueError, match="Base class missing"):
        ProblemSession(problem).source()
    for template in ProblemLibrary.templates():
        catalog = class_catalog(ProblemLibrary.create(template.scheme))
        parts = [
            spec
            for spec in catalog.values()
            if not spec.inherited
            and spec.path.rpartition(".")[0] == "ThisController.Params.GeometryParams"
        ]
        assert all("PartInterface" in spec.path.split(".")[-1] for spec in parts)


def test_nested_subclasses_replace_classes_and_retain_generated_configuration():
    problem = ProblemLibrary.create("shapeopt")
    customize(problem, "ThisController", "MyController", "step", "return 123")
    customize(problem, "ThisController.Params", "MyParams")
    customize(problem, "ThisController.Params.FEAParams", "MyLoads")
    customize(
        problem,
        "ThisController.Params.FEAParams.PressureInterface",
        "MyPressure",
        "initialize",
        "return 'pressure override'",
    )
    customize(
        problem,
        "ThisController.Params.MaterialsParams.HomogeneousMaterial",
        "MyMaterial",
        "initialize",
        "return 'material override'",
    )
    controller = load_classes(problem)
    assert controller.__bases__[0].__name__ == "MyController"
    assert object.__new__(controller).step() == 123
    assert controller.Params.__bases__[0].__name__ == "MyParams"
    loads = controller.Params.FEAParams()
    loads.define_interface()
    pressure = next(
        item
        for item in loads.interfaces.values()
        if type(item).__name__ == "MyPressure"
    )
    assert pressure.initialize() == "pressure override"
    loads.define_steps()
    assert loads.num_load_steps == problem.steps.num_steps
    materials = controller.Params.MaterialsParams()
    materials.define_interface()
    assert next(iter(materials.interfaces.values())).initialize() == "material override"


@pytest.mark.parametrize(
    "scheme", [template.scheme for template in ProblemLibrary.templates()]
)
def test_all_discovered_methods_have_executable_default_subclasses(scheme):
    problem = ProblemLibrary.create(scheme)
    for index, (path, spec) in enumerate(framework_class_catalog(problem).items()):
        custom = customize(problem, path, f"Custom{index}")
        for method in spec.methods.values():
            custom.add_child(
                MethodOverrideNode(name=method.name, params={"body": method.body})
            )
    # Execute declarations as well as compiling them to check defaults, scopes,
    # nested aliases, static methods and class methods together.
    load_classes(problem)


def test_super_calls_generated_method_and_classmethod_uses_custom_type(monkeypatch):
    import morphopt

    problem = ProblemLibrary.create("shapeopt")
    customize(problem, "ThisController.ObjectiveFunction", "MyObjective", "__init__")
    path = "ThisController.Params.GeometryParams.BoundaryPartInterface.BSP"
    customize(problem, path, "MySurface", "initialize_cylinder")

    def factory(cls, *args, **kwargs):
        return cls

    factory.__signature__ = inspect.signature(
        inspect.getattr_static(
            morphopt.BoundaryPartInterface.BSP, "initialize_cylinder"
        ).__func__
    )
    monkeypatch.setattr(
        morphopt.BoundaryPartInterface.BSP, "initialize_cylinder", classmethod(factory)
    )
    controller = load_classes(problem)
    objective = controller.ObjectiveFunction()
    assert objective.jacobian_needed == [
        node.name for node in problem.objective.jacobian_needed
    ]
    surface = controller.Params.GeometryParams.BoundaryPartInterface.BSP
    assert surface.initialize_cylinder(1, 2, 3, False) is surface


@pytest.mark.parametrize(
    "base,name,method,body",
    [
        ("MissingClass", "Custom", "step", "pass"),
        ("ThisController", "invalid name", "step", "pass"),
        ("ThisController", "ThisController", "step", "pass"),
        ("ThisController", "morphopt", "step", "pass"),
        ("ThisController", "class", "step", "pass"),
        ("ThisController", "Custom", "missing_method", "pass"),
        ("ThisController", "Custom", "step", "return ("),
    ],
)
def test_invalid_overrides_are_rejected_before_run(base, name, method, body):
    problem = ProblemLibrary.create("shapeopt")
    problem.custom_classes.append(
        CustomClassNode(
            name=name,
            params={"base_class": base},
            children=[MethodOverrideNode(name=method, params={"body": body})],
        )
    )
    with pytest.raises(ValueError):
        ProblemSession(problem).validate_for_run()


def test_workbench_routes_overrides_and_keeps_text_during_refresh(monkeypatch):
    from PySide6.QtWidgets import QApplication, QInputDialog, QWidget

    from morphopt.ui import workbench

    app = QApplication.instance() or QApplication([])

    class Viewer(QWidget):
        def set_problem(self, problem):
            pass

        def apply_language(self):
            pass

    monkeypatch.setattr(workbench, "PreviewViewer", Viewer)
    problem = ProblemLibrary.create("shapeopt")
    custom = customize(problem, "ThisController.ObjectiveFunction", "MyObjective")
    other = customize(
        problem,
        "morphopt.ObjectiveFunction",
        "OtherObjective",
        "get_metrics",
        "return {'other': 1}",
        bind=False,
    )
    customize(problem, "morphopt.Solver", "CustomSolver", bind=False)
    customize(problem, "morphopt.Controller", "CustomController", bind=False)
    customize(problem, "morphopt.Params", "CustomParams", bind=False)
    window = workbench.Workbench(problem)
    assert window.tree.topLevelItemCount() == 2
    helper_item = window.tree.topLevelItem(0)
    root_item = window.tree.topLevelItem(1)
    assert window.tree._item_node[root_item] is problem.root
    assert window.tree._item_node[helper_item].kind == "helper_code"
    assert [
        window.tree._item_node[root_item.child(i)].kind
        for i in range(root_item.childCount())
    ] == ["params_class", "solver", "updater"]
    params_item = root_item.child(0)
    assert [
        window.tree._item_node[params_item.child(i)].kind
        for i in range(params_item.childCount())
    ] == ["geometry", "loads_group", "materials"]
    window.tree.setCurrentItem(root_item)
    assert window.class_selector._path == "ThisController"
    assert window.class_selector.combo.findData("CustomController") >= 0
    assert window.class_selector.combo.findData("CustomSolver") == -1
    window.tree.setCurrentItem(params_item)
    assert window.class_selector._path == "ThisController.Params"
    assert window.class_selector.combo.findData("CustomParams") >= 0
    before = problem.root.to_dict()
    window._on_any_change()
    assert window.tree._item_node[window.tree.currentItem()].kind == "params_class"
    assert problem.root.to_dict() == before
    window._on_node_selected(problem.objective)
    assert window.class_selector.isHidden()
    window.tree._set_objective_class(other.name)
    assert problem.objective.custom_class == other.name
    assert load_classes(problem).ObjectiveFunction().get_metrics() == {"other": 1}
    window.tree._set_objective_class(custom.name)
    window._on_node_selected(problem.solver)
    assert window.class_selector.combo.findData("CustomSolver") >= 0
    assert window.class_selector.combo.findData(other.name) == -1
    for node in (
        problem.objective,
        problem.loads,
        problem.steps,
        problem.part_interfaces()[0],
        problem.interfaces()[0],
        problem.material_nodes()[0],
    ):
        window._on_node_selected(node)
        assert window.class_selector.isHidden()
    window._on_node_selected(custom)
    editor = window.custom_class_editor
    assert window._tree_split.count() == 2
    assert window._stack.currentWidget() is editor
    monkeypatch.setattr(
        QInputDialog,
        "getItem",
        lambda *args: (
            next(choice for choice in args[3] if choice.startswith("get_metrics(")),
            True,
        ),
    )
    editor.add_override()
    method = custom.children[0]
    editor.code.set_body("return {'from_ui': 42}")
    assert method.body == "return {'from_ui': 42}"
    window._on_any_change()
    assert editor.code.body() == method.body
    assert window.custom_tree.tree.topLevelItem(0).childCount() == 1
    assert route_editor(method).kind is EditorKind.CUSTOM_CLASS
    assert load_classes(problem).ObjectiveFunction().get_metrics() == {"from_ui": 42}
    monkeypatch.setattr(
        QInputDialog,
        "getItem",
        lambda *args: (
            next(
                choice for choice in args[3] if choice.startswith("objective_function(")
            ),
            True,
        ),
    )
    editor.add_override()
    window.custom_tree.rebuild()
    window.custom_tree.tree.setCurrentItem(
        window.custom_tree.tree.topLevelItem(0).child(0)
    )
    window._on_any_change()
    assert editor.current_method is method
    editor.code.set_body("return (")
    assert editor.error.text()
    editor.code.set_body("return {'from_ui': 42}")
    assert not editor.error.text()
    editor._remove_override()
    window._on_any_change()
    editor._remove_override()
    assert not custom.children
    editor.name.setText("RenamedObjective")
    editor._rename()
    assert problem.objective.custom_class == "RenamedObjective"
    window.custom_tree._remove(custom)
    assert "ThisController.ObjectiveFunction" not in problem.class_bindings
    assert not problem.objective.custom_class
    assert window._stack.currentWidget() is window.prop_editor
    window.close()
    app.processEvents()


def test_workbench_manages_helper_entries(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication, QWidget

    from morphopt.ui import workbench

    app = QApplication.instance() or QApplication([])

    class Viewer(QWidget):
        def set_problem(self, problem):
            pass

        def apply_language(self):
            pass

    monkeypatch.setattr(workbench, "PreviewViewer", Viewer)
    problem = ProblemLibrary.create("shapeopt")
    window = workbench.Workbench(problem)
    assert window._center.count() == 2
    helper_item = window.tree.topLevelItem(0)
    helper_node = window.tree._item_node[helper_item]
    assert route_editor(helper_node).kind is EditorKind.HELPER_CODE
    assert [window.tree._item_node[helper_item.child(i)].kind for i in range(3)] == [
        "helper_code_block", "helper_variables_group", "helper_functions_group",
    ]
    window._center.setCurrentWidget(window.code_view)
    window.tree.setCurrentItem(helper_item)
    assert window._center.currentIndex() == 0
    assert window._stack.currentWidget() is window.helper_page
    variable = window.tree.add_helper("helper_variable")
    assert window.tree._item_node[window.tree.currentItem()] is variable
    window.helper_name.setText("target_force")
    window.helper_value.setText("3.0")
    window._save_helper_fields()
    assert variable.name == "target_force"
    assert variable.value == "3.0"
    function = window.tree.add_helper("helper_function")
    window.helper_name.setText("target")
    window.helper_editor.set_body("return target_force")
    window._save_helper_fields()
    assert function.name == "target"
    assert function.body == "return target_force"
    window._on_any_change()
    assert window.tree._item_node[window.tree.currentItem()] is function
    assert window._stack.currentWidget() is window.helper_page
    window.refresh_code()
    assert "def target():" in window.code_view.toPlainText()
    window.apply_language()
    assert window.helper_editor.body() == function.body
    assert window._stack.currentWidget() is window.helper_page

    window._center.setCurrentWidget(window.code_view)
    window.tree.setCurrentItem(window.tree.topLevelItem(1))
    assert window._center.currentIndex() == 0
    assert window._stack.currentWidget() is window.prop_editor
    window._center.setCurrentWidget(window.code_view)
    window.tree.itemClicked.emit(window.tree.currentItem(), 0)
    assert window._center.currentIndex() == 0
    assert window._stack.currentWidget() is window.prop_editor

    path = ProblemLibrary.save(problem, tmp_path / "helpers.morph")
    window.set_problem(ProblemLibrary.load(path))
    loaded_function = window.problem.helper_functions[0]
    window.tree.setCurrentItem(window.tree._node_item[loaded_function])
    assert window._stack.currentWidget() is window.helper_page
    window.helper_parameters.setText("(")
    window._save_helper_fields()
    assert window.helper_error.text()
    window.refresh_code()
    assert "code generation failed" in window.code_view.toPlainText()
    window.tree.remove_helper(loaded_function)
    assert not window.problem.helper_functions
    window.close()
    app.processEvents()


def test_add_menus_attach_custom_classes_to_individual_interfaces(tmp_path):
    from PySide6.QtWidgets import QApplication, QMenu

    from morphopt.ui.widgets.model_tree import ModelTree

    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create("shapeopt")
    customize(
        problem,
        "morphopt.FEAParams.PressureInterface",
        "MyPressure",
        "initialize",
        "return 'custom pressure'",
        bind=False,
    )
    customize(
        problem,
        "morphopt.HomogeneousMaterial",
        "MyMaterial",
        "initialize",
        "return 'custom material'",
        bind=False,
    )
    customize(
        problem,
        "morphopt.BoundaryPartInterface",
        "MyPart",
        "define_instance",
        "return 'custom part'",
        bind=False,
    )
    customize(problem, "morphopt.BoundaryPartInterface.BSP", "MySurface", bind=False)
    tree = ModelTree()
    tree.set_problem(problem)

    def trigger_custom(node, name):
        menu = QMenu()
        tree._build_node_menu(menu, node)

        def search(menu):
            for action in menu.actions():
                if action.menu():
                    result = search(action.menu())
                    if result:
                        return result
                elif action.text().startswith(name + " ["):
                    return action
            return None

        action = search(menu)
        assert action is not None
        action.trigger()

    previous = len(problem.interfaces())
    trigger_custom(problem.loads, "MyPressure")
    custom_pressure = problem.interfaces()[-1]
    assert len(problem.interfaces()) == previous + 1
    assert custom_pressure.custom_class == "MyPressure"
    tree._add_interface("Pressure")
    default_pressure = problem.interfaces()[-1]
    assert not default_pressure.custom_class
    trigger_custom(problem.materials, "MyMaterial")
    custom_material = problem.material_nodes()[-1]
    trigger_custom(problem.geometry, "MyPart")
    custom_part = problem.part_interfaces()[-1]
    trigger_custom(custom_part, "MySurface")
    assert custom_part.surfaces()[-1].custom_class == "MySurface"
    path = ProblemLibrary.save(problem, tmp_path / "custom_items.morph")
    loaded = ProblemLibrary.load(path)
    assert loaded.interfaces()[-2].custom_class == "MyPressure"
    assert loaded.part_interfaces()[-1].custom_class == "MyPart"
    assert loaded.part_interfaces()[-1].surfaces()[-1].custom_class == "MySurface"
    controller = load_classes(loaded)
    loads = controller.Params.FEAParams()
    loads.define_interface()
    assert loads.interfaces[custom_pressure.name].initialize() == "custom pressure"
    assert type(loads.interfaces[default_pressure.name]).__name__ == "PressureInterface"
    materials = controller.Params.MaterialsParams()
    materials.define_interface()
    assert (
        next(
            item
            for item in materials.interfaces.values()
            if type(item).__name__ == "MyMaterial"
        ).initialize()
        == "custom material"
    )
    assert (
        type(next(iter(materials.interfaces.values()))).__name__
        == "HomogeneousMaterial"
    )
    assert (
        object.__new__(
            controller.Params.GeometryParams.BoundaryPartInterface2
        ).define_instance()
        == "custom part"
    )
    assert "MySurface.initialize_cylinder(" in ProblemSession(loaded).source()
    tree.close()
    app.processEvents()


def test_custom_objective_and_constraint_choices_use_existing_parameter_forms():
    from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

    from morphopt.ui.widgets.updater_editor import _item_list

    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create("shapeopt")
    customize(
        problem,
        "morphopt.UpdaterBoundaryPart.objectivefuncs.ShapeDerivative",
        "MyShape",
        "__call__",
        "return 5",
        bind=False,
    )
    customize(
        problem,
        "morphopt.UpdaterBoundaryPart.objectivefuncs.Fairness",
        "MyFairness",
        bind=False,
    )
    customize(
        problem,
        "morphopt.UpdaterBoundaryPart.objectivefuncs.BaseObjective",
        "MyGenericObjective",
        "__call__",
        "return 9",
        bind=False,
    )
    config = problem.updater.geometry[0]
    widgets = []
    for category, name, key in [
        ("objectives", "MyShape", "objective_functions"),
        ("constraints", "MyFairness", "constraints"),
        ("objectives", "MyGenericObjective", "objective_functions"),
    ]:
        widget = _item_list(config, "geometry", category, lambda: None, problem=problem)
        widgets.append(widget)
        combo = widget.findChildren(QComboBox)[-1]
        index = next(
            index
            for index in range(combo.count())
            if isinstance(combo.itemData(index), (tuple, list))
            and combo.itemData(index)[-1] == name
        )
        combo.setCurrentIndex(index)
        next(
            button
            for button in widget.findChildren(QPushButton)
            if button.text() == "＋"
        ).click()
        assert config[key][-1]["custom_class"] == name
    loaded = ProblemDefinition.from_dict(problem.to_dict())
    updater = load_classes(loaded).Updater.UpdaterBoundaryPart()
    updater.define_objective()
    assert any(type(item).__name__ == "MyShape" for item in updater.obj_funcs.values())
    assert any(
        type(item).__name__ == "MyFairness"
        for item in updater.constraints_funcs.values()
    )
    assert any(
        type(item).__name__ == "MyGenericObjective"
        for item in updater.obj_funcs.values()
    )
    for widget in widgets:
        widget.close()
    app.processEvents()


def test_missing_bindings_do_not_implicitly_replace_classes():
    problem = ProblemLibrary.create("shapeopt")
    customize(problem, "morphopt.Solver", "MySolver", bind=False)
    data = problem.to_dict()
    del data["class_bindings"]
    loaded = ProblemDefinition.from_dict(data)
    assert loaded.class_bindings == {}
    import morphopt

    assert load_classes(loaded).Solver.__bases__ == (morphopt.Solver,)


def test_deep_class_bindings_are_rejected():
    problem = ProblemLibrary.create("shapeopt")
    customize(problem, "morphopt.FEAParams.PressureInterface", "MyPressure", bind=False)
    problem.class_bindings["ThisController.Params.FEAParams.PressureInterface"] = (
        "MyPressure"
    )
    with pytest.raises(ValueError, match="Invalid configuration class selection"):
        ProblemSession(problem).source()


def test_custom_parts_are_added_only_through_defined_classes():
    from PySide6.QtWidgets import QApplication, QMenu

    from morphopt.ui.schemes.base import get_template
    from morphopt.ui.widgets.model_tree import ModelTree

    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create("shapeopt")
    customize(problem, "morphopt.BasePartInterface", "CustomPart", bind=False)
    tree = ModelTree()
    tree.set_problem(problem)
    assert (
        "BasePartInterface"
        not in get_template(problem.scheme).available_geometry_types()
    )
    menu = QMenu()
    tree._build_node_menu(menu, problem.geometry)
    geometry_menu = menu.actions()[0].menu()
    assert not any(
        action.data() == "BasePartInterface" for action in geometry_menu.actions()
    )
    custom_menu = next(
        action.menu() for action in geometry_menu.actions() if action.menu()
    )
    action = next(
        action
        for action in custom_menu.actions()
        if action.text() == "CustomPart [BasePartInterface]"
    )
    previous = len(problem.part_interfaces())
    tree._add_part_interface("BasePartInterface")
    assert len(problem.part_interfaces()) == previous
    action.trigger()
    added = problem.part_interfaces()[-1]
    assert added.custom_class == "CustomPart"
    title = f"{added.name} [CustomPart]"
    assert tree._node_item[added].text(0) == title
    tree.apply_language()
    tree.apply_language()
    assert tree._node_item[added].text(0) == title
    assert (
        tree._node_item[added.instances()[0]].text(0)
        == f"{added.instances()[0].name} [Instance]"
    )
    tree.close()
