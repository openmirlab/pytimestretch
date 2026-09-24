"""``audio``/``sample_rate``/``duration_ratio`` validation, plus the
channels-first guard.

All engine-independent: every raise here happens before a backend is ever
resolved, so these tests use ``backend="rubberband"`` as a stand-in name
without needing the real engine available.

Reads: pytimestretch, tests.contract.conftest.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import SAMPLE_RATE, fake_stretch, register_fake_backend, target_frames

import pytimestretch
from pytimestretch.errors import InvalidAudioError

# --- Validation --------------------------------------------------------


def test_list_input_rejected() -> None:
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            [0.0, 1.0], sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="rubberband",
        )


@pytest.mark.parametrize(
    "dtype", [np.int16, np.float16, np.complex64]
)
def test_disallowed_dtype_rejected(dtype: np.dtype) -> None:
    audio = np.zeros(10, dtype=dtype)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="rubberband",
        )


def test_3d_audio_rejected() -> None:
    audio = np.zeros((10, 2, 1), dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="rubberband",
        )


def test_zero_frames_rejected() -> None:
    audio = np.zeros((0,), dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="rubberband",
        )


def test_zero_channels_rejected() -> None:
    audio = np.zeros((10, 0), dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="rubberband",
        )


def test_nan_rejected() -> None:
    audio = np.array([0.0, np.nan, 1.0], dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="rubberband",
        )


def test_inf_rejected() -> None:
    audio = np.array([0.0, np.inf, 1.0], dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="rubberband",
        )


@pytest.mark.parametrize("sample_rate", [0, -1, True, 44_100.0])
def test_invalid_sample_rate_rejected(sample_rate: object) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=sample_rate, duration_ratio=1.0,
            backend="rubberband",
        )


@pytest.mark.parametrize(
    "ratio", [0, -1, float("nan"), float("inf"), True]
)
def test_invalid_duration_ratio_rejected(ratio: object) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=ratio,
            backend="rubberband",
        )


def test_ratio_too_small_for_frame_count_rejected() -> None:
    audio = np.ones(1, dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=0.25,
            backend="rubberband",
        )


def test_validation_errors_precede_backend_availability() -> None:
    # These would only succeed today if rubberband were available; they must
    # raise InvalidAudioError regardless, proving validation runs first.
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_stretch(
            [1, 2, 3], sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="rubberband",
        )


# --- Channels-first guard -------------------------------------------------


def test_channels_first_array_rejected_with_transpose_hint() -> None:
    audio = np.zeros((2, 44_100), dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        pytimestretch.time_stretch(
            audio, SAMPLE_RATE, duration_ratio=1.0, backend="rubberband"
        )
    assert ".T" in str(excinfo.value)


def test_wide_but_valid_channel_count_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    audio = np.zeros((100, 64), dtype=np.float32)
    out = pytimestretch.time_stretch(
        audio, SAMPLE_RATE, duration_ratio=1.0, backend="fake"
    )
    assert out.shape == (target_frames(100, 1.0), 64)
