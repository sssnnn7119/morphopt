"""Scoped Torch defaults used while reading and evaluating saved results."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import torch


@contextmanager
def torch_defaults(dtype: torch.dtype, device: torch.device | str) -> Iterator[None]:
    """Set numerical defaults for one operation and restore the caller's state."""
    previous_dtype = torch.get_default_dtype()
    previous_device = torch.get_default_device()
    torch.set_default_dtype(dtype)
    torch.set_default_device(device)
    try:
        yield
    finally:
        torch.set_default_dtype(previous_dtype)
        torch.set_default_device(previous_device)


def cpu_torch_defaults() -> AbstractContextManager[None]:
    """Use the CPU and float64 conventions of archived optimization data."""
    return torch_defaults(torch.float64, "cpu")


def evaluation_defaults(result: Any) -> AbstractContextManager[None]:
    """Match TorchFEA working arrays to the saved solution's dtype and device."""
    return torch_defaults(result.GC.dtype, result.GC.device)
