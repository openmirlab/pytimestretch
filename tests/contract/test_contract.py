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
    WrongDtypeFakeStretch,
    WrongShapeFakeStretch,
    fake_stretch,
)

import pytimestretch
from pytimestretch.errors import (
    BackendUnavailableError,
    EngineError,
    InvalidAudioError,
    UnknownBackendError,
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
    from pytimestretch import _backends

    monkeypatch.setitem(_backends._REGISTRY, "fake", lambda: fake_stretch)
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


def test_signalsmith_unavailable_today() -> None:
    # Step 3 lands rubberband's native module (see test_rubberband_unavailable_today's
    # replacement, test_package.py::test_time_stretch_smoke); signalsmith is
    # still unbuilt until step 4, so it must still raise BackendUnavailableError.
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(BackendUnavailableError) as excinfo:
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="signalsmith",
        )
    assert isinstance(excinfo.value, ImportError)
    assert "signalsmith" in str(excinfo.value)


def test_no_fallback_on_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from pytimestretch import _backends

    monkeypatch.setitem(_backends._REGISTRY, "fake", lambda: fake_stretch)
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(UnknownBackendError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="definitely-not-registered",
        )


def test_fake_backend_engine_exception_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pytimestretch import _backends

    monkeypatch.setitem(
        _backends._REGISTRY, "raising-fake", lambda: RaisingFakeStretch()
    )
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(EngineError) as excinfo:
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="raising-fake",
        )
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_fake_backend_wrong_shape_raises_engine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pytimestretch import _backends

    monkeypatch.setitem(
        _backends._REGISTRY, "wrong-shape-fake", lambda: WrongShapeFakeStretch()
    )
    audio = np.zeros(10, dtype=np.float32)
    with pytest.raises(EngineError):
        pytimestretch.time_stretch(
            audio, sample_rate=SAMPLE_RATE, duration_ratio=1.0,
            backend="wrong-shape-fake",
        )


def test_fake_backend_wrong_dtype_raises_engine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pytimestretch import _backends

    monkeypatch.setitem(
        _backends._REGISTRY, "wrong-dtype-fake", lambda: WrongDtypeFakeStretch()
    )
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
    from pytimestretch import _backends

    monkeypatch.setitem(_backends._REGISTRY, "fake", lambda: fake_stretch)
    audio = np.zeros((100, 64), dtype=np.float32)
    out = pytimestretch.time_stretch(
        audio, SAMPLE_RATE, duration_ratio=1.0, backend="fake"
    )
    assert out.shape == (target_frames(100, 1.0), 64)


# --- available_backends ---------------------------------------------------


def test_available_backends_returns_tuple_excluding_unbuilt_engines() -> None:
    # Step 3 lands rubberband's native module; signalsmith stays unbuilt
    # until step 4.
    names = pytimestretch.available_backends()
    assert isinstance(names, tuple)
    assert "rubberband" in names
    assert "signalsmith" not in names


def test_available_backends_includes_injected_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pytimestretch import _backends

    monkeypatch.setitem(_backends._REGISTRY, "fake", lambda: fake_stretch)
    assert "fake" in pytimestretch.available_backends()


# --- Packaging -------------------------------------------------------------


def test_py_typed_marker_present_in_installed_package() -> None:
    import pathlib

    import pytimestretch

    package_dir = pathlib.Path(pytimestretch.__file__).parent
    assert (package_dir / "py.typed").is_file()
