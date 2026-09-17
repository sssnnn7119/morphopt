"""test sensitivity tests."""

from morphopt.optcore.sensitivity import SensitivityAnalyzer


def test_sensitivity_type_exists():
    assert SensitivityAnalyzer().get_sensitivities() == {}
