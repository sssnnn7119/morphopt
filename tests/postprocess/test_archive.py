"""Regression checks for optimization archive state restoration."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import imageio.v2 as imageio
import pyvista as pv
import pytest
from PIL import Image

from morphopt.postprocess import (
    IterationModel,
    OptimizationArchive,
    export_design_components,
    export_history_gif,
    export_history_inp,
)
from morphopt.shapeopt.surfaces.brep_surface import BREPSurface


def test_history_inp_maps_lnj_to_standard_neo_hookean(iteration_model, tmp_path):
    import torchfea

    model, controller, _ = iteration_model
    block = controller.assembly.get_part("body").elems["C3D8"]
    name, original = next(iter(block.materials.items()))
    output = tmp_path / "model.inp"
    export_history_inp(model.folder, model.iteration, model.case, str(output))
    standard = output.read_bytes()
    block.set_materials(torchfea.materials.NeoHookeanLnJ(original.mu, original.kappa), name=name)
    controller.save_model(str(model.model_path), if_save_source_code=False)
    export_history_inp(model.folder, model.iteration, model.case, str(output))
    assert output.read_bytes() == standard


def test_partial_geometry_restore_invalidates_full_parameter_cache(tmp_path, monkeypatch):
    class Part:
        def __init__(self) -> None:
            self.iteration = None
            self.fail = False

        def load(self, *, foldpath: str, iteration: int) -> None:
            self.iteration = iteration
            if self.fail:
                raise RuntimeError("incomplete part restore")

    class Params:
        def __init__(self) -> None:
            self.geometry = SimpleNamespace(
                interfaces={"a": Part(), "b": Part()}, initialize=lambda: None
            )
            self.feamodel = SimpleNamespace(initialize_interfaces=lambda: None)
            self.materials = SimpleNamespace(initialize=lambda: None)
            self.loads: list[int] = []

        def load(self, *, foldpath: str, iteration: int) -> None:
            self.loads.append(iteration)
            for part in self.geometry.interfaces.values():
                part.iteration = iteration

    monkeypatch.setattr(
        "morphopt.postprocess.archive._import_controller",
        lambda _folder: SimpleNamespace(Params=Params),
    )
    archive = OptimizationArchive(tmp_path)
    params = archive.load_parameters(1)
    part = params.geometry.interfaces["a"]

    archive.load_geometry_part("a", 2)
    assert part.iteration == 2
    archive.load_parameters(1)
    assert part.iteration == 1
    assert params.loads == [1, 1]

    part.fail = True
    with pytest.raises(RuntimeError, match="incomplete part restore"):
        archive.load_geometry_part("a", 3)
    part.fail = False
    archive.load_parameters(1)
    assert part.iteration == 1
    assert params.loads == [1, 1, 1]


def test_history_surface_uses_preceding_checkpoint_when_scrubbing(design_archive):
    archive = design_archive
    part = archive.params.geometry.interfaces["body"]

    def controls(part):
        return part.surfaceinterfaces[1].control_points.detach().clone()

    expected = controls(archive.load_geometry_part("body", 1))
    initial = controls(archive.load_design_component(part, 1))
    assert not initial.equal(expected)
    assert controls(archive.load_design_component(part, 2)).equal(expected)
    assert controls(archive.load_design_component(part, 1)).equal(initial)


def test_first_history_row_restores_saved_initial_control_points(design_archive):
    archive = design_archive
    part = archive.params.geometry.interfaces["body"]
    surface = part.surfaceinterfaces[1]
    surface.update_variables(surface.control_points.new_full(surface.control_points.shape, 0.35))
    initial = surface.control_points.clone()
    part.save(str(archive.log_folder), iteration=0)

    updated = archive.load_design_component(part, 2).surfaceinterfaces[1].control_points.clone()
    assert not updated.equal(initial)
    assert archive.load_design_component(part, 1).surfaceinterfaces[1].control_points.equal(initial)
    assert archive.load_design_component(part, 2).surfaceinterfaces[1].control_points.equal(updated)


def test_deformation_uses_the_selected_model_and_case(iteration_model, tmp_path):
    import numpy as np
    from morphopt.optcore.objfunc import ObjectiveFunction
    from morphopt.postprocess import cpu_torch_defaults

    _, controller, result = iteration_model
    archive = OptimizationArchive(tmp_path / "new_run")
    objective = ObjectiveFunction()
    objective.fe = controller
    objective.fe_results = {"loaded": result}
    for folder in objective.pathlog_required():
        (archive.log_folder / folder).mkdir(parents=True)
    with cpu_torch_defaults():
        objective.save(str(archive.log_folder), 3)
        expected, = controller.assembly.get_meshes(GC=result.GC).values()
    assert not (archive.log_folder / "deformation").exists()
    assert archive.deformation_cases() == ("loaded",)
    mesh = archive.deformation_mesh("loaded", 3)
    np.testing.assert_allclose(
        sorted(map(tuple, mesh.points)), sorted(map(tuple, expected.clean().points))
    )
    assert mesh.n_cells == expected.n_cells
    assert archive.deformation_mesh("loaded", 2) is None
    assert archive.deformation_mesh("missing", 3) is None


def test_iteration_model_reads_named_cases_in_registered_order(tmp_path):
    folder = tmp_path / "log" / "femodel&results"
    folder.mkdir(parents=True)
    (folder / "load_cases.json").write_text(
        json.dumps(["case_b", "case_a", "case_missing"]), encoding="utf-8"
    )
    for filename in ("femodel_3.npz", "femodel_7.npz",
                     "result_case_a_iter_3.npz", "result_case_b_iter_3.npz"):
        (folder / filename).touch()

    model = IterationModel(str(tmp_path), 3, "case_b")
    assert model.iterations(str(tmp_path)) == (3, 7)
    assert model.cases() == ("case_b", "case_a")
    assert model.model_path == folder / "femodel_3.npz"
    assert model.result_path == folder / "result_case_b_iter_3.npz"




def test_simp_checkpoint_exports_sampled_density_field(tmp_path):
    import numpy as np
    import shutil
    import torch
    from morphopt.postprocess import cpu_torch_defaults

    sample = Path(__file__).resolve().parents[2] / "examples/simp_gripper/simp_gripper.py"
    archive = OptimizationArchive(tmp_path / "run")
    scripts = archive.folder / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(sample, scripts / "MAIN_SCRIPT_FOR_RESTART.py")
    with cpu_torch_defaults():
        material = archive.initialize_params().materials.interface("body")
        expected = torch.full_like(material.get_parameters()[0], 1.5)
        material.set_parameters([expected])
        material.save(str(archive.log_folder), 1)
        material.set_parameters([torch.zeros_like(expected)])
        material.load(str(archive.log_folder), 1)
        torch.testing.assert_close(material.get_parameters()[0], expected)
        material.export(tmp_path)
        grid = pv.read(tmp_path / "density.vti")
        expected_grid, = material.get_meshes()
        np.testing.assert_array_equal(grid.point_data["density"], expected_grid.point_data["density"])
        assert grid.dimensions == expected_grid.dimensions


def test_boundary_export_restores_all_archived_surfaces(design_archive, tmp_path):
    paths = export_design_components(
        str(design_archive.folder), 2, str(tmp_path / "surfaces"),
        [{"category": "Part", "name": "body", "mode": "all_surfaces"}],
    )
    assert {path.name for path in paths} == {"surface_0.stp", "surface_0.brep.json", "surface_1.stp"}
    assert all(BREPSurface(path).get_mesh().n_cells > 0 for path in paths if path.suffix == ".stp")


def test_boundary_export_rejects_unknown_mode_and_unsupported_surface(tmp_path):
    from morphopt import BoundaryPart

    part = BoundaryPart()
    part.add_surface_interface(part.BaseSurface())
    with pytest.raises(ValueError, match="does not support export mode"):
        part.export(tmp_path, mode="invalid")
    with pytest.raises(ValueError, match="surface_0 .* has no export format"):
        part.export(tmp_path)
    assert not list(tmp_path.iterdir())


def test_history_gif_exports_design_and_deformation_frames(deformation_archive, tmp_path):
    common = {
        "folder": str(deformation_archive.folder),
        "first_iteration": 1,
        "last_iteration": 2,
        "fps": 5,
        "camera": {
            "position": [[35, 35, 20], [0, 0, 8], [0, 0, 1]],
            "parallel_projection": True,
            "parallel_scale": 12,
        },
        "window_size": (300, 300),
        "style": {
            "background": "#101820", "text_color": "white",
            "geometry_color": "lightblue", "deformation_color": "lightblue",
            "mesh_ambient": 0.3, "mesh_diffuse": 0.7, "mesh_specular": 0.1,
            "mesh_specular_power": 10.0, "boundary_shell_opacity": 0.3,
        },
    }
    for mode, target in (
        ("design", {"category": "Part", "name": "body"}),
        ("deformation", {"case": "case"}),
    ):
        destination = tmp_path / f"{mode}.gif"
        assert export_history_gif(
            destination=str(destination), mode=mode, target=target, **common
        ) == 2
        assert len(imageio.mimread(destination)) == 2
        with Image.open(destination) as gif:
            assert gif.info["duration"] == 200


def test_failed_gif_write_closes_renderer_and_preserves_existing_file(
    deformation_archive, tmp_path, monkeypatch
):
    output = tmp_path / "history.gif"
    output.write_bytes(b"existing animation")
    closed = []
    original_close = pv.Plotter.close

    def close(plotter):
        closed.append(plotter)
        original_close(plotter)

    def fail_write(_frame):
        raise OSError("disk full")

    @contextmanager
    def writer(path, **_kwargs):
        Path(path).write_bytes(b"incomplete animation")
        yield SimpleNamespace(append_data=fail_write)

    monkeypatch.setattr(pv.Plotter, "close", close)
    monkeypatch.setattr(imageio, "get_writer", writer)
    with pytest.raises(OSError, match="disk full"):
        export_history_gif(
            folder=str(deformation_archive.folder), destination=str(output),
            mode="deformation", target={"case": "case"},
            first_iteration=1, last_iteration=1, fps=5,
            camera={"position": [[3, 3, 3], [0, 0, 0], [0, 0, 1]]},
            window_size=(100, 100),
            style={"background": "white", "text_color": "black",
                   "deformation_color": "blue", "mesh_ambient": 0.17,
                   "mesh_diffuse": 0.78, "mesh_specular": 0.24,
                   "mesh_specular_power": 30},
        )
    assert closed
    assert output.read_bytes() == b"existing animation"
    assert not list(tmp_path.glob(".*.partial.gif"))
