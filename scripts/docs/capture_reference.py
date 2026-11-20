"""Real editor and dialog scenarios for the UI reference gallery."""

import base64
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QComboBox, QDialog

from morphopt.constants import CONSTANT
from morphopt.ui.application import ProblemLibrary
from morphopt.ui.codegen.snippets import CodeSnippet
from morphopt.ui.i18n import tr
from morphopt.ui.model import registry
from morphopt.ui.model.configuration import (
    objective_term_config, symmetry_constraint, updater_constraint, updater_objective,
)
from morphopt.ui.model.problem import CADOperationNode, FEAComponentNode, SurfaceNode
from morphopt.ui.presentation.navigation import HelperCodeBlockTreeNode, UpdaterItemTreeNode, UpdaterTreeNode
from morphopt.ui.theme import theme_manager
from morphopt.ui.widgets.file_dialogs import create_file_dialog
from morphopt.ui.widgets.history_dialogs import HistoryCapacityDialog
from morphopt.ui.widgets.quickstart import QuickstartDialog
from morphopt.ui.widgets.template_insert_dialog import TemplateInsertDialog


def capture_reference(window, root, show, select, save):
    """Exercise model-backed forms, menus and view controls with disposable definitions."""
    assets = root / "scripts/docs/assets"
    bending = "examples/bending_actuator/bending_actuator.morph"
    wb = window._workbench

    def example():
        return ProblemLibrary.load(root / bending, issues=[])

    def shot(node, path):
        select(wb, node)
        save(path + ".png", node.name or node.kind)

    def dialog_shot(dialog, path):
        dialog.show()
        save(path + ".png", dialog.windowTitle(), dialog)
        dialog.reject()

    def popup(widget, path):
        if isinstance(widget, QComboBox):
            widget.showPopup()
            menu = widget.view().window()
        else:
            menu = widget
            menu.popup(window.mapToGlobal(window.rect().center()))
        save(path + ".png", path.rsplit("/", 1)[-1], menu)
        menu.hide()

    problem = ProblemLibrary.create_blank()
    show(problem, "Empty definition")
    window.problems.click()
    dialog_shot(window.findChild(QDialog, "modelProblemsDialog"), "ui-quickstart/workspace/model-problems")
    wizard = QuickstartDialog(parent=window)
    wizard.show()
    save("ui-quickstart/workspace/quickstart.png", "Actuator quick start", wizard)
    wizard.fields["method"].setCurrentIndex(wizard.fields["method"].findData("simp"))
    save("ui-quickstart/workspace/quickstart-simp.png", "Topology quick start", wizard)
    wizard.reject()
    dialog_shot(HistoryCapacityDialog(100, 100, window), "ui-quickstart/workspace/history-capacity")
    for name, menu in (("file", window._file_menu), ("settings", window._settings_menu),
                       ("analysis", window._analysis_menu)):
        popup(menu, f"ui-quickstart/workspace/{name}-menu")

    problem = example()
    show(problem, bending)
    select(wb, problem.solver)
    theme_manager.apply(None, "light", persist=False)
    save("ui-reference/appearance/light-theme.png", "Light theme with solver and assembly")
    theme_manager.apply(None, "dark", persist=False)
    for node, editor, path in [
        (problem.geometry, wb.geometry_editor, "geometry/add-part"),
        (problem.loads, wb.loads_editor, "loads/add-interface"),
        (problem.materials, wb.materials_editor, "materials/add-material"),
    ]:
        select(wb, node)
        popup(editor._add_menu, "ui-quickstart/" + path + "-menu")
    select(wb, problem.parts()[0])
    popup(wb.geometry_editor._surface_add_menu(problem.parts()[0]), "ui-quickstart/geometry/add-surface-menu")
    wb.viewer.view_combo.setCurrentIndex(wb.viewer.view_combo.findData("assembly"))
    wb.viewer.host.open_flight()
    dialog_shot(wb.viewer.host._flight_dialog, "ui-quickstart/geometry/first-person")
    wb.viewer.section_enabled.setChecked(True)
    save("ui-quickstart/geometry/section-view.png", "Assembly section")
    wb.viewer.section_enabled.setChecked(False)

    # One card per component, populated with references in the same assembly.
    component = FEAComponentNode.create
    problem.add_component(component("ReferencePoint", name="RP_base", rp_location=[0, 0, 0]))
    rp = dict(rp_name="RP_1")
    pair = dict(rp_name1="RP_1", rp_name2="RP_base")
    body = problem.instance_names()[0]
    for kind, filename, params in [
        ("ConcentratedForce", "concentrated-force", rp),
        ("ConcentratedMoment", "concentrated-moment", rp),
        ("Bodyforce", "body-force", dict(instance_name=body, element_name="C3D4")),
        ("SpringToGround", "spring-to-ground", rp),
        ("SpringBetweenRPs", "spring-between-reference-points", pair),
        ("SphericalJoint", "spherical-joint", pair),
        ("SingleDoFJoint", "single-dof-joint", pair),
        ("BoundaryConditionRP", "reference-point-boundary", rp),
        ("ContactSelf", "self-contact", dict(instance_name=body, surface_name="surface_1_All")),
        ("Contact", "contact", dict(instance_name1=body, instance_name2=body,
                                    surface_name1="surface_0_All", surface_name2="surface_1_All")),
    ]:
        node = component(kind, name=kind, **params)
        problem.add_component(node)
        wb.set_problem(problem)
        shot(node, "ui-reference/loads/" + filename)
    problem.set_jacobian_components(["ConcentratedForce", "ConcentratedMoment"])
    term = objective_term_config(CONSTANT.UI.OBJECTIVE.TYPE_CUSTOM_LOSS)
    term["body"] = "self.set_step('load_case_1')\nreturn self.fe_results['load_case_1'].GC.square().sum()"
    problem.objective.objective_terms = [term]
    wb.set_problem(problem)
    shot(problem.objective, "ui-reference/objectives/custom-loss")
    popup(wb.objective_editor.jacobian_loads.menu(), "ui-reference/objectives/jacobian-loads")
    snippets = next(c for c in wb.objective_editor.findChildren(QComboBox)
                    if c.count() and isinstance(c.itemData(0), CodeSnippet))
    popup(snippets, "ui-reference/objectives/fea-template-menu")
    jacobian = next(snippets.itemData(i) for i in range(snippets.count())
                    if snippets.itemData(i).key == "jacobian_6d_matrix")
    dialog_shot(TemplateInsertDialog(jacobian, problem, window),
                "ui-reference/objectives/jacobian-template-parameters")

    problem = example()
    material = problem.material_nodes()[0]
    show(problem, bending)
    select(wb, material)
    models = next(c for c in wb.materials_editor.findChildren(QComboBox) if c.findText("Ogden") >= 0)
    popup(models, "ui-reference/materials/constitutive-model-menu")
    for model in [models.itemText(i) for i in range(models.count())]:
        material.material_model = model
        wb.set_problem(problem)
        shot(material, "ui-reference/materials/models/" + model.lower())

    # Borrow the actual model and helper method used by a custom component.
    custom_path = "examples/simp_gripper/simp_gripper.morph"
    problem = ProblemLibrary.load(root / custom_path, issues=[])
    helper = registry.HelperFunctionNode(name="squared_error", params={
        "parameters": "value, target", "body": "return (value - target) ** 2",
    })
    problem.helper_functions.append(helper)
    show(problem, custom_path + " with a helper function")
    shot(HelperCodeBlockTreeNode(), "ui-quickstart/custom-code/helper-code")
    shot(helper, "ui-reference/custom-code/helper-function")
    custom = next(c for c in problem.custom_classes if c.base_class == "morphopt.ObjectiveFunction")
    shot(custom, "ui-reference/custom-code/framework-class")
    shot(custom.members[0], "ui-reference/custom-code/method-override")
    shot(problem.objective, "ui-quickstart/custom-code/framework-overrides")
    popup(wb.class_selector.combo, "ui-reference/custom-code/objective-class-selection")

    # Build each CAD history independently so every preview shows its final solid.
    def operation(kind, **params):
        return CADOperationNode.create(kind, operation_id=kind, **params)

    imported = operation("StepImport", filename="PartDesignExample-Body.step",
                         data=base64.b64encode((assets / "PartDesignExample-Body.step").read_bytes()).decode("ascii"))
    for kind, spec in registry.CAD_OPERATION_TYPES.items():
        if kind == "Sphere":
            # Show the spherical zone used in a solid intersection. Its two circular
            # rims are regular CAD edges, including on OCC versions with degenerate pole edges.
            ops = [operation("Sphere", radius=5), operation("Box", x=-6, y=-6, z=-4, dx=12, dy=12, dz=8),
                   operation("Intersect", object_id="Sphere", tool_id="Box")]
        elif spec.group == "primitive":
            ops = [operation(kind)]
        elif kind == "StepImport":
            ops = [imported]
        elif kind in {"Cut", "Fuse", "Intersect"}:
            ops = [operation("Box", dx=16, dy=12, dz=8),
                   operation("Cylinder", x=8, y=6, z=-2, dz=14, radius=4),
                   operation(kind, object_id="Box", tool_id="Cylinder")]
        else:
            ops = [operation("Box"), operation(kind, input_id="Box")]
        problem = ProblemLibrary.create_blank("CAD")
        part = registry.CADPartNode(name="body", children=ops)
        problem.add_part(part)
        show(problem, "CAD feature demonstration: " + kind)
        wb.viewer.view_combo.setCurrentIndex(wb.viewer.view_combo.findData("part"))
        wb.viewer.host.fit_view()
        if kind == "Cut":
            shot(part, "ui-reference/geometry/cad-part")
        shot(next(op for op in ops if op.operation_type == kind),
             "ui-reference/cad/" + ("boolean-cut" if kind == "Cut" else kind.lower()))

    with TemporaryDirectory(prefix="step-export-") as directory:
        picker = create_file_dialog(window, tr("ui.cad.export_step"), directory, save=True)
        picker.setSidebarUrls([])
        picker.setNameFilter("STEP (*.stp *.step)")
        picker.selectFile("body.stp")
        dialog_shot(picker, "ui-reference/cad/export-step-dialog")

    problem = ProblemLibrary.create_blank("Geometry assets")
    part = registry.CADPartNode(name="cad_body", children=[imported])
    problem.add_part(part)
    fixed = registry.MeshSurfaceNode(name="fixed_shell", path_stl=str((assets / "reference-boundary.stl").relative_to(root)))
    problem.add_part(registry.BoundaryPartNode(name="shell", children=[fixed]))
    inp = registry.INPPartNode(name="mesh", mesh_file=str((assets / "reference-box.inp").relative_to(root)))
    problem.add_part(inp)
    show(problem, assets.relative_to(root).as_posix())
    for node, owner, filename in [(fixed, problem.parts()[1], "fixed-stl"), (inp, inp, "inp-part")]:
        wb.viewer.part_combo.setCurrentIndex(next(i for i in range(wb.viewer.part_combo.count()) if wb.viewer.part_combo.itemData(i) is owner))
        shot(node, "ui-reference/geometry/" + filename)
    wb.viewer.part_combo.setCurrentIndex(wb.viewer.part_combo.findData(part))
    wb._center.setCurrentIndex(2)
    save("ui-quickstart/assets/geometry-assets.png", "STEP, STL and INP asset browser")

    for part_type, group, base, selector_path in [
        ("BoundaryPart", "geometry", "UpdaterBoundaryPart", "geometry/class-selection"),
        ("OffsetBoundaryPart", "geometry", "UpdaterOffsetBoundaryPart", "geometry/offset-class-selection"),
        ("BoxPart", "materials", "UpdaterSIMPMaterial", "materials/class-selection"),
    ]:
        problem = ProblemLibrary.create("simp") if group == "materials" else example()
        if part_type == "OffsetBoundaryPart":
            old = problem.parts()[0]
            part = registry.OffsetBoundaryPartNode(name=old.name, children=list(old.children))
            problem.replace_part(old, part)
        else:
            part = problem.parts()[0]
        custom = registry.CustomClassNode(name="My" + base, params={"base_class": "morphopt." + base,
                                                                    "class_type": "override"})
        problem.custom_classes.append(custom)
        show(problem, part_type + " updater demonstration")
        if part_type != "BoundaryPart":
            shot(part, "ui-reference/geometry/" + ("box-part" if group == "materials" else "offset-boundary-part"))
        select(wb, UpdaterTreeNode(problem.updater, group))
        popup(wb.class_selector.combo, "ui-reference/updaters/" + selector_path)
        cfg = getattr(problem.updater, group)[0]
        if group == "materials":
            kinds = [("objective_functions", "materials_objectives", updater_objective(k), k.lower())
                     for k in ("QuadraticSensitivity", "DensityFieldMinimize")]
            kinds.append(("constraints", "materials_penalty", updater_constraint("MaxValue"), "maximum-value"))
        elif part_type == "OffsetBoundaryPart":
            kinds = [("constraints", "geometry_penalty", updater_constraint(k), k.lower())
                     for k in ("InwardCurvatureRadius", "OffsetSurfaceMinThickness")]
        else:
            kinds = [("constraints", "geometry_penalty", updater_constraint(k), file)
                     for k, file in [("MinRadius", "min-radius"), ("VolumeMaximization", "volume-maximization")]]
            # Provide a matching CPGEO pair for the CPGEO-specific constraints.
            for r in (2, 1):
                problem.add_surface(SurfaceNode.create("cpgeo_cylinder", r0=r, length=60), part=part)
            for k in registry.SURFACE_SYMMETRY_CONSTRAINTS:
                if k in {"BspMirror", "Custom"}:
                    continue
                item = symmetry_constraint(k)
                item["surface_index"] = 2 if k.startswith("CPGEO") else 0
                file = {"CPGEORotation": "rotational-symmetry", "BspRelation": "surface-relation"}.get(k, k.lower())
                kinds.append(("symmetry_constraints", "geometry_symmetry", item, file))
        for key, category, item, file in kinds:
            cfg[key] = [item]
            wb.set_problem(problem)
            shot(UpdaterItemTreeNode(problem.updater, category, 0, item),
                 "ui-reference/updaters/" + ("material" if group == "materials" else group) + "/" + file)
