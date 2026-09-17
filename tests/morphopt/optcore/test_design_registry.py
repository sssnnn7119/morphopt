"""test design registry tests."""

from morphopt._torch import torch
from morphopt.optcore.design_registry import DesignKey, DesignRegistry


class Owner:
    def __init__(self):
        self.parameters = torch.as_tensor([1.0, 2.0])
        self.delta = torch.zeros_like(self.parameters)

    def get_parameters(self): return self.parameters
    def set_parameters(self, values): self.parameters = torch.as_tensor(values).clone()
    def build_design_delta(self): self.delta = torch.zeros_like(self.parameters)
    def get_design_delta(self): return self.delta
    def set_design_delta(self, values): self.delta = values
    def update_assembly(self, values): self.delta = values
    def apply_design_delta(self, values): self.parameters = self.parameters + values


def test_registry_layout_and_commit():
    owner = Owner()
    registry = DesignRegistry()
    registry.add_block(DesignKey("geometry", "body"), owner)
    registry.finalize()
    registry.build_design_delta()
    assert registry.get_block_range(DesignKey("geometry", "body")) == (0, 2)
    registry.apply_design_delta({DesignKey("geometry", "body"): torch.as_tensor([0.5, -0.5])})
    assert float(owner.parameters[0]) == 1.5
