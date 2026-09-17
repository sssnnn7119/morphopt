"""test init tests."""

def test_public_imports():
    import morphopt

    assert "Controller" in morphopt.__all__
