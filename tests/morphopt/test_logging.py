"""test logging tests."""

from morphopt.logging import configure_logging, get_logger


def test_logging_configuration_is_idempotent(tmp_path):
    logger = configure_logging(tmp_path / "run.log")
    configure_logging(tmp_path / "run.log")
    get_logger(__name__).info("smoke")
    assert (tmp_path / "run.log").exists()
    owned_handlers = [handler for handler in logger.handlers if getattr(handler, "_morphopt_handler", False)]
    assert len(owned_handlers) == 2
