"""Package facade: version, the time_stretch entry point, backend
introspection, and public errors.

Reads: .__about__, ._backends, .errors, .stretch.
"""

from .__about__ import __version__
from ._backends import BACKEND_NAMES, available_backends
from .errors import (
    BackendUnavailableError,
    EngineError,
    InvalidAudioError,
    PytimestretchError,
    UnknownBackendError,
)
from .stretch import time_stretch

__all__ = [
    "BACKEND_NAMES",
    "BackendUnavailableError",
    "EngineError",
    "InvalidAudioError",
    "PytimestretchError",
    "UnknownBackendError",
    "__version__",
    "available_backends",
    "time_stretch",
]
