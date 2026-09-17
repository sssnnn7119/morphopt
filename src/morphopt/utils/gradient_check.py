"""Finite-difference gradient checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from morphopt._torch import torch
from morphopt.optcore.controller import Controller


@dataclass(frozen=True, slots=True)
class GradientCheckResult:
    analytical: torch.Tensor
    numerical: torch.Tensor
    absolute_error: torch.Tensor
    relative_error: torch.Tensor


GradientCheckReport = GradientCheckResult
GradientCheckEntry = GradientCheckResult


@dataclass(frozen=True, slots=True)
class GradientCheckOptions:
    epsilon: float = 1e-6
    maximum_variables: int | None = None


def check_gradient(function: Callable[[torch.Tensor], torch.Tensor], values: torch.Tensor, epsilon: float = 1e-6) -> GradientCheckResult:
    point = values.detach().clone().requires_grad_(True)
    output = function(point)
    analytical = torch.autograd.grad(output, point)[0].detach()
    numerical = torch.zeros_like(point)
    flat = numerical.reshape(-1)
    source = point.detach().reshape(-1)
    for index in range(source.numel()):
        plus = source.clone(); plus[index] += epsilon
        minus = source.clone(); minus[index] -= epsilon
        flat[index] = (function(plus.reshape_as(point)).detach() - function(minus.reshape_as(point)).detach()) / (2 * epsilon)
    absolute = (analytical - numerical).abs()
    relative = absolute / analytical.abs().clamp_min(1e-12)
    return GradientCheckResult(analytical, numerical, absolute, relative)


def check_gradients(controller: Controller, options: GradientCheckOptions | None = None) -> GradientCheckReport:
    """Run the controller's future gradient-check hook.

    The concrete TorchFEA finite-difference workflow is a TODO; returning a
    structured zero report keeps CI and UI integrations callable now.
    """

    options = options or GradientCheckOptions()
    # TODO: Sample DesignRegistry blocks and compare implicit sensitivities.
    from morphopt._torch import torch

    zero = torch.zeros(0)
    return GradientCheckReport(zero, zero, zero, zero)
