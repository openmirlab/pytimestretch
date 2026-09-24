"""Output contract: length, shape, dtype, layout, and immutability.

Runs against the ``backend`` fixture (conftest.py: "fake" plus every
registered real backend that's available). Covers exact output length,
ndim/channel preservation, dtype preservation, fresh-array/contiguity
guarantees, input immutability, channel order, and finite output across
signal types.

Reads: pytimestretch, tests.contract.conftest.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import (
    FRAME_COUNTS,
    RATIOS,
    SAMPLE_RATE,
    fake_stretch,
    impulse,
    noise,
    register_fake_backend,
    silence,
    sine_440,
    target_frames,
)

import pytimestretch
from pytimestretch.errors import InvalidAudioError

# --- Length, shape, dtype ----------------------------------------------


@pytest.mark.parametrize("ratio", RATIOS)
@pytest.mark.parametrize("frames", FRAME_COUNTS)
def test_exact_output_length_mono_1d(backend: str, frames: int, ratio: float) -> None:
    audio = sine_440(frames).astype(np.float32)
    out = pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=ratio, backend=backend
    )
    assert out.shape == (target_frames(frames, ratio),)


@pytest.mark.parametrize("ratio", RATIOS)
def test_exact_output_length_small_input(backend: str, ratio: float) -> None:
    frames = 1
    tgt = target_frames(frames, ratio)
    audio = np.ones(frames, dtype=np.float32)
    if tgt < 1:
        with pytest.raises(InvalidAudioError):
            pytimestretch.time_stretch(
                audio, sample_rate=SAMPLE_RATE, duration_ratio=ratio, backend=backend
            )
        return
    out = pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=ratio, backend=backend
    )
    assert out.shape == (tgt,)


@pytest.mark.parametrize(
    "shape_kind", ["mono_1d", "mono_2d", "stereo"]
)
def test_ndim_and_channels_preserved(backend: str, shape_kind: str) -> None:
    frames = 2000
    if shape_kind == "mono_1d":
        audio = sine_440(frames).astype(np.float32)
        expected_ndim = 1
        expected_shape = None
    elif shape_kind == "mono_2d":
        audio = sine_440(frames).astype(np.float32).reshape(frames, 1)
        expected_ndim = 2
        expected_shape = (target_frames(frames, 1.5), 1)
    else:
        left = silence(frames)
        right = noise(frames)
        audio = np.stack([left, right], axis=1).astype(np.float32)
        expected_ndim = 2
        expected_shape = (target_frames(frames, 1.5), 2)

    out = pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=1.5, backend=backend
    )
    assert out.ndim == expected_ndim
    if expected_shape is not None:
        assert out.shape == expected_shape
    else:
        assert out.shape == (target_frames(frames, 1.5),)


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_dtype_preserved(backend: str, dtype: np.dtype) -> None:
    audio = sine_440(2000).astype(dtype)
    out = pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=1.5, backend=backend
    )
    assert out.dtype == dtype


def test_output_is_fresh_c_contiguous_array(backend: str) -> None:
    audio = sine_440(2000).astype(np.float32)
    out = pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=1.5, backend=backend
    )
    assert out is not audio
    assert out.flags["C_CONTIGUOUS"]


@pytest.mark.parametrize("layout", ["c_contig", "reversed", "fortran"])
def test_input_unchanged(backend: str, layout: str) -> None:
    frames = 2000
    base = np.stack([silence(frames), noise(frames)], axis=1).astype(np.float32)
    if layout == "c_contig":
        audio = base.copy()
    elif layout == "reversed":
        audio = base[::-1].copy()[::-1]  # non-contiguous view, still (N,2)
    else:
        audio = np.asfortranarray(base)

    before = audio.copy()
    pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=1.5, backend=backend
    )
    np.testing.assert_array_equal(audio, before)


def test_stereo_channel_order_preserved(backend: str) -> None:
    frames = 4410
    left = silence(frames)
    right = noise(frames)
    audio = np.stack([left, right], axis=1).astype(np.float32)

    out = pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=1.5, backend=backend
    )
    assert np.abs(out[:, 0]).max() < 1e-6
    assert np.abs(out[:, 1]).max() > 1e-3


def test_silence_in_silence_out_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    audio = silence(4410).astype(np.float32)
    out = pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=1.5, backend="fake"
    )
    assert np.abs(out).max() < 1e-6


@pytest.mark.parametrize("signal_fn", [impulse, sine_440, silence, noise])
def test_various_signals_produce_finite_output(
    backend: str, signal_fn
) -> None:
    audio = signal_fn(4410).astype(np.float32)
    out = pytimestretch.time_stretch(
        audio, sample_rate=SAMPLE_RATE, duration_ratio=0.5, backend=backend
    )
    assert np.isfinite(out).all()
