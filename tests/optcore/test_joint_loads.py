"""Joint definitions and named load cases reach the TorchFEA assembly."""

import pytest
import torch
import torchfea

from morphopt import FEAParams


@pytest.mark.parametrize("kind, direction, translation_energy", [
    ("SphericalJoint", [], 2.0),
    ("SingleDoFJoint", [1, 0, 0, 0, 0, 0], 0.0),
])
def test_joint_case_switch(kind, direction, translation_energy):
    params = FEAParams()
    for name, position in (("base", [0, 0, 0]), ("tip", [1, 0, 0])):
        params.add_interface(params.ReferencePoint(position), name)
    interface = getattr(params, kind)("base", "tip")
    params.add_interface(interface, "connector")
    params.add_step("default")
    params.add_step("working", {"connector": [100, 1, 0, 0, *direction]})
    fe = params.create_fea(torchfea.Assembly())
    fe.assembly.initialize()
    joint = fe.assembly.get_load("connector")
    assert type(joint).__name__ == kind
    params.process_fea(fe, "working")
    assert joint._parameters.tolist() == [100, 1, 0, 0, *direction]
    displacement = [torch.zeros_like(q) for q in fe.assembly._RGC]
    displacement[fe.assembly.get_reference_point("tip")._RGC_index][0] = 0.2
    assert -joint.get_potential_energy(displacement).item() == pytest.approx(translation_energy)
    params.process_fea(fe, "default")
    assert joint._parameters.tolist() == list(interface.default_values)
