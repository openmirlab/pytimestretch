"""``semitones``/``formants``/``quality`` validation, argument pass-through,
``pitch_shift``'s own contract, and the real-engine option matrix.

The pass-through tests assert exactly what the facade computed and handed
to the fake backend (pitch_scale, preserve_formants, quality, markers). The
tail section runs every option combination (pitch shift, formant
preservation, quality preset, K=3 markers) against both real engines,
skipping a backend that isn't built in this environment.

Reads: pytimestretch, tests.contract.conftest.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import (
    SAMPLE_RATE,
    fake_stretch,
    last_call,
    noise,
    register_fake_backend,
    silence,
    sine_440,
    target_frames,
)

import pytimestretch
from pytimestretch.errors import InvalidAudioError

# --- pitch_shift ------------------------------------------------------


def test_pitch_shift_keeps_length_shape_and_dtype(backend: str) -> None:
    # semitones=0.0 is pitch_scale=1.0, the identity two-marker case every
    # backend (fake and real) already implements, so this runs on all of
    # them without hitting an unimplemented-feature EngineError.
    frames = 4410
    audio = np.stack([silence(frames), noise(frames)], axis=1).astype(np.float32)
    out = pytimestretch.pitch_shift(
        audio, sample_rate=SAMPLE_RATE, semitones=0.0, backend=backend
    )
    assert out.shape == audio.shape
    assert out.dtype == audio.dtype


def test_pitch_shift_missing_semitones_raises_invalid_audio_error() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        pytimestretch.pitch_shift(audio, SAMPLE_RATE, backend="rubberband")
    assert "required" in str(excinfo.value)


# --- semitones / formants / quality validation --------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda audio: pytimestretch.time_stretch(
            audio, SAMPLE_RATE, duration_ratio=1.0, semitones="loud",
            backend="rubberband",
        ),
        lambda audio: pytimestretch.pitch_shift(
            audio, SAMPLE_RATE, semitones=float("nan"), backend="rubberband"
        ),
        lambda audio: pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(0, 0), (10, 10)], semitones=True,
            backend="rubberband",
        ),
    ],
)
def test_invalid_semitones_rejected(call) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError):
        call(audio)


@pytest.mark.parametrize(
    "call",
    [
        lambda audio: pytimestretch.time_stretch(
            audio, SAMPLE_RATE, duration_ratio=1.0, formants="nope",
            backend="rubberband",
        ),
        lambda audio: pytimestretch.pitch_shift(
            audio, SAMPLE_RATE, semitones=1.0, formants="nope", backend="rubberband"
        ),
        lambda audio: pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(0, 0), (10, 10)], formants="nope",
            backend="rubberband",
        ),
    ],
)
def test_invalid_formants_rejected(call) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        call(audio)
    assert "formants" in str(excinfo.value)


@pytest.mark.parametrize(
    "call",
    [
        lambda audio: pytimestretch.time_stretch(
            audio, SAMPLE_RATE, duration_ratio=1.0, quality="ultra",
            backend="rubberband",
        ),
        lambda audio: pytimestretch.pitch_shift(
            audio, SAMPLE_RATE, semitones=1.0, quality="ultra", backend="rubberband"
        ),
        lambda audio: pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(0, 0), (10, 10)], quality="ultra",
            backend="rubberband",
        ),
    ],
)
def test_invalid_quality_rejected(call) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        call(audio)
    assert "quality" in str(excinfo.value)


# quality="fast" was removed 2026-09-25 (blind listening round 2: no
# audible benefit, no real speed edge over "balanced", flat pure pitch
# shifts). It gets its own teaching message pointing at "balanced", raised
# by validation before a backend is ever resolved -- unlike a merely
# backend-unsupported quality (UnsupportedOptionError, in test_backends.py),
# "fast" is no longer pytimestretch vocabulary at all, on any backend.
@pytest.mark.parametrize(
    "call",
    [
        lambda audio: pytimestretch.time_stretch(
            audio, SAMPLE_RATE, duration_ratio=1.0, quality="fast",
            backend="rubberband",
        ),
        lambda audio: pytimestretch.pitch_shift(
            audio, SAMPLE_RATE, semitones=1.0, quality="fast", backend="rubberband"
        ),
        lambda audio: pytimestretch.time_warp(
            audio, SAMPLE_RATE, markers=[(0, 0), (10, 10)], quality="fast",
            backend="rubberband",
        ),
    ],
)
def test_quality_fast_rejected_before_backend_load(call) -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(InvalidAudioError) as excinfo:
        call(audio)
    assert "balanced" in str(excinfo.value)


# --- Argument pass-through (pitch_scale, preserve_formants, quality, markers)


@pytest.mark.parametrize(("semitones", "expected_pitch_scale"), [(12.0, 2.0), (-12.0, 0.5)])
def test_time_stretch_pitch_scale_recorded(
    monkeypatch: pytest.MonkeyPatch, semitones: float, expected_pitch_scale: float
) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    audio = sine_440(1000).astype(np.float32)
    pytimestretch.time_stretch(
        audio, SAMPLE_RATE, duration_ratio=1.0, semitones=semitones, backend="fake"
    )
    assert last_call.pitch_scale == pytest.approx(expected_pitch_scale)


def test_time_stretch_preserve_formants_and_quality_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    audio = sine_440(1000).astype(np.float32)
    pytimestretch.time_stretch(
        audio, SAMPLE_RATE, duration_ratio=1.0, formants="preserve",
        quality="balanced", backend="fake",
    )
    assert last_call.preserve_formants is True
    assert last_call.quality == "balanced"


def test_time_warp_markers_array_passed_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    frames = 100
    audio = sine_440(frames).astype(np.float32)
    markers = [(0, 0), (40, 50), (frames, 120)]
    pytimestretch.time_warp(audio, SAMPLE_RATE, markers=markers, backend="fake")
    assert last_call.markers.dtype == np.int64
    assert last_call.markers.shape == (3, 2)
    np.testing.assert_array_equal(last_call.markers, np.array(markers, dtype=np.int64))


# --- Real engines: both implement native contract v2 (step 4) -------------
#
# Rubber Band (step 3) and Signalsmith (step 4) both now implement native
# contract v2 in full: pitch shift, formant control, quality presets, and
# marker warp all succeed on both. Both engines' SUPPORTED_QUALITY is
# exactly ("high", "balanced") -- "fast" was removed 2026-09-25 (blind
# listening round 2: no audible benefit, no real speed edge over
# "balanced") and is rejected during validation for every backend, before
# UnsupportedOptionError's own backend-capability check is ever reached
# (see test_quality_fast_rejected_before_backend_load above).


@pytest.mark.parametrize(
    ("call", "expected_frames"),
    [
        pytest.param(
            lambda audio: pytimestretch.pitch_shift(
                audio, SAMPLE_RATE, semitones=2.0, backend="rubberband"
            ),
            1000,
            id="pitch_shift_semitones",
        ),
        pytest.param(
            lambda audio: pytimestretch.pitch_shift(
                audio, SAMPLE_RATE, semitones=0.0, formants="preserve",
                backend="rubberband",
            ),
            1000,
            id="pitch_shift_preserve_formants",
        ),
        pytest.param(
            lambda audio: pytimestretch.time_stretch(
                audio, SAMPLE_RATE, duration_ratio=1.5, quality="balanced",
                backend="rubberband",
            ),
            target_frames(1000, 1.5),
            id="time_stretch_quality_balanced",
        ),
        pytest.param(
            lambda audio: pytimestretch.time_warp(
                audio, SAMPLE_RATE,
                markers=[(0, 0), (300, 400), (1000, 1200)],
                backend="rubberband",
            ),
            1200,
            id="time_warp_k3_markers",
        ),
    ],
)
def test_rubberband_full_contract_v2_options_succeed(call, expected_frames: int) -> None:
    # Step 3 (native contract v2 for Rubber Band): every combination that
    # used to raise the "not implemented yet" EngineError now succeeds with
    # the exact length/shape/dtype native contract v2 promises.
    try:
        pytimestretch._backends.load_backend("rubberband")
    except pytimestretch.BackendUnavailableError:
        pytest.skip("rubberband is unavailable in this environment")
    audio = sine_440(1000).astype(np.float32)

    out = call(audio)

    assert isinstance(out, np.ndarray)
    assert out.dtype == np.float32
    assert out.shape == (expected_frames,)
    assert np.isfinite(out).all()


@pytest.mark.parametrize(
    ("call", "expected_frames"),
    [
        pytest.param(
            lambda audio: pytimestretch.pitch_shift(
                audio, SAMPLE_RATE, semitones=2.0, backend="signalsmith"
            ),
            1000,
            id="pitch_shift_semitones",
        ),
        pytest.param(
            lambda audio: pytimestretch.pitch_shift(
                audio, SAMPLE_RATE, semitones=0.0, formants="preserve",
                backend="signalsmith",
            ),
            1000,
            id="pitch_shift_preserve_formants",
        ),
        pytest.param(
            lambda audio: pytimestretch.time_stretch(
                audio, SAMPLE_RATE, duration_ratio=1.5, quality="balanced",
                backend="signalsmith",
            ),
            target_frames(1000, 1.5),
            id="time_stretch_quality_balanced",
        ),
        pytest.param(
            lambda audio: pytimestretch.time_warp(
                audio, SAMPLE_RATE,
                markers=[(0, 0), (300, 400), (1000, 1200)],
                backend="signalsmith",
            ),
            1200,
            id="time_warp_k3_markers",
        ),
    ],
)
def test_signalsmith_full_contract_v2_options_succeed(call, expected_frames: int) -> None:
    # Step 4 (native contract v2 for Signalsmith): every combination that
    # used to raise the "not implemented yet" EngineError now succeeds with
    # the exact length/shape/dtype native contract v2 promises. Rubber Band
    # and Signalsmith now share the same SUPPORTED_QUALITY, so there is no
    # engine-specific quality case to exercise here beyond "balanced".
    try:
        pytimestretch._backends.load_backend("signalsmith")
    except pytimestretch.BackendUnavailableError:
        pytest.skip("signalsmith is unavailable in this environment")
    audio = sine_440(1000).astype(np.float32)

    out = call(audio)

    assert isinstance(out, np.ndarray)
    assert out.dtype == np.float32
    assert out.shape == (expected_frames,)
    assert np.isfinite(out).all()
