"""Surface fairness as an external visitor owned by the geometric penalty."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from functools import partial, singledispatchmethod

import torch

from ...constants import CONSTANT
from ..surfaces.base_surface import BaseSurface
from ..surfaces.bsp_surface import BspSurface
from ..surfaces.cpgeo_surface import CPGEOSurface
from .basefuncs import BaseConstraints

_SETTINGS = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.FAIRNESS
PenaltyEvaluator = Callable[[torch.Tensor, torch.Tensor, torch.Tensor], torch.Tensor]


class Fairness(BaseConstraints):
    """Apply one curvature limit to all updatable boundary surfaces.

    BSP metric variation and nonorthogonality limits remain fixed at 0.1.
    The external visitor keeps type-specific calculations and per-surface
    reference compensation inside this single geometric penalty.
    """

    def __init__(
        self, max_curvature: float = _SETTINGS.CURVATURE_LIMIT,
    ) -> None:
        """Set the shared squared-curvature limit for the boundary Part.

        Args:
            max_curvature (float): Positive upper bound on k1**2 + k2**2, in inverse model length
                squared.

        Raises:
            ValueError: The bound is nonpositive or nonfinite.
        """
        super().__init__()
        if not math.isfinite(max_curvature) or max_curvature <= 0:
            raise ValueError("max_curvature must be finite and positive.")
        self.max_curvature = max_curvature
        self._evaluators: list[tuple[int, PenaltyEvaluator]] = []

    def initialize(
        self,
        r0: list[torch.Tensor],
        rdu0: list[torch.Tensor],
        rdu20: list[torch.Tensor],
        weights: list[torch.Tensor],
        *args: object,
        surfaces: Sequence[BaseSurface],
        **kwargs: object,
    ) -> None:
        """Initialize the Fairness state.

        Args:
            r0 (list[torch.Tensor]): Reference Cartesian surface samples, with one (num_points, 3)
                block per surface.
            rdu0 (list[torch.Tensor]): Reference first derivatives with one surface block of shape
                (num_points, 3, 2).
            rdu20 (list[torch.Tensor]): Reference second derivatives with one surface block of shape
                (num_points, 3, 2, 2).
            weights (list[torch.Tensor]): Integration, basis, or rational weights aligned with the
                corresponding points.
            surfaces (Sequence[BaseSurface]): Surface interfaces in boundary registration order:
                exterior first, followed by cavities.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """
        super().initialize(r0, rdu0, rdu20, weights, *args, surfaces=surfaces, **kwargs)
        with torch.no_grad():
            self._evaluators = [
                (index, self.visit(surface, rdu0[index], rdu20[index]))
                for index, surface in enumerate(self.surfaces) if surface.is_updatable
            ]

    def __call__(
        self,
        r: list[torch.Tensor],
        rdu: list[torch.Tensor],
        rdu2: list[torch.Tensor],
        *args: object,
        **kwargs: object,
    ) -> torch.Tensor:
        """Evaluate Fairness for the supplied inputs.

        Args:
            r (list[torch.Tensor]): Current Cartesian surface samples; each surface block has shape
                (num_points, 3).
            rdu (list[torch.Tensor]): Current first surface derivatives; each block has shape
                (num_points, 3, 2).
            rdu2 (list[torch.Tensor]): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: Integrated curvature and supported surface-regularity penalties for the
                current geometry.
        """
        if not self.surfaces:
            raise ValueError("Surface fairness must be initialized with the owning Part's surfaces.")
        return sum(
            (evaluate(self.integration_weights[index], rdu[index], rdu2[index])
             for index, evaluate in self._evaluators),
            r[0].new_zeros(()),
        )

    @singledispatchmethod
    def visit(
        self, surface: BaseSurface, rdu: torch.Tensor, rdu2: torch.Tensor,
    ) -> PenaltyEvaluator:
        """Bind an external surface evaluator; unsupported surfaces add zero.

        Args:
            surface (BaseSurface): Surface interface to register, evaluate, or constrain.
            rdu (torch.Tensor): Current first surface derivatives; each block has shape (num_points,
                3, 2).
            rdu2 (torch.Tensor): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).

        Returns:
            PenaltyEvaluator: Bind an external surface evaluator; unsupported surfaces add zero.
        """
        return self._zero

    @visit.register
    def _visit_bsp(
        self, surface: BspSurface, rdu: torch.Tensor, rdu2: torch.Tensor,
    ) -> PenaltyEvaluator:
        """Bind the BSP evaluator with fixed compensation from the reference parameterization.

        Args:
            surface (BspSurface): Surface interface to register, evaluate, or constrain.
            rdu (torch.Tensor): Current first surface derivatives; each block has shape (num_points,
                3, 2).
            rdu2 (torch.Tensor): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).

        Returns:
            PenaltyEvaluator: Callable accepting sample weights, first derivatives, and second
                derivatives for this BSP surface.
        """
        measures = self._bsp_measures(rdu, rdu2)[2]
        lengths = measures.new_tensor([
            (2 * surface.model.size[0] * surface.init_size) ** 2,
            (2 * surface.model.size[1] * surface.init_size) ** 2,
        ])[[0, 1, 0, 1], None]
        relative = measures / lengths
        bound = _SETTINGS.METRIC_VARIATION_LIMIT * _SETTINGS.REFERENCE_METRIC_RATIO
        active = relative > bound
        compensation = torch.where(
            active, bound / relative.clamp_min(torch.finfo(relative.dtype).tiny), 1.0,
        ) / lengths
        # Retain the established extra reference-length factor on cross/v terms.
        compensation[1:] = torch.where(
            active[1:], compensation[1:] / lengths[1:], compensation[1:],
        )
        return partial(self._bsp_penalty, compensation=compensation.detach())

    @visit.register
    def _visit_cpgeo(
        self, surface: CPGEOSurface, rdu: torch.Tensor, rdu2: torch.Tensor,
    ) -> PenaltyEvaluator:
        """Select the curvature-only evaluator for a CPGEO surface.

        Args:
            surface (CPGEOSurface): Surface interface to register, evaluate, or constrain.
            rdu (torch.Tensor): Current first surface derivatives; each block has shape (num_points,
                3, 2).
            rdu2 (torch.Tensor): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).

        Returns:
            PenaltyEvaluator: Callable accepting sample weights, first derivatives, and second
                derivatives for this CPGEO surface.
        """
        return self._cpgeo_penalty

    @staticmethod
    def _zero(weight: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor) -> torch.Tensor:
        """Provide a zero penalty for unsupported surface types.

        Args:
            weight (torch.Tensor): Per-sample area integration weights, including any installed
                pointwise penalty weighting.
            rdu (torch.Tensor): Current first surface derivatives; each block has shape (num_points,
                3, 2).
            rdu2 (torch.Tensor): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).

        Returns:
            torch.Tensor: Scalar zero on the supplied weight tensor's dtype and device.
        """
        return weight.new_zeros(())

    def _integrate(
        self, values: torch.Tensor, limit: float, power: int, weight: torch.Tensor,
    ) -> torch.Tensor:
        """Integrate the active polynomial barrier values using the supplied area weights.

        Args:
            values (torch.Tensor): Values aligned with the parameters or records processed by this
                interface.
            limit (float): Upper bound or constraint limit used by the selected operation.
            power (int): Exponent used by the polynomial penalty.
            weight (torch.Tensor): Per-sample area integration weights, including any installed
                pointwise penalty weighting.

        Returns:
            torch.Tensor: Scalar weighted sum over samples in the barrier activation region.
        """
        indices, penalty = self.barrier_function(values, limit, _SETTINGS.ACTIVATION_RATIO, power)
        return (weight[indices] * penalty).sum()

    @staticmethod
    def _curvature_and_metric(
        rdu: torch.Tensor, rdu2: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Compute the sum of squared principal curvatures and the surface metric.

        Args:
            rdu (torch.Tensor): Current first surface derivatives; each block has shape (num_points,
                3, 2).
            rdu2 (torch.Tensor): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).

        Returns:
            tuple[torch.Tensor, torch.Tensor]: Pair (k1**2 + k2**2, metric) with shapes (N,) and (N,
                2, 2); squared curvature has inverse-length-squared units.
        """
        normal = torch.cross(rdu[:, :, 1], rdu[:, :, 0], dim=1)
        normal = normal / normal.norm(dim=1, keepdim=True)
        metric = torch.einsum("pim,pin->pmn", rdu, rdu)
        second = torch.einsum("pimn,pi->pmn", rdu2, normal)
        mean = 0.5 * (metric.inverse() * second).sum((1, 2))
        gaussian = torch.linalg.det(second) / torch.linalg.det(metric)
        return 4 * mean.square() - 2 * gaussian, metric

    @classmethod
    def _bsp_measures(
        cls, rdu: torch.Tensor, rdu2: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Compute BSP curvature, tangent nonorthogonality, and relative metric derivatives.

        Args:
            rdu (torch.Tensor): Current first surface derivatives; each block has shape (num_points,
                3, 2).
            rdu2 (torch.Tensor): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).

        Returns:
            tuple[torch.Tensor, torch.Tensor, torch.Tensor]: Curvature (N,), squared tangent cosine
                (N,), and four squared metric-variation arrays (4, N).
        """
        curvature, metric = cls._curvature_and_metric(rdu, rdu2)
        e, g = metric[:, 0, 0], metric[:, 1, 1]
        nonorthogonality = metric[:, 0, 1] * metric[:, 1, 0] / g / e
        derivative = (
            torch.einsum("piuw,piv->puvw", rdu2, rdu)
            + torch.einsum("piu,pivw->puvw", rdu, rdu2)
        )
        variation = torch.stack([
            derivative[:, 0, 0, 0].square() / e.square(),
            derivative[:, 0, 0, 1].square() / e.square(),
            derivative[:, 1, 1, 0].square() / g.square(),
            derivative[:, 1, 1, 1].square() / g.square(),
        ])
        return curvature, nonorthogonality, variation

    def _bsp_penalty(
        self, weight: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor,
        *, compensation: torch.Tensor,
    ) -> torch.Tensor:
        """Integrate BSP curvature and parameterization penalties with reference compensation.

        Args:
            weight (torch.Tensor): Per-sample area integration weights, including any installed
                pointwise penalty weighting.
            rdu (torch.Tensor): Current first surface derivatives; each block has shape (num_points,
                3, 2).
            rdu2 (torch.Tensor): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).
            compensation (torch.Tensor): Reference-geometry compensation applied to the monitored
                surface quantity.

        Returns:
            torch.Tensor: Scalar sum of squared-curvature, nonorthogonality, and compensated
                metric-variation barriers.
        """
        curvature, nonorthogonality, variation = self._bsp_measures(rdu, rdu2)
        power = _SETTINGS.BSP_EXPONENT
        return (
            self._integrate(curvature, self.max_curvature, power, weight)
            + self._integrate(nonorthogonality, _SETTINGS.NONORTHOGONALITY_LIMIT, power, weight)
            + sum(self._integrate(value, _SETTINGS.METRIC_VARIATION_LIMIT, power, weight)
                  for value in variation * compensation)
        )

    def _cpgeo_penalty(
        self, weight: torch.Tensor, rdu: torch.Tensor, rdu2: torch.Tensor,
    ) -> torch.Tensor:
        """Integrate the squared-curvature barrier for a CPGEO boundary.

        Args:
            weight (torch.Tensor): Per-sample area integration weights, including any installed
                pointwise penalty weighting.
            rdu (torch.Tensor): Current first surface derivatives; each block has shape (num_points,
                3, 2).
            rdu2 (torch.Tensor): Current second surface derivatives; each block has shape
                (num_points, 3, 2, 2).

        Returns:
            torch.Tensor: Scalar area-weighted squared-curvature penalty.
        """
        curvature, _ = self._curvature_and_metric(rdu, rdu2)
        return self._integrate(curvature, self.max_curvature, _SETTINGS.CPGEO_EXPONENT, weight)
