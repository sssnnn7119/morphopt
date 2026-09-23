import pyvista as pv
import torch
import torchfea

from ..protocal import (
    ProtocalInitializable,
    ProtocalSavable,
    ProtocalUpdatable,
    ProtocalVisualizable,
)


class BaseParams(
    ProtocalInitializable,
    ProtocalSavable,
    ProtocalVisualizable,
):
    """
    Base class for all parameter classes including geometry, feamodel, and materials.
    """

    def __init__(self, **kwargs):
        """
        Initialize the parameters with the given keyword arguments.
        """
        super().__init__()
        self.interfaces: dict[str, object] = {}
        """Interfaces owned by this parameter collection."""

    def add_interface(self, interface: object, name: str | None = None) -> str:
        """Register one named interface and return its final name."""
        if name is None:
            prefix = type(interface).__name__
            index = 0
            name = f"{prefix}_{index}"
            while name in self.interfaces:
                index += 1
                name = f"{prefix}_{index}"

        name = str(name).strip()
        if not name:
            raise ValueError("Interface name cannot be empty.")
        if name in self.interfaces:
            raise ValueError(f"Interface {name!r} already exists.")

        interface._name = name
        self.interfaces[name] = interface
        return name

    @property
    def num_interfaces(self) -> int:
        """Number of registered interfaces."""
        return len(self.interfaces)

    def __repr__(self):
        """
        Return a string representation of the parameters.
        """
        return f"{self.__class__.__name__}({self.__dict__})"

    def __str__(self):
        """
        Return a string representation of the parameters.
        """
        return self.__repr__()

    def define_interface(self) -> None:
        """Declare the interfaces owned by this parameter collection."""

    def initialize(self, *args, **kwargs) -> None:
        """Initialize every registered interface."""
        if not self.interfaces:
            self.define_interface()
        for interface in self.interfaces.values():
            interface.initialize(*args, **kwargs)

    def reinitialize(self, iteration: int, *args, **kwargs) -> None:
        """Re-initialize every registered interface."""
        for interface in self.interfaces.values():
            interface.reinitialize(iteration, *args, **kwargs)

    def plot(
        self, plotter: pv.Plotter = None, meshes: list[pv.DataSet] = None
    ) -> pv.Plotter:
        """
        Plot the parameters.

        This method should be implemented in subclasses to plot specific parameters.

        Args:
            plotter (pv.Plotter, optional): An optional PyVista Plotter object to use for plotting. If None, a new Plotter will be created. Defaults to None.
            meshes (list[pv.DataSet], optional): An optional list of PyVista DataSet objects to plot. Defaults to None.

        Returns:
            pv.Plotter: The PyVista Plotter object used for plotting.
        """
        if plotter is None:
            plotter = pv.Plotter()

        for interface in self.interfaces.values():
            plotter = interface.plot(plotter=plotter, meshes=meshes)

        return plotter

    def get_meshes(self):
        """Return the meshes contributed by every registered interface."""
        meshes: list[pv.DataSet] = []
        for interface in self.interfaces.values():
            meshes.extend(interface.get_meshes())
        return meshes

    def design_interfaces(self) -> list[ProtocalUpdatable]:
        """Return interfaces that carry updateable design variables."""
        return [
            interface
            for interface in self.interfaces.values()
            if isinstance(interface, ProtocalUpdatable)
        ]

    def obtain_design_sensitivity_vars(
        self, assembly: torchfea.Assembly
    ) -> torch.Tensor:
        """Concatenate the design sensitivity variables of every interface."""
        values = [
            interface.obtain_design_sensitivity_vars(assembly).flatten()
            for interface in self.design_interfaces()
        ]
        values = [value for value in values if value.numel()]
        return torch.cat(values) if values else torch.zeros(0)

    def interface(self, name: str) -> object:
        """Return one registered interface by name."""
        try:
            return self.interfaces[str(name)]
        except KeyError:
            raise KeyError(
                f"Interface {name!r} does not exist; available: "
                f"{list(self.interfaces)}."
            ) from None

    def export_data(self, foldpath: str):
        """
        Export the data of parameters to file(s).

        Args:
            foldpath (str): The path to export the data.
        """

    def save(self, foldpath: str, iteration: int) -> None:
        """Save the state of every registered interface."""
        for interface in self.interfaces.values():
            interface.save(foldpath=foldpath, iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        """Load the state of every registered interface."""
        for interface in self.interfaces.values():
            interface.load(foldpath=foldpath, iteration=iteration)

    def modify_assembly(
        self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly
    ) -> None:
        """Dispatch design sensitivity variables to every updateable interface."""
        values = torch.as_tensor(design_sensitivity_vars).flatten()
        offset = 0
        for interface in self.design_interfaces():
            size = interface.num_variables
            interface.modify_assembly(values[offset : offset + size], assembly)
            offset += size
        if offset != values.numel():
            raise ValueError("Design sensitivity size does not match interfaces.")
