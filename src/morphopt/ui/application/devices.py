"""Discover usable solver devices without creating UI controls."""


def detect_devices() -> list[str]:
    """Return a list of usable devices: CPU plus any torch cuda devices."""
    devs = ["cpu"]
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                devs.append(f"cuda:{i}")
    except Exception:
        pass
    return devs
