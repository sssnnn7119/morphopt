import ctypes
import math
import os
import time
import torch
import numpy as np

_current_path = os.path.dirname(os.path.abspath(__file__))
class Surface_Base(object):
    faceApi = ctypes.WinDLL(_current_path + '/DLLs/geometric_functions.dll')
    # region virtual functions
    def __init__(self, symmetric: list[int] = None) -> None:
        """
        define symmetric constrain
            [
                symmetric type: 
                    0:None
                    1:Axis
                    2:Rotation
                parameter: 
                    1: the axis(xy2, yz0, xz1)
                    2: num_fold
            ]
        """
        if symmetric == None:
            symmetric = [0]
        self._symmetric = symmetric

        self.control_points: torch.Tensor
        """
        the control points of the surface 
        """

        self.pre_edges: torch.Tensor
        """
        the pre edges of the pre mesh
        """
        
    def map(self, Coordinates: torch.Tensor):
        pass

    def _show(self, color, alpha):
        pass

    def show(self, color, alpha):
        pass

    def symmetric_reinitialize(self):
        pass

    def save_to_file(self, filename):
        pass

    @staticmethod
    def load_from_file(filename):
        pass

    def get_surface_value(self,
                          ref_points: torch.Tensor = None,
                          derivatives: int = 0):
        pass

    def pre_load(self):
        pass

    def refine_surface(self):
        pass

    def _partial_derivative(self,
                            ref_points: torch.Tensor = None,
                            controlpoints: bool = False,
                            derivative: int = 0):
        pass

    # endregion

    # region geometric functions
    @staticmethod
    @torch.jit.script
    def _sparse_sum(indices: torch.Tensor,
                    values: torch.Tensor,
                    dim: int = 1,
                    numel_output: int = -1):
        if numel_output == -1:
            numel_output = indices[dim].max().item() + 1
        shape_output = list(values.shape[:-1]) + [numel_output]
        values = values.reshape([-1, values.shape[-1]])
        result = torch.zeros([values.shape[0], numel_output],
                             device=values.device)
        for i in range(values.shape[0]):
            result[i].scatter_add_(0, indices[dim], values[i])
        return result.reshape(shape_output)

    @staticmethod
    def _from_AdI_to_Adru(AdI: torch.Tensor = None,
                          AdII: torch.Tensor = None,
                          Idru: torch.Tensor = None,
                          IIdru: torch.Tensor = None,
                          IIdru2: torch.Tensor = None):
        if AdI is None:
            AdI = torch.zeros([1, 1, 1])
        if AdII is None:
            AdII = torch.zeros([1, 1, 1])
        if Idru is None:
            Idru = torch.zeros([1, 1, 1, 1, 1])
        if IIdru is None:
            IIdru = torch.zeros([1, 1, 1, 1, 1])

        Adru = torch.einsum('mnp, mnirp->irp', AdI, Idru) + \
                    torch.einsum('mnp, mnirp->irp', AdII, IIdru)
        Adru2 = torch.einsum('mnp, mnirsp->irsp', AdII, IIdru2)
        return Adru, Adru2

    @staticmethod
    def _from_AdI_to_Adru_2(AdI: torch.Tensor = None,
                            AdII: torch.Tensor = None,
                            AdI_2: torch.Tensor = None,
                            AdIdII: torch.Tensor = None,
                            AdII_2: torch.Tensor = None,
                            Idru: torch.Tensor = None,
                            IIdru: torch.Tensor = None,
                            IIdru2: torch.Tensor = None,
                            Idru_2: torch.Tensor = None,
                            IIdru_2: torch.Tensor = None,
                            IIdrudru2: torch.Tensor = None):
        """
        return: Adru_2, Adrudru2, Adru2_2
        """

        if AdI is None:
            AdI = torch.zeros([1, 1, 1])
        if AdII is None:
            AdII = torch.zeros([1, 1, 1])
        if AdI_2 is None:
            AdI_2 = torch.zeros([1, 1, 1, 1, 1])
        if AdIdII is None:
            AdIdII = torch.zeros([1, 1, 1, 1, 1])
        if AdII_2 is None:
            AdII_2 = torch.zeros([1, 1, 1, 1, 1])

        if Idru is None:
            Idru = torch.zeros([1, 1, 1, 1, 1])
        if IIdru is None:
            IIdru = torch.zeros([1, 1, 1, 1, 1])
        if IIdru2 is None:
            IIdru2 = torch.zeros([1, 1, 1, 1, 1, 1])
        if Idru_2 is None:
            Idru_2 = torch.zeros([1, 1, 1, 1, 1, 1, 1])
        if IIdru_2 is None:
            IIdru_2 = torch.zeros([1, 1, 1, 1, 1, 1, 1])
        if IIdrudru2 is None:
            IIdrudru2 = torch.zeros([1, 1, 1, 1, 1, 1, 1, 1])

        temp = torch.einsum('MNmnp, MNirp, mnjsp->irjsp', AdIdII, Idru, IIdru)
        Adru_2 = torch.einsum('mnp, mnirjsp->irjsp', AdI, Idru_2) + \
                    torch.einsum('MNmnp, MNirp, mnjsp->irjsp', AdI_2, Idru, Idru) + \
                    torch.einsum('mnp, mnirjsp->irjsp', AdII, IIdru_2) + \
                    torch.einsum('MNmnp, MNirp, mnjsp->irjsp', AdII_2, IIdru, IIdru) + \
                    temp + \
                    temp.permute([2, 3, 0, 1, 4])

        Adrudru2 = torch.einsum('MNmnp, MNirp, mnjsqp->irjsqp', AdIdII, Idru, IIdru2) + \
                    torch.einsum('MNmnp, MNirp, mnjsqp->irjsqp', AdII_2, IIdru, IIdru2) + \
                    torch.einsum('MNp, MNirjsqp->irjsqp', AdII, IIdrudru2)

        Adru2_2 = torch.einsum('MNmnp, MNiosp, mnjqrp->iosjqrp', AdII_2,
                               IIdru2, IIdru2)
        return Adru_2, Adrudru2, Adru2_2

    @staticmethod
    def _from_Adr_to_Adot(indices: torch.Tensor,
                          Adr: torch.Tensor = None,
                          Adru: torch.Tensor = None,
                          Adru2: torch.Tensor = None,
                          rdot: torch.Tensor = None,
                          rdudot: torch.Tensor = None,
                          rdu2dot: torch.Tensor = None,
                          numel_output: int = None):
        if Adr is None:
            Adr = torch.zeros([1, 1])
        else:
            Adr = Adr.index_select(-1, indices[1])

        if Adru is None:
            Adru = torch.zeros([1, 1, 1])
        else:
            Adru = Adru.index_select(-1, indices[1])

        if Adru2 is None:
            Adru2 = torch.zeros([1, 1, 1, 1])
        else:
            Adru2 = Adru2.index_select(-1, indices[1])

        if rdot is None:
            rdot = torch.zeros([1])

        if rdudot is None:
            rdudot = torch.zeros([1, 1])

        if rdu2dot is None:
            rdu2dot = torch.zeros([1, 1, 1])

        Adot = torch.einsum('ip, p->ip', Adr, rdot) + \
               torch.einsum('irp, rp->ip', Adru, rdudot) + \
               torch.einsum('irsp, rsp->ip', Adru2, rdu2dot)

        if numel_output is None:
            numel_output = int(indices[0].max().item() + 1)
        Adot = Adot.reshape([-1, int(Adot.shape[-1])])
        result = torch.zeros([int(Adot.shape[0]), numel_output],
                             device=Adot.device)
        for i in range(Adot.shape[0]):
            result[i].scatter_add_(0, indices[0], Adot[i])
        return result

    @staticmethod
    # @torch.jit.script
    def _from_Adr_to_Adot_2(indices: torch.Tensor,
                            Adr_2: torch.Tensor = torch.zeros([0]),
                            Adru_2: torch.Tensor = torch.zeros([0]),
                            Adrudru2: torch.Tensor = torch.zeros([0]),
                            Adru2_2: torch.Tensor = torch.zeros([0]),
                            rdot: torch.Tensor = torch.zeros([0]),
                            rdudot: torch.Tensor = torch.zeros([0]),
                            rdu2dot: torch.Tensor = torch.zeros([0])):

        indices_new = indices[1] * (indices[0].max() + 10) + indices[0]
        argsort = indices_new.argsort()
        # reorder the data
        indices0 = indices[:, argsort]

        num_points = int(indices[1].max().item() + 1)

        if Adr_2.numel() == 0:
            Adr_2 = torch.zeros([1, 1, num_points], device=indices.device)
        if Adru_2.numel() == 0:
            Adru_2 = torch.zeros([1, 1, 1, 1, num_points],
                                 device=indices.device)
        if Adrudru2.numel() == 0:
            Adrudru2 = torch.zeros([1, 1, 1, 1, 1, num_points],
                                   device=indices.device)
        if Adru2_2.numel() == 0:
            Adru2_2 = torch.zeros([1, 1, 1, 1, 1, 1, num_points],
                                  device=indices.device)

        if rdot.numel() == 0:
            rdot0 = torch.zeros([int(indices.shape[1])], device=indices.device)
        else:
            rdot0 = rdot[argsort]
        if rdudot.numel() == 0:
            rdudot0 = torch.zeros([1, int(indices.shape[1])],
                                  device=indices.device)
        else:
            rdudot0 = rdudot[:, argsort]
        if rdu2dot.numel() == 0:
            rdu2dot0 = torch.zeros([1, 1, int(indices.shape[1])],
                                   device=indices.device)
        else:
            rdu2dot0 = rdu2dot[:, :, argsort]

        indices_num = torch.bincount(indices0[1])

        indices_index_cusum = torch.cat([
            torch.tensor([0], dtype=indices_num.dtype, device=Adru_2.device),
            indices_num.cumsum(0)
        ])

        indices_num_unique = torch.unique(indices_num)

        numel_control_points = int(indices[0].max().item() + 1)
        numel_points = int(indices[1].max().item() + 1)

        Adot_2 = torch.sparse_coo_tensor(
            indices=torch.zeros([4, 0],
                                dtype=indices0.dtype,
                                device=indices0.device),
            values=torch.zeros([0], device=Adru_2.device),
            size=[3, numel_control_points, 3, numel_control_points],
            dtype=Adru_2.dtype,
            device=Adru_2.device).coalesce()

        for i in range(len(indices_num_unique)):
            ind = indices_num_unique[i]
            index_Adru = torch.where(indices_num == ind)[0]
            index_now = (indices_index_cusum[index_Adru] + torch.arange(
                ind, dtype=indices_num.dtype,
                device=indices_num.device).unsqueeze(-1))
            index_indices = indices0[0][index_now.flatten()].reshape_as(
                index_now)

            Adr_2_now = Adr_2.index_select(-1, index_Adru)
            Adru_2_now = Adru_2.index_select(-1, index_Adru)
            Adrudru2_now = Adrudru2.index_select(-1, index_Adru)
            Adru2_2_now = Adru2_2.index_select(-1, index_Adru)

            rdot_now = rdot0[index_now.flatten()].reshape(
                [int(ind.item()), -1])
            rdudot_now = rdudot0[:, index_now.flatten()].reshape(
                [int(rdudot0.shape[0]),
                 int(ind.item()), -1])
            rdu2dot_now = rdu2dot0[:, :, index_now.flatten()].reshape([
                int(rdu2dot0.shape[0]),
                int(rdu2dot0.shape[0]),
                int(ind.item()), -1
            ])

            v0 = torch.einsum('ijp, rp, sp->irjsp', Adr_2_now, rdot_now,
                              rdot_now)
            v1 = torch.einsum('imjnp, mrp, nsp->irjsp', Adru_2_now, rdudot_now,
                              rdudot_now)
            v2 = torch.einsum('imjnbp, mrp, nbsp->irjsp', Adrudru2_now,
                              rdudot_now, rdu2dot_now)
            v2 = v2 + v2.permute([2, 3, 0, 1, 4])
            v3 = torch.einsum('imajnbp, marp, nbsp->irjsp', Adru2_2_now,
                              rdu2dot_now, rdu2dot_now)

            result_values = (v0 + v1 + v2 + v3).flatten()
            result_indices1 = torch.tensor([0, 1, 2],
                                           dtype=indices0.dtype,
                                           device=indices0.device).reshape(
                                               [3, 1, 1, 1, 1]).repeat([
                                                   1,
                                                   int(ind), 3,
                                                   int(ind),
                                                   int(index_Adru.shape[0])
                                               ])
            result_indices2 = index_indices.reshape(
                [1, int(ind), 1, 1,
                 int(index_Adru.shape[0])]).repeat([3, 1, 3,
                                                    int(ind), 1])
            result_indices3 = torch.tensor([0, 1, 2],
                                           dtype=indices0.dtype,
                                           device=indices0.device).reshape(
                                               [1, 1, 3, 1, 1]).repeat([
                                                   3,
                                                   int(ind), 1,
                                                   int(ind),
                                                   int(index_Adru.shape[0])
                                               ])
            result_indices4 = index_indices.reshape(
                [1, 1, 1, int(ind),
                 int(index_Adru.shape[0])]).repeat([3, int(ind), 3, 1, 1])

            result_indices = torch.stack([
                result_indices1, result_indices2, result_indices3,
                result_indices4
            ],
                                         dim=0).reshape([4, -1])
            index = torch.where(result_values != 0)[0]
            Adot_2 = Adot_2 + (torch.sparse_coo_tensor(
                indices=result_indices[:, index],
                values=result_values[index],
                size=[3, numel_control_points, 3, numel_control_points],
                dtype=Adru_2.dtype,
                device=Adru_2.device).coalesce())
        Adot_2 = Adot_2.coalesce()
        return Adot_2

    @staticmethod
    def _from_Sdr_to_Sdot_2(indices: torch.Tensor, Sdr_2: torch.Tensor,
                            rdot: torch.Tensor):
        """
        Sdr: [3, num_points, 3, num_points]
        rdot: [num_sparse]
        """
        num_points = Sdr_2.shape[1]
        num_control_points = int(indices[0].max().item() + 1)

        rdot = torch.sparse_coo_tensor(indices=indices.flip(0),
                                       values=rdot,
                                       size=[num_points, num_control_points],
                                       dtype=rdot.dtype,
                                       device=rdot.device).coalesce()

        Sdr_2 = Surface_Base._sparse_reshape(Sdr_2,
                                             [3 * 3 * num_points, num_points])
        Sdot = Sdr_2 @ rdot
        Sdot = Surface_Base._sparse_reshape(
            Sdot, [3, num_points, 3, num_control_points])
        Sdot = Surface_Base._sparse_permute(Sdot, [2, 3, 0, 1])
        Sdot = Surface_Base._sparse_reshape(
            Sdot, [3 * num_control_points * 3, num_points])
        Sdot = Sdot @ rdot
        Sdot = Surface_Base._sparse_reshape(
            Sdot, [3, num_control_points, 3, num_control_points])
        return Sdot

    def _get_geometric_values(self,
                              partial_derivative: list[list[torch.Tensor]],
                              derivatives: int = 0,
                              save_derivatives: bool = False):

        r, rdu, rdu2 = partial_derivative[0]

        if derivatives >= 1:
            indices, rdot, rdudot, rdu2dot = partial_derivative[1]

        result = []

        if derivatives >= 0:
            Normal0 = torch.cross(rdu[:, 1], rdu[:, 0], dim=0)
            Normal = Normal0 / torch.sqrt(torch.sum(Normal0**2, dim=0))

            I = torch.einsum('imp, inp->mnp', rdu, rdu)
            invI = I.permute([2, 0, 1]).inverse().permute([1, 2, 0])
            II = torch.einsum('imnp, ip->mnp', rdu2, Normal)

            detI = I[0, 0] * I[1, 1] - I[0, 1] * I[1, 0]
            detII = II[0, 0] * II[1, 1] - II[0, 1] * II[1, 0]

            H = 0.5 * (invI * II).sum([0, 1])
            K = detII / detI

            C = 4 * H**2 - 2 * K

            # if torch.isnan(C).sum() != 0 or torch.isinf(C).sum() != 0:
            #     print('not ok')
            result.append([Normal0, I, detI, invI, II, detII, H, K, C])

        if derivatives >= 1:
            Idru = torch.zeros([2, 2, 3, 2, C.shape[0]])
            for i in range(2):
                Idru[i, :, :, i] += rdu.transpose(0, 1)
                Idru[:, i, :, i] += rdu.transpose(0, 1)
            invII = II.permute([2, 0, 1]).inverse().permute([1, 2, 0])
            detIdru = torch.einsum('mnp, nmiop->iop', invI, Idru) * detI

            Normal0dru = torch.zeros([3, 3, 2, C.shape[0]])
            Normal0dru[0, 1, 0] = -rdu[2, 1]
            Normal0dru[0, 2, 0] = rdu[1, 1]
            Normal0dru[1, 0, 0] = rdu[2, 1]
            Normal0dru[1, 2, 0] = -rdu[0, 1]
            Normal0dru[2, 0, 0] = -rdu[1, 1]
            Normal0dru[2, 1, 0] = rdu[0, 1]
            Normal0dru[0, 1, 1] = rdu[2, 0]
            Normal0dru[0, 2, 1] = -rdu[1, 0]
            Normal0dru[1, 0, 1] = -rdu[2, 0]
            Normal0dru[1, 2, 1] = rdu[0, 0]
            Normal0dru[2, 0, 1] = rdu[1, 0]
            Normal0dru[2, 1, 1] = -rdu[0, 0]

            Normaldru = Normal0dru / detI.sqrt() - 0.5 * torch.einsum(
                'ip, jmp->ijmp', Normal0, detIdru) / detI**1.5

            IIdru = torch.einsum('imnp, ijop->mnjop', rdu2, Normaldru)
            IIdru2 = torch.zeros([2, 2, 3, 2, 2, C.shape[0]])
            for i in range(2):
                for j in range(2):
                    IIdru2[i, j, :, i, j] = Normal

            invIdI = -torch.einsum('imp, njp->ijmnp', invI, invI)
            detIdI = detI * invI.transpose(0, 1)

            detIIdII = detII * invII.transpose(0, 1)

            HdI = 0.5 * torch.einsum('ijmnp, ijp->mnp', invIdI, II)
            HdII = 0.5 * invI
            KdI = -detII / detI**2 * detIdI
            KdII = detIIdII / detI

            CdI = 8 * H * HdI - 2 * KdI
            CdII = 8 * H * HdII - 2 * KdII

            Cdru, Cdru2 = self._from_AdI_to_Adru(CdI, CdII, Idru, IIdru,
                                                 IIdru2)
            if save_derivatives:
                self.__Idru = Idru
                self.__IIdru = IIdru
                self.__IIdru2 = IIdru2
                self.__rdudot = rdudot
                self.__rdu2dot = rdu2dot

            result.append([
                Normaldru, Idru, detIdI, invIdI, IIdru, IIdru2, detIIdII, Cdru,
                Cdru2
            ])

        if derivatives >= 2:

            Idru_2 = torch.zeros([2, 2, 3, 2, 3, 2, 1])
            for m in range(2):
                for n in range(2):
                    for i in range(3):
                        Idru_2[m, n, i, m, i, n] += 1
                        Idru_2[m, n, i, n, i, m] += 1

            Normal0dru_2 = torch.zeros([3, 3, 2, 3, 2, 1])
            Normal0dru_2[0, 1, 0, 2, 1] = -1
            Normal0dru_2[0, 2, 0, 1, 1] = 1
            Normal0dru_2[1, 0, 0, 2, 1] = 1
            Normal0dru_2[1, 2, 0, 0, 1] = -1
            Normal0dru_2[2, 0, 0, 1, 1] = -1
            Normal0dru_2[2, 1, 0, 0, 1] = 1
            Normal0dru_2[0, 1, 1, 2, 0] = 1
            Normal0dru_2[0, 2, 1, 1, 0] = -1
            Normal0dru_2[1, 0, 1, 2, 0] = -1
            Normal0dru_2[1, 2, 1, 0, 0] = 1
            Normal0dru_2[2, 0, 1, 1, 0] = 1
            Normal0dru_2[2, 1, 1, 0, 0] = -1

            detIdru_2 = + torch.einsum('imp, jnp->imjnp', Idru[0,0], Idru[1,1]) \
                        + torch.einsum('imp, jnp->imjnp', Idru[1,1], Idru[0,0]) \
                        - torch.einsum('imp, jnp->imjnp', Idru[0,1], Idru[1,0]) \
                        - torch.einsum('imp, jnp->imjnp', Idru[1,0], Idru[0,1]) \
                        + I[0,0] * Idru_2[1,1] + I[1,1] * Idru_2[0,0] - I[1,0] * Idru_2[0,1] - I[0,1] * Idru_2[1,0]

            Normaldru_2 = Normal0dru_2 / detI.sqrt() \
                - 0.5*torch.einsum('aimp, jnp->aimjnp', Normal0dru, detIdru) / detI**1.5\
                - 0.5*torch.einsum('ajnp, imp->aimjnp', Normal0dru, detIdru) / detI**1.5\
                - 0.5 * torch.einsum('ap, imjnp->aimjnp', Normal0, detIdru_2) / detI**1.5 \
                + 0.75 * torch.einsum('ap, imp, jnp->aimjnp', Normal0, detIdru, detIdru) / detI**2.5

            IIdru_2 = torch.einsum('imnp, ijokrp->mnjokrp', rdu2, Normaldru_2)

            IIdrudru2 = torch.zeros([2, 2, 3, 2, 3, 2, 2, C.shape[0]])
            for m in range(2):
                for n in range(2):
                    IIdrudru2[m, n, :, :, :, m,
                              n] = Normaldru.permute([1, 2, 0, 3])

            invIdI_2 = torch.einsum('ilp,kmp,njp->ijlkmnp', invI, invI, invI)\
                     + torch.einsum('imp,nlp,kjp->ijlkmnp', invI, invI, invI)
            detIdI_2 = detI * (torch.einsum('nmp,jip->ijmnp', invI, invI) -
                               torch.einsum('jmp,nip->ijmnp', invI, invI))

            detIIdII_2 = detII * (
                torch.einsum('nmp,jip->ijmnp', invII, invII) -
                torch.einsum('jmp,nip->ijmnp', invII, invII))

            HdI_2 = 0.5 * torch.einsum('ijlkmnp, ijp->lkmnp', invIdI_2, II)
            HdIdII = 0.5 * invIdI.permute([2, 3, 0, 1, 4])
            KdI_2 = 2*detII / detI**3 * torch.einsum('ijp,mnp->ijmnp', detIdI, detIdI) + \
                    -detII / detI**2 * detIdI_2
            KdIdII = -1 / detI**2 * torch.einsum('mnp,ijp->ijmnp', detIIdII,
                                                 detIdI)
            KdII_2 = detIIdII_2 / detI

            CdI_2 = 8 * torch.einsum('ijp,mnp->ijmnp', HdI,
                                     HdI) + 8 * H * HdI_2 - 2 * KdI_2
            CdIdII = 8 * torch.einsum('ijp,mnp->ijmnp', HdI,
                                      HdII) + 8 * H * HdIdII - 2 * KdIdII
            CdII_2 = 8 * torch.einsum('ijp,mnp->ijmnp', HdII,
                                      HdII) - 2 * KdII_2

            Cdru_2, Cdrudru2, Cdru2_2 = self._from_AdI_to_Adru_2(
                CdI, CdII, CdI_2, CdIdII, CdII_2, Idru, IIdru, IIdru2, Idru_2,
                IIdru_2, IIdrudru2)

            result.append([
                Normaldru_2, Idru_2, detIdI_2, invIdI_2, IIdru_2, IIdrudru2,
                detIIdII_2, Cdru_2, Cdrudru2, Cdru2_2
            ])

        # region method first to get the Idot_2 and IIdot_2

        # @staticmethod
        # def _sparse_hessian_indices(indices: torch.Tensor):
        #     indices_new = indices[1] * indices[0].max() + indices[0]
        #     argsort = indices_new.argsort()

        #     indices0 = indices[:, argsort]

        #     indices_unique, indices_num = indices0[1].unique_consecutive(
        #         return_counts=True)
        #     indices_index_cusum = torch.cat(
        #         [torch.tensor([0]), indices_num.cumsum(0)])

        #     indices_2 = []

        #     indices_num_unique = indices_num.unique()
        #     for ind in indices_num_unique:
        #         index_Adru = torch.where(indices_num == ind)[0]
        #         index_now = (indices_index_cusum[index_Adru] +
        #                     torch.arange(ind).unsqueeze(-1))
        #         index_indices = indices0[0][index_now.flatten()].reshape_as(
        #             index_now)

        #         indices_2.append([indices0[1][index_now[0]], index_indices])

        #     return indices_2, argsort, indices_num

        # @staticmethod
        # @torch.jit.script
        # def _sparse_hessian(indices: torch.Tensor,
        #                             Adru_2: torch.Tensor, rdudot1: torch.Tensor,
        #                             rdudot2: torch.Tensor, argsort: torch.Tensor, indices_num: torch.Tensor):

        #     shape0 = list(Adru_2.shape[:(Adru_2.dim() - rdudot1.dim() - rdudot2.dim() -
        #                             1)])

        #     num0 = int(torch.prod(torch.tensor(shape0)))
        #     num1 = int(torch.prod(torch.tensor(rdudot1.shape[:-1])))
        #     num2 = int(torch.prod(torch.tensor(rdudot2.shape[:-1])))

        #     Adru_2 = Adru_2.reshape([num0] +
        #                             [Adru_2.shape[len(shape0)]] +
        #                             [num1] +
        #                             [Adru_2.shape[len(shape0) + rdudot1.dim()]] +
        #                             [num2] +
        #                             [Adru_2.shape[-1]])

        #     rdudot1 = rdudot1.reshape([-1, rdudot1.shape[-1]])
        #     rdudot2 = rdudot2.reshape([-1, rdudot2.shape[-1]])

        #     # reorder the data
        #     indices0 = indices[:, argsort]
        #     rdudot10 = rdudot1[:, argsort]
        #     rdudot20 = rdudot2[:, argsort]

        #     Adot_2 = []
        #     indices_2 = []

        #     indices_index_cusum = torch.cat(
        #         [torch.tensor([0], dtype=indices_num.dtype, device=indices_num.device), indices_num.cumsum(0)])

        #     indices_num_unique = torch.unique(indices_num)
        #     for ind in indices_num_unique:
        #         index_Adru = torch.where(indices_num == ind)[0]
        #         index_now = (indices_index_cusum[index_Adru] +
        #                     torch.arange(ind, dtype=indices_num.dtype, device=indices_num.device).unsqueeze(-1))
        #         if Adru_2.shape[-1] == 1:
        #             Adru_2_now = Adru_2
        #         else:
        #             Adru_2_now = Adru_2.index_select(-1, index_Adru)
        #         rdudot1_now = rdudot10[:, index_now.flatten()].reshape([int(rdudot10.shape[0]), int(ind.item()), -1])
        #         rdudot2_now = rdudot20[:, index_now.flatten()].reshape([int(rdudot20.shape[0]), int(ind.item()), -1])
        #         values = torch.einsum('aimjnp, mrp, nsp->airjsp', Adru_2_now,
        #                             rdudot1_now, rdudot2_now)
        #         values = values.reshape(shape0 + list(values.shape[1:]))
        #         Adot_2.append(values)
        #     return Adot_2

        # if derivatives >= 2:

        #     indices_2, argsort, indices_num = self._sparse_hessian_indices(
        #         indices)

        #     Idru_2 = torch.zeros([2, 2, 3, 2, 1, 2, 1])
        #     for m in range(2):
        #         for n in range(2):
        #             for i in range(3):
        #                 Idru_2[m, n, i, m, 0, n] += 1
        #                 Idru_2[m, n, i, n, 0, m] += 1

        #     Idot_2_values = self._sparse_hessian(
        #         indices, Idru_2, rdudot, rdudot, argsort, indices_num)

        #     Normal0dru_2 = torch.zeros([3, 3, 2, 3, 2, 1])
        #     Normal0dru_2[0, 1, 0, 2, 1] = -1
        #     Normal0dru_2[0, 2, 0, 1, 1] = 1
        #     Normal0dru_2[1, 0, 0, 2, 1] = 1
        #     Normal0dru_2[1, 2, 0, 0, 1] = -1
        #     Normal0dru_2[2, 0, 0, 1, 1] = -1
        #     Normal0dru_2[2, 1, 0, 0, 1] = 1
        #     Normal0dru_2[0, 1, 1, 2, 0] = 1
        #     Normal0dru_2[0, 2, 1, 1, 0] = -1
        #     Normal0dru_2[1, 0, 1, 2, 0] = -1
        #     Normal0dru_2[1, 2, 1, 0, 0] = 1
        #     Normal0dru_2[2, 0, 1, 1, 0] = 1
        #     Normal0dru_2[2, 1, 1, 0, 0] = -1

        #     detIdru_2 = + torch.einsum('imp, jnp->imjnp', Idru[0,0], Idru[1,1]) \
        #                 + torch.einsum('imp, jnp->imjnp', Idru[1,1], Idru[0,0]) \
        #                 - torch.einsum('imp, jnp->imjnp', Idru[0,1], Idru[1,0]) \
        #                 - torch.einsum('imp, jnp->imjnp', Idru[1,0], Idru[0,1]) \
        #                 + I[0,0] * Idru_2[1,1] + I[1,1] * Idru_2[0,0] - I[1,0] * Idru_2[0,1] - I[0,1] * Idru_2[1,0]

        #     Normaldru_2 = Normal0dru_2 / detI.sqrt() \
        #         - 0.5*torch.einsum('aimp, jnp->aimjnp', Normal0dru, detIdru) / detI**1.5\
        #         - 0.5*torch.einsum('ajnp, imp->aimjnp', Normal0dru, detIdru) / detI**1.5\
        #         - 0.5 * torch.einsum('ap, imjnp->aimjnp', Normal0, detIdru_2) / detI**1.5 \
        #         + 0.75 * torch.einsum('ap, imp, jnp->aimjnp', Normal0, detIdru, detIdru) / detI**2.5

        #     IIdru_2 = torch.einsum('imnp, ijokrp->mnjokrp', rdu2, Normaldru_2)

        #     IIdot_2_values = self._sparse_hessian(
        #         indices, IIdru_2, rdudot, rdudot, argsort, indices_num)

        #     IIdrudru2 = torch.zeros([2, 2, 3, 2, 3, 2, 2, C.shape[0]])
        #     for m in range(2):
        #         for n in range(2):
        #             IIdrudru2[m, n, :, :, :, m,
        #                       n] = Normaldru.permute([1, 2, 0, 3])

        #     IIdot_2_2_values = self._sparse_hessian(
        #         indices, IIdrudru2, rdudot, rdu2dot, argsort, indices_num)

        #     for i in range(len(IIdot_2_2_values)):
        #         IIdot_2_values[i] += IIdot_2_2_values[i] + IIdot_2_2_values[i].transpose(2, 4).transpose(3, 5)

        #     invIdI_2 = torch.einsum('ilp,kmp,njp->ijlkmnp', invI, invI, invI)\
        #              + torch.einsum('imp,nlp,kjp->ijlkmnp', invI, invI, invI)
        #     detIdI_2 = detI * (torch.einsum('nmp,jip->ijmnp', invI, invI) -
        #                        torch.einsum('jmp,nip->ijmnp', invI, invI))

        #     detIIdII_2 = detII * (
        #         torch.einsum('nmp,jip->ijmnp', invII, invII) -
        #         torch.einsum('jmp,nip->ijmnp', invII, invII))

        #     HdI_2 = 0.5 * torch.einsum('ijlkmnp, ijp->lkmnp', invIdI_2, II)
        #     HdIdII = 0.5 * invIdI.permute([2, 3, 0, 1, 4])
        #     KdI_2 = 2*detII / detI**3 * torch.einsum('ijp,mnp->ijmnp', detIdI, detIdI) + \
        #             -detII / detI**2 * detIdI_2
        #     KdIdII = -1 / detI**2 * torch.einsum('mnp,ijp->ijmnp', detIIdII,
        #                                          detIdI)
        #     KdII_2 = detIIdII_2 / detI

        #     CdI_2 = 8 * torch.einsum('ijp,mnp->ijmnp', HdI,
        #                              HdI) + 8 * H * HdI_2 - 2 * KdI_2
        #     CdIdII = 8 * torch.einsum('ijp,mnp->ijmnp', HdI,
        #                               HdII) + 8 * H * HdIdII - 2 * KdIdII
        #     CdII_2 = 8 * torch.einsum('ijp,mnp->ijmnp', HdII, HdII) - 2 * KdII_2

        #     Cdot_2 = []

        #     indices_index_cusum = torch.cat(
        #         [torch.tensor([0]), indices_num.cumsum(0)])
        #     indices_num_unique = indices_num.unique()
        #     for i in range(len(indices_2)):
        #         ind = indices_num_unique[i]
        #         indices_dot = torch.where(indices_num == ind)[0]
        #         indices_dot = (indices_index_cusum[indices_dot] +
        #                  torch.arange(indices_2[i][1].shape[0]).unsqueeze(-1))

        #         Idot_now = Idot[:, :, :, argsort[indices_dot.view(-1)]].reshape([2,2,3,ind, -1])
        #         IIdot_now = IIdot[:, :, :, argsort[indices_dot.view(-1)]].reshape([2,2,3,ind, -1])

        #         CdI_now = CdI[:, :, indices_2[i][0]]
        #         CdII_now = CdII[:, :, indices_2[i][0]]
        #         CdI_2_now = CdI_2[:, :, :, :, indices_2[i][0]]
        #         CdII_2_now = CdII_2[:, :, :, :, indices_2[i][0]]
        #         CdIdII_now = CdIdII[:, :, :, :, indices_2[i][0]]

        #         values1 = torch.einsum('mnrsp, mnicp, rsjdp->icjdp', CdI_2_now, Idot_now, Idot_now)
        #         values2 = torch.einsum('mnrsp, mnicp, rsjdp->icjdp', CdII_2_now, IIdot_now, IIdot_now)
        #         values3 = torch.einsum('mnrsp, mnicp, rsjdp->icjdp', CdIdII_now, Idot_now, IIdot_now)
        #         values32 = values3.permute([2, 3, 0, 1, 4])
        #         values4 = torch.einsum('mnp, mnicjqp->icjqp', CdI_now, Idot_2_values[i])
        #         values5 = torch.einsum('mnp, mnicjqp->icjqp', CdII_now, IIdot_2_values[i])
        #         v = values1 + values2 + values3 + values32 + values4 + values5
        #         Cdot_2.append(v)


# torch.autograd.grad((torch.einsum('mnp, mnip->ip', CdI[:, :, indices[1]], Idot) + torch.einsum('mnp, mnip->ip', CdII[:, :, indices[1]], IIdot))[0,argsort[indices_dot[0][0]]], self.P0, retain_graph=True)[0][0, indices_2[-1][1].flatten()]
# Cdot_2[-1][0,0,0].flatten()
# endregion

        return result

    # endregion

    # region mesh method
    @staticmethod
    def _get_edges(elements: torch.Tensor):
        edge0 = torch.stack([elements[:, 0], elements[:, 1]],
                            dim=1).sort(dim=1).values
        edge1 = torch.stack([elements[:, 1], elements[:, 2]],
                            dim=1).sort(dim=1).values
        edge2 = torch.stack([elements[:, 2], elements[:, 0]],
                            dim=1).sort(dim=1).values

        edges = torch.cat([edge0, edge1, edge2], dim=0).unique(dim=0)

        return edges

    @staticmethod
    # @torch.jit.script
    def _get_adjacent_faces(faces: torch.Tensor):
        """
        the edges are sorted in the ascending order
        """

        max_node = faces.max() + 1

        edge1 = faces[:, [1, 2]].sort(dim=1).values
        edge2 = faces[:, [2, 0]].sort(dim=1).values
        edge3 = faces[:, [0, 1]].sort(dim=1).values

        edge1 = edge1[:, 0] * max_node + edge1[:, 1]
        edge2 = edge2[:, 0] * max_node + edge2[:, 1]
        edge3 = edge3[:, 0] * max_node + edge3[:, 1]

        edge_face = torch.stack([edge1, edge2, edge3], dim=1)

        edges00, adjacent_faces0 = edge_face.flatten().sort()
        edges0, num_adjacent_faces = edges00.unique_consecutive(
            return_counts=True)
        cumsum_adjacent_faces = np.array([0] +
                                         num_adjacent_faces.cumsum(0).tolist())

        index_double_faces = torch.where(num_adjacent_faces == 2)[0].tolist()
        index_single_faces = torch.where(num_adjacent_faces == 1)[0].tolist()
        index_more_faces = torch.where(num_adjacent_faces > 2)[0]
        if index_more_faces.numel() > 0:
            raise Exception('the mesh is not a manifold surface')

        adjacent_faces = torch.ones([edges0.shape[0], 2],
                                    dtype=torch.long) * -1

        adjacent_faces[index_double_faces, 0] = adjacent_faces0[
            cumsum_adjacent_faces[index_double_faces]] // 3
        adjacent_faces[index_double_faces, 1] = adjacent_faces0[
            cumsum_adjacent_faces[index_double_faces] + 1] // 3

        adjacent_faces[index_single_faces, 0] = adjacent_faces0[
            cumsum_adjacent_faces[index_single_faces]] // 3

        edges = torch.zeros([edges0.shape[0], 2],
                            dtype=faces.dtype,
                            device=faces.device)
        edges[:, 0] = edges0 // max_node
        edges[:, 1] = edges0 % max_node

        another_points_index = torch.ones([edges0.shape[0], 2],
                                          dtype=torch.long) * -1
        another_points_index[
            index_double_faces,
            0] = adjacent_faces0[cumsum_adjacent_faces[index_double_faces]] % 3
        another_points_index[index_double_faces, 1] = adjacent_faces0[
            cumsum_adjacent_faces[index_double_faces] + 1] % 3
        # another_points_index = adjacent_faces0.reshape([-1, 2]) % 3

        return edges, adjacent_faces, another_points_index

    @staticmethod
    def _refine_triangular_mesh(nodes: torch.Tensor, elems: torch.Tensor):
        edges, adjacent_faces, another_points_index = Surface_Base._get_adjacent_faces(
            elems)

        # for c++ code
        num_elements = int(elems.shape[0])
        num_nodes = int(nodes.shape[0])
        num_edges = int(edges.shape[0])

        edges = np.array(edges.tolist())
        adjacent_faces = np.array(adjacent_faces.tolist())
        another_points_index = np.array(another_points_index.tolist())
        elements = np.array(elems.tolist())
        nodes = np.array(nodes.tolist())

        edges_ptr = edges.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
        adjacent_faces_ptr = adjacent_faces.ctypes.data_as(
            ctypes.POINTER(ctypes.c_int32))
        another_points_index_ptr = another_points_index.ctypes.data_as(
            ctypes.POINTER(ctypes.c_int32))
        elements_ptr = elements.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
        nodes_ptr = nodes.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))

        result = np.zeros_like(elements)
        result_ptr = result.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
        Surface_Base.faceApi.refine_triangular_mesh(
            result_ptr, elements_ptr, num_elements, edges_ptr, num_edges,
            adjacent_faces_ptr, nodes_ptr, num_nodes)

        return torch.tensor(result.tolist())

    @staticmethod
    def _triangular_mesh(nodes: torch.Tensor):
        num_nodes = nodes.shape[0]
        nodes = np.array(nodes.tolist())
        nodes_ptr = nodes.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double))

        num_mesh = np.zeros([1], dtype=np.int32)
        num_mesh_ptr = num_mesh.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
        Surface_Base.faceApi.triangular_mesh(num_mesh_ptr, nodes_ptr, num_nodes)
        
        results = np.zeros([num_mesh[0], 3], dtype=np.int32)
        results_ptr = results.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
        Surface_Base.faceApi.get_triangular_mesh(results_ptr)

        return torch.tensor(results.tolist())
    
    @staticmethod
    def _find_boundary_edges(elements: torch.Tensor):
        edges, adjacent_faces, another_points_index = Surface_Base._get_adjacent_faces(
            elements)

        boundary_edges = edges[(adjacent_faces[:, 1] == -1) & (adjacent_faces[:, 0] != -1)]
        boundary_points = torch.unique(boundary_edges.flatten())
        
        boundary_points_circle = boundary_points[0].unsqueeze(0)

        for i in range(boundary_points.shape[0] - 1):
            benow = boundary_edges[(
                boundary_edges == boundary_points_circle[i]).sum(
                    dim=1) > 0].unique()
            ptnow = benow[0]
            if (boundary_points_circle == ptnow).sum() > 0:
                ptnow = benow[1]
                if (boundary_points_circle == ptnow).sum() > 0:
                    ptnow = benow[2]
            boundary_points_circle = torch.cat(
                [boundary_points_circle,
                ptnow.unsqueeze(0)], dim=0)

        return boundary_points_circle
    
    @staticmethod
    def _sphere_mesh(grids):
        points_plane = torch.zeros([grids.shape[0], 2])
        points_plane[:, 0] = 2 * grids[:, 0] / (1 - grids[:, 2])
        points_plane[:, 1] = 2 * grids[:, 1] / (1 - grids[:, 2])

        part1 = points_plane

        result1 = Surface_Base._triangular_mesh(part1)

        coo1 = result1

        inner_points = torch.ones([points_plane.shape[0]], dtype=torch.bool)
        inner_points[coo1.unique()] = False
        inner_points = torch.where(inner_points)[0]
        # make the boundary edges circular
        boundary_points_circle = Surface_Base._find_boundary_edges(coo1)

        part2 = points_plane[boundary_points_circle]
        aa = 0
        for i in range(boundary_points_circle.shape[0] - 1):
            ind1 = (i + 1) % boundary_points_circle.shape[0]
            aa += part2[i, 0] * part2[ind1, 1] - part2[ind1, 0] * part2[i, 1]
        if aa < 0:
            boundary_points_circle = boundary_points_circle.flip(0)

        def area(p1, p2, p3):
            return abs(p1[0] * p2[1] - p2[0] * p1[1] + p2[0] * p3[1] -
                       p3[0] * p2[1] + p3[0] * p1[1] - p1[0] * p3[1])

        def is_conterclockwise(p0, p1, p2):
            return (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (
                p1[1] - p0[1]) > 0
            
        def is_intersecting(p1, p2, q1, q2):

            if is_conterclockwise(p1, q1, q2) != is_conterclockwise(p1, q1, p2):
                return False
            if is_conterclockwise(p2, q1, q2) != is_conterclockwise(p2, q1, p1):
                return False
            if is_conterclockwise(p1, q2, q1) != is_conterclockwise(p1, q2, p2):
                return False
            if is_conterclockwise(p2, q2, q1) != is_conterclockwise(p2, q2, p1):
                return False

            return True
        
        def judge_triangle(ind0, ind1, ind2):

            p0 = points_plane[ind0]
            p1 = points_plane[ind1]
            p2 = points_plane[ind2]
            cond1 = is_conterclockwise(p0, p1, p2)
            if not cond1:
                return False
            # no other point is in the triangle
            cond2 = True
            A_012 = area(p0, p1, p2)
            for j in range(2, boundary_points_circle.shape[0]):
                if boundary_points_circle[j] == ind2 or boundary_points_circle[
                        j] == ind1 or boundary_points_circle[j] == ind0:
                    continue
                p = points_plane[boundary_points_circle[j]]
                A__12 = area(p1, p2, p)
                A__01 = area(p0, p1, p)
                A_02_ = area(p0, p2, p)
                if (A_012 - (A__12 + A__01 + A_02_)).abs() < 1e-14:
                    cond2 = False
                    break

            if not cond2:
                return False

            cond3 = True
            for j in range(boundary_points_circle.shape[0]):
                if boundary_points_circle[j] == ind0 or boundary_points_circle[
                        j] == ind1 or boundary_points_circle[j] == ind2:
                    continue

                if boundary_points_circle[
                        j - 1] == ind0 or boundary_points_circle[
                            j - 1] == ind1 or boundary_points_circle[j -
                                                                   1] == ind2:
                    continue

                if is_intersecting(
                        points_plane[ind0], points_plane[ind1],
                        points_plane[boundary_points_circle[(j - 1)]],
                        points_plane[boundary_points_circle[j]]):
                    cond3 = False
                    break
                if is_intersecting(
                        points_plane[ind1], points_plane[ind2],
                        points_plane[boundary_points_circle[(j - 1)]],
                        points_plane[boundary_points_circle[j]]):
                    cond3 = False
                    break
                if is_intersecting(
                        points_plane[ind2], points_plane[ind0],
                        points_plane[boundary_points_circle[(j - 1)]],
                        points_plane[boundary_points_circle[j]]):
                    cond3 = False
                    break
            return cond1 and cond2 and cond3

        def mesh_closed_curve(coo: torch.Tensor):
            if coo.shape[0] == 3:
                if judge_triangle(coo[0], coo[1], coo[2]):
                    return coo.unsqueeze(0)
                else:
                    return torch.zeros([0], dtype=torch.int64)
            if coo.shape[0] < 3:
                return torch.zeros([0, 3], dtype=torch.int64)

            for e in range(1, coo.shape[0]):
                ind0 = (e - 1) % coo.shape[0]
                ind1 = e

                p0 = points_plane[coo[ind0]]
                p1 = points_plane[coo[ind1]]

                for ind2 in range(coo.shape[0]):
                    if ind2 == ind0 or ind2 == ind1:
                        continue
                    p2 = points_plane[coo[ind2]]
                    # triangle is positive
                    cond = judge_triangle(coo[ind0], coo[ind1], coo[ind2])

                    if cond:

                        result = coo[[ind0, ind1, ind2]].unsqueeze(0)
                        coo_double = torch.cat([coo, coo])

                        if ind2 < ind1:
                            ii = ind2 + coo.shape[0]
                        else:
                            ii = ind2
                        coo1 = torch.cat([coo[[ind2]], coo_double[ind1:ii]], dim=0)
                        result1 = mesh_closed_curve(coo1)
                        if result1.ndim == 1:
                            continue
                        if ind0 < ind2:
                            ind00 = ind0 + coo.shape[0]
                        else:
                            ind00 = ind0
                        coo2 = torch.cat([coo[[ind0]], coo_double[ind2:ind00]],
                                        dim=0)
                        result2 = mesh_closed_curve(coo2)
                        if result2.ndim == 1:
                            continue
                        result = torch.cat([result, result1, result2], dim=0)
                        return result

            return torch.zeros([0], dtype=torch.int64)

        def insert_points(elements: torch.Tensor, index: torch.Tensor):
            for i in range(len(index)):
                # find which triangle the point is in
                for j in range(elements.shape[0]):
                    A0 = area(points_plane[elements[j, 0]],
                              points_plane[elements[j, 1]],
                              points_plane[elements[j, 2]])
                    A1 = area(points_plane[elements[j, 0]],
                              points_plane[elements[j, 1]],
                              points_plane[index[i]])
                    A2 = area(points_plane[elements[j, 1]],
                              points_plane[elements[j, 2]],
                              points_plane[index[i]])
                    A3 = area(points_plane[elements[j, 2]],
                              points_plane[elements[j, 0]],
                              points_plane[index[i]])
                    if (A0 - (A1 + A2 + A3)).abs() < 1e-14:
                        break
                # split the triangle
                elements = torch.cat([
                    elements[:j], elements[j + 1:],
                    torch.tensor([[elements[j, 0], elements[j, 1], index[i]],
                                  [elements[j, 1], elements[j, 2], index[i]],
                                  [elements[j, 2], elements[j, 0], index[i]]])
                ])
            return elements

        points_plane = torch.zeros([grids.shape[0], 2])
        points_plane[:, 0] = 2 * grids[:, 0] / (1 + grids[:, 2])
        points_plane[:, 1] = 2 * grids[:, 1] / (1 + grids[:, 2])
        coo2 = mesh_closed_curve(boundary_points_circle)

        normal0 = (
            points_plane[coo2[:, 1], 0] - points_plane[coo2[:, 0], 0]
        ) * (points_plane[coo2[:, 2], 1] - points_plane[coo2[:, 0], 1]) - (
            points_plane[coo2[:, 2], 0] - points_plane[coo2[:, 0], 0]) * (
                points_plane[coo2[:, 1], 1] - points_plane[coo2[:, 0], 1])

        normal = torch.cross(grids[coo2[:, 1]] - grids[coo2[:, 0]],
                             grids[coo2[:, 2]] - grids[coo2[:, 0]],
                             dim=1)
        normal = normal / normal.norm(dim=1).unsqueeze(1)
        point_mid = (grids[coo2[:, 0]] + grids[coo2[:, 1]] +
                     grids[coo2[:, 2]]) / 3

        coo2 = insert_points(coo2, inner_points)
        pp = torch.cat([points_plane, torch.zeros([points_plane.shape[0], 1])],
                       dim=1)
        coo2 = Surface_Base._refine_triangular_mesh(pp, coo2)

        coo = torch.cat([coo1, coo2], dim=0)

        connection = torch.tensor(coo.tolist())
        
        
        # change the order of the connection of the sphere to make the normal vector point outwards
        normal = torch.cross(grids[connection[:, 1]] - grids[connection[:, 0]],
                                grids[connection[:, 2]] - grids[connection[:, 0]],
                                dim=1)
        triangularcenter = (grids[connection[:, 0]] + grids[connection[:, 1]] + grids[connection[:, 2]]) / 3
        barycenter = grids.mean(dim=0)
        judge = (normal * (triangularcenter - barycenter)).sum(dim=1)
        index_flip = judge < 0
        connection[index_flip,
                   1], connection[index_flip,
                                  2] = connection[index_flip,
                                                  2], connection[index_flip, 1]

        # connection = self.refine_triangular_mesh(connection, grids)
        return connection

    @staticmethod
    def fibonacci_grid(N, dimen=3):
        """
        return the points on the sphere
        :param N: number of points
        :param dimen: dimension of the points
        :return: points
        """
        n = torch.arange(N) + 1
        phi = (math.sqrt(5) - 1) / 2
        zn = (2 * n - 1) / N - 1
        xn = torch.sqrt(1 - zn**2) * torch.cos(2 * torch.pi * n * phi)
        yn = torch.sqrt(1 - zn**2) * torch.sin(2 * torch.pi * n * phi)

        if dimen == 3:
            return torch.stack((xn, yn, zn), dim=0)
        else:
            theta = torch.atan2(yn, xn)
            phi = torch.acos(zn / torch.sqrt(xn**2 + yn**2 + zn**2))
            return torch.stack((theta, phi), dim=0)

    # endregion

    # region sparse method
    @staticmethod
    @torch.jit.script
    def _conjugate_gradient(A_indices: torch.Tensor,
                            A_values: torch.Tensor,
                            b: torch.Tensor,
                            x0: torch.Tensor = torch.zeros([0]),
                            tol: float = 1e-3,
                            max_iter: int = 1500):
        dtype0 = A_values.dtype
        A_values = A_values.to(torch.float64)
        b = b.to(torch.float64)
        x0 = x0.to(torch.float64)
        if x0.numel() == 0:
            x0 = torch.zeros_like(b)

        A = torch.sparse_coo_tensor(A_indices, A_values,
                                    [b.shape[0], b.shape[0]]).to_sparse_csr()

        r_r0 = torch.dot(b, b)

        x = x0.clone()

        r = b - A @ x
        p = r
        rsold = torch.dot(r, r)

        for i in range(max_iter):
            Ap = A @ p
            alpha = rsold / torch.dot(p, Ap)
            x = x + alpha * p
            r = r - alpha * Ap
            rsnew = torch.dot(r, r)
            if rsnew / r_r0 < tol:
                break
            p = r + rsnew / rsold * p
            rsold = rsnew
            # if i %100 == 0:
            #     print('\riter: %d, residual: %e' % (i, rsnew / r_r0), end='')

        return x.to(A_values.device).to(dtype0)

    @staticmethod
    def _sparse_reshape(sparse_tensor: torch.Tensor, new_shape: list[int]):

        # coalesce the COO sparse tensor
        sparse_tensor = sparse_tensor.coalesce()

        # get the indices and values of the COO sparse tensor
        indices = sparse_tensor._indices()
        values = sparse_tensor._values()

        # get the number of non-zero elements
        nnz = values.numel()

        # get the original shape and new shape of the COO sparse tensor
        original_shape = sparse_tensor.shape

        # get the true index of the COO sparse tensor
        true_indices = torch.zeros([nnz], dtype=torch.long)
        for i in range(len(original_shape)):
            true_indices = true_indices * original_shape[i] + indices[i]

        # calculate the new indices of the COO sparse tensor
        new_indices = torch.zeros([len(new_shape), nnz], dtype=torch.long)
        for i in range(len(new_shape) - 1, -1, -1):
            new_indices[i, :] = true_indices % new_shape[i]
            true_indices = true_indices // new_shape[i]

        # construct the new COO sparse tensor
        new_sparse_tensor = torch.sparse_coo_tensor(new_indices,
                                                    values,
                                                    size=new_shape)

        return new_sparse_tensor

    @staticmethod
    def _sparse_permute(sparse_tensor: torch.Tensor, permutation):
        sparse_tensor = sparse_tensor.coalesce()
        indices = sparse_tensor.indices()
        values = sparse_tensor.values()
        new_indices = indices[permutation]
        return torch.sparse_coo_tensor(
            new_indices,
            values,
            size=torch.tensor(sparse_tensor.shape)[permutation].tolist())

    @staticmethod
    def _sparse_unsqueeze_repeat(sparse_tensor: torch.Tensor, dim_insert: int,
                                 num_repeat: int):
        sparse_tensor = sparse_tensor.coalesce()
        indices = sparse_tensor.indices()
        values = sparse_tensor.values().reshape([-1,
                                                 1]).repeat([1, num_repeat
                                                             ]).flatten()
        indices = indices.reshape([indices.shape[0], indices.shape[1],
                                   1]).repeat([1, 1, num_repeat])
        indices = torch.cat([
            indices[:dim_insert],
            torch.arange(num_repeat).reshape([1, 1, -1]).repeat(
                [1, indices.shape[1], 1]), indices[dim_insert:]
        ],
                            dim=0).reshape([indices.shape[0] + 1, -1])
        new_size = list(sparse_tensor.shape)
        new_size.insert(dim_insert, num_repeat)
        return torch.sparse_coo_tensor(indices, values, size=new_size)

    # endregion

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

def show_surf2(r, coo, hold=False):
    r2 = torch.zeros_like(r[0]).tolist()
    r = r.tolist()
    coo = coo.tolist()
    from mayavi import mlab
    mlab.triangular_mesh(r[0], r[1], r2, coo, opacity=1)
    surface = mlab.pipeline.surface(mlab.pipeline.triangular_mesh_source(
        r[0], r[1], r2, coo),
                                    color=(1.0 / 255, 1.0 / 255, 1.0 / 255),
                                    opacity=1)
    surface.actor.property.representation = 'wireframe'

    if not hold:
        mlab.show()

def show_plot(data):
    from matplotlib import pyplot as plt
    d = data.detach().cpu().numpy()
    plt.plot(d)

def show_points(r):
    from mayavi import mlab
    r = r.tolist()
    mlab.points3d(r[0], r[1], r[2], scale_factor=0.1, color=(1, 0, 0))
    mlab.show()

def show_points2(r, scale_factor=0.1, hold=False, color=(1, 0, 0)):
    from mayavi import mlab
    r2 = torch.zeros_like(r[0]).tolist()
    r = r.tolist()
    mlab.points3d(r[0], r[1], r2, scale_factor=scale_factor, color=color)
    if not hold:
        mlab.show()

if __name__ == '__main__':
    import ClosedSurface.CS as CS
    print(CS.current_path)
    r = torch.from_numpy(np.loadtxt('r.txt'))
    a = torch.from_numpy(np.loadtxt('a.txt', dtype=np.int64))
    knots = torch.from_numpy(np.loadtxt('knots.txt'))
    aa = Surface_Base._refine_triangular_mesh(a, r.T)
    
    normal = torch.cross(knots[a[:, 1]] - knots[a[:, 0]], knots[a[:, 2]] - knots[a[:, 0]], dim=1)
    normal = normal / normal.norm(dim=0)
    mid = (knots[a[:, 0]] + knots[a[:, 1]] + knots[a[:, 2]]) / 3
    assert False
