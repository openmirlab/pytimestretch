"""Installed version consistency and a public audio-processing smoke check."""

from importlib.metadata import version

import numpy as np

import pytimestretch


def test_version_matches_installed_metadata() -> None:
    assert pytimestretch.__version__ == version("pytimestretch")


def test_time_stretch_smoke() -> None:
    # Step 3 lands the real rubberband native module: the default backend
    # now works end to end, so this is a genuine smoke call rather than
    # the temporary BackendUnavailableError placeholder from step 1.
    sample_rate = 48_000
    t = np.arange(sample_rate, dtype=np.float64) / sample_rate  # 1 second
    audio = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)

    out = pytimestretch.time_stretch(audio, sample_rate=sample_rate, duration_ratio=1.5)

    assert out.shape == (round(sample_rate * 1.5),)
    assert out.dtype == np.float32
    assert np.isfinite(out).all()
