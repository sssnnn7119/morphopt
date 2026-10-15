"""Keep text assertions independent of the application's default locale."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from morphopt.ui.i18n import localization, set_locale


@pytest.fixture(scope="session", autouse=True)
def ui_test_locale():
    previous = localization.locale
    set_locale("en-US")
    yield
    set_locale(previous)
