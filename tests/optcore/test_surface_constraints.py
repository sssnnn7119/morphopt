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


@pytest.mark.parametrize("order", [2, 3, 4, 5])
def test_bsp_rotation_repeats_each_row_clockwise(order):
    surface = BspSurface.initialize_cylinder(
        r0=2.0, length=4.0, seed_size=1.0, num_U_ratio=order,
    )
    points = surface.control_points.clone()
    points += torch.linspace(-0.1, 0.2, points.numel()).reshape_as(points)
    surface.control_points = points
    surface.add_constraint(surface.rotate(order=order))
    surface.apply_constraints()
    num_v, num_u = surface.model.size
    result = surface.control_points.reshape(num_v, num_u, 3)
    count = num_u // order
    sector = points.reshape(num_v, num_u, 3)[:, :count]
    torch.testing.assert_close(result[:, :count], sector)
    for step in range(order):
        angle = -math.tau * step / order
        rotation = points.new_tensor([
            [math.cos(angle), -math.sin(angle), 0],
            [math.sin(angle), math.cos(angle), 0],
            [0, 0, 1],
        ])
        torch.testing.assert_close(
            result[:, step * count:(step + 1) * count], sector @ rotation.T,
        )
    surface.apply_constraints()
    torch.testing.assert_close(surface.control_points.reshape_as(result), result)
    uv = points.new_tensor([[0.2, 0.14], [0.5, 0.37], [0.8, 0.62]])
    shifted_uv = uv.clone()
    shifted_uv[:, 1] = (shifted_uv[:, 1] + 1 / order) % 1
    angle = -math.tau / order
    rotation = points.new_tensor([
        [math.cos(angle), -math.sin(angle), 0],
        [math.sin(angle), math.cos(angle), 0],
        [0, 0, 1],
    ])
    torch.testing.assert_close(
        surface.map(shifted_uv), surface.map(uv) @ rotation.T,
        atol=1e-8, rtol=1e-7,
    )


def test_bsp_rotation_matches_ui_custom_rotation_and_mirror():
    surface = cylinder(BspSurface)
    points = surface.control_points.clone()
    points += torch.linspace(-0.1, 0.2, points.numel()).reshape_as(points)
    num_v, num_u = surface.model.size
    sector = points.reshape(num_v, num_u, 3)[:, :num_u // 3]
    copies = []
    for angle in (0, -2 * math.pi / 3, -4 * math.pi / 3):
        cosine, sine = math.cos(angle), math.sin(angle)
        copies.append(torch.stack((
            cosine * sector[..., 0] - sine * sector[..., 1],
            sine * sector[..., 0] + cosine * sector[..., 1],
            sector[..., 2],
        ), dim=-1))
    expected = torch.cat(copies, dim=1)
    reflected = expected.flip(dims=[1])
    expected = torch.stack((
        (expected[..., 0] + reflected[..., 0]) / 2,
        (expected[..., 1] - reflected[..., 1]) / 2,
        (expected[..., 2] + reflected[..., 2]) / 2,
    ), dim=-1)

    surface.control_points = points
    surface.add_constraint(surface.rotate(order=3))
    surface.add_constraint(surface.mirror("xz"))
    surface.apply_constraints()
    torch.testing.assert_close(surface.control_points.reshape_as(expected), expected)
    surface.reinitialize_constraints()
    torch.testing.assert_close(
        torch.as_tensor(surface.model.control_points), surface.control_points,
    )
    torch.testing.assert_close(surface.control_points.reshape_as(expected), expected)


def test_bsp_rotation_preserves_gradients_inside_torch_func():
    surface = cylinder(BspSurface)
    rotation = surface.rotate(order=3)
    points = surface.control_points.clone()
    weights = torch.linspace(-1, 2, points.numel()).reshape_as(points)

    def loss(values):
        surface.control_points = values
        rotation.apply(surface)
        return (surface.control_points * weights).sum()

    gradient = torch.func.grad(loss)(points)
    direction = torch.linspace(-0.3, 0.7, points.numel()).reshape_as(points)
    difference = (loss(points + 1e-5 * direction) - loss(points - 1e-5 * direction)) / 2e-5
    torch.testing.assert_close((gradient * direction).sum(), difference)
    num_v, num_u = surface.model.size
    gradient = gradient.reshape(num_v, num_u, 3)
    torch.testing.assert_close(
        gradient[:, num_u // 3:], torch.zeros_like(gradient[:, num_u // 3:]),
    )
    assert gradient[:, :num_u // 3].abs().sum() > 0


@pytest.mark.parametrize("order", [0, 1, -3, 2.5])
def test_bsp_rotation_rejects_invalid_order(order):
    with pytest.raises(ValueError, match="integer of at least 2"):
        BspSurface.rotate(order=order)


def test_bsp_rotation_rejects_unequal_sectors():
    surface = cylinder(BspSurface)
    with pytest.raises(ValueError, match="num_U_ratio=order"):
        surface.add_constraint(surface.rotate(order=5))


@pytest.mark.parametrize("adaptive", [False, True])
@pytest.mark.parametrize("symmetry", ["mirror", "rotate"])
def test_shape_update_enforces_relations_and_inner_solver_is_differentiable(adaptive, symmetry):
    part = BoundaryPart(part_name="body")
    source, target = cylinder(BspSurface, 2.0), cylinder(BspSurface, 0.5)
    source.add_constraint(
        source.mirror("xz") if symmetry == "mirror" else source.rotate(order=3)
    )
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
