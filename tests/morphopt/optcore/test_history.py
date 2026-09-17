"""test history tests."""

from morphopt.optcore.history import History, HistoryRecord
import csv


def test_history_round_trip(tmp_path):
    history = History(tmp_path, ("metric", "energy"))
    history.initialize()
    history.add_record(HistoryRecord(0, 1.5, ((2.0, 3.0),), result_path=tmp_path / "result"))
    history.save(tmp_path)
    with (tmp_path / "logs" / "history.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["iteration"] == "0"
    assert rows[0]["objective"] == "1.5"
    assert rows[0]["case_0_metric"] == "2.0"
    assert rows[0]["case_0_energy"] == "3.0"
    assert history.get_series("metric", case_index=0) == (2.0,)
    assert history.get_series("energy", case_index=0) == (3.0,)

    restored = History(tmp_path)
    restored.load(tmp_path)
    assert restored.get_current_iteration() == 0
    assert restored.get_series("objective") == (1.5,)
