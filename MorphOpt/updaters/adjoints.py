import torch


class Adjoints:
    def __init__(self):
        self.ADJu: torch.Tensor
        """the adjoint displacement for the displacement"""
        self.ADJudp: torch.Tensor
        """the adjoint displacement for the Jacobian"""
        self.ADJu_udp: torch.Tensor
        """the adjoint Jacobian for the displacement at the Jacobian projection"""
        self.ADJudf: torch.Tensor
        """the adjoint displacement for the compliance matrix"""
        self.ADJu_udf: torch.Tensor
        """the adjoint Jacobian for the compliance matrix at the Jacobian projection"""