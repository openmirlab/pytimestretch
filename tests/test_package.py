"""Smoke checks for the truthful bootstrap surface."""

import numpy as np
import pytest

import pytimestretch


def test_version_is_importable() -> None:
    assert pytimestretch.__version__ == "0.0.0"


def test_stretch_raises_backend_unavailable() -> None:
    # Temporary truth for step 1: the facade and contract are implemented,
    # but no native backend module exists yet, so the default backend
    # ("rubberband") always fails to load. This flips to real output once
    # step 3 ships the native module.
    audio = np.zeros(100, dtype=np.float32)
    with pytest.raises(pytimestretch.BackendUnavailableError):
        pytimestretch.time_stretch(audio, sample_rate=48_000, duration_ratio=1.5)
