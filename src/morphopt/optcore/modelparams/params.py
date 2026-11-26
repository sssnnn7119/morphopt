import math
import tempfile
from pathlib import Path

import pyvista as pv
import torch
from torchfea import Assembly

from ...constants import CONSTANT
from ..protocal import (
    ProtocalHistory,
    ProtocalInitializable,
    ProtocalSavable,
    ProtocalVisualizable,
)
from .feaparams import FEAParams
from .geometry import GeometryParams
from .materialsparams import MaterialsParams


class Params(
    ProtocalInitializable, ProtocalSavable, ProtocalVisualizable, ProtocalHistory
):
    """Compose geometry, finite-element declarations, and material assignments.

    This object constructs the FE assembly, exposes collection-specific design variables to
    adjoint analysis, and delegates saving, restoration, and visualization to its components.
    """

    def __init__(
        self, geometry: GeometryParams, feamodel: FEAParams, materials: MaterialsParams
    ) -> None:
        """Initialize the Params class.

        Args:
            geometry (GeometryParams): Geometry description or geometry collection processed by this
                interface.
            feamodel (FEAParams): Finite-element declarations and named load-case parameters.
            materials (MaterialsParams): Material-interface collection associated with the model.
        """
        self.geometry = geometry
        """
        GeometryParams: The geometry collection (Parts + Instances).
        """
        self.feamodel = feamodel
        """
        Loads: An instance of the Loads class from the ModelParams module.
        """
        self.materials = materials
        """
        Materials: An instance of the Materials class from the ModelParams module.
        """
        self._mesh_statistics: dict[str, int] = {"num_elements": 0, "num_nodes": 0}

    def history_data(self) -> dict[str, object]:
        """Report the mesh generated for the current finite element evaluation.

        Returns:
            dict[str, object]: Component-owned scalar or nested observations for the current
                iteration.
        """
        return dict(self._mesh_statistics)

    def pathlog_required(self) -> list[str]:
        """Declare this object's save directory before its child directories.

        Returns:
            list[str]: Relative log subdirectory names required before persistence.
        """
        return [
            "params",
            *self.geometry.pathlog_required(),
            *self.feamodel.pathlog_required(),
            *self.materials.pathlog_required(),
        ]

    def reinitialize(self, iteration: int) -> None:
        """reInitialize the parameters.

        Args:
            iteration (int): Iteration index associated with the saved or current model state.
        """
        self.geometry.reinitialize(iteration=iteration)
        self.feamodel.reinitialize(iteration=iteration)
        self.materials.reinitialize(iteration=iteration)

    def initialize(self):
        """
        Initialize the parameters.
        """
        self.geometry.initialize()
        self.feamodel.initialize()
        self.materials.initialize()

    def create_feamodel(self, path_result: str | None = None, pools=None):
        """Create the finite element model for sensitivity analysis.

        Args:
            path_result (str | None): The path to the result folder. If None, a temporary directory
                will be used. Defaults to None.
            pools: A list of multiprocessing pools for parallel processing. Defaults to None.

        Returns:
            feamodel: The created finite element model.
        """

        if path_result is None:
            with tempfile.TemporaryDirectory(prefix="morphopt_") as tempdir:
                assembly = self.geometry.generate(path_result=tempdir, pools=pools)
        else:
            assembly = self.geometry.generate(path_result=path_result, pools=pools)

        fe = self.feamodel.create_fea(assembly=assembly)
        self.materials.set_materials(fe)
        fe.initialize()

        # Count the initialized Assembly, including every Part, Instance and
        # element family. Retain only scalars, not another reference to FEA.
        instances = list(fe.assembly._instances.values())
        self._mesh_statistics = {
            "num_elements": sum(
                element._elems.shape[0]
                for instance in instances
                for element in instance.elems.values()
            ),
            "num_nodes": sum(instance.nodes.shape[0] for instance in instances),
        }

        return fe

    def obtain_design_sensitivity_vars(self, assembly: Assembly):
        """Obtain the design sensitivity variables for the optimization problem.

        Args:
            assembly (Assembly): The assembly to obtain design sensitivity variables for.

        Returns:
            dict[str, torch.Tensor]: A dictionary of design sensitivity variables for each parameter
                class.
        """
        # Obtain design sensitivity variables from each parameter class
        design_sensitivity_vars = {
            "geometry": self.geometry.obtain_design_sensitivity_vars(assembly),
            "feamodel": self.feamodel.obtain_design_sensitivity_vars(assembly),
            "materials": self.materials.obtain_design_sensitivity_vars(assembly),
        }

        return design_sensitivity_vars

    def modify_assembly(
        self, design_sensitivity_vars: dict[str, torch.Tensor], assembly: Assembly
    ) -> None:
        """
        Modify the assembly for sensitivity analysis.

        Args:
            design_sensitivity_vars (dict[str, torch.Tensor]): The design sensitivity variables.
            assembly (Assembly): The assembly to modify.
        """
        self.geometry.modify_assembly(design_sensitivity_vars["geometry"], assembly)
        self.feamodel.modify_assembly(design_sensitivity_vars["feamodel"], assembly)
        self.materials.modify_assembly(design_sensitivity_vars["materials"], assembly)

    def save(self, foldpath: str, iteration: int) -> None:
        """Save the parameters to a file.

        Args:
            foldpath (str): The path to save the parameters.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        directory = Path(self.save_directory(foldpath))
        self.geometry.save(foldpath=foldpath, iteration=iteration)
        self.feamodel.save(foldpath=foldpath, iteration=iteration)
        self.materials.save(foldpath=foldpath, iteration=iteration)

        plotter = pv.Plotter(
            off_screen=True,
            window_size=list(CONSTANT.KERNEL.VISUALIZATION.WINDOW_SIZE),
        )
        try:
            plotter.set_background("white")
            self.plot(plotter=plotter)
            plotter.enable_parallel_projection()
            azimuth = CONSTANT.KERNEL.VISUALIZATION.CAMERA_AZIMUTH_DEGREES
            elevation = CONSTANT.KERNEL.VISUALIZATION.CAMERA_ELEVATION_DEGREES
            plotter.view_vector(
                (
                    math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                    math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                    math.sin(math.radians(elevation)),
                )
            )
            plotter.screenshot(str(directory / f"{iteration}.jpg"))
        finally:
            plotter.close()

    def load(self, foldpath: str, iteration: int) -> None:
        """Load the parameters from a file.

        Args:
            foldpath (str): The path to load the parameters from.
            iteration (int): Iteration index associated with the saved or current model state.
        """
        self.geometry.load(foldpath=foldpath, iteration=iteration)
        self.feamodel.load(foldpath=foldpath, iteration=iteration)
        self.materials.load(foldpath=foldpath, iteration=iteration)

    def plot(
        self, plotter: pv.Plotter | None = None, meshes: list[pv.DataSet] | None = None
    ) -> pv.Plotter:
        """Plot the geometry and other relevant information using PyVista.

        Args:
            plotter (pv.Plotter | None): An optional PyVista Plotter object to use for plotting. If
                None, a new Plotter will be created. Defaults to None.
            meshes (list[pv.DataSet] | None): Optional precomputed visualization meshes; None
                obtains meshes from the model.

        Returns:
            pv.Plotter: The PyVista Plotter object used for plotting.
        """

        if plotter is None:
            plotter = pv.Plotter()

        self.geometry.plot(plotter=plotter, meshes=meshes)
        self.materials.plot(plotter=plotter, meshes=meshes)
        self.feamodel.plot(plotter=plotter, meshes=meshes)

        return plotter

    def get_meshes(self):
        """Get the meshes associated with the geometry.

        Returns:
            list[pv.DataSet]: Visualization meshes contributed by the geometry, load, and material
                collections.
        """
        return (
            self.geometry.get_meshes()
            + self.feamodel.get_meshes()
            + self.materials.get_meshes()
        )
