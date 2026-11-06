"""Updater strategy metadata shared by configuration, forms and code generation."""

from dataclasses import dataclass

from ...constants import CONSTANT
from .fields import FieldSpec, field_defaults


@dataclass(frozen=True)
class StrategySpec:
    name: str
    label_key: str
    fields: tuple[FieldSpec, ...] = ()
    groups: tuple[str, ...] = ("geometry", "materials")


_ADAPTIVE = CONSTANT.KERNEL.ADAPTIVE_SHAPE_WEIGHTS
_WEIGHT = CONSTANT.KERNEL.UPDATER_STRATEGIES.DEFAULT_CONSTRAINT_WEIGHT

STRATEGY_CATALOG: dict[str, tuple[StrategySpec, ...]] = {
    "step_length_strategy": (
        StrategySpec("FixedStepLength", "ui.strategies.fixed_step_length"),
    ),
    "constraint_weight_strategy": (
        StrategySpec(
            "ConstantConstraintWeights", "ui.strategies.constant_weights",
            (FieldSpec("value", "ui.strategies.value.label", "float", _WEIGHT,
                       minimum=0, doc_key="ui.strategies.value.help"),),
        ),
        StrategySpec(
            "AdaptiveShapeWeights", "ui.strategies.adaptive_shape_weights",
            (
                FieldSpec(
                    "tightening_steps", "ui.strategies.tightening_steps.label", "int",
                    _ADAPTIVE.TIGHTENING_STEPS, minimum=1,
                    doc_key="ui.strategies.tightening_steps.help",
                ),
                *(
                    FieldSpec(key, f"ui.strategies.{key}.label", "float", default,
                              doc_key=f"ui.strategies.{key}.help")
                    for key, default in (
                        ("initial_tolerance", _ADAPTIVE.INITIAL_TOLERANCE),
                        ("final_tolerance", _ADAPTIVE.FINAL_TOLERANCE),
                    )
                ),
            ),
            groups=("geometry",),
        ),
    ),
}


def strategy_specs(key: str, group: str) -> dict[str, StrategySpec]:
    return {spec.name: spec for spec in STRATEGY_CATALOG[key] if group in spec.groups}


def strategy_config(key: str, name: str | None = None) -> dict:
    """Create an independent parameter dictionary for the selected strategy."""
    spec = next(spec for spec in STRATEGY_CATALOG[key] if name is None or spec.name == name)
    return {"type": spec.name, "params": field_defaults(spec.fields)}
