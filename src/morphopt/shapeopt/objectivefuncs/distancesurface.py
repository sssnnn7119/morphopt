
import torch
from .basefuncs import BaseConstraints
import logging

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

        self.min_distance = torch.tensor(min_distance).to(torch.float32)
        """
        The minimum distance between the surfaces.
            [i, j] the minimum distance between surface i and surface j.
        """

        self.distance_threshold = max(self.min_distance.flatten()).item() * 1.5
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
        
        # prepare the normal vector for each surface
        normal0 = []
        for i in range(len(r0)):
            normal_vector = torch.cross(rdu0[i][:, :, 1], rdu0[i][:, :, 0], dim=1)
            normal_vector /= normal_vector.norm(dim=1, keepdim=True)
            normal0.append(normal_vector.detach().clone())

        num_points_total = []
        index_Surf = []
        for i in range(len(r0)):
            index_Surf.append(torch.ones(r0[i].shape[0]) * i)
            num_points_total += [r0[i].shape[0]]

        normal0 = torch.cat(normal0, dim=0).type(torch.float32)
        
        self.points_surface_index = torch.cat(index_Surf,
                                              dim=0).type(torch.int64)

        r0_combined = torch.cat(r0, dim=0)
        
        # get the neighbor points
        import scipy.spatial
        kdtree = scipy.spatial.KDTree(r0_combined.cpu().numpy())
        self.neighbor_points = kdtree.query_pairs(r=self.distance_threshold, output_type='ndarray').T

        self.neighbor_points = torch.from_numpy(self.neighbor_points).type(torch.int64).to(r0[0].device)

        # determine the minimum distance between the neighbor points
        self.neighbor_mindist = torch.zeros(self.neighbor_points.shape[1], dtype=torch.float32)

        
        index_remain = torch.ones(self.neighbor_points.shape[1], dtype=torch.bool)

        for i in range(self.min_distance.shape[0]):
            for j in range(self.min_distance.shape[1]):
                # Find indices where points are from surface i and j
                index = torch.where(
                    (self.points_surface_index[self.neighbor_points[0]] == i) &
                    (self.points_surface_index[self.neighbor_points[1]] == j))[0]
                
                self.neighbor_mindist[index] = self.min_distance[i, j]

                if i == j:
                    distance0 = torch.sqrt(((r0_combined[self.neighbor_points[0, index]] - r0_combined[self.neighbor_points[1, index]])**2).sum(dim=1))
                    index_remain[index] = distance0 > self.distance_threshold * 0.3

        self.neighbor_points = self.neighbor_points[:, index_remain]
        self.neighbor_mindist = self.neighbor_mindist[index_remain]

        logger.debug(f"Distance Objective Function: {self.neighbor_points.shape[1]} point pairs within threshold {self.distance_threshold}")

    def __call__(self, r: list[torch.Tensor], rdu: list[torch.Tensor], *args, **kwargs):

        R = torch.cat(r, dim=0).type(torch.float32)
        RDU = torch.cat(rdu, dim=0).type(torch.float32)
        normal_vector = torch.cross(RDU[:, :, 1], RDU[:, :, 0], dim=1)

        thre = 0.01
        degree = 5
        loss_distance = torch.tensor(0.0, dtype=torch.float32)
        weight_flatten = torch.cat(self.scaler, dim=0).type(torch.float32)

        
        normal_min = -0.7
        normal_max = 0.0

        normal_remain = normal_vector[self.neighbor_points, :]
        normal_remain = normal_remain / (normal_remain.norm(dim=2, keepdim=True) + 1e-8)

        normal_penalty = (normal_remain[0] * normal_remain[1]).sum(dim=1)

        index_remain = normal_penalty < normal_max

        normal_penalty = normal_penalty[index_remain]
        neighbor_points = self.neighbor_points[:, index_remain]
        neighbor_mindist = self.neighbor_mindist[index_remain]

        if torch.numel(neighbor_points) != 0:

            deltaR = R[neighbor_points[0], :] - R[neighbor_points[1], :]
            distance = torch.sqrt(((deltaR)**2).sum(dim=1))

            dist = neighbor_mindist - distance + thre

            indexl, l = self.barrier_function(dist, thre, 0, degree)
            
            if len(indexl) > 0:
                



                normal_penalty = (normal_max - torch.clamp(normal_penalty[indexl], normal_min, normal_max)) / (normal_max - normal_min)

                loss_distance += (l * 
                                  (6 * normal_penalty**2 - 15 * normal_penalty + 10) * normal_penalty**3 *
                                  weight_flatten[neighbor_points[0, indexl]] *
                                  weight_flatten[neighbor_points[1, indexl]]).sum()
                
        return loss_distance
