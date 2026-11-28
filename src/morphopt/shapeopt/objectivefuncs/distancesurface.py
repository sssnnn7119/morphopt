import logging

import torch

from ...constants import CONSTANT
from .basefuncs import BaseConstraints

logger = logging.getLogger(__name__)


class Distance(BaseConstraints):
    """
    Distance objective function for MorphOpt.
    """

    def __init__(self, min_distance: list[list[float]]):
        """Initialize the Distance objective function with a name.

        Args:
            min_distance (list[list[float]]): Required minimum surface separation in model length
                units.
        """
        super().__init__()

        self.neighbor_points: torch.Tensor
        """
        The neighbor points of the surfaces that need to be checked for distance.
        """

        self.neighbor_mindist: torch.Tensor
        """
        The allowable minimum distance between the points.
        """

        self.min_distance = torch.as_tensor(min_distance, dtype=torch.get_default_dtype())
        """
        The minimum distance between the surfaces.
            [i, j] the minimum distance between surface i and surface j.
        """

        self.distance_threshold = (
            max(self.min_distance.flatten()).item()
            * CONSTANT.KERNEL.SHAPE_CONSTRAINTS.DISTANCE_SEARCH_RATIO
        )
        """
        The distance threshold for the distance penalty.
        """

    def initialize(self, r0, rdu0, *args, **kwargs) -> None:
        """Initialize the Distance objective function with the surface points and their derivatives.

        Args:
            r0: List of surface points.
            rdu0: List of surface point derivatives.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """

        super().initialize(r0=r0, rdu0=rdu0, *args, **kwargs)

        r0_combined = torch.cat(r0, dim=0)
        if self.min_distance.shape != (len(r0), len(r0)):
            raise ValueError("min_distance must have one row and column per surface.")
        point_surfaces = torch.cat([
            torch.full((len(points),), index, dtype=torch.int64, device=points.device)
            for index, points in enumerate(r0)
        ])

        # get the neighbor points
        import scipy.spatial

        kdtree = scipy.spatial.KDTree(r0_combined.detach().cpu().numpy())
        pairs = torch.as_tensor(
            kdtree.query_pairs(r=self.distance_threshold, output_type="ndarray").T,
            device=r0_combined.device, dtype=torch.long,
        )
        settings = CONSTANT.KERNEL.SHAPE_CONSTRAINTS
        prune_radius = self.distance_threshold * settings.DISTANCE_PAIR_PRUNE_RATIO
        keep = []
        for first, second in pairs.split(settings.DISTANCE_PAIR_BATCH_SIZE, dim=1):
            separation = (r0_combined[first] - r0_combined[second]).norm(dim=1)
            keep.append((point_surfaces[first] != point_surfaces[second]) | (separation > prune_radius))
        self.neighbor_points = pairs[:, torch.cat(keep)]
        first, second = self.neighbor_points
        self.neighbor_mindist = self.min_distance.to(r0_combined)[
            point_surfaces[first], point_surfaces[second]
        ]

        logger.debug(
            f"Distance Objective Function: {self.neighbor_points.shape[1]} point pairs within threshold {self.distance_threshold}"
        )

    def __call__(self, r: list[torch.Tensor], rdu: list[torch.Tensor], *args, **kwargs):

        """Evaluate Distance for the supplied inputs.

        Args:
            r (list[torch.Tensor]): Current Cartesian surface samples; each surface block has shape
                (num_points, 3).
            rdu (list[torch.Tensor]): Current first surface derivatives; each block has shape
                (num_points, 3, 2).
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: Scalar tensor containing the area-weighted surface-separation penalty.
        """
        R = torch.cat(r, dim=0)
        RDU = torch.cat(rdu, dim=0)
        settings = CONSTANT.KERNEL.SHAPE_CONSTRAINTS
        normals = torch.cross(RDU[:, :, 1], RDU[:, :, 0], dim=1)
        normals = normals / (normals.norm(dim=1, keepdim=True) + settings.NORMALIZATION_TOLERANCE)

        # Orientation changes during the inner solve. Screen the current normals
        # in bounded batches and retain derivatives of the angular weight below.
        with torch.no_grad():
            facing = []
            for first, second in self.neighbor_points.split(settings.DISTANCE_PAIR_BATCH_SIZE, dim=1):
                dot = (normals[first] * normals[second]).sum(dim=1)
                facing.append(dot < settings.NORMAL_TRANSITION_MAX)
            indices = torch.cat(facing).nonzero(as_tuple=True)[0]

        first, second = self.neighbor_points[:, indices]
        required = self.neighbor_mindist[indices]
        threshold = settings.DISTANCE_BARRIER_THRESHOLD
        distance = torch.linalg.vector_norm(R[first] - R[second], dim=1)
        active, penalty = self.barrier_function(
            required - distance + threshold, threshold, settings.BARRIER_RATIO,
            settings.DISTANCE_BARRIER_EXPONENT,
            transition_scale=torch.where(required > 0, required, threshold),
        )
        first, second = first[active], second[active]
        dot = (normals[first] * normals[second]).sum(dim=1)
        low, high = settings.NORMAL_TRANSITION_MIN, settings.NORMAL_TRANSITION_MAX
        t = (high - dot.clamp(low, high)) / (high - low)
        angular_weight = (6 * t.square() - 15 * t + 10) * t.pow(3)
        weights = torch.cat(self.integration_weights)
        return (penalty * angular_weight * weights[first] * weights[second]).sum()
