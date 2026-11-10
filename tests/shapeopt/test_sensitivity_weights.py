"""Pointwise sensitivity factors reproduce the original geometric integrals."""

from types import SimpleNamespace

import pytest
import torch

from morphopt.shapeopt.objectivefuncs.basefuncs import BaseConstraints
from morphopt.shapeopt.objectivefuncs.boundarys import MinRadius
from morphopt.shapeopt.objectivefuncs.distancesurface import Distance
from morphopt.shapeopt.strategies import SensitivityShapeWeights


def point_problem(controls, points, penalties, areas=None):
    if areas is None:
        areas = [torch.ones(len(block), dtype=block.dtype) for block in points]
    rdu = [block.new_zeros((len(block), 3, 2)) for block in points]
    rdu2 = [block.new_zeros((len(block), 3, 2, 2)) for block in points]
    surfaces = [SimpleNamespace(is_updatable=True) for _ in points]
    for penalty in penalties.values():
        penalty.initialize(r0=points, rdu0=rdu, rdu20=rdu2, weights=areas, surfaces=surfaces)
    part = SimpleNamespace(
        get_parameters=lambda: [controls.flatten()],
        get_geometry_values=lambda: (points, rdu, rdu2),
    )
    updater = SimpleNamespace(update_kind="geometry", target=part, constraints_funcs=penalties)
    return updater


@pytest.mark.parametrize("scale", [1e-9, 1.0, 1e9])
def test_nearest_sensitivity_factors_preserve_raw_scales_and_area_weights(scale):
    controls = torch.tensor([
        [0., 0., 0.], [1000., 1., 0.], [0., 2., 0.], [1000., 0., 3.],
    ], dtype=torch.float64)
    points = [
        torch.stack((controls[0], controls[2], controls.new_tensor([600., 0., 0.]), controls[1])),
        controls[[3, 1]], controls[[1]],
    ]
    areas = [controls.new_tensor([2., 3., 4., 5.]), controls.new_tensor([6., 7.]), controls.new_tensor([11.])]
    penalties = {"first": BaseConstraints(), "second": BaseConstraints()}
    updater = point_problem(controls, points, penalties, areas)
    gradient = (scale * controls.new_tensor([[3., 4., 0.], [0., 0., 0.], [-12., 0., 5.], [0., -8., 0.]])).flatten().requires_grad_()
    original = gradient.detach().clone()
    coefficients = SensitivityShapeWeights()(updater, gradient)
    assert coefficients == {"first": 1., "second": 1.}
    expected = [controls.new_tensor([5., 13., 5., 5.]) * scale,
                controls.new_tensor([8., 8.]) * scale, controls.new_ones(1)]
    for penalty in penalties.values():
        for area, stored, factor, value in zip(areas, penalty.area_weights, penalty.sample_weights, expected):
            torch.testing.assert_close(stored, area, rtol=0, atol=0)
            torch.testing.assert_close(factor, value)
            assert not factor.requires_grad
        for effective, area, factor in zip(penalty.integration_weights, areas, expected):
            torch.testing.assert_close(effective, area * factor)
    torch.testing.assert_close(gradient.detach(), original, rtol=0, atol=0)


def test_zero_sensitivities_keep_unit_point_weights():
    controls = torch.tensor([[0., 0., 0.], [2., 0., 0.]], dtype=torch.float64)
    penalty = BaseConstraints()
    updater = point_problem(controls, [controls], {"limit": penalty})
    SensitivityShapeWeights()(updater, torch.zeros(6, dtype=controls.dtype))
    torch.testing.assert_close(penalty.sample_weights[0], torch.ones(2, dtype=controls.dtype))


def test_point_weights_enter_single_surface_integral_and_its_gradient():
    points = torch.tensor([[0.2, 0., 0.], [0.3, 0., 0.]], dtype=torch.float64)
    penalty = MinRadius(radius=0.5)
    area = points.new_tensor([2., 3.])
    updater = point_problem(points, [points], {"radius": penalty}, [area])
    gradient = points.new_tensor([2., 0., 0., 5., 0., 0.])
    SensitivityShapeWeights()(updater, gradient)

    def actual(shift):
        return penalty([points + torch.stack((shift, shift * 0, shift * 0))], [], []).sum()

    def reference(shift):
        z = (0.5 - points[:, 0] - shift) / 0.05
        return (area * points.new_tensor([2., 5.]) * z.pow(3)).sum()

    origin = points.new_zeros(())
    torch.testing.assert_close(actual(origin), reference(origin))
    torch.testing.assert_close(torch.func.grad(actual)(origin), torch.func.grad(reference)(origin))
    torch.testing.assert_close(penalty.area_weights[0], area)


def test_distance_keeps_the_original_product_of_two_point_weights():
    points = [torch.tensor([[0., 0., 0.]], dtype=torch.float64),
              torch.tensor([[0.9, 0., 0.]], dtype=torch.float64)]
    controls = torch.cat(points)
    penalty = Distance([[0., 1.], [1., 0.]])
    updater = point_problem(controls, points, {"distance": penalty})
    rdu = [controls.new_tensor([[[0., 0.], [1., 0.], [0., 1.]]]),
           controls.new_tensor([[[0., 0.], [1., 0.], [0., -1.]]])]
    unweighted = penalty(points, rdu)
    SensitivityShapeWeights()(updater, controls.new_tensor([2., 0., 0., 3., 0., 0.]))
    torch.testing.assert_close(penalty(points, rdu), 6 * unweighted)


def test_sample_factors_are_frozen_and_can_be_reset_independently_of_area():
    controls = torch.tensor([[0., 0., 0.]], dtype=torch.float64)
    penalty = BaseConstraints()
    point_problem(controls, [controls], {"limit": penalty})
    factors = controls.new_tensor([2.], requires_grad=True)
    penalty.set_sample_weights([factors])
    with torch.no_grad():
        factors.fill_(9.)
    torch.testing.assert_close(penalty.integration_weights[0], controls.new_tensor([2.]))
    penalty.set_sample_weights(None)
    torch.testing.assert_close(penalty.integration_weights[0], controls.new_ones(1))


@pytest.mark.parametrize("values", [
    [], [torch.ones(2)], [torch.tensor([-1.])], [torch.tensor([float("nan")])],
])
def test_invalid_sample_blocks_are_rejected(values):
    controls = torch.tensor([[0., 0., 0.]])
    penalty = BaseConstraints()
    point_problem(controls, [controls], {"limit": penalty})
    with pytest.raises(ValueError, match="Sample weights"):
        penalty.set_sample_weights(values)


def test_pointwise_shape_strategy_rejects_other_optimization_domains():
    with pytest.raises(TypeError, match="geometry"):
        SensitivityShapeWeights()(SimpleNamespace(update_kind="materials"), torch.ones(3))
