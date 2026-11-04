"""Physical curvature models, objective adapters and outer restart persistence."""

from pathlib import Path
from types import SimpleNamespace

import morphopt
import pytest
import torch
from scipy.optimize import BFGS

from morphopt.optcore.controller import Controller
from morphopt.optcore.modelparams import FEAParams, GeometryParams, MaterialsParams, Params
from morphopt.optcore.modelparams.materials import MaterialModels
from morphopt.optcore.objfunc import ObjectiveFunction
from morphopt.optcore.updaters import BaseUpdater, QuadraticHistory, Updaters
from morphopt.shapeopt.boundary_part import BoundaryPart
from morphopt.shapeopt.objectivefuncs import ShapeDerivative, QuadraticShapeDerivative
from morphopt.shapeopt.surfaces.base_surface import BaseSurface
from morphopt.shapeopt.update_boundary_part import UpdaterBoundaryPart
from morphopt.simp.objectivefuncs import Sensitivity, QuadraticSensitivity
from morphopt.simp.simpmaterial import SIMP_BSPFieldMaterials
from morphopt.simp.update_simpmaterial import UpdaterSIMPMaterial


@pytest.fixture(autouse=True)
def double_precision():
    previous = torch.get_default_dtype()
    torch.set_default_dtype(torch.float64)
    yield
    torch.set_default_dtype(previous)


def test_direct_hessian_matches_independent_dense_bfgs():
    model = QuadraticHistory(memory_size=3)
    hessian = torch.tensor([[4.0, 0.4, 0.0], [0.4, 2.0, 0.2], [0.0, 0.2, 3.0]])
    points = [torch.tensor(value) for value in (
        [0.0, 0.0, 0.0], [0.2, 0.1, -0.1], [0.1, -0.2, 0.1],
        [-0.3, 0.1, 0.2], [0.0, 0.2, -0.2], [0.1, 0.3, -0.1],
    )]
    for point in points:
        model.observe(point, hessian @ point)
    assert model.history_size == 3
    retained_steps = [new - old for old, new in zip(points[-4:-1], points[-3:])]
    last = retained_steps[-1]
    change = hessian @ last
    scale = float((change @ change) / (last @ change))
    reference = BFGS(init_scale=scale)
    reference.initialize(3, "hess")
    for step in retained_steps:
        reference.update(step.numpy(), (hessian @ step).numpy())
    actual = torch.stack([model.hessian_product(axis) for axis in torch.eye(3)], dim=1)
    torch.testing.assert_close(actual, torch.tensor(reference.get_matrix()))
    torch.testing.assert_close(actual @ last, hessian @ last)
    assert torch.linalg.eigvalsh(actual).min() > 0
    inverse = torch.stack([
        model.inverse_hessian_product(axis) for axis in torch.eye(3)
    ], dim=1)
    torch.testing.assert_close(inverse, torch.linalg.inv(actual))
    torch.testing.assert_close(inverse @ change, last)
    # Both the automatic gradient and Hessian use B, not B^{-1}.
    trial = points[-1] + torch.tensor([0.02, -0.01, 0.03])
    torch.testing.assert_close(torch.func.jacrev(model)(trial), hessian @ points[-1] + actual @ (trial - points[-1]))
    torch.testing.assert_close(torch.func.hessian(model)(trial), actual)
    assert float(model(points[-1])) == 0.0


def test_first_observation_and_invalid_curvature_stay_linear():
    model = QuadraticHistory()
    model.observe(torch.zeros(2), torch.tensor([1.0, 2.0]))
    trial = torch.tensor([0.1, 0.2])
    torch.testing.assert_close(model.inverse_hessian_product(trial), trial)
    assert model(trial) == pytest.approx(0.5)
    model.observe(torch.zeros(2), torch.tensor([2.0, 3.0]))  # zero step
    model.observe(torch.ones(2), torch.tensor([1.0, 2.0]))  # negative curvature
    model.observe(torch.tensor([2.0, 1.0]), torch.tensor([1.0, 3.0]))  # orthogonal
    assert model.history_size == 0
    torch.testing.assert_close(torch.func.jacrev(model)(trial), torch.tensor([1.0, 3.0]))


def test_layout_change_discards_history_and_bad_observations_fail():
    model = QuadraticHistory()
    model.observe(torch.zeros(2), torch.zeros(2), (2, 1))
    model.observe(torch.ones(2), torch.ones(2), (2, 1))
    assert model.history_size == 1
    model.observe(torch.ones(2), torch.ones(2), (1, 2))
    assert model.history_size == 0
    model.observe(torch.zeros(3), torch.ones(3))
    assert model.point.numel() == 3
    with pytest.raises(ValueError, match="same size"):
        model.observe(torch.zeros(2), torch.zeros(3))
    with pytest.raises(ValueError, match="finite"):
        model.observe(torch.tensor([float("nan")]), torch.ones(1))


@pytest.mark.parametrize("memory_size", [0, -1, 1.5, True])
def test_invalid_memory_size(memory_size):
    with pytest.raises(ValueError, match="positive integer"):
        QuadraticHistory(memory_size)


def test_snapshot_restores_anchor_and_next_secant(tmp_path: Path):
    uninterrupted = QuadraticHistory(2)
    for value in (0.0, 0.2, 0.5):
        point = torch.tensor([value, 2 * value])
        uninterrupted.observe(point, 3 * point)
    path = tmp_path / "history.npz"
    uninterrupted.save(path)
    resumed = QuadraticHistory(2)
    resumed.load(path)
    for model in (uninterrupted, resumed):
        model.observe(torch.tensor([0.7, 1.4]), torch.tensor([2.1, 4.2]))
    assert resumed.history_size == 2
    trial = torch.tensor([0.8, 1.5])
    torch.testing.assert_close(resumed(trial), uninterrupted(trial))
    torch.testing.assert_close(torch.func.jacrev(resumed)(trial), torch.func.jacrev(uninterrupted)(trial))


def test_unobserved_model_checkpoint(tmp_path: Path):
    path = tmp_path / "unused.npz"
    model = QuadraticHistory()
    model.save(path)
    model.observe(torch.ones(2), torch.ones(2))
    model.load(path)
    assert model.point is None
    assert model.history_size == 0
    model.observe(torch.ones(2), torch.ones(2))
    assert model.history_size == 0


def test_material_scaling_does_not_create_artificial_curvature():
    objective = QuadraticSensitivity(normalize_gradient=True)
    first = torch.tensor([0.2, 0.1])
    second = torch.tensor([0.5, 0.2])
    for point in (first, second):
        objective.initialize(gradient=3 * point, cps0=point, step_length=torch.ones(2))
    trial = second + torch.tensor([0.01, 0.02])
    torch.testing.assert_close(
        torch.func.jacrev(objective)(trial), 3 * trial / (3 * second).norm()
    )
    assert objective.history.history_size == 1


class ControlSurface(BaseSurface):
    """Small physical control-coordinate interface for updater integration."""

    def __init__(self, points: torch.Tensor, active: bool = True):
        super().__init__()
        self.points = points.clone()
        self.is_updatable = active

    @property
    def num_variables(self) -> int:
        return self.points.numel()

    def get_surface_parameters(self) -> torch.Tensor:
        return self.points

    @property
    def control_points(self) -> torch.Tensor:
        return self.points

    def get_points_weight(self) -> torch.Tensor:
        return torch.ones(len(self.points))

    def set_surface_parameters(self, values: torch.Tensor) -> None:
        self.points = values.reshape_as(self.points)

    def update_variables(self, x_change: torch.Tensor) -> None:
        self.points = self.points + x_change.reshape_as(self.points)

    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.points, torch.zeros(len(self.points), 3, 2), torch.zeros(len(self.points), 3, 3)


def make_shape_updater() -> UpdaterBoundaryPart:
    part = BoundaryPart()
    part._name = "body"
    part.add_surface_interface(ControlSurface(torch.tensor([[0.2, 0.3, 0.4]])))
    part.add_surface_interface(ControlSurface(torch.tensor([[0.0, 0.0, 1.0]]), active=False))
    updater = UpdaterBoundaryPart(max_step_iter=5, max_step_length=0.05)
    updater.bind_target(part)
    updater.add_objective_function(QuadraticShapeDerivative(memory_size=2))
    updater.initialize()
    return updater


def test_shape_inner_solver_uses_curvature_and_keeps_fixed_surface():
    updater = make_shape_updater()
    active, fixed = updater.surface_interfaces
    # Two high-fidelity observations of J=1.5 * ||theta||^2.
    updater.reinitialize(gradient=3 * torch.cat(updater.part.get_parameters()))
    active.points += 0.01
    updater.reinitialize(gradient=3 * torch.cat(updater.part.get_parameters()))
    objective = next(iter(updater.obj_funcs.values()))
    assert objective.history.history_size == 1
    before = active.points.clone()
    fixed_before = fixed.points.clone()
    trial = updater.part.get_variables().detach().clone()
    loss_before = updater.closure(trial)
    direction = updater.update()
    loss_after = updater.closure(direction)
    assert torch.isfinite(torch.func.jacrev(updater.closure)(direction)).all()
    assert loss_after < loss_before
    assert objective.history.history_size == 1  # inner evaluations never add pairs
    assert updater.optimizer.history is not objective.history
    assert updater.optimizer.history.history_size > 0
    updater.update_variables(direction)
    assert active.points.square().sum() < before.square().sum()
    torch.testing.assert_close(fixed.points, fixed_before)


def test_updater_manager_persists_independent_objective_history(tmp_path: Path):
    updater = make_shape_updater()
    for value in (0.0, 0.01):
        updater.surface_interfaces[0].points += value
        updater.reinitialize(gradient=3 * torch.cat(updater.part.get_parameters()))
    manager = Updaters(updaters={"body": updater})
    manager.save(str(tmp_path), 3)
    restored = make_shape_updater()
    resumed = Updaters(updaters={"body": restored})
    resumed.load(str(tmp_path), 3)
    original_model = next(iter(updater.obj_funcs.values())).history
    restored_model = next(iter(restored.obj_funcs.values())).history
    assert restored_model.history_size == 1
    torch.testing.assert_close(restored_model.point, original_model.point)
    for model in (original_model, restored_model):
        point = model.point + 0.01
        model.observe(point, 3 * point, model._layout)
    probe = original_model.point + 0.02
    torch.testing.assert_close(restored_model(probe), original_model(probe))


def test_default_material_objective_preserves_reciprocal_formula():
    objective = Sensitivity()
    point, gradient, step = torch.tensor([0.2, 0.5]), torch.tensor([2.0, -3.0]), torch.ones(2)
    objective.initialize(gradient=gradient, cps0=point, step_length=step)
    trial = point + torch.tensor([0.1, -0.2])
    expected = (1 / 0.9 - 1) * 2 + (1 / -0.8 + 1) * -3
    assert float(objective(trial)) == pytest.approx(expected)
    torch.testing.assert_close(torch.func.jacrev(objective)(point), gradient)


def test_material_inner_solver_and_restart(tmp_path: Path):
    material = SIMP_BSPFieldMaterials(
        mumax=1.0, kappamax=10.0, simp_ratio_min=0.01,
        bounding_box=[0.0, 2.0, 0.0, 2.0, 0.0, 2.0],
        simp_field_resolution=1.0, degree=1,
        material_parameters=MaterialModels.NeoHookeanLnJParams(mu=1.0, kappa=10.0),
        part_name="body",
    )
    material._name = "solid"
    material.initialize()
    updater = UpdaterSIMPMaterial(max_step_iter=5)
    updater.bind_target(material)
    objective = QuadraticSensitivity(memory_size=2)
    updater.add_objective_function(objective)
    updater.initialize()
    for shift in (0.0, 0.01):
        material._cps += shift
        updater.reinitialize(gradient=3 * material.get_design_values())
    assert objective.history.history_size == 1
    before = material.get_design_values().clone()
    direction = updater.update()
    assert torch.isfinite(direction).all()
    assert updater.closure(direction) < updater.closure(torch.zeros_like(direction))
    updater.update_variables(direction)
    assert material.get_design_values().square().sum() < before.square().sum()
    manager = Updaters(updaters={"solid": updater})
    manager.save(str(tmp_path), 2)
    resumed_objective = QuadraticSensitivity(memory_size=2)
    updater.obj_funcs["QuadraticSensitivity_0"] = resumed_objective
    manager.load(str(tmp_path), 2)
    assert resumed_objective.history.history_size == 1
    torch.testing.assert_close(resumed_objective.history.point, before)


def test_original_objectives_are_independent_of_quadratic_history():
    import inspect

    assert not inspect.signature(ShapeDerivative).parameters
    assert list(inspect.signature(Sensitivity).parameters) == ["normalize_gradient"]
    assert not hasattr(ShapeDerivative(), "history")
    assert not hasattr(Sensitivity(), "history")


def test_shape_first_observation_matches_original_linear_model():
    updater = make_shape_updater()
    quadratic = next(iter(updater.obj_funcs.values()))
    linear = ShapeDerivative()
    surfaces = updater.surface_interfaces
    r, _, _ = updater.part.get_geometry_values()
    gradient = torch.arange(1.0, 7.0)
    for objective in (linear, quadratic):
        objective.initialize(gradient=gradient, r0=r, surfaces=surfaces)
    surfaces[0].points += torch.tensor([[0.01, -0.02, 0.03]])
    torch.testing.assert_close(quadratic(r), linear(r))
    assert quadratic.history.history_size == 0


def test_fea_gradient_reaches_shape_history_without_normalization(monkeypatch):
    """Outer splitting, Part slicing and changing loss scales preserve raw g."""
    updater = make_shape_updater()
    quadratic = next(iter(updater.obj_funcs.values()))
    geometry = GeometryParams()
    leading = BoundaryPart()
    leading.add_surface_interface(ControlSurface(torch.tensor([[1.0, 2.0, 3.0]])))
    geometry.add_interface(leading, name="leading")
    geometry.add_interface(updater.part, name="body")
    params = Params(geometry, FEAParams(), MaterialsParams())
    manager = Updaters(params=params, updaters={"body": updater})
    # Exercise the real reinitialization path without moving the trial design.
    monkeypatch.setattr(updater, "update", lambda: torch.zeros(updater.part.num_variables))
    objective = ObjectiveFunction()
    controller = SimpleNamespace(
        params=params, updater=manager, objfun=objective,
        _detach_recursive=Controller._detach_recursive,
    )
    monkeypatch.setattr(morphopt, "controller", controller)
    first = torch.tensor([120.0, -900.0, 35.0])
    second = torch.tensor([240.0, -600.0, 55.0])
    step = (second - first) / 100000.0
    for index, gradient in enumerate((first, second)):
        if index:
            updater.surface_interfaces[0].points += step.reshape(1, 3)
        raw = torch.cat((torch.tensor([9e6, -7e6, 3e6]), gradient, torch.zeros(3)))
        source = raw.clone()
        solver = SimpleNamespace(get_jacobian_sensitivity_multistep=lambda **kwargs: raw)
        objective.fe = SimpleNamespace(assembly=object(), solver=solver)
        gradients = objective.sensitivity_analysis(params)
        torch.testing.assert_close(gradients["geometry"], source, rtol=0, atol=0)
        manager.update(gradients)
        torch.testing.assert_close(quadratic.history.gradient, gradient, rtol=0, atol=0)
        torch.testing.assert_close(quadratic.gradient[0].flatten(), gradient, rtol=0, atol=0)
        torch.testing.assert_close(raw, source, rtol=0, atol=0)
        assert float(quadratic.factor) == pytest.approx(1 / gradient.abs().max().item())
    assert quadratic.history.history_size == 1
    torch.testing.assert_close(quadratic.history.hessian_product(step), second - first)
    # Scaling applies to the complete model only when the loss is evaluated.
    delta = torch.tensor([0.001, -0.002, 0.003])
    updater.surface_interfaces[0].points += delta.reshape(1, 3)
    expected = second @ delta + 0.5 * (delta @ quadratic.history.hessian_product(delta))
    assert float(quadratic([])) == pytest.approx(float(expected / second.abs().max()))


def test_lbfgs_shared_history_converges_on_rosenbrock():
    def loss(point):
        return (1 - point[0]) ** 2 + 100 * (point[1] - point[0] ** 2) ** 2

    optimizer = BaseUpdater.Optimizer.LBFGS(loss, num_limit=5)
    point = torch.tensor([-1.2, 1.0])
    gradient = None
    for _ in range(150):
        before = float(loss(point))
        alpha, direction, gradient = optimizer.step(point, gradient)
        point = point + alpha * direction
        assert float(loss(point)) <= before + 1e-14
        assert optimizer.history.history_size <= 5
        if float(loss(point)) < 1e-14:
            break
    torch.testing.assert_close(point, torch.ones(2), atol=1e-6, rtol=0)


def test_lbfgs_discards_negative_pairs_and_failed_search(monkeypatch):
    optimizer = BaseUpdater.Optimizer.LBFGS(lambda point: -point.square().sum())
    point = torch.tensor([1.0, 2.0])
    gradient = None
    for _ in range(3):
        alpha, direction, gradient = optimizer.step(point, gradient)
        point = point + alpha * direction
        assert optimizer.history.history_size == 0
        torch.testing.assert_close(optimizer.history.point, point)
    monkeypatch.setattr(
        optimizer, "_LineSearchBacktracking",
        lambda **kwargs: (0.0, kwargs["obj0"]),
    )
    alpha, direction, unchanged_gradient = optimizer.step(point, gradient)
    assert alpha == 0
    assert not direction.any()
    assert optimizer.history.point is None
    torch.testing.assert_close(unchanged_gradient, gradient)


def test_lbfgs_at_stationary_point_has_no_spurious_pair():
    optimizer = BaseUpdater.Optimizer.LBFGS(lambda point: point.square().sum())
    point = torch.zeros(3)
    alpha, direction, gradient = optimizer.step(point)
    assert alpha == 0
    assert not direction.any()
    assert not gradient.any()
    assert optimizer.history.history_size == 0
