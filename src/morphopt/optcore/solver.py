import copy
import multiprocessing as mp

import numpy as np
import torch
import torchfea

import morphopt

from ..constants import CONSTANT
from .modelparams import FEAParams, Params
from .protocal import ProtocalHistory, ProtocalInitializable, ProtocalSavable


class Solver(ProtocalInitializable, ProtocalSavable, ProtocalHistory):
    """Solve ordered groups of named load cases on explicitly assigned worker devices.

    Groups are independent tasks; cases within one group run sequentially and can warm-start
    from the preceding result. Results are returned in load-case registration order. Debug mode
    executes every group once in the calling process and restores the caller's default tensor
    device and dtype.
    """

    def __init__(
        self,
        params: Params,
        num_process: int = CONSTANT.KERNEL.SOLVER.NUM_PROCESS,
        process_devices: list[str] | None = None,
        task_step_list: list[list[str]] | None = None,
    ) -> None:
        """Configure worker devices and ordered groups of named load cases.

        Args:
            params (Params): Model parameters containing geometry, finite-element declarations, and
                materials.
            num_process (int): The number of processes to use for parallel computation. Defaults to
                one process.
            process_devices (list[str] | None): One device name for each process. Defaults to CPU
                for every process.
            task_step_list (list[list[str]] | None): Ordered groups of named load cases; cases
                within a group use sequential warm starts.
        """

        super().__init__()

        self.params: Params = params

        self.num_process = num_process
        """
        int: The number of processes to use for parallel computation.
        """

        self.process_devices = list(process_devices or [])
        if len(self.process_devices) > num_process:
            raise ValueError(
                "process_devices cannot contain more entries than num_process"
            )
        self.process_devices.extend(["cpu"] * (num_process - len(self.process_devices)))

        self.task_step_list = task_step_list
        """
        list[list[str]]: Ordered task groups; load cases run sequentially per group.
        """

    def initialize(self) -> None:
        """Initialize the Solver state."""
        names = list(self.params.feamodel.fea_steps_params)
        if not names:
            raise ValueError("At least one named load case is required.")
        groups = self.task_step_list or []
        registered = [name for group in groups for name in group]
        if len(set(registered)) != len(registered) or not set(registered) <= set(names):
            raise ValueError("Solver task groups must reference existing load cases without duplicates.")
        # Each nested list is one pool task; unassigned cases default to
        # separate singleton tasks in load-case registration order.
        self.task_step_list = [*groups, *[[name] for name in names if name not in registered]]

    def reinitialize(self, iteration: int) -> None:
        """Reinitialize the solver for a new iteration.

        Args:
            iteration (int): The current iteration number.
        """

    def solve(self, U_guess: dict[str, np.ndarray | None] | None = None) -> dict[str, torchfea.solver.StaticResult]:
        """Solve every configured load-case group and restore registration-order results.

        When no explicit guesses are supplied, try previous-iteration solutions only for fixed
        geometry. Each worker group solves its cases sequentially; an absent case guess uses the
        preceding case's solution within that group.

        Args:
            U_guess (dict[str, np.ndarray | None] | None): Optional mapping from every requested
                load-case name to generalized coordinates or None. None enables automatic
                previous-iteration guesses.

        Returns:
            dict[str, torchfea.solver.StaticResult]: Converged results keyed in load-case
                registration order, moved to the caller's default device.

        Raises:
            ValueError: A finite-element load case fails to converge.
        """

        if U_guess is None:
            U_guess = self._previous_solution()

        pool = morphopt.controller.pools
        debug_mode = morphopt.controller._debug_mode
        process_devices = (
            {mp.current_process().name: self.process_devices[0]}
            if debug_mode else {
                worker.name: self.process_devices[index]
                for index, worker in enumerate(pool._pool)
            }
        )

        fe_cpu = copy.deepcopy(morphopt.controller.objfun.fe)
        fe_cpu.change_device(torch.device("cpu"))

        tasks = [
            {
                "fe": fe_cpu,
                "feamodel": self.params.feamodel,
                "step_names": group,
                "process_devices": process_devices,
                "U_guess": [U_guess[step] for step in group] if U_guess is not None else None,
                "path_result": morphopt.controller.path_result,
            }
            for group in self.task_step_list
        ]
        if debug_mode:
            # Keep every case in the debugger process and solve it only once.
            device, dtype = torch.get_default_device(), torch.get_default_dtype()
            try:
                grouped_results = [
                    self._solve_FEA(**{**task, "fe": copy.deepcopy(fe_cpu)})
                    for task in tasks
                ]
            finally:
                torch.set_default_device(device)
                torch.set_default_dtype(dtype)
        else:
            pending = [pool.apply_async(self._solve_FEA, kwds=task) for task in tasks]
            grouped_results = [result.get() for result in pending]
        indexed_results = {
            name: result
            for group, results in zip(self.task_step_list, grouped_results)
            for name, result in zip(group, results)
        }

        output: dict[str, torchfea.solver.StaticResult] = {}
        for step_name in self.params.feamodel.fea_steps_params:
            step_result = indexed_results[step_name]
            morphopt.controller.objfun.fe._change_device_recursive(
                step_result, torch.get_default_device()
            )
            if not step_result.converged:
                raise ValueError(
                    f"FEA did not converge for load case {step_name!r}"
                )
            output[step_name] = step_result

        del fe_cpu
        return output

    def _previous_solution(self) -> dict[str, np.ndarray | None] | None:
        """Load previous-iteration coordinates only for fixed-geometry models.

        ``history.iteration`` counts completed iterations and names the most recently saved result.
        Missing load-step files have no initial guess.

        Returns:
            dict[str, np.ndarray | None] | None: Saved generalized coordinates by case, or None for
                variable geometry, the first iteration, or an archive without usable results.
        """
        if any(part.is_variable for part in self.params.geometry.interfaces.values()):
            return None
        if morphopt.controller.history.iteration <= 0:
            return None

        iteration = morphopt.controller.history.iteration
        guesses = {}
        for step_name in self.params.feamodel.fea_steps_params:
            path = (
                morphopt.controller.path_result
                + f"/log/femodel&results/result_{step_name}_iter_{iteration}.npz"
            )
            try:
                result = torchfea.solver.StaticResult.load(path)
            except FileNotFoundError:
                guesses[step_name] = None
            else:
                guesses[step_name] = result.GC.detach().cpu().numpy()
        return guesses if any(guess is not None for guess in guesses.values()) else None

    @classmethod
    def _solve_FEA(
        cls,
        fe: torchfea.FEAController,
        feamodel: FEAParams,
        step_names: list[str],
        process_devices: dict[str, str],
        U_guess: list[np.ndarray | None] | None = None,
        path_result: str | None = None,
    ) -> list[torchfea.solver.StaticResult]:
        """Solve one ordered load-case group on its assigned worker device.

        Args:
            fe (torchfea.FEAController): TorchFEA controller whose assembly is modified or solved.
            feamodel (FEAParams): Finite-element declarations and named load-case parameters.
            step_names (list[str]): Load-case names in the order solved within this worker task.
            process_devices (dict[str, str]): Worker process names mapped to their assigned PyTorch
                device strings. This worker's process name must be present.
            U_guess (list[np.ndarray | None] | None): Optional per-case initial generalized
                coordinate arrays in step_names order; a None entry uses the preceding solved state
                or the assembly initial state.
            path_result (str | None): Existing optimization result directory containing the log
                subdirectory used for solver output.

        Returns:
            list[torchfea.solver.StaticResult]: Solutions in step_names order; each converged state
                initializes the next case unless an explicit guess is supplied.
        """
        import os

        os.environ["KMP_DUPLICATE_LIB_OK"] = "True"
        torchfea.enable_logging(
            log_file=os.path.join(path_result, "log", "torchfea.log")
        )

        current_process_name = mp.current_process().name
        device_now = process_devices[current_process_name]
        torch.set_default_device(device_now)
        print(f"Process {current_process_name} uses device: {device_now}")

        torch.set_default_dtype(torch.float64)
        torch.cuda.empty_cache()
        # construct the FEA
        fe.change_device(device_now)

        # Task-local guesses follow step_names, not global load-step order.
        U0 = fe.assembly._GC.to(torch.get_default_device())

        result_list = []
        for i in range(len(step_names)):
            if U_guess is not None and U_guess[i] is not None:
                U0 = torch.from_numpy(U_guess[i]).to(
                    dtype=torch.float64, device=torch.get_default_device()
                )
            feamodel.process_fea(fe=fe, step_name=step_names[i])
            result: torchfea.solver.StaticResult = fe.solve(
                GC0=U0.to(torch.get_default_device()), if_initialize=False
            )

            result_list.append(result)
            fe._change_device_recursive(result, torch.device("cpu"))
            U0 = result.GC.detach().clone()

        del fe
        torch.cuda.empty_cache()
        return result_list
