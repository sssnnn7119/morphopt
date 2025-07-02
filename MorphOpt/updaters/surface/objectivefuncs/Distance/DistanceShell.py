import torch
from ..BaseObj import BaseObj
from .Distance import Distance as BaseDistance
from .....modelparams import Surfaces
from .....dlls import interface

class DistanceShell(BaseDistance):
    """
    Distance objective function for MorphOpt.
    """

    def __init__(self, min_distance: list[list[float]], shell_thickness: float = 0.01):
        """
        Initialize the Distance objective function with a name.
        """
        super().__init__(min_distance=min_distance)
        self.shell_thickness = shell_thickness
        """
        The thickness of the shell surfaces.
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
            index_Surf.append(torch.ones(r0[i].shape[1], dtype=torch.int32) * i)
            num_points_total += [r0[i].shape[1]]

        normal0 = torch.cat(normal0, dim=1).type(torch.float32)
        r = torch.cat(r0, dim=1).type(torch.float32)
        
        # copy the surface points with their offsets
        r1 = r + self.shell_thickness * normal0
        r = torch.cat((r, r1), dim=1)
        normal0 = torch.cat((normal0, normal0), dim=1)

        self.points_surface_index = torch.cat(index_Surf,
                                              dim=0).type(torch.int32)
        self.points_surface_index = torch.cat((self.points_surface_index, self.points_surface_index), dim=0)
        
        # get the neighbor points
        self.neighbor_points = interface.get_distance_penalty(
            points=r.T,
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
                        # if the points are from the same surface, we use the normal vector to determine the minimum distance
                        normal1 = normal0[:, self.neighbor_points[0][index]]
                        normal2 = normal0[:, self.neighbor_points[1][index]]

                        normal_dot = (1+(normal1 * normal2).sum(dim=0).abs())

                        distance_init = (r[:, self.neighbor_points[0][index]] - r[:, self.neighbor_points[1][index]]).norm(dim=0)

                        index_far_points = torch.where(distance_init > self.min_distance[i, j])[0]
                        index_too_close_points = torch.where(((distance_init <= self.min_distance[i, j] * 0.9) & ((normal1 * normal2).sum(dim=0)>-0.2)))[0]

                        # the points are from the same surface, but the first point is on the external side
                        self.neighbor_mindist[index] = torch.sqrt((self.min_distance[i, j])**2/2 * (normal_dot))


                        self.neighbor_mindist[index[index_far_points]] = self.min_distance[i, j]
                        self.neighbor_mindist[index[index_too_close_points]] = 0.
                    else:  
                        # Different surfaces
                        self.neighbor_mindist[index] = self.min_distance[i, j]

    def __call__(self, weight, r, rdu, rdu2, *args, **kwargs):

        R = torch.cat(r, dim=1).type(torch.float32)
        # prepare the normal vector for each surface
        normal = []
        for i in range(len(rdu)):
            normal_vector = torch.cross(rdu[i][:, 1], rdu[i][:, 0], dim=0)
            normal_vector /= normal_vector.norm(dim=0)
            normal.append(normal_vector.detach().clone())
        normal = torch.cat(normal, dim=1).type(torch.float32)
        R1 = R + self.shell_thickness * normal

        R = torch.cat((R, R1), dim=1)

        thre = 0.05
        degree = 4
        loss_distance = torch.tensor(0.0, dtype=torch.float32)
        weight_flatten = torch.cat(weight, dim=0).type(torch.float32)
        weight_flatten = torch.cat((weight_flatten, weight_flatten), dim=0)
        if torch.numel(self.neighbor_points) != 0:

            deltaR = R[:, self.neighbor_points[0]] - R[:,
                                                       self.neighbor_points[1]]
            distance = torch.sqrt(((deltaR)**2).sum(dim=0))

            dist = self.neighbor_mindist - distance + 2*thre

            indexl, l = self.barrier_function(dist, thre, 0, degree)

            if len(indexl) > 0:
                loss_distance += (l * weight_flatten[self.neighbor_points[0, indexl]] *
                                  weight_flatten[self.neighbor_points[1, indexl]]).sum()
                
        return loss_distance

