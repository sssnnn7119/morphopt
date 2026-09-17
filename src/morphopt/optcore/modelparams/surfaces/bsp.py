"""B-spline surfaces and the cylindrical B-spline surface definition."""

from __future__ import annotations

from pathlib import Path

import gmsh
import numpy as np
import pyvista

from morphopt._torch import torch

import bspmap

from .base import SurfaceExportFormat
from .cpbased import CpBasedSurface
from .fairness import BSPFairnessEvaluator
from .preload import PreLoadData


class BSPSurface(CpBasedSurface):
    """Control-point B-spline surface with STP export.

    Subclasses create `_bsp_model` and `_control_shape` before invoking
    :meth:`initialize`.  Shared control-point/cache state is created by the
    first `super().__init__()` call.
    """

    def __init__(
        self,
        name: str = "",
        *,
        bsp_model: bspmap.BSP | None = None,
        control_points: torch.Tensor | None = None,
        control_shape: tuple[int, int] | None = None,
        degree: int = 3,
    ) -> None:
        super().__init__(name, control_points)
        self._bsp_model = bsp_model
        """B-spline backend used for sparse basis evaluation."""
        self._control_shape = control_shape
        """Structured control-point shape ordered as (v_count, u_count)."""
        self._degree = int(degree)
        """Common B-spline polynomial degree."""
        self._fairness_evaluator = BSPFairnessEvaluator()
        """Fairness evaluator owned by this editable BSP surface."""

    @property
    def fairness_evaluator(self) -> BSPFairnessEvaluator:
        """Return the evaluator dedicated to this B-spline surface."""
        return self._fairness_evaluator

    @classmethod
    def supported_export_formats(cls) -> tuple[SurfaceExportFormat, ...]:
        """Return the STP format supported by B-spline CAD export."""
        return ("stp",)

    def _initialize_backend(self) -> None:
        """Validate the B-spline backend and establish a sample preload."""
        if self._bsp_model is None or self._control_shape is None:
            raise RuntimeError(f"Surface '{self.name}' has no B-spline backend")
        if self._control_points.numel() == 0:
            self._control_points = torch.as_tensor(
                self._bsp_model.control_points
            ).reshape(-1, 3)
        if self._sample_parameters is None:
            self._sample_parameters = self._create_sample_parameters()
        self._build_bsp_preload(self._sample_parameters)

    def update_backend(self) -> None:
        """Synchronize committed control points into the B-spline backend."""
        if self._bsp_model is not None:
            self._bsp_model.control_points = (
                self._control_points.detach().cpu().numpy().reshape(-1, 3)
            )

    def map(self, parameters: torch.Tensor) -> torch.Tensor:
        """Evaluate B-spline coordinates for `(v, u)` parameter points."""
        if self._bsp_model is None:
            raise RuntimeError(f"Surface '{self.name}' has no B-spline backend")
        values = self._bsp_model.map(
            torch.as_tensor(parameters).detach().cpu().numpy().reshape(-1, 2)
        )
        return torch.as_tensor(values, dtype=self._control_points.dtype)

    def _evaluate_raw(
        self, parameters: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Evaluate position and first/second B-spline derivatives."""
        if self._bsp_model is None:
            raise RuntimeError(f"Surface '{self.name}' has no B-spline backend")
        values = torch.as_tensor(parameters).detach().cpu().numpy().reshape(-1, 2)
        coordinates = torch.as_tensor(
            self._bsp_model.map(values), dtype=self._control_points.dtype
        )
        first_derivatives = torch.stack(
            (
                torch.as_tensor(
                    self._bsp_model.map(values, derivative=[1, 0]),
                    dtype=coordinates.dtype,
                ),
                torch.as_tensor(
                    self._bsp_model.map(values, derivative=[0, 1]),
                    dtype=coordinates.dtype,
                ),
            ),
            dim=-1,
        )
        second_derivatives = torch.stack(
            (
                torch.stack(
                    (
                        torch.as_tensor(
                            self._bsp_model.map(values, derivative=[2, 0]),
                            dtype=coordinates.dtype,
                        ),
                        torch.as_tensor(
                            self._bsp_model.map(values, derivative=[1, 1]),
                            dtype=coordinates.dtype,
                        ),
                    ),
                    dim=-1,
                ),
                torch.stack(
                    (
                        torch.as_tensor(
                            self._bsp_model.map(values, derivative=[1, 1]),
                            dtype=coordinates.dtype,
                        ),
                        torch.as_tensor(
                            self._bsp_model.map(values, derivative=[0, 2]),
                            dtype=coordinates.dtype,
                        ),
                    ),
                    dim=-1,
                ),
            ),
            dim=-1,
        )
        return coordinates, first_derivatives, second_derivatives

    def _build_bsp_preload(self, parameters: torch.Tensor) -> None:
        """Build sparse zero-, first- and second-order B-spline weights."""
        if self._bsp_model is None:
            raise RuntimeError(f"Surface '{self.name}' has no B-spline backend")
        values = parameters.detach().cpu().numpy().reshape(-1, 2)
        position_weights, control_indices = self._bsp_model.get_weights(
            values, derivative=[0, 0]
        )
        derivative_u = self._bsp_model.get_weights(values, derivative=[1, 0])[0]
        derivative_v = self._bsp_model.get_weights(values, derivative=[0, 1])[0]
        derivative_uu = self._bsp_model.get_weights(values, derivative=[2, 0])[0]
        derivative_uv = self._bsp_model.get_weights(values, derivative=[1, 1])[0]
        derivative_vv = self._bsp_model.get_weights(values, derivative=[0, 2])[0]
        control_indices = np.asarray(control_indices, dtype=np.int64).reshape(
            parameters.shape[0], -1
        )
        sample_indices = np.repeat(
            np.arange(parameters.shape[0], dtype=np.int64), control_indices.shape[1]
        )
        faces = self._create_sample_faces(parameters)
        self.set_preload_data(
            PreLoadData(
                parameters=parameters.detach().clone(),
                control_point_indices=torch.as_tensor(
                    np.stack((sample_indices, control_indices.reshape(-1)))
                ),
                position_weights=torch.as_tensor(position_weights).reshape(-1),
                first_derivative_weights=torch.stack(
                    (
                        torch.as_tensor(derivative_u).reshape(-1),
                        torch.as_tensor(derivative_v).reshape(-1),
                    ),
                    dim=-1,
                ),
                second_derivative_weights=torch.stack(
                    (
                        torch.stack(
                            (
                                torch.as_tensor(derivative_uu).reshape(-1),
                                torch.as_tensor(derivative_uv).reshape(-1),
                            ),
                            dim=-1,
                        ),
                        torch.stack(
                            (
                                torch.as_tensor(derivative_uv).reshape(-1),
                                torch.as_tensor(derivative_vv).reshape(-1),
                            ),
                            dim=-1,
                        ),
                    ),
                    dim=-1,
                ),
                faces=faces,
            )
        )

    def _create_sample_parameters(self) -> torch.Tensor:
        """Create a stable structured `(v, u)` sample grid."""
        if self._control_shape is None:
            raise RuntimeError(f"Surface '{self.name}' has no control shape")
        count_v, count_u = self._control_shape
        samples_v = max(2, 2 * count_v)
        samples_u = max(4, 2 * count_u)
        values_v = torch.linspace(0.0, 1.0, samples_v)
        values_u = torch.linspace(0.0, 1.0, samples_u + 1)[:-1]
        grid_v, grid_u = torch.meshgrid(values_v, values_u, indexing="ij")
        return torch.stack((grid_v.reshape(-1), grid_u.reshape(-1)), dim=-1)

    def _create_sample_faces(self, parameters: torch.Tensor) -> torch.Tensor:
        """Create triangular connectivity for the structured periodic-u grid."""
        if self._control_shape is None:
            raise RuntimeError(f"Surface '{self.name}' has no control shape")
        count_v = max(2, 2 * self._control_shape[0])
        count_u = max(4, 2 * self._control_shape[1])
        if parameters.shape[0] != count_v * count_u:
            return torch.zeros((0, 3), dtype=torch.long)
        faces: list[tuple[int, int, int]] = []
        for index_v in range(count_v - 1):
            for index_u in range(count_u):
                next_u = (index_u + 1) % count_u
                lower_left = index_v * count_u + index_u
                lower_right = index_v * count_u + next_u
                upper_left = (index_v + 1) * count_u + index_u
                upper_right = (index_v + 1) * count_u + next_u
                faces.extend(
                    (
                        (lower_left, lower_right, upper_left),
                        (lower_right, upper_right, upper_left),
                    )
                )
        return torch.as_tensor(faces, dtype=torch.long)

    def _compute_preview_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Build the current sampled B-spline triangular preview."""
        preload_data = self.get_preload_data()
        coordinates, _, _ = self.get_geometry_values()
        return (self._create_poly_data(coordinates, preload_data.faces),)

    def _export_surface(self, path: Path, format: SurfaceExportFormat) -> Path:
        """Write a native OCC B-spline surface to a STEP file."""
        del format
        if self._control_shape is None:
            raise RuntimeError(f"Surface '{self.name}' has no control shape")
        points = self._control_points.detach().cpu().numpy().reshape(-1, 3)
        count_v, count_u = self._control_shape
        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Verbosity", 0)
            gmsh.model.add(self.name or "bsp_surface")
            point_tags = [
                gmsh.model.occ.addPoint(float(x), float(y), float(z))
                for x, y, z in points
            ]
            gmsh.model.occ.addBSplineSurface(
                point_tags,
                count_u,
                degreeU=min(self._degree, count_u - 1),
                degreeV=min(self._degree, count_v - 1),
            )
            gmsh.model.occ.synchronize()
            gmsh.write(str(path))
        finally:
            gmsh.finalize()
        return path


class BSPCylinderSurface(BSPSurface):
    """Periodic-u, clamped-v B-spline cylinder definition."""

    def __init__(
        self,
        radius: float,
        length: float,
        seed_size: float,
        *,
        name: str = "",
        num_u_ratio: int = 1,
        num_v_ratio: int = 1,
        degree: int = 3,
        init_location: tuple[float, float, float] = (0.0, 0.0, 0.0),
        perturbation_length: float | None = None,
    ) -> None:
        super().__init__(name, degree=degree)
        self._radius = float(radius)
        """Cylinder radius."""
        self._length = float(length)
        """Cylinder axial length."""
        self._seed_size = float(seed_size)
        """Target surface sampling size."""
        self._num_u_ratio = int(num_u_ratio)
        """Circumferential control-point density ratio."""
        self._num_v_ratio = int(num_v_ratio)
        """Axial control-point density ratio."""
        self._init_location = tuple(float(value) for value in init_location)
        """Cylinder origin in global coordinates."""
        self._perturbation_length = perturbation_length
        """Optional initial radial perturbation wavelength."""

    @property
    def radius(self) -> float:
        """Read cylinder radius."""
        return self._radius

    @property
    def length(self) -> float:
        """Read cylinder length."""
        return self._length

    @property
    def seed_size(self) -> float:
        """Read target sampling size."""
        return self._seed_size

    def _initialize_backend(self) -> None:
        """Create the structured cylinder B-spline backend once."""
        if self._bsp_model is None:
            control_points, control_shape = self._create_initial_control_points()
            count_v, count_u = control_shape
            basis_v = bspmap.BasisClamped(count_v, self._degree)
            basis_u = bspmap.BasisCircular(count_u, self._degree)
            self._bsp_model = bspmap.BSP(
                basis=[basis_v, basis_u],
                degree=self._degree,
                size=[count_v, count_u],
                control_points=control_points.detach().cpu().numpy().reshape(-1, 3),
            )
            self._control_points = control_points.reshape(-1, 3)
            self._control_shape = control_shape
        super()._initialize_backend()

    def _create_initial_control_points(self) -> tuple[torch.Tensor, tuple[int, int]]:
        """Create periodic circular control rows along the cylinder axis."""
        count_u = max(
            12,
            int(round(2.0 * np.pi * self._radius / self._seed_size)),
            self._degree + 1,
        )
        count_u = max(
            self._degree + 1,
            int(np.ceil(count_u / max(1, self._num_u_ratio))) * max(1, self._num_u_ratio),
        )
        count_v = max(
            self._degree + 1,
            int(np.ceil(max(1.0, self._length / self._seed_size) / max(1, self._num_v_ratio)))
            * max(1, self._num_v_ratio)
            + 1,
        )
        values_v = torch.linspace(0.0, self._length, count_v)
        values_u = torch.arange(count_u, dtype=torch.get_default_dtype()) / count_u
        grid_v, grid_u = torch.meshgrid(values_v, values_u, indexing="ij")
        angle = 2.0 * torch.pi * grid_u
        radius = torch.full_like(angle, self._radius)
        if self._perturbation_length is not None and self._perturbation_length > 0.0:
            radius = radius * (
                1.0
                + 0.04
                * torch.cos(
                    2.0
                    * torch.pi
                    * grid_v
                    / float(self._perturbation_length)
                )
            )
        control_points = torch.stack(
            (
                radius * torch.cos(angle) + self._init_location[0],
                radius * torch.sin(angle) + self._init_location[1],
                grid_v + self._init_location[2],
            ),
            dim=-1,
        )
        return control_points, (count_v, count_u)
