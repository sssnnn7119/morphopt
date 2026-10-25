"""INP selections stay usable before a mesh is ready for preview or analysis."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QComboBox

from morphopt.optcore.modelparams.parts import INPPart
from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.editing import set_node_field
from morphopt.ui.application.fields import dynamic_choices, fields_for_node
from morphopt.ui.application.part_sets import PartSetCatalog, PartSets
from morphopt.ui.model.node_types.parts import INPPartNode
from morphopt.ui.model.problem import FEAComponentNode
from morphopt.ui.widgets.definition_actions import DefinitionActions
from morphopt.ui.widgets.definition_manager import DefinitionManagerEditor


REFERENCE = Path(__file__).resolve().parents[2] / "docs/examples/reference-box.inp"


@pytest.fixture
def multi_part_inp(tmp_path):
    contents = REFERENCE.read_text()
    block, materials = contents.split("*Part, name=ReferenceBox\n", 1)[1].split(
        "*End Part\n", 1
    )
    path = tmp_path / "assembly.inp"
    path.write_text(
        "*Part, name=Body\n" + block.replace("extern", "body_outer")
        + "*End Part\n*Part, name=Lid\n"
        + block.replace("extern", "lid_outer").replace("nodes_xmin", "lid_fixed")
        + "*End Part\n" + materials
    )
    return path


def test_inp_catalog_matches_imported_mesh_sets():
    part = INPPartNode(name="imported", mesh_file=str(REFERENCE))
    imported = INPPart(str(REFERENCE), part_name=part.name).get_part()
    imported.initialize()

    assert PartSetCatalog.inp(part) == PartSets(
        tuple(imported.set_nodes), tuple(imported.surfaces.keys()), tuple(imported.elems)
    )
    fields, _, choices = fields_for_node(part)
    assert choices == {
        "inp_part_name": ["ReferenceBox"], "exterior_surface": ["extern"]
    }
    assert all(
        field.type == "combo" and not field.editable
        for field in fields if field.key in choices
    )


def test_multi_part_catalog_does_not_require_a_part_selection(multi_part_inp):
    problem = ProblemLibrary.create_blank()
    part = INPPartNode(name="imported", mesh_file=str(multi_part_inp))
    problem.add_part(part)
    catalog = PartSetCatalog(problem)
    _, _, choices = fields_for_node(part, problem, sets=catalog)

    assert choices == {"inp_part_name": ["Body", "Lid"], "exterior_surface": []}
    assert catalog.for_part(part) == PartSets()

    set_node_field(part, "inp_part_name", "Lid", problem)
    catalog.invalidate()
    pressure = FEAComponentNode.create("Pressure")
    problem.add_component(pressure)
    assert problem.set_component_reference(pressure, "instance_name", part.instances[0])
    assert dynamic_choices(problem, pressure.type, pressure, sets=catalog)[
        "surface_name"
    ] == ["lid_outer"]
    assert catalog.for_part(part).nodes == ("lid_fixed", "nodes_xmax")


def test_geometry_editor_updates_part_and_surface_choices(multi_part_inp):
    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create_blank()
    part = INPPartNode(name="imported")
    problem.add_part(part)
    actions = DefinitionActions()
    actions.set_problem(problem)
    manager = DefinitionManagerEditor("geometry", actions, sets=PartSetCatalog(problem))
    manager.edit_node(None, problem, part)
    editor, _ = manager._node_editors[part]
    part_combo = editor._controls["inp_part_name"]
    surface_combo = editor._controls["exterior_surface"]
    assert isinstance(part_combo, QComboBox) and not part_combo.isEditable()
    assert isinstance(surface_combo, QComboBox) and not surface_combo.isEditable()

    def select(combo, value):
        index = combo.findData(value)
        assert index >= 0
        combo.setCurrentIndex(index)

    try:
        file_edit = editor._controls["mesh_file"]
        file_edit.setText(str(multi_part_inp))
        file_edit.editingFinished.emit()
        select(part_combo, "Body")
        select(surface_combo, "body_outer")
        assert part.inp_part_name == "Body"
        assert part.exterior_surface == "body_outer"

        select(part_combo, "Lid")
        assert part.inp_part_name == "Lid"
        assert part.exterior_surface == ""
        assert surface_combo.currentData() == ""
        assert surface_combo.findData("body_outer") == -1
        select(surface_combo, "lid_outer")
        assert part.exterior_surface == "lid_outer"

        file_edit.setText(str(REFERENCE))
        file_edit.editingFinished.emit()
        assert part.inp_part_name == part_combo.currentData() == "ReferenceBox"
        assert part.exterior_surface == surface_combo.currentData() == ""
        assert surface_combo.findData("extern") >= 0
        assert part_combo.findData("Lid") == -1
        select(surface_combo, "extern")
        assert part.exterior_surface == "extern"
    finally:
        manager.close()
        manager.deleteLater()
        app.processEvents()


def test_inp_choices_do_not_construct_a_finite_element_model(tmp_path, monkeypatch):
    import torchfea

    def forbid_import(*args, **kwargs):
        pytest.fail("Discovering INP names must not construct a finite element model")

    monkeypatch.setattr(torchfea, "from_inp", forbid_import)
    path = tmp_path / "unfinished.inp"
    path.write_text(
        '** *Part, name=Comment\n'
        '*PART, NAME="Body"\n'
        '*ELEMENT, TYPE=c3d8\n'
        '*NSET, NSET=Fixed\n'
        '*SURFACE, TYPE=ELEMENT, NAME=Outer\n'
        '*SURFACE, TYPE=ELEMENT, NAME=Outer\n'
        '*END PART\n'
        '*Assembly, name=Assembly\n'
        '*Surface, name=AssemblySurface\n'
        '*End Assembly\n'
    )
    assert PartSetCatalog.inp_parts(str(path)) == {
        "Body": PartSets(nodes=("Fixed",), surfaces=("Outer",), elements=("C3D8",))
    }
    # A replacement at the same path must not reuse the previous file's names.
    path.write_text('*Part, name=NewBody\n*Surface, name=NewOuter\n*End Part\n')
    assert PartSetCatalog.inp_parts(str(path)) == {
        "NewBody": PartSets(surfaces=("NewOuter",))
    }


@pytest.mark.parametrize("file_kind", ["empty", "missing", "directory", "invalid_encoding"])
def test_unavailable_inp_keeps_selection_fields_editable(tmp_path, file_kind):
    path = tmp_path / "mesh.inp"
    if file_kind == "directory":
        path.mkdir()
    elif file_kind == "invalid_encoding":
        path.write_bytes(b"\xff\xfe\x00")
    part = INPPartNode(
        name="imported", inp_part_name="OldBody", exterior_surface="OldOuter"
    )
    set_node_field(part, "mesh_file", "" if file_kind == "empty" else str(path))
    assert part.inp_part_name == part.exterior_surface == ""
    assert fields_for_node(part)[2] == {"inp_part_name": [], "exterior_surface": []}
