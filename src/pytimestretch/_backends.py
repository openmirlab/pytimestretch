"""Backend registry — the sole owner of backend names and module paths.

Maps a public backend name (``"rubberband"``, ``"signalsmith"``) to a lazy
loader for its native module's ``render`` callable. Each native module
implements the shared native contract v2: ``render(buffer, sample_rate,
markers, pitch_scale, preserve_formants, quality) -> np.ndarray`` over a
float32, C-contiguous, ``(channels, frames)`` buffer, returning float32
``(channels, markers[-1][1])``. ``markers`` is an int64 ``(K, 2)`` array of
``(source_frame, output_frame)`` rows — first row ``(0, 0)``, last row
``(frames, target_frames)``, both columns strictly increasing, ``K >= 2``
— which the facade builds and the native module re-derives ``frames``/
``target_frames`` from (checking ``markers[-1][0]`` against the buffer's own
frame count) rather than taking them as separate arguments. ``pitch_scale``
is a linear frequency ratio (``1.0`` = unchanged), ``preserve_formants``
keeps the spectral envelope when pitch-shifting, and ``quality`` selects an
engine-specific speed/quality preset (``"high"``/``"balanced"``/``"fast"``,
not every engine honors every name — see each native module's
``SUPPORTED_QUALITY``). As of this native contract v2 step, every native
module still only implements the plain two-marker, ``pitch_scale=1.0``,
``preserve_formants=False``, ``quality="high"`` path; any other combination
raises ``ValueError`` (native ``std::invalid_argument``) naming the
unimplemented feature. A failed import is reported as
``BackendUnavailableError`` rather than leaking the raw ``ImportError``, so
callers get a message naming the backend and how to fix it.

Reads: .errors.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .errors import BackendUnavailableError, UnknownBackendError

RenderFn = Callable[[np.ndarray, int, np.ndarray, float, bool, str], np.ndarray]


def _load_rubberband() -> RenderFn:
    # `from ... import render` so a native module that is built but lacks
    # `render` raises ImportError (reported as BackendUnavailableError),
    # not AttributeError.
    from pytimestretch._rubberband import render

    return render


def _load_signalsmith() -> RenderFn:
    from pytimestretch._signalsmith import render

    return render


# Plain module-level dict so tests can inject a fake backend via
# monkeypatch.setitem(_backends._REGISTRY, "fake", lambda: fake_stretch).
_REGISTRY: dict[str, Callable[[], RenderFn]] = {
    "rubberband": _load_rubberband,
    "signalsmith": _load_signalsmith,
}

BACKEND_NAMES: tuple[str, ...] = tuple(_REGISTRY)


def load_backend(name: object) -> RenderFn:
    """Resolve a backend name to its native ``render`` callable.

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


__all__ = ["BACKEND_NAMES", "RenderFn", "available_backends", "load_backend"]
