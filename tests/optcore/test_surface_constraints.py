"""Surface projections preserve derivatives throughout shape subproblems."""

import math

import pytest
import torch

from morphopt import BoundaryPart, UpdaterBoundaryPart
from morphopt.shapeopt import strategies
from morphopt.shapeopt.surfaces.base_surface import BaseSurface
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
        r0=radius, length=4.0, seed_size=1.0,
    )


def test_bsp_step_export_contains_one_meshable_closed_solid(tmp_path):
    import gmsh

    surface = cylinder(BspSurface)
    surface.initialize()
    output = tmp_path / surface.output_data(tmp_path, "boundary")
    assert output.is_file()
    assert not gmsh.isInitialized()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.importShapes(str(output))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        assert len(volumes) == 1
        assert len(gmsh.model.getBoundary(volumes, oriented=False)) == 3
        assert gmsh.model.occ.getMass(*volumes[0]) > 0
        gmsh.option.setNumber("Mesh.MeshSizeMin", 1.0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 1.0)
        gmsh.model.mesh.generate(3)
        assert sum(map(len, gmsh.model.mesh.getElements(3)[1])) > 0
    finally:
        gmsh.finalize()


def test_bsp_step_export_reports_lost_solid_and_finalizes(tmp_path, monkeypatch):
    import gmsh

    def destroy_solid(dim_tags, **kwargs):
        gmsh.model.occ.remove(dim_tags)
        return []

    monkeypatch.setattr(gmsh.model.occ, "healShapes", destroy_solid)
    surface = cylinder(BspSurface)
    surface.initialize()
    with pytest.raises(ValueError, match="does not form a closed solid"):
        surface.output_data(tmp_path, "invalid")
    assert not (tmp_path / "invalid.stp").exists()
    assert not gmsh.isInitialized()


def test_bsp_step_export_propagates_write_failure_and_finalizes(tmp_path, monkeypatch):
    import gmsh

    write = gmsh.write

    def fail_step(filename):
        if str(filename).endswith(".stp"):
            raise OSError("STEP write failed")
        return write(filename)

    monkeypatch.setattr(gmsh, "write", fail_step)
    surface = cylinder(BspSurface)
    surface.initialize()
    with pytest.raises(OSError, match="STEP write failed"):
        surface.output_data(tmp_path, "boundary")
    assert not gmsh.isInitialized()


@pytest.mark.parametrize("factory", [BspSurface, CPGEOSurface])
def test_boundary_order_owns_surface_orientation(factory):
    surface = cylinder(factory)
    surface.initialize()
    uv = (
        torch.as_tensor(surface.model.reference_to_curvilinear(surface.model._knots[[20, 40]]))
        if factory is CPGEOSurface else torch.tensor([[0.2, 0.4], [0.6, 0.7]])
    )
    outer_normals = surface.get_normals(uv)
    torch.testing.assert_close(outer_normals.norm(dim=1), torch.ones(2))
    part = BoundaryPart(part_name="body")
    part.add_surface_interface(BaseSurface())
    part.add_surface_interface(surface)
    assert surface.flip is True
    torch.testing.assert_close(surface.get_normals(uv), -outer_normals)
    with pytest.raises(AttributeError):
        surface.flip = False
    # Reinitializing a reordered Part derives orientation from the new order.
    part.surface_interfaces().reverse()
    part.initialize()
    assert [surface.flip for surface in part.surface_interfaces()] == [False, True]


def test_reinitialize_derives_orientation_after_removing_outer_surface():
    part = BoundaryPart(part_name="body")
    for _ in range(3):
        part.add_surface_interface(BaseSurface())
    assert [surface.flip for surface in part.surface_interfaces()] == [False, True, True]
    part.surface_interfaces().pop(0)
    part.reinitialize(iteration=1)
    assert [surface.flip for surface in part.surface_interfaces()] == [False, True]


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


@pytest.mark.parametrize("adaptive", [False, True])
def test_shape_update_enforces_relations_and_inner_solver_is_differentiable(adaptive):
    part = BoundaryPart(part_name="body")
    source, target = cylinder(BspSurface, 2.0), cylinder(BspSurface, 0.5)
    source.add_constraint(source.mirror("xz"))
    source.add_constraint(source.relate(target, pose=[0.0, 0.0, 0.0, 0.0, 0.0, math.pi / 2]))
    part.add_surface_interface(source)
    part.add_surface_interface(target)
    part.initialize()
    saved = part.get_parameters()
    updater = UpdaterBoundaryPart(
        max_step_iter=2, max_step_length=0.05,
        constraint_weight_strategy=strategies.AdaptiveShapeWeights() if adaptive else None,
    )
    updater.bind_target(part)
    updater.add_objective_function(updater.objectivefuncs.ShapeDerivative())
    updater.add_constraints(updater.objectivefuncs.Fairness())
    updater.initialize()
    updater.objective_value = float(sum(value.square().sum() for value in saved))
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
