"""Engine-independent contract suite for time_stretch.

Runs against the ``backend`` fixture (today: only "fake"; real engines join
for free once steps 3-4 register native modules), plus a handful of
backend-resolution tests that exercise ``_backends`` and the facade's error
wiring directly.

Reads: pytimestretch, pytimestretch._backends, pytimestretch.errors,
tests.contract.conftest.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from conftest import (
    RaisingFakeStretch,
    ValueErrorFakeStretch,
    WrongDtypeFakeStretch,
    WrongShapeFakeStretch,
    fake_stretch,
    last_call,
    register_fake_backend,
)

import pytimestretch
from pytimestretch.errors import (
    BackendUnavailableError,
    EngineError,
    InvalidAudioError,
    UnknownBackendError,
    UnsupportedOptionError,
)

SAMPLE_RATE = 48_000
RATIOS = [0.25, 0.5, 0.999, 1.0, 1.5, 3.0]
FRAME_COUNTS = [1001, 4410]


def target_frames(frames: int, ratio: float) -> int:
    return math.floor(frames * ratio + 0.5)


# --- Signal builders -------------------------------------------------------


def impulse(frames: int) -> np.ndarray:
    sig = np.zeros(frames, dtype=np.float64)
    sig[0] = 1.0
    return sig


def sine_440(frames: int, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    t = np.arange(frames, dtype=np.float64) / sample_rate
    return np.sin(2 * np.pi * 440.0 * t)


def silence(frames: int) -> np.ndarray:
    return np.zeros(frames, dtype=np.float64)


def noise(frames: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(frames)


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


# --- Backend resolution and error wrapping ------------------------------


def test_unknown_backend_name_raises() -> None:
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(UnknownBackendError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="not-a-real-backend",
        )
    with pytest.raises(ValueError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="not-a-real-backend",
        )


def test_backend_unavailable_wraps_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Step 4 lands signalsmith's native module alongside rubberband, so
    # both real backends are available today; this test instead covers the
    # BackendUnavailableError path directly by injecting a registry loader
    # that raises ImportError, the same way a genuinely unbuilt native
    # module would fail to import.
    from pytimestretch import _backends

    def _raise() -> _backends.RenderFn:
        raise ImportError("no module named pytimestretch._nope")

    monkeypatch.setitem(_backends._REGISTRY, "unbuilt", _raise)
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(BackendUnavailableError) as excinfo:
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="unbuilt",
        )
    assert isinstance(excinfo.value, ImportError)
    assert "unbuilt" in str(excinfo.value)


def test_no_fallback_on_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(UnknownBackendError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="definitely-not-registered",
        )


def test_fake_backend_engine_exception_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "raising-fake", RaisingFakeStretch())
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(EngineError) as excinfo:
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="raising-fake",
        )
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_fake_backend_value_error_wrapped_as_engine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mirrors a real native module raising std::invalid_argument for an
    # unimplemented native contract v2 option (arrives in Python as a plain
    # ValueError): it must still be wrapped as EngineError, not leak as a
    # bare ValueError, since ValueError is not itself a PytimestretchError.
    register_fake_backend(monkeypatch, "value-error-fake", ValueErrorFakeStretch())
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(EngineError) as excinfo:
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="value-error-fake",
        )
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, ValueError)


def test_fake_backend_wrong_shape_raises_engine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "wrong-shape-fake", WrongShapeFakeStretch())
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(EngineError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="wrong-shape-fake",
        )


def test_fake_backend_wrong_dtype_raises_engine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "wrong-dtype-fake", WrongDtypeFakeStretch())
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(EngineError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="wrong-dtype-fake",
        )


def test_all_error_classes_are_pytimestretch_errors_and_exported() -> None:
    from pytimestretch.errors import PytimestretchError

    for name in (
        "InvalidAudioError",
        "UnknownBackendError",
        "BackendUnavailableError",
        "EngineError",
    ):
        cls = getattr(pytimestretch, name)
        assert issubclass(cls, PytimestretchError)


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


# --- available_backends ---------------------------------------------------


def test_available_backends_returns_tuple_of_both_engines() -> None:
    # Step 4 lands signalsmith's native module alongside rubberband (step
    # 3); both are now built and importable in this environment.
    names = pytimestretch.available_backends()
    assert isinstance(names, tuple)
    assert "rubberband" in names
    assert "signalsmith" in names


def test_available_backends_includes_injected_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    assert "fake" in pytimestretch.available_backends()


# --- Packaging -------------------------------------------------------------


def test_py_typed_marker_present_in_installed_package() -> None:
    import pathlib

    import pytimestretch

    package_dir = pathlib.Path(pytimestretch.__file__).parent
    assert (package_dir / "py.typed").is_file()


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
# backend-unsupported quality (UnsupportedOptionError, above), "fast" is no
# longer pytimestretch vocabulary at all, on any backend.
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


# --- UnsupportedOptionError ----------------------------------------------


def test_unsupported_quality_raises_unsupported_option_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(
        monkeypatch, "limited-fake", fake_stretch, supported_quality=("high",)
    )
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(UnsupportedOptionError) as excinfo:
        pytimestretch.time_stretch(
            audio, SAMPLE_RATE, duration_ratio=1.0, quality="balanced",
            backend="limited-fake",
        )
    assert isinstance(excinfo.value, ValueError)
    assert "limited-fake" in str(excinfo.value)
    assert "balanced" in str(excinfo.value)


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


# --- All three validate before backend loading ---------------------------


def test_pitch_shift_validates_before_backend_availability() -> None:
    with pytest.raises(InvalidAudioError):
        pytimestretch.pitch_shift([1, 2, 3], SAMPLE_RATE, semitones=1.0, backend="rubberband")


def test_time_warp_validates_before_backend_availability() -> None:
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_warp([1, 2, 3], SAMPLE_RATE, markers=None, backend="rubberband")


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
