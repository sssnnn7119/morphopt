"""Create and run the STEP-cylinder/BSP-cavity optimization regression case."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from morphopt.ui.model.problem import ProblemDefinition


def create_case(destination: Path) -> ProblemDefinition:
    """Build a portable .morph containing an exact cylindrical BREP asset."""
    from morphopt.ui.application import ProblemLibrary
    from morphopt.ui.application.cad import convert_cad_to_boundary
    from morphopt.ui.application.quickstart import (
        QuickstartObjective, QuickstartOptions, build_quickstart,
    )
    from morphopt.ui.model.chamberlayout import ChamberLayer
    from morphopt.ui.model.node_types.parts import CADPartNode
    from morphopt.ui.model.problem import CADOperationNode

    options = QuickstartOptions(
        label="BREP_BSP_Cylinder", result_folder=".results/", radius=4.0,
        mesh_size=2.0, mu=0.3, kappa=3.0, wall=1.0, optimize_outer=False,
        layers=[ChamberLayer(
            length=16.0, chambers=1, radius=1.4, center_radius=0.0,
            arrangement="ring", shape="cylinder", pressure_channels=[1],
        )],
        objectives=[QuickstartObjective(
            kind="extend", target=0.15, pressures_kpa={1: 20.0},
        )],
    )
    problem = build_quickstart(options)
    problem.helper_variables[:] = [
        variable for variable in problem.helper_variables if variable.name != "quickstart_settings"
    ]
    cad_problem = ProblemLibrary.create_blank()
    cylinder = CADPartNode(name="outer_cylinder", mesh_size=2.0, mesh_order=1)
    cylinder.add_child(CADOperationNode.create(
        "Cylinder", operation_id="cylinder", radius=4.0, dz=16.0,
        x=0.0, y=0.0, z=0.0, dx=0.0, dy=0.0,
    ))
    cad_problem.add_part(cylinder)
    with TemporaryDirectory(prefix="morphopt_brep_case_") as directory:
        converted = convert_cad_to_boundary(cylinder, cad_problem, directory)
        outer = converted.surfaces[0]
        outer.name = "outer_cylinder"
        outer.filename = "outer-cylinder.stp"
        part = problem.parts()[0]
        part.surfaces[0] = outer
    part.mesh_order = 1
    inner = part.surfaces[1]
    inner.name = "inner_cavity"
    inner.seed_size = 2.0
    inner.degree = 2
    inner.is_updatable = True
    config = problem.updater.geometry[0]
    config["max_step_iter"] = 5
    problem.device = "cpu"
    problem.updater_device = "cpu"
    problem.solver.num_process = 1
    problem.solver.gpus = []
    destination.parent.mkdir(parents=True, exist_ok=True)
    ProblemLibrary.save(problem, destination)
    return problem


def run_case(case_path: Path, workdir: Path, iterations: int) -> dict[str, object]:
    """Run real FE solves, sensitivities and shape updates, then save a report."""
    import numpy as np
    import torch
    import morphopt
    import torchfea
    from morphopt.ui.application import ProblemLibrary

    torch.set_default_dtype(torch.float64)
    torch.set_default_device("cpu")
    torch.set_num_threads(1)
    workdir.mkdir(parents=True, exist_ok=True)
    problem = ProblemLibrary.load(case_path)
    problem.result_folder = str((workdir / "results").resolve())
    script = Path(ProblemLibrary.export_python_bundle(problem, workdir / "job")).resolve()
    spec = importlib.util.spec_from_file_location(script.stem, script)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script.parent))
    sys.modules[script.stem] = module
    spec.loader.exec_module(module)
    controller = module.ThisController()
    torchfea.enable_logging()
    morphopt.enable_logging()
    controller.initialize()
    controller.initialize_path(str(script))
    part = controller.params.geometry.interface("body")
    outer, inner = part.surface_interfaces()
    asset_digest = hashlib.sha256(outer.path_step.read_bytes()).hexdigest()
    initial = inner.control_points.detach().clone()
    records = []
    try:
        assert outer.num_variables == 0
        assert inner.num_variables > 0
        for index in range(iterations):
            controller.clear_cache()
            values = controller.step()
            controller.record_history(*values)
            controller.save()
            loss = float(values[0])
            assert np.isfinite(loss)
            assert torch.isfinite(inner.control_points).all()
            assert all(result.converged for result in controller.objfun.fe_results)
            mesh = controller.objfun.fe.assembly.get_part("body")
            for name in ("surface_0_All", "surface_1_All"):
                assert len(mesh.surfaces[name])
                assert len(mesh.set_nodes[name])
            for name in outer.face_names:
                assert name in mesh.surfaces
                assert f"{name}_nodes" in mesh.set_nodes
            assert len(mesh.set_nodes["surface_0_Bottom"])
            assert len(mesh.set_nodes["surface_0_Head"])
            points = mesh.nodes[mesh.set_nodes["surface_0_All"]]
            radial_error = (points[:, :2].norm(dim=1) - 4.0).abs()
            boundary_error = torch.minimum(
                radial_error, torch.minimum(points[:, 2].abs(), (points[:, 2] - 16.0).abs()),
            )
            assert float(boundary_error.max()) < 1e-8
            record = {
                "iteration": index, "objective": loss,
                "metrics": [float(value) for value in controller.objfun.get_metrics()],
                "nodes": int(mesh.nodes.shape[0]),
                "elements": sum(int(element._elems.shape[0]) for element in mesh.elems.values()),
            }
            records.append(record)
            print(json.dumps(record), flush=True)
        change = float(torch.linalg.vector_norm(inner.control_points - initial))
        assert change > 0.0
        assert hashlib.sha256(outer.path_step.read_bytes()).hexdigest() == asset_digest
        final_mesh = part.build_part(str(workdir / "final_mesh"), pools=controller.pools)
        report = {
            "case": case_path.name, "device": "cpu", "processes": 1,
            "iterations": records, "control_point_change_norm": change,
            "outer_step_unchanged": True, "result_directory": controller.path_result,
            "final_mesh_nodes": int(final_mesh.nodes.shape[0]),
            "final_mesh_elements": sum(int(element._elems.shape[0]) for element in final_mesh.elems.values()),
        }
        (workdir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        controller.pools.close()
        controller.pools.join()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=Path("docs/examples/brep-bsp-cylinder.morph"))
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--workdir", type=Path, default=Path(".results/brep-bsp-validation"))
    arguments = parser.parse_args()
    if arguments.iterations < 1:
        parser.error("--iterations must be positive")
    if not arguments.run or not arguments.case.is_file():
        create_case(arguments.case)
        print(f"Created {arguments.case}", flush=True)
    if arguments.run:
        print(json.dumps(run_case(arguments.case, arguments.workdir, arguments.iterations), indent=2))


if __name__ == "__main__":
    main()
