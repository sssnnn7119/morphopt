"""Control-point surface implementation shared by BSP and CPGEO."""

from __future__ import annotations

import numpy as np

from morphopt._torch import torch

from .base import BaseSurfaceInterface
from .preload import PreLoadData


class CpBasedSurface(BaseSurfaceInterface):
    """Evaluate a surface from a frozen sparse control-point mapping."""

    def __init__(self, name: str = "", control_points: torch.Tensor | None = None) -> None:
        super().__init__(name)
        self._control_points = torch.as_tensor(
            control_points if control_points is not None else torch.zeros((0, 3))
        ).detach().clone()
        """Committed control-point positions in stable backend order."""
        self._preload_data: PreLoadData | None = None
        """Frozen sample-to-control-point interpolation mapping."""

    def get_surface_parameters(self) -> torch.Tensor:
        """Read a detached control-point snapshot."""
        return self._control_points.detach().clone()

    def set_surface_parameters(self, parameters: torch.Tensor) -> None:
        """Replace committed control points with a detached clone."""
        values = torch.as_tensor(parameters)
        if values.shape != self._control_points.shape:
            raise ValueError(
                f"Surface '{self.name}' expected control-point shape "
                f"{tuple(self._control_points.shape)}, got {tuple(values.shape)}"
            )
        self._control_points = values.detach().clone()
        self.update_backend()
        if self._preload_data is not None:
            self.update_geometry()

    def build_preload(self, points: torch.Tensor, faces: torch.Tensor) -> None:
        """Build a one-to-one preload mapping for a control mesh."""
        points = torch.as_tensor(points, dtype=self._control_points.dtype)
        faces = torch.as_tensor(faces, dtype=torch.long)
        point_count = int(points.shape[0])
        if point_count != int(self._control_points.shape[0]):
            raise ValueError(
                "The default preload requires one sample point per control point"
            )
        index = torch.arange(point_count, dtype=torch.long, device=points.device)
        first_weights = torch.zeros((point_count, 2), dtype=points.dtype)
        second_weights = torch.zeros((point_count, 2, 2), dtype=points.dtype)
        self._preload_data = PreLoadData(
            parameters=points,
            control_point_indices=torch.stack((index, index)),
            position_weights=torch.ones(point_count, dtype=points.dtype),
            first_derivative_weights=first_weights,
            second_derivative_weights=second_weights,
            faces=faces,
        )
        self._sample_parameters = points.detach().clone()

    def get_preload_data(self) -> PreLoadData:
        """Read the established parameter-mapping cache."""
        if self._preload_data is None:
            raise RuntimeError(f"Surface '{self.name}' has no preload cache")
        return self._preload_data

    def set_preload_data(self, preload_data: PreLoadData) -> None:
        """Replace the parameter-mapping cache supplied by a concrete backend."""
        self._preload_data = preload_data
        self._sample_parameters = preload_data.parameters.detach().clone()

    def get_control_points_list(self) -> tuple[torch.Tensor, ...]:
        """Read this surface's single control-point tensor."""
        return (self._control_points,)

    def update_backend(self) -> None:
        """Synchronize committed control points into the concrete backend."""
        return None

    def update_geometry(self, parameters: torch.Tensor | None = None) -> None:
        """Evaluate committed or trial control points through the preload cache."""
        control_points = (
            self._control_points
            if parameters is None
            else torch.as_tensor(parameters, dtype=self._control_points.dtype)
        )
        if self._preload_data is None:
            raise RuntimeError(f"Surface '{self.name}' has no preload cache")
        coordinates, first_derivatives, second_derivatives = self._evaluate_control_points(
            control_points, self._preload_data
        )
        if self._flip:
            first_derivatives = first_derivatives.clone()
            second_derivatives = second_derivatives.clone()
            first_derivatives[..., 1] = -first_derivatives[..., 1]
            second_derivatives[..., 0, 1] = -second_derivatives[..., 0, 1]
            second_derivatives[..., 1, 0] = -second_derivatives[..., 1, 0]
        from .base import SurfaceGeometryData

        self._geometry_data = SurfaceGeometryData(
            coordinates=coordinates,
            first_derivative_u=first_derivatives[..., 0],
            first_derivative_v=first_derivatives[..., 1],
            second_derivative_uu=second_derivatives[..., 0, 0],
            second_derivative_uv=second_derivatives[..., 0, 1],
            second_derivative_vv=second_derivatives[..., 1, 1],
        )
        self._points_weight = self._preload_data.compute_point_weights(coordinates)
        self._preview_meshes = ()

    def map(self, parameters: torch.Tensor) -> torch.Tensor:
        """Map sample parameters using the concrete backend evaluator."""
        return self._evaluate_raw(torch.as_tensor(parameters))[0]

    def _evaluate_control_points(
        self, control_points: torch.Tensor, preload_data: PreLoadData
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Apply sparse interpolation weights to positions and derivatives."""
        point_count = preload_data.get_num_points()
        device = control_points.device
        dtype = control_points.dtype
        mapping = preload_data.to_device(str(device))
        sample_indices = mapping.control_point_indices[0].to(dtype=torch.long)
        control_indices = mapping.control_point_indices[1].to(dtype=torch.long)
        selected = control_points[control_indices]
        coordinates = torch.zeros((point_count, 3), dtype=dtype, device=device)
        coordinates.index_add_(
            0, sample_indices, selected * mapping.position_weights[:, None]
        )
        first_derivatives = torch.zeros(
            (point_count, 3, 2), dtype=dtype, device=device
        )
        second_derivatives = torch.zeros(
            (point_count, 3, 2, 2), dtype=dtype, device=device
        )
        for direction in range(2):
            values = selected * mapping.first_derivative_weights[:, direction, None]
            first_derivatives[..., direction].index_add_(0, sample_indices, values)
        for first_direction in range(2):
            for second_direction in range(2):
                values = selected * mapping.second_derivative_weights[
                    :, first_direction, second_direction, None
                ]
                second_derivatives[..., first_direction, second_direction].index_add_(
                    0, sample_indices, values
                )
        return coordinates, first_derivatives, second_derivatives

    def _evaluate_raw(
        self, parameters: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Use nearest cached sample values for generic control-point surfaces."""
        preload_data = self.get_preload_data()
        coordinates, first_derivatives, second_derivatives = self._evaluate_control_points(
            self._control_points, preload_data
        )
        query = torch.as_tensor(parameters, dtype=preload_data.parameters.dtype)
        samples = preload_data.parameters
        distance = torch.cdist(query.reshape(-1, samples.shape[-1]), samples)
        indices = distance.argmin(dim=1)
        return (
            coordinates[indices],
            first_derivatives[indices],
            second_derivatives[indices],
        )

    @staticmethod
    def _create_poly_data(points: torch.Tensor, faces: torch.Tensor):
        """Create a PyVista triangular mesh from Torch tensors."""
        points_array = points.detach().cpu().numpy()
        faces_array = faces.detach().cpu().numpy().astype(np.int64, copy=False)
        packed_faces = np.column_stack(
            (np.full(faces_array.shape[0], 3, dtype=np.int64), faces_array)
        ).reshape(-1)
        return __import__("pyvista").PolyData(points_array, packed_faces)
