"""Discover usable solver devices without creating UI controls."""

from functools import cache


@cache
def detect_devices() -> tuple[str, ...]:
    """Discover devices on first use: CPU plus any torch cuda devices.

    Returns:
        tuple[str, ...]: Usable devices: CPU plus any torch cuda devices.
    """
    devs = ["cpu"]
    try:
        import torch

        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                devs.append(f"cuda:{i}")
    except Exception:
        pass
    return tuple(devs)
