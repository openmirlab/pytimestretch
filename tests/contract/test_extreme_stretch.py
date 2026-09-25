"""Separate creative contract for libpaulstretch's native-duration output."""

from __future__ import annotations

import numpy as np
import pytest

import pytimestretch
from pytimestretch.errors import InvalidAudioError


def _tone(frames: int, *, dtype: type[np.float32 | np.float64] = np.float32) -> np.ndarray:
    t = np.arange(frames, dtype=np.float64) / 44_100
    return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(dtype)


def test_original_ratio_keeps_upstream_approximate_length() -> None:
    audio = _tone(4 * 44_100)
    output = pytimestretch.extreme_stretch(audio, 44_100, duration_ratio=8.0)
    assert output.shape == (1_376_256,)  # 31.208 s, rather than exact 32 s
    assert np.isfinite(output).all()
    assert np.max(np.abs(output)) > 0.01


def test_subunit_ratio_can_shorten_audio() -> None:
    audio = _tone(4 * 44_100)
    output = pytimestretch.extreme_stretch(audio, 44_100, duration_ratio=0.1)
    assert output.shape == (20_480,)  # 0.116x, rather than exact 0.1x
    assert np.isfinite(output).all()
    assert np.max(np.abs(output)) > 0.01


def test_smallest_supported_ratio_stays_within_native_skip_limit() -> None:
    audio = np.zeros(81_920, dtype=np.float32)
    output = pytimestretch.extreme_stretch(audio, 44_100, duration_ratio=1e-5)
    assert output.shape == (4096,)
    assert np.isfinite(output).all()


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_stereo_dtype_layout_and_input_immutability(dtype: type) -> None:
    tone = _tone(81_920, dtype=dtype)
    base = np.stack((np.zeros_like(tone), tone), axis=1)
    audio = np.asfortranarray(base)
    before = audio.copy()
    output = pytimestretch.extreme_stretch(audio, 44_100, duration_ratio=2.0)
    assert output.shape == (147_456, 2)
    assert output.dtype == dtype
    assert output.flags.c_contiguous
    assert not np.shares_memory(output, audio)
    np.testing.assert_array_equal(audio, before)
    assert np.max(np.abs(output[:, 0])) < 1e-6
    assert np.max(np.abs(output[:, 1])) > 0.01


def test_reversed_input_and_phase_randomization() -> None:
    audio = _tone(81_920)[::-1]
    assert not audio.flags.c_contiguous
    before = audio.copy()
    first = pytimestretch.extreme_stretch(audio, 44_100, duration_ratio=2.0)
    second = pytimestretch.extreme_stretch(audio, 44_100, duration_ratio=2.0)
    assert first.shape == second.shape
    assert np.isfinite(first).all() and np.isfinite(second).all()
    assert not np.array_equal(first, second)
    np.testing.assert_array_equal(audio, before)


def test_silence_and_mono_2d() -> None:
    audio = np.zeros((81_920, 1), dtype=np.float32)
    output = pytimestretch.extreme_stretch(audio, 44_100, duration_ratio=2.0)
    assert output.shape == (147_456, 1)
    assert np.max(np.abs(output)) == 0.0


@pytest.mark.parametrize("frames", [1, 12_288, 81_919])
def test_rejects_too_short_audio(frames: int) -> None:
    with pytest.raises(InvalidAudioError, match="81920 input frames"):
        pytimestretch.extreme_stretch(
            np.zeros(frames, dtype=np.float32), 44_100, duration_ratio=8.0
        )


@pytest.mark.parametrize("ratio", [0, 1e-6, -1, float("nan"), float("inf"), True, "8"])
def test_rejects_invalid_duration_ratio(ratio: object) -> None:
    with pytest.raises(InvalidAudioError, match="duration_ratio"):
        pytimestretch.extreme_stretch(
            np.zeros(81_920, dtype=np.float32), 44_100, duration_ratio=ratio
        )


def test_rejects_more_than_stereo() -> None:
    with pytest.raises(InvalidAudioError, match="mono or stereo"):
        pytimestretch.extreme_stretch(
            np.zeros((81_920, 3), dtype=np.float32), 44_100, duration_ratio=8.0
        )


def test_invalid_audio_and_sample_rate_reuse_public_validation() -> None:
    with pytest.raises(InvalidAudioError, match="finite"):
        audio = np.zeros(81_920, dtype=np.float32)
        audio[0] = np.nan
        pytimestretch.extreme_stretch(audio, 44_100, duration_ratio=8.0)
    with pytest.raises(InvalidAudioError, match="sample_rate"):
        pytimestretch.extreme_stretch(
            np.zeros(81_920, dtype=np.float32), 0, duration_ratio=8.0
        )
