"""Task entry points retain spawn, resume and debugger semantics after merging."""

import json
import multiprocessing as mp
import sys
from pathlib import Path
from queue import Empty
from types import SimpleNamespace

import pytest

from morphopt import opt_runner
from morphopt.postprocess import cpu_torch_defaults


def task_script(folder: Path, fail: bool = False) -> Path:
    script = folder / "runner_test_task.py"
    script.write_text(
        '''import json
from pathlib import Path
import torch

class ThisController:
    created = 0

    def __init__(self):
        type(self).created += 1
        self.path_result = "finished-run"

    def record(self, action, **kwargs):
        Path("report.json").write_text(json.dumps({
            "action": action, "created": self.created,
            "debug": self._debug_mode, "device": self.optdevice,
            "dtype": str(torch.get_default_dtype()),
            "restart_per_iteration": self.restart_per_iteration,
            **kwargs,
        }))

    def start_optimization(self, main_filepath):
        self.record("start", main_filepath=main_filepath)
        if FAIL:
            raise RuntimeError("intentional first-iteration failure")

    def restart_optimization(self, path_result, target_iteration):
        self.record("resume", path_result=path_result, target_iteration=target_iteration)
'''.replace("FAIL", repr(fail)), encoding="utf-8",
    )
    return script


@pytest.mark.parametrize("iteration", [None, 7])
def test_debug_uses_one_controller_and_forwards_resume(iteration, tmp_path, monkeypatch):
    script = task_script(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, script.stem, raising=False)
    monkeypatch.setattr(opt_runner, "_main_script", lambda _folder: str(script))
    with cpu_torch_defaults():
        opt_runner.debug_optimization(
            path_result="saved-run" if iteration else None,
            target_iteration=iteration, restart_per_iteration=3,
        )
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["debug"] is True
    assert report["created"] == 1
    assert report["device"] == "cpu"
    assert report["dtype"] == "torch.float64"
    assert report["restart_per_iteration"] == 3
    assert report["action"] == ("resume" if iteration else "start")
    if iteration:
        assert report["target_iteration"] == iteration
        assert report["path_result"] == "saved-run"


def test_worker_function_is_spawnable(tmp_path):
    script = task_script(tmp_path)
    process = mp.get_context("spawn").Process(
        target=opt_runner._run_worker, kwargs={"main_filepath": str(script)},
    )
    process.start()
    try:
        process.join(timeout=30)
        assert not process.is_alive()
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join()
        process.close()
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["debug"] is False
    assert report["action"] == "start"


def test_public_start_reports_failure_before_first_checkpoint(tmp_path, monkeypatch):
    script = task_script(tmp_path, fail=True)
    monkeypatch.setattr(opt_runner, "_main_script", lambda _folder: str(script))
    with pytest.raises(ChildProcessError, match="Optimization task failed"):
        opt_runner.start_optimization()
    assert (tmp_path / "report.json").is_file()


@pytest.mark.parametrize("phase", ["step", "save"])
@pytest.mark.parametrize("resume", [False, True])
def test_worker_writes_complete_exception_chain_to_result_log(tmp_path, phase, resume):
    script = tmp_path / "runner_logging_task.py"
    script.write_text('''from pathlib import Path
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder=str(Path(__file__).parent))
        self.path_result = str(Path(__file__).parent / "result")
        (Path(self.path_result) / "log").mkdir(parents=True)

    def start_optimization(self, main_filepath):
        self.opt_loop()

    def restart_optimization(self, path_result, target_iteration):
        self.opt_loop()

    def clear_cache(self):
        pass

    def step(self):
        if PHASE == "step":
            raise ValueError("intentional optimization-step failure")
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    def record_history(self, *args):
        pass

    def print_info(self, *args):
        pass

    def save(self):
        try:
            (Path(self.path_result) / "missing" / "1.jpg").write_bytes(b"image")
        except FileNotFoundError as exc:
            raise RuntimeError("intentional save failure") from exc
'''.replace("PHASE", repr(phase)), encoding="utf-8")
    process = mp.get_context("spawn").Process(
        target=opt_runner._run_worker,
        kwargs={
            "main_filepath": str(script),
            "path_result": str(tmp_path / "result") if resume else None,
            "target_iteration": 3 if resume else None,
        },
    )
    process.start()
    try:
        process.join(timeout=30)
        assert not process.is_alive()
        assert process.exitcode == 1
    finally:
        if process.is_alive():
            process.terminate()
            process.join()
        process.close()
    text = (tmp_path / "result" / "log" / "morphopt.log").read_text(encoding="utf-8")
    assert text.count("Optimization worker failed") == 1
    assert "Traceback (most recent call last)" in text
    assert script.name in text
    if phase == "step":
        assert "ValueError: intentional optimization-step failure" in text
    else:
        assert "FileNotFoundError" in text and "1.jpg" in text
        assert "RuntimeError: intentional save failure" in text
        assert "direct cause" in text


@pytest.mark.parametrize("exitcode", [0, 1])
def test_task_continues_from_last_checkpoint(exitcode, monkeypatch):
    launches = []
    closed = []

    class StopTest(Exception):
        pass

    class Checkpoints:
        def __init__(self):
            self.sent = False

        def get(self, timeout):
            if not self.sent:
                self.sent = True
                return {"path_result": "saved-run", "iteration": 4}
            raise Empty

        def close(self):
            closed.append("close")

        def join_thread(self):
            closed.append("join")

    def process_factory(target, kwargs):
        launches.append((target, kwargs))
        if len(launches) > 1:
            raise StopTest
        return SimpleNamespace(
            start=lambda: None, is_alive=lambda: False, join=lambda: None,
            close=lambda: None, exitcode=exitcode,
        )

    monkeypatch.setattr(opt_runner.mp, "Queue", Checkpoints)
    monkeypatch.setattr(opt_runner.mp, "Process", process_factory)
    with pytest.raises(StopTest):
        opt_runner._run_task(path_result=None, main_filepath="job.py")
    assert launches[1][0] is opt_runner._run_worker
    assert launches[1][1]["path_result"] == "saved-run"
    assert launches[1][1]["target_iteration"] is None
    assert closed == ["close", "join"]
