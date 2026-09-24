"""Backend-neutral time-stretch entry point.

``time_stretch`` is the sole owner of the public contract: it validates
``audio``/``sample_rate``/``duration_ratio``, computes the exact output frame
count, converts the input into the native contract's channels-first float32
layout (always a fresh copy, never aliasing the caller's array), dispatches
to the resolved backend, and checks the backend's result before converting
it back to the caller's original layout and dtype. Backend selection and
native-module loading are owned by ``_backends``; validation errors are
always raised before a backend is resolved, so an unavailable backend never
masks a bad call.

Reads: ._backends, .errors.
"""

from __future__ import annotations

import math
import numbers

import numpy as np

from ._backends import load_backend
from .errors import EngineError, InvalidAudioError, PytimestretchError

# 2-D input past this many "channels" is almost certainly a channels-first
# array (e.g. librosa's ``(channels, samples)``) rather than genuine audio.
MAX_CHANNELS = 64

# Keyword names from pyrubberband/librosa's ``time_stretch(y, sr, rate=...)``
# family whose *sign convention is inverted* relative to ours: their value
# is a speed factor (>1 = faster/shorter), ours is a duration ratio (>1 =
# longer/slower). ``time_ratio`` is Rubber Band's own C++ option name, which
# already means output/input, so it maps straight through instead of
# inverting.
_SPEED_ALIASES = ("rate", "speed", "stretch_factor", "time_ratio", "tempo", "factor")

_ACCEPTED_KEYWORDS = ("duration_ratio", "backend")

_DURATION_RATIO_EXPLAINER = (
    "pytimestretch uses duration_ratio = output length / input length "
    "(>1 = longer/slower, <1 = shorter/faster), not a speed factor"
)


def _check_audio(audio: object) -> tuple[int, int | None]:
    """Validate ``audio`` and return ``(frames, channels)`` (channels is
    ``None`` for 1-D input)."""
    if not isinstance(audio, np.ndarray):
        raise InvalidAudioError(f"audio must be a numpy.ndarray, got {type(audio)!r}")
    if audio.dtype not in (np.float32, np.float64):
        raise InvalidAudioError(
            f"audio dtype must be float32 or float64, got {audio.dtype}"
        )
    if audio.ndim not in (1, 2):
        raise InvalidAudioError(f"audio must be 1-D or 2-D, got ndim={audio.ndim}")

    frames = audio.shape[0]
    if frames < 1:
        raise InvalidAudioError(f"audio must have at least 1 frame, got {frames}")

    channels = None
    if audio.ndim == 2:
        channels = audio.shape[1]
        if channels < 1:
            raise InvalidAudioError(
                f"audio must have at least 1 channel, got {channels}"
            )
        if channels > MAX_CHANNELS:
            raise InvalidAudioError(
                f"audio has shape {audio.shape}, which looks channels-first "
                f"(e.g. librosa's (channels, samples)) rather than "
                f"pytimestretch's expected (frames, channels) layout, like "
                "soundfile. Pass audio.T instead (and .T the result back if "
                "you need the original orientation)."
            )

    if not np.isfinite(audio).all():
        raise InvalidAudioError("audio must be finite (no NaN or inf)")

    return frames, channels


def _check_sample_rate(sample_rate: object) -> int:
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, numbers.Integral):
        raise InvalidAudioError(
            f"sample_rate must be an integer, got {type(sample_rate)!r}"
        )
    if sample_rate <= 0:
        raise InvalidAudioError(f"sample_rate must be > 0, got {sample_rate}")
    return int(sample_rate)


def _alias_conversion_note(key: str, value: object) -> str:
    """Best-effort teaching note for an alias keyword's value, or "" if the
    value isn't a usable positive finite number."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return ""
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        return ""
    if key == "time_ratio":
        return f"{key}={value!r} corresponds to duration_ratio={value!r}"
    converted = 1.0 / value
    return f"{key}={value!r} corresponds to duration_ratio={converted!r}"


def _reject_unexpected_kwargs(unexpected: dict[str, object]) -> None:
    """Raise ``TypeError`` for any leftover keyword argument.

    Must run before any other validation: an alias like ``rate=2.0`` is a
    caller mistake about *which* keyword to use, and should be diagnosed as
    that, not masked by an "duration_ratio is required" InvalidAudioError.
    """
    if not unexpected:
        return

    key, value = next(iter(unexpected.items()))
    if key in _SPEED_ALIASES:
        note = _alias_conversion_note(key, value)
        message = f"time_stretch() got an unexpected keyword argument {key!r}: "
        message += _DURATION_RATIO_EXPLAINER
        if note:
            message += f". {note}"
        raise TypeError(message)

    accepted = ", ".join(repr(k) for k in _ACCEPTED_KEYWORDS)
    raise TypeError(
        f"time_stretch() got an unexpected keyword argument {key!r}; "
        f"accepted keywords are: {accepted}"
    )


def _resolve_duration_ratio(duration_ratio: object) -> float:
    if duration_ratio is None:
        raise InvalidAudioError(
            "duration_ratio is required: output length / input length, "
            "e.g. 2.0 = twice as long/slower, 0.5 = half as long/faster"
        )
    if isinstance(duration_ratio, bool) or not isinstance(
        duration_ratio, numbers.Real
    ):
        raise InvalidAudioError(
            f"duration_ratio must be a real number, got {type(duration_ratio)!r}"
        )
    duration_ratio = float(duration_ratio)
    if not math.isfinite(duration_ratio) or duration_ratio <= 0:
        raise InvalidAudioError(
            f"duration_ratio must be finite and > 0, got {duration_ratio}"
        )
    return duration_ratio


def _target_frames(frames: int, duration_ratio: float) -> int:
    target = math.floor(frames * duration_ratio + 0.5)
    if target < 1:
        raise InvalidAudioError(
            "duration_ratio is too small for this many frames: "
            f"target_frames={target}"
        )
    return target


def time_stretch(
    audio: np.ndarray,
    sample_rate: int,
    *,
    duration_ratio: float | None = None,
    backend: str = "rubberband",
    **unexpected: object,
) -> np.ndarray:
    """Time-stretch ``audio`` to a new duration.

    Parameters
    ----------
    audio : numpy.ndarray
        1-D ``(frames,)`` mono or 2-D ``(frames, channels)`` audio, like
        ``soundfile.read`` returns — not librosa's channels-first
        ``(channels, samples)``. dtype must be ``float32`` or ``float64``;
        engines compute internally in ``float32`` and the returned array
        matches the input's dtype.
    sample_rate : int
        Sample rate in Hz, > 0.
    duration_ratio : float, optional
        Output length / input length. ``2.0`` makes the result twice as
        long (slower); ``0.5`` makes it half as long (faster). Required —
        there is no default, since silently picking one would hide a
        caller's forgotten argument. This is *not* the same convention as
        pyrubberband/librosa's ``rate`` (a speed factor, inverted) or
        Rubber Band's own ``time_ratio`` (already output/input, same as
        this parameter).
    backend : str, default "rubberband"
        Registered backend name; see ``pytimestretch.available_backends()``
        for which are usable in this environment.

    Returns
    -------
    numpy.ndarray
        Same ``ndim`` and channel count as ``audio``, same dtype as
        ``audio``, with exactly ``floor(frames * duration_ratio + 0.5)``
        frames.

    Raises
    ------
    TypeError
        An unrecognized keyword argument was passed. If it's a known
        pyrubberband/librosa/Rubber Band alias (``rate``, ``speed``,
        ``stretch_factor``, ``time_ratio``, ``tempo``, ``factor``), the
        message explains the ``duration_ratio`` convention and, when
        possible, shows the converted value.
    InvalidAudioError
        ``audio``, ``sample_rate``, or ``duration_ratio`` is invalid or
        missing, including a channels-first 2-D array (> 64 "channels").
    UnknownBackendError, BackendUnavailableError
        ``backend`` doesn't name a registered backend, or its native module
        failed to import.
    EngineError
        The backend raised, or returned output violating the native
        contract.

    Examples
    --------
    Make a stereo file 1.5x longer/slower:

    >>> import soundfile as sf
    >>> audio, sr = sf.read("song.wav")  # (frames, channels)
    >>> longer = time_stretch(audio, sr, duration_ratio=1.5)  # doctest: +SKIP

    Fit audio to an exact target length:

    >>> target_frames = 132_300
    >>> fitted = time_stretch(
    ...     audio, sr, duration_ratio=target_frames / len(audio)
    ... )  # doctest: +SKIP

    librosa loads channels-first ``(channels, samples)``; transpose in and
    back out:

    >>> import librosa
    >>> y, sr = librosa.load("song.wav", mono=False)
    >>> stretched = time_stretch(y.T, sr, duration_ratio=0.8).T  # doctest: +SKIP
    """
    _reject_unexpected_kwargs(unexpected)

    frames, _ = _check_audio(audio)
    sample_rate = _check_sample_rate(sample_rate)
    duration_ratio = _resolve_duration_ratio(duration_ratio)
    target_frames_ = _target_frames(frames, duration_ratio)

    stretch_fn = load_backend(backend)

    # np.array(..., copy=True) is required rather than ascontiguousarray:
    # a Fortran-order (frames, channels) input transposes into an
    # already-C-contiguous view of the *same* memory, which
    # ascontiguousarray would return unchanged, aliasing the caller's array.
    buffer = np.array(
        audio.reshape(frames, -1).T, dtype=np.float32, copy=True, order="C"
    )

    try:
        result = stretch_fn(buffer, sample_rate, duration_ratio, target_frames_)
    except PytimestretchError:
        raise
    except Exception as exc:
        raise EngineError(f"{backend} engine failed: {exc}") from exc

    channels = buffer.shape[0]
    expected_shape = (channels, target_frames_)
    if (
        not isinstance(result, np.ndarray)
        or result.dtype != np.float32
        or result.shape != expected_shape
    ):
        got_shape = getattr(result, "shape", None)
        got_dtype = getattr(result, "dtype", None)
        raise EngineError(
            f"{backend} engine returned an invalid result: expected ndarray "
            f"float32 shape {expected_shape}, got dtype={got_dtype} "
            f"shape={got_shape}"
        )

    output = np.ascontiguousarray(result.T, dtype=audio.dtype)
    if audio.ndim == 1:
        output = output.reshape(target_frames_)
    return output
