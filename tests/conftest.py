"""CAD assets and a saved finite-element solution shared by regressions."""

from collections.abc import Callable
import json
from pathlib import Path
import shutil

import gmsh
import pytest
import torchfea
from torchfea import cad


@pytest.fixture
def step_factory(tmp_path: Path) -> Callable[[str], Path]:
    def create(kind: str) -> Path:
        path = tmp_path / f"{kind}.step"
        with cad.occ_session(f"test_{kind}") as context:
            if kind == "box":
                context.occ.addBox(0, 0, 0, 6, 4, 3)
            elif kind == "cylinder":
                context.occ.addCylinder(0, 0, 0, 0, 0, 5, 2)
            elif kind == "hole":
                box = context.occ.addBox(0, 0, 0, 6, 4, 3)
                hole = context.occ.addCylinder(2, 2, -1, 0, 0, 5, 0.6)
                context.occ.cut([(3, box)], [(3, hole)])
            elif kind == "triangle":
                points = [context.occ.addPoint(*xyz) for xyz in
                          ((0, 0, 0), (6, 0, 0), (0, 4, 0))]
                lines = [context.occ.addLine(points[i], points[(i + 1) % 3]) for i in range(3)]
                wire = context.occ.addCurveLoop(lines)
                face = context.occ.addPlaneSurface([wire])
                context.occ.extrude([(2, face)], 0, 0, 3)
            else:
                raise ValueError(kind)
            context.occ.synchronize()
            gmsh.write(str(path))
        return path
    return create


@pytest.fixture
def iteration_model(tmp_path):
    from morphopt import BoxPart
    from morphopt.postprocess import IterationModel, cpu_torch_defaults

    folder = tmp_path / "optimization"
    saved = folder / "log" / "femodel&results"
    saved.mkdir(parents=True)
    with cpu_torch_defaults():
        part = BoxPart(
            length=1, height=1, depth=1, mesh_size=1, mesh_order=1
        ).build_part()
        part.elems["C3D8"].set_materials(
            torchfea.materials.NeoHookean(mu=1.0, kappa=10.0)
        )
        controller = torchfea.FEAController()
        controller.assembly = torchfea.Assembly()
        controller.assembly.add_part(part, "body")
        controller.assembly.add_instance(torchfea.Instance("body"), "body-1")
        controller.assembly.add_boundary(
            torchfea.boundarys.Boundary_Condition("body-1", "nodes_xmin"), "fixed"
        )
        controller.assembly.add_load(
            torchfea.loads.BodyForce("body-1", "C3D8", [0.002, 0.0, 0.0]),
            "body_force",
        )
        controller.solver = torchfea.solver.StaticImplicitSolver(tol_error=1e-8)
        controller.initialize()
        result = controller.solve(if_initialize=False)
        assert result.converged
        controller.save_model(str(saved / "femodel_3.npz"), if_save_source_code=False)
        result.save(str(saved / "result_0_iter_3.npz"))
    (saved / "load_cases.json").write_text(json.dumps(["0", "7"]), encoding="utf-8")
    return IterationModel(str(folder), 3, "0"), controller, result


@pytest.fixture
def design_archive(tmp_path):
    from morphopt.optcore.history import History
    from morphopt.postprocess import OptimizationArchive, cpu_torch_defaults
    import torch

    example = Path(__file__).resolve().parents[1] / "examples" / "hybrid_cylinder"
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
