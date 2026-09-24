"""Public error hierarchy for pytimestretch.

All errors raised across the package's public surface derive from
``PytimestretchError`` so callers can catch the whole family in one clause,
while each subclass also derives from the closest matching stdlib exception
(``ValueError``, ``ImportError``, ``RuntimeError``) so existing except-clauses
written against those keep working.

Reads: nothing internal.
"""

from __future__ import annotations


class PytimestretchError(Exception):
    """Base class for every error this package raises deliberately."""


class InvalidAudioError(PytimestretchError, ValueError):
    """Raised when ``audio``, ``sample_rate``, or ``duration_ratio`` is invalid."""


class UnknownBackendError(PytimestretchError, ValueError):
    """Raised when ``backend`` does not name a registered backend."""


class BackendUnavailableError(PytimestretchError, ImportError):
    """Raised when a registered backend's native module fails to import."""


class EngineError(PytimestretchError, RuntimeError):
    """Raised when a backend fails or returns output violating its contract."""


class UnsupportedOptionError(PytimestretchError, ValueError):
    """Raised when the requested backend cannot honor a requested option.

    Distinct from ``InvalidAudioError``: the option is valid pytimestretch
    vocabulary (e.g. ``quality="fast"``), but the *resolved backend*
    declares it unsupported (its native module's ``SUPPORTED_QUALITY``
    doesn't list it) — never a silent alias to a different value.
    """
