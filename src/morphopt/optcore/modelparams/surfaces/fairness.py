"""Per-surface geometric fairness evaluators."""

from __future__ import annotations

from morphopt._torch import torch

from .base import SurfaceGeometryData


class FairnessEvaluator:
    """Base continuous barrier evaluator for one editable surface."""

    def __init__(
        self,
        *,
        maximum_curvature: float = 1.0,
        maximum_fairness_factor: float = 0.2,
    ) -> None:
        self._maximum_curvature = float(maximum_curvature)
        """Upper bound for curvature magnitude."""
        self._maximum_fairness_factor = float(maximum_fairness_factor)
        """Upper bound for normalized fairness variation."""
        self._reference_geometry: SurfaceGeometryData | None = None
        """Reference geometry retained for relative fairness evaluation."""

    @property
    def maximum_curvature(self) -> float:
        """Read the curvature limit."""
        return self._maximum_curvature

    @property
    def maximum_fairness_factor(self) -> float:
        """Read the fairness-factor limit."""
        return self._maximum_fairness_factor

    def initialize(
        self, geometry_values: SurfaceGeometryData, point_weights: torch.Tensor
    ) -> None:
        """Store the initial direction-consistent geometry as the reference."""
        del point_weights
        self._reference_geometry = geometry_values

    def reinitialize(
        self,
        iteration: int,
        geometry_values: SurfaceGeometryData,
        point_weights: torch.Tensor,
    ) -> None:
        """Refresh reference data only when topology-dependent samples changed."""
        del iteration, point_weights
        if self._reference_geometry is None:
            self._reference_geometry = geometry_values

    def compute_fairness(
        self, geometry_values: SurfaceGeometryData, point_weights: torch.Tensor
    ) -> torch.Tensor:
        """Compute a differentiable curvature/fairness barrier scalar."""
        curvature = self._compute_curvature(geometry_values)
        curvature_penalty = self._compute_barrier(
            curvature.abs(), self._maximum_curvature
        )
        if self._reference_geometry is None:
            reference = curvature.detach()
        else:
            reference = self._compute_curvature(self._reference_geometry).detach()
        denominator = torch.clamp(reference.abs(), min=1e-12)
        fairness_factor = (curvature - reference).abs() / denominator
        fairness_penalty = self._compute_barrier(
            fairness_factor, self._maximum_fairness_factor
        )
        return (point_weights * (curvature_penalty + fairness_penalty)).sum()

    def _compute_curvature(self, geometry_values: SurfaceGeometryData) -> torch.Tensor:
        """Estimate mean curvature from first and second fundamental forms."""
        first_u = geometry_values.first_derivative_u
        first_v = geometry_values.first_derivative_v
        normal = torch.linalg.cross(first_v, first_u)
        normal = normal / torch.clamp(
            torch.linalg.vector_norm(normal, dim=-1, keepdim=True),
            min=torch.finfo(normal.dtype).eps,
        )
        first_form_uu = (first_u * first_u).sum(dim=-1)
        first_form_uv = (first_u * first_v).sum(dim=-1)
        first_form_vv = (first_v * first_v).sum(dim=-1)
        second_form_uu = (geometry_values.second_derivative_uu * normal).sum(dim=-1)
        second_form_uv = (geometry_values.second_derivative_uv * normal).sum(dim=-1)
        second_form_vv = (geometry_values.second_derivative_vv * normal).sum(dim=-1)
        denominator = torch.clamp(
            first_form_uu * first_form_vv - first_form_uv.square(), min=1e-12
        )
        return (
            first_form_uu * second_form_vv
            - 2.0 * first_form_uv * second_form_uv
            + first_form_vv * second_form_uu
        ) / (2.0 * denominator)

    @staticmethod
    def _compute_barrier(values: torch.Tensor, limit: float) -> torch.Tensor:
        """Return zero below 80% of a limit and smooth growth above it."""
        threshold = 0.8 * float(limit)
        scaled = torch.relu((values - threshold) / max(float(limit) - threshold, 1e-12))
        return scaled.square()


class BSPFairnessEvaluator(FairnessEvaluator):
    """BSP evaluator with an additional curvature-radius-change threshold."""

    def __init__(
        self,
        *,
        maximum_radius_change: float = 0.2,
        maximum_curvature: float = 1.0,
        maximum_fairness_factor: float = 0.2,
    ) -> None:
        super().__init__(
            maximum_curvature=maximum_curvature,
            maximum_fairness_factor=maximum_fairness_factor,
        )
        self._maximum_radius_change = float(maximum_radius_change)
        """Maximum relative curvature-radius change."""
        self._rr_compensation: torch.Tensor | None = None
        """Reference curvature-radius factor cached at initialization."""

    @property
    def maximum_radius_change(self) -> float:
        """Read the curvature-radius change limit."""
        return self._maximum_radius_change

    def initialize(
        self, geometry_values: SurfaceGeometryData, point_weights: torch.Tensor
    ) -> None:
        """Store reference geometry and its curvature radius."""
        super().initialize(geometry_values, point_weights)
        curvature = self._compute_curvature(geometry_values).detach()
        self._rr_compensation = 1.0 / torch.clamp(curvature.abs(), min=1e-12)

    def compute_fairness(
        self, geometry_values: SurfaceGeometryData, point_weights: torch.Tensor
    ) -> torch.Tensor:
        """Add a curvature-radius-change barrier to the common fairness term."""
        value = super().compute_fairness(geometry_values, point_weights)
        curvature = self._compute_curvature(geometry_values)
        radius = 1.0 / torch.clamp(curvature.abs(), min=1e-12)
        reference_radius = (
            radius.detach() if self._rr_compensation is None else self._rr_compensation
        )
        change = (radius - reference_radius).abs() / torch.clamp(
            reference_radius.abs(), min=1e-12
        )
        return value + (
            point_weights
            * self._compute_barrier(change, self._maximum_radius_change)
        ).sum()


class CPGEOFairnessEvaluator(FairnessEvaluator):
    """CPGEO evaluator using the common discrete geometry representation."""
