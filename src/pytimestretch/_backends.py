"""Backend registry — the sole owner of backend names and module paths.

Maps a public backend name (``"rubberband"``, ``"signalsmith"``) to a lazy
loader for its native module, resolved into a ``Backend(render,
supported_quality)`` pair. Each native module implements the shared
contract ``render(buffer, sample_rate, markers, pitch_scale,
preserve_formants, quality) -> np.ndarray`` over a float32 C-contiguous
``(channels, frames)`` buffer and an int64 ``(K, 2)`` ``markers`` array
(``(source_frame, output_frame)`` rows, first ``(0, 0)``, strictly
increasing), returning float32 ``(channels, markers[-1][1])``. Its
``SUPPORTED_QUALITY`` tuple names the qualities it can honor; the facade
(``stretch._render``) checks a requested ``quality`` against it before
calling ``render()``. A failed import is reported as
``BackendUnavailableError`` rather than leaking the raw ``ImportError``.

Reads: .errors.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import numpy as np

from .errors import BackendUnavailableError, UnknownBackendError

RenderFn = Callable[[np.ndarray, int, np.ndarray, float, bool, str], np.ndarray]


class Backend(NamedTuple):
    """A resolved backend: its native ``render`` callable plus the quality
    presets it declares support for (``native_module.SUPPORTED_QUALITY``)."""

    render: RenderFn
    supported_quality: tuple[str, ...]


def _load_rubberband() -> Backend:
    # `from ... import render, SUPPORTED_QUALITY` so a native module that is
    # built but lacks either raises ImportError (reported as
    # BackendUnavailableError), not AttributeError.
    from pytimestretch._rubberband import SUPPORTED_QUALITY, render

    return Backend(render=render, supported_quality=tuple(SUPPORTED_QUALITY))


def _load_signalsmith() -> Backend:
    from pytimestretch._signalsmith import SUPPORTED_QUALITY, render

    return Backend(render=render, supported_quality=tuple(SUPPORTED_QUALITY))


# Plain module-level dict so tests can inject a fake backend via
# monkeypatch.setitem(_backends._REGISTRY, "fake", lambda: Backend(...)).
_REGISTRY: dict[str, Callable[[], Backend]] = {
    "rubberband": _load_rubberband,
    "signalsmith": _load_signalsmith,
}

BACKEND_NAMES: tuple[str, ...] = tuple(_REGISTRY)


def load_backend(name: object) -> Backend:
    """Resolve a backend name to its ``Backend(render, supported_quality)``.

    Raises ``UnknownBackendError`` for a name not in the registry (including
    non-string names), and ``BackendUnavailableError`` if the registered
    module fails to import.
    """
    if not isinstance(name, str) or name not in _REGISTRY:
        valid = ", ".join(repr(n) for n in _REGISTRY)
        raise UnknownBackendError(
            f"unknown backend {name!r}; valid backends are: {valid}"
        )

    loader = _REGISTRY[name]
    try:
        return loader()
    except ImportError as exc:
        raise BackendUnavailableError(
            f"backend {name!r} is unavailable: its native module failed to "
            f"import ({exc}). Rebuild or reinstall pytimestretch with its "
            "native extensions (e.g. `uv sync`) to enable it."
        ) from exc


def available_backends() -> tuple[str, ...]:
    """Return the names of registered backends whose native module loads.

    Iterates the live registry (not the frozen ``BACKEND_NAMES``) and tries
    each loader, so a backend registered after import time (tests inject a
    fake this way) is reflected too. A backend whose loader raises
    ``BackendUnavailableError`` or ``ImportError`` is silently excluded;
    other exceptions propagate.
    """
    names = []
    for name, loader in _REGISTRY.items():
        try:
            loader()
        except (BackendUnavailableError, ImportError):
            continue
        names.append(name)
    return tuple(names)


__all__ = ["BACKEND_NAMES", "Backend", "RenderFn", "available_backends", "load_backend"]
