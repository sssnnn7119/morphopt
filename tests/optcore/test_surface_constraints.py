"""Surface projections preserve derivatives throughout shape subproblems."""

import math

import cpgeo
import numpy as np
import pytest
import torch

from morphopt import BoundaryPart, UpdaterBoundaryPart
from morphopt.constants import CONSTANT
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


def test_cpgeo_stl_rejects_open_control_mesh(tmp_path):
    surface = cylinder(CPGEOSurface)
    surface.model._cp_faces = surface.model._cp_faces[:-1]
    with pytest.raises(ValueError, match="closed control mesh"):
        surface.write_surface(tmp_path / "open", "stl")
    assert not (tmp_path / "open.stl").exists()


def test_cpgeo_preload_uses_all_samples_in_a_closed_inward_mesh():
    surface = cylinder(CPGEOSurface)
    surface.initialize()
    surface.pre_load()
    sample = surface.preload_data
    faces = sample.faces.cpu().numpy()
    points = surface.model.curvilinear_to_reference(sample.uv.cpu().numpy())[0]
    np.testing.assert_array_equal(np.unique(faces), np.arange(len(points)))
    edges = np.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    assert (np.unique(edges, axis=0, return_counts=True)[1] == 2).all()
    a, b, c = points[faces].transpose(1, 0, 2)
    assert (np.einsum("ij,ij->i", a, np.cross(b - a, c - a)) < 0).all()


def test_cpgeo_stl_retains_uniform_samples_for_fe_matching(tmp_path, monkeypatch):
    import pyvista as pv

    surface = cylinder(CPGEOSurface)
    surface.initialize()
    knots, faces = surface.model._knots, surface.model._cp_faces
    order = np.arange(len(knots))[::-1]
    samples, triangles = knots[order], order[faces].copy()
    monkeypatch.setattr(surface.model, "uniformly_mesh", lambda **kwargs: (samples, triangles))

    mesh = pv.read(surface.write_surface(tmp_path / "surface", "stl"))
    np.testing.assert_array_equal(surface._output_rsphere, samples)
    np.testing.assert_array_equal(surface._output_cpfaces, triangles)
    assert mesh.n_open_edges == 0


@pytest.mark.parametrize("cavity", [False, True])
def test_cpgeo_cylinder_side_normals_follow_boundary_role(cavity):
    center = torch.tensor([2.0, -3.0, 5.0])
    surface = CPGEOSurface.initialize_cylinder(3, 8, 0.9, init_location=center.tolist())
    part = BoundaryPart()
    if cavity:
        part.add_surface_interface(BaseSurface())
    part.add_surface_interface(surface)
    surface.initialize()
    surface.pre_load()
    points = surface.get_r() - center
    side = (points[:, 2] - 4).abs() < 2
    radial = torch.nn.functional.normalize(points[side, :2])
    assert side.any()

    normal = surface.get_normals(surface.preload_data.uv[side])
    expected = -radial if cavity else radial
    assert ((normal[:, :2] * expected).sum(dim=1) > 0.95).all()
    du, dv = surface.get_rdu()[side].unbind(dim=2)
    torch.testing.assert_close(torch.nn.functional.normalize(torch.cross(dv, du, dim=1)), normal)


def test_cpgeo_cylinder_locks_planar_disks_before_first_reconstruction():
    radius, length, spacing = 4.0, 10.0, 1.4
    surface = CPGEOSurface.initialize_cylinder(radius, length, spacing)
    points = surface.model.control_points
    anchors = points[surface._fixed_indices.numpy()].copy()
    for height in (0, length):
        disk = anchors[anchors[:, 2] == height]
        np.testing.assert_array_equal(disk, points[points[:, 2] == height])
        radii = np.linalg.norm(disk[:, :2], axis=1)
        assert np.any((radii > 0) & (radii < 0.8 * radius))
        assert np.isclose(radii, radius).any()
    assert np.isin(anchors[:, 2], [0, length]).all()

    surface.add_constraint(surface.mirror("xz"))
    surface.initialize()
    surface.reinitialize_constraints()
    for _ in range(2):
        surface._reinitialize()
        surface.reinitialize_constraints()
        surface.apply_constraints()
        np.testing.assert_array_equal(surface.control_points[surface._fixed_indices], anchors)
        assert len(surface._fixed_indices.unique()) == len(anchors)
        faces = surface.model._cp_faces
        for z in (0, length):
            disk = np.isclose(surface.model.control_points[:, 2], z, rtol=0, atol=1e-10)
            assert np.isin(np.flatnonzero(disk), surface._fixed_indices).all()
            # The cap is a triangulated disk, including its shared wall rim.
            disk_faces = faces[disk[faces].all(axis=1)]
            radii = np.linalg.norm(surface.model.control_points[:, :2], axis=1)
            interior = disk & (radii < radius - 1e-8)
            assert disk[faces[interior[faces].any(axis=1)]].all()
            edges = np.sort(disk_faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
            assert len(np.unique(disk_faces)) - len(np.unique(edges, axis=0)) + len(disk_faces) == 1
        uv = surface.model.reference_to_curvilinear(surface.model._knots)
        for end in surface.get_node_sets(surface.model.control_points, node_uv=uv).values():
            assert len(end) >= 3
            assert np.isin(end, surface._fixed_indices).all()


def test_cpgeo_reconstructed_actuator_cavity_has_no_crossing_control_faces():
    import pyvista as pv
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkCommonTransforms import vtkTransform
    from vtkmodules.vtkFiltersModeling import vtkCollisionDetectionFilter

    surface = CPGEOSurface.initialize_cylinder(
        4, 74, 1, init_location=[0, 0, 3], perturbation_L=10, fix_end_caps=False,
    )
    surface.add_constraint(surface.mirror("xz"))
    surface.initialize()
    surface.reinitialize_constraints()
    surface.apply_constraints()
    surface.reinitialize(0)
    surface.reinitialize_constraints()
    surface.apply_constraints()

    faces = surface.model._cp_faces
    mesh = pv.PolyData.from_regular_faces(surface.model.control_points, faces)
    contacts = vtkCollisionDetectionFilter()
    contacts.SetCollisionModeToHalfContacts()
    for side in (0, 1):
        contacts.SetInputData(side, mesh)
        contacts.SetTransform(side, vtkTransform())
    contacts.Update()
    left, right = (vtk_to_numpy(contacts.GetContactCells(side)) for side in (0, 1))
    # Contact between cells sharing a control vertex is expected on a closed shell.
    assert (faces[left, :, None] == faces[right, None, :]).any(axis=(1, 2)).all()


@pytest.mark.parametrize("reverse", [False, True])
def test_cpgeo_mirror_reinserts_cap_centers_without_reversing_winding(reverse):
    surface = CPGEOSurface.initialize_cylinder(3, 9, 1)
    if reverse:
        surface.model._cp_faces = surface.model._cp_faces[:, [0, 2, 1]].copy()
    surface.initialize()
    # Both cap centers lie on the mirror plane and are removed by the cut.
    centers = np.flatnonzero(np.all(surface.model.control_points[:, :2] == 0, axis=1))
    surface._capture_fixed_controls(centers)
    anchors = surface._fixed_points.clone()

    def signed_volume():
        points = surface.model.control_points
        a, b, c = (points - points.mean(axis=0))[surface.model._cp_faces].transpose(1, 0, 2)
        return np.einsum("ij,ij->", a, np.cross(b, c)) / 6

    before = signed_volume()
    mirror = surface.mirror("xz")
    surface.add_constraint(mirror)
    surface.reinitialize_constraints()

    assert len(surface.control_points) == mirror._replicated_count + 2
    torch.testing.assert_close(surface.control_points[surface._fixed_indices], anchors, rtol=0, atol=0)
    assert signed_volume() * before > 0


def test_cpgeo_end_controls_survive_design_updates_reconstruction_and_restart(tmp_path):
    surface = CPGEOSurface.initialize_cylinder(3, 9, 1, init_location=[1, -2, 5])
    surface.initialize()
    surface.reinitialize(0)
    surface.reinitialize_constraints()
    anchors = surface.control_points.detach()[surface._fixed_indices].clone()
    for _ in range(2):
        surface.synchronize()
        surface._reinitialize()
        before = surface.control_points.clone()
        delta = torch.full_like(before, 0.01, requires_grad=True)
        surface.update_variables(delta)
        grad, = torch.autograd.grad(surface.control_points.sum(), delta)
        locked = surface._fixed_indices
        free = torch.ones(len(before), dtype=torch.bool)
        free[locked] = False
        torch.testing.assert_close(grad[locked], torch.zeros_like(grad[locked]))
        torch.testing.assert_close(grad[free], torch.ones_like(grad[free]))
        np.testing.assert_array_equal(surface.control_points.detach()[surface._fixed_indices], anchors)
    surface.save(tmp_path / "surface")
    native = cpgeo.CPGEO.load(tmp_path / "surface.npz")
    np.testing.assert_array_equal(native.control_points, surface.control_points.detach().numpy())
    np.testing.assert_array_equal(native._cp_faces, surface.model._cp_faces)
    np.testing.assert_allclose(native.map3(native._knots), surface.model.map3(surface.model._knots))

    restored = cylinder(CPGEOSurface)
    restored.load(tmp_path / "surface")
    np.testing.assert_array_equal(restored._cap_disks, surface._cap_disks)
    restored._reinitialize()
    np.testing.assert_array_equal(restored.control_points[restored._fixed_indices], anchors)


def test_cpgeo_cylinder_with_free_ends_remains_closed_and_updates_after_restart(tmp_path):
    surface = CPGEOSurface.initialize_cylinder(2, 4, 1, fix_end_caps=False)
    fixed = cylinder(CPGEOSurface)
    np.testing.assert_array_equal(surface.model.control_points, fixed.model.control_points)
    np.testing.assert_array_equal(surface.model._cp_faces, fixed.model._cp_faces)
    surface.initialize()
    surface.reinitialize(0)
    surface.reinitialize_constraints()
    assert surface.get_node_sets(surface.model.control_points) == {}
    assert surface._fixed_indices is None
    surface.save(tmp_path / "cavity")
    fixed.load(tmp_path / "cavity")
    assert fixed.end_node_set_names == ()
    before = fixed.control_points.clone()
    delta = torch.full_like(before, 0.1)
    fixed.update_variables(delta)
    torch.testing.assert_close(fixed.control_points, before + delta)


def test_cpgeo_native_archive_loads_without_end_constraints(tmp_path):
    surface = cylinder(CPGEOSurface)
    path = tmp_path / "native.surface.npz"
    surface.model.save(path)
    surface.load(path)
    assert surface.end_node_set_names == ()
    assert surface._fixed_indices is None
    surface.update_variables(torch.ones_like(surface.control_points))
    surface.save(path)
    native = cpgeo.CPGEO.load(path)
    np.testing.assert_array_equal(native.control_points, surface.control_points.numpy())
    with np.load(path) as state:
        assert "cap_indices" not in state


@pytest.mark.parametrize("order", [1, 2])
def test_cpgeo_cap_node_sets_on_volume_mesh(order):
    part = BoundaryPart(fea_seed_size=0.8, mesh_order=order, part_name="cylinder")
    surface = CPGEOSurface.initialize_cylinder(3, 9, 1, init_location=[0, 0, 2])
    surface.add_constraint(surface.mirror("xz"))
    part.add_surface_interface(surface)
    part.initialize()
    part.reinitialize(0)
    mesh = part.get_part()
    coords = mesh.nodes.detach().numpy()
    ends = []
    for name, height in (("Bottom", 2), ("Head", 11)):
        indices = mesh.set_nodes[f"surface_0_{name}"]
        points = coords[indices]
        assert len(points) >= 3
        assert np.all(np.abs(points[:, 2] - height) < surface.init_size / 2)
        assert np.linalg.matrix_rank(points[:, :2] - points[:, :2].mean(0)) == 2
        ends.append(indices)
    assert not np.intersect1d(*ends).size


def test_cpgeo_short_cylinder_end_bands_exclude_midplane_and_outside_disk():
    surface = CPGEOSurface.initialize_cylinder(2, 0.5, 1, init_location=[1, -2, 3])
    surface.initialize()
    nodes = np.array([[1, -2, 3.1], [1, -2, 3.4], [1, -2, 3.25], [4, -2, 3.1]])
    centers = np.flatnonzero(np.all(surface.model.control_points[:, :2] == [1, -2], axis=1))
    uv = surface.model.reference_to_curvilinear(surface.model._knots[centers[[0, 1, 0, 0]]])
    sets = surface.get_node_sets(nodes, node_uv=uv)
    np.testing.assert_array_equal(sets["Bottom"], [0])
    np.testing.assert_array_equal(sets["Head"], [1])


def test_cpgeo_folded_side_wall_stays_out_of_both_cap_sets():
    surface = CPGEOSurface.initialize_cylinder(3, 9, 1)
    surface.initialize()
    surface.reinitialize(0)
    surface.reinitialize_constraints()
    model = surface.model
    points = model.control_points.copy()
    height = points[:, 2]
    side = np.flatnonzero((height > 3) & (height < 6))[:2]
    fixed = surface._fixed_indices.cpu().numpy()
    caps = [fixed[np.argmin(np.linalg.norm(points[fixed] - center, axis=1))]
            for center in surface._cap_disks[:, :3]]

    # Both wall controls enter the exact same positions as real cap controls.
    # Their reference knots still identify them as part of the side wall.
    points[side] = points[caps]
    surface.set_surface_parameters(torch.from_numpy(points))
    surface.synchronize()
    query = [side[0], caps[1], caps[0], side[1]]
    uv = model.reference_to_curvilinear(model._knots[query])
    sets = surface.get_node_sets(model.control_points[query], node_uv=uv)
    np.testing.assert_array_equal(sets["Bottom"], [2])
    np.testing.assert_array_equal(sets["Head"], [1])


def test_bsp_rejects_stl_export(tmp_path):
    surface = cylinder(BspSurface)
    with pytest.raises(ValueError, match="BspSurface does not support 'stl'"):
        surface.write_surface(tmp_path / "boundary", "stl")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("method", [None, "mirror_z", "antisymmetry_z", "periodic_z"])
def test_bsp_step_export_contains_one_meshable_closed_solid(tmp_path, method):
    import gmsh

    surface = cylinder(BspSurface)
    if method:
        surface = BspSurface.initialize_cylinder(
            r0=2, length=4, seed_size=1, num_V_ratio=2 if method == "periodic_z" else 1,
        )
        surface.add_constraint(getattr(surface, method)())
        delta = 0.01 * torch.sin(torch.arange(surface.control_points.numel()))
        surface.update_variables(delta.reshape_as(surface.control_points))
        surface.apply_constraints()
    surface.initialize()
    output = surface.write_surface(tmp_path / "boundary")
    assert output == tmp_path / "boundary.stp"
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
        surface.write_surface(tmp_path / "invalid", "stp")
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
        surface.write_surface(tmp_path / "boundary", "stp")
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
    surface.add_constraint(mirror)
    surface.initialize()
    surface.reinitialize_constraints()
    points = surface.control_points.clone()

    def loss(values):
        surface.control_points = values
        mirror.apply(surface)
        return surface.control_points[:, 0].sum()

    gradient = torch.func.grad(loss)(points)
    assert torch.isfinite(gradient).all()
    assert gradient[:, 0].abs().sum() > 0
    torch.testing.assert_close(gradient[:, 1:], torch.zeros_like(gradient[:, 1:]))


@pytest.mark.parametrize("plane,axis", [("yz", 0), ("xz", 1), ("xy", 2)])
@pytest.mark.parametrize("offset", [0.0, 1.25])
def test_cpgeo_mirror_reinitializes_coordinates_and_topology(plane, axis, offset):
    center = [0.0, 0.0, 0.0]
    center[axis] = offset
    surface = CPGEOSurface.initialize_Sphere(
        r0=2.0, seed_size=0.5, init_location=center,
    )
    surface.add_constraint(surface.mirror(plane, offset))
    surface.initialize()
    surface.reinitialize_constraints()
    surface.apply_constraints()

    vertices = surface.model.control_points
    faces = surface.model._cp_faces
    assert np.issubdtype(vertices.dtype, np.floating)
    assert np.issubdtype(faces.dtype, np.integer)
    assert faces.min() >= 0 and faces.max() < len(vertices)
    assert np.max(np.abs(vertices - center)) <= 2.0 + 1e-10
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    assert np.all(np.unique(edges, axis=0, return_counts=True)[1] == 2)

    source, reflected = surface.control_points.chunk(2)
    expected = source.clone()
    expected[:, axis] = 2 * offset - expected[:, axis]
    torch.testing.assert_close(reflected, expected)
    assert torch.isfinite(surface.get_r()).all()


def test_cpgeo_rotation_can_run_inside_torch_func():
    surface = CPGEOSurface.initialize_cylinder(2.0, 4.0, seed_size=0.5)
    rotation = surface.rotate(axis="z", order=3)
    surface.add_constraint(rotation)
    surface.initialize()
    surface.reinitialize(0)
    surface.reinitialize_constraints()
    points = surface.control_points.clone()

    def loss(values):
        surface.control_points = values
        rotation.apply(surface)
        return surface.control_points[:, 2].sum()

    gradient = torch.func.grad(loss)(points)
    count = rotation._replicated_count // rotation.order
    expected = torch.zeros_like(points)
    expected[:count, 2] = rotation.order
    expected[surface._fixed_indices] = 0.0
    torch.testing.assert_close(gradient, expected)
    np.testing.assert_array_equal(surface.control_points[surface._fixed_indices], surface._fixed_points)


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


@pytest.mark.parametrize("method", ["mirror_z", "antisymmetry_z"])
def test_bsp_axial_symmetry_preserves_end_constraints_and_shifted_cylinder(method):
    surface = BspSurface.initialize_cylinder(
        r0=2, length=30, seed_size=1, init_location=[2, 3, 7],
    )
    surface.add_constraint(getattr(surface, method)())
    initial = surface.control_points.clone()
    surface.reinitialize_constraints()
    torch.testing.assert_close(surface.control_points, initial)
    delta = 0.05 * torch.sin(torch.arange(initial.numel())).reshape_as(initial)
    surface.update_variables(delta)
    before = surface.control_points.clone().reshape(*surface.model.size, 3)
    surface.apply_constraints()
    points = surface.control_points.reshape_as(before)
    guard = CONSTANT.KERNEL.SURFACE.FIXED_END_CONTROL_POINT_ROWS
    torch.testing.assert_close(points[[0, -1]], before[[0, -1]], atol=0, rtol=0)
    torch.testing.assert_close(points[:guard, :, 2], before[:guard, :, 2], atol=0, rtol=0)
    torch.testing.assert_close(points[-guard:, :, 2], before[-guard:, :, 2], atol=0, rtol=0)
    if method == "mirror_z":
        paired = points.flip((0,))
        expected = torch.stack((points[..., 0], points[..., 1], 44 - points[..., 2]), dim=-1)
    else:
        paired = torch.roll(points.flip((0, 1)), -1, 1)
        expected = torch.stack((points[..., 0], 6 - points[..., 1], 44 - points[..., 2]), dim=-1)
    torch.testing.assert_close(paired, expected)
    projected = surface.control_points.clone()
    surface.apply_constraints()
    torch.testing.assert_close(surface.control_points, projected)


@pytest.mark.parametrize("periods", [2, 3, 5])
@pytest.mark.parametrize("degree", [2, 3, 4])
def test_bsp_axial_periods_preserve_ends_and_surface_derivatives(periods, degree):
    surface = BspSurface.initialize_cylinder(
        r0=2, length=40, seed_size=1, degree=degree, num_V_ratio=periods,
        init_location=[2, 3, 7],
    )
    constraint = surface.periodic_z(periods=periods)
    surface.add_constraint(constraint)
    initial = surface.control_points.clone()
    delta = 0.02 * torch.sin(torch.arange(initial.numel())).reshape_as(initial)
    surface.update_variables(delta)
    before = surface.control_points.clone().reshape(*surface.model.size, 3)
    surface.apply_constraints()
    points = surface.control_points.reshape_as(before)
    guard = CONSTANT.KERNEL.SURFACE.FIXED_END_CONTROL_POINT_ROWS
    torch.testing.assert_close(points[:guard], before[:guard], atol=0, rtol=0)
    torch.testing.assert_close(points[-guard:], before[-guard:], atol=0, rtol=0)
    num_v, _num_u = surface.model.size
    count = (num_v - 2 * guard - degree) // periods
    shift = points.new_tensor([0, 0, constraint.period_length])
    block = points[guard:guard + count]
    for step in range(periods):
        start = guard + step * count
        torch.testing.assert_close(points[start:start + count], block + step * shift)
    torch.testing.assert_close(points[-guard - degree:-guard], block[:degree] + periods * shift)

    # The wrapping rows give exactly `periods` full spans in the interior.
    parameter_step = count / (num_v - degree)
    lower = guard / (num_v - degree)
    # Avoid knots: quadratic splines have a discontinuous second derivative.
    uv = points.new_tensor([[lower + 0.237 * parameter_step, 0.17],
                            [lower + 0.673 * parameter_step, 0.63]])

    def evaluate(parameters, derivative):
        weights, indices = surface.model.get_weights(parameters.numpy(), derivative=derivative)
        weights = torch.as_tensor(weights).reshape(len(parameters), -1, 1)
        indices = torch.as_tensor(indices).reshape(len(parameters), -1)
        return (weights * surface.control_points[indices]).sum(dim=1)

    for step in range(1, periods):
        shifted_uv = uv + points.new_tensor([step * parameter_step, 0])
        torch.testing.assert_close(
            surface.map(shifted_uv), surface.map(uv) + step * shift,
            atol=1e-7, rtol=1e-7,
        )
        for derivative in ([1, 0], [2, 0], [0, 1]):
            torch.testing.assert_close(
                evaluate(shifted_uv, derivative), evaluate(uv, derivative),
                atol=1e-6, rtol=1e-6,
            )
    projected = surface.control_points.clone()
    period_length = constraint.period_length
    surface.reinitialize_constraints()
    assert constraint.period_length == period_length
    torch.testing.assert_close(surface.control_points, projected)


@pytest.mark.parametrize("method", ["mirror_z", "antisymmetry_z", "periodic_z"])
def test_bsp_axial_constraints_are_differentiable_with_fixed_ends(method):
    surface = BspSurface.initialize_cylinder(
        r0=2, length=30, seed_size=1, num_V_ratio=2 if method == "periodic_z" else 1,
    )
    surface.add_constraint(getattr(surface, method)())
    initial = surface.control_points.clone()
    weights = torch.linspace(-1, 2, initial.numel()).reshape_as(initial)

    def loss(change):
        surface.control_points = initial
        surface.update_variables(change)
        surface.apply_constraints()
        return (surface.control_points * weights).sum()

    change = torch.zeros_like(initial)
    gradient = torch.func.grad(loss)(change)
    direction = torch.linspace(-0.3, 0.7, initial.numel()).reshape_as(initial)
    difference = (loss(change + 1e-5 * direction) - loss(change - 1e-5 * direction)) / 2e-5
    torch.testing.assert_close((gradient * direction).sum(), difference)
    gradient = gradient.reshape(*surface.model.size, 3)
    guard = CONSTANT.KERNEL.SURFACE.FIXED_END_CONTROL_POINT_ROWS
    torch.testing.assert_close(gradient[[0, -1]], torch.zeros_like(gradient[[0, -1]]))
    torch.testing.assert_close(gradient[:guard, :, 2], torch.zeros_like(gradient[:guard, :, 2]))
    torch.testing.assert_close(gradient[-guard:, :, 2], torch.zeros_like(gradient[-guard:, :, 2]))
    assert gradient.abs().sum() > 0


@pytest.mark.parametrize("periods", [0, 1, -2, 2.5])
def test_bsp_axial_periods_reject_invalid_counts(periods):
    with pytest.raises(ValueError, match="integer of at least 2"):
        BspSurface.periodic_z(periods=periods)


def test_bsp_axial_periods_require_reserved_control_rows():
    surface = cylinder(BspSurface)
    with pytest.raises(ValueError, match="num_V_ratio=periods"):
        surface.add_constraint(surface.periodic_z(periods=2))


@pytest.mark.parametrize("adaptive", [False, True])
@pytest.mark.parametrize("symmetry", ["mirror", "rotate", "mirror_z", "antisymmetry_z", "periodic_z"])
def test_shape_update_enforces_relations_and_inner_solver_is_differentiable(adaptive, symmetry):
    part = BoundaryPart(part_name="body")
    source, target = cylinder(BspSurface, 2.0), cylinder(BspSurface, 0.5)
    if symmetry == "periodic_z":
        source = BspSurface.initialize_cylinder(r0=2, length=4, seed_size=1, num_V_ratio=2)
    kwargs = {"order": 3} if symmetry == "rotate" else {}
    source.add_constraint(getattr(source, symmetry)(**kwargs))
    source.add_constraint(source.relate(target, pose=[0.0, 0.0, 0.0, 0.0, 0.0, math.pi / 2]))
    part.add_surface_interface(source)
    part.add_surface_interface(target)
    part.initialize()
    saved = part.get_parameters()
    updater = UpdaterBoundaryPart(
        max_step_iter=2, max_step_length=0.05,
        update_strategy=strategies.AdaptiveShapeUpdate() if adaptive else None,
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
