"""Backend-neutral public entry points: time_stretch, pitch_shift, time_warp.

All three validate their own parameters (audio/sample_rate plus whichever of
duration_ratio/semitones/formants/quality/markers apply) via ``_validation``,
build a native-contract-v2 marker array, and funnel into the single private
``_render`` helper, which is the sole owner of the buffer copy into the
native ``(channels, frames)`` float32 layout, backend resolution and its
quality-capability check, dispatch, ``EngineError`` wrapping, result checks,
and conversion back to the caller's original layout/dtype. Backend selection
and native-module loading are owned by ``_backends``; validation itself
(audio/sample-rate/ratio/semitones/formants/quality/marker checks, teaching-
error text) lives in ``_validation``. Validation errors are always raised
before a backend is resolved, so an unavailable or capability-limited
backend never masks a bad call.

Reads: ._backends, ._validation, .errors.
"""

from __future__ import annotations

import numpy as np

from ._backends import load_backend
from ._validation import (
    PITCH_SHIFT_KEYWORDS,
    TIME_STRETCH_KEYWORDS,
    TIME_WARP_KEYWORDS,
    _check_audio,
    _check_formants,
    _check_markers,
    _check_quality,
    _check_sample_rate,
    _check_semitones,
    _pitch_scale,
    _reject_unexpected_kwargs,
    _resolve_duration_ratio,
    _target_frames,
)
from .errors import EngineError, PytimestretchError, UnsupportedOptionError

__all__ = ["pitch_shift", "time_stretch", "time_warp"]


def _render(
    audio: np.ndarray,
    sample_rate: int,
    markers: np.ndarray,
    semitones: float,
    preserve_formants: bool,
    quality: str,
    backend: str,
) -> np.ndarray:
    """Shared engine dispatch for time_stretch/pitch_shift/time_warp.

    ``markers`` must already be a validated int64 ``(K, 2)`` array whose
    first row is ``(0, 0)`` and whose last row's source frame equals
    ``len(audio)``; each public function builds it (``time_stretch`` from
    ``duration_ratio``, ``pitch_shift`` as the identity-length two-marker
    case, ``time_warp`` from the caller's own markers) and validates
    ``semitones``/``formants``/``quality`` before calling this. Owns: the
    backend resolution and quality-capability check (``UnsupportedOptionError``
    before any native call), the buffer copy into native contract v2's
    channels-first float32 layout (always a fresh copy, never aliasing the
    caller's array), dispatch, ``EngineError`` wrapping, result shape/dtype
    checks, and conversion back to the caller's original layout/dtype.
    """
    frames = audio.shape[0]
    target_frames = int(markers[-1, 1])
    pitch_scale = _pitch_scale(semitones)

    resolved = load_backend(backend)
    if quality not in resolved.supported_quality:
        supported = ", ".join(repr(q) for q in resolved.supported_quality)
        raise UnsupportedOptionError(
            f"backend {backend!r} does not support quality={quality!r}; "
            f"supported qualities for {backend!r} are: {supported}"
        )

    # np.array(..., copy=True) is required rather than ascontiguousarray:
    # a Fortran-order (frames, channels) input transposes into an
    # already-C-contiguous view of the *same* memory, which
    # ascontiguousarray would return unchanged, aliasing the caller's array.
    buffer = np.array(
        audio.reshape(frames, -1).T, dtype=np.float32, copy=True, order="C"
    )

    try:
        result = resolved.render(
            buffer, sample_rate, markers, pitch_scale, preserve_formants, quality
        )
    except PytimestretchError:
        raise
    except Exception as exc:
        raise EngineError(f"{backend} engine failed: {exc}") from exc

    channels = buffer.shape[0]
    expected_shape = (channels, target_frames)
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
        output = output.reshape(target_frames)
    return output


def time_stretch(
    audio: np.ndarray,
    sample_rate: int,
    *,
    duration_ratio: float | None = None,
    semitones: float = 0.0,
    formants: str = "shift",
    quality: str = "high",
    backend: str = "rubberband",
    **unexpected: object,
) -> np.ndarray:
    """Time-stretch ``audio`` to a new duration, with optional pitch shift.

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
    semitones : float, default 0.0
        Pitch shift in semitones, positive = up, negative = down, applied
        independently of the duration change.
    formants : {"shift", "preserve"}, default "shift"
        ``"shift"`` moves the spectral envelope with the pitch (default,
        both engines' natural behavior); ``"preserve"`` keeps it in place,
        useful for voices so a pitched-up singer doesn't sound like a
        chipmunk.
    quality : {"high", "balanced", "fast"}, default "high"
        Speed/quality preset. Not every backend supports every value; an
        unsupported combination raises ``UnsupportedOptionError`` rather
        than silently aliasing to a different quality.
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
        ``stretch_factor``, ``time_ratio``, ``tempo``, ``factor``,
        ``n_steps``, ``time_map``, ``rbargs``), the message explains the
        pytimestretch equivalent and, when possible, shows the converted
        value.
    InvalidAudioError
        ``audio``, ``sample_rate``, ``duration_ratio``, ``semitones``,
        ``formants``, or ``quality`` is invalid or missing, including a
        channels-first 2-D array (> 64 "channels").
    UnknownBackendError, BackendUnavailableError
        ``backend`` doesn't name a registered backend, or its native module
        failed to import.
    UnsupportedOptionError
        The resolved backend cannot honor the requested ``quality``.
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
    _reject_unexpected_kwargs("time_stretch", unexpected, TIME_STRETCH_KEYWORDS)

    frames, _ = _check_audio(audio)
    sample_rate = _check_sample_rate(sample_rate)
    duration_ratio = _resolve_duration_ratio(duration_ratio)
    target_frames = _target_frames(frames, duration_ratio)
    semitones = _check_semitones(semitones)
    preserve_formants = _check_formants(formants)
    quality = _check_quality(quality)

    markers = np.array([[0, 0], [frames, target_frames]], dtype=np.int64)
    return _render(
        audio, sample_rate, markers, semitones, preserve_formants, quality, backend
    )


def pitch_shift(
    audio: np.ndarray,
    sample_rate: int,
    *,
    semitones: float | None = None,
    formants: str = "shift",
    quality: str = "high",
    backend: str = "rubberband",
    **unexpected: object,
) -> np.ndarray:
    """Pitch-shift ``audio`` without changing its duration.

    Equivalent to ``time_stretch`` with ``duration_ratio=1.0``: the output
    has the same length as ``audio``, only the pitch changes.

    Parameters
    ----------
    audio : numpy.ndarray
        1-D ``(frames,)`` mono or 2-D ``(frames, channels)`` audio; see
        ``time_stretch`` for the layout and dtype contract.
    sample_rate : int
        Sample rate in Hz, > 0.
    semitones : float
        Pitch shift in semitones, positive = up, negative = down. Required
        — there is no default, since pitch_shift has no meaningful "do
        nothing" call.
    formants : {"shift", "preserve"}, default "shift"
        See ``time_stretch``.
    quality : {"high", "balanced", "fast"}, default "high"
        See ``time_stretch``.
    backend : str, default "rubberband"
        See ``time_stretch``.

    Returns
    -------
    numpy.ndarray
        Same ``ndim``, channel count, dtype, and frame count as ``audio``.

    Raises
    ------
    TypeError
        An unrecognized keyword argument was passed; see ``time_stretch``.
    InvalidAudioError
        ``audio``, ``sample_rate``, ``semitones`` (including a missing
        value), ``formants``, or ``quality`` is invalid.
    UnknownBackendError, BackendUnavailableError
        See ``time_stretch``.
    UnsupportedOptionError
        The resolved backend cannot honor the requested ``quality``.
    EngineError
        See ``time_stretch``.

    Examples
    --------
    Shift a loop up a perfect fifth (+7 semitones):

    >>> import soundfile as sf
    >>> audio, sr = sf.read("loop.wav")
    >>> shifted = pitch_shift(audio, sr, semitones=7.0)  # doctest: +SKIP

    Shift a vocal down a minor third while keeping its formants (so it
    doesn't sound like a different speaker):

    >>> alto = pitch_shift(
    ...     audio, sr, semitones=-3.0, formants="preserve"
    ... )  # doctest: +SKIP
    """
    _reject_unexpected_kwargs("pitch_shift", unexpected, PITCH_SHIFT_KEYWORDS)

    frames, _ = _check_audio(audio)
    sample_rate = _check_sample_rate(sample_rate)
    semitones = _check_semitones(semitones, required=True)
    preserve_formants = _check_formants(formants)
    quality = _check_quality(quality)

    markers = np.array([[0, 0], [frames, frames]], dtype=np.int64)
    return _render(
        audio, sample_rate, markers, semitones, preserve_formants, quality, backend
    )


def time_warp(
    audio: np.ndarray,
    sample_rate: int,
    *,
    markers: object = None,
    semitones: float = 0.0,
    formants: str = "shift",
    quality: str = "high",
    backend: str = "rubberband",
    **unexpected: object,
) -> np.ndarray:
    """Warp ``audio`` to align source frames to target frames, with optional
    pitch shift.

    Unlike ``time_stretch``'s single global ratio, ``time_warp`` stretches
    non-uniformly according to ``markers``: a sequence of
    ``(source_frame, output_frame)`` pairs that pin specific input
    positions to specific output positions (e.g. aligning transients to a
    beat grid).

    Parameters
    ----------
    audio : numpy.ndarray
        1-D ``(frames,)`` mono or 2-D ``(frames, channels)`` audio; see
        ``time_stretch`` for the layout and dtype contract.
    sample_rate : int
        Sample rate in Hz, > 0.
    markers : sequence or numpy.ndarray
        ``(source_frame, output_frame)`` integer pairs (Python ``int`` or
        numpy integer dtype — floats are rejected even when
        integral-valued). Required. The first pair must be exactly
        ``(0, 0)``; the last pair's source frame must equal ``len(audio)``
        and its output frame is the output length; both columns must
        strictly increase; at least 2 pairs. Accepts a list/tuple of pairs
        or an array-like of shape ``(K, 2)``.
    semitones : float, default 0.0
        See ``time_stretch``.
    formants : {"shift", "preserve"}, default "shift"
        See ``time_stretch``.
    quality : {"high", "balanced", "fast"}, default "high"
        See ``time_stretch``.
    backend : str, default "rubberband"
        See ``time_stretch``.

    Returns
    -------
    numpy.ndarray
        Same ``ndim`` and channel count as ``audio``, same dtype as
        ``audio``, with exactly ``markers[-1][1]`` frames.

    Raises
    ------
    TypeError
        An unrecognized keyword argument was passed; see ``time_stretch``.
    InvalidAudioError
        ``audio``, ``sample_rate``, ``markers`` (including a missing or
        malformed value), ``semitones``, ``formants``, or ``quality`` is
        invalid.
    UnknownBackendError, BackendUnavailableError
        See ``time_stretch``.
    UnsupportedOptionError
        The resolved backend cannot honor the requested ``quality``.
    EngineError
        See ``time_stretch``.

    Examples
    --------
    Align a transient at 0.52 s to beat 2 of a 120 BPM grid (beat 2 lands
    at 0.5 s, one beat = 0.5 s at 120 BPM):

    >>> import soundfile as sf
    >>> audio, sr = sf.read("loop.wav")
    >>> transient_frame = int(round(0.52 * sr))
    >>> beat_2_frame = int(round(0.5 * sr))
    >>> warped = time_warp(
    ...     audio,
    ...     sr,
    ...     markers=[(0, 0), (transient_frame, beat_2_frame), (len(audio), len(audio))],
    ... )  # doctest: +SKIP
    """
    _reject_unexpected_kwargs("time_warp", unexpected, TIME_WARP_KEYWORDS)

    frames, _ = _check_audio(audio)
    sample_rate = _check_sample_rate(sample_rate)
    markers_array = _check_markers(markers, frames)
    semitones = _check_semitones(semitones)
    preserve_formants = _check_formants(formants)
    quality = _check_quality(quality)

    return _render(
        audio,
        sample_rate,
        markers_array,
        semitones,
        preserve_formants,
        quality,
        backend,
    )
