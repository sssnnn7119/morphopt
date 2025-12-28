from calendar import c
import sys
import os

sys.path.append(os.getcwd())
_current_path = os.path.dirname(os.path.abspath(__file__))
import copy
import ctypes

import numpy as np
import time
import torch
from ..basesurfacemodel import Surface_Base


class BSP():
    faceApi = ctypes.WinDLL(_current_path + '/Bspline.dll')

    def __init__(self,
                 P0: torch.Tensor,
                 degree: int,
                 dimension_input: int,
                 dimension_output: int,
                 vector_type: list[list[int]],
                 symmetric: list[int] = None,
                 domain_zoom: list[list[int]] = None) -> None:
        """
        :param P0: the control points
        :param degree: the degree of the surface
        :param dimension_input: the dimension of the input
        :param dimension_output: the dimension of the output
        :param vector_type: the type of the vector, 
            vector_type 0:clamed, 1:opened, 2:circular
        :param symmetric: the symmetric of the surface
        :param domain_zoom: the zoom of the domain
        """

        # initialize
        self._symmetric = symmetric
        self.dimension_IO = [dimension_input, dimension_output]
        self.vector_type = np.array(vector_type)
        self.num_points = np.array(
            P0.shape[1:]) + (self.vector_type[:, 0] == 2) * (degree - 1)
        self.degree = degree
        self.control_points = P0
        self.interval_size = 1 / (self.num_points - self.degree + 1)
        if domain_zoom is None:
            self.domain_zoom = [[0, 1] for i in range(dimension_input)]
        else:
            self.domain_zoom = domain_zoom

        # build basis functions
        self.knot_vector = []
        self.basis_function = []
        for i in range(dimension_input):

            # determine the knot_vector
            self.knot_vector.append(
                np.linspace(0, 1, (self.num_points[i] - self.degree + 2)))
            if self.vector_type[i][0] == 0:
                head = np.zeros(self.degree - 1)
            else:
                head = -np.flip(self.knot_vector[i][1:self.degree])
            if self.vector_type[i][1] == 0:
                rear = np.ones(self.degree - 1)
            else:
                rear = 1 + self.knot_vector[i][1:self.degree]
            self.knot_vector[i] = np.append(head, self.knot_vector[i])
            self.knot_vector[i] = np.append(self.knot_vector[i], rear)

            self.basis_function.append(
                torch.zeros([
                    self.num_points[i] - self.degree + 1, self.degree,
                    self.num_points[i]
                ]))

            if self.vector_type[i][0] == 2:
                self.basis_function[i] = self.basis_function[
                    i][:, :, 0:self.num_points[i] - self.degree + 1]

            for interval_now in range(self.num_points[i] + 1 - self.degree):
                kv = (self.knot_vector[i] - interval_now *
                      self.interval_size[i])[interval_now:interval_now +
                                             self.degree]
                basis = self._DeBoor_Cox(kv, self.degree, self.degree)
                basis_now = torch.zeros([
                    self.num_points[i] - self.degree + 1, self.degree,
                    self.num_points[i]
                ])
                basis_now[interval_now, :,
                          interval_now:interval_now + self.degree] = basis
                # make circle
                if self.vector_type[i][1] == 2:
                    for j in range(self.degree - 1):
                        basis_now[:, :,
                                  j] = basis_now[:, :,
                                                 j] + basis_now[:, :, self.
                                                                num_points[i] -
                                                                self.degree +
                                                                1 + j]
                    basis_now = basis_now[:, :, 0:self.num_points[i] -
                                          self.degree + 1]

                self.basis_function[i][interval_now] = basis_now[interval_now]
            if self.vector_type[i][0] == 2:
                self.num_points[i] -= self.degree - 1

        # for preload
        self.core = {}
        self.basis = []
        self.coordinates: torch.Tensor
        for i in range(self.dimension_IO[0]):
            self.basis.append({})

    def _DeBoor_Cox(self, U, N, D):
        # [区间，次数-1, d, k+1]

        B_arr = np.zeros((N + D - 1) * D * D * (N + D - 1))
        B_arr_ptr = B_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

        U_ptr = U.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

        BSP.faceApi.DeBoor_Cox(U_ptr, B_arr_ptr, int(N), int(D))

        B = torch.tensor(B_arr.tolist())

        B = B.reshape([N + D - 1, D, D, N + D - 1])
        return B[D - 1:N, :, D - 1, 0:N]

    def __Derive_Basis_Function(self, B):
        D = B.shape[1]
        dB = B.clone()
        for i in range(D - 1):
            dB[:, i, :] = B[:, i + 1, :] * (i + 1)
        dB[:, D - 1, :] = 0
        return dB

    def Find_Basis_Index(self, Coordinate, dimension):

        outputSize = Coordinate.shape
        Coo = Coordinate.flatten()

        # find the interval assoiated with the inputs
        index_Input = torch.ceil(Coo / self.interval_size[dimension]) - 1
        index_Input[index_Input == -1] = 0
        index_Input[Coo == 1] = self.num_points[dimension] - self.degree
        index_Input = index_Input.type(torch.int64)

        # find the control points associated with the interval
        [a, b] = torch.meshgrid(torch.arange(self.degree),
                                index_Input,
                                indexing='ij')
        index_Points = a + b
        if self.vector_type[dimension, 0] == 2:
            index_Points = index_Points % self.num_points[dimension]

        return [index_Input, index_Points]

    def Get_ControlPoints_Weight(self, Coordinate, dimension, derivative=0):

        if type(Coordinate) != torch.Tensor:
            Coordinate = torch.tensor(copy.deepcopy(Coordinate))

        Coordinate = (Coordinate - self.domain_zoom[dimension][0]) / (
            self.domain_zoom[dimension][1] - self.domain_zoom[dimension][0])

        outputSize = Coordinate.shape
        numOfInput = np.prod(outputSize)
        basis_function = self.basis_function[dimension]

        Coo = Coordinate.flatten()

        # get derivative
        for d in range(derivative):
            basis_function = self.__Derive_Basis_Function(basis_function)

        # limit input
        if self.vector_type[dimension, 0] == 2:
            Coo = Coo - torch.floor(Coo)
        else:
            Coo[Coo > 1] = 1
            Coo[Coo < 0] = 0

        # find input interval
        [index_Input, index_Points] = self.Find_Basis_Index(Coo, dimension)

        # calculate the polynomial
        Coo = Coo - self.interval_size[dimension] * index_Input
        index = index_Points + (self.degree - 1) * basis_function.shape[
            2] + index_Input * basis_function.shape[2] * basis_function.shape[1]
        weight = basis_function.flatten()[index.flatten().type(
            torch.int64)].reshape([self.degree, numOfInput])
        for j in range(self.degree - 1):
            index = index_Points + (
                self.degree - 1 - (j + 1)
            ) * basis_function.shape[2] + index_Input * basis_function.shape[
                2] * basis_function.shape[1]
            weight = weight * Coo + basis_function.flatten()[index.flatten(
            ).type(torch.int64)].reshape([self.degree, numOfInput])

        weight = weight.reshape(list(np.append(self.degree, outputSize))) / (
            self.domain_zoom[dimension][1] -
            self.domain_zoom[dimension][0])**derivative
        index_Points = index_Points.reshape(
            list(np.append(self.degree, outputSize)))
        return weight, index_Points

    def Get_Map_Kernel(self, weight0, index_points):
        output_size = weight0[0].shape[1:]
        num_input = np.prod(output_size)

        # get the total weight of control index_point
        for i in range(self.dimension_IO[0]):
            ii = self.dimension_IO[0] - i - 1
            if i == 0:
                weight = weight0[ii].reshape(self.degree, num_input)
            else:
                b = weight0[ii].reshape([self.degree, 1, num_input])
                weight = weight.reshape(list(np.append(1, weight.shape)))

                weight = weight * b
                weight = weight.reshape(-1, num_input)

        for i in range(self.dimension_IO[0]):
            ii = self.dimension_IO[0] - i - 1
            if i == 0:
                pt_index = index_points[ii].reshape([self.degree, num_input])
            else:
                b = index_points[ii].reshape([self.degree, 1, num_input])
                pt_index = pt_index.reshape(list(np.append(1, pt_index.shape)))

                pt_index = pt_index + b * np.prod(self.num_points[ii + 1:])
                pt_index = pt_index.reshape(-1, num_input)
        pt_index = pt_index.type(torch.int64)

        return [weight, pt_index]

    def Map_Core(self, core, ControlPoint=0):
        if ControlPoint == 0:
            ControlPoint = self.control_points
        # ControlPoint = np.transpose(ControlPoint, np.append(0, np.flip(np.array(range(
        #     self.dimension_IO[0]))+1)))

        ControlPoint = ControlPoint.reshape(self.dimension_IO[1], -1)

        result = np.zeros([self.dimension_IO[1], core[0].shape[1]])
        result_ptr = result.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

        ControlPoint_ptr = ControlPoint.detach().cpu().numpy().astype(
            float).ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        weight_ptr = core[0].cpu().numpy().astype(float).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))
        pt_index_ptr = core[1].cpu().numpy().astype(int).ctypes.data_as(
            ctypes.POINTER(ctypes.c_int))

        BSP.faceApi.Map_core(int(np.prod(self.num_points)),
                             int(core[0].shape[1]), int(self.dimension_IO[1]),
                             int(core[0].shape[0]), ControlPoint_ptr,
                             weight_ptr, pt_index_ptr, result_ptr)
        result = torch.tensor(result)
        return result

    def Map_Core_Py(self, core, ControlPoint: torch.Tensor = None):
        if ControlPoint is None:
            ControlPoint = self.control_points
        ControlPoint = ControlPoint.reshape(self.dimension_IO[1], -1)

        result = torch.zeros(self.dimension_IO[1], core[0].shape[1])
        for i in range(core[0].shape[0]):
            cp = ControlPoint[:, core[1][i, :]]
            result = result + core[0][i, :] * cp
        return result

    def map(self,
            Coordinates: list[torch.Tensor] = None,
            derivative: list[int] = None):

        if derivative == None:
            derivative = np.zeros(self.dimension_IO[0], dtype=int)
        if Coordinates == None:
            Coordinates = self.coordinates
        # Coordinates = torch.tensor(Coordinates)
        weight0 = []
        index_points = []
        output_size = Coordinates[0].shape

        t1 = time.time()
        # get weight of control points
        for i in range(len(Coordinates)):
            weight_now, index_points_now = self.Get_ControlPoints_Weight(
                Coordinates[i], i, derivative[i])
            weight0.append(weight_now)
            index_points.append(index_points_now)
        t2 = time.time()
        core = self.Get_Map_Kernel(weight0, index_points)
        t3 = time.time()
        # mapping

        result = self.Map_Core_Py(core).reshape(
            list(np.append(self.dimension_IO[1], output_size)))

        # result = self.Map_Core(core).reshape(
        #     list(np.append(self.dimension_IO[1], output_size)))
        t4 = time.time()
        return result

    def pre_load(self, num_points: list[int], coordinates=0, order_derive=0):

        # determine the coordinates of pre load
        self.coordinates = []
        if type(coordinates) == int:
            coo = []
            str_now = ""
            for i in range(len(num_points)):
                if self.vector_type[i, 0] == 2:
                    coo.append(torch.linspace(0, 1, num_points[i] + 1)[1:])
                else:
                    coo.append(torch.linspace(0, 1, num_points[i]))
                str_now += "coo[" + str(i) + "],"
            Coordinates = list(
                eval("torch.meshgrid(" + str_now + " indexing='ij')"))

            for i in range(len(Coordinates)):
                self.coordinates.append(
                    torch.clone(
                        (Coordinates[i]) *
                        (self.domain_zoom[i][1] - self.domain_zoom[i][0]) +
                        self.domain_zoom[i][0]))
            self.coordinates = torch.stack(self.coordinates, dim=0)
        else:
            self.coordinates = torch.tensor(coordinates)

        # get the weight of each control points for each grid
        for dev in range((order_derive + 1)**self.dimension_IO[0]):
            num_derive = np.zeros(self.dimension_IO[0], dtype=int)
            ind = dev
            for j in range(self.dimension_IO[0]):
                num_derive[j] = ind % (order_derive + 1)
                ind = ind / (order_derive + 1)
            num_derive = tuple(num_derive)
            weight0 = []
            index_points = []
            for i in range(len(self.coordinates)):
                weight_now, index_points_now = self.Get_ControlPoints_Weight(
                    self.coordinates[i], i, num_derive[i])
                weight0.append(weight_now)
                if num_derive[i] not in self.basis[i].keys():
                    self.basis[i][num_derive[i]] = weight_now
                index_points.append(index_points_now)

            self.core[num_derive] = self.Get_Map_Kernel(weight0, index_points)

    def Group_Sum(self, data, index):
        result = np.zeros(self.control_points.shape)
        result_ptr = result.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

        num_points = np.prod(data.shape[1:])
        num_degrees = data.shape[0]
        num_controlpoints = np.prod(result.shape[1:])
        dimension = data.shape[0]

        data_ptr = np.array(data.cpu(), dtype=float).copy().ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))
        index_ptr = np.array(index.cpu(), dtype=int).copy().ctypes.data_as(
            ctypes.POINTER(ctypes.c_int))
        BSP.faceApi.Group_Sum(result_ptr, data_ptr, index_ptr, int(num_points),
                              int(num_controlpoints), int(dimension))

        return torch.tensor(result)

    def save_to_file(self, filename):
        """
        degree: int,
        dimension_input: int,
        dimension_output: int,
        vector_type: list[list[int]],
        symmetric: list[int]=None,
        domain_zoom=1
        P0: torch.Tensor,
        """
        data = ''
        data += '*degree:%d\n' % self.degree
        data += '*dimensionIO:%d,%d\n' % (self.dimension_IO[0],
                                          self.dimension_IO[1])
        data += '*vector_type:%s\n' % str(self.vector_type.tolist())
        data += '*symmetric:%s\n' % str(self._symmetric)
        data += '*domain_zoom:%s\n' % str(self.domain_zoom)
        data += '*P0:%s\n' % str(self.control_points.tolist())

        with open(filename, 'w') as f:
            f.write(data)
            f.close()
            return True
        return False

    @staticmethod
    def load_from_file(file_name):
        """
        load surface from file
        """
        f = open(file_name, 'r')
        data = f.read()
        f.close()
        data = data.replace('\n', '')
        data = data.split('*')
        for i in range(len(data)):
            data_now = data[i].split(':')
            if data_now[0] == 'degree':
                degree = int(data_now[1])
            if data_now[0] == 'dimensionIO':
                dimension_input = int(data_now[1].split(',')[0])
                dimension_output = int(data_now[1].split(',')[1])
            if data_now[0] == 'vector_type':
                vector_type = eval(data_now[1])
            if data_now[0] == 'symmetric':
                symmetric = eval(data_now[1])
            if data_now[0] == 'domain_zoom':
                domain_zoom = eval(data_now[1])
            if data_now[0] == 'Pshape':
                Pshape = eval(data_now[1])
            if data_now[0] == 'P0':
                P0 = torch.tensor(eval(data_now[1]))
        return BSP(P0=P0,
                   degree=degree,
                   dimension_input=dimension_input,
                   dimension_output=dimension_output,
                   vector_type=vector_type,
                   symmetric=symmetric,
                   domain_zoom=domain_zoom)


class BSP_Surf(BSP, Surface_Base):

    def __init__(self, P0, degree, vector_type, symmetric: list[int] = None):
        super().__init__(P0=P0,
                         degree=degree,
                         dimension_input=2,
                         dimension_output=3,
                         vector_type=vector_type,
                         symmetric=symmetric)

    def pre_load(self, num_points: int = None, num_derive=2, coordinates=0,):
        
        if num_points is None:
            num_points = (np.array(list(self.control_points.shape[1:])) * 2).tolist()
            
        super().pre_load(num_points=num_points, order_derive=num_derive, coordinates=coordinates)

        # initial position
        self.R0 = self.get_surface_value(derivatives=0)[0][0]

        # find the connection of the surface
        index = torch.arange(0, np.prod(num_points)).reshape(num_points)
        index_up = torch.roll(index, 1, 0)
        index_left = torch.roll(index, 1, 1)
        self.pre_edges = torch.cat([
            torch.stack([index.flatten(), index_up.flatten()], dim=1),
            torch.stack(
                [index.flatten(), index_left.flatten()], dim=1)
        ],
                                   dim=0)
        # sort the connection
        index = self.pre_edges[:, 0] * num_points[1] + self.pre_edges[:, 1]
        index, ind = torch.sort(index)
        self.pre_edges = self.pre_edges[ind]

    def Show_Surf_Matplotlib(self, fig=0):
        import matplotlib.pyplot as plt
        u = torch.linspace(0, 1, self.num_points[0] * 2)
        v = torch.linspace(0, 1, self.num_points[1] * 2)
        [U, V] = torch.meshgrid(u, v, indexing='ij')
        result = self.map([U, V]).cpu()

        plt.sca
        if fig == 0:
            fig = plt.figure()
        ax = plt.axes(projection='3d')
        ax.plot_surface(result[0], result[1], result[2], cmap=plt.cm.plasma)
        plt.axis('equal')
        plt.axis('off')

        fig.show()

        return fig

    def show(self, color=(40.0 / 255, 120.0 / 255, 181.0 / 255), alpha=1.):
        from mayavi import mlab
        self._show(color=color, alpha=alpha)
        mlab.show()

    def _show(self, color=(40.0 / 255, 120.0 / 255, 181.0 / 255), alpha=1.):
        from mayavi import mlab
        u = torch.linspace(0, 1, self.num_points[0] * 2)
        v = torch.linspace(0, 1, self.num_points[1] * 2)
        [U, V] = torch.meshgrid(u, v, indexing='ij')
        result = self.map([U, V]).cpu().detach().numpy()
        
        

        mlab.mesh(result[0], result[1], result[2], color=color, opacity=alpha)

        # mlab.points3d(self.control_points[0].flatten().tolist(),
        #               self.control_points[1].flatten().tolist(),
        #               self.control_points[2].flatten().tolist(),
        #               color=(0, 0, 0),
        #               scale_factor=0.1)

    def _partial_derivative(self,
                            ref_points: torch.Tensor = None,
                            controlpoints: bool = False,
                            derivative: int = 0):

        P0 = self.control_points
        if ref_points is not None:
            U = ref_points[0]
            V = ref_points[1]
            num_points = U.numel()
            U = U.flatten()
            V = V.flatten()
            Bu, index_points_u = self.Get_ControlPoints_Weight(U, 0, 0)
            dBu = self.Get_ControlPoints_Weight(U, 0, 1)[0]
            d2Bu = self.Get_ControlPoints_Weight(U, 0, 2)[0]
            Bv, index_points_v = self.Get_ControlPoints_Weight(V, 1, 0)
            dBv = self.Get_ControlPoints_Weight(V, 1, 1)[0]
            d2Bv = self.Get_ControlPoints_Weight(V, 1, 2)[0]
            weight0, pt_index = self.Get_Map_Kernel(
                [Bu, Bv], [index_points_u, index_points_v])
            if derivative >= 1:
                weightu, pt_index = self.Get_Map_Kernel(
                    [dBu, Bv], [index_points_u, index_points_v])
                weightv, pt_index = self.Get_Map_Kernel(
                    [Bu, dBv], [index_points_u, index_points_v])
            if derivative >= 2:
                weightuu, pt_index = self.Get_Map_Kernel(
                    [d2Bu, Bv], [index_points_u, index_points_v])
                weightuv, pt_index = self.Get_Map_Kernel(
                    [dBu, dBv], [index_points_u, index_points_v])
                weightvv, pt_index = self.Get_Map_Kernel(
                    [Bu, d2Bv], [index_points_u, index_points_v])
        else:
            num_points = self.coordinates[0].numel()
            pt_index = self.core[(0, 0)][1]
            weight0 = self.core[(0, 0)][0]
            weightu = self.core[(1, 0)][0]
            weightv = self.core[(0, 1)][0]
            weightuu = self.core[(2, 0)][0]
            weightuv = self.core[(1, 1)][0]
            weightvv = self.core[(0, 2)][0]

        r = self.Map_Core_Py((weight0, pt_index), ControlPoint=P0)
        output = [[r]]
        if derivative >= 1:
            ru = self.Map_Core_Py((weightu, pt_index), ControlPoint=P0)
            rv = self.Map_Core_Py((weightv, pt_index), ControlPoint=P0)
            rdu = torch.stack([ru, rv], dim=1)
            output[0].append(rdu)
        if derivative >= 2:
            rdu2 = torch.zeros([3, 2, 2, num_points])
            rdu2[:, 0, 0] = self.Map_Core_Py((weightuu, pt_index),
                                             ControlPoint=P0)
            rdu2[:, 0, 1] = self.Map_Core_Py((weightuv, pt_index),
                                             ControlPoint=P0)
            rdu2[:, 1, 0] = rdu2[:, 0, 1]
            rdu2[:, 1, 1] = self.Map_Core_Py((weightvv, pt_index),
                                             ControlPoint=P0)
            output[0].append(rdu2)

        if controlpoints:
            indices1 = torch.arange(0, num_points).unsqueeze(0).repeat(
                weight0.shape[0], 1)
            indices = torch.stack(
                [pt_index.flatten(), indices1.flatten()], dim=0)
            controlpoints_derivative = [indices, weight0.flatten()]
            if derivative >= 1:
                rdudot = torch.stack(
                    [weightu.flatten(), weightv.flatten()], dim=0)
                controlpoints_derivative.append(rdudot)
            if derivative >= 2:
                rdu2dot = torch.zeros([2, 2, weight0.numel()])
                rdu2dot[0, 0] = weightuu.flatten()
                rdu2dot[0, 1] = weightuv.flatten()
                rdu2dot[1, 0] = rdu2dot[0, 1]
                rdu2dot[1, 1] = weightvv.flatten()
                controlpoints_derivative.append(rdu2dot)
            output.append(controlpoints_derivative)
        return output

    def get_surface_value(self,
                          ref_points: torch.Tensor = None,
                          derivatives: int = 0):
        """
        ref_points: torch.Tensor, the reference points
            shape: [2, num_points]
        derivatives: int, the order of the derivatives
        
        return: 
            [0]: [r, rdu, rdu2, Normal0, C, FF, RR]
            [1]: [rdot, rdudot, rdu2dot, indices, Cdru, Cdru2, FFdru, RRdru, RRdru2]
            [2]: [Cdru_2, Cdrudru2, Cdru2_2, FFdru_2, RRdru_2, RRdrudru2, RRdru2_2]
        """

        if ref_points is None:
            ref_points = self.coordinates
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

        # basic properties

        geo_values = self._get_geometric_values(partial_derivative,
                                                derivatives=derivatives,
                                                save_derivatives=derivatives
                                                > 0)
        result = []
        if derivatives >= 0:
            Normal0, I, detI, invI, II, detII, H, K, C = geo_values[0]
            F = I[0, 1]
            E = I[0, 0]
            G = I[1, 1]
            FF = I[0, 1] * I[1, 0] / I[1, 1] / I[0, 0]

            Iu = torch.einsum('iuwp, ivp->uvwp', rdu2, rdu) + \
                    torch.einsum('iup, ivwp->uvwp', rdu, rdu2)

            RRuu = Iu[0, 0, 0]**2 / E**2
            RRuv = Iu[0, 0, 1]**2 / E**2
            RRvu = Iu[1, 1, 0]**2 / G**2
            RRvv = Iu[1, 1, 1]**2 / G**2

            result.append(
                [r, rdu, rdu2, Normal0, C, FF, RRuu, RRuv, RRvu, RRvv])

        return result

    def symmetric_reinitialize(self):
        Pout = self.control_points.clone()
        Zoffset = (Pout[2].max() + Pout[2].min()) / 2
        Pout[2] = Pout[2] - Zoffset
        if self._symmetric[0] == 1:
            for s in self._symmetric[1]:
                if s == 1:
                    flipdim = -1
                if s == 2:
                    flipdim = -2
                for i in range(3):
                    if i == s:
                        Pout[i] = (Pout[i] -
                                   torch.flip(Pout[i], dims=[flipdim])) / 2
                    else:
                        Pout[i] = (Pout[i] +
                                   torch.flip(Pout[i], dims=[flipdim])) / 2
        Pout[2] = Pout[2] + Zoffset
        self.control_points = Pout

    @ staticmethod
    def load_from_file(file_name):
        """
        load surface from file
        """
        f = open(file_name, 'r')
        data = f.read()
        f.close()
        data = data.replace('\n', '')
        data = data.split('*')
        for i in range(len(data)):
            data_now = data[i].split(':')
            if data_now[0] == 'degree':
                degree = int(data_now[1])
            if data_now[0] == 'dimensionIO':
                dimension_input = int(data_now[1].split(',')[0])
                dimension_output = int(data_now[1].split(',')[1])
            if data_now[0] == 'vector_type':
                vector_type = eval(data_now[1])
            if data_now[0] == 'symmetric':
                symmetric = eval(data_now[1])
            if data_now[0] == 'domain_zoom':
                domain_zoom = eval(data_now[1])
            if data_now[0] == 'Pshape':
                Pshape = eval(data_now[1])
            if data_now[0] == 'P0':
                P0 = torch.tensor(eval(data_now[1]))
        return BSP_Surf(P0=P0,
                        degree=degree,
                        vector_type=vector_type,
                        symmetric=symmetric)


class BSP_Curve(BSP):

    def __init__(self,
                 P0: torch.Tensor,
                 degree: int,
                 vector_type: list[list[int]] = [[0, 0]]) -> None:
        super().__init__(P0,
                         degree,
                         1,
                         P0.shape[0],
                         vector_type,
                         symmetric=None)

    def Get_tangent_vector(self, U: torch.Tensor):
        tanget = self.map(Coordinates=[U], derivative=[1])


if __name__ == '__main__':

    torch.set_default_tensor_type(torch.DoubleTensor)
    torch.set_default_device(torch.device('cuda'))

    u = torch.linspace(0, 1, 100)
    v = torch.linspace(0, 1, 77)[:-1]

    [U, V] = torch.meshgrid(u, v, indexing='ij')
    theta = 2 * torch.pi * V + 1 / 76 * torch.pi
    P0 = torch.empty([3, 100, 76])
    P0[0] = torch.cos(theta) * (12 + 1 * torch.rand_like(theta))
    P0[1] = torch.sin(theta) * (12 + 1 * torch.rand_like(theta))
    P0[2] = U * 100

    t1 = time.time()
    self = BSP_Surf(P0, 4, [[0, 0], [2, 2]], [1, [1, 2]])
    t2 = time.time()
    print('construct time comsumption:\t', t2 - t1)

    self.control_points.requires_grad_()

    self.save_to_file('P0.txt')

    A = BSP_Surf.load_from_file('P0.txt')

    initSize = [200, 152]
    self.pre_load(initSize, init_size=1)
    
    self._partial_derivative(controlpoints=True, derivative=2)

    self.symmetric_reinitialize()

    result = self.Map_Core(self.core[(0, 0)])

    u = torch.linspace(0, 1, 1000)
    v = torch.linspace(0, 1, 1000)
    [U, V] = torch.meshgrid(u, v, indexing='ij')
    t1 = time.time()
    result = self.map([U, V])
    torch.cuda.synchronize()
    t2 = time.time()
    print('map time comsumption:\t', t2 - t1)

    self.show()

    t1 = time.time()
    a = self.get_surface_value(derivatives=2)

    result = torch.zeros_like(a[1])
    for i in a[1:]:
        result += i
    result = result.sum()
    result.backward()
    gd = a[0].grad
    t2 = time.time()
    print('backword time comsumption:\t', t2 - t1)

    a = self.get_surface_value(order=1)

    result = torch.zeros_like(a[1])
    for i in a[1:]:
        result += i
    result = result.sum()
    result.backward()
    gd2 = a[0].grad

    bsp = copy.deepcopy(self)
    bsp.control_points[0][0][0] = 100

    print('ok')
