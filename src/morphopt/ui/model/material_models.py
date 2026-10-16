"""Material parameter signatures read from the kernel models."""
from dataclasses import fields
from ...optcore.modelparams.materials import MaterialModels

MATERIAL_MODEL_CHOICES: tuple[str, ...] = tuple(
    name.removesuffix("Params")
    for name in vars(MaterialModels)
    if name.endswith("Params")
)

MATERIAL_MODEL_PARAMETERS: dict[str, tuple[str, ...]] = {
    name.removesuffix("Params"): tuple(field.name for field in fields(parameter_class))
    for name, parameter_class in vars(MaterialModels).items()
    if name.endswith("Params")
}
