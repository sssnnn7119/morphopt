"""Updater strategy metadata shared by configuration, forms and code generation."""

from dataclasses import dataclass

from ...constants import CONSTANT
from .fields import FieldSpec, field_defaults


@dataclass(frozen=True)
class StrategySpec:
    """Describe a selectable updater strategy and the fields shown by its editor."""
    name: str
    label_key: str
    fields: tuple[FieldSpec, ...] = ()
    groups: tuple[str, ...] = ("geometry", "materials")


_ADAPTIVE = CONSTANT.KERNEL.ADAPTIVE_SHAPE_UPDATE
_WEIGHT = CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT

STRATEGY_CATALOG = (
    StrategySpec(
        "FixedUpdate", "ui.strategies.fixed_update",
        (FieldSpec("value", "ui.strategies.value.label", "float", _WEIGHT,
                   minimum=0, doc_key="ui.strategies.value.help"),),
    ),
    StrategySpec(
        "SensitivityShapeUpdate", "ui.strategies.sensitivity_shape_update",
        groups=("geometry",),
    ),
    StrategySpec(
        "AdaptiveShapeUpdate", "ui.strategies.adaptive_shape_update",
        (FieldSpec("max_solves", "ui.strategies.max_solves.label", "int", _ADAPTIVE.MAX_SOLVES,
                   minimum=1, doc_key="ui.strategies.max_solves.help"),) + tuple(
            FieldSpec(key, f"ui.strategies.{key}.label", "float", default,
                      doc_key=f"ui.strategies.{key}.help")
            for key, default in (
                ("initial_tolerance", _ADAPTIVE.INITIAL_TOLERANCE),
                ("final_tolerance", _ADAPTIVE.FINAL_TOLERANCE),
                ("tightening_increment", _ADAPTIVE.TIGHTENING_INCREMENT),
                ("violation_tolerance", _ADAPTIVE.VIOLATION_TOLERANCE),
                ("weight_change_limit", _ADAPTIVE.WEIGHT_CHANGE_LIMIT),
            )
        ),
        groups=("geometry",),
    ),
)


def strategy_specs(group: str) -> dict[str, StrategySpec]:
    """Return the update strategies applicable to a geometry or material updater."""
    return {spec.name: spec for spec in STRATEGY_CATALOG if group in spec.groups}


def strategy_config(group: str, name: str | None = None) -> dict:
    """Build a fresh configuration for a strategy supported by this updater group."""
    if name is None:
        name = "AdaptiveShapeUpdate" if group == "geometry" else "FixedUpdate"
    spec = strategy_specs(group)[name]
    return {"type": name, "params": field_defaults(spec.fields)}
