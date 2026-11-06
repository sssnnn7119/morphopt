"""Fairness owns thresholds, reference state and extensible surface dispatch."""

import pytest
import torch

from morphopt.shapeopt.barriers import PolynomialBarrier
from morphopt.shapeopt.objectivefuncs.surfacefairness import Fairness
from morphopt.shapeopt.surfaces.base_surface import BaseSurface
from morphopt.shapeopt.surfaces.bsp_surface import BspSurface
from morphopt.shapeopt.surfaces.cpgeo_surface import CPGEOSurface


@pytest.fixture(autouse=True)
def geometry_dtype():
    previous = torch.get_default_dtype()
    torch.set_default_dtype(torch.float64)
    yield
    torch.set_default_dtype(previous)


@pytest.fixture
def surfaces():
    return [factory.initialize_cylinder(r0=2, length=12, seed_size=1.5)
            for factory in (BspSurface, CPGEOSurface)]


def patch_geometry(count=2):
    r = torch.zeros(count, 3)
    rdu = torch.tensor([[1., 0.], [0., 1.], [0., 0.]]).expand(count, -1, -1).clone()
    rdu2 = torch.zeros(count, 3, 2, 2)
    rdu2[:, 2, 0, 0] = 0.9**0.5
    weight = torch.arange(1, count + 1, dtype=r.dtype)
    return r, rdu, rdu2, weight


def bind(penalty, surfaces, count=2):
    r, rdu, rdu2, weight = patch_geometry(count)
    penalty.initialize(
        [r] * len(surfaces), [rdu] * len(surfaces), [rdu2] * len(surfaces),
        [weight] * len(surfaces), surfaces=surfaces,
    )
    return r, rdu, rdu2, weight


@pytest.mark.parametrize("index,power", [(0, 3), (1, 5)])
def test_curvature_penalty_matches_an_analytic_patch(surfaces, index, power):
    penalty = Fairness()
    r, rdu, rdu2, weight = bind(penalty, [surfaces[index]])
    actual = penalty([r], [rdu], [rdu2])
    # Principal curvatures are sqrt(0.9) and zero. The barrier argument is 0.5.
    torch.testing.assert_close(actual, weight.sum() * 0.5**power)
    relaxed = Fairness(max_curvature=2)
    bind(relaxed, [surfaces[index]])
    assert relaxed([r], [rdu], [rdu2]) == 0
    for surface in surfaces:
        assert not any(hasattr(surface, name) for name in (
            "MaxC", "MaxR", "MaxFF", "barrier_function", "rr_compensation",
            "get_penalty_fairness", "_geofair_data",
        ))


def test_bsp_nonorthogonality_uses_the_fixed_point_one_limit(surfaces):
    penalty = Fairness()
    r, rdu, rdu2, weight = bind(penalty, surfaces)
    rdu[:, :, 1] = torch.tensor([0.09**0.5, 0.91**0.5, 0.])
    rdu2 = torch.zeros_like(rdu2)
    value = penalty([r, r], [rdu, rdu], [rdu2, rdu2])
    torch.testing.assert_close(value, weight.sum() * 0.5**3)


def test_reference_compensation_is_private_to_each_penalty(surfaces):
    first, second = Fairness(), Fairness()
    r, rdu, rdu2, weight = bind(first, surfaces, count=2)
    bind(second, surfaces, count=3)
    expected = first([r, r], [rdu, rdu], [rdu2, rdu2])
    # Rebinding another visitor must not resize or overwrite this visitor's state.
    torch.testing.assert_close(first([r, r], [rdu, rdu], [rdu2, rdu2]), expected)
    bind(first, surfaces, count=4)
    assert len(first._evaluators[0][1].keywords["compensation"][0]) == 4
    assert len(second._evaluators[0][1].keywords["compensation"][0]) == 3
    assert weight.shape == (2,)


def test_bsp_metric_variation_uses_the_fixed_point_one_limit(surfaces):
    r, rdu, rdu2, weight = patch_geometry()
    reference_second = torch.zeros_like(rdu2)
    length = (2 * surfaces[0].model.size[0] * surfaces[0].init_size) ** 2
    current_second = torch.zeros_like(rdu2)
    current_second[:, 0, 0, 0] = 0.5 * (0.09 * length)**0.5
    penalty = Fairness()
    penalty.initialize([r] * 2, [rdu] * 2, [reference_second] * 2, [weight] * 2, surfaces=surfaces)
    torch.testing.assert_close(penalty([r] * 2, [rdu] * 2, [current_second] * 2), weight.sum() * 0.5**3)


@pytest.mark.parametrize("index", [0, 1])
def test_visitor_retains_first_and_second_derivatives(surfaces, index):
    penalty = Fairness()
    selected = [surfaces[index]]
    r, rdu, rdu2, _ = bind(penalty, selected)
    before = [surface.control_points.clone() for surface in surfaces]
    def value(scale):
        return penalty([r], [rdu], [rdu2 * scale])
    scale = torch.tensor(1.0, requires_grad=True)
    assert torch.autograd.gradcheck(value, (scale,))
    assert torch.autograd.gradgradcheck(value, (scale,))
    for surface, original in zip(surfaces, before):
        torch.testing.assert_close(surface.control_points, original)


def test_one_fairness_sums_all_updatable_surfaces(surfaces):
    penalty = Fairness()
    r, rdu, rdu2, weight = bind(penalty, surfaces)
    torch.testing.assert_close(penalty([r, r], [rdu, rdu], [rdu2, rdu2]), weight.sum() * (0.5**3 + 0.5**5))
    surfaces[0].is_updatable = False
    bind(penalty, surfaces)
    torch.testing.assert_close(penalty([r, r], [rdu, rdu], [rdu2, rdu2]), weight.sum() * 0.5**5)
    surfaces[1].is_updatable = False
    bind(penalty, surfaces)
    zero = penalty([r, r], [rdu, rdu], [rdu2, rdu2])
    assert zero == 0 and zero.dtype == r.dtype and zero.device == r.device


def test_new_surface_handler_uses_the_existing_penalty_barrier():
    class NewSurface(BaseSurface):
        pass

    surface = NewSurface()
    surface.is_updatable = True
    penalty = Fairness()
    # Register a valid evaluator with the visitor; no new method is added to geometry.
    @Fairness.visit.register(NewSurface)
    def visit_new(self, surface, rdu, rdu2):
        return lambda weight, rdu, rdu2: self._integrate(
            rdu[:, 0, 0], self.max_curvature, 3, weight,
        )

    r, rdu, rdu2, weight = bind(penalty, [surface])
    calls = []
    barrier = PolynomialBarrier()

    def shared_barrier(*args, **kwargs):
        calls.append(True)
        return barrier(*args, **kwargs)

    penalty.barrier_function = shared_barrier
    assert penalty([r], [rdu], [rdu2]) > 0
    assert calls == [True]
    assert not hasattr(surface, "get_penalty_fairness")


@pytest.mark.parametrize("parameters", [
    {"max_curvature": 0}, {"max_curvature": float("nan")}, {"max_curvature": float("inf")},
])
def test_invalid_fairness_configuration_is_rejected(parameters):
    with pytest.raises(ValueError):
        Fairness(**parameters)


def test_all_surfaces_share_one_curvature_limit_and_one_weight(surfaces):
    from morphopt.optcore.updaters import BaseUpdater
    from morphopt.shapeopt.strategies import AdaptiveShapeWeights
    class PatchUpdater(BaseUpdater):
        update_kind = "geometry"
        def __init__(self):
            super().__init__()
            self.obj_funcs = {"physical": object()}
            self.penalty = Fairness()
            self.add_constraints(self.penalty)
            self.data = bind(self.penalty, surfaces)
        def closure(self, x, return_list=False):
            r, rdu, rdu2, _ = self.data
            values = [rdu2 * (1 + 0.1*x[0]), rdu2 * (1 + 0.1*x[3])]
            return [-x[0] - 2*x[3]], [self.penalty([r, r], [rdu, rdu], values)]
    updater = PatchUpdater()
    x = torch.zeros(6)
    jacobian = torch.func.grad(lambda x: updater.closure(x, True)[1][0])(x)
    assert jacobian[0] > 0 and jacobian[3] > 0
    weights = AdaptiveShapeWeights()(updater, torch.tensor([-1., 0, 0, -2., 0, 0]))
    assert list(weights) == list(updater.constraints_funcs) and len(weights) == 1
    updater.penalty.max_curvature = 2.0
    assert updater.closure(x, True)[1][0] == 0
    torch.testing.assert_close(torch.func.grad(lambda x: updater.closure(x, True)[1][0])(x), torch.zeros(6))


def test_public_fairness_constructor_only_exposes_curvature():
    import inspect
    from morphopt.constants import CONSTANT
    assert set(inspect.signature(Fairness).parameters) == {"max_curvature"}
    settings = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.FAIRNESS
    assert settings.METRIC_VARIATION_LIMIT == settings.NONORTHOGONALITY_LIMIT == 0.1
    for name in ("surface_index", "max_metric_variation", "max_nonorthogonality"):
        with pytest.raises(TypeError):
            Fairness(**{name: 0.2})
