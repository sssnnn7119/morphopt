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
        """
        Initialize the Distance objective function with a name.
        """
        super().__init__()

        self.neighbor_points: torch.Tensor
        """
        The neighbor points of the surfaces that need to be checked for distance.
        """

        self.points_surface_index: torch.Tensor
        """
        The index of the surfaces for each point.
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
        """
        Initialize the Distance objective function with the surface points and their derivatives.
        Parameters:
            r0 (list[torch.Tensor]): List of surface points.
            rdu0 (list[torch.Tensor]): List of surface point derivatives.
        """

        super().initialize(r0=r0, rdu0=rdu0, *args, **kwargs)

        r0_combined = torch.cat(r0, dim=0)
        if self.min_distance.shape != (len(r0), len(r0)):
            raise ValueError("min_distance must have one row and column per surface.")
        self.points_surface_index = torch.cat([
            torch.full((len(points),), index, dtype=torch.int64, device=points.device)
            for index, points in enumerate(r0)
        ])

        # get the neighbor points
        import scipy.spatial

        kdtree = scipy.spatial.KDTree(r0_combined.detach().cpu().numpy())
        self.neighbor_points = kdtree.query_pairs(
            r=self.distance_threshold, output_type="ndarray"
        ).T

        self.neighbor_points = (
            torch.from_numpy(self.neighbor_points).type(torch.int64).to(r0[0].device)
        )

        surface_ids = self.points_surface_index[self.neighbor_points]
        self.neighbor_mindist = self.min_distance.to(r0_combined)[surface_ids[0], surface_ids[1]]
        distance0 = (
            r0_combined[self.neighbor_points[0]] - r0_combined[self.neighbor_points[1]]
        ).norm(dim=1)
        index_remain = (surface_ids[0] != surface_ids[1]) | (
            distance0 > self.distance_threshold * CONSTANT.KERNEL.SHAPE_CONSTRAINTS.DISTANCE_PAIR_PRUNE_RATIO
        )

        self.neighbor_points = self.neighbor_points[:, index_remain]
        self.neighbor_mindist = self.neighbor_mindist[index_remain]

        logger.debug(
            f"Distance Objective Function: {self.neighbor_points.shape[1]} point pairs within threshold {self.distance_threshold}"
        )

    def __call__(self, r: list[torch.Tensor], rdu: list[torch.Tensor], *args, **kwargs):

        R = torch.cat(r, dim=0)
        RDU = torch.cat(rdu, dim=0)
        normal_vector = torch.cross(RDU[:, :, 1], RDU[:, :, 0], dim=1)

        thre = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.DISTANCE_BARRIER_THRESHOLD
        degree = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.DISTANCE_BARRIER_EXPONENT
        loss_distance = R.new_zeros(())
        weight_flatten = torch.cat(self.integration_weights, dim=0)

        normal_min = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.NORMAL_TRANSITION_MIN
        normal_max = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.NORMAL_TRANSITION_MAX

        normal_remain = normal_vector[self.neighbor_points, :]
        normal_remain = normal_remain / (
            normal_remain.norm(dim=2, keepdim=True)
            + CONSTANT.KERNEL.SHAPE_CONSTRAINTS.NORMALIZATION_TOLERANCE
        )

        normal_penalty = (normal_remain[0] * normal_remain[1]).sum(dim=1)

        index_remain = normal_penalty < normal_max

        normal_penalty = normal_penalty[index_remain]
        neighbor_points = self.neighbor_points[:, index_remain]
        neighbor_mindist = self.neighbor_mindist[index_remain]

        if torch.numel(neighbor_points) != 0:
            deltaR = R[neighbor_points[0], :] - R[neighbor_points[1], :]
            distance = torch.sqrt(((deltaR) ** 2).sum(dim=1))

            dist = neighbor_mindist - distance + thre
            reference_distance = torch.where(neighbor_mindist > 0, neighbor_mindist, thre)

            indexl, l = self.barrier_function(
                dist,
                thre,
                CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_RATIO,
                degree,
                transition_scale=reference_distance,
            )

            if len(indexl) > 0:
                normal_penalty = (
                    normal_max
                    - torch.clamp(normal_penalty[indexl], normal_min, normal_max)
                ) / (normal_max - normal_min)

                loss_distance += (
                    l
                    * (6 * normal_penalty**2 - 15 * normal_penalty + 10)
                    * normal_penalty**3
                    * weight_flatten[neighbor_points[0, indexl]]
                    * weight_flatten[neighbor_points[1, indexl]]
                ).sum()

        return loss_distance
