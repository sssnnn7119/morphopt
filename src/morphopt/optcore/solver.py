import copy
import multiprocessing as mp

import numpy as np
import torch
import torchfea

import morphopt

from ..constants import CONSTANT
from .modelparams import FEAParams, Params
from .protocal import ProtocalInitializable, ProtocalSavable


class Solver(ProtocalInitializable, ProtocalSavable):
    """
    This class is responsible for solving the FEA and get the displacement of the soft robot.
    """

    def __init__(
        self,
        params: Params,
        num_process: int = CONSTANT.KERNEL.SOLVER.NUM_PROCESS,
        available_gpus: list[str] | None = None,
        task_step_list: list[list[str]] | None = None,
    ) -> None:
        """
        Initialize the Solver class with a list of pressure values.

        Parameters:
            params (Params):
            num_process (int): The number of processes to use for parallel computation.
                Defaults to one process.
            available_gpus (list[str] | None): GPU devices to use. Defaults to
                CPU execution when omitted or empty.
        """

        super().__init__()

        self.params: Params = params
        """
        Pressures: An instance of the params of the optimization problem.
        """

        self.num_process = num_process
        """
        int: The number of processes to use for parallel computation.
        """

        self.available_gpus = list(available_gpus or [])

        self.task_step_list = task_step_list
        """
        list[list[str]]: Named load cases grouped for sequential execution.
        """

    def initialize(self) -> None:
        names = list(self.params.feamodel.fea_steps_params)
        if not names:
            raise ValueError("At least one named load case is required.")
        groups = self.task_step_list or []
        registered = [name for group in groups for name in group]
        if len(set(registered)) != len(registered) or not set(registered) <= set(names):
            raise ValueError("Solver task groups must reference existing load cases without duplicates.")
        self.task_step_list = [*groups, *[[name] for name in names if name not in registered]]

    def reinitialize(self, iteration: int) -> None:
        """
        Reinitialize the solver for a new iteration.

        Parameters:
            iteration (int): The current iteration number.
        """

    def solve(self, U_guess: dict[str, np.ndarray | None] | None = None) -> dict[str, torchfea.solver.StaticResult]:
        """
        Solve the optimization problem using the specified solver.

        Returns:
            The result of the optimization problem.
        """

        if U_guess is None:
            U_guess = self._previous_solution()

        # multiprocess FEA

        fe_cpu = copy.deepcopy(morphopt.controller.objfun.fe)
        fe_cpu.change_device(torch.device("cpu"))

        if morphopt.controller._debug_mode:
            self._solve_FEA(
                fe=fe_cpu,
                feamodel=self.params.feamodel,
                step_names=self.task_step_list[0],
                available_gpus=self.available_gpus,
                U_guess=[U_guess[step] for step in self.task_step_list[0]]
                if U_guess is not None else None,
                path_result=morphopt.controller.path_result,
            )

        pools = morphopt.controller.pools
        # pools.close()
        # pools.join()
        # pools = mp.Pool(processes=self.num_process)
        # morphopt.controller.pools = pools
        result = []
        for i in range(len(self.task_step_list)):
            result.append(
                pools.apply_async(
                    self._solve_FEA,
                    kwds={
                        "fe": fe_cpu,
                        "feamodel": self.params.feamodel,
                        "step_names": self.task_step_list[i],
                        "available_gpus": self.available_gpus,
                        "U_guess": [U_guess[step] for step in self.task_step_list[i]]
                        if U_guess is not None
                        else None,
                        "path_result": morphopt.controller.path_result,
                    },
                )
            )

        # get the result
        indexed_results = []
        for i in range(len(result)):
            indexed_results.extend(zip(self.task_step_list[i], result[i].get()))
        indexed_results = dict(indexed_results)

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

        ``history.iteration`` counts completed iterations and names the most
        recently saved result. Missing load-step files have no initial guess.
        """
        if any(part.is_variable for part in self.params.geometry.interfaces.values()):
            return None
        if morphopt.controller.history.iteration <= 0:
            return None

        iteration = morphopt.controller.history.iteration
        guesses = {}
        for taskidx, step_name in enumerate(self.params.feamodel.fea_steps_params):
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
        available_gpus: list[str],
        U_guess: list[np.ndarray | None] | None = None,
        path_result: str | None = None,
    ) -> list[torchfea.solver.StaticResult]:
        import os

        os.environ["KMP_DUPLICATE_LIB_OK"] = "True"
        import sys

        import torch

        sys.path.append(os.getcwd())

        import torchfea

        torchfea.enable_logging(
            log_file=os.path.join(path_result, "log", "torchfea.log")
        )

        current_process_name = mp.current_process().name
        try:
            pool_id = int(current_process_name[-1])
        except:
            pool_id = 0

        if len(available_gpus) > 0:
            cuda_now = (pool_id + 1) % len(available_gpus)
            torch.set_default_device(available_gpus[cuda_now])
            device_now = available_gpus[cuda_now]
            print(
                "Process %s use GPU: %s"
                % (current_process_name, available_gpus[cuda_now])
            )
        else:
            torch.set_default_device("cpu")
            device_now = "cpu"
            print("Process %s use CPU" % (current_process_name))

        # torch.set_default_device(torch.device('cuda:0'))
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
