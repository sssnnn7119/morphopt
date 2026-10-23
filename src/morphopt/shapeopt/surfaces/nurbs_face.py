"""Bspmap basis evaluation and nodal parameter matching for one CAD face."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

import bspmap
import numpy as np
from scipy.spatial import KDTree
import torch

from .base_surface import ControlPointSurface

if TYPE_CHECKING:
    from OCP.Geom import Geom_BSplineSurface
    from OCP.TopoDS import TopoDS_Face, TopoDS_Shape


class _KnotBasis(bspmap.Basis):
    """Use a CAD knot vector with bspmap's existing basis implementation."""

    def __init__(self, knots: np.ndarray, num_cps: int, degree: int) -> None:
        self._cad_knots = np.asarray(knots, dtype=np.float64)
        super().__init__(num_cps, degree)

    def _build_knots(self, degree: int, num_cps: int) -> np.ndarray:
        return self._cad_knots


class NURBSFace(ControlPointSurface):
    """One tensor-product support with fixed weights and differentiable poles.

    UV coordinates use the native CAD parameterization. Trimming and face
    membership belong to the owning BREPSurface; this object evaluates the
    support and matches points already assigned to that face.
    """

    def __init__(
        self, control_points: np.ndarray, weights: np.ndarray,
        degrees: tuple[int, int], knots: tuple[np.ndarray, np.ndarray],
    ) -> None:
        super().__init__()
        control_points = np.asarray(control_points, dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64)
        if control_points.ndim != 3 or control_points.shape[2] != 3 or weights.shape != control_points.shape[:2]:
            raise ValueError("NURBS poles require shape (nu, nv, 3) and weights shape (nu, nv).")
        if not np.isfinite(control_points).all() or not np.isfinite(weights).all() or np.any(weights <= 0):
            raise ValueError("NURBS poles must be finite and weights finite and positive.")
        self.size = tuple(control_points.shape[:2])
        self.degrees = degrees
        self.weights = np.asarray(weights, dtype=np.float64).reshape(-1)
        self._cps = torch.as_tensor(
            np.asarray(control_points, dtype=np.float64).reshape(-1, 3),
            device=torch.get_default_device(),
        ).clone()
        for vector, count, degree in zip(knots, self.size, degrees, strict=True):
            if not 1 <= degree < count or len(vector) != count + degree + 1:
                raise ValueError("NURBS degree, pole count and knot-vector length are inconsistent.")
            if not np.isfinite(vector).all() or np.any(np.diff(vector) < 0) or vector[degree] >= vector[-degree - 1]:
                raise ValueError("NURBS knots must be finite, nondecreasing and span a nonempty domain.")
        self.basis = tuple(_KnotBasis(vector, count, degree)
                           for vector, count, degree in zip(knots, self.size, degrees, strict=True))
        self.parameter_bounds = np.array([
            [basis.knots[basis.degree], basis.knots[-basis.degree - 1]] for basis in self.basis
        ])
        self.surf_node_idx = np.empty(0, dtype=np.int64)
        self.surf_node_uv = np.empty((0, 2), dtype=np.float64)
        self.projection_errors = np.empty(0, dtype=np.float64)
        self.design_mask: np.ndarray | None = None
        self._fixed_poles: torch.Tensor | None = None
        self._bound_basis: dict[tuple[int, int], tuple[torch.Tensor, torch.Tensor]] = {}

    def set_design_mask(self, mask: np.ndarray) -> None:
        """Freeze poles whose basis influences a trim edge."""
        mask = np.asarray(mask, dtype=bool).reshape(-1)
        if len(mask) != self._cps.shape[0]:
            raise ValueError("NURBS design mask must have one entry per pole.")
        self.design_mask = mask.copy()
        self._fixed_poles = self._cps.detach().clone()

    def set_surface_parameters(self, x: torch.Tensor) -> None:
        """Set poles while keeping trim-influencing poles fixed."""
        values = x.reshape(self._cps.shape)
        if self.design_mask is not None:
            mask = torch.as_tensor(self.design_mask[:, None], device=values.device)
            values = torch.where(mask, values, self._fixed_poles.to(values.device))
        self._cps = values

    @classmethod
    def from_occ(cls, surface: Geom_BSplineSurface) -> NURBSFace:
        """Expand periodic poles/knots into a standard nonperiodic support."""
        model = _expanded_support(surface)
        nu, nv = model.NbUPoles(), model.NbVPoles()
        poles = np.array([[list(model.Pole(u, v).Coord()) for v in range(1, nv + 1)]
                          for u in range(1, nu + 1)])
        weights = np.array([[model.Weight(u, v) for v in range(1, nv + 1)]
                            for u in range(1, nu + 1)])
        knots_u = np.repeat([model.UKnot(i) for i in range(1, model.NbUKnots() + 1)],
                            [model.UMultiplicity(i) for i in range(1, model.NbUKnots() + 1)])
        knots_v = np.repeat([model.VKnot(i) for i in range(1, model.NbVKnots() + 1)],
                            [model.VMultiplicity(i) for i in range(1, model.NbVKnots() + 1)])
        return cls(poles, weights, (model.UDegree(), model.VDegree()), (knots_u, knots_v))

    def to_occ(self) -> Geom_BSplineSurface:
        """Create an OCC support from the current poles and fixed knot data."""
        from OCP import collections
        from OCP.Geom import Geom_BSplineSurface
        from OCP.gp import gp_Pnt

        nu, nv = self.size
        poles = collections.Array2_gp_Pnt(1, nu, 1, nv)
        weights = collections.Array2_double(1, nu, 1, nv)
        positions = self.control_points.detach().cpu().numpy().reshape(nu, nv, 3)
        for u in range(nu):
            for v in range(nv):
                poles.SetValue(u + 1, v + 1, gp_Pnt(*map(float, positions[u, v])))
                weights.SetValue(u + 1, v + 1, float(self.weights[u * nv + v]))
        vectors = []
        multiplicities = []
        for basis in self.basis:
            unique, counts = np.unique(basis.knots, return_counts=True)
            values = collections.Array1_double(1, len(unique))
            counts_occ = collections.Array1_int(1, len(unique))
            for index, (value, count) in enumerate(zip(unique, counts, strict=True), 1):
                values.SetValue(index, float(value))
                counts_occ.SetValue(index, int(count))
            vectors.append(values)
            multiplicities.append(counts_occ)
        return Geom_BSplineSurface(
            poles, weights, *vectors, *multiplicities, *self.degrees,
        )

    def refine(
        self, u_knots: tuple[float, ...] = (), v_knots: tuple[float, ...] = (),
    ) -> NURBSFace:
        """Insert knots without changing the represented CAD geometry."""
        support = self.to_occ()
        for value in u_knots:
            support.InsertUKnot(float(value), 1, 1e-9)
        for value in v_knots:
            support.InsertVKnot(float(value), 1, 1e-9)
        return type(self).from_occ(support)

    def get_weights(
        self, uv: np.ndarray, derivative: tuple[int, int] = (0, 0),
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return rational basis coefficients and local pole indices."""
        if derivative not in {(0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2)}:
            raise ValueError("NURBS derivatives support total order zero, one or two.")
        parameters = np.asarray(uv, dtype=np.float64).reshape(-1, 2)
        if not len(parameters):
            count = (self.degrees[0] + 1) * (self.degrees[1] + 1)
            return np.empty((0, count)), np.empty((0, count), dtype=np.int64)
        lower, upper = self.parameter_bounds.T
        if not np.isfinite(parameters).all() or np.any(parameters < lower - 1e-10) or np.any(parameters > upper + 1e-10):
            raise ValueError("UV coordinates lie outside the NURBS support.")
        parameters = np.clip(parameters, lower, upper)
        orders = [order for order in ((0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2))
                  if order[0] <= derivative[0] and order[1] <= derivative[1]]
        derivatives: dict[tuple[int, int], np.ndarray] = {}
        denominators: dict[tuple[int, int], np.ndarray] = {}
        rational: dict[tuple[int, int], np.ndarray] = {}
        basis_u = [self.basis[0].get_weight(parameters[:, 0], d) for d in range(derivative[0] + 1)]
        basis_v = [self.basis[1].get_weight(parameters[:, 1], d) for d in range(derivative[1] + 1)]
        indices = (basis_u[0][1][:, :, None] * self.size[1] + basis_v[0][1][:, None, :]).reshape(len(parameters), -1)
        for a, b in orders:
            values = (basis_u[a][0][:, :, None] * basis_v[b][0][:, None, :]).reshape(indices.shape)
            derivatives[a, b] = values * self.weights[indices]
            denominators[a, b] = derivatives[a, b].sum(axis=1, keepdims=True)
        denominator = denominators[0, 0]
        rational[0, 0] = derivatives[0, 0] / denominator
        for a, b in orders[1:]:
            value = derivatives[a, b].copy()
            for i in range(a + 1):
                for j in range(b + 1):
                    if i == 0 and j == 0:
                        continue
                    coefficient = 2 if (a == 2 and i == 1) or (b == 2 and j == 1) else 1
                    value -= coefficient * denominators[i, j] * rational[a - i, b - j]
            rational[a, b] = value / denominator
        return rational[derivative], indices

    def map(self, uv: torch.Tensor, derivative: tuple[int, int] = (0, 0)) -> torch.Tensor:
        """Evaluate with detached UV and a live PyTorch control-point graph."""
        weights, indices = self.get_weights(uv.detach().cpu().numpy(), derivative)
        coefficients = torch.as_tensor(weights, dtype=self._cps.dtype, device=self._cps.device)
        indices_t = torch.as_tensor(indices, dtype=torch.long, device=self._cps.device)
        return (coefficients[:, :, None] * self._cps[indices_t]).sum(dim=1)

    def map_bound_nodes(self, derivative: tuple[int, int] = (0, 0)) -> torch.Tensor:
        """Evaluate cached nodal basis inside autograd and torch.func transforms."""
        coefficients, indices = self._bound_basis[derivative]
        coefficients = coefficients.to(dtype=self._cps.dtype, device=self._cps.device)
        indices = indices.to(device=self._cps.device)
        return (coefficients[:, :, None] * self._cps[indices]).sum(dim=1)

    def match_coordinates(
        self, surf_node_idx: np.ndarray, surf_nodes: np.ndarray,
        initial_uv: np.ndarray | None = None, batch_size: int = 4096,
        tolerance: float = 1e-9, max_iterations: int = 40,
    ) -> np.ndarray:
        """Use KD-tree seeds and batched Newton projection, as in BspSurface."""
        nodes = np.asarray(surf_nodes, dtype=np.float64).reshape(-1, 3)
        node_ids = np.asarray(surf_node_idx, dtype=np.int64).reshape(-1)
        if len(node_ids) != len(nodes):
            raise ValueError("Node indices and coordinates must have equal lengths.")
        if len(nodes) == 0:
            self.surf_node_idx, self.surf_node_uv = node_ids.copy(), np.empty((0, 2))
            self.projection_errors = np.empty(0)
            self._bound_basis = {
                order: tuple(torch.from_numpy(value) for value in self.get_weights(self.surf_node_uv, order))
                for order in ((0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2))
            }
            return nodes.copy()
        lower, upper = self.parameter_bounds.T
        poles = self._cps.detach().cpu().numpy()
        def evaluate(uv: np.ndarray, order: tuple[int, int] = (0, 0)) -> np.ndarray:
            weights, indices = self.get_weights(uv, order)
            return (weights[:, :, None] * poles[indices]).sum(axis=1)
        if initial_uv is None:
            axes = [np.linspace(*bounds, max(9, count * 5))
                    for bounds, count in zip(self.parameter_bounds, self.size, strict=True)]
            u, v = np.meshgrid(*axes, indexing="ij")
            seeds = np.column_stack((u.ravel(), v.ravel()))
            _, nearest = KDTree(evaluate(seeds)).query(nodes)
            initial_uv = seeds[nearest]
        initial_uv = np.asarray(initial_uv, dtype=np.float64).reshape(-1, 2)
        if len(initial_uv) != len(nodes) or batch_size <= 0:
            raise ValueError("Initial UV count must match nodes and batch_size must be positive.")
        result = np.empty_like(initial_uv)
        for start in range(0, len(nodes), batch_size):
            stop = min(start + batch_size, len(nodes))
            uv, points = np.clip(initial_uv[start:stop], lower, upper), nodes[start:stop]
            for _ in range(max_iterations):
                r = evaluate(uv)
                ru, rv = evaluate(uv, (1, 0)), evaluate(uv, (0, 1))
                difference = r - points
                gradient = np.column_stack(((difference * ru).sum(axis=1), (difference * rv).sum(axis=1)))
                hessian = np.empty((len(uv), 2, 2))
                hessian[:, 0, 0] = (ru * ru).sum(axis=1) + (difference * evaluate(uv, (2, 0))).sum(axis=1)
                hessian[:, 1, 1] = (rv * rv).sum(axis=1) + (difference * evaluate(uv, (0, 2))).sum(axis=1)
                hessian[:, 0, 1] = hessian[:, 1, 0] = (ru * rv).sum(axis=1) + (difference * evaluate(uv, (1, 1))).sum(axis=1)
                # Least squares also covers rank loss at a collapsed CAD pole.
                delta = -np.einsum("nij,nj->ni", np.linalg.pinv(hessian, rcond=1e-12), gradient)
                updated = uv.copy()
                error = (difference**2).sum(axis=1)
                for power in range(8):
                    candidate = np.clip(uv + delta * 0.5**power, lower, upper)
                    candidate_error = ((evaluate(candidate) - points)**2).sum(axis=1)
                    improved = candidate_error < error
                    updated[improved], error[improved] = candidate[improved], candidate_error[improved]
                change = np.max(np.abs((updated - uv) / (upper - lower)))
                uv = updated
                if change < tolerance:
                    break
            result[start:stop] = uv
        projected = evaluate(result)
        self.surf_node_idx, self.surf_node_uv = node_ids.copy(), result
        self.projection_errors = np.linalg.norm(projected - nodes, axis=1)
        self._bound_basis = {}
        for order in ((0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2)):
            weights, indices = self.get_weights(result, order)
            self._bound_basis[order] = (torch.from_numpy(weights), torch.from_numpy(indices))
        return projected


def _expanded_support(surface: Geom_BSplineSurface) -> Geom_BSplineSurface:
    """Use one native parameter period with ordinary indexed poles."""
    model = surface.Copy()
    bounds = model.Bounds()
    if model.IsUPeriodic():
        model.SetUNotPeriodic()
    if model.IsVPeriodic():
        model.SetVNotPeriodic()
    model.Segment(*bounds)
    return model


def _matched_occ_faces(
    path: Path, probes: Mapping[str, np.ndarray],
) -> tuple[TopoDS_Shape, dict[str, tuple[TopoDS_Face, Geom_BSplineSurface]]]:
    """Return the solid and uniquely identified trimmed NURBS faces."""
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepTools import BRepTools
    from OCP.Geom import Geom_BSplineSurface
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_ON
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Shape
    from OCP.gp import gp_Pnt

    shape = TopoDS_Shape()
    if not BRepTools.Read_s(shape, str(path), BRep_Builder()):
        raise ValueError(f"Cannot read BREP geometry: {path}")
    faces = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        support = BRep_Tool.Surface_s(face)
        if isinstance(support, Geom_BSplineSurface):
            faces.append((face, support))
        explorer.Next()
    result = {}
    for name, points in probes.items():
        matches = [(face, support) for face, support in faces if all(
            GeomAPI_ProjectPointOnSurf(gp_Pnt(*map(float, point)), support).LowerDistance() < 1e-7
            and BRepClass_FaceClassifier(face, gp_Pnt(*map(float, point)), 1e-7).State()
            in (TopAbs_IN, TopAbs_ON) for point in points
        )]
        if len(matches) != 1:
            raise ValueError(f"Cannot uniquely identify NURBS support of {name}.")
        result[name] = matches[0]
    return shape, result


def read_nurbs_faces(path: Path, probes: Mapping[str, np.ndarray]) -> dict[str, NURBSFace]:
    """Read OCC supports by geometric membership, independently of face order."""
    _, faces = _matched_occ_faces(path, probes)
    return {name: NURBSFace.from_occ(support) for name, (_, support) in faces.items()}


def write_nurbs_faces(
    source: Path, destination: Path, probes: Mapping[str, np.ndarray],
    models: Mapping[str, NURBSFace], tolerance: float = 1e-7,
) -> None:
    """Write changed poles while preserving the trimmed wires of a closed solid.

    Edges remain fixed. A requested pole movement that displaces any existing
    trim is rejected before the STEP file is written.
    """
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.ShapeFix import ShapeFix_Shape
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    shape, faces = _matched_occ_faces(source, probes)
    if models.keys() != faces.keys():
        raise ValueError("NURBS models and source faces must have identical names.")
    builder = BRep_Builder()
    for name, (face, original) in faces.items():
        model = models[name]
        support = model.to_occ()
        if not np.allclose(support.Bounds(), original.Bounds(), rtol=0, atol=1e-9):
            raise ValueError(f"NURBS parameter domain changed for {name}.")
        edges = TopExp_Explorer(face, TopAbs_EDGE)
        while edges.More():
            curve = BRepAdaptor_Curve(TopoDS.Edge(edges.Current()))
            for parameter in np.linspace(curve.FirstParameter(), curve.LastParameter(), 65):
                point = curve.Value(float(parameter))
                projector = GeomAPI_ProjectPointOnSurf(point, support)
                if projector.NbPoints() == 0 or projector.LowerDistance() > tolerance:
                    raise ValueError(f"NURBS update moves a trim edge of {name}; keep shared and hole boundaries fixed.")
            edges.Next()
        builder.UpdateFace(face, support, face.Location(), tolerance)
    repair = ShapeFix_Shape(shape)
    repair.Perform()
    shape = repair.Shape()
    if not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError("Updated NURBS faces do not form a valid closed solid.")
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise ValueError("Cannot transfer the updated BREP solid to STEP.")
    if writer.Write(str(destination)) != IFSelect_RetDone:
        raise ValueError(f"Cannot write STEP geometry: {destination}")
