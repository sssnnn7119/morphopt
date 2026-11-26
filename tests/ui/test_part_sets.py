"""Part set lists select exact FE faces and nodes in the right-hand viewport."""

from pathlib import Path

import numpy as np
import pyvista as pv
import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.part_mesh import build_part_mesh
from morphopt.ui.model.node_types.parts import BoundaryPartNode, BoxPartNode, CADPartNode, INPPartNode, OffsetBoundaryPartNode
from morphopt.ui.model.node_types.surfaces import BREPSurfaceNode
from morphopt.ui.model.problem import CADOperationNode, CustomClassNode, FEAComponentNode, HelperVariableNode, MaterialNode, MethodOverrideNode, PartNode
from morphopt.ui.visualization.geometry import PreviewGeometry
from morphopt.ui.visualization.loads import LoadPreviewVisitor
from morphopt.ui.visualization.scene import MarkerLoad, MessageItem


@pytest.fixture
def window(monkeypatch):
    from morphopt.ui import workbench
    from morphopt.ui.widgets import viewer
    from morphopt.ui.widgets.viewport import PlotViewport

    app = QApplication.instance() or QApplication([])

    class Host(QWidget):
        scene_update = PlotViewport.scene_update
        viewChanged = Signal()
        def __init__(self, parent=None):
            super().__init__(parent)
            self.plotter = pv.Plotter(off_screen=True, window_size=(400, 400))
            self._camera_initialized = False
            self._scene_has_geometry = False
            self._geometry_keys = frozenset()

    monkeypatch.setattr(viewer, "PlotViewport", Host)
    problem = ProblemLibrary.create_blank()
    part = BoxPartNode(name="box", length=2, height=2, depth=2, mesh_size=1, mesh_order=1)
    part.instances[0].translation = [10, 20, 30]
    part.instances[0].rotation = [0, 0, np.pi / 2]
    problem.add_part(part)
    window = workbench.Workbench(problem)
    window.geometry_editor.edit_node(None, problem, part)
    yield window, part
    window.viewer.host.plotter.close()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_part_list_highlights_nodes_and_surfaces_without_changing_definition(window):
    window, part = window
    viewer = window.viewer
    tree = window.geometry_editor._part_set_lists[part]
    before = window.problem.to_dict()
    assert viewer.view_combo.currentData() == "assembly"

    def select(kind, name):
        group = tree.topLevelItem(0 if kind == "surfaces" else 1)
        item = next(group.child(i) for i in range(group.childCount()) if group.child(i).text(0) == name)
        tree.setCurrentItem(item)

    select("nodes", "nodes_xmax")
    assert viewer.view_combo.currentData() == "part"
    assert viewer.part_combo.currentData() is part
    assert viewer._set_selection == (part, "nodes", "nodes_xmax")
    camera = viewer.host.plotter.camera_position
    actor = viewer.renderer._set_actors[0]
    assert actor.mapper.dataset.n_points == 9
    assert np.allclose(actor.mapper.dataset.points[:, 0], 2)
    assert "nodes_xmax" in viewer.face_info.text()
    assert not actor.GetPickable()

    model = viewer.geometry._part_cache[id(part)]
    select("surfaces", "surface_xmin")
    assert viewer.geometry._part_cache[id(part)] is model
    assert len(viewer.renderer._set_actors) == 1
    assert np.allclose(viewer.renderer._set_actors[0].mapper.dataset.points[:, 0], 0)
    assert "surface_xmin" in viewer.face_info.text()
    viewer.section_enabled.setChecked(True)
    assert viewer.renderer._set_actors[0].mapper.GetNumberOfClippingPlanes() == 1
    assert viewer._set_selection == (part, "surfaces", "surface_xmin")
    assert viewer.host.plotter.camera_position == camera
    assert window.problem.to_dict() == before

    tree.setCurrentItem(tree.topLevelItem(0))
    assert not viewer.renderer.has_set_selection
    assert all(actor.prop.opacity == 1 for actor in viewer.renderer._geometry_actors)


def test_selection_follows_geometry_edits_and_switching_preview_modes(window):
    window, part = window
    viewer = window.viewer
    viewer.show_part_set(part, "nodes", "nodes_zmax")
    part.depth = 4
    viewer.set_problem(window.problem)
    assert viewer._set_selection == (part, "nodes", "nodes_zmax")
    assert np.allclose(viewer.renderer._set_actors[0].mapper.dataset.points[:, 2], 4)
    viewer.view_combo.setCurrentIndex(viewer.view_combo.findData("assembly"))
    assert viewer._set_selection is None
    assert not viewer.renderer.has_set_selection
    assert all(actor.prop.opacity == 1 for actor in viewer.renderer._geometry_actors)
    viewer.set_problem(window.problem)
    assert not viewer.renderer.has_set_selection
    viewer.view_combo.setCurrentIndex(viewer.view_combo.findData("part"))
    assert not viewer.renderer.has_set_selection
    viewer.show_part_set(part, "nodes", "nodes_zmax")
    assert np.allclose(viewer.renderer._set_actors[0].mapper.dataset.points[:, 2], 4)
    viewer.show_part_set(part, "nodes", "deleted_set")
    assert not viewer.renderer.has_set_selection
    assert viewer._set_selection is None
    assert "deleted_set" in viewer.face_info.text()


def test_selecting_another_parts_set_switches_to_its_local_view(window):
    window, first = window
    viewer = window.viewer
    second = BoxPartNode(name="other", length=6, height=2, depth=2, mesh_size=1, mesh_order=1)
    window.problem.add_part(second)
    viewer.set_problem(window.problem)
    viewer.show_part_set(first, "nodes", "nodes_xmax")
    viewer.show_part_set(second, "nodes", "nodes_xmax")
    assert viewer.view_combo.currentData() == "part"
    assert viewer.part_combo.currentData() is second
    assert viewer._set_selection == (second, "nodes", "nodes_xmax")
    assert np.allclose(viewer.renderer._set_actors[0].mapper.dataset.points[:, 0], 6)


def test_inp_highlight_uses_actual_node_sets():
    problem = ProblemLibrary.create_blank()
    part = INPPartNode(name="imported", mesh_file=str(Path(__file__).resolve().parents[2] / "scripts/docs/assets/reference-box.inp"))
    problem.add_part(part)
    geometry = PreviewGeometry()
    geometry.build(problem, "part", part)
    selected = geometry.mesh_for_set(part, "nodes", "nodes_xmin")
    assert selected.n_points == 4
    assert np.allclose(selected.points[:, 0], 0)


def test_brep_selection_mesh_preserves_exact_named_sets(step_factory):
    import base64
    from morphopt.shapeopt.surfaces.brep_surface import BREPSurface

    source = step_factory("box")
    brep = BREPSurface(source)
    metadata = brep.metadata()
    part = BoundaryPartNode(name="boundary", fea_seed_size=2, mesh_order=1)
    import json
    part.add_surface(BREPSurfaceNode(
        name="outer", filename=source.name,
        data=base64.b64encode(source.read_bytes()).decode("ascii"),
        brep_metadata=json.dumps(metadata),
    ))
    problem = ProblemLibrary.create_blank()
    problem.add_part(part)
    mesh = build_part_mesh(part, problem)
    assert "surface_0_All" in mesh.surfaces
    assert "surface_0_All" in mesh.set_nodes
    geometry = PreviewGeometry()
    geometry.build(problem, "part", part)
    face = next(iter(metadata["face_map"]))
    selected = geometry.mesh_for_set(part, "nodes", f"{face}_nodes")
    assert selected.n_points > 0
    assert np.count_nonzero(np.ptp(selected.points, axis=0) < 1e-8) == 1


def test_custom_part_lists_and_highlights_its_kernel_sets(monkeypatch):
    from morphopt.ui.application import part_mesh
    from morphopt.ui.application.part_sets import PartSetCatalog

    problem = ProblemLibrary.create_blank()
    custom = CustomClassNode(name="NamedPart", params={"base_class": "morphopt.BasePart"})
    custom.add_child(MethodOverrideNode(name="build_part", params={"body": (
        "mesh = morphopt.BoxPart(length=2, height=2, depth=2, mesh_size=1, mesh_order=1).get_part()\n"
        "mesh.add_node_set('custom_tip', [0])\n"
        "return mesh"
    )}))
    problem.custom_classes.append(custom)
    part = PartNode.create("BasePart", name="custom_body")
    part.custom_class = "NamedPart"
    problem.add_part(part)
    builds = []
    def build(node, definition):
        builds.append(node)
        return build_part_mesh(node, definition)

    monkeypatch.setattr(part_mesh, "build_part_mesh", build)
    catalog = PartSetCatalog(problem)
    assert "custom_tip" in catalog.for_part(part).nodes
    geometry = PreviewGeometry()
    geometry.part_sets = catalog
    scene = geometry.build(problem, "part", part)
    assert len(scene.base_meshes) == 1
    selected = geometry.mesh_for_set(part, "nodes", "custom_tip")
    assert selected.n_points == 1
    assert builds == [part]

    method = custom.members[0]
    method.body = method.body.replace("custom_tip", "new_tip")
    catalog.invalidate()
    assert "new_tip" in catalog.for_part(part).nodes
    geometry.build(problem, "part", part)
    assert geometry.mesh_for_set(part, "nodes", "new_tip").n_points == 1
    assert builds == [part, part]


def test_cad_preview_with_serializable_helper_class_and_custom_boundary_set():
    problem = ProblemLibrary.create_blank()
    problem.helper_code = (
        "import numpy as np\n"
        "from torchfea.model.boundarys import Boundary_Condition\n"
        "class PreviewTestBoundary(Boundary_Condition):\n"
        "    pass\n"
    )
    problem.helper_variables.append(HelperVariableNode(
        name="length", params={"value": "4.0"},
    ))
    custom = CustomClassNode(name="PortCADPart", params={"base_class": "morphopt.CADPart"})
    custom.add_child(MethodOverrideNode(name="define_mesh_sets", params={"body": (
        "super().define_mesh_sets(part)\n"
        "x = part.nodes[:, 0].detach().cpu().numpy()\n"
        "part.add_node_set('port', np.flatnonzero(np.isclose(x, length)))"
    )}))
    problem.custom_classes.append(custom)
    part = CADPartNode(name="finger", mesh_size=1)
    part.custom_class = custom.name
    part.add_child(CADOperationNode.create("Box", "body", dx="length", dy=2, dz=2))
    instance = part.instances[0]
    instance.translation = [10, 20, 30]
    problem.add_part(part)
    problem.add_component(FEAComponentNode.create(
        "BoundaryCondition", "fixed_port", instance_name=instance.name,
        set_nodes_name="port", index_dof=[0, 1, 2],
    ))

    geometry = PreviewGeometry()
    scene = geometry.build(problem, "assembly")
    assert not any(isinstance(item, MessageItem) for item in scene.items)
    assert scene.bounds == pytest.approx((10, 14, 20, 22, 30, 32))
    loads = LoadPreviewVisitor().build(geometry, None)
    assert not any(isinstance(item, MessageItem) for item in loads.items)
    (marker,) = [item for item in loads.items if isinstance(item, MarkerLoad)]
    port = geometry.mesh_for_set(part, "nodes", "port")
    assert port.n_points > 0
    np.testing.assert_allclose(marker.location, port.points.mean(axis=0) + instance.translation)


@pytest.mark.parametrize("part_type,element_name,quadratic_type", [
    (BoundaryPartNode, "C3D4", "C3D10"),
    (OffsetBoundaryPartNode, "C3D4", "C3D10"),
    (OffsetBoundaryPartNode, "C3D6", "C3D15"),
    (CADPartNode, "C3D4", "C3D10"),
    (BoxPartNode, "C3D8", "C3D20"),
])
@pytest.mark.parametrize("order", [1, 2])
def test_material_and_bodyforce_share_stable_names_and_actual_types(part_type, element_name, quadratic_type, order):
    from morphopt.ui.application.fields import fields_for_node
    from morphopt.ui.application.part_sets import PartSetCatalog
    from morphopt.ui.application.validation import DefinitionValidation
    from morphopt.ui.widgets.editor import PropertyEditor

    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create_blank()
    part = part_type(name="body", mesh_order=order)
    if isinstance(part, CADPartNode):
        part.add_child(CADOperationNode.create("Box", operation_id="box"))
    problem.add_part(part)
    material = MaterialNode.create("HomogeneousMaterial", name="solid")
    problem.add_material(material)
    problem.set_material_part(material, part)
    material.elementname = element_name
    bodyforce = FEAComponentNode.create("Bodyforce", name="gravity")
    problem.add_component(bodyforce)
    problem.set_component_reference(bodyforce, "instance_name", part.instances[0])
    bodyforce.element_name = element_name

    actual_type = quadratic_type if order == 2 else element_name
    assert PartSetCatalog.element_type(part, element_name) == actual_type
    expected_names = ("C3D4", "C3D6") if isinstance(part, OffsetBoundaryPartNode) else (element_name,)
    assert PartSetCatalog(problem).for_part(part).elements == expected_names
    for node, key in ((material, "elementname"), (bodyforce, "element_name")):
        fields, _, choices = fields_for_node(node, problem)
        spec = next(field for field in fields if field.key == key)
        assert choices[key] == list(expected_names)
        assert element_name in spec.choices
        validation = DefinitionValidation(problem)
        validation.field(node, spec, element_name)
        assert not validation.errors
        validation.field(node, spec, "missing_block")
        assert id(node) in validation.errors
        editor = PropertyEditor()
        try:
            editor.edit_node(node, completion_problem=problem)
            selector = editor._controls[key]
            expected = f"{element_name} [{actual_type}]" if order == 2 else element_name
            assert selector.currentText() == expected
            assert selector.currentData() == element_name
            if order == 2:
                part.mesh_order = 1
                editor.edit_node(node, completion_problem=problem)
                assert selector.currentText() == element_name
                part.mesh_order = 2
        finally:
            editor.close()
    assert "" in next(field for field in fields_for_node(material, problem)[0] if field.key == "elementname").choices


def test_material_selector_refresh_removes_the_previous_parts_blocks():
    from morphopt.ui.widgets.editor import PropertyEditor

    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create("shapeopt")
    material = problem.material_nodes()[0]
    material.elementname = "C3D4"
    second = BoxPartNode(name="box")
    problem.add_part(second)
    editor = PropertyEditor()
    try:
        editor.edit_node(material, completion_problem=problem)
        assert editor._controls["elementname"].findData("C3D4") >= 0
        problem.set_material_part(material, second)
        editor.refresh_choices()
        selector = editor._controls["elementname"]
        assert selector.findData("C3D4") == -1
        assert selector.findData("C3D8") >= 0
    finally:
        editor.close()


@pytest.mark.parametrize("order", [1, 2])
def test_offset_catalog_matches_the_exported_kernel_part(order):
    from morphopt.ui.application.part_sets import PartSetCatalog
    from morphopt.ui.model.problem import SurfaceNode

    problem = ProblemLibrary.create_blank()
    part = OffsetBoundaryPartNode(
        name="offset", fea_seed_size=1.5, mesh_order=order,
        shell_thickness=0.15, num_layers=2,
    )
    part.add_surface(SurfaceNode.create(
        "bsp_cylinder", r0=3.0, length=8.0, seed_size=1.0, perturbation_L=-1.0,
    ))
    part.add_surface(SurfaceNode.create(
        "cpgeo_sphere", r0=1.0, seed_size=0.3,
        init_location=[0.0, 0.0, 4.0],
    ))
    problem.add_part(part)
    model = build_part_mesh(part, problem)
    assert tuple(model.elems) == PartSetCatalog(problem).for_part(part).elements == ("C3D4", "C3D6")
    for name, element in model.elems.items():
        assert element._elems.shape[0] > 0
        assert type(element).__name__ == PartSetCatalog.element_type(part, name)


def test_new_material_binds_the_only_part_and_offers_both_offset_blocks():
    from morphopt.ui.application.editing import DefinitionCommands
    from morphopt.ui.widgets.definition_actions import DefinitionActions
    from morphopt.ui.widgets.definition_manager import DefinitionManagerEditor

    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create_blank()
    part = OffsetBoundaryPartNode(name="offset")
    problem.add_part(part)
    material = DefinitionCommands(problem).add_material("HomogeneousMaterial")
    assert material.part is part
    actions = DefinitionActions()
    actions.set_problem(problem)
    manager = DefinitionManagerEditor("materials", actions)
    try:
        manager.edit_node(None, problem, material)
        editor = manager._node_editors[material][0]
        selector = editor._controls["elementname"]
        assert selector.isEnabled()
        assert [selector.itemData(index) for index in range(selector.count())] == ["", "C3D4", "C3D6"]
        selector.setCurrentIndex(selector.findData("C3D6"))
        assert material.elementname == "C3D6"
    finally:
        manager.close()


def test_material_requires_a_part_before_offering_element_choices():
    from morphopt.ui.application.editing import DefinitionCommands
    from morphopt.ui.widgets.definition_actions import DefinitionActions
    from morphopt.ui.widgets.definition_manager import DefinitionManagerEditor

    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create_blank()
    first, second = OffsetBoundaryPartNode(name="offset"), BoxPartNode(name="box")
    problem.add_part(first)
    problem.add_part(second)
    material = DefinitionCommands(problem).add_material("HomogeneousMaterial")
    actions = DefinitionActions()
    actions.set_problem(problem)
    manager = DefinitionManagerEditor("materials", actions)
    try:
        manager.edit_node(None, problem, material)
        editor = manager._node_editors[material][0]
        selector = editor._controls["elementname"]
        assert not selector.isEnabled()
        assert selector.currentIndex() == -1
        assert selector.placeholderText()
        parts = editor._controls["part_name"]
        parts.setCurrentIndex(parts.findData("offset"))
        assert material.part is first
        assert selector.isEnabled()
        assert selector.findData("C3D6") >= 0
        parts.setCurrentIndex(parts.findData("box"))
        assert material.part is second
        assert selector.findData("C3D6") == -1
        assert selector.findData("C3D8") >= 0
    finally:
        manager.close()


@pytest.mark.parametrize("name,valid", [("C3D4", True), ("C3D6", True), ("C3D8", False)])
def test_offset_bodyforce_and_volume_fraction_validate_the_owning_parts_blocks(name, valid):
    from morphopt.ui.application.validation import DefinitionValidation

    problem = ProblemLibrary.create_blank()
    part = OffsetBoundaryPartNode(name="offset")
    problem.add_part(part)
    material = MaterialNode.create("SIMP_BSPFieldMaterials", name="density")
    problem.add_material(material)
    problem.set_material_part(material, part)
    bodyforce = FEAComponentNode.create("Bodyforce", name="gravity", element_name=name)
    problem.add_component(bodyforce)
    problem.set_component_reference(bodyforce, "instance_name", part.instances[0])
    config = problem.add_material_updater(material)
    volume = next(item for item in config["constraints"] if item["type"] == "VolFrac")
    volume["params"]["elementname"] = name
    validation = DefinitionValidation(problem)
    validation.node(bodyforce)
    validation.updaters()
    assert (id(bodyforce) not in validation.errors) == valid
    assert (id(volume) not in validation.errors) == valid
