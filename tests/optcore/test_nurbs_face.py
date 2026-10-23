"""NURBS basis, FE-node parameters and control-point gradient regressions."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import torch

from morphopt.shapeopt.boundary_part import BoundaryPart
from morphopt.shapeopt.surfaces.brep_surface import BREPSurface
from morphopt.shapeopt.surfaces.nurbs_face import NURBSFace


def most_influential_pole(model: NURBSFace) -> int:
    weights, indices = model.get_weights(model.surf_node_uv)
    influence = np.bincount(indices.ravel(), weights=np.abs(weights).ravel(),
                            minlength=model.control_points.shape[0])
    return int(np.argmax(np.where(model.design_mask, influence, -1)))


@pytest.fixture
def quarter_cylinder() -> NURBSFace:
    poles = np.array([[[1, 0, 0], [1, 0, 3]],
                      [[1, 1, 0], [1, 1, 3]],
                      [[0, 1, 0], [0, 1, 3]]], dtype=float)
    weights = np.repeat([[1], [np.sqrt(0.5)], [1]], 2, axis=1)
    return NURBSFace(poles, weights, (2, 1),
                     (np.array([-2, -2, -2, 5, 5, 5]), np.array([10, 10, 14, 14])))


def test_rational_basis_native_domain_endpoints_and_derivatives(quarter_cylinder: NURBSFace) -> None:
    model = quarter_cylinder
    uv = torch.tensor([[-2, 10], [5, 14], [0.3, 11.5], [2.7, 13]], dtype=torch.float64)
    xyz = model.map(uv).detach().numpy()
    np.testing.assert_allclose(np.linalg.norm(xyz[:, :2], axis=1), 1, atol=1e-12)
    np.testing.assert_allclose(xyz[:, 2], (uv[:, 1].numpy() - 10) * 3 / 4, atol=1e-12)
    np.testing.assert_allclose(xyz[:2], [[1, 0, 0], [0, 1, 3]], atol=1e-12)
    weights, _ = model.get_weights(uv.numpy())
    np.testing.assert_allclose(weights.sum(axis=1), 1, atol=1e-12)
    points = uv[2:]
    h = 1e-4
    for axis, order, second in ((0, (1, 0), (2, 0)), (1, (0, 1), (0, 2))):
        delta = torch.zeros_like(points)
        delta[:, axis] = h
        plus, minus, center = model.map(points + delta), model.map(points - delta), model.map(points)
        torch.testing.assert_close(model.map(points, order), (plus - minus) / (2 * h), atol=1e-8, rtol=1e-6)
        torch.testing.assert_close(model.map(points, second), (plus - 2 * center + minus) / h**2, atol=1e-7, rtol=1e-5)
    du, dv = torch.tensor([h, 0]), torch.tensor([0, h])
    mixed = (model.map(points + du + dv) - model.map(points + du - dv)
             - model.map(points - du + dv) + model.map(points - du - dv)) / (4 * h**2)
    torch.testing.assert_close(model.map(points, (1, 1)), mixed, atol=1e-7, rtol=1e-5)


def test_control_point_autograd_matches_finite_difference(quarter_cylinder: NURBSFace) -> None:
    model = quarter_cylinder
    uv = torch.tensor([[-1.7, 10.5], [0.4, 12.8], [4.2, 13.3]], dtype=torch.float64)
    original = model.get_surface_parameters().detach().clone()
    def evaluate(parameters: torch.Tensor) -> torch.Tensor:
        model.set_surface_parameters(parameters)
        return model.map(uv)
    try:
        assert torch.autograd.gradcheck(evaluate, (original.requires_grad_(),), eps=1e-6, atol=1e-7, rtol=1e-5)
    finally:
        model.set_surface_parameters(original.detach())


def test_batched_kdtree_newton_matching_and_empty_input(quarter_cylinder: NURBSFace) -> None:
    model = quarter_cylinder
    uv = np.column_stack((np.linspace(-2, 5, 19), np.linspace(14, 10, 19)))
    points = model.map(torch.from_numpy(uv)).detach().numpy()
    ids = np.arange(19, dtype=np.int64) * 7 + 5
    matched = model.match_coordinates(ids, points, batch_size=4)
    np.testing.assert_allclose(matched, points, atol=1e-8)
    np.testing.assert_allclose(model.surf_node_uv, uv, atol=1e-7)
    np.testing.assert_array_equal(model.surf_node_idx, ids)
    assert model.projection_errors.max() < 1e-8
    assert model.match_coordinates(np.empty(0, dtype=int), np.empty((0, 3))).shape == (0, 3)
    assert model.map_bound_nodes().shape == (0, 3)
    assert model.map(torch.empty((0, 2), dtype=torch.float64)).shape == (0, 3)


@pytest.mark.parametrize("kind", ["box", "triangle", "hole", "cylinder"])
@pytest.mark.parametrize("order", [1, 2])
def test_final_mesh_nodes_bind_to_trimmed_nurbs_and_have_gradients(
    kind: str, order: int, step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    brep = BREPSurface(step_factory(kind), control_point_spacing=0.7)
    if kind == "box":
        chosen = list(brep.faces)[:2]
    elif kind == "hole":
        chosen = [name for name, face in brep.faces.items() if len(face.loops) == 2]
    elif kind == "triangle":
        chosen = [name for name, face in brep.faces.items() if len(face.loops[0]) == 3]
    else:
        chosen = [name for name, face in brep.faces.items() if face.geometry_type == "Cylinder"]
    brep.convert_faces_to_nurbs(chosen)
    boundary = BoundaryPart(fea_seed_size=1.2, mesh_order=order, part_name="body")
    boundary.add_surface_interface(brep)
    boundary.initialize()
    mesh = boundary.build_part(str(tmp_path))
    assert set(brep.nurbs_faces) == set(chosen)
    node_positions = {}
    for name, model in brep.nurbs_faces.items():
        indices = mesh.set_nodes[f"surface_0_{name}_nodes"]
        np.testing.assert_array_equal(model.surf_node_idx, indices)
        assert model.surf_node_uv.shape == (len(indices), 2)
        # The basis reproduces the exact OCC support in the original UV domain.
        reference = brep.evaluate_face(name, model.surf_node_uv)
        xyz = brep.map_face_nodes(name)
        np.testing.assert_allclose(xyz.detach().numpy(), reference, atol=1e-7)
        np.testing.assert_allclose(mesh.nodes[indices].cpu().numpy(), reference, atol=5e-7)
        assert brep.contains_face_parameters(name, model.surf_node_uv).all()
        if order == 2:
            corner_nodes = np.unique(mesh.elems["C3D4"]._elems[:, :4].cpu().numpy())
            assert len(indices) > len(np.intersect1d(indices, corner_nodes))
        parameters = model.get_surface_parameters().detach().clone().requires_grad_()
        model.set_surface_parameters(parameters)
        loss = brep.map_face_nodes(name).square().sum()
        gradient, = torch.autograd.grad(loss, parameters)
        assert torch.isfinite(gradient).all()
        assert float(gradient.abs().max()) > 0
        # Transfer the coordinate graph into an actual tetrahedral mesh and
        # compare a mesh-volume derivative with a control-point perturbation.
        base_nodes = mesh.nodes.detach().to(dtype=parameters.dtype, device=parameters.device)
        node_ids = torch.as_tensor(indices, device=parameters.device)
        elements = mesh.elems["C3D4"]._elems[:, :4].to(device=parameters.device)
        def volume(values: torch.Tensor) -> torch.Tensor:
            model.set_surface_parameters(values)
            nodes = base_nodes.index_copy(0, node_ids, brep.map_face_nodes(name))
            tetrahedra = nodes[elements]
            edges = tetrahedra[:, 1:] - tetrahedra[:, :1]
            return torch.linalg.det(edges).abs().sum() / 6
        volume_gradient, = torch.autograd.grad(volume(parameters), parameters)
        component = int(volume_gradient.abs().argmax())
        change = torch.zeros_like(parameters)
        change[component] = 1e-6
        finite_difference = (volume(parameters.detach() + change) - volume(parameters.detach() - change)) / 2e-6
        torch.testing.assert_close(volume_gradient[component], finite_difference, atol=1e-6, rtol=1e-5)
        # Every adjacent face stores its own UV for the same shared node.
        for index, point in zip(indices, reference, strict=True):
            if int(index) in node_positions:
                np.testing.assert_allclose(node_positions[int(index)], point, atol=1e-7)
            node_positions[int(index)] = point
        model.set_surface_parameters(parameters.detach())
    assert brep.num_variables == 0  # Binding alone does not enable shape updates.


@pytest.mark.parametrize("kind", ["box", "hole", "cylinder"])
@pytest.mark.parametrize("order", [1, 2])
def test_brep_poles_write_step_and_remesh_next_iteration(
    kind: str, order: int, step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    brep = BREPSurface(step_factory(kind), control_point_spacing=0.7)
    if kind == "cylinder":
        name = next(name for name, face in brep.faces.items() if face.geometry_type == "Cylinder")
    elif kind == "hole":
        name = next(name for name, face in brep.faces.items() if len(face.loops) == 2)
    else:
        name = next(name for name, face in brep.faces.items() if abs(face.signature[3] - 3) < 1e-7)
    brep.convert_faces_to_nurbs(name)
    brep.select_design_faces(name)
    brep.is_updatable = True
    body = BoundaryPart(fea_seed_size=1.2, mesh_order=order, part_name="body")
    body.add_surface_interface(brep)
    body.initialize()
    initial_mesh = body.build_part(str(tmp_path))
    model = brep.nurbs_faces[name]
    assert model.design_mask is not None and model.design_mask.any()
    assert brep.num_variables == model.control_points.numel()
    assert body.obtain_design_sensitivity_vars(None).numel() == brep.num_variables
    points, tangents, curvatures = brep.get_geometry_values()
    weights = brep.get_points_weight()
    assert points.shape == (len(model.surf_node_idx), 3)
    assert tangents.shape == (len(points), 3, 2)
    assert curvatures.shape == (len(points), 3, 2, 2)
    assert weights.shape == (len(points),)
    assert weights.sum() > 0
    old = brep.get_surface_parameters().detach().clone()
    def transformed_loss(parameters: torch.Tensor) -> torch.Tensor:
        brep.set_surface_parameters(parameters)
        r, du, d2 = brep.get_geometry_values()
        return r.square().sum() + du.square().sum() + d2.square().sum()
    transformed_gradient = torch.func.grad(transformed_loss)(old)
    assert torch.isfinite(transformed_gradient).all()
    assert transformed_gradient.abs().max() > 0
    brep.set_surface_parameters(old)
    free = most_influential_pole(model)
    component = free * 3 + (0 if kind == "cylinder" else 2)
    change = torch.zeros_like(old)
    change[component] = 0.05
    brep.update_variables(change)
    torch.testing.assert_close(brep.get_surface_parameters()[component], old[component] + 0.05)
    fixed = int(np.flatnonzero(~model.design_mask)[0])
    assert brep.get_surface_parameters()[fixed * 3].item() == old[fixed * 3].item()

    destination = tmp_path / "updated.stp"
    brep.export_step(destination)
    restored = BREPSurface(destination)
    assert set(restored.faces) == set(brep.faces)
    uv = model.parameter_bounds.mean(axis=1)[None, :]
    # The exported support and the live differentiable map use the same poles.
    np.testing.assert_allclose(restored.evaluate_face(name, uv),
                               model.map(torch.from_numpy(uv)).detach().numpy(), atol=1e-7)
    if kind == "box" and order == 1:
        preview = brep.get_mesh()
        assert preview.points[:, 2].max() > 3
    next_mesh = body.build_part(str(tmp_path))
    assert len(next_mesh.nodes) > 0
    assert not torch.allclose(initial_mesh.nodes.mean(axis=0), next_mesh.nodes.mean(axis=0), atol=1e-5)

    class Assembly:
        def get_part(self, name: str):
            assert name == "body"
            return next_mesh

    parameters = brep.get_surface_parameters().detach().clone().requires_grad_()
    body.modify_assembly(parameters, Assembly())
    gradient, = torch.autograd.grad(next_mesh.nodes.square().sum(), parameters)
    assert torch.isfinite(gradient).all()
    assert gradient[component].abs() > 0
    assert gradient[fixed * 3] == 0

    archive = str(tmp_path / "iteration")
    brep.save(archive)
    brep.update_variables(-change)
    brep.load(archive)
    torch.testing.assert_close(brep.get_surface_parameters(), parameters.detach())


def test_step_export_rejects_a_moved_trim_edge(
    step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    brep = BREPSurface(step_factory("box"), control_point_spacing=0.7)
    name = next(name for name, face in brep.faces.items() if abs(face.signature[3] - 3) < 1e-7)
    brep.convert_faces_to_nurbs(name)
    model = brep.nurbs_faces[name]
    changed = model.control_points.detach().clone()
    changed[0, 2] += 0.1
    model.control_points = changed
    with pytest.raises(ValueError, match="trim edge"):
        brep.export_step(tmp_path / "invalid.stp")


def test_native_nurbs_step_without_selection_metadata_updates_next_mesh(
    step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    source = BREPSurface(step_factory("box"), control_point_spacing=0.7)
    name = next(name for name, face in source.faces.items() if abs(face.signature[3] - 3) < 1e-7)
    source.convert_faces_to_nurbs(name)
    path = source.export_step(tmp_path / "native.stp")
    path.with_suffix(".brep.json").unlink()
    brep = BREPSurface(path, control_point_spacing=0.7)
    brep.select_design_faces(name)
    brep.is_updatable = True
    body = BoundaryPart(fea_seed_size=1.2, mesh_order=1, part_name="body")
    body.add_surface_interface(brep)
    body.initialize()
    initial = body.build_part(str(tmp_path))
    model = brep.nurbs_faces[name]
    free = most_influential_pole(model)
    change = torch.zeros(brep.num_variables, dtype=brep.get_surface_parameters().dtype)
    change[free * 3 + 2] = 0.05
    brep.update_variables(change)
    updated = body.build_part(str(tmp_path))
    assert updated.nodes[:, 2].max() > initial.nodes[:, 2].max() + 1e-3


def test_brep_update_requires_a_nurbs_face(step_factory: Callable[[str], Path]) -> None:
    brep = BREPSurface(step_factory("box"), control_point_spacing=0.7)
    brep.is_updatable = True
    with pytest.raises(ValueError, match="requires select_design_faces"):
        _ = brep.num_variables


def test_only_selected_nurbs_face_enters_design_vector(
    step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    brep = BREPSurface(step_factory("box"), control_point_spacing=0.7)
    top = next(name for name, face in brep.faces.items() if abs(face.signature[3] - 3) < 1e-7)
    bottom = next(name for name, face in brep.faces.items() if abs(face.signature[3]) < 1e-7)
    brep.convert_faces_to_nurbs((top, bottom))
    brep.select_design_faces(top)
    brep.is_updatable = True
    body = BoundaryPart(fea_seed_size=1.2, mesh_order=1, part_name="body")
    body.add_surface_interface(brep)
    body.initialize()
    body.build_part(str(tmp_path))
    assert set(brep.nurbs_faces) == {top, bottom}
    assert set(brep.design_faces) == {top}
    assert brep.num_variables == brep.nurbs_faces[top].num_variables
    assert brep.nurbs_faces[bottom].design_mask is None
    step = torch.zeros(brep.num_variables, dtype=brep.get_surface_parameters().dtype)
    free = most_influential_pole(brep.nurbs_faces[top])
    step[free * 3 + 2] = 0.05
    brep.update_variables(step)
    exported = BREPSurface(brep.export_step(tmp_path / "selected.stp"))
    assert not exported.design_faces
    assert "design_faces" not in exported.metadata()
    assert "nurbs_faces" not in exported.metadata()
    exported.is_updatable = True
    with pytest.raises(ValueError, match="requires select_design_faces"):
        _ = exported.num_variables
    uv = np.asarray(brep.faces[bottom].parameter_bounds).mean(axis=1)[None, :]
    np.testing.assert_allclose(exported.evaluate_face(bottom, uv),
                               brep.evaluate_face(bottom, uv), atol=1e-8)


def test_constructor_controls_refinement_without_changing_geometry(
    step_factory: Callable[[str], Path],
) -> None:
    path = step_factory("cylinder")
    original = BREPSurface(path)
    name = next(name for name, face in original.faces.items() if face.geometry_type == "Cylinder")
    original.convert_faces_to_nurbs(name)
    original.select_design_faces(name)
    original.is_updatable = True
    base = original.nurbs_faces[name]
    refined = BREPSurface(path, control_point_spacing=0.8)
    refined.convert_faces_to_nurbs(name)
    refined.select_design_faces(name)
    refined.is_updatable = True
    model = refined.nurbs_faces[name]
    assert model.size[0] >= 17
    assert model.size[1] >= 8
    assert base.size[1] == 2  # Default leaves the analytic conversion unchanged.
    u = np.linspace(*base.parameter_bounds[0], 17)
    v = np.linspace(*base.parameter_bounds[1], 17)
    uv = torch.from_numpy(np.column_stack((u, v)))
    torch.testing.assert_close(model.map(uv), base.map(uv), atol=1e-10, rtol=1e-10)
    assert "control_point_spacing" not in refined.metadata()
    for spacing in (0, -1, float("inf"), float("nan"), True):
        with pytest.raises(ValueError, match="control_point_spacing"):
            BREPSurface(path, control_point_spacing=spacing)


def test_spacing_uses_physical_lengths_and_model_scale(quarter_cylinder: NURBSFace) -> None:
    coarse = quarter_cylinder.refine_by_spacing(0.5)
    fine = quarter_cylinder.refine_by_spacing(0.25)
    assert coarse.size == (5, 7)
    assert fine.size == (8, 13)
    uv = torch.tensor([[-2.0, 10.0], [0.2, 12.3], [5.0, 14.0]], dtype=torch.float64)
    torch.testing.assert_close(coarse.map(uv), quarter_cylinder.map(uv), atol=1e-12, rtol=1e-12)
    quarter_cylinder.control_points = quarter_cylinder.control_points * 2
    scaled = quarter_cylinder.refine_by_spacing(0.5)
    assert scaled.size == fine.size
