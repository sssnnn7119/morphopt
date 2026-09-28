"""Force-profile objective checks; no nonlinear FE solve is launched."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch


@pytest.fixture
def case():
    path = Path(__file__).resolve().parents[2] / "examples/force_regulating_gripper.py"
    spec = importlib.util.spec_from_file_location("force_gripper_objective_case", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(case, forces):
    objective = SimpleNamespace(get_force_displacement=lambda i: (forces[i], None))
    return case.ThisController.ObjectiveFunction.objective_function(objective)


def reference(case):
    return case._target_force_at_closure(torch.tensor(case.closure_steps, dtype=torch.float64))


@pytest.mark.parametrize("join", [0.0, 1.0])
def test_transition_has_three_continuous_derivatives_at_joins(case, join):
    x = torch.tensor(join, dtype=torch.float64, requires_grad=True)
    derivative = case._smoothstep_c3(x)
    assert derivative.item() == pytest.approx(join)
    for _ in range(3):
        derivative = torch.autograd.grad(derivative, x, create_graph=True)[0]
        assert derivative.item() == pytest.approx(0.0, abs=1e-12)
    # The third derivative also approaches the constant exterior derivative.
    inside = torch.tensor(
        1e-8 if join == 0 else 1.0 - 1e-8, dtype=torch.float64, requires_grad=True
    )
    derivative = case._smoothstep_c3(inside)
    for _ in range(3):
        derivative = torch.autograd.grad(derivative, inside, create_graph=True)[0]
    assert abs(derivative.item()) < 1e-5


def test_reference_is_monotone_with_exact_zero_and_plateau(case):
    gap = (case.initial_gap - case.object_diameter) / 2
    sample = torch.tensor(
        [
            0.0,
            gap,
            (gap + case.force_ramp_end) / 2,
            case.force_ramp_end,
            case.closure_steps[-1],
        ],
        dtype=torch.float64,
    )
    expected = sample.new_tensor([0, 0, 0.5, 1, 1]) * case.target_force
    torch.testing.assert_close(case._target_force_at_closure(sample), expected)
    dense = torch.linspace(0.0, case.closure_steps[-1], 1001, dtype=torch.float64)
    assert torch.all(torch.diff(case._target_force_at_closure(dense)) >= -1e-13)


def test_reference_minimizes_loss_and_every_step_contributes(case):
    target = reference(case)
    assert evaluate(case, target).item() == pytest.approx(0.0, abs=1e-25)
    assert evaluate(case, torch.zeros_like(target)).item() >= 1.0
    for i in range(len(target)):
        perturbed = target.clone()
        perturbed[i] += 0.1 * case.target_force
        assert evaluate(case, perturbed).item() > 0.0


def test_flatness_distinguishes_ripple_from_equal_force_error(case):
    target = reference(case)
    _, start = case._force_objective_grid()
    offset = 0.1 * case.target_force
    biased = target.clone()
    biased[start:] += offset
    ripple = biased.clone()
    ripple[start + 1 :: 2] -= 2 * offset
    biased_terms = case._force_objective_terms(biased)
    ripple_terms = case._force_objective_terms(ripple)
    torch.testing.assert_close(biased_terms[0], ripple_terms[0])
    torch.testing.assert_close(biased_terms[2], ripple_terms[2])
    assert biased_terms[1].item() == pytest.approx(0.0)
    assert ripple_terms[1].item() > 0.0
    assert evaluate(case, ripple) > evaluate(case, biased)


def test_nonuniform_grid_uses_displacement_weights(case, monkeypatch):
    results = []
    for grid in [list(np.linspace(0, 20, 21)), [0, 1, 4, 7, 10, 10.2, 13, 19, 20]]:
        monkeypatch.setattr(case, "closure_steps", grid)
        target = reference(case)
        results.append(evaluate(case, target + 0.1 * case.target_force))
        displacement = torch.tensor(grid, dtype=torch.float64)
        slope_value = case._force_objective_terms(0.2 * displacement)[1]
        expected = (0.2 * (grid[-1] - case.force_ramp_end) / case.target_force) ** 2
        assert slope_value.item() == pytest.approx(expected)
    torch.testing.assert_close(results[0], results[1])


def test_force_objective_gradients_and_three_derivatives(case):
    target = reference(case)
    direction = torch.linspace(-0.3, 0.5, len(target), dtype=torch.float64)
    forces = (target + direction).requires_grad_()
    loss = lambda values: evaluate(case, values)
    assert torch.autograd.gradcheck(loss, (forces,))
    assert torch.autograd.gradgradcheck(loss, (forces,))
    # A smooth surrogate response gives a nontrivial third derivative:
    # F(t) = reference + sin(t) * direction, so J(t) = coefficient * sin(t)^2.
    coefficient = evaluate(case, target + direction).detach()
    t = torch.tensor(0.17, dtype=torch.float64, requires_grad=True)
    derivative = evaluate(case, target + t.sin() * direction)
    expected = [
        coefficient * (2 * t).sin(),
        2 * coefficient * (2 * t).cos(),
        -4 * coefficient * (2 * t).sin(),
    ]
    for value in expected:
        derivative = torch.autograd.grad(derivative, t, create_graph=True)[0]
        torch.testing.assert_close(derivative, value)


def test_volume_equality_has_correct_hessian_and_third_derivative(case):
    volume = case.volume_fraction_max
    q = torch.tensor(np.log(volume / (1 - volume)), dtype=torch.float64, requires_grad=True)
    constraint = case.ThisController.Updater.UpdaterSIMPMaterial.VolumeFractionTarget(
        volfrac_min=volume, volfrac_max=volume, penalty=1e6, elementname="design"
    )
    constraint.gaussian_points = torch.zeros((2, 3), dtype=torch.float64)
    constraint.gaussian_weights = torch.tensor([1.0, 2.0], dtype=torch.float64)
    constraint._indices = (
        torch.tensor([0, 1], dtype=torch.long),
        torch.tensor([0, 0], dtype=torch.long),
    )
    constraint._weights = torch.ones(2, dtype=torch.float64)
    material = SimpleNamespace(_cps=torch.zeros((1, 1), dtype=torch.float64))
    constraint._material_interface = material
    loss = constraint(cps=q, material_params=material)
    first = torch.autograd.grad(loss, q, create_graph=True)[0]
    second = torch.autograd.grad(first, q, create_graph=True)[0]
    third = torch.autograd.grad(second, q)[0]
    drho = volume * (1 - volume)
    ddrho = drho * (1 - 2 * volume)
    assert first.item() == pytest.approx(0.0, abs=1e-9)
    assert second.item() == pytest.approx(2e6 * drho**2)
    assert third.item() == pytest.approx(6e6 * drho * ddrho)
    transformed_gradient = torch.func.grad(
        lambda value: constraint(cps=value, material_params=material)
    )(q.detach().reshape(1))
    assert torch.isfinite(transformed_gradient).all()


def test_symmetric_update_preserves_ad_derivative_at_zero(case):
    shape = [2, 3, 4]
    material = SimpleNamespace(
        _bsp_size=shape, _cps=torch.zeros((np.prod(shape), 1), dtype=torch.float64)
    )
    change = torch.zeros(np.prod(shape), dtype=torch.float64, requires_grad=True)
    update = case.ThisController.Params.BodyMaterial.update_variables
    update(material, change)
    gradient = torch.autograd.grad(material._cps.sum(), change)[0]
    torch.testing.assert_close(gradient, torch.full_like(change, 2 / torch.pi))
    update(material, torch.linspace(-1, 1, change.numel(), dtype=torch.float64))
    field = material._cps.reshape(shape)
    torch.testing.assert_close(field, field.flip(dims=[2]))
    torch.testing.assert_close(field[:, 0], field[:, -1])


def test_registered_bound_penalties_are_c3_at_activation(case):
    updater = case.ThisController.Updater.UpdaterSIMPMaterial()
    updater.define_objective()
    bounds = [item for item in updater.constraints_funcs.values() if hasattr(item, "p")]
    assert len(bounds) == 2
    for bound in bounds:
        minimum = hasattr(bound, "xmin")
        limit = bound.xmin if minimum else bound.xmax
        for offset in [-1e-12, 0.0, 1e-12]:
            x = torch.tensor([limit + offset], dtype=torch.float64, requires_grad=True)
            # Keep a zero-valued graph when a bound is inactive.
            derivative = bound(cps=x).sum() + 0.0 * x.pow(4).sum()
            for _ in range(3):
                derivative = torch.autograd.grad(derivative, x, create_graph=True)[0]
                assert abs(derivative.item()) < 1e-4


@pytest.mark.parametrize("grid", [[0, 4, 9, 11, 20], [0, 4, 10, 10, 20], [0, 4, 10]])
def test_invalid_working_intervals_fail_before_solving(case, monkeypatch, grid):
    monkeypatch.setattr(case, "closure_steps", grid)
    with pytest.raises(ValueError):
        case._force_objective_grid()
