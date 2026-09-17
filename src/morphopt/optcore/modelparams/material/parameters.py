"""Constitutive parameter value objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import torchfea


@dataclass(frozen=True, slots=True)
class MaterialParameters:
    """Immutable constitutive parameter value object."""
    def as_dict(self) -> dict[str, float | tuple[float, ...]]:
        return asdict(self)

    @property
    def material_class(self) -> type[torchfea.materials.Materials_Base]:
        return torchfea.materials.Materials_Base


@dataclass(frozen=True, slots=True)
class LinearElasticParams(MaterialParameters):
    """Linear-elastic Young's modulus and Poisson ratio."""
    youngs_modulus: float
    poisson_ratio: float


@dataclass(frozen=True, slots=True)
class NeoHookeanParams(MaterialParameters):
    """Compressible Neo-Hookean shear and bulk parameters."""
    shear_modulus: float
    bulk_modulus: float


@dataclass(frozen=True, slots=True)
class NeoHookeanLnJParams(MaterialParameters):
    """Log-J Neo-Hookean constitutive parameters."""
    shear_modulus: float
    bulk_modulus: float


@dataclass(frozen=True, slots=True)
class MooneyRivlinParams(MaterialParameters):
    """Two-term Mooney-Rivlin constitutive parameters."""
    c10: float
    c01: float
    bulk_modulus: float


@dataclass(frozen=True, slots=True)
class YeohParams(MaterialParameters):
    """Yeoh polynomial constitutive parameters."""
    c10: float
    c20: float = 0.0
    c30: float = 0.0
    bulk_modulus: float = 0.0


@dataclass(frozen=True, slots=True)
class GentParams(MaterialParameters):
    """Gent limiting-chain constitutive parameters."""
    shear_modulus: float
    limiting_chain_parameter: float
    bulk_modulus: float


@dataclass(frozen=True, slots=True)
class ArrudaBoyceParams(MaterialParameters):
    """Arruda-Boyce chain-segment constitutive parameters."""
    shear_modulus: float
    chain_segments: float
    bulk_modulus: float


@dataclass(frozen=True, slots=True)
class OgdenParams(MaterialParameters):
    """Ogden multi-term constitutive parameters."""
    shear_moduli: tuple[float, ...]
    exponents: tuple[float, ...]
    bulk_modulus: float
