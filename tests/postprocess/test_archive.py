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


def test_native_fea_archive_has_no_history_views(iteration_model, tmp_path):
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
    assert IterationModel(str(archive.folder), 3).cases() == ("loaded",)
    assert archive.deformation_cases(3) == ()
    assert archive.deformation_mesh("loaded", 3) is None
    assert archive.visualizable_components(3) == ()
    assert not archive._controller_loaded


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


def test_vtk_snapshot_is_independent_of_task_and_checkpoints(design_archive, iteration_model, tmp_path):
    import numpy as np
    import torch
    from morphopt.postprocess import cpu_torch_defaults, design_view_options
    from morphopt.postprocess.snapshots import capture_design, save_snapshot

    archive = OptimizationArchive(tmp_path / "portable")
    _, controller, solution = iteration_model
    params = design_archive.params
    with cpu_torch_defaults(), torch.no_grad():
        part = params.geometry.interfaces["body"]
        surface = part.surfaceinterfaces[1]
        original = surface.control_points.cpu().numpy().copy()
        scene = capture_design(params)
        surface.update_variables(torch.full_like(surface.control_points, 0.4))
        save_snapshot(archive.log_folder, 1, scene,
                      SimpleNamespace(fe=controller, fe_results={"load": solution}))
        expected_mesh, = controller.assembly.get_meshes(GC=solution.GC).values()
    (category, component), = archive.visualizable_components(1)
    assert (category, component.name) == ("Part", "body")
    assert "surface:1:control-net" in [v.key for v in design_view_options(component)]
    np.testing.assert_allclose(component.mesh("net_1").points, original)
    assert component.mesh("surface_0").n_cells > 0
    assert archive.deformation_cases(1) == ("load",)
    mesh = archive.deformation_mesh("load", 1)
    assert mesh.point_data["U"].shape == mesh.points.shape
    np.testing.assert_allclose(sorted(map(tuple, mesh.points)),
                               sorted(map(tuple, expected_mesh.clean().points)))
    assert not archive._controller_loaded


def test_simp_snapshot_preserves_density_grid(iteration_model, tmp_path):
    import shutil
    import numpy as np
    import torch
    from morphopt.postprocess import cpu_torch_defaults
    from morphopt.postprocess.snapshots import capture_design, save_snapshot

    archive = OptimizationArchive(tmp_path / "material")
    scripts = archive.folder / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[2] / "examples/simp_gripper/simp_gripper.py",
                    scripts / "MAIN_SCRIPT_FOR_RESTART.py")
    _, controller, solution = iteration_model
    with cpu_torch_defaults(), torch.no_grad():
        params = archive.initialize_params()
        expected, = params.materials.interface("body").get_meshes()
        scene = capture_design(params)
        save_snapshot(archive.log_folder, 1, scene,
                      SimpleNamespace(fe=controller, fe_results={"load": solution}))
    grid = archive.design_view_component("Material", "body", 1).mesh("mesh_0")
    assert isinstance(grid, pv.ImageData)
    np.testing.assert_array_equal(grid["density"], expected["density"])
    np.testing.assert_array_equal(grid.field_data["density_max"], expected.field_data["density_max"])


def test_snapshot_of_custom_plot_only_component():
    from morphopt.optcore.protocal import ProtocalVisualizable
    from morphopt.postprocess.snapshots import capture_design

    class CustomComponent(ProtocalVisualizable):
        name = "probe"

        def plot(self, plotter=None, meshes=None):
            plotter.add_mesh(pv.Line())
            return plotter

    empty = SimpleNamespace(design_interfaces=lambda: [])
    params = SimpleNamespace(geometry=empty, materials=empty,
                             feamodel=SimpleNamespace(design_interfaces=lambda: [CustomComponent()]))
    mesh = capture_design(params)["FEA"]["probe"]["CustomComponent"]["mesh_0"]
    assert mesh.n_lines == 1


def test_shared_exteriors_follow_instance_activation_and_node_order(tmp_path):
    import numpy as np
    import torch
    from morphopt.postprocess.snapshots import Snapshot, save_snapshot

    # Node 0 is internal, so compact surface indices differ from FE node indices.
    points = np.array([[0.25, 0.25, 0], [1., 0., 0.], [0., 1., 0.], [0., 0., 0.]])
    faces = [3, 3, 1, 2]
    instances = {
        name: SimpleNamespace(
            enabled=True, _RGC_index=slice(12*i, 12*i+12),
            get_mesh=lambda i=i: pv.PolyData(points + [3*i, 0, 0], faces),
        ) for i, name in enumerate(("left", "right"))
    }

    def activate(names):
        for name, instance in instances.items():
            instance.enabled = name in names

    assembly = SimpleNamespace(_instances=instances, get_work_conditions=lambda: ("left", "right"),
                               set_work_conditions=activate)
    fe = SimpleNamespace(assembly=assembly, GC2RGC=lambda gc: gc)
    cases = {"right_only": ("right",), "both": ("left", "right"), "left_only": ("left",)}
    results = {case: SimpleNamespace(work_conditions=names, GC=torch.arange(24).double() * i)
               for i, (case, names) in enumerate(cases.items(), 1)}
    save_snapshot(tmp_path, 1, pv.MultiBlock(), SimpleNamespace(fe=fe, fe_results=results))
    path = tmp_path / "views" / "iteration_000001.vtm"
    assert all(instance.enabled for instance in instances.values())
    stored = pv.read(path)["Displacement"]
    assert len(list(path.with_suffix("").glob("*.vtp"))) == len(instances)
    assert set(stored["left"].point_data) == {"U_both", "U_left_only"}
    assert set(stored["right"].point_data) == {"U_right_only", "U_both"}
    snapshot = Snapshot(path)
    assert snapshot.cases == tuple(cases)
    for case, names in cases.items():
        mesh = snapshot.deformation_mesh(case)
        assert mesh.n_cells == len(names)
        assert set(mesh.point_data) == {"U"}
        expected = []
        for name in names:
            instance = instances[name]
            u = results[case].GC[instance._RGC_index].reshape(-1, 3).numpy()
            expected.extend((instance.get_mesh().points + u)[1:])
        np.testing.assert_array_equal(sorted(map(tuple, mesh.points)), sorted(map(tuple, expected)))
    assert snapshot.deformation_mesh("missing") is None
