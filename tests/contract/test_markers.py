"""``time_warp`` marker contract: length/equivalence and validation.

Covers the K=2 plain-stretch-equivalent case, exact output length as the
last marker's output frame, list/ndarray input equivalence, and every
``_check_markers`` rejection (missing, wrong shape, too few rows, doesn't
start at origin, last source mismatch, non-positive output length,
non-strictly-increasing columns, float/bool dtypes).

Reads: pytimestretch, tests.contract.conftest.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import (
    SAMPLE_RATE,
    fake_stretch,
    register_fake_backend,
    sine_440,
    target_frames,
)

import pytimestretch
from pytimestretch.errors import InvalidAudioError

# --- time_warp: length and marker equivalence --------------------------


def test_time_warp_two_marker_exact_length(backend: str) -> None:
    # K=2 markers reduce to the same plain-stretch case every backend (fake
    # and real) already implements.
    frames = 4410
    audio = sine_440(frames).astype(np.float32)
    target = target_frames(frames, 1.5)
    out = pytimestretch.time_warp(
        audio, SAMPLE_RATE, markers=[(0, 0), (frames, target)], backend=backend
    )
    assert out.shape == (target,)


def test_time_warp_multi_marker_exact_length_is_last_output_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    frames = 4410
    audio = sine_440(frames).astype(np.float32)
    markers = [(0, 0), (2000, 3000), (frames, 5000)]
    out = pytimestretch.time_warp(audio, SAMPLE_RATE, markers=markers, backend="fake")
    assert out.shape == (5000,)


def test_time_warp_markers_list_and_ndarray_equivalent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    frames = 4410
    audio = sine_440(frames).astype(np.float32)
    markers_list = [(0, 0), (2000, 3000), (frames, 5000)]
    markers_arr = np.array(markers_list, dtype=np.int64)

    out_list = pytimestretch.time_warp(
        audio, SAMPLE_RATE, markers=markers_list, backend="fake"
    )
    out_arr = pytimestretch.time_warp(
        audio, SAMPLE_RATE, markers=markers_arr, backend="fake"
    )
    np.testing.assert_array_equal(out_list, out_arr)


# --- time_warp: marker validation ---------------------------------------


def test_time_warp_missing_markers_raises_invalid_audio_error() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        pytimestretch.time_warp(audio, SAMPLE_RATE, backend="rubberband")
    assert "markers" in str(excinfo.value)


def test_time_warp_markers_must_be_shape_kx2() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[0, 1, 2], backend="rubberband"
        )


def test_time_warp_markers_need_at_least_two_rows() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(0, 0)], backend="rubberband"
        )


def test_time_warp_markers_must_start_at_origin() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(1, 0), (10, 10)], backend="rubberband"
        )
    assert "(0, 0)" in str(excinfo.value)


def test_time_warp_markers_last_source_must_equal_frame_count() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(0, 0), (9, 10)], backend="rubberband"
        )
    assert "10" in str(excinfo.value)


def test_time_warp_markers_last_output_must_be_positive() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(0, 0), (10, 0)], backend="rubberband"
        )


@pytest.mark.parametrize(
    "markers",
    [
        [(0, 0), (5, 5), (5, 8), (10, 10)],  # source repeats (5 == 5)
        [(0, 0), (5, 5), (8, 5), (10, 10)],  # output repeats (5 == 5)
        [(0, 0), (6, 4), (3, 8), (10, 10)],  # source decreases (6 -> 3)
    ],
)
def test_time_warp_markers_must_strictly_increase(markers: list) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        pytimestretch.time_warp(audio, SAMPLE_RATE, markers=markers, backend="rubberband")
    assert "strictly increase" in str(excinfo.value)


def test_time_warp_float_markers_rejected_with_round_hint() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(0.0, 0.0), (10.0, 10.0)],
            backend="rubberband",
        )
    assert "np.round" in str(excinfo.value)


def test_time_warp_bool_markers_rejected() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=np.array([[False, False], [True, True]]),
            backend="rubberband",
        )
