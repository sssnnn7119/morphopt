import torch
from ..BaseObj import BaseObj
from .....modelparams import Surfaces
from .....dlls import interface

class Distance(BaseObj):
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
        
        # prepare the normal vector for each surface
        normal0 = []
        for i in range(len(r0)):
            normal_vector = torch.cross(rdu0[i][:, 1], rdu0[i][:, 0], dim=0)
            normal_vector /= normal_vector.norm(dim=0)
            normal0.append(normal_vector.detach().clone())

        num_points_total = []
        index_Surf = []
        for i in range(len(r0)):
            index_Surf.append(torch.ones(r0[i].shape[1]) * i)
            num_points_total += [r0[i].shape[1]]

        normal0 = torch.cat(normal0, dim=1).type(torch.float32)
        
        self.points_surface_index = torch.cat(index_Surf,
                                              dim=0).type(torch.int64)

        
        # get the neighbor points
        self.neighbor_points = interface.get_distance_penalty(
            points=torch.cat(r0, dim=1).T,
            normal=normal0.T,
            surface_index=self.points_surface_index,
            distance_threshold=self.distance_threshold).T

        self.neighbor_points = torch.tensor(self.neighbor_points, dtype=torch.int64)

        # determine the minimum distance between the neighbor points
        self.neighbor_mindist = torch.zeros(self.neighbor_points.shape[1], dtype=torch.float32)
        for i in range(self.min_distance.shape[0]):
            for j in range(self.min_distance.shape[1]):
                # Find indices where points are from surface i and j
                index = torch.where(
                    (self.points_surface_index[self.neighbor_points[0]] == i) &
                    (self.points_surface_index[self.neighbor_points[1]] == j))[0]
                
                if len(index) > 0:
                    if i == j:  # Same surface case
                        # Use normal vector direction to determine distance for same surface
                        self.neighbor_mindist[index] = self.min_distance[i, j] * (-normal0[:, self.neighbor_points[0][index]] *
                            normal0[:, self.neighbor_points[1][index]]).sum(dim=0)
                    else:  
                        # Different surfaces
                        self.neighbor_mindist[index] = self.min_distance[i, j]

    def __call__(self, weight, r, rdu, rdu2, *args, **kwargs):

        R = torch.cat(r, dim=1).type(torch.float32)
        thre = 0.05
        degree = 3
        loss_distance = torch.tensor(0.0, dtype=torch.float32)
        weight_flatten = torch.cat(weight, dim=0).type(torch.float32)
        if torch.numel(self.neighbor_points) != 0:

            deltaR = R[:, self.neighbor_points[0]] - R[:,
                                                       self.neighbor_points[1]]
            distance = torch.sqrt(((deltaR)**2).sum(dim=0))

            dist = self.neighbor_mindist - distance + thre

            indexl, l = self.barrier_function(dist, thre, 0, degree)

            if len(indexl) > 0:
                loss_distance += (l * weight_flatten[self.neighbor_points[0, indexl]] *
                                  weight_flatten[self.neighbor_points[1, indexl]]).sum()
                
        return loss_distance
