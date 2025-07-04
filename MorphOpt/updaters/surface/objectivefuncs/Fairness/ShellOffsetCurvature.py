
import torch
from ..BaseObj import BaseObj

class ShellOffsetCurvature(BaseObj):
    """
    Control the curvature of the shell surfaces to ensure that when the surfaces are offset along their normals, the offset surface does not self-intersect.
    This is achieved by penalizing the minus curvature of the shell surfaces.
    """

    def __init__(self, shell_thickness: float, surf_index: list[int]):
        """
        Initialize the fairness objective function with a name.
        """
        super().__init__()
        self.shell_thickness = shell_thickness
        """
        The thickness of the shell surfaces.
        """

        self.surf_index = surf_index
        """
        The indices of the surfaces to be considered for fairness.
        """


    def __call__(self, weight: list[torch.Tensor], r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor], *args, **kwargs) -> float:
        """
        Call the fairness objective function.

        Args:
            weight (list[torch.Tensor]): The weights for each point.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the fairness objective function.
        """
        penalty = torch.tensor(0., dtype=torch.float64)
        for surf_ind in self.surf_index:

            rdu_now = rdu[surf_ind]
            rdu2_now = rdu2[surf_ind]

            # Calculate the curvature
            E = (rdu_now[:, 0]**2).sum(dim=0)
            F = (rdu_now[:, 0] * rdu_now[:, 1]).sum(dim=0)
            G = (rdu_now[:, 1]**2).sum(dim=0)

            # Calculate normal vectors
            normal = torch.cross(rdu_now[:, 0], rdu_now[:, 1])
            normal_length = torch.sqrt((normal**2).sum(dim=0))
            normal = normal / normal_length

            # Calculate second fundamental form coefficients
            L = (normal * rdu2_now[:, 0, 0]).sum(dim=0)
            M = (normal * rdu2_now[:, 0, 1]).sum(dim=0)
            N = (normal * rdu2_now[:, 1, 1]).sum(dim=0)

            # Calculate principal curvatures k1 and k2
            EG_F2 = E * G - F**2
            H = (E * N - 2 * F * M + G * L) / (2 * EG_F2)  # Mean curvature
            K = (L * N - M**2) / EG_F2  # Gaussian curvature

            # Calculate the principal curvatures
            sqrt_term = torch.sqrt(torch.clamp(H**2 - K, min=0))
            k1 = H + sqrt_term
            k2 = H - sqrt_term

            # Penalize negative curvatures that cause self-intersection
            safe_radius = 1.0 / self.shell_thickness if self.shell_thickness > 0 else torch.tensor(float('inf'))

            thre = safe_radius / 20
            p=5
            indexl, l = self.barrier_function(-safe_radius*0.6-k2, thre, 0, p)
            if len(indexl) > 0:
                penalty += (l * weight[surf_ind][indexl]).sum()

        return penalty