"""Material-interface collection and material-parameter aggregation."""

from __future__ import annotations

from typing import Any

import pyvista as pv
import torch
import torchfea

from .baseparam import BaseParams

__all__ = [
    "MaterialsParams",
]


class MaterialsParams(BaseParams):
    """Ordered collection of named material interfaces."""

    from .materialinterface import BaseMaterialInterface, HomogeneousMaterial
    from .materialinterface.materialmodels import MaterialModels as materialmodels

    def __init__(self) -> None:
        super().__init__()
        self.materialinterfaces: dict[str, MaterialsParams.BaseMaterialInterface] = {}
        self.define_interface()

    def define_interface(self) -> None:
        """Define the material interfaces for a user model."""

    def add_material_interface(
        self,
        interface: MaterialsParams.BaseMaterialInterface,
        name: str | None = None,
    ) -> str:
        """Add one named material interface and return its final name."""
        if not isinstance(interface, self.BaseMaterialInterface):
            raise TypeError("interface must be a BaseMaterialInterface.")
        if name is None:
            prefix = type(interface).__name__
            index = 0
            name = f"{prefix}_{index}"
            while name in self.materialinterfaces:
                index += 1
                name = f"{prefix}_{index}"
        if name in self.materialinterfaces:
            raise ValueError(f"Material interface {name!r} already exists.")
        self.materialinterfaces[name] = interface
        interface._name = name
        return name

    @property
    def num_material_interfaces(self) -> int:
        return len(self.materialinterfaces)

    def interfaces(self) -> list[MaterialsParams.BaseMaterialInterface]:
        return list(self.materialinterfaces.values())

    def design_interfaces(self) -> list[MaterialsParams.BaseMaterialInterface]:
        return [
            interface
            for interface in self.interfaces()
            if interface.get_variables().numel()
        ]

    def set_materials(self, fe: torchfea.FEAController) -> None:
        for interface in self.interfaces():
            interface.set_materials(fe)

    def initialize(self, *args: Any, **kwargs: Any) -> None:
        for interface in self.interfaces():
            interface.initialize(*args, **kwargs)

    def reinitialize(self, iteration: int, *args: Any, **kwargs: Any) -> None:
        for interface in self.interfaces():
            interface.reinitialize(iteration, *args, **kwargs)

    def get_parameters(self) -> list[torch.Tensor]:
        values: list[torch.Tensor] = []
        for interface in self.interfaces():
            values.extend(interface.get_parameters())
        return values

    def set_parameters(self, values: list[torch.Tensor]) -> None:
        index = 0
        for interface in self.interfaces():
            count = len(interface.get_parameters())
            interface.set_parameters(values[index : index + count])
            index += count
        if index != len(values):
            raise ValueError("Material parameter list does not match interfaces.")

    def get_design_values(self) -> torch.Tensor:
        values = [
            interface.get_design_values() for interface in self.design_interfaces()
        ]
        values = [value.flatten() for value in values if value.numel()]
        return torch.cat(values) if values else torch.zeros(0)

    def get_variables(self) -> torch.Tensor:
        values = [
            interface.get_variables().flatten()
            for interface in self.design_interfaces()
        ]
        return torch.cat(values) if values else torch.zeros(0)

    def update_variables(
        self,
        x_change: torch.Tensor,
        max_step_length: torch.Tensor | None = None,
    ) -> None:
        sizes = [interface.get_variables().numel() for interface in self.interfaces()]
        x_change = x_change.flatten()
        if x_change.numel() != sum(sizes):
            raise ValueError("Material update size does not match interfaces.")
        offset = 0
        for interface, size in zip(self.interfaces(), sizes):
            if not size:
                continue
            step = (
                None
                if max_step_length is None
                else max_step_length[offset : offset + size]
            )
            interface.update_variables(
                x_change[offset : offset + size],
                max_step_length=step,
            )
            offset += size

    def obtain_design_sensitivity_vars(
        self,
        assembly: torchfea.Assembly,
    ) -> torch.Tensor:
        values = [
            interface.obtain_design_sensitivity_vars(assembly).flatten()
            for interface in self.interfaces()
        ]
        values = [value for value in values if value.numel()]
        return torch.cat(values) if values else torch.zeros(0)

    def modify_assembly(
        self,
        design_sensitivity_vars: torch.Tensor,
        assembly: torchfea.Assembly,
    ) -> None:
        values = design_sensitivity_vars.flatten()
        offset = 0
        for interface in self.interfaces():
            size = interface.obtain_design_sensitivity_vars(assembly).numel()
            if size:
                interface.modify_assembly(values[offset : offset + size], assembly)
                offset += size
        if offset != values.numel():
            raise ValueError("Material sensitivity size does not match interfaces.")

    def pathlog_required(self) -> list[str]:
        return ["materials"]

    def save(self, foldpath: str, iteration: int) -> None:
        for interface in self.interfaces():
            interface.save(foldpath=foldpath, iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        for interface in self.interfaces():
            interface.load(foldpath=foldpath, iteration=iteration)

    def get_meshes(self) -> list[pv.DataSet]:
        meshes: list[pv.DataSet] = []
        for interface in self.interfaces():
            meshes.extend(interface.get_meshes())
        return meshes

    def plot(
        self,
        plotter: pv.Plotter | None = None,
        meshes: list[pv.DataSet] | pv.DataSet | None = None,
    ) -> pv.Plotter:
        if plotter is None:
            plotter = pv.Plotter()
        for interface in self.interfaces():
            plotter = interface.plot(plotter=plotter, meshes=meshes)
        return plotter
