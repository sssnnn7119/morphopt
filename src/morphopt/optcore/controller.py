from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyvista import MultiBlock

    from .. import ObjectiveFunction, Params, Solver, Updaters
import datetime
import gc
import importlib
import logging
import multiprocessing as mp
import os
import shutil
import time
from multiprocessing import get_context
from pathlib import Path

import torch

import morphopt

from ..constants import CONSTANT
from ..utils.paths import sanitize_name, write_result_launcher
from .history import History

logger = logging.getLogger(__name__)


class Controller:
    """Coordinate model construction, finite-element solution, adjoint sensitivity, and design
    updates.

    Subclass the nested Params, Solver, Updater, and ObjectiveFunction declarations to define a
    task. The controller owns the outer iteration, result directory, persistence, and history
    collection; numerical responsibilities remain in the composed components.
    """

    class Params:
        """Declare the model-parameter implementation used by the task controller."""

    class Solver:
        """Declare the finite-element solver implementation used by the task controller."""

    class Updater:
        """Declare the updater collection used by the task controller."""

    class ObjectiveFunction:
        """Declare the physical objective and named metrics used by the task controller."""

    def __init__(
        self, path_result_folder: str, opt_label: str = "DefaultLabel"
    ) -> None:
        """Initialize the Controller class.

        This class is responsible for managing the optimization process. It initializes the
        workflow, generates the model, performs finite element analysis (FEA), and updates the
        surfaces.

        Args:
            path_result_folder (str): Parent directory in which timestamped result directories are
                created.
            opt_label (str): Run label used as the prefix of the timestamped result directory.
        """

        self.params: Params
        """
        Params: An instance of the Params class from the ModelParams module.
        """

        self.solver: Solver
        """
        Solver: An instance of the Solver class from the Solve module.
        """

        self.updater: Updaters
        """
        Updaters: An instance of the Updaters class from the Update module.
        """

        self.objfun: ObjectiveFunction
        """
        ObjFun: An instance of the ObjectiveFunction class from the ObjFunc module.
        """

        self.opt_label: str = opt_label
        """
        The name of the optimization.
        """

        self.path_result_folder: str = path_result_folder
        """
        The foldpath to the result directory.
        """

        self.path_result: str = None
        """
        The path to the result directory.
        """

        self.history = History()
        """
        History: An instance of the History class from the History module to record the optimization history.
        """

        self.restart_per_iteration: int = (
            CONSTANT.KERNEL.CONTROLLER.RESTART_PER_ITERATION
        )
        """
        The frequency of restarting the optimization process.
        """

        self.dataqueue: mp.Queue | None = None

        self.pools = None
        """
        The multiprocessing pool for parallel computation.
        """

        self.optdevice: str = "cpu"
        """
        The device to run the optimization on.
        """

        self._debug_mode: bool = False
        """
        Whether to run in debug mode, which may include additional checks and logging.
        """

    def initialize_path(self, main_filepath: str = None) -> None:
        """Initialize the workflow by importing necessary modules and setting up the environment.

        Args:
            main_filepath (str): Task script archived with the run; None resolves the current main
                module.
        """

        def vendor_package(package_name, target_dir="."):
            """
            copy the specified package to the target directory.

            Args:
                package_name: The name of the package to copy.
                target_dir: The target directory, default is the current directory.
            """
            try:
                # import the package
                module = importlib.import_module(package_name)

                # get the package path
                package_path = os.path.dirname(module.__file__)

                # construct the target path
                target_path = os.path.join(target_dir, package_name)

                # if the target directory exists, remove it first
                if os.path.exists(target_path):
                    if os.path.isfile(target_path):
                        os.remove(target_path)
                    else:
                        shutil.rmtree(target_path)

                # copy the package files
                if os.path.isdir(package_path):
                    shutil.copytree(package_path, target_path)
                    print(
                        f"successfully copied package '{package_name}' to {target_path}"
                    )
                else:
                    shutil.copy2(package_path, target_path)
                    print(
                        f"successfully copied module '{package_name}' to {target_path}"
                    )

                # Check if there are related .pth files or other metadata that need to be handled
                # For pure Python packages, the above steps are usually sufficient

            except ImportError:
                print(
                    f"Error: Package '{package_name}' not found. Please install it first."
                )
            except Exception as e:
                print(f"Error occurred during copying: {e!s}")

        self.path_result = (
            self.path_result_folder
            + "/"
            + sanitize_name(self.opt_label)
            + "_"
            + "T"
            + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            + "/"
        )

        # create the result path if it does not exist
        os.makedirs(self.path_result + "/cache/")
        pathlog_list = []
        pathlog_list += self.params.pathlog_required()
        pathlog_list += self.solver.pathlog_required()
        pathlog_list += self.updater.pathlog_required()
        pathlog_list += self.objfun.pathlog_required()
        for pathlog in pathlog_list:
            os.makedirs(self.path_result + "/log/" + pathlog)

        os.makedirs(self.path_result + "/fea")

        os.makedirs(self.path_result + "/scripts/", exist_ok=True)
        if main_filepath is None:
            import __main__

            main_filepath = __main__.__file__
        scripts_directory = self.path_result + "/scripts/"
        shutil.copy(main_filepath, scripts_directory + "MAIN_SCRIPT_FOR_RESTART.py")
        definition = Path(main_filepath).with_suffix(".morph")
        if definition.is_file():
            shutil.copyfile(definition, Path(scripts_directory) / "MAIN_SCRIPT_FOR_RESTART.morph")
        asset_directory = os.path.join(
            os.path.dirname(os.path.abspath(main_filepath)), "morphopt_assets"
        )
        if os.path.isdir(asset_directory):
            shutil.copytree(
                asset_directory,
                os.path.join(scripts_directory, "morphopt_assets"),
            )

        vendor_package("torchfea", target_dir=self.path_result + "/scripts/")
        vendor_package("cpgeo", target_dir=self.path_result + "/scripts/")
        vendor_package("morphopt", target_dir=self.path_result + "/scripts/")
        write_result_launcher(Path(self.path_result))

    def initialize(self) -> None:
        """
        Initialize the workflow by initializing the Params, Solver, Updaters, and ObjFun classes.
        """
        morphopt.controller = self

        self.params = self.Params()
        self.solver = self.Solver(params=self.params)
        self.updater = self.Updater(params=self.params)
        self.objfun = self.ObjectiveFunction()

        self.params.initialize()
        self.solver.initialize()
        self.updater.initialize()
        self.objfun.initialize()
        self.history.initialize()

        # Use 'spawn' context for the Pool to avoid inheriting CUDA context
        # and Qt/X11 connections from forked subprocesses
        self.pools = get_context("spawn").Pool(processes=self.solver.num_process)

    def start_optimization(self, main_filepath: str = None) -> None:
        """Initialize a new task and run the outer optimization loop.

        Create the result directory and log layout, initialize the composed model and numerical
        components, then record completed iterations until the task terminates.

        Args:
            main_filepath (str): Task script archived with the run; None resolves the current main
                module.
        """
        self.initialize()
        self.initialize_path(main_filepath=main_filepath)
        self.opt_loop()

    def _load_history(self, path_result: str, target_iteration: int = None) -> None:
        """Load history.

        Args:
            path_result (str): Optimization result directory containing scripts and log
                subdirectories.
            target_iteration (int): Completed iteration to restore; None selects the latest saved
                iteration.
        """
        self.path_result = path_result
        self.initialize()
        self.history.load(
            foldpath=self.path_result + "/log/", iteration=target_iteration
        )

        if target_iteration is None:
            target_iteration = self.history.iteration

        self.params.load(
            foldpath=self.path_result + "/log/", iteration=target_iteration
        )
        self.solver.load(
            foldpath=self.path_result + "/log/", iteration=target_iteration
        )
        self.updater.load(
            foldpath=self.path_result + "/log/", iteration=target_iteration
        )

    def restart_optimization(
        self, path_result: str, target_iteration: int = None
    ) -> None:
        """Restore an archived task at a completed checkpoint and continue optimization.

        Args:
            path_result (str): Optimization result directory containing scripts and log
                subdirectories.
            target_iteration (int): Completed iteration to restore; None selects the latest saved
                iteration.
        """
        self._load_history(path_result=path_result, target_iteration=target_iteration)
        self.opt_loop()

    def opt_loop(self) -> None:
        """This function runs the optimization loop for a specified number of iterations. It calls the
        opt_step function in each iteration.
        """
        import torchfea

        torchfea.enable_logging(
            log_file=os.path.join(self.path_result, "log", "torchfea.log"),
            file_log_level=logging.DEBUG,
        )
        morphopt.enable_logging(
            log_file=os.path.join(self.path_result, "log", "morphopt.log"),
            file_log_level=logging.DEBUG,
        )

        while True:
            # Explicitly release large objects to ensure they are collected
            self.clear_cache()

            _, t0, t1, t2, t3, t4, design_snapshot = self.step()

            # Record the history of the optimization process
            self.record_history(t0, t1, t2, t3, t4)

            # Print the information
            self.print_info(t0, t1, t2, t3, t4)

            # Save the current parameters and plot the figures
            self.save(design_snapshot)
            del design_snapshot  # Release the meshes before building the next FE model.

            # if dataqueue is not None, send the data to the queue
            if self.dataqueue is not None:
                self.dataqueue.put(
                    {
                        "iteration": self.history.iteration,
                        "path_result": self.path_result,
                    }
                )

            if (
                self.restart_per_iteration > 0
                and (self.history.iteration + 1) % self.restart_per_iteration == 0
            ):
                self.pools.close()
                self.pools.join()
                return

            if self.history.iteration == 2:
                self.pools.close()
                self.pools.join()
                return

    def step(self) -> tuple[torch.Tensor, float, float, float, float, float, MultiBlock]:
        """Execute one complete outer iteration: build, solve, differentiate, and update.

        Returns:
            The physical objective, timestamps t0 through t4, and the design meshes
            used for this solve, captured before the design update.
        """
        t0 = time.time()

        logger.info(
            "\n"
            + "=" * 50
            + f"\nStarting optimization step {self.history.iteration}...\n"
            + "=" * 50
        )

        # Initialize the workflow
        self.params.reinitialize(iteration=self.history.iteration)
        self.solver.reinitialize(iteration=self.history.iteration)
        self.updater.reinitialize(iteration=self.history.iteration)
        self.objfun.reinitialize(iteration=self.history.iteration)

        if self.history.iteration == 0:
            self.params.geometry.save(
                foldpath=os.path.join(self.path_result, "log"), iteration=0
            )

        # Perform the optimization step
        logger.info(f"Creating FEA model for iteration {self.history.iteration}...")
        self.objfun.fe = self.params.create_feamodel(
            path_result=self.path_result + "/cache/", pools=self.pools
        )

        from ..postprocess.snapshots import capture_design

        with torch.no_grad():
            design_snapshot = capture_design(self.params)
        t1 = time.time()

        # Perform finite element analysis (FEA)
        logger.info(f"Performing FEA for iteration {self.history.iteration}...")
        self.objfun.fe_results = self.solver.solve()

        t2 = time.time()

        # sensitivity analysis
        logger.info(
            f"Performing sensitivity analysis for iteration {self.history.iteration}..."
        )
        gradients = self.objfun.sensitivity_analysis(params=self.params)

        t3 = time.time()

        # Update the surfaces based on the FEA results
        logger.info(f"Updating surfaces for iteration {self.history.iteration}...")
        loss = self.objfun.evaluate()
        self.updater.update(gradients=gradients, objective_value=loss.detach().item())
        self.updater.update_variables()

        t4 = time.time()

        return loss, t0, t1, t2, t3, t4, design_snapshot

    def record_history(
        self, t0: float, t1: float, t2: float, t3: float, t4: float
    ) -> None:
        """Merge component-owned fields with the controller's iteration timing.

        Args:
            t0 (float): Timestamp before model construction for this outer iteration.
            t1 (float): Timestamp after model construction.
            t2 (float): Timestamp after finite-element solution.
            t3 (float): Timestamp after sensitivity analysis.
            t4 (float): Timestamp after the design update.
        """
        self.history.append(
            iteration=self.history.iteration + 1,
            **self.objfun.history_data(),
            time={
                "init": t1 - t0,
                "fea": t2 - t1,
                "sens": t3 - t2,
                "update": t4 - t3,
            },
            **self.params.history_data(),
            **self.solver.history_data(),
            **self.updater.history_data(),
        )

    def print_info(self, t0, t1, t2, t3, t4) -> None:
        """Print the current information of the optimization process.

        Args:
            t0: Timestamp before model construction for this outer iteration.
            t1: Timestamp after model construction.
            t2: Timestamp after finite-element solution.
            t3: Timestamp after sensitivity analysis.
            t4: Timestamp after the design update.
        """
        logger.info(f"Iteration: {self.history.iteration}")
        logger.info(f"Loss: {self.history.records[-1]['objective']:.6f}")
        logger.info("Time Breakdown:")
        logger.info(f"  Initialization Time: {t1 - t0:.2f} seconds")
        logger.info(f"  FEA Time: {t2 - t1:.2f} seconds")
        logger.info(f"  Sensitivity Time: {t3 - t2:.2f} seconds")
        logger.info(f"  Update Time: {t4 - t3:.2f} seconds")
        logger.info(f"  Total Time: {t4 - t0:.2f} seconds")
        logger.info("-" * 50)

    def save(self, design_snapshot: MultiBlock) -> None:
        """Archive the completed solve and its updated design parameters.

        Args:
            design_snapshot: Design meshes captured for the finite-element solve.
        """
        from ..postprocess.snapshots import save_snapshot

        log_folder = self.path_result + "/log/"
        iteration = self.history.iteration
        self.params.save(foldpath=log_folder, iteration=iteration)
        self.solver.save(foldpath=log_folder, iteration=iteration)
        self.updater.save(foldpath=log_folder, iteration=iteration)
        self.objfun.save(foldpath=log_folder, iteration=iteration)
        with torch.no_grad():
            save_snapshot(log_folder, iteration, design_snapshot, self.objfun)
        # Publish a completed iteration only after its model and results exist.
        self.history.save(foldpath=log_folder, iteration=iteration)

    def clear_cache(self) -> None:
        """
        Clear the cache directory.
        """
        self.objfun.fe = None

        torch.cuda.empty_cache()
        data = gc.collect()
        logger.info(f"Garbage collector: collected {data} objects.")

    def change_device(self, device: torch.device, obj: object = None) -> None:
        """Recursively change the device of the finite element model and all nested objects.

        Args:
            device (torch.device): The target device.
            obj (object): The object to change the device for. If None, change the device for the
                Controller instance itself.

        Returns:
            None
        """
        if obj is not None:
            self._change_device_recursive(obj, device)
        else:
            self._change_device_recursive(self, device)

    @staticmethod
    def _instance_attributes(obj: object) -> dict[str, object] | None:
        """Instance attributes of ``obj``, or ``None`` when it carries none.

        The walkers below recurse into containers explicitly and into any other object only through
        its ``__dict__``; ``vars`` is the read-only form of that lookup.

        Args:
            obj (object): Object whose attributes or tensor state are traversed.

        Returns:
            dict[str, object] | None: Instance attributes of ``obj``, or ``None`` when it carries
                none.
        """
        try:
            return vars(obj)
        except TypeError:
            return None

    @classmethod
    def _detach_recursive(cls, obj: object, visited: set = None):
        """Recursively detach tensors to clean up the computation graph. For mutable containers (list,
        dict, objects), replaces tensors with detached versions. This avoids inplace detach_()
        errors on views.

        Args:
            obj (object): Object whose attributes or tensor state are traversed.
            visited (set): Object identities already traversed, used to avoid recursive cycles.
        """
        if visited is None:
            visited = set()

        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)

        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, torch.Tensor):
                    obj[k] = v.detach()
                else:
                    cls._detach_recursive(v, visited)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, torch.Tensor):
                    obj[i] = v.detach()
                else:
                    cls._detach_recursive(v, visited)
        elif isinstance(obj, tuple):
            for v in obj:
                cls._detach_recursive(v, visited)
        else:
            attributes = cls._instance_attributes(obj)
            if attributes is None:
                return
            # Iterate over a copy of items to avoid modification issues
            for k, v in list(attributes.items()):
                if k.startswith("__"):
                    continue
                if isinstance(v, torch.Tensor) and v.requires_grad:
                    setattr(obj, k, v.detach())
                else:
                    cls._detach_recursive(v, visited)

    def _change_device_recursive(self, obj, device, visited=None):
        """Recursively move tensors to the target device.

        Args:
            obj: Object whose attributes or tensor state are traversed.
            device: PyTorch device used for tensor operations; None retains the owning controller's
                device when supported.
            visited: Object identities already traversed, used to avoid recursive cycles.
        """
        if visited is None:
            visited = set()

        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)

        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, torch.Tensor):
                    obj[k] = v.to(device)
                else:
                    self._change_device_recursive(v, device, visited)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, torch.Tensor):
                    obj[i] = v.to(device)
                else:
                    self._change_device_recursive(v, device, visited)
        elif isinstance(obj, tuple):
            for v in obj:
                self._change_device_recursive(v, device, visited)
        else:
            attributes = self._instance_attributes(obj)
            if attributes is None:
                return
            for k, v in list(attributes.items()):
                if isinstance(v, torch.Tensor):
                    setattr(obj, k, v.to(device))
                else:
                    self._change_device_recursive(v, device, visited)

            # TorchFEA keeps reference-space shape data on element classes
            # rather than on each element instance.  Those tensors must move
            # with the runtime object graph as well; otherwise a temporary
            # updater device leaves ``shape_function`` or
            # ``gaussian_coordinates`` behind on the old device.
            for k, v in vars(type(obj)).items():
                if k.startswith("__") or k in attributes:
                    continue
                if isinstance(v, torch.Tensor):
                    setattr(type(obj), k, v.to(device))
                elif isinstance(v, (dict, list, tuple)):
                    self._change_device_recursive(v, device, visited)
