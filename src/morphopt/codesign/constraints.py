import torch

from ..constants import CONSTANT
from ..shapeopt.objectivefuncs.basefuncs import BaseConstraints
from .offset_boundary_part import OffsetBoundaryPart


class InwardCurvatureRadius(BaseConstraints):
    """
    Constrain inward principal curvature so offset shells do not self-intersect.

    For each selected surface point, this constraint enforces:
        k_inward <= 1 / (thickness + margin)
    where only inward curvature is penalized; outward curvature is ignored.
    """

    def __init__(
        self,
        surface_start: int = 1,
        surface_ids: list[int] | None = None,
        margin: float = CONSTANT.KERNEL.CODESIGN.CURVATURE_MARGIN,
        margin_ratio: float = CONSTANT.KERNEL.CODESIGN.CURVATURE_MARGIN_RATIO,
        barrier_thre_ratio: float = CONSTANT.KERNEL.CODESIGN.CURVATURE_BARRIER_THRESHOLD_RATIO,
        barrier_ratio: float = CONSTANT.KERNEL.CODESIGN.BARRIER_PENALTY_RATIO,
        p: int = CONSTANT.KERNEL.CODESIGN.BARRIER_EXPONENT,
        penalty_scale: float = CONSTANT.KERNEL.CODESIGN.PENALTY_SCALE,
        hard_violation_beta: float = CONSTANT.KERNEL.CODESIGN.HARD_VIOLATION_BETA,
        normal_sign: float = 1.0,
    ) -> None:
        """
        Initialize the inward curvature radius constraint.

        Args:
            surface_start (int, optional): The starting index of surfaces to apply the constraint. Defaults to 1.
            surface_ids (list[int] | None, optional): The specific surface indices to apply the constraint. If None, applies to all surfaces starting from surface_start. Defaults to None.
            margin (float, optional): The absolute margin added to thickness for curvature limit. Defaults to 0.4.
            margin_ratio (float, optional): The ratio of thickness to determine margin if margin is None. Defaults to 0.45.
            barrier_thre_ratio (float, optional): The ratio of curvature limit to determine the barrier threshold. Defaults to 0.1.
            barrier_ratio (float, optional): The ratio to scale the barrier penalty. Defaults to 0.0.
            p (int, optional): The power for the barrier function. Defaults to 8.
            penalty_scale (float, optional): Global multiplier for this constraint penalty. Defaults to 1e3.
            hard_violation_beta (float, optional): Exponential amplification factor for large violations. Defaults to 8.0.
            normal_sign (float, optional): The sign to determine inward direction. Use 1.0 if normals point outward, -1.0 if normals point inward. Defaults to 1.0.

        """

        super().__init__()

        self.surface_start = int(surface_start)
        """Stores the surface start used by InwardCurvatureRadius."""
        self.surface_ids = (
            None if surface_ids is None else [int(i) for i in surface_ids]
        )
        """Stores the surface ids used by InwardCurvatureRadius."""

        self.margin = margin
        """Stores the margin used by InwardCurvatureRadius."""
        self.margin_ratio = float(margin_ratio)
        """Stores the margin ratio used by InwardCurvatureRadius."""
        self.barrier_thre_ratio = float(barrier_thre_ratio)
        """Stores the barrier thre ratio used by InwardCurvatureRadius."""
        self.barrier_ratio = float(barrier_ratio)
        """Stores the barrier ratio used by InwardCurvatureRadius."""
        self.p = int(p)
        """Stores the p used by InwardCurvatureRadius."""
        self.penalty_scale = float(penalty_scale)
        """Stores the penalty scale used by InwardCurvatureRadius."""
        self.hard_violation_beta = float(hard_violation_beta)
        """Stores the hard violation beta used by InwardCurvatureRadius."""
        self.normal_sign = 1.0 if normal_sign >= 0 else -1.0
        """Stores the normal sign used by InwardCurvatureRadius."""

    @staticmethod
    def _principal_curvatures(
        rdu: torch.Tensor,
        rdu2: torch.Tensor,
        eps: float = CONSTANT.KERNEL.CODESIGN.GEOMETRY_TOLERANCE,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        normal0 = torch.cross(rdu[:, :, 1], rdu[:, :, 0], dim=1)
        normal = normal0 / (normal0.norm(dim=1, keepdim=True) + eps)

        I = torch.einsum("pim,pin->pmn", rdu, rdu)
        eye2 = torch.eye(2, dtype=I.dtype, device=I.device).unsqueeze(0)
        I = I + eps * eye2

        II = torch.einsum("pimn,pi->pmn", rdu2, normal)
        S = torch.linalg.solve(I, II)

        tr = S[:, 0, 0] + S[:, 1, 1]
        det = S[:, 0, 0] * S[:, 1, 1] - S[:, 0, 1] * S[:, 1, 0]
        disc = (tr * tr - 4.0 * det).clamp(min=0.0)
        root = torch.sqrt(disc)

        k1 = 0.5 * (tr + root)
        k2 = 0.5 * (tr - root)
        return k1, k2

    def initialize(self, r0, rdu0, *args, part_interface=None, **kwargs) -> None:
        """Take the Part this constraint is evaluated for.

        The geometry updater hands over the Part it evaluates; only a
        :class:`~morphopt.codesign.OffsetBoundaryPart` carries a
        shell, so anything else is rejected here.
        """
        super().initialize(r0=r0, rdu0=rdu0, *args, **kwargs)
        if not isinstance(part_interface, OffsetBoundaryPart):
            raise TypeError(
                f"{type(self).__name__} is evaluated for one co-design Part "
                f"(got {type(part_interface).__name__})."
            )
        self.shell_thickness = float(part_interface.shell_thickness)

    def _selected_surface_ids(self, n_surface: int) -> list[int]:
        if self.surface_ids is None:
            return [i for i in range(max(self.surface_start, 0), n_surface)]
        return [i for i in self.surface_ids if 0 <= i < n_surface]

    def __call__(
        self,
        r: list[torch.Tensor],
        rdu: list[torch.Tensor],
        rdu2: list[torch.Tensor],
        *args,
        **kwargs,
    ) -> torch.Tensor:
        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)

        for i in self._selected_surface_ids(len(r)):
            t = self.shell_thickness
            if t <= 0:
                continue

            margin_abs = max(
                float((self.margin_ratio * t) + self.margin),
                CONSTANT.KERNEL.CODESIGN.GEOMETRY_TOLERANCE,
            )
            k_limit = 1.0 / (t + margin_abs)
            barrier_thre = max(
                k_limit * self.barrier_thre_ratio,
                CONSTANT.KERNEL.CODESIGN.GEOMETRY_TOLERANCE,
            )

            k1, k2 = self._principal_curvatures(rdu[i], rdu2[i])

            k1_in = torch.relu(self.normal_sign * k1)
            k2_in = torch.relu(self.normal_sign * k2)
            k_inward = torch.maximum(k1_in, k2_in)

            violation = k_inward - k_limit
            index, penalty = self.barrier_function(
                violation, barrier_thre, self.barrier_ratio, self.p
            )
            if index.numel() > 0:
                # Strong amplification: base polynomial barrier + exponential hard-violation boost.
                rel_violation = (violation[index] / barrier_thre).clamp(min=0.0)
                hard_boost = torch.exp(
                    (self.hard_violation_beta * (rel_violation - 1.0)).clamp(
                        min=0.0,
                        max=CONSTANT.KERNEL.CODESIGN.HARD_VIOLATION_EXPONENT_MAX,
                    )
                )
                penalty_strong = self.penalty_scale * penalty * hard_boost
                loss = loss + (self.scaler[i][index] * penalty_strong).sum()

        return loss


class OffsetSurfaceMinThickness(BaseConstraints):
    """
    Enforce a minimum distance on the offset surface to reduce self-intersection risk.

    This constraint builds neighbor pairs on the offset surface during initialize,
    and penalizes pairs whose distance becomes smaller than the required minimum.
    """

    def __init__(
        self,
        surface_start: int = 1,
        surface_ids: list[int] | None = None,
        min_distance: float | None = None,
        search_ratio: float = CONSTANT.KERNEL.CODESIGN.THICKNESS_SEARCH_RATIO,
        barrier_thre_ratio: float = CONSTANT.KERNEL.CODESIGN.THICKNESS_BARRIER_THRESHOLD_RATIO,
        barrier_ratio: float = CONSTANT.KERNEL.CODESIGN.BARRIER_PENALTY_RATIO,
        p: int = CONSTANT.KERNEL.CODESIGN.BARRIER_EXPONENT,
        penalty_scale: float = CONSTANT.KERNEL.CODESIGN.PENALTY_SCALE,
        hard_violation_beta: float = CONSTANT.KERNEL.CODESIGN.HARD_VIOLATION_BETA,
        normal_sign: float = 1.0,
        normal_opposition_thre: float = CONSTANT.KERNEL.CODESIGN.NORMAL_OPPOSITION_THRESHOLD,
        normal_min: float = CONSTANT.KERNEL.CODESIGN.NORMAL_TRANSITION_MIN,
        normal_max: float = CONSTANT.KERNEL.CODESIGN.NORMAL_TRANSITION_MAX,
    ) -> None:
        """
        Initialize the minimum thickness constraint for the offset surface.

        Args:
            surface_start (int, optional): The starting index of surfaces to apply the constraint. Defaults to 1.
            surface_ids (list[int] | None, optional): The specific surface indices to apply the constraint. If None, applies to all surfaces starting from surface_start. Defaults to None.
            min_distance (float | None, optional): The required minimum distance.
                Defaults to twice the shell thickness.
        """
        super().__init__()

        self.surface_start = int(surface_start)
        """Stores the surface start used by OffsetSurfaceMinThickness."""
        self.surface_ids = (
            None if surface_ids is None else [int(i) for i in surface_ids]
        )
        """Stores the surface ids used by OffsetSurfaceMinThickness."""

        self.min_distance = min_distance
        """Stores the min distance used by OffsetSurfaceMinThickness."""
        self.search_ratio = float(search_ratio)
        """Stores the search ratio used by OffsetSurfaceMinThickness."""
        self.barrier_thre_ratio = float(barrier_thre_ratio)
        """Stores the barrier thre ratio used by OffsetSurfaceMinThickness."""
        self.barrier_ratio = float(barrier_ratio)
        """Stores the barrier ratio used by OffsetSurfaceMinThickness."""
        self.p = int(p)
        """Stores the p used by OffsetSurfaceMinThickness."""
        self.penalty_scale = float(penalty_scale)
        """Stores the penalty scale used by OffsetSurfaceMinThickness."""
        self.hard_violation_beta = float(hard_violation_beta)
        """Stores the hard violation beta used by OffsetSurfaceMinThickness."""
        self.normal_sign = 1.0 if normal_sign >= 0 else -1.0
        """Stores the normal sign used by OffsetSurfaceMinThickness."""
        self.normal_opposition_thre = float(normal_opposition_thre)
        """Stores the normal opposition thre used by OffsetSurfaceMinThickness."""
        self.normal_min = float(normal_min)
        """Stores the normal min used by OffsetSurfaceMinThickness."""
        self.normal_max = float(normal_max)
        """Stores the normal max used by OffsetSurfaceMinThickness."""

        self._neighbor_pairs: dict[int, torch.Tensor] = {}
        """Stores the neighbor pairs used by OffsetSurfaceMinThickness."""
        self._neighbor_mindist: dict[int, torch.Tensor] = {}
        """Stores the neighbor mindist used by OffsetSurfaceMinThickness."""

    def _selected_surface_ids(self, n_surface: int) -> list[int]:
        if self.surface_ids is None:
            return [i for i in range(max(self.surface_start, 0), n_surface)]
        return [i for i in self.surface_ids if 0 <= i < n_surface]

    @staticmethod
    def _surface_normals(rdu_sf: torch.Tensor) -> torch.Tensor:
        normal0 = torch.cross(rdu_sf[:, :, 1], rdu_sf[:, :, 0], dim=1)
        normals = normal0 / (
            normal0.norm(dim=1, keepdim=True)
            + CONSTANT.KERNEL.CODESIGN.GEOMETRY_TOLERANCE
        )
        return normals

    def _offset_points(
        self, r_sf: torch.Tensor, rdu_sf: torch.Tensor, thickness: float
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Offset surface points and the normals they were offset along."""
        normals = self._surface_normals(rdu_sf=rdu_sf)
        return r_sf + self.normal_sign * thickness * normals, normals

    def _min_distance(self, thickness: float) -> float:
        dmin = (
            float(self.min_distance)
            if self.min_distance is not None
            else (2.0 * thickness)
        )
        return max(dmin, CONSTANT.KERNEL.CODESIGN.GEOMETRY_TOLERANCE)

    def initialize(self, r0, rdu0, *args, part_interface=None, **kwargs) -> None:
        """Take the Part this constraint is evaluated for and pair its points.

        The geometry updater hands over the Part it evaluates; only a
        :class:`~morphopt.codesign.OffsetBoundaryPart` carries a
        shell, so anything else is rejected here.
        """
        super().initialize(r0=r0, rdu0=rdu0, *args, **kwargs)
        if not isinstance(part_interface, OffsetBoundaryPart):
            raise TypeError(
                f"{type(self).__name__} is evaluated for one co-design Part "
                f"(got {type(part_interface).__name__})."
            )
        self.shell_thickness = float(part_interface.shell_thickness)

        self._neighbor_pairs = {}
        self._neighbor_mindist = {}

        if self.shell_thickness <= 0:
            return

        import scipy.spatial

        for sf_idx in self._selected_surface_ids(len(r0)):
            dmin = self._min_distance(self.shell_thickness)
            search_radius = max(dmin * self.search_ratio, dmin)

            roff, normals = self._offset_points(
                r_sf=r0[sf_idx], rdu_sf=rdu0[sf_idx], thickness=self.shell_thickness
            )

            tree = scipy.spatial.KDTree(roff.detach().cpu().numpy())
            pairs_np = tree.query_pairs(r=search_radius, output_type="ndarray")
            if pairs_np.size == 0:
                continue

            pairs = torch.from_numpy(pairs_np.T).to(
                dtype=torch.int64, device=r0[sf_idx].device
            )

            dotn = (normals[pairs[0]] * normals[pairs[1]]).sum(dim=1)
            opposition = (-dotn).clamp(min=0.0)
            keep = opposition > self.normal_opposition_thre
            if keep.any():
                pairs = pairs[:, keep]
                self._neighbor_pairs[sf_idx] = pairs
                self._neighbor_mindist[sf_idx] = dmin * opposition[keep]

    def __call__(
        self,
        r: list[torch.Tensor],
        rdu: list[torch.Tensor],
        rdu2: list[torch.Tensor],
        *args,
        **kwargs,
    ) -> torch.Tensor:
        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)

        for sf_idx in self._selected_surface_ids(len(r)):
            pairs = self._neighbor_pairs.get(sf_idx, None)
            if pairs is None or pairs.numel() == 0:
                continue

            thickness = self.shell_thickness
            if thickness <= 0:
                continue
            barrier_thre = max(
                self._min_distance(thickness) * self.barrier_thre_ratio,
                CONSTANT.KERNEL.CODESIGN.GEOMETRY_TOLERANCE,
            )

            # Base surface normals (offset surface shares same normal direction)
            normals = self._surface_normals(rdu_sf=rdu[sf_idx])
            dotn = (normals[pairs[0]] * normals[pairs[1]]).sum(dim=1)

            # Pre-filter pairs where normals are not opposing enough
            mask_n = dotn < self.normal_max
            if not mask_n.any():
                continue

            pairs_n = pairs[:, mask_n]
            dotn_n = dotn[mask_n]
            mindist_n = self._neighbor_mindist[sf_idx][mask_n].to(
                device=r[sf_idx].device, dtype=r[sf_idx].dtype
            )
            scaler_n0 = self.scaler[sf_idx][pairs_n[0]]
            scaler_n1 = self.scaler[sf_idx][pairs_n[1]]

            # Offset points and distance
            roff, _ = self._offset_points(
                r_sf=r[sf_idx], rdu_sf=rdu[sf_idx], thickness=thickness
            )
            delta = roff[pairs_n[0]] - roff[pairs_n[1]]
            dist = torch.sqrt(
                (delta * delta).sum(dim=1)
                + CONSTANT.KERNEL.CODESIGN.DISTANCE_SQUARED_TOLERANCE
            )

            violation = mindist_n - dist + barrier_thre
            indexl, l = self.barrier_function(
                violation, barrier_thre, self.barrier_ratio, self.p
            )

            if indexl.numel() > 0:
                # Smooth normal penalty (same as Distance class)
                np_val = (
                    self.normal_max
                    - torch.clamp(dotn_n[indexl], self.normal_min, self.normal_max)
                ) / (self.normal_max - self.normal_min)
                np_smooth = (6 * np_val**2 - 15 * np_val + 10) * np_val**3

                rel_violation = (violation[indexl] / barrier_thre).clamp(min=0.0)
                hard_boost = torch.exp(
                    (self.hard_violation_beta * (rel_violation - 1.0)).clamp(
                        min=0.0,
                        max=CONSTANT.KERNEL.CODESIGN.HARD_VIOLATION_EXPONENT_MAX,
                    )
                )
                penalty_strong = self.penalty_scale * l * hard_boost * np_smooth

                loss = (
                    loss
                    + (penalty_strong * scaler_n0[indexl] * scaler_n1[indexl]).sum()
                )

        return loss
