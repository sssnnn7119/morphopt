"""Base material assignment definition for the V4 Assembly pipeline."""

from __future__ import annotations

from pathlib import Path

import pyvista
import torchfea

from .models import MaterialModels
from .parameters import MaterialParameters


class BaseMaterialInterface:
    """Bind one constitutive material definition to a Part element family.

    Materials are declared independently of geometry. ``reinitialize()``
    receives an Assembly generated for one optimization iteration, resolves
    its target elements and stores native references for direct assignment.
    """

    def __init__(
        self,
        name: str,
        part_name: str,
        element_name: str,
        material_parameters: MaterialParameters,
        density: float = 1.0,
    ) -> None:
        self._name = str(name)
        """Stable material registration name."""
        self._part_name = str(part_name)
        """Target Part name in the generated Assembly."""
        self._element_name = str(element_name)
        """Target element-family name; an empty name selects all families."""
        self._material_parameters = material_parameters
        """Immutable constitutive-model parameter definition."""
        self._density = float(density)
        """Mass density assigned to every targeted element."""
        self._torchfea_Assembly: torchfea.Assembly | None = None
        """Current iteration Assembly resolved by ``reinitialize()``."""
        self._torchfea_Elements: tuple[torchfea.elements.Element_3D, ...] = ()
        """Native target element families selected from the current Part."""
        self._torchfea_Material: torchfea.materials.Materials_Base | None = None
        """Native constitutive object created by ``build_material()``."""
        self._meshes: tuple[pyvista.DataSet, ...] = ()
        """Cached material-field visualization meshes."""

    @property
    def name(self) -> str:
        """Return the material registration name."""
        return self._name

    @property
    def part_name(self) -> str:
        """Return the target Part name."""
        return self._part_name

    @property
    def element_name(self) -> str:
        """Return the target element-family name."""
        return self._element_name

    @property
    def density(self) -> float:
        """Return the homogeneous mass density."""
        return self._density

    @density.setter
    def density(self, value: float) -> None:
        """Set the homogeneous mass density for the next assignment."""
        self._density = float(value)

    @property
    def material_parameters(self) -> MaterialParameters:
        """Return the immutable constitutive parameter definition."""
        return self._material_parameters

    def initialize(self) -> None:
        """Prepare definition-only material state."""
        return None

    def reinitialize(self, iteration: int, assembly: torchfea.Assembly) -> None:
        """Bind the new Assembly and resolve this material's element family."""
        self._torchfea_Assembly = assembly
        self._torchfea_Elements = self._resolve_target_elements(assembly)
        self._torchfea_Material = None

    def build_material(self) -> None:
        """Create and cache the native constitutive object for this iteration."""
        self._torchfea_Material = MaterialModels.create_material(self._material_parameters)

    def assign_material(self) -> None:
        """Assign the cached material and density to every resolved element family."""
        for elements in self._torchfea_Elements:
            elements.delete_material()
            elements.set_materials(self._torchfea_Material)
            elements.density = self._density

    def build_meshes(self) -> None:
        """Build material preview meshes for the current material field."""
        self._meshes = ()

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Read the already-built material preview meshes."""
        return self._meshes

    def plot(
        self,
        plotter: pyvista.Plotter,
        meshes: tuple[pyvista.DataSet, ...],
    ) -> pyvista.Plotter:
        """Draw supplied material meshes with the shared viewer style."""
        for mesh in meshes:
            plotter.add_mesh(mesh)
        return plotter

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Save material data for the iteration result folder."""
        return None

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Load material data from the iteration result folder."""
        return None

    def _resolve_target_elements(
        self,
        assembly: torchfea.Assembly,
    ) -> tuple[torchfea.elements.Element_3D, ...]:
        """Resolve the declared Part and optional element-family selection."""
        part = assembly.get_part(self._part_name)
        if self._element_name:
            return (part.elems[self._element_name],)
        return tuple(part.elems.values())
