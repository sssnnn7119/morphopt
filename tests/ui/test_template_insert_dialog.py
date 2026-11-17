"""FE code templates select element blocks from their selected instance."""

import pytest
from PySide6.QtWidgets import QApplication

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.fields import SnippetInputs
from morphopt.ui.codegen.snippets import shared_fea_snippets
from morphopt.ui.model.node_types.parts import (
    BoundaryPartNode, BoxPartNode, OffsetBoundaryPartNode,
)
from morphopt.ui.widgets.template_insert_dialog import TemplateInsertDialog


@pytest.fixture
def problem():
    definition = ProblemLibrary.create_blank()
    for part in (
        OffsetBoundaryPartNode(name="offset"),
        OffsetBoundaryPartNode(name="other_offset"),
        BoundaryPartNode(name="boundary"),
        BoxPartNode(name="box"),
    ):
        definition.add_part(part)
    return definition


@pytest.mark.parametrize("instance,elements", [
    ("", []),
    ("missing", []),
    ("offset-1", ["C3D4", "C3D6"]),
    ("boundary-1", ["C3D4"]),
    ("box-1", ["C3D8"]),
])
def test_snippet_element_catalog_is_scoped_to_its_instance(problem, instance, elements):
    assert SnippetInputs(problem).values("elements", instance_name=instance) == elements


@pytest.mark.parametrize("key", ["gaussian_energy_density", "gaussian_deformation_gradient"])
def test_element_selector_follows_instance_and_preserves_only_valid_selections(problem, key):
    app = QApplication.instance() or QApplication([])
    snippet = next(item for item in shared_fea_snippets() if item.key == key)
    dialog = TemplateInsertDialog(snippet, problem)
    instances = dialog._fields["instance_name"]
    elements = dialog._fields["element_name"]

    def names():
        return [elements.itemData(index) for index in range(elements.count())]

    try:
        assert names() == [""]
        instances.setCurrentIndex(instances.findData("offset-1"))
        assert names() == ["", "C3D4", "C3D6"]
        elements.setCurrentIndex(elements.findData("C3D6"))
        instances.setCurrentIndex(instances.findData("other_offset-1"))
        assert dialog.parameter_values()["element_name"] == "C3D6"
        assert "element_name = 'C3D6'" in snippet.render(dialog.parameter_values())

        instances.setCurrentIndex(instances.findData("boundary-1"))
        assert names() == ["", "C3D4"]
        assert dialog.parameter_values()["element_name"] == ""
        elements.setCurrentIndex(elements.findData("C3D4"))
        instances.setCurrentIndex(instances.findData("offset-1"))
        assert dialog.parameter_values()["element_name"] == "C3D4"

        instances.setCurrentIndex(instances.findData("box-1"))
        assert names() == ["", "C3D8"]
        assert dialog.parameter_values()["element_name"] == ""
        instances.setEditText("missing")
        assert names() == [""]
    finally:
        dialog.close()
        app.processEvents()
