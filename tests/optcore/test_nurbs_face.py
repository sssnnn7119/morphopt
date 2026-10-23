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
    assert model.map(torch.empty((0, 2), dtype=torch.float64)).shape == (0, 3)


@pytest.mark.parametrize("kind", ["box", "triangle", "hole", "cylinder"])
@pytest.mark.parametrize("order", [1, 2])
def test_final_mesh_nodes_bind_to_trimmed_nurbs_and_have_gradients(
    kind: str, order: int, step_factory: Callable[[str], Path], tmp_path: Path,
) -> None:
    brep = BREPSurface(step_factory(kind))
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
