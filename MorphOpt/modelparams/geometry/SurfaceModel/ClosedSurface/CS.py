import ctypes

import os
import time


import math
import numpy as np
import torch
from mayavi import mlab

import vtk

from ..Surface_Base import Surface_Base

current_path = os.path.dirname(os.path.abspath(__file__))

class ClosedSurface(Surface_Base):
    """
    This class is used to define the surface with SRBF
    """

    # region initialize

    def __init__(self,
                 seed_size: float = 0.5,
                 init_location: list[float] = [0.0, 0.0, 0.0],
                 flip=False,
                 symmetric: list[int] = [0, []]) -> None:
        """
        initialize the SRBF
        :param num_init_knot: number of initial knots
        :param symmetric: symmetry of the surface
        :return:
        """
        super(ClosedSurface, self).__init__(symmetric=symmetric)

        self.knots: torch.Tensor
        """
        knots: the knots of the SRBF in the reference coordinates
            shape: [num_knots, 3]
        """

        self.knots_element: torch.Tensor
        """
        knots_element: the elements of the knots
            shape: [num_elements, 3]
        """

        self.control_points: torch.Tensor
        """
        P0: the knots of the SRBF in the real coordinates
            shape: [3, num_knots]
        """

        self.threshold: torch.Tensor
        """
        threshold: the threshold of the SRBF
        """

        self.epsilon = 1e-10
        """
        epsilon: the initial distance
        """

        self.degree = 3
        """
        degree: the degree of the SRBF
        """

        self.seed_size = seed_size
        """
        knots_length_ref: the expected length of the knots in the real coordinates
        """

        self.flip = flip
        """
        flip: whether to flip the surface
        """

        self._init_location = torch.tensor(init_location)
        """
        init_location: the initial location of the surface
        """

        self.__c_dll = ctypes.CDLL(
            os.path.join(current_path, 'ClosedSurface.dll'))
        self.__c_dll.build_trees.restype = ctypes.POINTER(ctypes.c_void_p)
        """
        c_dll: the c++ dll
        """

        self._weight_tree: ctypes.c_void_p = None
        """
        weight_tree: the tree of the weights
        """

    def initialize(self, initial_surface_func: callable):

        self.control_points, self.knots = initial_surface_func()

        self.control_points = self.control_points + self._init_location.unsqueeze(
            1)

        self._symmetric_PdP0 = torch.ones([3, 1])
        if self._symmetric[0] == 1:
            ratio = torch.ones([3])
            for sym in self._symmetric[1]:
                ratio = ratio.reshape([3, -1]).unsqueeze(1).repeat(1, 2, 1)
                ratio[sym, 1, :] *= -1
            ratio = ratio.reshape([3, -1])
            self._symmetric_PdP0 = ratio

            index_remain = torch.ones([self.knots.shape[0]], dtype=torch.bool)
            for s in self._symmetric[1]:
                index_remain[self.knots[:, s] < 0.01] = False
            self.knots = self.knots[index_remain]
            self.control_points = self.control_points[:, index_remain]

        self.knots_element = self._sphere_mesh(
            (self.knots.unsqueeze(0).repeat(self._symmetric_PdP0.shape[1], 1,
                                            1) *
             self._symmetric_PdP0.T.unsqueeze(1)).reshape(-1, 3))
        self._reinitialize()

    def _reinitialize(self):

        # edges = self._get_edges(self.knots_element)
        # edges = np.array(edges.tolist())
        # edges_ptr = edges.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))

        # knots_now = self.knots

        # knots_now = knots_now.unsqueeze(
        #     0) * self._symmetric_PdP0.T.unsqueeze(1)
        # knots_now = knots_now.reshape([-1, 3])
        # knots = np.array(knots_now.tolist())
        # knots_ptr = knots.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

        # num_knots = knots.shape[0]
        # num_edges = edges.shape[0]

        # threshold = np.zeros(num_knots)
        # threshold_ptr = threshold.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

        # self.__c_dll.get_thresholds(threshold_ptr, edges_ptr, knots_ptr, num_edges, num_knots)

        # self.threshold = torch.tensor(threshold.tolist())
        # self.threshold = self.threshold[:self.control_points.shape[1]]
        knots_now = self.knots.cpu()

        knots_now = knots_now.unsqueeze(
            0) * self._symmetric_PdP0.cpu().T.unsqueeze(1)
        knots_now = knots_now.reshape([-1, 3])

        Y = knots_now

        x = (((Y.reshape([1, -1, 3]) -
               Y.reshape([-1, 1, 3]))**2).sum(dim=-1)).sort(dim=1).values

        threshold0 = x[:, 30].to(self.knots.device)
        self.threshold = threshold0[:self.control_points.shape[1]]

        self._get_weights_c_build_trees(knots_now, threshold0)

    # endregion

    # region map function
    def map(self, Coordinates: torch.Tensor = None) -> torch.Tensor:
        """
        ref_coordinates: reference coordinates
            shape: [3, num_points]
        """
        if Coordinates is None:
            Coordinates = self.pre_nodes
        
        control_points, knots, threshold = self.symmetrize_knots_CPs()

        indices, weights_values = self._get_weights(knots, threshold,
                                                    Coordinates)

        Wsum = torch.zeros(Coordinates.shape[1]).scatter_add_(
            dim=0, index=indices[1], src=weights_values)

        Rweight0 = control_points[:, indices[0]] * weights_values

        RW = self._sparse_sum(indices,
                              Rweight0,
                              numel_output=Coordinates.shape[1])
        r = RW / Wsum

        return r

    def _get_weights_c_build_trees(self, knots: torch.Tensor,
                                   threshold: torch.Tensor):
        t0 = time.time()
        # for c++ code
        num_knots = knots.shape[0]

        _knots = np.array(knots.tolist())

        _threshold = np.array(threshold.tolist())

        _knots_ptr = _knots.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))

        _threshold_ptr = _threshold.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))

        if self._weight_tree is None:
            self.__c_dll.delete_trees(self._weight_tree)
        self._weight_tree = self.__c_dll.build_trees(
            _knots_ptr, _threshold_ptr, ctypes.c_double(self.epsilon),
            num_knots)

    def _get_weights_c(self,
                       knots: torch.Tensor,
                       threshold: torch.Tensor,
                       ref_points: torch.Tensor,
                       build_trees: bool = False):
        """
        return the weights of the reference points
        """
        t0 = time.time()
        # for c++ code
        num_knots = knots.shape[0]
        num_nodes = ref_points.shape[1]
        result_sum = np.zeros([1], dtype=int)

        _knots = np.array(knots.tolist())
        _nodes = np.array(ref_points.T.tolist())
        _threshold = np.array(threshold.tolist())

        _knots_ptr = _knots.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))

        _nodes_ptr = _nodes.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))

        _threshold_ptr = _threshold.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))

        result_ptr = result_sum.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
        t1 = time.time()
        # print('prepare data:', t1 - t0)
        if build_trees:
            self._get_weights_c_build_trees(knots, threshold)

        t2 = time.time()

        self.__c_dll.cal_weights(self._weight_tree, _knots_ptr,
                                 _nodes_ptr, _threshold_ptr,
                                 ctypes.c_double(self.epsilon), num_knots,
                                 num_nodes, result_ptr)
        t3 = time.time()
        # print('cal weights:', t3 - t2)
        indices = torch.zeros([2, result_sum[0]],
                              dtype=torch.int32,
                              device='cpu')
        indices_result = indices.numpy()

        indices_result_ptr = indices_result.ctypes.data_as(
            ctypes.POINTER(ctypes.c_int32))
        self.__c_dll.get_weights(indices_result_ptr)
        t4 = time.time()
        # print('get weights:', t4 - t3)
        indices = indices.to(self.knots.device).to(torch.int64)

        return indices

    def _get_weights_torch(self, knots: torch.Tensor, threshold: torch.Tensor,
                           ref_points: torch.Tensor):

        device = knots.device

        knots = knots.T

        d = ref_points.reshape([3, 1, -1]) - knots.unsqueeze(-1)
        # D = torch.sqrt((d**2).sum(dim=0) + self.epsilon)
        D = (d**2).sum(dim=0)

        weight = (threshold.unsqueeze(1) - D) / (threshold).unsqueeze(1)
        weight = torch.nn.functional.relu(weight)
        weight = weight.to_sparse_coo()

        indices = weight.indices()
        values = weight.values()

        return indices, D.flatten()[indices[0] * ref_points.shape[1] +
                                    indices[1]]

    def _get_weights(self,
                     knots: torch.Tensor,
                     threshold: torch.Tensor,
                     ref_points: torch.Tensor,
                     derivative: int = 0):

        y = ref_points
        Y = knots

        if ref_points.shape[1] * knots.shape[0] > 1e5:
            indices = self._get_weights_c(Y, threshold, y)
            D = ((y[:, indices[1]] - Y[indices[0]].T)**2).sum(dim=0)

        else:
            indices, D = self._get_weights_torch(Y, threshold, y)

        threshold_flatten = threshold[indices[0]]
        DD = (threshold_flatten - D)
        ind_remain = DD > 0
        indices = indices[:, ind_remain]
        D = D[ind_remain]
        threshold_flatten = threshold[indices[0]]

        weight0 = (threshold_flatten - D) / (threshold_flatten)

        weight = weight0**self.degree

        if derivative == 0:
            return indices, weight

        delta = y[:, indices[1]] - Y[indices[0]].T

        Ddx = delta * 2

        wdx = -self.degree / (threshold_flatten) * weight / weight0 * Ddx

        if derivative == 1:
            return indices, weight, wdx

        Ddx2 = torch.eye(3).reshape([3, 3, 1]) * 2

        wdx2 = self.degree * (self.degree - 1) / (threshold_flatten)**2 * weight / weight0**2 * torch.einsum('ip,jp->ijp',Ddx,Ddx) \
            - self.degree / (threshold_flatten) * weight / weight0 * Ddx2

        return indices, weight, wdx, wdx2

    def symmetrize_knots_CPs(self, derivative: int = 0):

        control_points = self.control_points - self._init_location.unsqueeze(1)
        knots = self.knots
        threshold = self.threshold
        if self._symmetric[0] == 1:
            control_points = control_points.unsqueeze(1).repeat(
                1, self._symmetric_PdP0.shape[1],
                1) * self._symmetric_PdP0.unsqueeze(-1)
            knots = knots.unsqueeze(0).repeat(
                self._symmetric_PdP0.shape[1], 1,
                1) * self._symmetric_PdP0.T.unsqueeze(1)
            threshold = threshold.unsqueeze(0).repeat(
                self._symmetric_PdP0.shape[1], 1)

        control_points = control_points.reshape(
            3, -1) + self._init_location.unsqueeze(1)
        knots = knots.reshape(-1, 3)
        threshold = threshold.reshape(-1)

        return control_points, knots, threshold

    def unsymmetrical(self):
        self.control_points, self.knots, self.threshold = self.symmetrize_knots_CPs(
        )
        self._symmetric = [0, [0]]
        self._symmetric_PdP0 = torch.ones([3, 1])

    def _partial_derivative(self,
                            ref_points: torch.Tensor = None,
                            controlpoints: bool = False,
                            derivative: int = 0):
        """
        return the partial derivtive to u,v
            Ru, Rv, Ruu, Ruv, Rvv
        """
        if ref_points is None:
            ref_points = self.pre_nodes
            refspartial = self._partial_derivative_refSphere(
                derivative=derivative, controlpoints=controlpoints)
        else:
            refspartial = self._partial_derivative_refSphere(
                ref_points=ref_points,
                controlpoints=controlpoints,
                derivative=derivative)

        if derivative == 0:
            r = refspartial
        else:
            r = refspartial[0][0]
        output = [[r]]
        if derivative >= 1:
            rdx = refspartial[0][1]
            xdu = torch.zeros([3, 2, ref_points.shape[1]])
            xdu[0, 0] = -ref_points[1]
            xdu[0, 1] = ref_points[0] * ref_points[2] / torch.sqrt(
                1 - ref_points[2]**2)
            xdu[1, 0] = ref_points[0]
            xdu[1, 1] = ref_points[1] * ref_points[2] / torch.sqrt(
                1 - ref_points[2]**2)
            xdu[2, 1] = -torch.sqrt(1 - ref_points[2]**2)
            rdu = torch.einsum('ilp, lup->iup', rdx, xdu)
            output[0].append(rdu)
        if derivative >= 2:
            rdx2 = refspartial[0][2]
            xdu2 = torch.zeros([3, 2, 2, ref_points.shape[1]])
            xdu2[0, 1, 1] = -ref_points[0]
            xdu2[0, 1, 0] = -xdu[1, 1]
            xdu2[0, 0, 0] = -ref_points[0]
            xdu2[0, 0, 1] = -xdu[1, 1]
            xdu2[1, 0, 0] = -ref_points[1]
            xdu2[1, 0, 1] = xdu[0, 1]
            xdu2[1, 1, 0] = xdu[0, 1]
            xdu2[1, 1, 1] = -ref_points[1]
            xdu2[2, 1, 1] = -ref_points[2]
            rdu2 = torch.einsum('ilmp, lup, mvp->iuvp', rdx2,
                                xdu, xdu) + torch.einsum(
                                    'ilp, luvp->iuvp', rdx, xdu2)
            output[0].append(rdu2)

        if controlpoints:
            indices = refspartial[1][0]
            controlpoints_derivative = [indices, refspartial[1][1]]
            if derivative >= 1:
                rdxdot = refspartial[1][2]
                rdudot = torch.einsum('lp, lup->up', rdxdot, xdu[:, :,
                                                                 indices[1]])
                controlpoints_derivative += [rdudot]
            if derivative >= 2:
                rdx2dot = refspartial[1][3]
                rdu2dot = torch.einsum(
                    'lmp, lup, mvp->uvp', rdx2dot, xdu[:, :, indices[1]],
                    xdu[:, :, indices[1]]) + torch.einsum(
                        'lp, luvp->uvp', rdxdot, xdu2[:, :, :, indices[1]])
                controlpoints_derivative += [rdu2dot]

            output += [controlpoints_derivative]
        return output

    def _partial_derivative_refSphere(self,
                                      ref_points: torch.Tensor = None,
                                      controlpoints: bool = False,
                                      derivative: int = 0):
        """
        type: list of type of the partial derivative
            'spartial': partial derivative to the reference coordinates
            'controlpoints': partial derivative to the control points
        """

        control_points, knots, threshold = self.symmetrize_knots_CPs()

        # get the basic data
        if ref_points is None:
            # using the pre-calculated data
            num_output = self.pre_nodes.shape[1]
            indices = self.pre_indices
            weight_values = self.pre_weight_values
            Wsum = self.pre_Wsum
            Wsumdx = self.pre_Wsumdx
            Wsumdx2 = self.pre_Wsumdx2
            Wdx_values = self.pre_Wdx_values
            Wdx2_values = self.pre_Wdx2_values
        else:
            # re calculate the data
            num_output = ref_points.shape[1]
            # determine the sparse indices and values
            result = self._get_weights(knots,
                                       threshold,
                                       ref_points,
                                       derivative=derivative)

            indices = result[0]
            weight_values = result[1]

            # prepare the weight values
            Wsum = torch.zeros(ref_points.shape[1]).scatter_add_(
                dim=0, index=indices[1], src=weight_values)
            Knots_expension = knots[indices[0]].transpose(0, 1)

            if derivative >= 1:
                Wdx_values = result[2]
                Wsumdx = self._sparse_sum(indices,
                                          Wdx_values,
                                          numel_output=ref_points.shape[1])

            if derivative >= 2:
                Wdx2_values = result[3]
                Wsumdx2 = self._sparse_sum(indices,
                                           Wdx2_values,
                                           numel_output=num_output)

        Rweight0 = control_points[:, indices[0]] * weight_values

        RW = self._sparse_sum(indices, Rweight0, numel_output=num_output)
        r = RW / Wsum

        if derivative == 0:
            return r

        # get the expension of each component
        Wsum_expension = Wsum[indices[1]]
        P0_expension = control_points[:, indices[0]]

        # determine the output
        spartial = [r]

        spartial_derivative = []
        if derivative >= 1:
            # get the first partial derivative

            RWdx_values = torch.einsum('ip, mp->imp', P0_expension, Wdx_values)
            RWdx = self._sparse_sum(indices,
                                    RWdx_values,
                                    numel_output=num_output)
            rdx = (RWdx -
                   torch.einsum('ip, mp->imp', RW, Wsumdx) / Wsum) / Wsum
            spartial_derivative += [rdx]
        if derivative >= 2:
            # get the second partial derivative

            rdx2 = torch.einsum('ip, mnp->imnp', P0_expension, Wdx2_values)
            rdx2 = self._sparse_sum(
                indices, rdx2, numel_output=num_output) / Wsum - torch.einsum(
                    'mnp, ip->imnp', Wsumdx2, RW) / Wsum**2

            A = torch.einsum('imp, np->imnp', RWdx, Wsumdx)
            B = -A - A.transpose(1, 2) + 2 * torch.einsum(
                'ip,mp,np->imnp', RW, Wsumdx, Wsumdx) / Wsum
            rdx2 = rdx2 + B / Wsum**2

            spartial_derivative += [rdx2]

        spartial += spartial_derivative
        output = [spartial]
        if controlpoints:

            controlpoints_derivative = [
                indices, weight_values / Wsum_expension
            ]

            if derivative >= 1:
                # get the first partial derivative

                rdxdot = Wdx_values / Wsum_expension - weight_values * Wsumdx[:, indices[
                    1]] / Wsum_expension**2

                controlpoints_derivative += [rdxdot]

            if derivative >= 2:
                rdx2dot = Wdx2_values / Wsum_expension - weight_values * Wsumdx2[:, :, indices[
                    1]] / Wsum_expension**2

                Adot = torch.einsum('ip, np->inp', Wdx_values,
                                    Wsumdx[:, indices[1]])
                Bdot = -Adot - Adot.transpose(0, 1) + 2 * torch.einsum(
                    'p,mp,np->mnp', weight_values, Wsumdx[:, indices[1]],
                    Wsumdx[:, indices[1]]) / Wsum_expension
                rdx2dot = rdx2dot + Bdot / Wsum_expension**2

                controlpoints_derivative += [rdx2dot]
            output += [controlpoints_derivative]
        return output

    def get_surface_value(self,
                          ref_points: torch.Tensor = None,
                          derivatives: int = 0):
        """
        
        """
        if ref_points is None:
            ref_points = self.pre_nodes
            partial_derivative = self._partial_derivative(
                derivative=2, controlpoints=derivatives > 0)
        else:
            partial_derivative = self._partial_derivative(
                ref_points=ref_points,
                derivative=2,
                controlpoints=derivatives > 0)

        r, rdu, rdu2 = partial_derivative[0]
        if derivatives > 0:
            indices, rdot, rdudot, rdu2dot = partial_derivative[1]

        geo_values = self._get_geometric_values(partial_derivative,
                                                derivatives=derivatives)

        result = []
        if derivatives >= 0:
            [Normal0, I, detI, invI, II, detII, H, K, C] = geo_values[0]

            result.append([r, rdu, rdu2, Normal0, C])
        if derivatives >= 1:
            Normaldru, Idru, detIdI, invIdI, IIdru, IIdru2, detIIdII, Cdru, Cdru2 = geo_values[
                1]
            result.append([rdot, rdudot, rdu2dot, indices, Cdru, Cdru2])
        if derivatives >= 2:
            Normaldru_2, Idru_2, detIdI_2, invIdI_2, IIdru_2, IIdrudru2, detIIdII_2, Cdru_2, Cdrudru2, Cdru2_2 = geo_values[
                2]
            result.append([Cdru_2, Cdrudru2, Cdru2_2])

        return result

    def pre_load(self,
                 num_points: int = 0,
                 pre_nodes: torch.Tensor = None,
                 pre_elements: torch.Tensor = None):

        if pre_nodes is None and pre_elements is None:
            if num_points > 0:
                self.pre_nodes, self.pre_elements = self.Sphere_Mesh(
                    num_points, 3)
            else:
                knots = self.symmetrize_knots_CPs()[1]
                knots_mid = torch.sum(
                    knots.T[:, self.knots_element.view(-1)].reshape(3, -1, 3),
                    dim=-1) / 3
                knots_mid = knots_mid / knots_mid.norm(dim=0)
                # self.pre_nodes = knots.T
                self.pre_nodes = torch.cat([knots.T, knots_mid], dim=1)

                self.pre_elements = torch.cat([
                    torch.stack([
                        torch.arange(self.knots_element.shape[0]) +
                        knots.shape[0], self.knots_element[:, 0],
                        self.knots_element[:, 1]
                    ],
                                dim=1),
                    torch.stack([
                        torch.arange(self.knots_element.shape[0]) +
                        knots.shape[0], self.knots_element[:, 1],
                        self.knots_element[:, 2]
                    ],
                                dim=1),
                    torch.stack([
                        torch.arange(self.knots_element.shape[0]) +
                        knots.shape[0], self.knots_element[:, 2],
                        self.knots_element[:, 0]
                    ],
                                dim=1)
                ],
                                              dim=0)

                # self.pre_elements = self.knots_element
                r = self.map(self.pre_nodes)
                self.pre_elements = self._refine_triangular_mesh(
                    r.T, self.pre_elements)

        else:
            self.pre_nodes = pre_nodes
            self.pre_elements = pre_elements

        self.pre_edges = self._get_edges(self.pre_elements)

        control_points, knots, threshold = self.symmetrize_knots_CPs()

        self.pre_indices, self.pre_weight_values, self.pre_Wdx_values, self.pre_Wdx2_values = self._get_weights(
            knots, threshold, self.pre_nodes, derivative=2)

        self.pre_Wsum = self._sparse_sum(self.pre_indices,
                                         self.pre_weight_values,
                                         numel_output=self.pre_nodes.shape[1])

        self.pre_Wsumdx = self._sparse_sum(
            self.pre_indices,
            self.pre_Wdx_values,
            numel_output=self.pre_nodes.shape[1])

        self.pre_Wsumdx2 = self._sparse_sum(
            self.pre_indices,
            self.pre_Wdx2_values,
            numel_output=self.pre_nodes.shape[1])

    def refine_surface(self):
        self._refine_surface_reseed()
        self._refine_knots()
        self._reinitialize()

        # optimize the surface to minimize the matching error
        self._refine_P0_newton()

        self.pre_load()

    # endregion

    # region: initial surface
    class _initial_surface:

        @staticmethod
        def sphere(radius: float, seed_size: float, flip: bool = False):
            num_points = round(4 * math.pi * radius**2 /
                               (1.732 * seed_size**2) * 2)
            num_points = max(400, num_points)

            knots = ClosedSurface.fibonacci_grid(num_points, dimen=3).T

            ref_points_out = knots * radius
            control_points = ref_points_out.transpose(0, 1)

            if flip:
                control_points[0] = -control_points[0]

            return control_points, knots

        @staticmethod
        def cylinder(radius: float,
                     height: float,
                     seed_size: float,
                     flip: bool = False):
            num_points = round(
                (2 * math.pi * radius * height + 2 * math.pi * radius**2) /
                (1.732 * seed_size**2) * 2)
            num_points = max(100, num_points)

            threshold = (height / 1.2) / (height + radius * 2)

            knots = ClosedSurface.fibonacci_grid(num_points, dimen=3).T

            phi0 = (torch.acos(knots[:, 2]) - math.pi / 2) / (math.pi / 2)

            index_lateral = (phi0.abs() < threshold)
            index_head = ~index_lateral & (phi0 >= 0)
            index_bottom = ~index_lateral & (phi0 <= 0)

            theta = torch.atan2(knots[index_lateral, 1], knots[index_lateral,
                                                               0])
            phi = phi0[index_lateral]
            phi = phi / phi.abs().max()

            control_points = torch.zeros([3, num_points])
            control_points[0, index_lateral] = radius * torch.cos(theta)
            control_points[1, index_lateral] = radius * torch.sin(theta)
            control_points[2, index_lateral] = height * phi / 2

            control_points[0, index_head] = knots[index_head, 0] / math.cos(
                threshold * math.pi / 2) * radius
            control_points[1, index_head] = knots[index_head, 1] / math.cos(
                threshold * math.pi / 2) * radius
            control_points[2, index_head] = height / 2

            control_points[0,
                           index_bottom] = knots[index_bottom, 0] / math.cos(
                               threshold * math.pi / 2) * radius
            control_points[1,
                           index_bottom] = knots[index_bottom, 1] / math.cos(
                               threshold * math.pi / 2) * radius
            control_points[2, index_bottom] = -height / 2

            if not flip:
                control_points[0] = -control_points[0]

            return control_points, knots

    # endregion

    # region: mesh operation
    # methods to get points on the sphere

    def _init_surface_grids(self, N):

        grids = self.knots.T
        elems = self.knots_element
        while True:

            grids_now = grids.unsqueeze(1) * self._symmetric_PdP0.unsqueeze(-1)
            grids_now = grids_now.reshape([3, -1])

            if abs(grids_now.shape[1] - N) <= 10:
                break

            r = self._partial_derivative_refSphere(ref_points=grids_now)
            elems = self._sphere_mesh(grids_now.T)
            elems = self._refine_triangular_mesh(r.T, elems)

            index_remain = (elems < grids.shape[1]).all(dim=1)
            elems_now = elems[index_remain]

            area = torch.cross(r[:, elems_now[:, 1]] - r[:, elems_now[:, 0]],
                               r[:, elems_now[:, 2]] - r[:, elems_now[:, 0]],
                               dim=0).norm(dim=0) / 2
            grids_mid = (grids[:, elems_now[:, 0]] + grids[:, elems_now[:, 1]]
                         + grids[:, elems_now[:, 2]]) / 3
            grids_mid = grids_mid / grids_mid.norm(dim=0)

            if grids_now.shape[1] < N - 10:
                grids = torch.cat([
                    grids, grids_mid[:,
                                     area.argsort()[round(
                                         (grids_now.shape[1] - N) /
                                         self._symmetric_PdP0.shape[0]):]]
                ],
                                  dim=1)
            elif grids_now.shape[1] > N + 10:
                edges = self._get_edges(elems_now)
                length = (r[:, edges[:, 0]] - r[:, edges[:, 1]]).norm(dim=0)
                ind = length.argsort()[:round((grids_now.shape[1] - N) /
                                              self._symmetric_PdP0.shape[0])]

                edges_now = edges[ind]
                index = 0
                while True:
                    if index == edges_now.shape[0]:
                        break

                    index_remain = ((edges_now == edges_now[index, 0]) |
                                    (edges_now == edges_now[index, 1])).sum(
                                        dim=1) == 0
                    index_remain[:index + 1] = True
                    edges_now = edges_now[index_remain]

                    index += 1

                grids_add = (grids[:, edges_now[:, 0]] +
                             grids[:, edges_now[:, 1]]) / 2
                grids_add = grids_add / grids_add.norm(dim=0)

                index_remain = torch.ones([grids.shape[1]], dtype=torch.bool)
                index_remain[edges_now.flatten()] = False

                grids = torch.cat([grids[:, index_remain], grids_add], dim=1)

        return grids

    def _refine_surface_reseed(self):

        # self.pre_load()
        knots = self.symmetrize_knots_CPs(derivative=0)[1]

        r = self.get_surface_value(ref_points=knots.T, derivatives=0)[0][0]

        rr = torch.zeros([
            self.knots_element.shape[0],
            3,
            3,
        ])
        rr[:, 0] = r[:, self.knots_element[:, 0]].T
        rr[:, 1] = r[:, self.knots_element[:, 1]].T
        rr[:, 2] = r[:, self.knots_element[:, 2]].T

        area = (torch.cross(rr[:, 1] - rr[:, 0], rr[:, 2] - rr[:, 0],
                            dim=1).norm(dim=1) / 2)

        num_points = round(area.sum().item() / (1.732 * self.seed_size**2 / 2))
        num_points = max(num_points, 400)

        knots_new = self._init_surface_grids(num_points).T

        PdP0 = torch.ones([3, 1])
        if self._symmetric[0] == 1:
            for s in self._symmetric[1]:
                index_remain_nodes = (knots_new[:, s] > 0)
                knots_new = knots_new[index_remain_nodes]

        if self._symmetric[0] == 1:

            knots_new = knots_new.unsqueeze(0).repeat(
                self._symmetric_PdP0.shape[1], 1,
                1) * self._symmetric_PdP0.T.unsqueeze(1)
            PdP0 = self._symmetric_PdP0

        knots_new = knots_new.reshape([-1, 3])
        # knots_element_new = self.knots_element
        knots_element_new = self._sphere_mesh(knots_new)
        knots_new_2 = knots_new.clone()
        a = knots_element_new
        # t0 = time.time()
        for i in range(3):
            r = self._partial_derivative_refSphere(ref_points=knots_new_2.T,
                                                   derivative=0)
            a = self._refine_triangular_mesh(nodes=r.T, elems=a)

            knots_new_2 = self._refine_mesh(knots_new_2.T, PdP0, a, order=4).T

        knots_new_2, a = self._refine_mesh_post_process(knots_new_2.T)
        knots_new_2 = knots_new_2.T
        knots_new_2 = self._refine_mesh(knots_new_2.T, PdP0, a, order=4).T
        r = self._partial_derivative_refSphere(ref_points=knots_new_2.T,
                                               derivative=0)
        knots_element_new = self._refine_triangular_mesh(nodes=r.T, elems=a)

        # define the initial P0 and knots for the new surface
        result = self.get_surface_value(ref_points=knots_new_2.T,
                                        derivatives=0)
        r_ref = result[0][0]

        self.control_points = result[0][0].reshape(
            [3, PdP0.shape[1], -1])[:, 0]
        self.knots_element = knots_element_new
        self.knots = knots_new_2
        self.knots = self.knots.reshape([PdP0.shape[1], -1, 3])[0]

    def _refine_mesh(self,
                     point_sphere: torch.Tensor,
                     PdP0: torch.Tensor,
                     elements: torch.Tensor,
                     order=3):

        r = self._partial_derivative_refSphere(point_sphere)
        re0 = r[:, elements[:, 0]]
        re1 = r[:, elements[:, 1]]
        re2 = r[:, elements[:, 2]]
        V = (torch.cross(re0, re1, dim=0) * re2).sum().abs()

        point_sphere = point_sphere.reshape([3, PdP0.shape[1], -1])[:, 0]
        point_now = point_sphere.clone()
        edges = self._get_edges(elements)

        edges = self.__symmetric_edges(edges, point_sphere.shape[1])

        epsilon = torch.zeros([3, 3, 3])
        epsilon[0, 1, 2] = epsilon[1, 2, 0] = epsilon[2, 0, 1] = 1
        epsilon[0, 2, 1] = epsilon[2, 1, 0] = epsilon[1, 0, 2] = -1

        for step in [1, -1]:

            design_variables = torch.zeros([2, point_now.shape[1]])
            design_variables[0] = 2 * point_now[0] / (1 - step * point_now[2])
            design_variables[1] = 2 * point_now[1] / (1 - step * point_now[2])

            if step == 1:
                index_boundary = torch.where(
                    design_variables.norm(dim=0) > 10)[0].tolist()
                index_remain = torch.tensor(
                    list(set(range(point_now.shape[1])) - set(index_boundary)))

            if step == -1:
                index_boundary = torch.where(
                    design_variables.norm(dim=0) > 10)[0].tolist()
                index_remain = torch.tensor(
                    list(set(range(point_now.shape[1])) - set(index_boundary)))

            if len(index_remain) == 0:
                continue

            index_remain_elements = torch.isin(
                elements.flatten() % design_variables.shape[1],
                index_remain).reshape([-1, 3]).sum(dim=1) == 3
            elements_now = elements[index_remain_elements]

            index_remain_edges = torch.isin(
                edges.flatten() % design_variables.shape[1],
                index_remain).reshape([-1, 2]).sum(dim=1) == 2
            edges_inside = edges[index_remain_edges]
            index_remain_edges = torch.isin(
                edges.flatten() % design_variables.shape[1],
                index_remain).reshape([-1, 2]).sum(dim=1) == 1
            edges_boundary = edges[index_remain_edges]
            edges_now = torch.cat(
                [edges_inside, edges_boundary, edges_boundary], dim=0)

            num_points = design_variables.shape[1]

            low_count = 0
            alpha = 1

            def closure_edge_length(r, derivatives=0):

                edge_length2 = torch.sum(
                    (r[:, edges[:, 0]] - r[:, edges[:, 1]])**2, dim=0).sqrt()

                loss = (edge_length2**order).sum()

                if derivatives == 0:
                    return [loss]

                Ldl = order * edge_length2**(order - 1)

                ldre = (r[:, edges[:, 0]] - r[:, edges[:, 1]]) / edge_length2
                values_1 = Ldl * ldre

                Ldr = torch.zeros([3, r.shape[1]])
                Ldr.scatter_add_(1, edges[:, 0].unsqueeze(0).repeat(3, 1),
                                 values_1)
                Ldr.scatter_add_(1, edges[:, 1].unsqueeze(0).repeat(3, 1),
                                 -values_1)

                if derivatives == 1:
                    return loss, Ldr

                Ldl_2 = order * (order - 1) * edge_length2**(order - 2)
                ldre_2 = torch.eye(3).reshape(3, 3, 1) / edge_length2 + \
                        -torch.einsum('ip, jp->ijp', ldre, ldre) / edge_length2

                values_2 = Ldl_2 * torch.einsum('ip,jp->ijp', ldre,
                                                ldre) + Ldl * ldre_2
                # diag
                Ldr2_values = [values_2.flatten(), values_2.flatten()]

                # cross item
                Ldr2_values += [-values_2.flatten(), -values_2.flatten()]

                Ldr2_values = torch.cat(Ldr2_values, dim=-1)

                # region : define the indices
                # diag
                Ldr2_indices0 = [
                    torch.stack([
                        torch.tensor([0, 1, 2]).reshape([3, 1, 1]).repeat([
                            1, 3, edges.shape[0]
                        ]), edges[:, 0].reshape([1, 1, -1]).repeat([3, 3, 1]),
                        torch.tensor([0, 1, 2]).reshape([1, 3, 1]).repeat([
                            3, 1, edges.shape[0]
                        ]), edges[:, 0].reshape([1, 1, -1]).repeat([3, 3, 1])
                    ],
                                dim=0).reshape([4, -1]),
                    torch.stack([
                        torch.tensor([0, 1, 2]).reshape([3, 1, 1]).repeat([
                            1, 3, edges.shape[0]
                        ]), edges[:, 1].reshape([1, 1, -1]).repeat([3, 3, 1]),
                        torch.tensor([0, 1, 2]).reshape([1, 3, 1]).repeat([
                            3, 1, edges.shape[0]
                        ]), edges[:, 1].reshape([1, 1, -1]).repeat([3, 3, 1])
                    ],
                                dim=0).reshape([4, -1]),
                ]

                # cross item
                Ldr2_indices0 += [
                    torch.stack([
                        torch.tensor([0, 1, 2]).reshape([3, 1, 1]).repeat(
                            [1, 3, edges.shape[0]]), edges[:, 0].reshape(
                                [1, 1, edges.shape[0]]).repeat([3, 3, 1]),
                        torch.tensor([0, 1, 2]).reshape([1, 3, 1]).repeat(
                            [3, 1, edges.shape[0]]), edges[:, 1].reshape(
                                [1, 1, edges.shape[0]]).repeat([3, 3, 1])
                    ],
                                dim=0).reshape([4, -1]),
                    torch.stack([
                        torch.tensor([0, 1, 2]).reshape([3, 1, 1]).repeat(
                            [1, 3, edges.shape[0]]), edges[:, 1].reshape(
                                [1, 1, edges.shape[0]]).repeat([3, 3, 1]),
                        torch.tensor([0, 1, 2]).reshape([1, 3, 1]).repeat(
                            [3, 1, edges.shape[0]]), edges[:, 0].reshape(
                                [1, 1, edges.shape[0]]).repeat([3, 3, 1])
                    ],
                                dim=0).reshape([4, -1]),
                ]
                Ldr2_indices = torch.cat(Ldr2_indices0, dim=-1)

                # endregion

                Ldr2 = torch.sparse_coo_tensor(Ldr2_indices, Ldr2_values,
                                               [3, r.shape[1], 3, r.shape[1]])

                return loss, Ldr, Ldr2

            def closure_points_mid(r, derivatives=0):

                re = r[:, elements_now.flatten()].reshape([3, -1, 3])

                loss = 2 / 3 * ((re[:, :, 0]**2).sum(dim=0) +
                                (re[:, :, 1]**2).sum(dim=0) +
                                (re[:, :, 2]**2).sum(dim=0) -
                                (re[:, :, 0] * re[:, :, 1]).sum(dim=0) -
                                (re[:, :, 1] * re[:, :, 2]).sum(dim=0) -
                                (re[:, :, 2] * re[:, :, 0]).sum(dim=0)).sum()

                if derivatives == 0:
                    return [loss]

                Ldre = torch.zeros([3, elements_now.shape[0], 3])
                Ldre[:, :,
                     0] = 2 / 3 * (2 * re[:, :, 0] - re[:, :, 1] - re[:, :, 2])
                Ldre[:, :,
                     1] = 2 / 3 * (2 * re[:, :, 1] - re[:, :, 2] - re[:, :, 0])
                Ldre[:, :,
                     2] = 2 / 3 * (2 * re[:, :, 2] - re[:, :, 0] - re[:, :, 1])

                Ldr = torch.zeros([3, r.shape[1]])
                Ldr.scatter_add_(
                    1,
                    elements_now.flatten().unsqueeze(0).repeat(3, 1),
                    Ldre.reshape([3, -1]))

                if derivatives == 1:
                    return loss, Ldr

                Ldre2 = torch.zeros([3, elements_now.shape[0], 3, 3])
                Ldre2[:, :, 0, 0] = 2 / 3 * 2
                Ldre2[:, :, 0, 1] = 2 / 3 * -1
                Ldre2[:, :, 0, 2] = 2 / 3 * -1
                Ldre2[:, :, 1, 0] = 2 / 3 * -1
                Ldre2[:, :, 1, 1] = 2 / 3 * 2
                Ldre2[:, :, 1, 2] = 2 / 3 * -1
                Ldre2[:, :, 2, 0] = 2 / 3 * -1
                Ldre2[:, :, 2, 1] = 2 / 3 * -1
                Ldre2[:, :, 2, 2] = 2 / 3 * 2

                Ldr2_indices = torch.stack([
                    torch.tensor([0, 1, 2]).reshape([3, 1, 1, 1]).repeat(
                        [1, elements_now.shape[0], 3, 3]),
                    elements_now.reshape([1, elements_now.shape[0], 3, 1
                                          ]).repeat([3, 1, 1, 3]),
                    torch.tensor([0, 1, 2]).reshape([3, 1, 1, 1]).repeat(
                        [1, elements_now.shape[0], 3, 3]),
                    elements_now.reshape([1, elements_now.shape[0], 1, 3
                                          ]).repeat([3, 1, 3, 1])
                ],
                                           dim=0).reshape([4, -1])

                Ldr2 = torch.sparse_coo_tensor(
                    Ldr2_indices,
                    Ldre2.flatten(),
                    size=[3, r.shape[1], 3, r.shape[1]]).coalesce()

                return loss, Ldr, Ldr2

            def closure(desgin_variables, derivatives=0):
                # desgin_variables = desgin_variables.requires_grad_(True)

                point_sphere = desgin_variables.clone()
                # point_sphere = desgin_variables.unsqueeze(1).repeat(1, self._symmetric_PdP0.shape[1], 1) * PdP0.unsqueeze(-1)
                # point_sphere = point_sphere.reshape([2, -1])
                num_points = point_sphere.shape[1]
                t = 1 / (4 + point_sphere[0]**2 + point_sphere[1]**2)

                point_now = torch.zeros([3, point_sphere.shape[1]])
                point_now[0] = point_sphere[0] * 4 * t
                point_now[1] = point_sphere[1] * 4 * t
                point_now[2] = (1 - 8 * t) * step

                point_now = point_now.unsqueeze(1).repeat(
                    1, self._symmetric_PdP0.shape[1], 1) * PdP0.unsqueeze(-1)
                point_now = point_now.reshape([3, -1])

                r, rdx, rdx2 = self._partial_derivative_refSphere(
                    ref_points=point_now, derivative=2)[0]
                r0dx = rdx.reshape([3, 3, PdP0.shape[1], -1])[:, :, 0]
                r0dx2 = rdx2.reshape([3, 3, 3, PdP0.shape[1], -1])[:, :, :, 0]

                result1 = closure_edge_length(r, derivatives)
                result2 = closure_points_mid(r, derivatives)

                result = []
                for i in range(len(result1)):
                    result.append(result1[i] + result2[i])

                loss = result[0]
                if derivatives == 0:
                    return loss

                Ldr = result[1]
                Ldr0 = (Ldr.reshape([3, PdP0.shape[1], -1]) *
                        PdP0.unsqueeze(-1)).sum(dim=1)

                tdp = torch.zeros([2, num_points])
                tdp[0] = -2 * point_sphere[0] * t**2
                tdp[1] = -2 * point_sphere[1] * t**2
                xdp = torch.zeros([3, 2, num_points])
                xdp[0, 0] = 4 * t + 4 * point_sphere[0] * tdp[0]
                xdp[0, 1] = 4 * point_sphere[0] * tdp[1]
                xdp[1, 0] = 4 * point_sphere[1] * tdp[0]
                xdp[1, 1] = 4 * t + 4 * point_sphere[1] * tdp[1]
                xdp[2, 0] = -8 * tdp[0] * step
                xdp[2, 1] = -8 * tdp[1] * step
                r0dp = torch.einsum('ijp, jkp->ikp', r0dx, xdp)
                Ldp = torch.einsum('ijp, ip->jp', r0dp, Ldr0)

                if derivatives == 1:
                    return loss, Ldp

                Ldr2 = result[2]

                Ldr2 = self._sparse_reshape(
                    Ldr2, 2 * ([3, PdP0.shape[-1], desgin_variables.shape[1]]))

                Ldr02 = (Ldr2 * (PdP0.reshape([3, PdP0.shape[1], 1, 1, 1, 1]) *
                                 PdP0.reshape([3, PdP0.shape[1], 1]))).sum(
                                     dim=1).sum(dim=-2)

                tdp2 = torch.zeros([2, 2, num_points])
                tdp2[0, 0] = -2 * t**2 - 4 * point_sphere[0] * t * tdp[0]
                tdp2[1, 1] = -2 * t**2 - 4 * point_sphere[1] * t * tdp[1]
                tdp2[0, 1] = -4 * point_sphere[0] * t * tdp[1]
                tdp2[1, 0] = tdp2[0, 1]

                xdp2 = torch.zeros([3, 2, 2, num_points])
                xdp2[0, 0, 0] = 4 * tdp[0] + 4 * point_sphere[0] * tdp2[
                    0, 0] + 4 * tdp[0]
                xdp2[0, 0, 1] = 4 * tdp[1] + 4 * point_sphere[0] * tdp2[0, 1]
                xdp2[0, 1, 0] = xdp2[0, 0, 1]
                xdp2[0, 1, 1] = 4 * point_sphere[0] * tdp2[1, 1]
                xdp2[1, 0, 0] = 4 * point_sphere[1] * tdp2[0, 0]
                xdp2[1, 0, 1] = 4 * tdp[0] + 4 * point_sphere[1] * tdp2[0, 1]
                xdp2[1, 1, 0] = xdp2[1, 0, 1]
                xdp2[1, 1, 1] = 4 * tdp[1] + 4 * point_sphere[1] * tdp2[
                    1, 1] + 4 * tdp[1]
                xdp2[2] = -8 * tdp2 * step

                r0dp2 = torch.einsum('irsp, rmp, snp->imnp', r0dx2, xdp,
                                     xdp) + torch.einsum(
                                         'irp, rmnp->imnp', r0dx, xdp2)

                Ldp2_values2 = torch.einsum('ip, imnp->mnp', Ldr0, r0dp2)
                Ldp2_indices2 = torch.stack([
                    torch.tensor([0, 1]).reshape([2, 1, 1]).repeat(
                        [1, 2, num_points]),
                    torch.arange(0, num_points).reshape([1, 1, num_points
                                                         ]).repeat([2, 2, 1]),
                    torch.tensor([0, 1]).reshape([1, 2, 1]).repeat(
                        [2, 1, num_points]),
                    torch.arange(0, num_points).reshape([1, 1, num_points
                                                         ]).repeat([2, 2, 1])
                ],
                                            dim=0).reshape([4, -1])

                Ldp2_2 = torch.sparse_coo_tensor(
                    Ldp2_indices2, Ldp2_values2.flatten(),
                    [2, num_points, 2, num_points])
                Ldp2_1 = self._sparse_unsqueeze_repeat(Ldr02,
                                                       dim_insert=1,
                                                       num_repeat=2)
                Ldp2_1 = (Ldp2_1 * r0dp.reshape([3, 2, -1, 1, 1])).sum(dim=0)
                Ldp2_1 = self._sparse_unsqueeze_repeat(Ldp2_1,
                                                       dim_insert=3,
                                                       num_repeat=2)
                Ldp2_1 = (Ldp2_1 * r0dp).sum(dim=-3)
                Ldp2 = Ldp2_1 + Ldp2_2

                return loss, Ldp, Ldp2

            def torch_opt(design_variables, loss_init):
                design_variables_now = design_variables.detach().clone(
                ).requires_grad_(True)
                optimizer = torch.optim.Adam([design_variables_now])

                def closure_torch():
                    with torch.no_grad():
                        loss, ldp = closure(design_variables_now,
                                            derivatives=1)
                    ldp.data[:, index_boundary] = 0
                    ldp[ldp.isnan()] = 0
                    fake_loss = ldp * design_variables_now
                    fake_loss.sum().backward()
                    return loss

                loss = loss_init
                for i in range(100):
                    optimizer.zero_grad()
                    loss0 = loss
                    loss = closure_torch()
                    optimizer.step()
                    print('\rrefine mesh: loss = %e' % (loss), end='')
                    if (abs(loss - loss0) / abs(loss0) < 1e-4
                            or loss > loss0) and i > 5:
                        break
                optimizer.zero_grad()

                if loss < loss_init:
                    return design_variables_now.data, loss
                else:
                    return design_variables, loss_init

            loss = closure(design_variables, derivatives=0)
            # design_variables_new, loss_new = torch_opt(design_variables, loss)
            # design_variables.data = design_variables_new

            dP = torch.zeros([2, num_points - len(index_boundary)])

            while True:
                loss0 = loss
                loss, Ldp, Ldp2 = closure(design_variables, derivatives=2)

                # region: solve the linear system

                Ldp = Ldp[:, index_remain]
                Ldp2 = Ldp2.index_select(1, index_remain).index_select(
                    3, index_remain).coalesce()
                Ldp2 = self._sparse_reshape(Ldp2, [
                    2 * (num_points - len(index_boundary)), 2 *
                    (num_points - len(index_boundary))
                ]).coalesce()
                if Ldp.numel() < 10000:
                    try:
                        dP = torch.linalg.solve(Ldp2.to_dense(),
                                                -Ldp.flatten())
                    except:
                        dP = self._conjugate_gradient(Ldp2.indices(),
                                                      Ldp2.values(),
                                                      -Ldp.flatten(),
                                                      tol=1e-10,
                                                      max_iter=500)
                elif low_count == 0 and alpha > 1e-2:
                    dP = self._conjugate_gradient(Ldp2.indices(),
                                                  Ldp2.values(),
                                                  -Ldp.flatten(),
                                                  dP.flatten(),
                                                  tol=1e-4,
                                                  max_iter=500)
                else:
                    dP = self._conjugate_gradient(Ldp2.indices(),
                                                  Ldp2.values(),
                                                  -Ldp.flatten(),
                                                  tol=1e-10,
                                                  max_iter=500)
                dP = dP.reshape([2, -1])
                dP.view(-1)[dP.view(-1).isnan()] = 0
                # endregion

                # region: line search
                alpha = 1
                if (dP * Ldp).sum() > 0:
                    dP = -dP
                while True:
                    point_plane_new = design_variables.clone()
                    point_plane_new[:,
                                    index_remain] = design_variables[:,
                                                                     index_remain] + dP * alpha
                    loss_new = closure(point_plane_new, derivatives=0)

                    t = 1 / (4 + point_plane_new[0]**2 + point_plane_new[1]**2)
                    point_sphere_now = torch.zeros(
                        [3, point_plane_new.shape[1]])
                    point_sphere_now[0] = point_plane_new[0] * 4 * t
                    point_sphere_now[1] = point_plane_new[1] * 4 * t
                    point_sphere_now[2] = (1 - 8 * t) * step

                    point_sphere_now = point_sphere_now.unsqueeze(1).repeat(
                        1, self._symmetric_PdP0.shape[1],
                        1) * PdP0.unsqueeze(-1)
                    point_sphere_now = point_sphere_now.reshape([3, -1])
                    r = self._partial_derivative_refSphere(point_sphere_now)
                    re0 = r[:, elements[:, 0]]
                    re1 = r[:, elements[:, 1]]
                    re2 = r[:, elements[:, 2]]
                    V_now = (torch.cross(re0, re1, dim=0) * re2).sum().abs()

                    if not loss_new.isnan() and loss_new < loss and (abs(V_now - V) / V) < 0.01:
                        break
                    alpha *= 0.5
                    if alpha < 1e-10:
                        alpha = 0
                        break

                # endregion

                design_variables.data[:,
                                      index_remain] = design_variables.data[:,
                                                                            index_remain] + dP * alpha
                loss = loss_new
                # criterion to stop the iteration
                if abs(loss - loss0) / abs(loss0) < 1e-6:
                    low_count += 1
                    dP = torch.zeros([2, num_points - len(index_boundary)])
                elif abs(loss - loss0) / abs(loss0) < 1e-4:
                    low_count += 0.5
                else:
                    low_count = 0

                if low_count > 3:
                    break

                print('\rrefine mesh: loss = %e, alpha = %e' % (loss, alpha),
                      end='')

            t = 1 / (4 + design_variables[0]**2 + design_variables[1]**2)
            point_now = torch.zeros([3, design_variables.shape[1]])
            point_now[0] = design_variables[0] * 4 * t
            point_now[1] = design_variables[1] * 4 * t
            point_now[2] = (1 - 8 * t) * step

        t = 1 / (4 + design_variables[0]**2 + design_variables[1]**2)
        point_now = torch.zeros([3, design_variables.shape[1]])
        point_now[0] = design_variables[0] * 4 * t
        point_now[1] = design_variables[1] * 4 * t
        point_now[2] = (1 - 8 * t) * step

        point_now = point_now.unsqueeze(1).repeat(
            1, self._symmetric_PdP0.shape[1], 1) * PdP0.unsqueeze(-1)
        point_now = point_now.reshape([3, -1])

        return point_now

    def _refine_mesh_post_process(self, point_now: torch.Tensor):

        def __area_insert(point_now, r, elements):
            amin = self.seed_size**2 * 0.4 * 0.5
            amax = self.seed_size**2 * 0.4 * 3.0

            re0 = r[:, elements[:, 0]]
            re1 = r[:, elements[:, 1]]
            re2 = r[:, elements[:, 2]]

            normal = (re1 - re0).cross(re2 - re0, dim=0)

            area = normal.norm(dim=0) / 2

            ind1 = torch.where((area > amax))[0]
            if len(ind1) > 0:

                point_mid = (point_now[:, elements[ind1, 0]] +
                             point_now[:, elements[ind1, 1]] +
                             point_now[:, elements[ind1, 2]]) / 3
                point_mid = point_mid / point_mid.norm(dim=0)

                point_now = torch.cat([point_now, point_mid], dim=1)

                return point_now, True
            return point_now, False

        def __area_delete(point_now, r, elements):

            amin = self.seed_size**2 * 0.4 * 0.5
            amax = self.seed_size**2 * 0.4 * 3.0

            re0 = r[:, elements[:, 0]]
            re1 = r[:, elements[:, 1]]
            re2 = r[:, elements[:, 2]]

            normal = (re1 - re0).cross(re2 - re0, dim=0)

            area = normal.norm(dim=0) / 2

            ind2 = torch.where((area < amin))[0]
            if len(ind2) > 0:
                ind2 = ind2[area[ind2].argsort()]
                elems = elements[ind2]
                index = 0
                while True:
                    if index == elems.shape[0]:
                        break

                    index_remain = ((elems == elems[index, 0]) |
                                    (elems == elems[index, 1]) |
                                    (elems == elems[index, 2])).sum(dim=1) == 0
                    index_remain[:index + 1] = True
                    elems = elems[index_remain]

                    index += 1

                point_mid = (point_now[:, elems[:, 0]] +
                             point_now[:, elems[:, 1]] +
                             point_now[:, elems[:, 2]]) / 3
                point_mid = point_mid / point_mid.norm(dim=0)

                index_remain = torch.ones([point_now.shape[1]],
                                          dtype=torch.bool)
                index_remain[elems.flatten()] = False

                point_now = torch.cat([point_now[:, index_remain], point_mid],
                                      dim=1)

                return point_now, True
            return point_now, False

        def __angle_insert(point_now, r, elements):

            re0 = r[:, elements[:, 0]]
            re1 = r[:, elements[:, 1]]
            re2 = r[:, elements[:, 2]]

            normal = (re1 - re0).cross(re2 - re0, dim=0)

            edges, adjacent, another = self._get_adjacent_faces(elements)
            adjacent = adjacent[(adjacent[:, 0] >= 0) & (adjacent[:, 1] >= 0)]
            normal0 = normal / normal.norm(dim=0)

            discrete_curvature = (normal0[:, adjacent[:, 0]] *
                                  normal0[:, adjacent[:, 1]]).sum(dim=0)
            ind2 = torch.where((discrete_curvature < 0.7))[0]
            if len(ind2) > 0:
                adj_now = adjacent[ind2].flatten().unique()
                elements_new = elements[adj_now]

                point_mid = (point_now[:, elements_new[:, 0]] +
                             point_now[:, elements_new[:, 1]] +
                             point_now[:, elements_new[:, 2]]) / 3
                point_mid = point_mid / point_mid.norm(dim=0)
                point_now = torch.cat([point_now, point_mid], dim=1)
                return point_now, True
            return point_now, False

        def __broken_triangle(point_now, r, elements):

            re0 = r[:, elements[:, 0]]
            re1 = r[:, elements[:, 1]]
            re2 = r[:, elements[:, 2]]

            theta0 = ((re1 - re0) * (re2 - re0)).sum(dim=0) / (re1 - re0).norm(
                dim=0) / (re2 - re0).norm(dim=0)
            theta1 = ((re0 - re1) * (re2 - re1)).sum(dim=0) / (re0 - re1).norm(
                dim=0) / (re2 - re1).norm(dim=0)
            theta2 = ((re0 - re2) * (re1 - re2)).sum(dim=0) / (re0 - re2).norm(
                dim=0) / (re1 - re2).norm(dim=0)

            ind0 = torch.where((theta0 < math.cos(5 * math.pi / 6)))[0]
            ind1 = torch.where((theta1 < math.cos(5 * math.pi / 6)))[0]
            ind2 = torch.where((theta2 < math.cos(5 * math.pi / 6)))[0]
            if len(ind0) + len(ind1) + len(ind2) > 0:
                r_delete = torch.cat(
                    [elements[ind0, 0], elements[ind1, 1], elements[ind2, 2]],
                    dim=0).sort().values
                index_remain = torch.ones([point_now.shape[1]],
                                          dtype=torch.bool)
                index_remain[r_delete] = False
                point_now = point_now[:, index_remain]

                return point_now, True
            return point_now, False

        def __length_insert(point_now, r, elements):
            edges = self._get_edges(elements)
            l0 = (r[:, elements[:, 1]] - r[:, elements[:, 2]]).norm(dim=0)
            l1 = (r[:, elements[:, 0]] - r[:, elements[:, 2]]).norm(dim=0)
            l2 = (r[:, elements[:, 0]] - r[:, elements[:, 1]]).norm(dim=0)

        point_now = point_now.reshape([3, self._symmetric_PdP0.shape[1],
                                       -1])[:, 0]

        while True:

            point_now2 = point_now.unsqueeze(1).repeat(
                1, self._symmetric_PdP0.shape[1],
                1) * self._symmetric_PdP0.unsqueeze(-1)
            point_now2 = point_now2.reshape([3, -1])

            elements = self._sphere_mesh(point_now2.T)

            r = self._partial_derivative_refSphere(point_now2, derivative=0)

            elements = self._refine_triangular_mesh(nodes=r.T, elems=elements)
            index_remain = (elements < point_now.shape[1]).sum(dim=1) == 3
            elements_now = elements[index_remain]

            # point_now, cond = __broken_triangle(point_now, r, elements_now)
            # if cond:
            #     continue

            point_now, cond = __area_insert(point_now, r, elements_now)
            if cond:
                continue
            # point_now, cond = __area_delete(point_now, r, elements_now)
            # if cond:
            #     continue
            # point_now, cond = __angle_insert(point_now, r, elements_now)
            # if cond:
            #     continue

            break

        point_now = point_now.unsqueeze(1).repeat(
            1, self._symmetric_PdP0.shape[1],
            1) * self._symmetric_PdP0.unsqueeze(-1)
        point_now = point_now.reshape([3, -1])
        return point_now, elements

    def _map_closedsurface2sphere(self, r: torch.Tensor, knots: torch.Tensor,
                                  elements: torch.Tensor):

        def closure_edge_length(desgin_variables, edges, derivatives=0):

            order = 2

            r = desgin_variables.clone()

            edge_length2 = torch.sum(
                (r[:, edges[:, 0]] - r[:, edges[:, 1]])**2, dim=0).sqrt()

            loss = (edge_length2**order).sum()

            if derivatives == 0:
                return loss

            Ldl = order * edge_length2**(order - 1)

            ldre = (r[:, edges[:, 0]] - r[:, edges[:, 1]]) / edge_length2
            values_1 = Ldl * ldre

            Ldr = torch.zeros([2, r.shape[1]])
            Ldr.scatter_add_(1, edges[:, 0].unsqueeze(0).repeat(2, 1),
                             values_1)
            Ldr.scatter_add_(1, edges[:, 1].unsqueeze(0).repeat(2, 1),
                             -values_1)

            if derivatives == 1:
                return loss, Ldr

            Ldl_2 = order * (order - 1) * edge_length2**(order - 2)

            ldre_2 = torch.eye(2).reshape(2, 2, 1) / edge_length2 + \
                    -torch.einsum('ip, jp->ijp', ldre, ldre) / edge_length2

            values_2 = Ldl_2 * torch.einsum('ip,jp->ijp', ldre,
                                            ldre) + Ldl * ldre_2
            # diag
            Ldr2_values = [values_2.flatten(), values_2.flatten()]

            # cross item
            Ldr2_values += [-values_2.flatten(), -values_2.flatten()]

            Ldr2_values = torch.cat(Ldr2_values, dim=-1)
            # region : define the indices
            # diag
            Ldr2_indices0 = [
                torch.stack([
                    torch.tensor([0, 1]).reshape([2, 1, 1]).repeat([
                        1, 2, edges.shape[0]
                    ]), edges[:, 0].reshape([1, 1, -1]).repeat([2, 2, 1]),
                    torch.tensor([0, 1]).reshape([1, 2, 1]).repeat([
                        2, 1, edges.shape[0]
                    ]), edges[:, 0].reshape([1, 1, -1]).repeat([2, 2, 1])
                ],
                            dim=0).reshape([4, -1]),
                torch.stack([
                    torch.tensor([0, 1]).reshape([2, 1, 1]).repeat([
                        1, 2, edges.shape[0]
                    ]), edges[:, 1].reshape([1, 1, -1]).repeat([2, 2, 1]),
                    torch.tensor([0, 1]).reshape([1, 2, 1]).repeat([
                        2, 1, edges.shape[0]
                    ]), edges[:, 1].reshape([1, 1, -1]).repeat([2, 2, 1])
                ],
                            dim=0).reshape([4, -1]),
            ]

            # cross item
            Ldr2_indices0 += [
                torch.stack([
                    torch.tensor([0, 1]).reshape([2, 1, 1]).repeat(
                        [1, 2, edges.shape[0]]), edges[:, 0].reshape(
                            [1, 1, edges.shape[0]]).repeat([2, 2, 1]),
                    torch.tensor([0, 1]).reshape([1, 2, 1]).repeat(
                        [2, 1, edges.shape[0]]), edges[:, 1].reshape(
                            [1, 1, edges.shape[0]]).repeat([2, 2, 1])
                ],
                            dim=0).reshape([4, -1]),
                torch.stack([
                    torch.tensor([0, 1]).reshape([2, 1, 1]).repeat(
                        [1, 2, edges.shape[0]]), edges[:, 1].reshape(
                            [1, 1, edges.shape[0]]).repeat([2, 2, 1]),
                    torch.tensor([0, 1]).reshape([1, 2, 1]).repeat(
                        [2, 1, edges.shape[0]]), edges[:, 0].reshape(
                            [1, 1, edges.shape[0]]).repeat([2, 2, 1])
                ],
                            dim=0).reshape([4, -1]),
            ]
            Ldr2_indices = torch.cat(Ldr2_indices0, dim=-1)

            # endregion
            Ldr2 = torch.sparse_coo_tensor(Ldr2_indices, Ldr2_values,
                                           [2, r.shape[1], 2, r.shape[1]])

            return loss, Ldr, Ldr2

        def process(r: torch.Tensor, elements: torch.Tensor):
            boundary_points_circle = self._find_boundary_edges(elements)
            result = torch.rand([2, r.shape[1]]) * 0.01
            circle = torch.linspace(0, 2 * math.pi,
                                    boundary_points_circle.shape[0] +
                                    1)[:boundary_points_circle.shape[0]]
            result[0, boundary_points_circle] = torch.cos(circle) * 2
            result[1, boundary_points_circle] = torch.sin(circle) * 2

            index_remain = torch.ones([r.shape[1]], dtype=torch.bool)
            index_remain[boundary_points_circle] = False
            index_remain = torch.where(index_remain)[0]
            edges = self._get_edges(elements)

            for i in range(3):
                L, Ldp, Ldp2 = closure_edge_length(result,
                                                   edges,
                                                   derivatives=2)
                Ldp = Ldp[:, index_remain]
                Ldp2 = Ldp2.index_select(1, index_remain).index_select(
                    3, index_remain).coalesce()
                Ldp2 = self._sparse_reshape(Ldp2, [
                    2 * (r.shape[1] - len(boundary_points_circle)), 2 *
                    (r.shape[1] - len(boundary_points_circle))
                ]).coalesce()
                dP = torch.linalg.solve(Ldp2.to_dense(), -Ldp.flatten())
                result[:, index_remain] = result[:, index_remain] + dP.reshape(
                    [2, -1])

            return result

        # if self._symmetric[0] == 1:
        #     index_remain = torch.where(r[self._symmetric[1][0]] > 0)[0]
        # else:
        threshold = knots[:, 2].sort().values[int(knots.shape[0] * 0.5)]
        index_remain = torch.where(knots[:, 2] > threshold)[0]

        part1 = r[:, index_remain]
        index_remain_elements_part1 = torch.isin(
            elements.flatten() % r.shape[1],
            index_remain).reshape([-1, 3]).sum(dim=1) == 3
        elements_part1 = elements[index_remain_elements_part1].cpu().numpy()
        index_remain = index_remain.cpu().numpy()
        elements_part1 = np.vectorize(
            lambda x: np.where(index_remain == x)[0])(elements_part1)
        elements_part1 = torch.tensor(elements_part1.tolist())
        result1 = process(part1, elements_part1)

        # part2 = r[:, ~index_remain]
        # index_remain_elements_part2 = torch.isin(elements.flatten() % r.shape[1], ~index_remain).reshape([-1, 3]).sum(dim=1) == 3
        # elements_part2 = elements[index_remain_elements_part2]

    def _refine_knots(self):
        point_sphere = self.knots.T
        point_now = point_sphere.clone()
        elements = self.knots_element.clone()

        edges = self._get_edges(elements)
        edges = self.__symmetric_edges(edges, point_now.shape[1])

        epsilon = torch.zeros([3, 3, 3])
        epsilon[0, 1, 2] = epsilon[1, 2, 0] = epsilon[2, 0, 1] = 1
        epsilon[0, 2, 1] = epsilon[2, 1, 0] = epsilon[1, 0, 2] = -1

        step_iter = [1, -1, 1, -1]

        for iter_now in range(4):

            step = step_iter[iter_now]
            if self._symmetric[0] == 1:
                if 2 in self._symmetric[1]:
                    step = -1

            design_variables = torch.zeros([2, point_now.shape[1]])
            design_variables[0] = 2 * point_now[0] / (1 - step * point_now[2])
            design_variables[1] = 2 * point_now[1] / (1 - step * point_now[2])

            k12 = self._symmetric_PdP0[0:2].unsqueeze(-1)
            k3 = self._symmetric_PdP0[2].unsqueeze(-1)

            # design_variables = design_variables.requires_grad_(True)
            num_points = design_variables.shape[1]
            num_elems = elements.shape[0]

            de_norm = design_variables.norm(dim=0)
            sorted_de_norm, indices = de_norm.sort()
            # threshold = sorted_de_norm[int(num_points * 0.5)]

            # if self._symmetric[0] == 1 and 2 in self._symmetric[1]:
            threshold = 2

            index_boundary = torch.where(de_norm >= threshold)[0]

            index_remain = torch.tensor(
                list(
                    set(range(point_now.shape[1])) -
                    set(index_boundary.tolist())))

            index_remain_elements = torch.isin(
                elements.flatten() % design_variables.shape[1],
                index_remain).reshape([-1, 3]).sum(dim=1) == 3
            elements_now = elements[index_remain_elements]

            index_remain_edges = torch.isin(
                edges.flatten() % design_variables.shape[1],
                index_remain).reshape([-1, 2]).sum(dim=1) == 2
            edges_inside = edges[index_remain_edges]
            index_remain_edges = torch.isin(
                edges.flatten() % design_variables.shape[1],
                index_remain).reshape([-1, 2]).sum(dim=1) == 1
            edges_boundary = edges[index_remain_edges]

            index_another_elements = torch.isin(
                elements.flatten() % design_variables.shape[1],
                index_remain).reshape([-1, 3]).sum(dim=1) == 0
            elements_another = elements[index_another_elements]

            elements_connect = elements[(~index_remain_elements)
                                        & (~index_another_elements)]

            edges_now = torch.cat([
                edges_inside, edges_boundary, edges_boundary
            ],
                                  dim=0)

            low_count = 0
            alpha = 1

            def closure_edge_length(r, derivatives=0):

                order = 2

                edge_length2 = torch.sum(
                    (r[:, edges_now[:, 0]] - r[:, edges_now[:, 1]])**2,
                    dim=0).sqrt()

                loss = (edge_length2**order).sum()

                if derivatives == 0:
                    return [loss]

                Ldl = order * edge_length2**(order - 1)

                ldre = (r[:, edges_now[:, 0]] -
                        r[:, edges_now[:, 1]]) / edge_length2
                values_1 = Ldl * ldre

                Ldr = torch.zeros([2, r.shape[1]])
                Ldr.scatter_add_(1, edges_now[:, 0].unsqueeze(0).repeat(2, 1),
                                 values_1)
                Ldr.scatter_add_(1, edges_now[:, 1].unsqueeze(0).repeat(2, 1),
                                 -values_1)

                if derivatives == 1:
                    return loss, Ldr

                Ldl_2 = order * (order - 1) * edge_length2**(order - 2)

                ldre_2 = torch.eye(2).reshape(2, 2, 1) / edge_length2 + \
                        -torch.einsum('ip, jp->ijp', ldre, ldre) / edge_length2

                values_2 = Ldl_2 * torch.einsum('ip,jp->ijp', ldre,
                                                ldre) + Ldl * ldre_2
                # diag
                Ldr2_values = [values_2.flatten(), values_2.flatten()]

                # cross item
                Ldr2_values += [-values_2.flatten(), -values_2.flatten()]

                Ldr2_values = torch.cat(Ldr2_values, dim=-1)
                # region : define the indices
                # diag
                Ldr2_indices0 = [
                    torch.stack([
                        torch.tensor([0, 1]).reshape([2, 1, 1]).repeat(
                            [1, 2, edges_now.shape[0]]),
                        edges_now[:, 0].reshape([1, 1, -1]).repeat([2, 2, 1]),
                        torch.tensor([0, 1]).reshape([1, 2, 1]).repeat(
                            [2, 1, edges_now.shape[0]]),
                        edges_now[:, 0].reshape([1, 1, -1]).repeat([2, 2, 1])
                    ],
                                dim=0).reshape([4, -1]),
                    torch.stack([
                        torch.tensor([0, 1]).reshape([2, 1, 1]).repeat(
                            [1, 2, edges_now.shape[0]]),
                        edges_now[:, 1].reshape([1, 1, -1]).repeat([2, 2, 1]),
                        torch.tensor([0, 1]).reshape([1, 2, 1]).repeat(
                            [2, 1, edges_now.shape[0]]),
                        edges_now[:, 1].reshape([1, 1, -1]).repeat([2, 2, 1])
                    ],
                                dim=0).reshape([4, -1]),
                ]

                # cross item
                Ldr2_indices0 += [
                    torch.stack([
                        torch.tensor([0, 1]).reshape([2, 1, 1]).repeat([
                            1, 2, edges_now.shape[0]
                        ]), edges_now[:, 0].reshape([1, 1, edges_now.shape[0]
                                                     ]).repeat([2, 2, 1]),
                        torch.tensor([0, 1]).reshape([1, 2, 1]).repeat([
                            2, 1, edges_now.shape[0]
                        ]), edges_now[:, 1].reshape([1, 1, edges_now.shape[0]
                                                     ]).repeat([2, 2, 1])
                    ],
                                dim=0).reshape([4, -1]),
                    torch.stack([
                        torch.tensor([0, 1]).reshape([2, 1, 1]).repeat([
                            1, 2, edges_now.shape[0]
                        ]), edges_now[:, 1].reshape([1, 1, edges_now.shape[0]
                                                     ]).repeat([2, 2, 1]),
                        torch.tensor([0, 1]).reshape([1, 2, 1]).repeat([
                            2, 1, edges_now.shape[0]
                        ]), edges_now[:, 0].reshape([1, 1, edges_now.shape[0]
                                                     ]).repeat([2, 2, 1])
                    ],
                                dim=0).reshape([4, -1]),
                ]
                Ldr2_indices = torch.cat(Ldr2_indices0, dim=-1)

                # endregion
                Ldr2 = torch.sparse_coo_tensor(Ldr2_indices, Ldr2_values,
                                               [2, r.shape[1], 2, r.shape[1]])

                return loss, Ldr, Ldr2

            def closure_points_mid(r, derivatives=0):

                re = r[:, elements_now.flatten()].reshape([2, -1, 3])

                loss = 2 / 3 * ((re[:, :, 0]**2).sum(dim=0) +
                                (re[:, :, 1]**2).sum(dim=0) +
                                (re[:, :, 2]**2).sum(dim=0) -
                                (re[:, :, 0] * re[:, :, 1]).sum(dim=0) -
                                (re[:, :, 1] * re[:, :, 2]).sum(dim=0) -
                                (re[:, :, 2] * re[:, :, 0]).sum(dim=0)).sum()

                if derivatives == 0:
                    return [loss]

                Ldre = torch.zeros([2, elements_now.shape[0], 3])
                Ldre[:, :,
                     0] = 2 / 3 * (2 * re[:, :, 0] - re[:, :, 1] - re[:, :, 2])
                Ldre[:, :,
                     1] = 2 / 3 * (2 * re[:, :, 1] - re[:, :, 2] - re[:, :, 0])
                Ldre[:, :,
                     2] = 2 / 3 * (2 * re[:, :, 2] - re[:, :, 0] - re[:, :, 1])

                Ldr = torch.zeros([2, r.shape[1]])
                Ldr.scatter_add_(
                    1,
                    elements_now.flatten().unsqueeze(0).repeat(2, 1),
                    Ldre.reshape([2, -1]))

                if derivatives == 1:
                    return loss, Ldr

                Ldre2 = torch.zeros([2, elements_now.shape[0], 3, 3])
                Ldre2[:, :, 0, 0] = 2 / 3 * 2
                Ldre2[:, :, 0, 1] = 2 / 3 * -1
                Ldre2[:, :, 0, 2] = 2 / 3 * -1
                Ldre2[:, :, 1, 0] = 2 / 3 * -1
                Ldre2[:, :, 1, 1] = 2 / 3 * 2
                Ldre2[:, :, 1, 2] = 2 / 3 * -1
                Ldre2[:, :, 2, 0] = 2 / 3 * -1
                Ldre2[:, :, 2, 1] = 2 / 3 * -1
                Ldre2[:, :, 2, 2] = 2 / 3 * 2

                Ldr2_indices = torch.stack([
                    torch.tensor([0, 1]).reshape([2, 1, 1, 1]).repeat(
                        [1, elements_now.shape[0], 3, 3]),
                    elements_now.reshape([1, elements_now.shape[0], 3, 1
                                          ]).repeat([2, 1, 1, 3]),
                    torch.tensor([0, 1]).reshape([2, 1, 1, 1]).repeat(
                        [1, elements_now.shape[0], 3, 3]),
                    elements_now.reshape([1, elements_now.shape[0], 1, 3
                                          ]).repeat([2, 1, 3, 1])
                ],
                                           dim=0).reshape([4, -1])

                Ldr2 = torch.sparse_coo_tensor(
                    Ldr2_indices,
                    Ldre2.flatten(),
                    size=[2, r.shape[1], 2, r.shape[1]]).coalesce()

                return loss, Ldr, Ldr2

            def closure(desgin_variables, derivatives=0):

                t = (8 * k3 +
                     (4 + desgin_variables[0]**2 + desgin_variables[1]**2) *
                     (1 - k3))

                r = 8 * torch.einsum('iqp, ip, qp->iqp', k12, desgin_variables,
                                     1 / t)
                r[:, :,
                  index_boundary] = r[:, :,
                                      index_boundary] / r[:, :,
                                                          index_boundary].norm(
                                                              dim=0) * threshold
                r = r.reshape([2, -1])

                if iter_now == 0:
                    boundary_points_circle = self._find_boundary_edges(
                        elements_another)
                    rb = r[:, boundary_points_circle]

                    area = rb[0] * torch.roll(rb[1], -1) - rb[1] * torch.roll(
                        rb[0], -1)
                    if area.sum() < 0:
                        boundary_points_circle = torch.flip(boundary_points_circle,
                                                            [0])
                    
                    
                    start_angle = 0
                    if self._symmetric[0] == 1:
                        while boundary_points_circle[-1] < desgin_variables.shape[1]:
                            boundary_points_circle = torch.roll(boundary_points_circle, 1)
                        if 0 in self._symmetric[1]:
                            start_angle = -math.pi/2
                    
                    angle = torch.linspace(start_angle, start_angle + 2 * math.pi,
                                        boundary_points_circle.shape[0] + 1)[:boundary_points_circle.shape[0]] + 2 * math.pi / boundary_points_circle.shape[0]
                    r[:, boundary_points_circle] = torch.stack([torch.cos(angle), torch.sin(angle)], dim=0) * threshold

                result1 = closure_edge_length(r, derivatives)
                # result2 = closure_points_mid(r, derivatives)

                result = []
                for i in range(len(result1)):
                    result.append(result1[i])

                loss = result[0]

                if derivatives == 0:
                    return loss

                Ldr = result[1]

                tdr0 = 2 * torch.einsum('qp, mp->mqp',
                                        (1 - k3), desgin_variables)
                rdr0 = \
                    8*torch.einsum('iqp, im, qp->imqp', k12, torch.eye(2), 1/t) + \
                    8*torch.einsum('iqp, ip, qp, mqp->imqp', k12, desgin_variables, -1/t**2, tdr0)

                Ldr0 = torch.einsum('iqp, imqp->mp',
                                    Ldr.reshape([2, rdr0.shape[2], -1]),
                                    rdr0).reshape([2, -1])

                if derivatives == 1:
                    return loss, Ldr0

                Ldr2 = result[2]
                tdr0_2 = 2 * torch.einsum('qp, mn->mnqp',
                                          (1 - k3), torch.eye(2))
                rdr0_2 = \
                    8*torch.einsum('iqp, im, qp, nqp->imnqp', k12, torch.eye(2), -1/t**2, tdr0) + \
                    8*torch.einsum('iqp, in, qp, mqp->imnqp', k12, torch.eye(2), -1/t**2, tdr0) + \
                    8*torch.einsum('iqp, ip, qp, mqp, nqp->imnqp', k12, desgin_variables, 2/t**3, tdr0, tdr0) + \
                    8*torch.einsum('iqp, ip, qp, mnqp->imnqp', k12, desgin_variables, -1/t**2, tdr0_2)

                Ldr0_21 = self._sparse_reshape(
                    Ldr2, 2 * [2, rdr0.shape[2], desgin_variables.shape[1]])
                Ldr0_21 = (self._sparse_unsqueeze_repeat(Ldr0_21, 4, 2) *
                           rdr0).sum(dim=[3, 5])
                Ldr0_21 = (self._sparse_unsqueeze_repeat(Ldr0_21, 1, 2) *
                           rdr0.unsqueeze(-1).unsqueeze(-1)).sum(dim=[0, 2])

                Ldr0_22_values = torch.einsum(
                    'iqp, imnqp->mnp', Ldr.reshape([2, rdr0.shape[2], -1]),
                    rdr0_2)
                Ldr0_22_indices = torch.stack([
                    torch.tensor([0, 1]).reshape([2, 1, 1]).repeat(
                        [1, 2, desgin_variables.shape[1]]),
                    torch.arange(desgin_variables.shape[1]).reshape(
                        [1, 1, -1]).repeat([2, 2, 1]),
                    torch.tensor([0, 1]).reshape([1, 2, 1]).repeat(
                        [2, 1, desgin_variables.shape[1]]),
                    torch.arange(desgin_variables.shape[1]).reshape(
                        [1, 1, -1]).repeat([2, 2, 1])
                ],
                                              dim=0).reshape([4, -1])
                Ldr0_22 = torch.sparse_coo_tensor(
                    Ldr0_22_indices, Ldr0_22_values.flatten(), [
                        2, desgin_variables.shape[1], 2,
                        desgin_variables.shape[1]
                    ])

                Ldr02 = (Ldr0_21 + Ldr0_22).coalesce()

                return loss, Ldr0, Ldr02

            def newton_opt(design_variables, loss_init):
                design_variables = design_variables.detach().clone()
                dP = torch.zeros([2, num_points - len(index_boundary)])
                loss = loss_init
                low_count = 0
                alpha = 1.
                while True:
                    loss0 = loss
                    loss, Ldp, Ldp2 = closure(design_variables, derivatives=2)

                    # region: solve the linear system

                    Ldp = Ldp[:, index_remain]

                    Ldp2 = Ldp2.index_select(1, index_remain).index_select(
                        3, index_remain).coalesce()
                    Ldp2 = self._sparse_reshape(Ldp2, [
                        2 * (num_points - len(index_boundary)), 2 *
                        (num_points - len(index_boundary))
                    ]).coalesce()

                    dP = torch.linalg.solve(Ldp2.to_dense(), -Ldp.flatten())
                    dP = dP.reshape([2, -1])
                    dP.view(-1)[dP.view(-1).isnan()] = 0
                    # endregion

                    elements_now
                    elements_another
                    elements_connect
                    t = (
                        8 * k3 +
                        (4 + design_variables[0]**2 + design_variables[1]**2) *
                        (1 - k3))

                    r = 8 * torch.einsum('iqp, ip, qp->iqp', k12,
                                         design_variables, 1 / t)

                    r = r.reshape([2, -1])

                    # criterion to stop the iteration
                    if dP.norm() < 1e-14:

                        break

                    # region: line search
                    alpha = 1
                    # if (dP * Ldp).sum() > 0:
                    #     dP = -dP
                    # while True:
                    #     design_variables_new = design_variables.clone()
                    #     design_variables_new[:, index_remain] = design_variables_new[:,
                    #                                                               index_remain] + dP * alpha
                    #     loss_new = closure(design_variables_new, derivatives=0)
                    #     if not loss_new.isnan() and loss_new < loss:
                    #         break
                    #     alpha *= 0.5
                    #     if alpha < 1e-4:
                    #         alpha = 0
                    #         break

                    # if alpha == 0:
                    #     break

                    # endregion

                    design_variables.data[:,
                                          index_remain] = design_variables.data[:,
                                                                                index_remain] + dP * alpha

                    print('\rrefine knots: loss = %e, alpha = %e' %
                          (loss, alpha),
                          end='')
                return design_variables, loss

            loss = closure(design_variables, derivatives=0)

            for i in range(1):
                design_variables_new, loss_new = newton_opt(
                    design_variables, loss)
                design_variables.data = design_variables_new
            # design_variables_new, loss_new = newton_opt(design_variables, loss)
            # design_variables.data = design_variables_new

            t = 1 / (4 + design_variables[0]**2 + design_variables[1]**2)
            point_now = torch.zeros([3, design_variables.shape[1]])
            point_now[0] = design_variables[0] * 4 * t
            point_now[1] = design_variables[1] * 4 * t
            point_now[2] = (1 - 8 * t) * step

        point_now = point_now.unsqueeze(1).repeat(
            1, self._symmetric_PdP0.shape[1],
            1) * self._symmetric_PdP0.unsqueeze(-1)
        point_now = point_now.reshape([3, -1])

        self.knots = point_now.T

        self.knots = self.knots.reshape([self._symmetric_PdP0.shape[1], -1, 3])[0]
        return point_now


    def _refine_P0_newton(self, alpha = 0.1):
        # self.control_points.requires_grad_(True)
        r_ref = self.control_points.clone()
        r_ref = r_ref.unsqueeze(1) * self._symmetric_PdP0.unsqueeze(-1)
        r_ref = r_ref.reshape([3, -1])

        [control_points, knots,
         thresholds] = self.symmetrize_knots_CPs(derivative=1)

        num_points = knots.shape[0]

        result_now = self.get_surface_value(ref_points=knots.T, derivatives=1)

        [r, rdu, rdu2, Normal0, C] = result_now[0]
        [rdot_now, rdudot_now, rdu2dot_now, indices, _, _] = result_now[1]

        epsilon = torch.zeros([3, 3, 3])
        epsilon[0, 1, 2] = epsilon[1, 2, 0] = epsilon[2, 0, 1] = 1
        epsilon[0, 2, 1] = epsilon[2, 1, 0] = epsilon[1, 0, 2] = -1

        loss0 = ((r - r_ref)**2).sum()
        loss1 = ((control_points - r_ref)**2).sum() * alpha

        # [1, 1, 1, 1, 1, 1, num_points]
        print()
        print('before refine P0: loss = %e' % (loss0 + loss1 * alpha))

        ldr = 2 * (r - r_ref)
        ldr_2_values = 2 * torch.ones([3, num_points]).flatten()
        ldr_2_indices = torch.stack([
            torch.arange(0, 3).reshape([3, 1]).repeat(1, num_points),
            torch.arange(0, num_points).reshape([1, num_points]).repeat(3, 1),
            torch.arange(0, 3).reshape([3, 1]).repeat(1, num_points),
            torch.arange(0, num_points).reshape([1, num_points]).repeat(3, 1),
        ],
                                    dim=0).reshape([4, -1])
        ldr_2 = torch.sparse_coo_tensor(ldr_2_indices,
                                        ldr_2_values,
                                        size=[3, num_points, 3, num_points])

        l0dot = self._from_Adr_to_Adot(indices=indices,
                                       Adr=ldr,
                                       rdot=rdot_now,
                                       numel_output=knots.shape[0])

        l1dot = 2 * (control_points - r_ref)

        ldot = l0dot + l1dot * alpha

        ldot = ldot.reshape([3, self._symmetric_PdP0.shape[1], -1])

        ldot = (ldot * self._symmetric_PdP0.unsqueeze(-1)).sum(1)

        l0dot_2 = self._from_Sdr_to_Sdot_2(indices=indices,
                                           Sdr_2=ldr_2,
                                           rdot=rdot_now)

        l1dot_2 = ldr_2

        ldot_2 = l0dot_2 + l1dot_2 * alpha

        ldot_2 = self._sparse_reshape(
            ldot_2, 2 *
            ([3, self._symmetric_PdP0.shape[1], self.control_points.shape[1]
              ])).coalesce()
        ldot_2 = (ldot_2 * (self._symmetric_PdP0.reshape([3, -1, 1, 1, 1, 1]) *
                            self._symmetric_PdP0.reshape([3, -1, 1]))).sum(
                                dim=1).sum(dim=-2)

        ldot_2 = self._sparse_reshape(
            ldot_2, 2 * [3 * self.control_points.shape[1]]).coalesce()

        dP = self._conjugate_gradient(ldot_2.indices(),
                                      ldot_2.values(),
                                      -ldot.flatten(),
                                      tol=1e-7,
                                      max_iter=30000)
        dP.view(-1)[dP.view(-1).isnan()] = 0
        dP = dP.reshape([3, -1])
        # dP_norm = dP.norm(dim=0)
        # index = torch.where(dP_norm > 10 * dP_norm.mean())[0]
        # dP[:, index] *= 10 * dP_norm.mean() / dP_norm[index]
        self.control_points = self.control_points + dP.reshape([3, -1])

        [control_points, knots,
         thresholds] = self.symmetrize_knots_CPs(derivative=1)

        result_now = self.get_surface_value(ref_points=knots.T, derivatives=1)
        [r, rdu, rdu2, Normal0, C] = result_now[0]

        epsilon = torch.zeros([3, 3, 3])
        epsilon[0, 1, 2] = epsilon[1, 2, 0] = epsilon[2, 0, 1] = 1
        epsilon[0, 2, 1] = epsilon[2, 1, 0] = epsilon[1, 0, 2] = -1

        loss0 = ((r - r_ref)**2).sum()
        loss1 = ((control_points - r_ref)**2).sum() * alpha

        print('after refine P0: loss = %e' % (loss0 + loss1 * alpha))

    def _refine_P0_CG(self, r_ref):
        # self.control_points.requires_grad_(True)
        num_points = self.knots.shape[0]

        result_now = self.get_surface_value(ref_points=self.knots.T,
                                            derivatives=1)
        [r, rdu, rdu2, Normal0, C] = result_now[0]
        [rdot_now, rdudot_now, rdu2dot_now, indices, _, _] = result_now[1]

        # normal_element = torch.cross(
        #     r[:, self.knots_element[:, 1]] - r[:, self.knots_element[:, 0]],
        #     r[:, self.knots_element[:, 2]] - r[:, self.knots_element[:, 0]],
        #     dim=0)
        # normal_node = torch.zeros([3, num_points]).scatter_add(
        #     1,
        #     self.knots_element.unsqueeze(0).repeat([3, 1, 1]).reshape([3, -1]),
        #     normal_element.unsqueeze(-1).repeat(1, 1, 3).reshape([3, -1]))
        # normal_node = normal_node / normal_node.norm(dim=0)

        alpha = 1e6
        # beta = 1

        [control_points, knots,
         thresholds] = self.symmetrize_knots_CPs(derivative=1)

        epsilon = torch.zeros([3, 3, 3])
        epsilon[0, 1, 2] = epsilon[1, 2, 0] = epsilon[2, 0, 1] = 1
        epsilon[0, 2, 1] = epsilon[2, 1, 0] = epsilon[1, 0, 2] = -1

        loss0 = ((r - r_ref)**2).sum()
        loss1 = ((self.control_points - r_ref)**2).sum() * alpha
        # loss2 = (((self.control_points - r_ref).cross(normal_node,
        #                                               dim=0))**2).sum()

        # [1, 1, 1, 1, 1, 1, num_points]
        print()
        print('before refine P0: loss = %e' % (loss0 + loss1 * alpha))

        indices, weights_values = self._get_weights(knots, thresholds,
                                                    self.knots.T)
        weights_values = (weights_values)**self.degree

        Wsum = torch.zeros(self.knots.shape[0]).scatter_add_(
            dim=0, index=indices[1], src=weights_values)

        def closure(x):

            control_points = x + self.control_points - self._init_location.unsqueeze(
                1)

            if self._symmetric[0] == 1:
                control_points = control_points.unsqueeze(1).repeat(
                    1, self._symmetric_PdP0.shape[1],
                    1) * self._symmetric_PdP0.unsqueeze(-1)

            control_points = control_points.reshape(
                3, -1) + self._init_location.unsqueeze(1)

            Rweight0 = control_points[:, indices[0]] * weights_values
            RW = self._sparse_sum(indices,
                                  Rweight0,
                                  numel_output=self.knots.shape[0])
            r = RW / Wsum

            ldr = 2 * (r - r_ref)

            l0dot = self._from_Adr_to_Adot(indices=indices,
                                           Adr=ldr,
                                           rdot=rdot_now,
                                           numel_output=knots.shape[0])
            l0dot = l0dot.reshape([3, self._symmetric_PdP0.shape[1], -1])
            l1dot = 2 * (x + self.control_points - r_ref)
            # l2dot = 2 * (
            #     ((x + self.control_points - r_ref).cross(normal_node, dim=0)).T
            #     * torch.einsum('ajk,jp->apk', epsilon, normal_node)).sum(-1)

            l0dot = (l0dot * self._symmetric_PdP0.unsqueeze(-1)).sum(1)

            ldot = l0dot + l1dot * alpha  # + l2dot * beta
            return ldot

        x = torch.zeros_like(self.control_points)
        r = -closure(x)
        p = r
        rsold = (r**2).sum()

        for i in range(100000):
            Ap = torch.autograd.functional.jvp(closure, (x, ), (p, ))[1]
            alpha = rsold / (p * Ap).sum()
            x = x + alpha * p
            r = r - alpha * Ap
            rsnew = (r**2).sum()
            if rsnew < 1e-12:
                break
            p = r + rsnew / rsold * p
            rsold = rsnew
            if i % 100 == 0:
                print('\riter: %d, residual: %e' % (i, rsnew), end='')

        self.control_points = x + self.control_points
        result_now = self.get_surface_value(ref_points=self.knots.T,
                                            derivatives=1)
        [r, rdu, rdu2, Normal0, C] = result_now[0]
        [rdot_now, rdudot_now, rdu2dot_now, indices, _, _] = result_now[1]

        [control_points, knots,
         thresholds] = self.symmetrize_knots_CPs(derivative=1)

        epsilon = torch.zeros([3, 3, 3])
        epsilon[0, 1, 2] = epsilon[1, 2, 0] = epsilon[2, 0, 1] = 1
        epsilon[0, 2, 1] = epsilon[2, 1, 0] = epsilon[1, 0, 2] = -1

        loss0 = ((r - r_ref)**2).sum()
        loss1 = ((self.control_points - r_ref)**2).sum() * alpha
        # loss2 = (((self.control_points - r_ref).cross(normal_node,
        #                                               dim=0))**2).sum()

        print('after refine P0: loss = %e' % (loss0 + loss1 * alpha))

    def __symmetric_edges(self, edges: torch.Tensor, P_size: int):

        if self._symmetric[0] != 0:
            # clear the symmetric points
            edges_part = edges // P_size

            ## self connection
            ind1 = (edges_part == 0).sum(dim=1)
            part1 = edges[ind1 == 2]

            ## cross connection
            ind2 = (edges_part[:, 0] == 0) & (edges_part[:, 1] > 0)
            part2 = edges[ind2]

            edges = torch.cat([part1, part1, part2], dim=0)

        return edges

    # endregion

    # region file operation
    

    def save_to_file(self, filename):
        """
        Save the surface to the given file
        param filename:
        num_init_points: number of points
        symmetry: Symmetry of the surface
        """
        data = ''
        data += '*seed_size:%e\n' % self.seed_size
        data += '*symmetry:%s\n' % str(self._symmetric)
        data += '*init_location:%s\n' % str(self._init_location.tolist())
        data += '*flip:%d\n' % self.flip

        data += '*Knots:%s\n' % str(self.knots.tolist())
        data += '*P0:%s\n' % str(self.control_points.tolist())
        data += '*elements:%s\n' % str(self.knots_element.tolist())

        with open(filename, 'w') as f:
            f.write(data)
            f.close()
            return True
        return False

    @staticmethod
    def load_from_file(filename):
        """
        Load the surface from the given file
        """
        with open(filename, 'r') as f:
            data = f.read()
            f.close()

        data = data.replace('\n', '')
        data = data.split('*')
        for i in range(len(data)):
            data_now = data[i].split(':')
            if data_now[0] == 'seed_size':
                seed_size = eval(data_now[1])
                continue
            if data_now[0] == 'symmetry':
                symmetry = eval(data_now[1])
                continue
            if data_now[0] == 'init_location':
                init_location = torch.tensor(torch.tensor(eval(data_now[1])))
                continue
            if data_now[0] == 'flip':
                flip = bool(eval(data_now[1]))
                continue

            if data_now[0] == 'Knots':
                Knots = torch.tensor(torch.tensor(eval(data_now[1])))
                continue
            if data_now[0] == 'P0':
                P0 = torch.tensor(torch.tensor(eval(data_now[1])))
                continue
            if data_now[0] == 'elements':
                Knots_element = torch.tensor(torch.tensor(eval(data_now[1])))
                continue

        srbf = ClosedSurface(1)
        srbf.knots = Knots
        srbf.control_points = P0

        try:
            srbf.seed_size = seed_size
        except:
            srbf.seed_size = 2.0

        try:
            srbf._symmetric = symmetry
        except:
            srbf._symmetric = [0, []]
        try:
            srbf._init_location = init_location
        except:
            srbf._init_location = torch.zeros([3])
        try:
            srbf.knots_element = Knots_element
        except:
            srbf.knots_element = srbf._sphere_mesh(srbf.knots)
        try:
            srbf.flip = flip
        except:
            srbf.flip = False

        srbf._symmetric_PdP0 = torch.ones([3, 1])
        if srbf._symmetric[0] == 1:
            ratio = torch.ones([3])
            for sym in srbf._symmetric[1]:
                ratio = ratio.reshape([3, -1]).unsqueeze(1).repeat(1, 2, 1)
                ratio[sym, 1, :] *= -1
            ratio = ratio.reshape([3, -1])
            srbf._symmetric_PdP0 = ratio
        srbf._reinitialize()

        return srbf

    # endregion

    # region show
    def show(self,
             points3d: list[list[float]] = None,
             coo: list[list[int]] = None,
             color=(40.0 / 255, 120.0 / 255, 181.0 / 255),
             alpha=1):
        """
        show the surface.
        :param color: color of the surface
        :param alpha: transparency of the surface
        :return:
        """
        self._show(points3d, coo, color, alpha)
        mlab.show()

    def show_P0(self):
        control_points = self.symmetrize_knots_CPs()[0]
        mlab.triangular_mesh(control_points[0].tolist(),
                             control_points[1].tolist(),
                             control_points[2].tolist(),
                             self.knots_element.tolist(),
                             opacity=1)
        surface = mlab.pipeline.surface(
            mlab.pipeline.triangular_mesh_source(control_points[0].tolist(),
                                                 control_points[1].tolist(),
                                                 control_points[2].tolist(),
                                                 self.knots_element.tolist()),
            color=(1.0 / 255, 1.0 / 255, 1.0 / 255),
            opacity=1)
        surface.actor.property.representation = 'wireframe'
        mlab.show()

    def show_knots(self,
                   xlimit: list[float] = [-1.0, 1.0],
                   ylimit: list[float] = [-1.0, 1.0],
                   zlimit: list[float] = [-1.0, 1.0],
                   hold=False):
        knots = self.symmetrize_knots_CPs()[1]

        elements = self.knots_element
        elements_center = (knots[self.knots_element[:, 0]] +
                           knots[self.knots_element[:, 1]] +
                           knots[self.knots_element[:, 2]]) / 3

        remain = torch.ones([elements_center.shape[0]], dtype=torch.bool)

        remain[elements_center[:, 0] < xlimit[0]] = False
        remain[elements_center[:, 0] > xlimit[1]] = False
        remain[elements_center[:, 1] < ylimit[0]] = False
        remain[elements_center[:, 1] > ylimit[1]] = False
        remain[elements_center[:, 2] < zlimit[0]] = False
        remain[elements_center[:, 2] > zlimit[1]] = False

        elements = elements[remain]

        mlab.triangular_mesh(knots[:, 0].tolist(),
                             knots[:, 1].tolist(),
                             knots[:, 2].tolist(),
                             elements.tolist(),
                             opacity=1)
        surface = mlab.pipeline.surface(mlab.pipeline.triangular_mesh_source(
            knots[:, 0].tolist(), knots[:, 1].tolist(), knots[:, 2].tolist(),
            elements.tolist()),
                                        color=(1.0 / 255, 1.0 / 255,
                                               1.0 / 255),
                                        opacity=1)
        surface.actor.property.representation = 'wireframe'
        if not hold:
            mlab.show()

    def _show(self,
              points3d: list[list[float]] = None,
              coo: list[list[int]] = None,
              color=(40.0 / 255, 120.0 / 255, 181.0 / 255),
              alpha=1):
        """
        show the surface.
        :param color: color of the surface
        :param alpha: transparency of the surface
        :return:
        """
        if points3d is None or coo is None:
            points3d = self.pre_nodes
            coo = self.pre_elements
        r = self.map(points3d).tolist()

        coo = coo.tolist()

        mlab.triangular_mesh(r[0], r[1], r[2], coo, color=color, opacity=alpha)
        # surface = mlab.pipeline.surface(
        #     mlab.pipeline.triangular_mesh_source(r[0], r[1], r[2], coo),
        #     color=(1.0 / 255, 1.0 / 255, 1.0 / 255),
        #     opacity=alpha)
        # surface.actor.property.representation = 'wireframe'

        # mlab.points3d(self.control_points[0].tolist(),
        #               self.control_points[1].tolist(),
        #               self.control_points[2].tolist(),
        #               scale_factor=0.05,
        #               color=(1, 0, 0))

    # endregion


def show_quiver3d(R, N):
    from mayavi import mlab
    r = R.detach().cpu().numpy()
    n = N.detach().cpu().numpy()
    mlab.quiver3d(r[0], r[1], r[2], n[0], n[1], n[2])
    mlab.show()


def show_surf(r, coo, hold=False):
    r = r.tolist()
    coo = coo.tolist()
    from mayavi import mlab
    mlab.triangular_mesh(r[0], r[1], r[2], coo, opacity=1)
    surface = mlab.pipeline.surface(mlab.pipeline.triangular_mesh_source(
        r[0], r[1], r[2], coo),
                                    color=(1.0 / 255, 1.0 / 255, 1.0 / 255),
                                    opacity=1)
    surface.actor.property.representation = 'wireframe'

    if not hold:
        mlab.show()


def show_surf2(r,
               coo,
               hold=False,
               color=(232.0 / 255, 232.0 / 255, 232.0 / 255),
               if_points=False):

    r0 = r.clone()[:, coo.unique()]

    r2 = torch.zeros_like(r[0]).tolist()
    r = r.tolist()
    coo = coo.tolist()
    from mayavi import mlab
    mlab.triangular_mesh(r[0], r[1], r2, coo, opacity=1, color=color)
    surface = mlab.pipeline.surface(mlab.pipeline.triangular_mesh_source(
        r[0], r[1], r2, coo),
                                    color=(1.0 / 255, 1.0 / 255, 1.0 / 255),
                                    opacity=1)
    surface.actor.property.representation = 'wireframe'

    if if_points:

        mlab.points3d(r0[0],
                      r0[1],
                      torch.zeros_like(r0[0]).tolist(),
                      scale_factor=0.04,
                      color=(40.0 / 255, 120.0 / 255, 181.0 / 255))

    if not hold:
        mlab.show()


def show_plot(data):
    from matplotlib import pyplot as plt
    d = data.detach().cpu().numpy()
    plt.plot(d)


def show_points(r, scale_factor=0.1):
    from mayavi import mlab
    r = r.tolist()
    mlab.points3d(r[0], r[1], r[2], scale_factor=scale_factor, color=(1, 0, 0))
    mlab.show()


def show_points2(r, scale_factor=0.1):
    from mayavi import mlab
    r2 = torch.zeros_like(r[0]).tolist()
    r = r.tolist()
    mlab.points3d(r[0], r[1], r2, scale_factor=scale_factor, color=(1, 0, 0))
    mlab.show()


def __remesh_test(srbf: ClosedSurface):

    # srbf.control_points.requires_grad_()
    # srbf.pre_load()

    # srbf.refine_knots(point_sphere=srbf.knots.T, elements=srbf.knots_element, PdP0=srbf._symmetric_PdP0)
    # a = srbf.get_surface_value(derivatives=2)

    # srbf._show(color=(160 / 255, 255 / 255, 248 / 255), alpha=0.5)

    # srbf.refine_surface_reseed()
    # srbf.refine_knots_max()
    srbf._refine_surface_reseed()
    srbf._reinitialize()
    srbf.pre_load()

    # srbf.control_points.requires_grad_()
    a = srbf.get_surface_value(derivatives=2)

    [r, rdu, rdu2, normal, C0] = a[0]
    print(C0.max())

    srbf.pre_load()

    # srbf._show(color=(248 / 255, 160 / 255, 248 / 255), alpha=0.5)

    # mlab.show(stop=False)
    bsp = srbf.to_bspline()
    assert False


def __test(srbf: ClosedSurface):

    t1 = time.time()
    srbf._get_weights_c_build_trees(srbf.knots, srbf.threshold)
    t11 = time.time()
    print('c++1 time:', (t11 - t1))
    for i in range(100):
        indices = srbf._get_weights_c(srbf.knots,
                                      srbf.threshold,
                                      srbf.knots.T,
                                      build_trees=False)
    t2 = time.time()
    print('c++ time:', (t2 - t1))

    t1 = time.time()
    for i in range(100):
        indices1, weight1 = srbf._get_weights_torch(srbf.knots, srbf.threshold,
                                                    srbf.knots.T)
        torch.cuda.synchronize()
    t2 = time.time()
    print('torch time:', (t2 - t1))

    srbf2 = ClosedSurface(2.0,
                          torch.tensor([0, 0, 0]),
                          flip=True,
                          symmetric=[1, [1]])
    srbf2.initialize(lambda: srbf._initial_surface.cylinder(
        radius=7, height=50, seed_size=2.0, flip=True))

    indices = srbf2._get_weights_c(srbf2.knots, srbf2.threshold, srbf2.knots.T)
    indices1 = srbf2._get_weights_torch(srbf2.knots, srbf2.threshold,
                                        srbf2.knots.T)[0]

    srbf.pre_load()
    srbf._reinitialize()
    a = srbf.get_surface_value(ref_points=srbf.pre_nodes.requires_grad_(),
                               derivatives=2)

    [r, rdu, rdu2, normal, C0] = a[0]

    assert False


if __name__ == '__main__':

    torch.set_default_device(torch.device('cuda'))
    torch.set_default_tensor_type(torch.DoubleTensor)

    # srbf = ClosedSurface.load_from_file('test5.txt')
    # srbf.flip = True
    srbf = ClosedSurface(1.2,
                         torch.tensor([0, 0, 0]),
                         flip=True,
                         symmetric=[1, [1]])
    srbf.initialize(lambda: srbf._initial_surface.cylinder(
        radius=5, height=50, seed_size=1.2, flip=True))

    # srbf2 = ClosedSurface(1.2,
    #                      torch.tensor([0, 0, 0]),
    #                      flip=True,
    #                      symmetric=[1, [1]])
    # srbf2.initialize(lambda: srbf._initial_surface.cylinder(
    #     radius=5, height=20, seed_size=1.2, flip=True))
    # srbf.show_knots()
    # srbf.initialize(lambda: srbf._initial_surface.sphere(
    #     radius=3, seed_size=1.2, flip=True))
    # srbf._refine_knots2(srbf.knots.T, srbf._symmetric_PdP0, srbf.knots_element)
    __remesh_test(srbf)

    assert False
