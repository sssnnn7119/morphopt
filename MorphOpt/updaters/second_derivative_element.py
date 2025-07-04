import torch
import FEA
import numpy as np


class SensitivityElement(FEA.elements.C3.Element_3D):

    def __init__(self, elems: np.ndarray, elems_index: np.ndarray) -> None:
        super().__init__(elems=elems, elems_index=elems_index)
        self.pp: torch.Tensor = None
        self.point_request_ref: torch.Tensor = None
        self.points_request: torch.Tensor = None
        self.shapeFun0: torch.Tensor = None
        self.shapeFun1: torch.Tensor = None
        self.shapeFun2: torch.Tensor = None
        self.Jacobian1: torch.Tensor = None
        self.Jacobian2: torch.Tensor = None
        self.inv_Jacobian1: torch.Tensor = None
        self.inv_Jacobian2: torch.Tensor = None

    def initialize_from_p0(self, fea: FEA.Main.FEA_Main):

        shape_i = torch.zeros(
            [3, self.shape_function[0].shape[0], self.shape_function[0].shape[1]])
        shape_i[0] = self._shape_function_derivative(self.shape_function[0], 0)
        shape_i[1] = self._shape_function_derivative(self.shape_function[0], 1)
        shape_i[2] = self._shape_function_derivative(self.shape_function[0], 2)
        self.shape_function.append(shape_i)

        shape_ii = torch.zeros(
            [3, 3, self.shape_function[0].shape[0], self.shape_function[0].shape[1]])
        for i in range(3):
            for j in range(3):
                shape_ii[i, j] = self._shape_function_derivative(shape_i[i], j)

        self.shape_function.append(shape_ii)

        self._pre_load_gaussian(self.point_request_ref, nodes=fea.nodes)

        p0 = self.point_request_ref
        pp = torch.zeros([self._num_gaussian, self.shape_function[0].shape[1]])
        pp[:, 0] = 1
        pp[:, 1] = p0[:, 0]
        pp[:, 2] = p0[:, 1]
        pp[:, 3] = p0[:, 2]
        if self.shape_function[0].shape[1] > 4:
            pp[:, 4] = p0[:, 0] * p0[:, 1]
            pp[:, 5] = p0[:, 1] * p0[:, 2]
            pp[:, 6] = p0[:, 2] * p0[:, 0]
        if self.shape_function[0].shape[1] > 7:
            pp[:, 7] = p0[:, 0]**2
            pp[:, 8] = p0[:, 1]**2
            pp[:, 9] = p0[:, 2]**2
        if self.shape_function[0].shape[1] > 10:
            pp[:, 10] = p0[:, 0]**2 * p0[:, 1]
            pp[:, 11] = p0[:, 1]**2 * p0[:, 0]
            pp[:, 12] = p0[:, 1]**2 * p0[:, 2]
            pp[:, 13] = p0[:, 2]**2 * p0[:, 1]
            pp[:, 14] = p0[:, 2]**2 * p0[:, 0]
            pp[:, 15] = p0[:, 0]**2 * p0[:, 2]
            pp[:, 16] = p0[:, 0] * p0[:, 1] * \
                        p0[:, 2]
        if self.shape_function[0].shape[1] > 17:
            pp[:, 17] = p0[:, 0]**3
            pp[:, 18] = p0[:, 1]**3
            pp[:, 19] = p0[:, 2]**3
        self.pp = pp

        self.Jacobian1 = torch.zeros([p0.shape[0], len(self._elems), 3, 3])
        self.Jacobian2 = torch.zeros([p0.shape[0], len(self._elems), 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            self.Jacobian1 += torch.einsum('gb,mb,ei->geim', self.pp,
                                           self.shape_function[1][:, i],
                                           fea.nodes[self._elems[:, i]])
            self.Jacobian2 += torch.einsum('gb,mnb,ei->geimn', self.pp,
                                           self.shape_function[2][:, :, i],
                                           fea.nodes[self._elems[:, i]])

        self.inv_Jacobian1 = self.Jacobian1.cpu().inverse().to(self.pp.device)
        self.inv_Jacobian2 = -torch.einsum(
            'gemj,gepk,genl,gejnp->gemlk', self.inv_Jacobian1,
            self.inv_Jacobian1, self.inv_Jacobian1, self.Jacobian2)

        Nksi1 = torch.einsum('gb,mab->gma', self.pp, self.shape_function[1])
        Nksi2 = torch.einsum('gb,mnab->gmna', self.pp, self.shape_function[2])

        self.shapeFun0 = torch.einsum('ab, gb->ga', self.shape_function[0],
                                      self.pp)
        self.shapeFun1 = torch.einsum('gemi,gma->geia', self.inv_Jacobian1,
                                      Nksi1)
        self.shapeFun2 = torch.einsum(
            'gemi, genj,gmna->geija',
            self.inv_Jacobian1, self.inv_Jacobian1, Nksi2) + torch.einsum(
                'gemij, gma->geija', self.inv_Jacobian2, Nksi1)

        points_request = torch.zeros(
            [self.pp.shape[0], self._elems.shape[0], 3])
        for i in range(self.num_nodes_per_elem):
            points_request = points_request + torch.einsum(
                'g,eI->geI', self.shapeFun0[:, i], fea.nodes[self._elems[:,
                                                                         i]])

        self.points_request = points_request

    def displacement(self, U: torch.Tensor):
        Ue = torch.zeros([self.pp.shape[0], self._elems.shape[0], 3])
        for i in range(self.num_nodes_per_elem):
            Ue = Ue + torch.einsum('g,eI->geI', self.shapeFun0[:, i],
                                   U[self._elems[:, i]])
        return Ue

    def gradient_displacement(self, U: torch.Tensor):
        Ugrad = torch.zeros([self.pp.shape[0], self._elems.shape[0], 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad = Ugrad + torch.einsum(
                'gei,eI->geIi', self.shapeFun1[:, :, :, i], U[self._elems[:,
                                                                          i]])
        return Ugrad

    def gradient_2nd_displacement(self, U: torch.Tensor):
        Ugrad2 = torch.zeros([self.pp.shape[0], self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 = Ugrad2 + torch.einsum(
                'geij,eI->geIij', self.shapeFun2[:, :, :, :,
                                                 i], U[self._elems[:, i]])
        return Ugrad2

    def sensitivity_conponent(self, U: torch.Tensor):
        Ugrad = self.gradient_displacement(U)
        Ugrad2 = self.gradient_2nd_displacement(U)

        F, I1, J, invF, s, C = self.components_Solid(U=U)

        return J, F, invF, Ugrad, Ugrad2, s, C

    @staticmethod
    def get_sensitivity_element(elems: FEA.elements.C3.Element_3D, fe: FEA.FEA_Main) -> 'SensitivityElement':
        """
        Get the sensitivity element based on the type of elements.
        Args:
            elems (FEA.elements.C3.Element_3D): The elements to get the sensitivity element for.
            fe (FEA.FEA_Main): The finite element analysis instance.
        Returns:
            SensitivityElement: An instance of the sensitivity element class.
        """
        if elems.__class__.__name__ == 'C3D10':
            element_sensitive = C3D10_Sensitivity(
                elems_index=elems._elems_index,
                elems=elems._elems,
                fea=fe)
        elif elems.__class__.__name__ == 'C3D15':
            element_sensitive = C3D15_Sensitivity(
                elems_index=elems._elems_index,
                elems=elems._elems,
                fea=fe)
        elif elems.__class__.__name__ == 'C3D15Transition12':
            element_sensitive = C3D15Transition12_Sensitivity(
                elems_index=elems._elems_index,
                elems=elems._elems,
                fea=fe)
        elif elems.__class__.__name__ == 'C3D4':
            element_sensitive = C3D4_Sensitivity(
                elems_index=elems._elems_index,
                elems=elems._elems,
                fea=fe)
        elif elems.__class__.__name__ == 'C3D6':
            element_sensitive = C3D6_Sensitivity(
                elems_index=elems._elems_index,
                elems=elems._elems,
                fea=fe)
        element_sensitive.set_materials(elems.materials)
        return element_sensitive

class C3D10_Sensitivity(SensitivityElement):

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray,
                 fea) -> None:
        super().__init__(elems, elems_index)

        self.shape_function = [
            torch.tensor([[1., -3., -3., -3., 4., 4., 4., 2., 2., 2.],
                          [0., -1., 0., 0., 0., 0., 0., 2., 0., 0.],
                          [0., 0., -1., 0., 0., 0., 0., 0., 2., 0.],
                          [0., 0., 0., -1., 0., 0., 0., 0., 0., 2.],
                          [0., 4., 0., 0., -4., 0., -4., -4., 0., 0.],
                          [0., 0., 0., 0., 4., 0., 0., 0., 0., 0.],
                          [0., 0., 4., 0., -4., -4., 0., 0., -4., 0.],
                          [0., 0., 0., 4., 0., -4., -4., 0., 0., -4.],
                          [0., 0., 0., 0., 0., 0., 4., 0., 0., 0.],
                          [0., 0., 0., 0., 0., 4., 0., 0., 0., 0.]])
        ]
        self.gaussian_weight = torch.tensor([1 / 24, 1 / 24, 1 / 24, 1 / 24])
        self.num_nodes_per_elem = 10
        self._num_gaussian = 4

        alpha = 0.58541020
        beta = 0.13819660
        self.point_request_ref = torch.tensor([[beta, beta, beta],
                                               [alpha, beta, beta],
                                               [beta, alpha, beta],
                                               [beta, beta, alpha]])

        self.initialize_from_p0(fea)


class C3D15_Sensitivity(SensitivityElement):

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray,
                 fea) -> None:
        super().__init__(elems, elems_index)

        self.shape_function = [
            torch.tensor([[
                0, -1.0, -1.0, -0.5, 2.0, 1.5, 1.5, 1.0, 1.0, 0.5, 0, 0, -1.0,
                -0.5, -0.5, -1.0, -2.0, 0, 0, 0
            ],
                          [
                              0, -1.0, 0, 0, 0, 0, 0.5, 1.0, 0, 0, 0, 0, 0, 0,
                              0.5, -1.0, 0, 0, 0, 0
                          ],
                          [
                              0, 0, -1.0, 0, 0, 0.5, 0, 0, 1.0, 0, 0, 0, -1.0,
                              0.5, 0, 0, 0, 0, 0, 0
                          ],
                          [
                              0, -1.0, -1.0, 0.5, 2.0, -1.5, -1.5, 1.0, 1.0,
                              0.5, 0, 0, 1.0, -0.5, -0.5, 1.0, 2.0, 0, 0, 0
                          ],
                          [
                              0, -1.0, 0, 0, 0, 0, -0.5, 1.0, 0, 0, 0, 0, 0, 0,
                              0.5, 1.0, 0, 0, 0, 0
                          ],
                          [
                              0, 0, -1.0, 0, 0, -0.5, 0, 0, 1.0, 0, 0, 0, 1.0,
                              0.5, 0, 0, 0, 0, 0, 0
                          ],
                          [
                              0, 2.0, 0, 0, -2.0, 0, -2.0, -2.0, 0, 0, 0, 0, 0,
                              0, 0, 2.0, 2.0, 0, 0, 0
                          ],
                          [
                              0, 0, 0, 0, 2.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                              -2.0, 0, 0, 0
                          ],
                          [
                              0, 0, 2.0, 0, -2.0, -2.0, 0, 0, -2.0, 0, 0, 0,
                              2.0, 0, 0, 0, 2.0, 0, 0, 0
                          ],
                          [
                              0, 2.0, 0, 0, -2.0, 0, 2.0, -2.0, 0, 0, 0, 0, 0,
                              0, 0, -2.0, -2.0, 0, 0, 0
                          ],
                          [
                              0, 0, 0, 0, 2.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                              2.0, 0, 0, 0
                          ],
                          [
                              0, 0, 2.0, 0, -2.0, 2.0, 0, 0, -2.0, 0, 0, 0,
                              -2.0, 0, 0, 0, -2.0, 0, 0, 0
                          ],
                          [
                              1.0, -1.0, -1.0, 0, 0, 0, 0, 0, 0, -1.0, 0, 0, 0,
                              1.0, 1.0, 0, 0, 0, 0, 0
                          ],
                          [
                              0, 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1.0,
                              0, 0, 0, 0, 0
                          ],
                          [
                              0, 0, 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1.0, 0,
                              0, 0, 0, 0, 0
                          ]]),
        ]
        gaussian_weight_triangle = torch.tensor([1 / 6, 1 / 6, 1 / 6])
        gaussian_points_triangle = torch.tensor([[1 / 6, 1 / 6],
                                                    [2 / 3, 1 / 6],
                                                    [1 / 6, 2 / 3]])

        gaussian_weight_height = torch.tensor([5 / 9, 8 / 9, 5 / 9])
        gaussian_points_height = torch.tensor(
            [-np.sqrt(3 / 5), 0, np.sqrt(3 / 5)])

        # Combine weights and points for 3D integration
        self.gaussian_weight = torch.einsum(
            'i,j->ij', gaussian_weight_triangle,
            gaussian_weight_height).flatten()
        self.point_request_ref = torch.cat([
            gaussian_points_triangle,
            torch.zeros([gaussian_points_triangle.shape[0], 1])
        ],
                        dim=1)
        self.point_request_ref = self.point_request_ref.reshape([-1, 1, 3
                            ]).repeat([1, gaussian_points_height.shape[0], 1])
        self.point_request_ref[:, :, 2] = gaussian_points_height.reshape([1, -1])

        self.point_request_ref = self.point_request_ref.reshape([-1, 3])
        # Gauss integration points setup
        self.num_nodes_per_elem = 15
        self._num_gaussian = 9

        self.initialize_from_p0(fea)

class C3D15Transition12_Sensitivity(SensitivityElement):

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray,
                 fea) -> None:
        super().__init__(elems, elems_index)

        self.shape_function = [
            torch.tensor([[
                0, -1.0, -1.0, -0.5, 2.0, 1.5, 1.5, 1.0, 1.0, 0.5, 0, 0, -1.0,
                -0.5, -0.5, -1.0, -2.0, 0, 0, 0
            ],
                          [
                              0, -1.0, 0, 0, 0, 0, 0.5, 1.0, 0, 0, 0, 0, 0, 0,
                              0.5, -1.0, 0, 0, 0, 0
                          ],
                          [
                              0, 0, -1.0, 0, 0, 0.5, 0, 0, 1.0, 0, 0, 0, -1.0,
                              0.5, 0, 0, 0, 0, 0, 0
                          ],
                          [
                              0, -1.0, -1.0, 0.5, 2.0, -1.5, -1.5, 1.0, 1.0,
                              0.5, 0, 0, 1.0, -0.5, -0.5, 1.0, 2.0, 0, 0, 0
                          ],
                          [
                              0, -1.0, 0, 0, 0, 0, -0.5, 1.0, 0, 0, 0, 0, 0, 0,
                              0.5, 1.0, 0, 0, 0, 0
                          ],
                          [
                              0, 0, -1.0, 0, 0, -0.5, 0, 0, 1.0, 0, 0, 0, 1.0,
                              0.5, 0, 0, 0, 0, 0, 0
                          ],
                          [
                              0, 2.0, 0, 0, -2.0, 0, -2.0, -2.0, 0, 0, 0, 0, 0,
                              0, 0, 2.0, 2.0, 0, 0, 0
                          ],
                          [
                              0, 0, 0, 0, 2.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                              -2.0, 0, 0, 0
                          ],
                          [
                              0, 0, 2.0, 0, -2.0, -2.0, 0, 0, -2.0, 0, 0, 0,
                              2.0, 0, 0, 0, 2.0, 0, 0, 0
                          ],
                          [
                              0, 2.0, 0, 0, -2.0, 0, 2.0, -2.0, 0, 0, 0, 0, 0,
                              0, 0, -2.0, -2.0, 0, 0, 0
                          ],
                          [
                              0, 0, 0, 0, 2.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                              2.0, 0, 0, 0
                          ],
                          [
                              0, 0, 2.0, 0, -2.0, 2.0, 0, 0, -2.0, 0, 0, 0,
                              -2.0, 0, 0, 0, -2.0, 0, 0, 0
                          ],
                          [
                              1.0, -1.0, -1.0, 0, 0, 0, 0, 0, 0, -1.0, 0, 0, 0,
                              1.0, 1.0, 0, 0, 0, 0, 0
                          ],
                          [
                              0, 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1.0,
                              0, 0, 0, 0, 0
                          ],
                          [
                              0, 0, 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1.0, 0,
                              0, 0, 0, 0, 0
                          ]]),
        ]

        self.shape_function[0][0] += 0.5 * self.shape_function[0][6]
        self.shape_function[0][0] += 0.5 * self.shape_function[0][8]
        self.shape_function[0][1] += 0.5 * self.shape_function[0][7]
        self.shape_function[0][1] += 0.5 * self.shape_function[0][6]
        self.shape_function[0][2] += 0.5 * self.shape_function[0][8]
        self.shape_function[0][2] += 0.5 * self.shape_function[0][7]
        self.shape_function[0][6] = 0.
        self.shape_function[0][7] = 0.
        self.shape_function[0][8] = 0.

        gaussian_weight_triangle = torch.tensor([1 / 6, 1 / 6, 1 / 6])
        gaussian_points_triangle = torch.tensor([[1 / 6, 1 / 6],
                                                    [2 / 3, 1 / 6],
                                                    [1 / 6, 2 / 3]])

        gaussian_weight_height = torch.tensor([5 / 9, 8 / 9, 5 / 9])
        gaussian_points_height = torch.tensor(
            [-np.sqrt(3 / 5), 0, np.sqrt(3 / 5)])

        # Combine weights and points for 3D integration
        self.gaussian_weight = torch.einsum(
            'i,j->ij', gaussian_weight_triangle,
            gaussian_weight_height).flatten()
        self.point_request_ref = torch.cat([
            gaussian_points_triangle,
            torch.zeros([gaussian_points_triangle.shape[0], 1])
        ],
                        dim=1)
        self.point_request_ref = self.point_request_ref.reshape([-1, 1, 3
                            ]).repeat([1, gaussian_points_height.shape[0], 1])
        self.point_request_ref[:, :, 2] = gaussian_points_height.reshape([1, -1])

        self.point_request_ref = self.point_request_ref.reshape([-1, 3])
        # Gauss integration points setup
        self.num_nodes_per_elem = 15
        self._num_gaussian = 9

        self.initialize_from_p0(fea)


class C3D6_Sensitivity(SensitivityElement):

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray,
                 fea) -> None:
        super().__init__(elems, elems_index)

        self.shape_function = [
            torch.tensor([
                [0.5, -0.5, -0.5, -0.5, 0.0, 0.5, 0.5],
                [0.0, 0.5, 0.0, 0.0, 0.0, 0.0, -0.5],
                [0.0, 0.0, 0.5, 0.0, 0.0, -0.5, 0.0],
                [0.5, -0.5, -0.5, 0.5, 0.0, -0.5, -0.5],
                [0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.5],
                [0.0, 0.0, 0.5, 0.0, 0.0, 0.5, 0.0]]),
        ]
        self.gaussian_weight = torch.tensor([1 / 2, 1 / 2, ])
        self.point_request_ref = torch.tensor([[1/3, 1/3, 1 / np.sqrt(3)],
                           [1/3, 1/3, -1 / np.sqrt(3)]])

        # Gauss integration points setup
        self.num_nodes_per_elem = 6
        self._num_gaussian = 2

        self.initialize_from_p0(fea)


class C3D4_Sensitivity(SensitivityElement):

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray,
                 fea) -> None:
        super().__init__(elems, elems_index)

        self.shape_function = [
            torch.tensor([[1.0, -1.0, -1.0, -1.0], [0.0, 1.0, 0.0, 0.0],
                          [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
        ]
        self.gaussian_weight = torch.tensor([1 / 6])
        self.num_nodes_per_elem = 4
        self._num_gaussian = 1

        self.point_request_ref = torch.tensor([[0.25, 0.25, 0.25]])

        self.initialize_from_p0(fea)
