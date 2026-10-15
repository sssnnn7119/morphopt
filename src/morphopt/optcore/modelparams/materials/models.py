"""TorchFEA material models exposed by :class:`MaterialsParams`."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar

import torchfea


class MaterialModels:
    """Material parameter types and their TorchFEA material classes."""

    @dataclass(frozen=True)
    class MaterialParameters:
        """Base type for all material parameter objects."""

        material_class: ClassVar[type[torchfea.materials.Materials_Base]]

    @dataclass(frozen=True)
    class LinearElasticParams(MaterialParameters):
        """Parameters for ``torchfea.materials.LinearElastic``."""

        E: float
        nu: float
        material_class: ClassVar[type[torchfea.materials.Materials_Base]] = \
            torchfea.materials.LinearElastic

    @dataclass(frozen=True)
    class NeoHookeanParams(MaterialParameters):
        """Parameters for ``torchfea.materials.NeoHookean``."""

        mu: float
        kappa: float
        material_class: ClassVar[type[torchfea.materials.Materials_Base]] = \
            torchfea.materials.NeoHookean

    @dataclass(frozen=True)
    class NeoHookeanLnJParams(MaterialParameters):
        """Parameters for ``torchfea.materials.NeoHookeanLnJ``."""

        mu: float
        kappa: float
        material_class: ClassVar[type[torchfea.materials.Materials_Base]] = \
            torchfea.materials.NeoHookeanLnJ

    @dataclass(frozen=True)
    class MooneyRivlinParams(MaterialParameters):
        """Parameters for ``torchfea.materials.MooneyRivlin``."""

        c10: float
        c01: float
        kappa: float
        material_class: ClassVar[type[torchfea.materials.Materials_Base]] = \
            torchfea.materials.MooneyRivlin

    @dataclass(frozen=True)
    class YeohParams(MaterialParameters):
        """Parameters for ``torchfea.materials.Yeoh``."""

        c1: float
        c2: float
        c3: float
        kappa: float
        material_class: ClassVar[type[torchfea.materials.Materials_Base]] = \
            torchfea.materials.Yeoh

    @dataclass(frozen=True)
    class GentParams(MaterialParameters):
        """Parameters for ``torchfea.materials.Gent``."""

        mu: float
        Jm: float
        kappa: float
        material_class: ClassVar[type[torchfea.materials.Materials_Base]] = \
            torchfea.materials.Gent

    @dataclass(frozen=True)
    class ArrudaBoyceParams(MaterialParameters):
        """Parameters for ``torchfea.materials.ArrudaBoyce``."""

        mu: float
        N: float
        kappa: float
        material_class: ClassVar[type[torchfea.materials.Materials_Base]] = \
            torchfea.materials.ArrudaBoyce

    @dataclass(frozen=True)
    class OgdenParams(MaterialParameters):
        """Parameters for ``torchfea.materials.Ogden``."""

        mu: float
        alpha: float | list[float]
        kappa: float
        material_class: ClassVar[type[torchfea.materials.Materials_Base]] = \
            torchfea.materials.Ogden

    @classmethod
    def create_material(
            cls,
            material_parameters: MaterialParameters,
    ) -> torchfea.materials.Materials_Base:
        """Create a TorchFEA material from its typed parameter object."""
        if not isinstance(material_parameters, cls.MaterialParameters):
            raise TypeError(
                "material_parameters must be a MaterialModels parameter object.")
        parameters = {
            field.name: getattr(material_parameters, field.name)
            for field in fields(material_parameters)
        }
        return material_parameters.material_class(**parameters)
