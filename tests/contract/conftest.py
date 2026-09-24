"""Shared fixtures for the engine-independent contract suite.

Provides a test-only fake backend implementing native contract v2
(``render(buffer, sample_rate, markers, pitch_scale, preserve_formants,
quality) -> np.ndarray``) via per-marker-segment linear interpolation (each
consecutive marker pair resamples its own segment independently, so markers
genuinely shape both the length and the placement of the output -- not just
the two-marker plain-stretch endpoint case), plus a ``backend`` fixture
parameterized over every registered backend name plus the fake, so the same
suite runs against real engines once they exist without any changes here.
The fake ignores ``pitch_scale``/``preserve_formants``/``quality`` for its
own output (steps 3/4 give the real engines opinions about them) but
records every argument of its last call on the module-level ``last_call``
object, so tests can assert exactly what the facade passed through.

``register_fake_backend`` wraps a render callable (and a configurable
``SUPPORTED_QUALITY``, default all three presets) into the ``Backend``
shape ``_backends.load_backend`` now returns, for tests that inject other
fakes (raising, wrong-shape, wrong-dtype, limited-quality) into the
registry.

Reads: pytimestretch._backends, pytimestretch.errors.
"""

from __future__ import annotations

import numpy as np
import pytest

from pytimestretch import _backends
from pytimestretch._backends import Backend
from pytimestretch.errors import BackendUnavailableError


class _LastCall:
    """Module-level recorder for the fake backend's most recent render()
    call, so contract tests can assert exactly what the facade passed
    through (pitch_scale, preserve_formants, quality, markers)."""

    buffer: np.ndarray | None = None
    sample_rate: int | None = None
    markers: np.ndarray | None = None
    pitch_scale: float | None = None
    preserve_formants: bool | None = None
    quality: str | None = None


last_call = _LastCall()


def fake_stretch(
    buffer: np.ndarray,
    sample_rate: int,
    markers: np.ndarray,
    pitch_scale: float,
    preserve_formants: bool,
    quality: str,
) -> np.ndarray:
    """Native-contract-v2 fake: per-marker-segment linear interpolation.

    Each consecutive marker pair resamples its own segment of the input
    independently onto its own span of the output, so the fake's output
    genuinely reflects marker placement (not just the overall two-endpoint
    ratio). ``pitch_scale``/``preserve_formants``/``quality`` don't affect
    this fake's output, but every argument is recorded on ``last_call``
    before the input buffer is zeroed, so tests can assert what the facade
    computed and passed through.

    Also overwrites its input buffer after reading, so a test relying on
    caller-array immutability catches a facade that fails to copy.
    """
    last_call.buffer = buffer.copy()
    last_call.sample_rate = sample_rate
    last_call.markers = markers.copy()
    last_call.pitch_scale = pitch_scale
    last_call.preserve_formants = preserve_formants
    last_call.quality = quality

    channels, frames = buffer.shape
    target_frames = int(markers[-1, 1])
    buffer_f64 = buffer.astype(np.float64)
    xp = np.arange(frames, dtype=np.float64)

    out = np.empty((channels, target_frames), dtype=np.float32)
    for i in range(len(markers) - 1):
        src_start, dst_start = int(markers[i, 0]), int(markers[i, 1])
        src_end, dst_end = int(markers[i + 1, 0]), int(markers[i + 1, 1])
        seg_len = dst_end - dst_start
        # np.interp clamps queries outside [0, frames) to the boundary
        # sample rather than raising, so src_end == frames (the last
        # marker's convention) needs no special-casing here.
        query_x = np.linspace(src_start, src_end, num=seg_len, endpoint=False)
        for c in range(channels):
            out[c, dst_start:dst_end] = np.interp(
                query_x, xp, buffer_f64[c]
            ).astype(np.float32)

    buffer[...] = 0  # prove the facade never hands the engine a live alias
    return out


def register_fake_backend(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    render,
    supported_quality: tuple[str, ...] = ("high", "balanced"),
) -> None:
    """Register ``render`` under ``name`` in ``_backends._REGISTRY``, wrapped
    as the ``Backend(render, supported_quality)`` shape ``load_backend`` now
    returns."""
    monkeypatch.setitem(
        _backends._REGISTRY,
        name,
        lambda: Backend(render=render, supported_quality=supported_quality),
    )


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
        register_fake_backend(monkeypatch, "fake", fake_stretch)
        return "fake"

    try:
        _backends.load_backend(name)
    except BackendUnavailableError:
        pytest.skip(f"backend {name!r} is unavailable in this environment")
    return name
