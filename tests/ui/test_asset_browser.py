from __future__ import annotations

import base64
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.codegen.assets import DefinitionAsset, collect_python_assets
from morphopt.ui.model.node_types.parts import BoundaryPartNode, CADPartNode, INPPartNode
from morphopt.ui.model.node_types.surfaces import MeshSurfaceNode
from morphopt.ui.model.problem import CADOperationNode
from morphopt.ui.refresh import RefreshContext
from morphopt.ui.visualization.assets import geometry_asset_scene
from morphopt.ui.widgets import asset_browser
from morphopt.ui.widgets.asset_browser import AssetBrowser, AssetPreview


EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def geometry_problem(format):
    problem = ProblemLibrary.create_blank()
    if format == "step":
        path = EXAMPLES / "PartDesignExample-Body.step"
        operation = CADOperationNode.create("StepImport", operation_id="import_body")
        operation.filename = path.name
        operation.data = base64.b64encode(path.read_bytes()).decode("ascii")
        problem.add_part(CADPartNode(name="body", children=[operation]))
    elif format == "inp":
        problem.add_part(INPPartNode(name="body", mesh_file=str(EXAMPLES / "reference-box.inp")))
    else:
        surface = MeshSurfaceNode(name="shell", path_stl=str(EXAMPLES / "reference-boundary.stl"))
        problem.add_part(BoundaryPartNode(name="body", children=[surface]))
    return problem


@pytest.mark.parametrize("format", ["step", "stl", "inp"])
def test_geometry_assets_build_real_scenes_without_changing_definition(format):
    problem = geometry_problem(format)
    problem.helper_code = "raise RuntimeError('Asset preview must not execute model helpers')"
    before = problem.to_dict()
    paths, assets = collect_python_assets(problem)
    asset = next(iter(assets.values()))
    scene = geometry_asset_scene(asset)
    assert asset.category == "geometry"
    assert asset.format == format
    assert asset.relative_path in paths.values()
    assert asset.references
    assert scene.base_meshes
    assert all(mesh.n_cells > 0 for _, mesh, _ in scene.base_meshes)
    assert problem.to_dict() == before


class TextAssetPreview(AssetPreview):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.shown = []
        self.text = QLabel()
        QVBoxLayout(self).addWidget(self.text)

    def set_asset(self, asset, problem):
        self.shown.append(asset.name)
        self.text.setText(asset.content.decode("utf-8"))


def test_asset_list_is_lazy_updates_references_and_preserves_selection(app, tmp_path):
    path = tmp_path / "mesh.inp"
    path.write_text("mesh one")
    problem = ProblemLibrary.create_blank()
    problem.add_part(INPPartNode(name="first", mesh_file=str(path)))
    problem.add_part(INPPartNode(name="second", mesh_file=str(path)))
    browser = AssetBrowser()
    browser.register_preview("geometry", "ui.assets.geometry", TextAssetPreview)
    browser.refresh_ui(RefreshContext(problem))
    assert not browser._previews
    assert browser.tree.topLevelItemCount() == 0

    browser.show()
    app.processEvents()
    group = browser.tree.topLevelItem(0)
    assert group.childCount() == 1
    assert group.child(0).data(0, Qt.ItemDataRole.UserRole) == "mesh.inp"
    preview = browser._previews["geometry"]
    assert preview.shown == ["mesh.inp"]
    assert "first, second" in browser.info.text()
    browser.reload_button.click()
    assert preview.shown == ["mesh.inp"]
    path.write_text("mesh two")
    browser.reload_button.click()
    assert preview.text.text() == "mesh two"
    path.unlink()
    browser.reload_button.click()
    assert browser.stack.currentWidget() is browser.message
    assert str(path) in browser.message.text()
    browser.close()


def test_asset_category_can_register_its_own_display(app, monkeypatch):
    problem = ProblemLibrary.create_blank()
    asset = DefinitionAsset(
        "config.txt", b"parameter=1", "txt", "configuration",
        None, problem.root, ["settings"],
    )
    monkeypatch.setattr(asset_browser, "collect_python_assets", lambda _: ({}, {asset.name: asset}))
    browser = AssetBrowser()
    browser.register_preview("configuration", "ui.assets.name", TextAssetPreview)
    browser.refresh_ui(RefreshContext(problem))
    browser.show()
    app.processEvents()
    preview = browser._previews["configuration"]
    assert browser.stack.currentWidget() is preview
    assert preview.text.text() == "parameter=1"
    assert not browser._previews.get("geometry")
    browser.close()
