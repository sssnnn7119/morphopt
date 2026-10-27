"""Display labels and Qt combo value access for form controls."""

from __future__ import annotations

from ..i18n import tr

#: labels for degree-of-freedom check boxes (dof index -> short name)
DOF_LABELS = {0: "X", 1: "Y", 2: "Z", 3: "Rx", 4: "Ry", 5: "Rz"}
DOF_COUNT = 6

_CHOICE_LABELS = {
    ("obj_type", "auto"): "ui.widgets.values.choice.auto",
    ("obj_type", "node"): "ui.widgets.values.choice.node",
    ("obj_type", "element"): "ui.widgets.values.choice.element",
    ("obj_type", "part"): "ui.widgets.values.choice.part",
    ("elementname", ""): "ui.widgets.values.choice.all",
    ("inp_part_name", ""): "ui.widgets.values.choice.only_inp_part",
    ("exterior_surface", ""): "ui.widgets.values.choice.default_exterior",
}


def display_choice(key: str, value) -> str:
    """Return a localized label while retaining the backend choice value."""
    labels = _CHOICE_LABELS.get((key, str(value)))
    return tr(labels) if labels else str(value)


def combo_value(combo) -> object:
    """Read a combo's backend value, or custom text when it was edited."""
    index = combo.currentIndex()
    if index >= 0 and combo.currentText() == combo.itemText(index):
        return combo.itemData(index)
    return combo.currentText()
