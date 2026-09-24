"""Backend registry, resolution, availability, and error wrapping.

Covers ``_backends`` directly (unknown name, unavailable import, no
fallback), the facade's ``EngineError``/``UnsupportedOptionError`` wrapping
around a fake backend's failures, ``available_backends()``, and the
validate-before-backend-resolution ordering for ``pitch_shift``/
``time_warp`` (``time_stretch``'s own version lives in
test_audio_validation.py).

Reads: pytimestretch, pytimestretch._backends, pytimestretch.errors,
tests.contract.conftest.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import (
    SAMPLE_RATE,
    RaisingFakeStretch,
    ValueErrorFakeStretch,
    WrongDtypeFakeStretch,
    WrongShapeFakeStretch,
    fake_stretch,
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
    # Both real backends are built and importable in this environment; this
    # test instead covers the BackendUnavailableError path directly by
    # injecting a registry loader that raises ImportError, the same way a
    # genuinely unbuilt native module would fail to import.
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


# --- available_backends ---------------------------------------------------


def test_available_backends_returns_tuple_of_both_engines() -> None:
    names = pytimestretch.available_backends()
    assert isinstance(names, tuple)
    assert "rubberband" in names
    assert "signalsmith" in names


def test_available_backends_includes_injected_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_fake_backend(monkeypatch, "fake", fake_stretch)
    assert "fake" in pytimestretch.available_backends()


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


# --- All three validate before backend loading ---------------------------


def test_pitch_shift_validates_before_backend_availability() -> None:
    with pytest.raises(InvalidAudioError):
        pytimestretch.pitch_shift([1, 2, 3], SAMPLE_RATE, semitones=1.0, backend="rubberband")


def test_time_warp_validates_before_backend_availability() -> None:
    with pytest.raises(InvalidAudioError):
        pytimestretch.time_warp([1, 2, 3], SAMPLE_RATE, markers=None, backend="rubberband")
