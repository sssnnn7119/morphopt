"""Scoped Torch defaults used while reading and evaluating saved results."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import torch


@contextmanager
def torch_defaults(dtype: torch.dtype, device: torch.device | str) -> Iterator[None]:
    """Set numerical defaults for one operation and restore the caller's state.

    Args:
        dtype (torch.dtype): PyTorch floating-point dtype used for the constructed tensors.
        device (torch.device | str): PyTorch device used for tensor operations; None retains the
            owning controller's device when supported.

    Yields:
        None: Execute the enclosed operation under the requested Torch defaults; restore both dtype and device on exit.
    """
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
    """Use the CPU and float64 conventions of archived optimization data.

    Returns:
        AbstractContextManager[None]: Scope that uses CPU tensors and float64, restoring the
            previous defaults on exit.
    """
    return torch_defaults(torch.float64, "cpu")


def evaluation_defaults(result: Any) -> AbstractContextManager[None]:
    """Match TorchFEA working arrays to the saved solution's dtype and device.

    Args:
        result (Any): Finite-element solution or completed operation result.

    Returns:
        AbstractContextManager[None]: Scope that uses the saved solution's dtype and device,
            restoring the previous defaults on exit.
    """
    return torch_defaults(result.GC.dtype, result.GC.device)
