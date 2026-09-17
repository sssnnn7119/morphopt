"""Frozen control-point to sample-point mapping data."""

from __future__ import annotations

from dataclasses import dataclass

from morphopt._torch import torch


@dataclass(frozen=True, slots=True)
class PreLoadData:
    """Reusable sparse control-point evaluation mapping.

    Every row in `control_point_indices` contains the control-point index
    used by the corresponding row in the weight tensors.  The first index is
    the sample-point index, making `index_add_` evaluation differentiable.
    """

    parameters: torch.Tensor
    control_point_indices: torch.Tensor
    position_weights: torch.Tensor
    first_derivative_weights: torch.Tensor
    second_derivative_weights: torch.Tensor
    faces: torch.Tensor

    def get_num_points(self) -> int:
        """Return the number of sample points."""
        return int(self.parameters.shape[0])

    def to_device(self, device: str) -> PreLoadData:
        """Return an equivalent record with every tensor on `device`."""
        return PreLoadData(
            parameters=self.parameters.to(device),
            control_point_indices=self.control_point_indices.to(device),
            position_weights=self.position_weights.to(device),
            first_derivative_weights=self.first_derivative_weights.to(device),
            second_derivative_weights=self.second_derivative_weights.to(device),
            faces=self.faces.to(device),
        )

    def compute_point_weights(self, points: torch.Tensor) -> torch.Tensor:
        """Compute one-third triangle-area weights at every sampled point."""
        if self.faces.numel() == 0:
            return torch.ones(
                points.shape[0], dtype=points.dtype, device=points.device
            )
        triangles = points[self.faces.to(device=points.device, dtype=torch.long)]
        triangle_area = 0.5 * torch.linalg.vector_norm(
            torch.linalg.cross(
                triangles[:, 1] - triangles[:, 0],
                triangles[:, 2] - triangles[:, 0],
            ),
            dim=-1,
        )
        weights = torch.zeros(
            points.shape[0], dtype=points.dtype, device=points.device
        )
        weights.index_add_(
            0,
            self.faces.reshape(-1).to(device=points.device, dtype=torch.long),
            triangle_area.repeat_interleave(3) / 3.0,
        )
        return weights


SurfacePreload = PreLoadData
