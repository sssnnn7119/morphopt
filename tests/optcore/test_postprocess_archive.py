"""Regression checks for optimization archive state restoration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import imageio.v2 as imageio
import pyvista as pv
import pytest
import torch
from PIL import Image

from morphopt.optcore.history import History
from morphopt.postprocess import (
    IterationModel,
    OptimizationArchive,
    cpu_torch_defaults,
    export_boundary_surfaces,
    export_history_gif,
)
from morphopt.shapeopt.surfaces.brep_surface import BREPSurface


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


@pytest.fixture
def design_archive(tmp_path):
    example = Path(__file__).resolve().parents[2] / "examples" / "hybrid_cylinder"
    folder = tmp_path / "run"
    scripts = folder / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(example / "hybrid_cylinder.py", scripts / "MAIN_SCRIPT_FOR_RESTART.py")
    shutil.copytree(example / "assets", scripts / "assets")
    archive = OptimizationArchive(folder)
    params = archive.initialize_params()
    part = params.geometry.interfaces["body"]
    archive.log_folder.mkdir()
    with cpu_torch_defaults():
        part.save(foldpath=str(archive.log_folder), iteration=1)
        inner = part.surface_interfaces()[1]
        inner.update_variables(torch.full_like(inner.control_points, 0.2))
        part.save(foldpath=str(archive.log_folder), iteration=2)
    history = History()
    history.append("objective", 1.0)
    history.append("objective", 0.9)
    history.save(foldpath=str(archive.log_folder))
    return archive


def test_boundary_export_restores_archived_step_and_stl_surfaces(design_archive, tmp_path):
    paths = export_boundary_surfaces(
        str(design_archive.folder), 2, str(tmp_path / "surfaces"),
        [{"part": "body", "index": index, "format": "stp"} for index in (0, 1)],
    )
    step_files = [path for path in paths if path.suffix == ".stp"]
    assert {path.name for path in step_files} == {"surface_0.stp", "surface_1.stp"}
    assert all(BREPSurface(path).get_mesh().n_cells > 0 for path in step_files)
    stl_files = export_boundary_surfaces(
        str(design_archive.folder), 2, str(tmp_path / "surfaces"),
        [{"part": "body", "index": index, "format": "stl"} for index in (0, 1)],
    )
    assert {path.name for path in stl_files} == {"surface_0.stl", "surface_1.stl"}
    assert all(pv.read(path).n_cells > 0 for path in stl_files)


def test_history_gif_exports_design_and_deformation_frames(design_archive, tmp_path):
    deformation = design_archive.log_folder / "deformation"
    deformation.mkdir()
    for iteration, radius in ((1, 3.0), (2, 4.0)):
        pv.Cylinder(center=(0, 0, 8), direction=(0, 0, 1), radius=radius, height=16).triangulate().save(
            deformation / f"task_case_iter_{iteration}.stl"
        )
    common = {
        "folder": str(design_archive.folder),
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
