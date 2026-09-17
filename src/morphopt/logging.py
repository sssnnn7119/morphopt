"""Central logging configuration for MorphOpt.

Only this module configures handlers.  Library code should call
``get_logger(__name__)`` and never configure the process-wide root logger.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TextIO

_LOGGER_NAME = "morphopt"
_DEFAULT_FORMAT = "% (asctime)s | %(levelname)-8s | %(name)s | %(message)s".replace("% ", "%")
_OWNED_HANDLERS: set[logging.Handler] = set()


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger below the ``morphopt`` namespace.

    Parameters
    ----------
    name:
        Module name.  A bare name is automatically prefixed with
        ``morphopt.`` so library code never configures unrelated loggers.
    """

    if not name:
        return logging.getLogger(_LOGGER_NAME)
    if name == _LOGGER_NAME or name.startswith(f"{_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def configure_logging(
    log_path: str | Path | None = None,
    *,
    level: int | str = logging.INFO,
    console: bool = True,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure and return the MorphOpt logger.

    Repeated calls replace only handlers owned by MorphOpt, so task restarts
    and UI embedding do not duplicate every line of output.  ``log_path`` is
    created as UTF-8 text and ``stream`` is useful for a UI console adapter.
    """

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(_DEFAULT_FORMAT)
    for handler in tuple(logger.handlers):
        if handler in _OWNED_HANDLERS:
            logger.removeHandler(handler)
            _OWNED_HANDLERS.remove(handler)
            handler.close()

    if console:
        console_handler = logging.StreamHandler(stream)
        console_handler._morphopt_handler = True  # type: ignore[attr-defined]
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        _OWNED_HANDLERS.add(console_handler)
    if log_path is not None:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler._morphopt_handler = True  # type: ignore[attr-defined]
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        _OWNED_HANDLERS.add(file_handler)
    return logger


def enable_logging() -> None:
    """Enable all handlers previously created by :func:`configure_logging`."""

    for handler in logging.getLogger(_LOGGER_NAME).handlers:
        handler.disabled = False


def disable_logging() -> None:
    """Temporarily silence MorphOpt-owned handlers without removing them."""

    for handler in logging.getLogger(_LOGGER_NAME).handlers:
        handler.disabled = True
