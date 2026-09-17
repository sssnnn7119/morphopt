"""test protocols tests."""

from morphopt.optcore.protocols import Initializable, Persistable, Updatable, Visualizable


def test_protocols_are_runtime_checkable():
    assert Initializable is not None
    assert Persistable is not None
    assert Updatable is not None
    assert Visualizable is not None
