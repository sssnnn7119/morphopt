"""Real OCC regressions for BREP topology, trimming, export and FE sets."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gmsh
import numpy as np
import pytest
from scipy.integrate import quad
import torch
import torchfea
from torchfea import cad
from torchfea.cad import BREPTopology

from morphopt.shapeopt.boundary_part import BoundaryPart
from morphopt.shapeopt.surfaces.brep_surface import BREPSurface


def assert_same_geometry(before: BREPTopology, after: BREPTopology) -> None:
    assert after.faces.keys() == before.faces.keys()
    assert after.edges.keys() == before.edges.keys()
    assert after.vertices.keys() == before.vertices.keys()
    for name, face in before.faces.items():
        assert sorted(tuple(sorted(loop)) for loop in after.faces[name].loops) == sorted(
            tuple(sorted(loop)) for loop in face.loops)
    for name, edge in before.edges.items():
        np.testing.assert_allclose(after.edges[name].signature, edge.signature, rtol=1e-7, atol=1e-8)
        assert set(after.edges[name].vertices) == set(edge.vertices)
        assert set(after.edges[name].faces) == set(edge.faces)
    for name, vertex in before.vertices.items():
        np.testing.assert_allclose(after.vertices[name].coordinates, vertex.coordinates, atol=1e-8)


def sample_faces(surface: BREPSurface) -> dict[str, np.ndarray]:
    samples = {}
    with cad.occ_session("sample_source_faces") as context:
        surface._build_geometry(context)
        for name, face in surface.faces.items():
            u, v = np.meshgrid(*(np.linspace(*bounds, 9) for bounds in face.parameter_bounds))
            uv = np.column_stack((u.ravel(), v.ravel()))
            tag = surface.topology.face_tags[name]
            inside = [bool(gmsh.model.isInside(2, tag, point, parametric=True)) for point in uv]
            samples[name] = np.asarray(gmsh.model.getValue(2, tag, uv[inside].ravel())).reshape(-1, 3)
    return samples


def assert_samples_on_faces(surface: BREPSurface, samples: dict[str, np.ndarray]) -> None:
    with cad.occ_session("check_converted_faces") as context:
        surface._build_geometry(context)
        for name, points in samples.items():
            tag = surface.topology.face_tags[name]
            projected, _ = gmsh.model.getClosestPoint(2, tag, points.ravel())
            np.testing.assert_allclose(np.asarray(projected).reshape(-1, 3), points, atol=1e-7)


def test_topology_without_meshing_and_adjacency(
    step_factory: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    surface = BREPSurface(step_factory("box"))
    def no_mesh(*args: object, **kwargs: object) -> None:
        pytest.fail("Topology inspection must not generate a mesh")
    monkeypatch.setattr(gmsh.model.mesh, "generate", no_mesh)
    topology = surface.topology
    assert (len(topology.faces), len(topology.edges), len(topology.vertices)) == (6, 12, 8)
    assert all(len(face.loops) == 1 and len(face.loops[0]) == 4 for face in surface.faces.values())
    assert all(len(edge.faces) == 2 and len(edge.vertices) == 2 for edge in surface.edges.values())
    assert all(len(vertex.edges) == 3 for vertex in surface.vertices.values())
    assert not surface.is_updatable
    assert surface.num_variables == 0
    assert not gmsh.isInitialized()


@pytest.mark.parametrize("kind", ["box", "triangle", "hole", "cylinder"])
def test_selected_nurbs_conversion_export_and_reload(
    kind: str, step_factory: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    surface = BREPSurface(step_factory(kind))
    before = surface.topology
    samples = sample_faces(surface)
    if kind == "triangle":
        selected = next(name for name, face in surface.faces.items() if len(face.loops[0]) == 3)
    elif kind == "hole":
        selected = next(name for name, face in surface.faces.items() if len(face.loops) == 2)
    elif kind == "cylinder":
        selected = next(name for name, face in surface.faces.items() if face.geometry_type == "Cylinder")
    else:
        selected = next(iter(surface.faces))
    edge = surface.faces[selected].loops[0][0]
    vertex = surface.edges[edge].vertices[0]
    surface.add_surface_set("loaded", selected)
    surface.add_node_set("rim", [edge, vertex])
    def no_mesh(*args: object, **kwargs: object) -> None:
        pytest.fail("Conversion and STEP export must not generate a mesh")
    monkeypatch.setattr(gmsh.model.mesh, "generate", no_mesh)
    assert surface.convert_faces_to_nurbs(selected) is surface
    assert surface.faces[selected].is_nurbs
    assert_same_geometry(before, surface.topology)
    assert_samples_on_faces(surface, samples)
    for name in before.faces.keys() - {selected}:
        assert surface.faces[name].geometry_type == before.faces[name].geometry_type
    surface.convert_faces_to_nurbs(selected)
    assert_same_geometry(before, surface.topology)
    output = surface.export_step(tmp_path / "export" / f"{kind}.stp")
    assert "ISO-10303-21;" in output.read_text()
    assert output.with_suffix(".faces.json").is_file()
    assert output.with_suffix(".brep.json").is_file()
    restored = BREPSurface(output)
    assert restored.faces[selected].is_nurbs
    assert_same_geometry(before, restored.topology)
    assert_samples_on_faces(restored, samples)
    assert restored.surface_sets == {"loaded": (selected,)}
    assert restored.node_sets == {"rim": (edge, vertex)}
    # Check the actual STEP, independently of sidecars or replayed conversion.
    with cad.occ_session("check_exported_solid") as context:
        entities = context.occ.importShapes(str(output))
        context.occ.synchronize()
        volumes = [tag for dim, tag in entities if dim == 3]
        assert len(volumes) == 1
        expected = {"box": 72, "triangle": 36, "hole": 72 - np.pi * 0.6**2 * 3,
                    "cylinder": np.pi * 2**2 * 5}[kind]
        if kind == "cylinder":
            # OCC's default nonadaptive mass quadrature is inaccurate for a
            # rational cylinder. Integrate radial flux independently instead.
            tag = next(tag for _, tag in gmsh.model.getEntities(2)
                       if "bspline" in gmsh.model.getType(2, tag).casefold())
            lower, upper = gmsh.model.getParametrizationBounds(2, tag)
            def radial_flux(u: float) -> float:
                uv = [u, (lower[1] + upper[1]) / 2]
                xyz = np.asarray(gmsh.model.getValue(2, tag, uv))
                du, dv = np.asarray(gmsh.model.getDerivative(2, tag, uv)).reshape(2, 3)
                return float(xyz[:2] @ np.cross(du, dv)[:2] / 2)
            # The axial direction is linear; adapt across rational knot spans.
            integral, _ = quad(radial_flux, lower[0], upper[0], epsabs=1e-10, epsrel=1e-10, limit=200)
            volume = abs(integral * (upper[1] - lower[1]))
            assert volume == pytest.approx(expected, rel=1e-9)
            uv = np.column_stack((np.linspace(lower[0], upper[0], 101), np.full(101, lower[1])))
            xyz = np.asarray(gmsh.model.getValue(2, tag, uv.ravel())).reshape(-1, 3)
            np.testing.assert_allclose(np.linalg.norm(xyz[:, :2], axis=1), 2, atol=1e-9)
        else:
            assert context.occ.getMass(3, volumes[0]) == pytest.approx(expected, rel=1e-7)
        assert sum("bspline" in gmsh.model.getType(2, tag).casefold()
                   for _, tag in gmsh.model.getEntities(2)) == 1
    assert not gmsh.isInitialized()


@pytest.mark.parametrize("kind", ["triangle", "hole"])
def test_nurbs_trim_classification_and_edge_parameterization(
    kind: str, step_factory: Callable[[str], Path],
) -> None:
    surface = BREPSurface(step_factory(kind))
    face_name = next(name for name, face in surface.faces.items()
                     if (len(face.loops) == 2 if kind == "hole" else len(face.loops[0]) == 3))
    surface.convert_faces_to_nurbs(face_name)
    # Obtain UV coordinates from world points, so no support-plane orientation
    # or OCC parameterization convention is assumed by this regression.
    with cad.occ_session("test_trim_uv") as context:
        surface._build_geometry(context)
        tag = surface.topology.face_tags[face_name]
        z = surface.faces[face_name].signature[3]
        world = [[0.5, 0.5, z], [5.5, 3.5, z]] if kind == "triangle" else [[0.5, 0.5, z], [2, 2, z]]
        uv = np.asarray(gmsh.model.getParametrization(2, tag, np.ravel(world))).reshape(-1, 2)
    np.testing.assert_array_equal(surface.contains_face_parameters(face_name, uv), [True, False])
    np.testing.assert_allclose(surface.evaluate_face(face_name, uv), world, atol=1e-7)
    for edge_name in surface.faces[face_name].loops[0]:
        edge = surface.edges[edge_name]
        parameters = np.linspace(*edge.parameter_bounds, 5)
        edge_uv = surface.edge_parameters_on_face(face_name, edge_name, parameters)
        np.testing.assert_allclose(surface.evaluate_face(face_name, edge_uv),
                                   surface.evaluate_edge(edge_name, parameters), atol=1e-7)


def test_invalid_selections_leave_geometry_and_session_intact(step_factory: Callable[[str], Path]) -> None:
    surface = BREPSurface(step_factory("box"))
    before = surface.topology
    with pytest.raises(ValueError, match="Unknown faces"):
        surface.convert_faces_to_nurbs("face_1000")
    for name, members in (("All", "face_0"), ("loaded", "face_1000"), ("loaded", [])):
        with pytest.raises(ValueError):
            surface.add_surface_set(name, members)
    for name, members in (("edge_0", "vertex_0"), ("rim", "edge_1000"), ("rim", [])):
        with pytest.raises(ValueError):
            surface.add_node_set(name, members)
    assert surface.topology is before
    assert not gmsh.isInitialized()


def test_convert_multiple_faces_preserves_source_asset(
    step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    path = step_factory("box")
    original = path.read_bytes()
    surface = BREPSurface(path)
    before = surface.topology
    surface.convert_faces_to_nurbs(tuple(surface.faces))
    assert all(face.is_nurbs for face in surface.faces.values())
    assert_same_geometry(before, surface.topology)
    restored = BREPSurface(surface.export_step(tmp_path / "all_nurbs.step"))
    assert all(face.is_nurbs for face in restored.faces.values())
    assert_same_geometry(before, restored.topology)
    assert path.read_bytes() == original


@pytest.mark.parametrize("kind", ["triangle", "hole", "cylinder"])
def test_converted_preview_retains_face_ids_and_closed_surface(
    kind: str, step_factory: Callable[[str], Path],
) -> None:
    surface = BREPSurface(step_factory(kind))
    selected = next(name for name, face in surface.faces.items()
                    if (face.geometry_type == "Cylinder" if kind == "cylinder"
                        else len(face.loops) == 2 if kind == "hole" else len(face.loops[0]) == 3))
    surface.convert_faces_to_nurbs(selected)
    mesh = surface.get_mesh()
    assert mesh.n_cells > 0
    assert np.isfinite(mesh.points).all()
    assert set(mesh.cell_data["face_index"]) == {int(name[5:]) for name in surface.faces}
    assert mesh.clean().n_open_edges == 0
    assert not gmsh.isInitialized()


def test_occ_session_preserves_active_model_and_finalizes_on_error() -> None:
    with cad.occ_session("outer"):
        with pytest.raises(RuntimeError, match="active Gmsh model"):
            with cad.occ_session("nested"):
                pytest.fail("Nested session should be rejected")
        assert gmsh.isInitialized()
        assert gmsh.model.getCurrent() == "outer"
    with pytest.raises(ValueError, match="abort"):
        with cad.occ_session("failure"):
            raise ValueError("abort")
    assert not gmsh.isInitialized()


def test_open_step_rejected_and_session_released(tmp_path: Path) -> None:
    path = tmp_path / "open.step"
    with cad.occ_session("open_surface") as context:
        context.occ.addRectangle(0, 0, 0, 2, 3)
        context.occ.synchronize()
        gmsh.write(str(path))
    with pytest.raises(ValueError, match="one closed shell"):
        BREPSurface(path).topology
    assert not gmsh.isInitialized()


@pytest.mark.parametrize("order", [1, 2])
def test_converted_boundary_mesh_maps_face_edge_vertex_and_union_sets(
    order: int, step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    surface = BREPSurface(step_factory("box"))
    selected = tuple(surface.faces)[:2]
    edge_name = surface.faces[selected[0]].loops[0][0]
    vertex_name = surface.edges[edge_name].vertices[0]
    surface.add_surface_set("loaded", selected)
    surface.add_node_set("rim", [edge_name, vertex_name])
    surface.convert_faces_to_nurbs(selected[0])
    part = BoundaryPart(fea_seed_size=1.5, mesh_order=order, part_name="body")
    part.add_surface_interface(surface)
    part.initialize()
    mesh = part.build_part(str(tmp_path))
    assert len(mesh.elems["C3D4"]._elems) > 0
    assert mesh.elems["C3D4"]._elems.shape[1] == (4 if order == 1 else 10)
    face_nodes = []
    for name in selected:
        np.testing.assert_array_equal(mesh.set_nodes[f"surface_0_{name}_nodes"], mesh.set_nodes[f"{name}_nodes"])
        face_nodes.append(mesh.set_nodes[f"{name}_nodes"])
    np.testing.assert_array_equal(mesh.set_nodes["surface_0_loaded_nodes"], np.unique(np.concatenate(face_nodes)))
    edge_nodes = mesh.set_nodes[f"surface_0_{edge_name}"]
    vertex_nodes = mesh.set_nodes[f"surface_0_{vertex_name}"]
    assert len(edge_nodes) >= 2
    assert len(vertex_nodes) == 1
    assert set(vertex_nodes) <= set(edge_nodes) <= set(face_nodes[0])
    np.testing.assert_array_equal(mesh.set_nodes["surface_0_rim"], np.union1d(edge_nodes, vertex_nodes))
    coordinates = mesh.nodes[edge_nodes].detach().cpu().numpy()
    endpoints = np.array([surface.vertices[name].coordinates for name in surface.edges[edge_name].vertices])
    direction = endpoints[1] - endpoints[0]
    np.testing.assert_allclose(np.cross(coordinates - endpoints[0], direction), 0, atol=1e-7)
    assert "surface_0_Head" not in mesh.set_nodes
    assert "surface_0_Bottom" not in mesh.set_nodes
    assert not gmsh.isInitialized()


@pytest.mark.parametrize("order", [1, 2])
def test_named_brep_sets_support_actual_pressure_solve(
    order: int, step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    previous_dtype = torch.get_default_dtype()
    torch.set_default_dtype(torch.float64)
    try:
        surface = BREPSurface(step_factory("box"))
        fixed = next(name for name, face in surface.faces.items() if face.signature[1] == 0)
        loaded = next(name for name, face in surface.faces.items() if face.signature[1] == 6)
        surface.add_node_set("fixed", fixed)
        surface.add_surface_set("loaded", loaded)
        surface.convert_faces_to_nurbs([fixed, loaded])
        boundary = BoundaryPart(fea_seed_size=2.0, mesh_order=order, part_name="body")
        boundary.add_surface_interface(surface)
        boundary.initialize()
        mesh = boundary.build_part(str(tmp_path))
        mesh.elems["C3D4"].set_materials(torchfea.materials.NeoHookean(mu=1.0, kappa=10.0))
        controller = torchfea.FEAController()
        controller.assembly = torchfea.Assembly()
        controller.assembly.add_part(mesh, "body")
        controller.assembly.add_instance(torchfea.Instance("body"), "body-1")
        controller.assembly.add_boundary(
            torchfea.boundarys.Boundary_Condition("body-1", "surface_0_fixed"), "fixed")
        controller.assembly.add_load(torchfea.loads.Pressure("body-1", "surface_0_loaded", 0.001), "pressure")
        controller.solver = torchfea.solver.StaticImplicitSolver(tol_error=1e-8)
        result = controller.solve()
        assert result.converged
        assert torch.isfinite(result.GC).all()
        assert float(result.GC.abs().max()) > 1e-5
    finally:
        torch.set_default_dtype(previous_dtype)
