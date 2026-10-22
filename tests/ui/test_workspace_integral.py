"""Check emitted workspace expressions against maps with known measures."""
from __future__ import annotations

from collections.abc import Callable
from textwrap import indent
from types import SimpleNamespace

import pytest
import torch

from morphopt.optcore.quadrature import actuation_boundary_gauss_points
from morphopt.ui.codegen.workspace import workspace_integral_body
from morphopt.ui.codegen.generator import _objective_function_body


def evaluate_workspace(
    axes: list[int],
    bounds: list[tuple[float, float]],
    motion_and_jacobian: Callable[[torch.Tensor], tuple[torch.Tensor, torch.Tensor]],
    order: int = 3,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Execute the generated body and capture its signed sum before abs()."""
    points, weights, tangents, orientations = actuation_boundary_gauss_points(bounds, order)
    names = [f"gauss_{index}" for index in range(len(points))]
    loads = [f"input_{index}" for index in range(len(axes))]
    results = {}
    for name, point in zip(names, points, strict=True):
        motion, jacobian = motion_and_jacobian(torch.tensor(point, dtype=torch.float64))
        state = torch.zeros(6, dtype=torch.float64)
        state[axes] = motion
        derivatives = {}
        for index, load in enumerate(loads):
            column = torch.zeros((6, 1), dtype=torch.float64)
            column[axes, 0] = jacobian[:, index]
            derivatives[load] = column
        results[name] = SimpleNamespace(GC=state, jacobian=derivatives)
    assembly = SimpleNamespace(
        device="cpu",
        _GC_list_indexStart=[0],
        _GC2RGC=lambda coordinates: [coordinates],
        get_reference_point=lambda name: SimpleNamespace(_RGC_index=0),
    )
    objective = SimpleNamespace(
        fe=SimpleNamespace(assembly=assembly),
        fe_results=results,
        set_step=lambda name: None,
    )
    body = workspace_integral_body(
        reference_point_name="RP", axes=axes,
        load_groups=[[(load, 0)] for load in loads],
        case_names=names, weights=weights.tolist(), tangents=tangents.tolist(),
        orientations=orientations.tolist(),
    )
    signed_sums = []

    def capture_abs(value: torch.Tensor) -> torch.Tensor:
        signed_sums.append(value)
        return value.abs()

    namespace = {"abs": capture_abs, "Any": object}
    exec("def measure(self):\n" + indent(body, "    "), namespace)
    measure = namespace["measure"](objective)
    kind = {
        (0, 2): "workspace_plane", (0, 1, 2): "workspace_space",
        (0, 2, 4): "workspace_pose", (3, 4, 5): "workspace_rotation",
    }[tuple(axes)]
    term = {
        "type": "workspace", "kind": kind, "weight": 2.0,
        "normalization": 5.0, "reference_point_name": "RP", "gauss_order": order,
        "inputs": [{"parameters": [[load, 0]], "upper": upper} for load, (_lower, upper) in zip(loads, bounds, strict=True)],
        "case_names": names,
    }
    problem = SimpleNamespace(
        steps=SimpleNamespace(step_values={name: {} for name in names}),
        fea_components=lambda: [SimpleNamespace(type="ReferencePoint", name="RP")],
        reference_point_names=lambda: ["RP"],
        amplitude_components=lambda: [SimpleNamespace(name=load, num_values=1) for load in loads],
    )
    loss_body = _objective_function_body(SimpleNamespace(objective_terms=[term]), problem)
    exec("def objective_function(self):\n" + indent(loss_body, "    "), namespace)
    loss = namespace["objective_function"](objective)
    return measure, signed_sums[0], loss


@pytest.mark.parametrize("axes", [[0, 2], [0, 1, 2]])
def test_identity_map(axes: list[int]) -> None:
    dimensions = len(axes)

    def mapping(point: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return point, torch.eye(dimensions, dtype=torch.float64)

    measure, signed, loss = evaluate_workspace(axes, [(0.0, 1.0)] * dimensions, mapping)
    assert signed.item() == pytest.approx(float(dimensions))
    assert measure.item() == pytest.approx(1.0)
    assert loss.item() == pytest.approx(-0.4)


@pytest.mark.parametrize("order", [1, 2, 4])
@pytest.mark.parametrize("reflected", [False, True])
def test_planar_signed_area_and_maximization_gradient(order: int, reflected: bool) -> None:
    scale = torch.tensor(1.3, dtype=torch.float64, requires_grad=True)
    matrix = torch.tensor([[1.0, 0.4], [0.2, 1.5]], dtype=torch.float64)
    if reflected:
        matrix[0] *= -1
    translation = torch.tensor([5.0, -7.0], dtype=torch.float64)

    def mapping(point: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return scale * (matrix @ point) + translation, scale * matrix

    measure, signed, loss = evaluate_workspace([0, 2], [(0.0, 2.0), (0.0, 3.0)], mapping, order)
    signed_area = scale**2 * torch.linalg.det(matrix) * 6.0
    assert signed.item() == pytest.approx((2 * signed_area).item())
    assert measure.item() == pytest.approx(signed_area.abs().item())
    assert loss.item() == pytest.approx(-2.0 * measure.item() / 5.0)
    gradient, = torch.autograd.grad(loss, scale)
    expected = -2.0 / 5.0 * 2 * scale * torch.linalg.det(matrix).abs() * 6.0
    assert gradient.item() == pytest.approx(expected.item())
    assert gradient.item() < 0


def test_planar_nonlinear_map() -> None:
    def mapping(point: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        x, y = point
        return torch.stack([x**2, y**3]), torch.diag(torch.stack([2 * x, 3 * y**2]))

    measure, signed, loss = evaluate_workspace([0, 2], [(0.0, 2.0), (0.0, 3.0)], mapping)
    assert signed.item() == pytest.approx(216.0)
    assert measure.item() == pytest.approx(108.0)
    assert loss.item() == pytest.approx(-43.2)


@pytest.mark.parametrize("axes,divisor", [([0, 1, 2], 3.0), ([0, 2, 4], 3.0), ([3, 4, 5], 24.0)])
@pytest.mark.parametrize("reflected", [False, True])
def test_spatial_signed_volume_and_maximization_gradient(axes: list[int], divisor: float, reflected: bool) -> None:
    scale = torch.tensor(1.3, dtype=torch.float64, requires_grad=True)
    matrix = torch.tensor([[1.0, 0.2, 0.1], [0.0, 2.0, 0.3], [0.0, 0.0, 3.0]], dtype=torch.float64)
    if reflected:
        matrix[0] *= -1
    translation = torch.tensor([5.0, -7.0, 9.0], dtype=torch.float64)

    def mapping(point: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return scale * (matrix @ point) + translation, scale * matrix

    measure, signed, loss = evaluate_workspace(axes, [(0.0, 2.0), (0.0, 3.0), (0.0, 4.0)], mapping)
    volume = scale**3 * torch.linalg.det(matrix) * 24.0
    assert signed.item() == pytest.approx((3 * volume).item())
    assert measure.item() == pytest.approx((3 * volume.abs() / divisor).item())
    assert loss.item() == pytest.approx(-2.0 * measure.item() / 5.0)
    gradient, = torch.autograd.grad(loss, scale)
    expected = -2.0 / 5.0 * 9.0 / divisor * scale**2 * torch.linalg.det(matrix).abs() * 24.0
    assert gradient.item() == pytest.approx(expected.item())
    assert gradient.item() < 0


def test_planar_edge_sign_order_with_nonlinear_shear() -> None:
    points, weights, tangents, orientations = actuation_boundary_gauss_points([(0.0, 1.0)] * 2, 2)
    assert orientations.tolist() == [-1.0, -1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0]
    assert tangents[:, 0].tolist() == [1, 1, 1, 1, 0, 0, 0, 0]
    assert points[:2, 0].tolist() == [0.0, 0.0]
    assert points[2:4, 0].tolist() == [1.0, 1.0]
    assert points[4:6, 1].tolist() == [0.0, 0.0]
    assert points[6:8, 1].tolist() == [1.0, 1.0]

    # u = (p1 + 0.6*p2**2, p2) is injective, has det(J)=1 and unit area.
    contributions = []
    for (p1, p2), weight, (axis, _unused) in zip(points, weights, tangents, strict=True):
        x, y = p1 + 0.6 * p2**2, p2
        dx, dy = (1.0, 0.0) if axis == 0 else (1.2 * p2, 1.0)
        contributions.append(weight * (x * dy - y * dx))
    signed_sum = sum(sign * value for sign, value in zip(orientations, contributions, strict=True))
    proposed_signs = [-1.0] * 4 + [1.0] * 4
    proposed_sum = sum(sign * value for sign, value in zip(proposed_signs, contributions, strict=True))
    assert signed_sum == pytest.approx(2.0)
    assert abs(signed_sum) / 2 == pytest.approx(1.0)
    assert abs(proposed_sum) / 2 == pytest.approx(0.8)
