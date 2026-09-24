"""Teaching-error text for legacy pyrubberband/librosa keyword aliases.

Covers the speed-family aliases (``rate``/``speed``/``stretch_factor``/
``tempo``/``factor``/``time_ratio``), ``n_steps``, ``time_map``, and
``rbargs`` on all three public functions, plus the generic unknown-keyword
message and its per-function accepted-keyword list. All engine-independent:
every raise here happens before ``_reject_unexpected_kwargs`` lets a call
reach validation or backend resolution.

Reads: pytimestretch, tests.contract.conftest.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import SAMPLE_RATE

import pytimestretch
from pytimestretch.errors import InvalidAudioError

# --- Teaching errors: legacy rate/speed keyword aliases -----------------


@pytest.mark.parametrize(
    ("kwarg", "value", "expected_ratio"),
    [
        ("rate", 2.0, 0.5),
        ("speed", 2.0, 0.5),
        ("stretch_factor", 4, 0.25),
        ("tempo", 2.0, 0.5),
        ("factor", 2.0, 0.5),
        ("time_ratio", 1.5, 1.5),
    ],
)
def test_speed_alias_keyword_raises_with_conversion(
    kwarg: str, value: object, expected_ratio: float
) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_stretch(audio, SAMPLE_RATE, **{kwarg: value})
    message = str(excinfo.value)
    assert kwarg in message
    assert f"duration_ratio={expected_ratio!r}" in message


@pytest.mark.parametrize("value", [0, "x"])
def test_speed_alias_keyword_without_conversion(value: object) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_stretch(audio, SAMPLE_RATE, rate=value)
    message = str(excinfo.value)
    assert "rate" in message
    assert "duration_ratio=" not in message
    assert "corresponds to" not in message


def test_unknown_keyword_argument_raises_type_error() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_stretch(audio, SAMPLE_RATE, foo=1)
    message = str(excinfo.value)
    assert "foo" in message
    assert "duration_ratio" in message


def test_missing_duration_ratio_raises_invalid_audio_error() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        pytimestretch.time_stretch(audio, SAMPLE_RATE)
    assert "required" in str(excinfo.value)


def test_unexpected_kwarg_checked_before_other_validation() -> None:
    # A bad keyword must raise TypeError even when the rest of the call is
    # also invalid (list input, missing duration_ratio).
    with pytest.raises(TypeError):
        pytimestretch.time_stretch([1, 2, 3], SAMPLE_RATE, rate=2.0)


# --- Teaching errors: pyrubberband aliases on all three functions --------


def test_n_steps_alias_teaches_semitones_on_time_stretch() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_stretch(audio, SAMPLE_RATE, duration_ratio=1.0, n_steps=7)
    message = str(excinfo.value)
    assert "n_steps" in message
    assert "semitones" in message
    assert "semitones=7.0" in message


def test_n_steps_alias_teaches_semitones_on_pitch_shift() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.pitch_shift(audio, SAMPLE_RATE, n_steps=-3)
    message = str(excinfo.value)
    assert "n_steps" in message
    assert "semitones" in message


def test_n_steps_alias_teaches_semitones_on_time_warp() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_warp(audio, SAMPLE_RATE, n_steps=2)
    message = str(excinfo.value)
    assert "n_steps" in message
    assert "semitones" in message


def test_time_map_alias_teaches_markers_on_time_stretch() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_stretch(
            audio, SAMPLE_RATE, duration_ratio=1.0, time_map=[(0, 0), (10, 10)]
        )
    message = str(excinfo.value)
    assert "time_map" in message
    assert "markers" in message


def test_time_map_alias_teaches_markers_on_pitch_shift() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.pitch_shift(audio, SAMPLE_RATE, semitones=1.0, time_map=[])
    message = str(excinfo.value)
    assert "time_map" in message
    assert "markers" in message


def test_time_map_alias_teaches_markers_on_time_warp() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_warp(audio, SAMPLE_RATE, time_map=[])
    message = str(excinfo.value)
    assert "time_map" in message
    assert "markers" in message


def test_rbargs_alias_teaches_presets_on_time_stretch() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_stretch(
            audio, SAMPLE_RATE, duration_ratio=1.0, rbargs={"foo": "bar"}
        )
    message = str(excinfo.value)
    assert "rbargs" in message
    assert "quality" in message
    assert "formants" in message
    assert "semitones" in message


def test_rbargs_alias_teaches_presets_on_pitch_shift() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.pitch_shift(audio, SAMPLE_RATE, semitones=1.0, rbargs={})
    message = str(excinfo.value)
    assert "rbargs" in message


def test_rbargs_alias_teaches_presets_on_time_warp() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_warp(audio, SAMPLE_RATE, rbargs={})
    message = str(excinfo.value)
    assert "rbargs" in message


# --- Unknown kwargs list each function's own accepted keywords -----------


def test_unknown_kwarg_on_pitch_shift_lists_pitch_shift_keywords() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.pitch_shift(audio, SAMPLE_RATE, semitones=1.0, foo=1)
    message = str(excinfo.value)
    assert "semitones" in message
    assert "formants" in message
    assert "quality" in message
    assert "backend" in message
    assert "duration_ratio" not in message
    assert "markers" not in message


def test_unknown_kwarg_on_time_warp_lists_time_warp_keywords() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(TypeError) as excinfo:
        pytimestretch.time_warp(audio, SAMPLE_RATE, markers=[(0, 0), (10, 10)], foo=1)
    message = str(excinfo.value)
    assert "markers" in message
    assert "semitones" in message
    assert "formants" in message
    assert "quality" in message
    assert "backend" in message
    assert "duration_ratio" not in message
