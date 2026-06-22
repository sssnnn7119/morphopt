
from .basefuncs import BaseConstraints
import torch
from ..geometryinterfaces import CPGEOInterface
from .. import GeometryParams

class VolumeMaximization(BaseConstraints):

    def __init__(self, geometryparam: GeometryParams, surf_idx: int, weight: float = 1.0):
        super().__init__()
        cpgeo_interface = geometryparam.surface_list[surf_idx]
        if not isinstance(cpgeo_interface, CPGEOInterface):
            raise ValueError("cpgeo_interface must be an instance of CPGEOInterface")
        self._cpgeo_interface = cpgeo_interface
        self._weight = weight
        self._surf_idx = surf_idx

    def __call__(self, r, rdu, rdu2, *args, **kwargs):
        cpr = r[self._surf_idx]
        faces = self._cpgeo_interface._preload_data.faces

        volume = (torch.cross(cpr[faces[:, 0]], cpr[faces[:, 1]]) * cpr[faces[:, 2]] / 6.0).sum()


        return -volume * self._weight