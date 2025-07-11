from mayavi.mlab import surf
import torch
import FEA
import numpy as np


class SensitivityElement(FEA.elements.C3.Element_3D):

    def __init__(self, elems: np.ndarray, elems_index: np.ndarray, surf_order: torch.Tensor) -> None:
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
        self.surf_order = surf_order

    def initialize_from_p0(self, fea: FEA.Main.FEA_Main):



        self._pre_load_gaussian(self.point_request_ref, nodes=fea.nodes)

        p0 = self.point_request_ref
        self.pp = self._get_interpolation_coordinates(p0)

                # get the possible surface order
        if self.surf_order.ndim == 1:
            self.surf_order = self.surf_order.unsqueeze(0).repeat(self._elems.shape[0], 1)
        self.surf_order = self.surf_order[:, :self.num_surfaces]
        surf_order_all = self._get_all_possible_surface_order()


        self.Jacobian1 = torch.zeros([p0.shape[0], len(self._elems), 3, 3])
        self.Jacobian2 = torch.zeros([p0.shape[0], len(self._elems), 3, 3, 3])
        self.inv_Jacobian1 = torch.zeros([p0.shape[0], len(self._elems), 3, 3])
        self.inv_Jacobian2 = torch.zeros([p0.shape[0], len(self._elems), 3, 3, 3])
        self.shapeFun0 = torch.einsum('ab, gb->ga', self.shape_function[0],
                                      self.pp)
        self.shapeFun1 = torch.zeros([p0.shape[0], len(self._elems), 3, self.num_nodes_per_elem])
        self.shapeFun2 = torch.zeros([p0.shape[0], len(self._elems), 3, 3, self.num_nodes_per_elem])

        points_request = torch.zeros(
                [self.pp.shape[0], self._elems.shape[0], 3])
        

        for order_ind in range(surf_order_all.shape[0]):
            surf_order_now = surf_order_all[order_ind]

            elem_index = torch.where((self.surf_order - surf_order_now).abs().sum(1) == 0)[0]
            if elem_index.shape[0] == 0:
                continue
            elem_now = self._elems[elem_index]

            # process the shape function for the reduced order elements
            shape0_now = self._reduce_order_shape_function(self.shape_function[0], surf_order_now)

            # get the derivative of the shape function
            shape1_now = torch.stack([
                    self._shape_function_derivative(shape0_now, 0),
                    self._shape_function_derivative(shape0_now, 1),
                    self._shape_function_derivative(shape0_now, 2),
                ],
                            dim=0)
            shape2_now = torch.zeros(
                [3, 3, self.shape_function[0].shape[0], self.shape_function[0].shape[1]])
            for i in range(3):
                for j in range(3):
                    shape2_now[i, j] = self._shape_function_derivative(shape1_now[i], j)


            for i in range(self.num_nodes_per_elem):
                self.Jacobian1[:, elem_index] += torch.einsum('gb,mb,ei->geim', self.pp,
                                            shape1_now[:, i],
                                            fea.nodes[elem_now[:, i]])
                self.Jacobian2[:, elem_index] += torch.einsum('gb,mnb,ei->geimn', self.pp,
                                            shape2_now[:, :, i],
                                            fea.nodes[elem_now[:, i]])

            inv_Jacobian1_now = self.Jacobian1[:, elem_index].cpu().inverse().to(self.pp.device)
            self.inv_Jacobian1[:, elem_index] = inv_Jacobian1_now

            inv_Jacobian2_now = -torch.einsum(
                'gemj,gepk,genl,gejnp->gemlk', inv_Jacobian1_now,
                inv_Jacobian1_now, inv_Jacobian1_now, self.Jacobian2[:, elem_index])
            self.inv_Jacobian2[:, elem_index] = inv_Jacobian2_now

            Nksi1 = torch.einsum('gb,mab->gma', self.pp, shape1_now)
            Nksi2 = torch.einsum('gb,mnab->gmna', self.pp, shape2_now)

            
            self.shapeFun1[:, elem_index] = torch.einsum('gemi,gma->geia', inv_Jacobian1_now,
                                        Nksi1)
            self.shapeFun2[:, elem_index] = torch.einsum(
                'gemi, genj,gmna->geija',
                inv_Jacobian1_now, inv_Jacobian1_now, Nksi2) + torch.einsum(
                    'gemij, gma->geija', inv_Jacobian2_now, Nksi1)

            
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
                elems=elems._elems, surf_order=elems.surf_order.clone(),
                fea=fe)
        elif elems.__class__.__name__ == 'C3D15':
            element_sensitive = C3D15_Sensitivity(
                elems_index=elems._elems_index,
                elems=elems._elems, surf_order=elems.surf_order.clone(),
                fea=fe)
        elif elems.__class__.__name__ == 'C3D4':
            element_sensitive = C3D4_Sensitivity(
                elems_index=elems._elems_index,
                elems=elems._elems, surf_order=elems.surf_order.clone(),
                fea=fe)
        elif elems.__class__.__name__ == 'C3D6':
            element_sensitive = C3D6_Sensitivity(
                elems_index=elems._elems_index,
                elems=elems._elems, surf_order=elems.surf_order.clone(),
                fea=fe)
        element_sensitive.set_materials(elems.materials)
        return element_sensitive

class C3D10_Sensitivity(SensitivityElement):

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray, surf_order: torch.Tensor,
                 fea) -> None:
        super().__init__(elems, elems_index, surf_order)

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
        self.num_surfaces = 4

        alpha = 0.58541020
        beta = 0.13819660
        self.point_request_ref = torch.tensor([[beta, beta, beta],
                                               [alpha, beta, beta],
                                               [beta, alpha, beta],
                                               [beta, beta, alpha]])

        self.initialize_from_p0(fea)


class C3D15_Sensitivity(SensitivityElement):

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray, surf_order: torch.Tensor,
                 fea) -> None:
        super().__init__(elems, elems_index, surf_order)
        self.num_surfaces = 5

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


class C3D6_Sensitivity(SensitivityElement):

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray, surf_order: torch.Tensor,
                 fea) -> None:
        super().__init__(elems, elems_index, surf_order)
        self.num_surfaces = 5

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

    def __init__(self, elems_index: np.ndarray, elems: np.ndarray, surf_order: torch.Tensor,
                 fea) -> None:
        super().__init__(elems, elems_index, surf_order)
        self.num_surfaces = 4

        self.shape_function = [
            torch.tensor([[1.0, -1.0, -1.0, -1.0], [0.0, 1.0, 0.0, 0.0],
                          [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
        ]
        self.gaussian_weight = torch.tensor([1 / 6])
        self.num_nodes_per_elem = 4
        self._num_gaussian = 1

        self.point_request_ref = torch.tensor([[0.25, 0.25, 0.25]])

        self.initialize_from_p0(fea)
