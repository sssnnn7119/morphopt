"""Shared surface lifecycle, geometry-cache and export implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
import pyvista

from morphopt._torch import torch

if TYPE_CHECKING:
    from .fairness import FairnessEvaluator


SurfaceExportFormat = Literal["stp", "stl"]


@dataclass(frozen=True, slots=True)
class SurfaceGeometryData:
    """Cached surface position and parametric derivatives.

    The three tensors returned by :meth:`get_values` use the V3 layout:
    `r` is `(point, xyz)`, `rdu` is `(point, xyz, u_or_v)`, and
    `rdu2` is `(point, xyz, u_or_v, u_or_v)`.
    """

    coordinates: torch.Tensor
    first_derivative_u: torch.Tensor
    first_derivative_v: torch.Tensor
    second_derivative_uu: torch.Tensor
    second_derivative_uv: torch.Tensor
    second_derivative_vv: torch.Tensor

    def get_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Return V3-compatible position, first and second derivative tensors."""
        first_derivatives = torch.stack(
            (self.first_derivative_u, self.first_derivative_v), dim=-1
        )
        second_derivatives = torch.stack(
            (
                torch.stack(
                    (self.second_derivative_uu, self.second_derivative_uv), dim=-1
                ),
                torch.stack(
                    (self.second_derivative_uv, self.second_derivative_vv), dim=-1
                ),
            ),
            dim=-1,
        )
        return self.coordinates, first_derivatives, second_derivatives


class BaseSurfaceInterface:
    """Base implementation for an ordered BoundaryPart surface.

    Concrete surfaces provide :meth:`_evaluate_raw` and
    :meth:`_compute_preview_meshes`.  This class owns orientation handling,
    cache lifecycle, closest-node parameter mapping and file export routing.
    """

    def __init__(self, name: str = "") -> None:
        self._name = str(name)
        """Stable surface name assigned by BoundaryPart registration."""
        self._flip = False
        """Runtime v-parameter orientation selected by BoundaryPart."""
        self._geometry_data: SurfaceGeometryData | None = None
        """Cached position and first/second derivative tensors."""
        self._points_weight: torch.Tensor | None = None
        """Cached per-sample integration weights."""
        self._sample_parameters: torch.Tensor | None = None
        """Cached parameter coordinates used for geometry evaluation."""
        self._surf_node_idx: np.ndarray | None = None
        """Indices of FEA nodes associated with this surface."""
        self._surf_node_uv: np.ndarray | None = None
        """Parameter coordinates associated with the FEA surface nodes."""
        self._preview_meshes: tuple[pyvista.DataSet, ...] = ()
        """Cached visualization meshes."""
        self._initialized = False
        """Whether static surface data and its initial cache exist."""

    @property
    def name(self) -> str:
        """Return the stable surface name."""
        return self._name

    @property
    def geometry_data(self) -> SurfaceGeometryData | None:
        """Return the current geometry cache."""
        return self._geometry_data

    def get_flip(self) -> bool:
        """Read the runtime v-direction orientation."""
        return self._flip

    def get_export_formats(self) -> tuple[SurfaceExportFormat, ...]:
        """Read the formats supported by this concrete surface."""
        return self.supported_export_formats()

    def initialize(self) -> None:
        """Create static backend data and establish the first geometry cache."""
        self._initialize_backend()
        self.update_geometry()
        self._initialized = True

    def reinitialize(self, iteration: int) -> None:
        """Refresh geometry values after committed parameters changed."""
        del iteration
        self.update_geometry()

    def get_geometry_values(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Read cached `r`, `rdu` and `rdu2` without recomputation."""
        if self._geometry_data is None:
            raise RuntimeError(f"Surface '{self._name}' has not been initialized")
        return self._geometry_data.get_values()

    def get_points_weight(self) -> torch.Tensor:
        """Read cached integration weights without recomputation."""
        if self._points_weight is None:
            raise RuntimeError(f"Surface '{self._name}' has not been initialized")
        return self._points_weight

    def get_surface_parameters(self) -> torch.Tensor:
        """Read the concrete surface design parameters."""
        return torch.zeros(0)

    def set_surface_parameters(self, parameters: torch.Tensor) -> None:
        """Replace concrete surface design parameters."""
        del parameters
        raise TypeError(f"{type(self).__name__} has no editable surface parameters")

    def map(self, parameters: torch.Tensor) -> torch.Tensor:
        """Map parameter-domain coordinates to three-dimensional coordinates."""
        return self._evaluate_raw(torch.as_tensor(parameters))[0]

    def compute_normals(self, parameters: torch.Tensor) -> torch.Tensor:
        """Compute unit normals from orientation-correct parametric tangents."""
        _, first_derivatives, _ = self._evaluate_geometry(torch.as_tensor(parameters))
        normals = torch.linalg.cross(first_derivatives[..., 1], first_derivatives[..., 0])
        norm = torch.linalg.vector_norm(normals, dim=-1, keepdim=True)
        return normals / torch.clamp(norm, min=torch.finfo(normals.dtype).eps)

    def match_coordinates(
        self, node_index: np.ndarray, nodes: np.ndarray
    ) -> np.ndarray:
        """Associate supplied FEA nodes with their nearest sample parameters."""
        if self._sample_parameters is None or self._geometry_data is None:
            raise RuntimeError(f"Surface '{self._name}' has not been initialized")
        sample_coordinates = self._geometry_data.coordinates.detach().cpu().numpy()
        query_coordinates = np.asarray(nodes, dtype=float).reshape(-1, 3)
        distance = query_coordinates[:, None, :] - sample_coordinates[None, :, :]
        nearest = np.square(distance).sum(axis=-1).argmin(axis=1)
        self._surf_node_idx = np.asarray(node_index, dtype=int).reshape(-1)
        parameters = self._sample_parameters.detach().cpu().numpy()[nearest]
        self._surf_node_uv = parameters
        return parameters

    def update_geometry(self, parameters: torch.Tensor | None = None) -> None:
        """Recompute and cache geometry data from committed or trial parameters."""
        evaluation_parameters = (
            torch.as_tensor(parameters)
            if parameters is not None
            else self._get_evaluation_parameters()
        )
        coordinates, first_derivatives, second_derivatives = self._evaluate_geometry(
            evaluation_parameters
        )
        self._geometry_data = SurfaceGeometryData(
            coordinates=coordinates,
            first_derivative_u=first_derivatives[..., 0],
            first_derivative_v=first_derivatives[..., 1],
            second_derivative_uu=second_derivatives[..., 0, 0],
            second_derivative_uv=second_derivatives[..., 0, 1],
            second_derivative_vv=second_derivatives[..., 1, 1],
        )
        self._points_weight = self._compute_point_weights(coordinates)
        self._preview_meshes = ()

    def build_meshes(self) -> None:
        """Build and cache visualization meshes for the current geometry."""
        self._preview_meshes = tuple(self._compute_preview_meshes())

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Read already-built visualization meshes."""
        return self._preview_meshes

    def export_surface(
        self, path: str | Path, format: SurfaceExportFormat
    ) -> Path:
        """Export the current surface through its concrete backend."""
        normalized_format = format.lower().lstrip(".")
        if normalized_format not in self.get_export_formats():
            raise ValueError(
                f"{type(self).__name__} supports {self.get_export_formats()}, "
                f"not '{format}'"
            )
        target_path = Path(path).with_suffix(f".{normalized_format}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        return self._export_surface(target_path, normalized_format)

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist portable design parameters and node-parameter associations."""
        folder = Path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
        payload_path = folder / f"{self._name}_{int(iteration):06d}.pt"
        torch.save(
            {
                "parameters": self.get_surface_parameters().detach().cpu(),
                "node_index": self._surf_node_idx,
                "node_parameters": self._surf_node_uv,
            },
            payload_path,
        )

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Restore portable surface state and refresh geometry caches."""
        payload_path = Path(folder_path) / f"{self._name}_{int(iteration):06d}.pt"
        payload = torch.load(payload_path, weights_only=False)
        parameters = torch.as_tensor(payload["parameters"])
        if parameters.numel():
            self.set_surface_parameters(parameters)
        self._surf_node_idx = payload.get("node_index")
        self._surf_node_uv = payload.get("node_parameters")
        self.update_geometry()

    @classmethod
    def supported_export_formats(cls) -> tuple[SurfaceExportFormat, ...]:
        """Return concrete surface export formats."""
        raise NotImplementedError

    def _set_name(self, name: str) -> None:
        """Assign the Part-scoped stable surface name."""
        self._name = str(name)

    def _set_flip(self, flip: bool) -> None:
        """Assign runtime parameter orientation during Part initialization."""
        self._flip = bool(flip)

    def _initialize_backend(self) -> None:
        """Create concrete immutable backend data."""
        return None

    def _get_evaluation_parameters(self) -> torch.Tensor:
        """Read default parameters used to refresh this surface."""
        if self._sample_parameters is None:
            raise RuntimeError(f"Surface '{self._name}' has no sample parameters")
        return self._sample_parameters

    def _evaluate_geometry(
        self, parameters: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Evaluate raw geometry then apply the documented v-direction flip."""
        coordinates, first_derivatives, second_derivatives = self._evaluate_raw(
            parameters
        )
        if self._flip:
            first_derivatives = first_derivatives.clone()
            second_derivatives = second_derivatives.clone()
            first_derivatives[..., 1] = -first_derivatives[..., 1]
            second_derivatives[..., 0, 1] = -second_derivatives[..., 0, 1]
            second_derivatives[..., 1, 0] = -second_derivatives[..., 1, 0]
        return coordinates, first_derivatives, second_derivatives

    def _evaluate_raw(
        self, parameters: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Evaluate concrete geometry before runtime orientation is applied."""
        raise NotImplementedError

    def _compute_point_weights(self, coordinates: torch.Tensor) -> torch.Tensor:
        """Compute uniform point weights when a concrete class has no topology."""
        return torch.ones(
            coordinates.shape[0],
            dtype=coordinates.dtype,
            device=coordinates.device,
        )

    def _compute_preview_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Convert concrete geometry into Viewer preview meshes."""
        raise NotImplementedError

    def _export_surface(self, path: Path, format: SurfaceExportFormat) -> Path:
        """Write a concrete surface file after public format validation."""
        del format
        meshes = self._compute_preview_meshes()
        if not meshes:
            raise RuntimeError(f"Surface '{self._name}' has no export mesh")
        meshes[0].save(path)
        return path
