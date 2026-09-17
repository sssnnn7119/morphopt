"""Optional Torch import used by the architecture skeleton.

Production MorphOpt uses PyTorch.  Keeping a tiny NumPy-backed fallback makes
the pure orchestration and persistence tests runnable before the heavy
scientific dependencies are installed.
"""

from __future__ import annotations

import contextlib
import types
from typing import Any

import numpy as _np

try:  # pragma: no cover - exercised when the project dependency is installed
    import torch as torch
except ImportError:  # pragma: no cover - fallback is covered indirectly
    class Tensor:
        def __init__(self, value: Any) -> None:
            self._array = _np.asarray(value)
            """NumPy storage backing the lightweight Tensor fallback."""

        @property
        def shape(self): return self._array.shape
        @property
        def ndim(self): return self._array.ndim
        @property
        def dtype(self): return self._array.dtype
        @property
        def device(self): return "cpu"
        def numel(self): return int(self._array.size)
        def reshape(self, *shape): return Tensor(self._array.reshape(*shape))
        def reshape_as(self, other): return Tensor(self._array.reshape(other.shape))
        def clone(self): return Tensor(self._array.copy())
        def detach(self): return self
        def requires_grad_(self, value=True): return self
        def clamp(self, minimum, maximum): return Tensor(_np.clip(self._array, minimum, maximum))
        def clamp_min(self, minimum): return Tensor(_np.maximum(self._array, minimum))
        def abs(self): return Tensor(_np.abs(self._array))
        def sum(self, *args, **kwargs): return Tensor(self._array.sum(*args, **kwargs))
        def all(self): return bool(self._array.all())
        def item(self): return self._array.item()
        def __getitem__(self, key): return Tensor(self._array[key])
        def __setitem__(self, key, value): self._array[key] = _unwrap(value)
        def __len__(self): return len(self._array)
        def __float__(self): return float(self._array)
        def __add__(self, other): return Tensor(self._array + _unwrap(other))
        def __radd__(self, other): return Tensor(_unwrap(other) + self._array)
        def __sub__(self, other): return Tensor(self._array - _unwrap(other))
        def __rsub__(self, other): return Tensor(_unwrap(other) - self._array)
        def __mul__(self, other): return Tensor(self._array * _unwrap(other))
        def __rmul__(self, other): return Tensor(_unwrap(other) * self._array)
        def __truediv__(self, other): return Tensor(self._array / _unwrap(other))
        def __pow__(self, other): return Tensor(self._array ** other)
        def __repr__(self): return f"Tensor({self._array!r})"

    def _unwrap(value):
        return value._array if isinstance(value, Tensor) else value

    class _Autograd:
        @staticmethod
        def grad(*args, **kwargs):
            raise RuntimeError("PyTorch is required for autograd operations")

    class _TorchFallback(types.SimpleNamespace):
        Tensor = Tensor
        float32 = _np.float32
        autograd = _Autograd()
        def as_tensor(self, value, dtype=None, device=None): return Tensor(_np.asarray(_unwrap(value), dtype=dtype))
        def tensor(self, value, dtype=None, device=None): return self.as_tensor(value, dtype=dtype, device=device)
        def zeros(self, shape=(), dtype=None, device=None, requires_grad=False): return Tensor(_np.zeros(shape, dtype=dtype))
        def zeros_like(self, value, **kwargs): return Tensor(_np.zeros_like(_unwrap(value)))
        def cat(self, values, dim=0): return Tensor(_np.concatenate([_unwrap(v) for v in values], axis=dim))
        def isfinite(self, value): return Tensor(_np.isfinite(_unwrap(value)))
        @contextlib.contextmanager
        def no_grad(self): yield

    torch = _TorchFallback()
