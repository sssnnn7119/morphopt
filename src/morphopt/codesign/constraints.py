import torch

from ..optcore.updaters.geometry.objectivefuncs.basefuncs import BaseConstraints
from .geometry import CodesignGeometry


class InwardCurvatureRadius(BaseConstraints):
    """
    Constrain inward principal curvature so offset shells do not self-intersect.

    For each selected surface point, this constraint enforces:
        k_inward <= 1 / (thickness + margin)
    where only inward curvature is penalized; outward curvature is ignored.
    """

    def __init__(
        self,
        geometry: CodesignGeometry,
        surface_start: int = 1,
        surface_ids: list[int] | None = None,
        margin: float = 0.1,
        margin_ratio: float = 0.45,
        barrier_thre_ratio: float = 0.05,
        barrier_ratio: float = 0.0,
        p: int = 8,
        penalty_scale: float = 1e3,
        hard_violation_beta: float = 8.0,
        normal_sign: float = 1.0,
    ) -> None:
        """
        Initialize the inward curvature radius constraint.

        Args:
            geometry (CodesignGeometry): The geometry parameters containing the surfaces.
            surface_start (int, optional): The starting index of surfaces to apply the constraint. Defaults to 1.
            surface_ids (list[int] | None, optional): The specific surface indices to apply the constraint. If None, applies to all surfaces starting from surface_start. Defaults to None.
            margin (float, optional): The absolute margin added to thickness for curvature limit. Defaults to 0.5.
            margin_ratio (float, optional): The ratio of thickness to determine margin if margin is None. Defaults to 0.45.
            barrier_thre_ratio (float, optional): The ratio of curvature limit to determine the barrier threshold. Defaults to 0.05.
            barrier_ratio (float, optional): The ratio to scale the barrier penalty. Defaults to 0.0.
            p (int, optional): The power for the barrier function. Defaults to 8.
            penalty_scale (float, optional): Global multiplier for this constraint penalty. Defaults to 1e3.
            hard_violation_beta (float, optional): Exponential amplification factor for large violations. Defaults to 8.0.
            normal_sign (float, optional): The sign to determine inward direction. Use 1.0 if normals point outward, -1.0 if normals point inward. Defaults to 1.0.
        
        """


        super().__init__()

        self.geometry = geometry
        self.surface_start = int(surface_start)
        self.surface_ids = None if surface_ids is None else [int(i) for i in surface_ids]

        self.margin = margin
        self.margin_ratio = float(margin_ratio)
        self.barrier_thre_ratio = float(barrier_thre_ratio)
        self.barrier_ratio = float(barrier_ratio)
        self.p = int(p)
        self.penalty_scale = float(penalty_scale)
        self.hard_violation_beta = float(hard_violation_beta)
        self.normal_sign = 1.0 if normal_sign >= 0 else -1.0

    @staticmethod
    def _principal_curvatures(rdu: torch.Tensor, rdu2: torch.Tensor, eps: float = 1e-12) -> tuple[torch.Tensor, torch.Tensor]:
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

    def _selected_surface_ids(self, n_surface: int) -> list[int]:
        if self.surface_ids is None:
            return [i for i in range(max(self.surface_start, 0), n_surface)]
        return [i for i in self.surface_ids if 0 <= i < n_surface]

    def __call__(self, r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor], *args, **kwargs) -> torch.Tensor:
        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)

        t = float(self.geometry.shell_thickness)
        if t <= 0:
            return loss

        margin_abs = (self.margin_ratio * t) + self.margin
        margin_abs = max(float(margin_abs), 1e-12)
        t_eff = t + margin_abs

        k_limit = 1.0 / t_eff
        barrier_thre = max(k_limit * self.barrier_thre_ratio, 1e-12)

        for i in self._selected_surface_ids(len(r)):
            k1, k2 = self._principal_curvatures(rdu[i], rdu2[i])

            k1_in = torch.relu(self.normal_sign * k1)
            k2_in = torch.relu(self.normal_sign * k2)
            k_inward = torch.maximum(k1_in, k2_in)

            violation = k_inward - k_limit
            index, penalty = self.barrier_function(violation, barrier_thre, self.barrier_ratio, self.p)
            if index.numel() > 0:
                # Strong amplification: base polynomial barrier + exponential hard-violation boost.
                rel_violation = (violation[index] / barrier_thre).clamp(min=0.0)
                hard_boost = torch.exp((self.hard_violation_beta * (rel_violation - 1.0)).clamp(min=0.0, max=20.0))
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
        geometry: CodesignGeometry,
        surface_start: int = 1,
        surface_ids: list[int] | None = None,
        min_distance: float | None = None,
        search_ratio: float = 1.5,
        barrier_thre_ratio: float = 0.05,
        barrier_ratio: float = 0.0,
        p: int = 8,
        penalty_scale: float = 1e3,
        hard_violation_beta: float = 8.0,
        normal_sign: float = 1.0,
        normal_opposition_thre: float = 0.0,
    ) -> None:
        super().__init__()

        self.geometry = geometry
        self.surface_start = int(surface_start)
        self.surface_ids = None if surface_ids is None else [int(i) for i in surface_ids]

        self.min_distance = min_distance
        self.search_ratio = float(search_ratio)
        self.barrier_thre_ratio = float(barrier_thre_ratio)
        self.barrier_ratio = float(barrier_ratio)
        self.p = int(p)
        self.penalty_scale = float(penalty_scale)
        self.hard_violation_beta = float(hard_violation_beta)
        self.normal_sign = 1.0 if normal_sign >= 0 else -1.0
        self.normal_opposition_thre = float(normal_opposition_thre)

        self._neighbor_pairs: dict[int, torch.Tensor] = {}
        self._neighbor_mindist: dict[int, torch.Tensor] = {}

    def _selected_surface_ids(self, n_surface: int) -> list[int]:
        if self.surface_ids is None:
            return [i for i in range(max(self.surface_start, 0), n_surface)]
        return [i for i in self.surface_ids if 0 <= i < n_surface]

    @staticmethod
    def _surface_normals(rdu_sf: torch.Tensor) -> torch.Tensor:
        normal0 = torch.cross(rdu_sf[:, :, 1], rdu_sf[:, :, 0], dim=1)
        normals = normal0 / (normal0.norm(dim=1, keepdim=True) + 1e-12)
        return normals

    def _offset_points(self, r_sf: torch.Tensor, rdu_sf: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        normals = self._surface_normals(rdu_sf=rdu_sf)
        thickness = float(self.geometry.shell_thickness)
        return r_sf + self.normal_sign * thickness * normals, normals

    def initialize(self, r0, rdu0, *args, **kwargs) -> None:
        super().initialize(r0=r0, rdu0=rdu0, *args, **kwargs)

        self._neighbor_pairs = {}
        self._neighbor_mindist = {}

        import scipy.spatial

        thickness = float(self.geometry.shell_thickness)
        dmin = float(self.min_distance) if self.min_distance is not None else (2.0 * thickness)
        dmin = max(dmin, 1e-12)
        search_radius = max(dmin * self.search_ratio, dmin)

        for sf_idx in self._selected_surface_ids(len(r0)):
            roff, normals = self._offset_points(r_sf=r0[sf_idx], rdu_sf=rdu0[sf_idx])

            tree = scipy.spatial.KDTree(roff.detach().cpu().numpy())
            pairs_np = tree.query_pairs(r=search_radius, output_type='ndarray')
            if pairs_np.size == 0:
                continue

            pairs = torch.from_numpy(pairs_np.T).to(dtype=torch.int64, device=r0[sf_idx].device)

            dotn = (normals[pairs[0]] * normals[pairs[1]]).sum(dim=1)
            opposition = (-dotn).clamp(min=0.0)
            keep = opposition > self.normal_opposition_thre
            if keep.any():
                pairs = pairs[:, keep]
                self._neighbor_pairs[sf_idx] = pairs
                self._neighbor_mindist[sf_idx] = dmin * opposition[keep]

    def __call__(self, r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor], *args, **kwargs) -> torch.Tensor:
        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)

        if float(self.geometry.shell_thickness) <= 0:
            return loss

        thickness = float(self.geometry.shell_thickness)
        dmin = float(self.min_distance) if self.min_distance is not None else (2.0 * thickness)
        dmin = max(dmin, 1e-12)
        barrier_thre = max(dmin * self.barrier_thre_ratio, 1e-12)

        for sf_idx in self._selected_surface_ids(len(r)):
            pairs = self._neighbor_pairs.get(sf_idx, None)
            if pairs is None or pairs.numel() == 0:
                continue

            roff, _ = self._offset_points(r_sf=r[sf_idx], rdu_sf=rdu[sf_idx])
            delta = roff[pairs[0]] - roff[pairs[1]]
            dist = torch.sqrt((delta * delta).sum(dim=1) + 1e-18)

            mindist = self._neighbor_mindist[sf_idx].to(device=dist.device, dtype=dist.dtype)
            violation = mindist - dist + barrier_thre

            index, penalty = self.barrier_function(violation, barrier_thre, self.barrier_ratio, self.p)
            if index.numel() > 0:
                rel_violation = (violation[index] / barrier_thre).clamp(min=0.0)
                hard_boost = torch.exp((self.hard_violation_beta * (rel_violation - 1.0)).clamp(min=0.0, max=20.0))
                penalty_strong = self.penalty_scale * penalty * hard_boost

                w0 = self.scaler[sf_idx][pairs[0, index]]
                w1 = self.scaler[sf_idx][pairs[1, index]]
                loss = loss + (penalty_strong * w0 * w1).sum()

        return loss
