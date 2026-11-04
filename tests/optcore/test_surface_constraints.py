"""Surface projections preserve derivatives throughout shape subproblems."""

import math

import pytest
import torch

from morphopt import BoundaryPart, UpdaterBoundaryPart
from morphopt.shapeopt.surfaces.bsp_surface import BspSurface
from morphopt.shapeopt.surfaces.cpgeo_surface import CPGEOSurface


@pytest.fixture(autouse=True)
def double_precision():
    previous = torch.get_default_dtype()
    torch.set_default_dtype(torch.float64)
    yield
    torch.set_default_dtype(previous)


def cylinder(factory, radius=2.0):
    return factory.initialize_cylinder(
        r0=radius, length=4.0, seed_size=1.0, flip=False,
    )


@pytest.mark.parametrize("factory", [BspSurface, CPGEOSurface])
def test_related_surface_gradient_reaches_source(factory):
    source, target = cylinder(factory), cylinder(factory)
    relation = source.relate(target, pose=[1.0, -2.0, 3.0, 0.0, 0.0, math.pi / 2])
    points = source.control_points.clone()
    weights = torch.arange(points.numel(), dtype=points.dtype).reshape_as(points)

    def loss(values):
        source.control_points = values
        relation.apply(source)
        return (target.control_points * weights).sum()

    gradient = torch.func.grad(loss)(points)
    # A +90 degree rotation maps (x, y, z) to (-y, x, z).
    expected = torch.stack((weights[:, 1], -weights[:, 0], weights[:, 2]), dim=1)
    torch.testing.assert_close(gradient, expected)
    direction = torch.randn_like(points)
    difference = (loss(points + 1e-5 * direction) - loss(points - 1e-5 * direction)) / 2e-5
    torch.testing.assert_close((gradient * direction).sum(), difference)


@pytest.mark.parametrize("factory", [BspSurface, CPGEOSurface])
def test_mirror_can_run_inside_torch_func(factory):
    surface = cylinder(factory)
    mirror = surface.mirror("xz")
    points = surface.control_points.clone()

    def loss(values):
        surface.control_points = values
        mirror.apply(surface)
        return surface.control_points[:, 0].sum()

    gradient = torch.func.grad(loss)(points)
    assert torch.isfinite(gradient).all()
    assert gradient[:, 0].abs().sum() > 0
    torch.testing.assert_close(gradient[:, 1:], torch.zeros_like(gradient[:, 1:]))


def test_cpgeo_rotation_can_run_inside_torch_func():
    surface = cylinder(CPGEOSurface)
    rotation = surface.rotate(axis="z", order=3)
    points = surface.control_points.clone()

    def loss(values):
        surface.control_points = values
        rotation.apply(surface)
        return surface.control_points[:, 2].sum()

    gradient = torch.func.grad(loss)(points)
    count = len(points) // 3
    torch.testing.assert_close(gradient[:count, 2], torch.full((count,), 3.0))
    torch.testing.assert_close(gradient[count:], torch.zeros_like(gradient[count:]))


def test_shape_update_enforces_relations_and_inner_solver_is_differentiable():
    part = BoundaryPart(part_name="body")
    source, target = cylinder(BspSurface, 2.0), cylinder(BspSurface, 0.5)
    source.add_constraint(source.mirror("xz"))
    source.add_constraint(source.relate(target, pose=[0.0, 0.0, 0.0, 0.0, 0.0, math.pi / 2]))
    part.add_surface_interface(source)
    part.add_surface_interface(target)
    part.initialize()
    saved = part.get_parameters()
    updater = UpdaterBoundaryPart(max_step_iter=2, max_step_length=0.05)
    updater.bind_target(part)
    updater.add_objective_function(updater.objectivefuncs.ShapeDerivative())
    updater.add_constraints(updater.objectivefuncs.Fairness())
    updater.initialize()
    updater.reinitialize(gradient=2 * torch.cat(saved))
    trial = torch.randn(part.num_variables) * 0.01
    gradient = torch.func.grad(updater.closure)(trial)
    assert torch.isfinite(gradient).all()
    # Dependent target variables do not independently change the geometry.
    torch.testing.assert_close(gradient[source.num_variables:], torch.zeros(target.num_variables))
    for surface, expected in zip(part.surface_interfaces(), saved):
        torch.testing.assert_close(surface.control_points.flatten(), expected)
    value_before = updater.closure(part.get_variables())
    change = updater.update()
    assert torch.isfinite(change).all()
    assert updater.closure(change) < value_before
    updater.update_variables(change)
    expected = torch.stack((-source.control_points[:, 1], source.control_points[:, 0], source.control_points[:, 2]), dim=1)
    torch.testing.assert_close(target.control_points, expected)
    # This is the later, non-differentiable geometry-export phase.
    source.synchronize()
    target.synchronize()
