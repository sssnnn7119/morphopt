"""Typed constructors for TorchFEA constitutive material objects."""

from __future__ import annotations

import torchfea

from .parameters import (
    ArrudaBoyceParams,
    GentParams,
    LinearElasticParams,
    MaterialParameters,
    MooneyRivlinParams,
    NeoHookeanLnJParams,
    NeoHookeanParams,
    OgdenParams,
    YeohParams,
)


class MaterialModels:
    """Create native material models from V4's explicit parameter objects."""

    @staticmethod
    def create_material(
        parameters: MaterialParameters,
    ) -> torchfea.materials.Materials_Base:
        """Create one TorchFEA constitutive model from ``parameters``.

        This is the single translation point from descriptive V4 field names
        to the concise names used by TorchFEA constructors.
        """
        if isinstance(parameters, LinearElasticParams):
            return torchfea.materials.LinearElastic(
                E=parameters.youngs_modulus,
                nu=parameters.poisson_ratio,
            )
        if isinstance(parameters, NeoHookeanParams):
            return torchfea.materials.NeoHookean(
                mu=parameters.shear_modulus,
                kappa=parameters.bulk_modulus,
            )
        if isinstance(parameters, NeoHookeanLnJParams):
            return torchfea.materials.NeoHookeanLnJ(
                mu=parameters.shear_modulus,
                kappa=parameters.bulk_modulus,
            )
        if isinstance(parameters, MooneyRivlinParams):
            return torchfea.materials.MooneyRivlin(
                c10=parameters.c10,
                c01=parameters.c01,
                kappa=parameters.bulk_modulus,
            )
        if isinstance(parameters, YeohParams):
            return torchfea.materials.Yeoh(
                c1=parameters.c10,
                c2=parameters.c20,
                c3=parameters.c30,
                kappa=parameters.bulk_modulus,
            )
        if isinstance(parameters, GentParams):
            return torchfea.materials.Gent(
                mu=parameters.shear_modulus,
                Jm=parameters.limiting_chain_parameter,
                kappa=parameters.bulk_modulus,
            )
        if isinstance(parameters, ArrudaBoyceParams):
            return torchfea.materials.ArrudaBoyce(
                mu=parameters.shear_modulus,
                N=parameters.chain_segments,
                kappa=parameters.bulk_modulus,
            )
        if isinstance(parameters, OgdenParams):
            return torchfea.materials.Ogden(
                mu=list(parameters.shear_moduli),
                alpha=list(parameters.exponents),
                kappa=parameters.bulk_modulus,
            )
        raise TypeError(f"Unsupported material parameters: {type(parameters).__name__}")
