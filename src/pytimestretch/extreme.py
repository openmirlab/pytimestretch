"""Creative extreme stretching through libpaulstretch.

This operation deliberately keeps the native stretch factor and complete
FFT-sized output chunks. Its length is approximate; the exact-frame
``time_stretch`` contract and its backend registry remain separate.

Reads: ._paulstretch, ._validation, .errors.
"""

from __future__ import annotations

import math
import numbers

import numpy as np

from ._validation import _check_audio, _check_sample_rate
from .errors import EngineError, InvalidAudioError

__all__ = ["extreme_stretch"]

_FFT_SIZE = 4096
_MIN_INPUT_FRAMES = 20 * _FFT_SIZE


def extreme_stretch(
    audio: np.ndarray,
    sample_rate: int,
    *,
    duration_ratio: float,
) -> np.ndarray:
    """Turn mono or stereo audio into a long spectral texture.

    ``duration_ratio`` is passed directly to libpaulstretch (``8.0`` asks
    for an eightfold stretch). The renderer emits complete 4,096-frame
    chunks, so the returned frame count is **approximate**, especially near
    the minimum input length. It is never padded, trimmed, or internally
    re-ratioed to force an exact duration. Use :func:`time_stretch` when an
    exact output frame count is required.

    The input must be a finite ``float32`` or ``float64`` NumPy array with
    shape ``(frames,)`` or ``(frames, channels)`` and one or two channels.
    At least 81,920 frames are required: shorter clips are dominated by the
    engine's fixed startup window and can miss the requested ratio badly.
    ``duration_ratio`` must be finite and at least 1.0. The result is a new,
    C-contiguous array matching the input's dtype and channel layout;
    calculation inside the engine uses ``float32``. Input is not changed.
    Output is not peak-normalized or clipped.
    PaulStretch randomizes spectral phase: repeated calls on the same input
    produce different waveforms, though their frame counts remain the same.
    """
    frames, channels = _check_audio(audio)
    sample_rate = _check_sample_rate(sample_rate)
    if frames < _MIN_INPUT_FRAMES:
        raise InvalidAudioError(
            "extreme_stretch requires at least 81920 input frames "
            "(20 FFT chunks); shorter clips miss the requested duration ratio badly"
        )
    if channels is not None and channels > 2:
        raise InvalidAudioError("extreme_stretch supports only mono or stereo audio")
    if isinstance(duration_ratio, bool) or not isinstance(duration_ratio, numbers.Real):
        raise InvalidAudioError("duration_ratio must be a real number >= 1")
    ratio = float(duration_ratio)
    if not math.isfinite(ratio) or ratio < 1.0 or ratio > np.finfo(np.float32).max:
        raise InvalidAudioError("duration_ratio must be finite and >= 1")

    buffer = np.array(
        audio.reshape(frames, -1).T, dtype=np.float32, copy=True, order="C"
    )
    try:
        from . import _paulstretch

        result = _paulstretch.render(buffer, sample_rate, ratio)
    except Exception as exc:
        raise EngineError(f"libpaulstretch engine failed: {exc}") from exc

    channel_count = buffer.shape[0]
    if (
        not isinstance(result, np.ndarray)
        or result.dtype != np.float32
        or result.ndim != 2
        or result.shape[0] != channel_count
        or result.shape[1] < 1
        or not np.isfinite(result).all()
    ):
        raise EngineError("libpaulstretch engine returned invalid audio")

    output = np.ascontiguousarray(result.T, dtype=audio.dtype)
    if audio.ndim == 1:
        output = output.reshape(result.shape[1])
    return output
