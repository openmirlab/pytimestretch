"""Backend registry — the sole owner of backend names and module paths.

Maps a public backend name (``"rubberband"``, ``"signalsmith"``) to a lazy
loader for its native module's ``stretch`` callable. Each native module
implements the shared native contract: ``stretch(buffer, sample_rate,
duration_ratio, target_frames) -> np.ndarray`` over a float32,
C-contiguous, ``(channels, frames)`` buffer, returning float32
``(channels, target_frames)``. A failed import is reported as
``BackendUnavailableError`` rather than leaking the raw ``ImportError``, so
callers get a message naming the backend and how to fix it.

Reads: .errors.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .errors import BackendUnavailableError, UnknownBackendError

StretchFn = Callable[[np.ndarray, int, float, int], np.ndarray]


def _load_rubberband() -> StretchFn:
    # `from ... import stretch` so a native module that is built but lacks
    # `stretch` raises ImportError (reported as BackendUnavailableError),
    # not AttributeError.
    from pytimestretch._rubberband import stretch

    return stretch


def _load_signalsmith() -> StretchFn:
    from pytimestretch._signalsmith import stretch

    return stretch


# Plain module-level dict so tests can inject a fake backend via
# monkeypatch.setitem(_backends._REGISTRY, "fake", lambda: fake_stretch).
_REGISTRY: dict[str, Callable[[], StretchFn]] = {
    "rubberband": _load_rubberband,
    "signalsmith": _load_signalsmith,
}

BACKEND_NAMES: tuple[str, ...] = tuple(_REGISTRY)


def load_backend(name: object) -> StretchFn:
    """Resolve a backend name to its native ``stretch`` callable.

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


__all__ = ["BACKEND_NAMES", "StretchFn", "available_backends", "load_backend"]
