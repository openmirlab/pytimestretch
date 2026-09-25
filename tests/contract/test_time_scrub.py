"""Public position-curve contract for Bungee Basic."""

from __future__ import annotations

import numpy as np
import pytest

import pytimestretch as pts
from pytimestretch.errors import InvalidAudioError


def _tone(frames: int, sample_rate: int = 48_000) -> np.ndarray:
    return (0.2 * np.sin(2 * np.pi * 220 * np.arange(frames) / sample_rate)).astype(
        np.float32
    )


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_hold_keeps_audio_alive_and_preserves_dtype_layout(dtype: type) -> None:
    sample_rate = 48_000
    left = _tone(sample_rate).astype(dtype)
    right = (left * 0.5).copy()
    audio = np.asfortranarray(np.stack((left, right), axis=1))
    before = audio.copy()

    output = pts.time_scrub(
        audio,
        sample_rate,
        control_points=[(0, 0), (sample_rate, sample_rate // 2),
                        (2 * sample_rate, sample_rate // 2)],
    )

    assert output.shape == (2 * sample_rate, 2)
    assert output.dtype == dtype
    assert output.flags.c_contiguous
    assert not np.shares_memory(audio, output)
    np.testing.assert_array_equal(audio, before)
    assert np.sqrt(np.mean(output[int(1.2 * sample_rate):int(1.8 * sample_rate), 0] ** 2)) > 0.04
    assert np.sqrt(np.mean(output[int(1.2 * sample_rate):int(1.8 * sample_rate), 1] ** 2)) > 0.02


def test_reverse_position_places_transient_on_both_passes() -> None:
    sample_rate = 48_000
    audio = np.zeros(sample_rate, dtype=np.float32)
    audio[sample_rate // 2] = 1.0
    output = pts.time_scrub(
        audio,
        sample_rate,
        control_points=[(0, 0), (sample_rate, sample_rate),
                        (2 * sample_rate, 0)],
    )
    for expected in (sample_rate // 2, sample_rate + sample_rate // 2):
        region = output[expected - 48:expected + 48]
        assert np.max(np.abs(region)) > 0.2
        assert abs(np.argmax(np.abs(region)) - 48) <= 3


def test_fractional_source_position_and_mono_2d() -> None:
    audio = np.zeros((48_000, 1), dtype=np.float32)
    output = pts.time_scrub(
        audio, 48_000, control_points=[(0, 0.5), (24_000, 47_999.5)]
    )
    assert output.shape == (24_000, 1)
    assert np.max(np.abs(output)) == 0.0


@pytest.mark.parametrize(
    "points, message",
    [
        (None, "required"),
        ([(0, 0)], "at least 2"),
        ([(1, 0), (10, 10)], "start at output frame 0"),
        ([(0, 0), (0, 10)], "strictly increase"),
        ([(0, 0), (-1, 10)], "strictly increase"),
        ([(0.0, 0), (10, 10)], "integers"),
        ([(False, 0), (10, 10)], "integers"),
        ([(0, 0), (10, float("nan"))], "finite"),
        ([(0, 0), (10, -1)], "within"),
        ([(0, 0), (10, 48_001)], "within"),
        ([(0, 0), (10, True)], "real numbers"),
        ([(0, 0), (10, 5, 3)], "pair"),
    ],
)
def test_invalid_control_points(points: object, message: str) -> None:
    with pytest.raises(InvalidAudioError, match=message):
        pts.time_scrub(
            np.zeros(48_000, dtype=np.float32), 48_000, control_points=points
        )


def test_sample_rate_channels_and_pitch_limits() -> None:
    mono = np.zeros(48_000, dtype=np.float32)
    with pytest.raises(InvalidAudioError, match="sample_rate"):
        pts.time_scrub(mono, 1, control_points=[(0, 0), (48_000, 48_000)])
    with pytest.raises(InvalidAudioError, match="mono or stereo"):
        pts.time_scrub(
            np.zeros((48_000, 3), dtype=np.float32),
            48_000,
            control_points=[(0, 0), (48_000, 48_000)],
        )
    for semitones in (-25, 25, float("nan")):
        with pytest.raises(InvalidAudioError, match="semitones"):
            pts.time_scrub(
                mono, 48_000,
                control_points=[(0, 0), (48_000, 48_000)],
                semitones=semitones,
            )


def test_finite_float64_input_must_fit_native_float32() -> None:
    audio = np.array([1e100, 0.0], dtype=np.float64)
    with pytest.raises(InvalidAudioError, match="fit in float32"):
        pts.time_scrub(audio, 48_000, control_points=[(0, 0), (2, 2)])
