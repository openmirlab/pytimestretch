"""Package facade: time/pitch/warp and creative extreme-stretch entry points,
version, backend introspection, and public errors.

Reads: .__about__, ._backends, .errors, .extreme, .scrub, .stretch.
"""

from .__about__ import __version__
from ._backends import BACKEND_NAMES, available_backends
from .errors import (
    BackendUnavailableError,
    EngineError,
    InvalidAudioError,
    PytimestretchError,
    UnknownBackendError,
    UnsupportedOptionError,
)
from .extreme import extreme_stretch
from .scrub import time_scrub
from .stretch import pitch_shift, time_stretch, time_warp

__all__ = [
    "BACKEND_NAMES",
    "BackendUnavailableError",
    "EngineError",
    "InvalidAudioError",
    "PytimestretchError",
    "UnknownBackendError",
    "UnsupportedOptionError",
    "__version__",
    "available_backends",
    "extreme_stretch",
    "pitch_shift",
    "time_scrub",
    "time_stretch",
    "time_warp",
]
