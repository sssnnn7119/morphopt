"""Run / debug optimization workers.

Runs started from *code* never open a UI: the PySide6 observer lives inside the
MorphOpt UI and simply polls the result folder on disk (per finished
iteration).  The old ``no_gui`` flag and separate observer process were
therefore removed; browse results from the observer page in the main UI.
"""


def start_optimization(device='cpu', restart_per_iteration: int = 20,
                       path_result: str = None, target_iteration=None, **kwargs):
    """
    Start an optimization process (always headless).

    Args:
        device (str, optional): device to use for computation ('cpu'/'cuda:0').
        restart_per_iteration (int): iterations between process restarts.
        path_result (str, optional): existing result folder -> continue there,
            otherwise a fresh timestamped run folder is created.
        target_iteration (int, optional): when continuing, resume from this
            step; None/0 -> resume from the last saved step.
    """
    import multiprocessing as mp

    mp.set_start_method("spawn", force=True)

    if path_result is None:
        import __main__
        main_filepath = __main__.__file__
    else:
        main_filepath = path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py'

    from .taskoptmization import TaskOptimization

    process_optimization = mp.Process(
        target=TaskOptimization.task_optimization,
        kwargs={'path_result': path_result,
                'main_filepath': main_filepath,
                'device': device,
                'target_iteration': target_iteration,
                'restart_per_iteration': restart_per_iteration})
    process_optimization.start()
    process_optimization.join()


def debug_optimization(device='cpu', restart_per_iteration: int = 20,
                       path_result: str = None, target_iteration=None, **kwargs):
    """
    Run the optimization in the current process (debugger friendly).
    """
    import os
    import sys
    import __main__
    import multiprocessing as mp

    from .taskoptmization import TaskOptimization
    import morphopt

    mp.set_start_method("spawn", force=True)

    if path_result is None:
        main_filepath = __main__.__file__
    else:
        main_filepath = path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py'

    filename = os.path.splitext(os.path.basename(main_filepath))[0]
    filepath = os.path.dirname(main_filepath)
    os.chdir(filepath)
    sys.path.append(os.getcwd())

    Controller = getattr(__import__(filename), 'ThisController')

    controller: morphopt.Controller = Controller()
    controller.restart_per_iteration = restart_per_iteration
    controller.optdevice = device
    controller._debug_mode = True

    TaskOptimization.optmain(device=device,
                             path_result=path_result,
                             target_iteration=target_iteration,
                             restart_per_iteration=restart_per_iteration,
                             main_filepath=main_filepath)
