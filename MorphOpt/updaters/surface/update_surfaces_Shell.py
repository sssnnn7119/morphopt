from tkinter import SE
from scipy import interpolate
import torch

from MorphOpt.solvers.FE_result import FE_result
from ...GLOBAL import PATH, History

from .update_surfaces import UpdaterSurfaces
from ...modelparams.surfaces.Surfaces_offset import Surfaces_offset
from ..second_derivative_element import SensitivityElement
from . import objectivefuncs

class UpdaterSurface_Shell(UpdaterSurfaces):
    """
    The Updater class is responsible for updating the parameters of the optimization process.
    It contains methods to update the parameters based on the optimization algorithm used.
    """

    def __init__(self, params, *args, **kwargs):
        """
        Initialize the Updater class with the given parameters.
        
        Parameters:
            params (Params): The parameters for the optimization process.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(params=params, *args, **kwargs)

        self.params_update: Surfaces_offset = self.params.surfaces

    def _sensitivity_interpolation(
            self, Ldot: dict[str,
                             torch.Tensor], points_request: dict[str,
                                                                 torch.Tensor],
            interpolated_points: list[tuple[torch.Tensor]]
    ) -> list[torch.Tensor]:
        """
        Interpolate the sensitivity into the structural grids.
        
        Parameters:
            Ldot (dict[str, torch.Tensor]): The sensitivity values for elements gaussian points.
                [num_points, num_surface]
            points_request (dict[str, torch.Tensor]): The coordinates of the elements.
                [num_points, 3]
            interpolated_points (list[tuple[torch.Tensor]]): The coordinates of the interpolation points.
                [num_surface, 3]
                
        Returns:
            list[torch.Tensor]: The interpolated sensitivity values for the structural grids.
                [num_surface, sensitivity]
        """

        # merge the origin coordinates
        Ldot_solid = Ldot['element-0']
        points_request_solid = points_request['element-0']

        Ldot_shell = Ldot['shell_elements']
        points_request_shell = points_request['shell_elements']

        # interpolate the sensitivity into the structral grids
        output_senNodes = []
        for surf_index in range(len(interpolated_points)):

            part_solid = interpolate.griddata(
                points_request_solid.reshape([-1, 3]).detach().cpu().numpy(),
                Ldot_solid[:, 0].flatten().detach().cpu().numpy(),
                (interpolated_points[surf_index][0][0],
                 interpolated_points[surf_index][0][1],
                 interpolated_points[surf_index][0][2]),
                method='nearest',
                fill_value=0,
                rescale=True)

            part_shell_minus = interpolate.griddata(
                points_request_shell.reshape([-1, 3]).detach().cpu().numpy(),
                Ldot_shell[:, 0].flatten().detach().cpu().numpy(),
                (interpolated_points[surf_index][0][0],
                 interpolated_points[surf_index][0][1],
                 interpolated_points[surf_index][0][2]),
                method='nearest',
                fill_value=0,
                rescale=True)

            part_shell_plus = interpolate.griddata(
                points_request_shell.reshape([-1, 3]).detach().cpu().numpy(),
                Ldot_shell[:, surf_index].flatten().detach().cpu().numpy(),
                (interpolated_points[surf_index][1][0],
                 interpolated_points[surf_index][1][1],
                 interpolated_points[surf_index][1][2]),
                method='nearest',
                fill_value=0,
                rescale=True)

            output_senNodes.append(
                torch.tensor((part_solid + part_shell_plus -
                              part_shell_minus).tolist()))

        return output_senNodes
    
    def _get_shape_derivative(
            self, fe_result: FE_result, LdU: torch.Tensor,
            LdUdp: torch.Tensor, LdUdF: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Get the shape derivative of the design variables.
        
        Args:
            fe_result (FE_result): The result of the finite element analysis.
            LdU (torch.Tensor): The sensitivity of the displacement vector.
            LdUdp (torch.Tensor): The sensitivity of the Jacobian vector.
            
        Returns:
            tuple: A tuple containing:
                - point_sensitivity dict[str, torch.Tensor]: The sensitivity of the design variables at the points.
                - Ldot dict[str, torch.Tensor]: The sensitivity of the design variables at the points.
        """
        pressure_list = fe_result.pressure_list
        device = torch.zeros(1).device

        points_request = {} 
        Ldot = {}

        for element_str in fe_result.fe.elems.keys():

            
            elems = fe_result.fe.elems[element_str]
            
            element_sensitive = SensitivityElement.get_sensitivity_element(elems=elems, fe=fe_result.fe)

            for p in range(len(pressure_list)):
                sen_U_now, sen_Udp_now, sen_UdF_now = self._cal_shape_derivative_displacement_jacobian(
                    fe=fe_result.fe,
                    element_sensitive=element_sensitive,
                    pressure_list=pressure_list[p].to(device),
                    GC0=fe_result.U[p].to(device),
                    Udp0=fe_result.Udp[p].to(device),
                    UdF0=fe_result.UdF[p].to(device),
                    ADJu=fe_result.ADJu[p].to(device),
                    ADJudp=fe_result.ADJudp[p].to(device),
                    ADJudf=fe_result.ADJudf[p].to(device),)

                if p == 0:
                    Ldot_now = torch.einsum('u, gesu->ges', LdU[p], sen_U_now) + \
                        torch.einsum('up, gesup->ges', LdUdp[p], sen_Udp_now) + \
                        torch.einsum('uf, gesuf->ges', LdUdF[p], sen_UdF_now)
                else:
                    Ldot_now += torch.einsum('u, gesu->ges', LdU[p], sen_U_now) + \
                        torch.einsum('up, gesup->ges', LdUdp[p], sen_Udp_now) + \
                        torch.einsum('uf, gesuf->ges', LdUdF[p], sen_UdF_now)

            points_request[element_str] = (element_sensitive.points_request)
            Ldot[element_str] = (Ldot_now.reshape([-1, Ldot_now.shape[-1]]))

        return points_request, Ldot

    def _get_interpolate_points(self, *args, **kwargs):
        """
        Get the interpolated points for the design variables.

        Parameters:
        *args: Additional arguments.
        **kwargs: Additional keyword arguments.

        Returns:
            list[torch.Tensor]: The interpolated points for the design variables.
        """
        r0, rdu0 = self.params_update.get_geometry_values()[:2]
        interpolated_points = []
        for sf in range(self.params_update.num_surface):

            normal = torch.cross(rdu0[sf][:, 1], rdu0[sf][:, 0], dim=0)

            normal = normal / torch.norm(normal, dim=0, keepdim=True)

            r_init = r0[sf]
            r_offset = r_init + self.params_update.thickness * normal

            interpolated_points.append(
                (r0[sf].cpu().numpy(), r_offset.cpu().numpy()))
        return interpolated_points
