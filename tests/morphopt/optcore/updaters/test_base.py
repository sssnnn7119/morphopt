"""test base tests."""

from morphopt.optcore.updaters.base import BaseUpdater


def test_base_updater():
    assert BaseUpdater("demo").name == "demo"
