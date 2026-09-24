"""Backend-neutral time-stretch entry point.

``time_stretch`` is the sole owner of the public contract: it validates
``audio``/``sample_rate``/``duration_ratio``, computes the exact output frame
count, converts the input into the native contract's channels-first float32
layout (always a fresh copy, never aliasing the caller's array), dispatches
to the resolved backend, and checks the backend's result before converting
it back to the caller's original layout and dtype. Backend selection and
native-module loading are owned by ``_backends``; validation itself (audio/
sample-rate/ratio checks, frame-count math, teaching-error text) lives in
``_validation``. Validation errors
are always raised before a backend is resolved, so an unavailable backend
never masks a bad call.

Reads: ._backends, ._validation, .errors.
"""

from __future__ import annotations

import numpy as np

from ._backends import load_backend
from ._validation import (
    _check_audio,
    _check_sample_rate,
    _reject_unexpected_kwargs,
    _resolve_duration_ratio,
    _target_frames,
)
from .errors import EngineError, PytimestretchError

__all__ = ["time_stretch"]


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

    render_fn = load_backend(backend)

    # np.array(..., copy=True) is required rather than ascontiguousarray:
    # a Fortran-order (frames, channels) input transposes into an
    # already-C-contiguous view of the *same* memory, which
    # ascontiguousarray would return unchanged, aliasing the caller's array.
    buffer = np.array(
        audio.reshape(frames, -1).T, dtype=np.float32, copy=True, order="C"
    )

    # Native contract v2: a plain time_stretch is the two-marker case, no
    # pitch/formant/quality change. pitch_shift/time_warp (step 2) build
    # richer marker arrays and non-default pitch_scale/preserve_formants/
    # quality through this same render() call.
    markers = np.array([[0, 0], [frames, target_frames_]], dtype=np.int64)

    try:
        result = render_fn(buffer, sample_rate, markers, 1.0, False, "high")
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
