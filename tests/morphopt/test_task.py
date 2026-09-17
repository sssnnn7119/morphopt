"""test task tests."""

from functools import partial
from queue import Empty

from morphopt.task import RuntimeEvent, TaskRunner
from morphopt.optcore.controller import Controller


def build_empty_controller(result_root, **kwargs):
    """Pickle-safe factory used to validate the spawn supervisor."""
    return Controller(
        result_root=result_root,
        optimization_name="process_flow",
        maximum_iterations=5,
        checkpoint_interval=1,
        debug=False,
        **kwargs,
    )


def build_failing_controller(**kwargs):
    """Factory used to verify supervisor exit-code propagation."""
    raise RuntimeError("factory failure")


def test_runtime_event_round_trip():
    event = RuntimeEvent("started", "run-1", payload={"iteration": 0})
    restored = RuntimeEvent.from_dict(event.to_dict())
    assert restored.event_type == "started"
    assert restored.payload["iteration"] == 0


def test_debug_runner_executes_lifecycle_without_spawn(tmp_path):
    runner = TaskRunner(
        partial(build_empty_controller, str(tmp_path)),
        main_file_path=__file__,
        worker_restart_interval=0,
    )
    assert runner.run_debug() == 0
    assert runner.get_result_path() is not None
    assert (runner.get_result_path() / "logs" / "history.csv").exists()
    events = []
    while True:
        try:
            events.append(runner.event_queue.get(timeout=0.2))
        except Empty:
            break
    assert [event["event_type"] for event in events].count("iteration_finished") == 5
    assert any(event["event_type"] == "finished" for event in events)


def test_spawn_supervisor_forwards_events_and_restarts(tmp_path):
    factory = partial(build_empty_controller, str(tmp_path))
    runner = TaskRunner(
        factory,
        main_file_path=__file__,
        worker_restart_interval=2,
    )
    runner.start()
    assert runner.wait(timeout=60) == 0

    events = []
    while True:
        try:
            events.append(runner.event_queue.get(timeout=0.2))
        except Empty:
            break
    event_types = [event["event_type"] for event in events]
    assert event_types.count("started") == 3
    assert event_types.count("restart_requested") == 2
    assert event_types.count("iteration_finished") == 5
    assert "finished" in event_types

    run_path = runner.get_result_path()
    assert run_path is not None and run_path.exists()
    assert (run_path / "logs" / "history.csv").exists()
    with (run_path / "logs" / "history.csv").open(encoding="utf-8") as stream:
        assert sum(1 for _ in stream) == 6
    assert all(
        (run_path / "checkpoints" / f"iteration_{index:06d}" / "manifest.json").exists()
        for index in range(5)
    )


def test_spawn_supervisor_propagates_worker_failure():
    runner = TaskRunner(
        build_failing_controller, main_file_path=__file__, worker_restart_interval=2
    )
    runner.start()
    assert runner.wait(timeout=60) == 1
    assert runner.event_queue.get(timeout=1)["event_type"] == "failed"
