"""Shared fixtures for the engine-independent contract suite.

Provides a test-only fake backend implementing native contract v2
(``render(buffer, sample_rate, markers, pitch_scale, preserve_formants,
quality) -> np.ndarray``) via per-channel linear interpolation from
``markers[0][0]``..``markers[-1][0]`` to ``markers[0][1]``..``markers[-1][1]``,
and a ``backend`` fixture parameterized over every registered backend name
plus the fake, so the same suite runs against real engines once they exist
without any changes here. The fake ignores ``pitch_scale``/
``preserve_formants``/``quality`` (steps 3/4 give the real engines opinions
about them); it only needs to honor the marker-derived output length.

Reads: pytimestretch._backends, pytimestretch.errors.
"""

from __future__ import annotations

import numpy as np
import pytest

from pytimestretch import _backends
from pytimestretch.errors import BackendUnavailableError


def fake_stretch(
    buffer: np.ndarray,
    sample_rate: int,
    markers: np.ndarray,
    pitch_scale: float,
    preserve_formants: bool,
    quality: str,
) -> np.ndarray:
    """Native-contract-v2 fake: per-channel linear interpolation to
    ``markers[-1][1]`` frames.

    Also overwrites its input buffer after reading, so a test relying on
    caller-array immutability catches a facade that fails to copy.
    """
    channels, frames = buffer.shape
    target_frames = int(markers[-1, 1])
    src_x = np.arange(frames, dtype=np.float64)
    dst_x = np.linspace(0, max(frames - 1, 0), num=target_frames, dtype=np.float64)

    out = np.empty((channels, target_frames), dtype=np.float32)
    for c in range(channels):
        out[c] = np.interp(dst_x, src_x, buffer[c].astype(np.float64)).astype(
            np.float32
        )

    buffer[...] = 0  # prove the facade never hands the engine a live alias
    return out


class RaisingFakeStretch:
    """Fake backend that always raises, for EngineError-wrapping tests."""

    def __call__(self, *_args: object, **_kwargs: object) -> np.ndarray:
        raise RuntimeError("fake engine failure")


class ValueErrorFakeStretch:
    """Fake backend that raises a plain ValueError, mimicking a native
    std::invalid_argument ("not implemented yet") arriving from a real
    engine's render() -- must still become EngineError, not leak as-is."""

    def __call__(self, *_args: object, **_kwargs: object) -> np.ndarray:
        raise ValueError("fake: feature not implemented yet")


class WrongShapeFakeStretch:
    """Fake backend that returns the wrong shape, for EngineError tests."""

    def __call__(
        self,
        buffer: np.ndarray,
        sample_rate: int,
        markers: np.ndarray,
        pitch_scale: float,
        preserve_formants: bool,
        quality: str,
    ) -> np.ndarray:
        channels = buffer.shape[0]
        target_frames = int(markers[-1, 1])
        return np.zeros((channels, target_frames + 1), dtype=np.float32)


class WrongDtypeFakeStretch:
    """Fake backend that returns the wrong dtype, for EngineError tests."""

    def __call__(
        self,
        buffer: np.ndarray,
        sample_rate: int,
        markers: np.ndarray,
        pitch_scale: float,
        preserve_formants: bool,
        quality: str,
    ) -> np.ndarray:
        channels = buffer.shape[0]
        target_frames = int(markers[-1, 1])
        return np.zeros((channels, target_frames), dtype=np.float64)


@pytest.fixture(params=["fake", "rubberband", "signalsmith"])
def backend(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """A backend name usable with time_stretch, real or faked.

    "fake" registers ``fake_stretch`` under the fake name; real backend
    names are skipped when their native module is unavailable, so this
    suite passes today on "fake" alone and picks up real engines for free
    once steps 3-4 land.
    """
    name = request.param
    if name == "fake":
        monkeypatch.setitem(_backends._REGISTRY, "fake", lambda: fake_stretch)
        return "fake"

    try:
        _backends.load_backend(name)
    except BackendUnavailableError:
        pytest.skip(f"backend {name!r} is unavailable in this environment")
    return name
