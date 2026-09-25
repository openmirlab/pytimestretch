"""Offline position-curve rendering through Bungee Basic.

The output-first curve may hold or reverse the source playhead. This is a
separate creative contract from the forward-only ``time_warp`` markers and
the shared exact-length backend registry.

Reads: ._bungee, ._validation, .errors.
"""

from __future__ import annotations

import numpy as np

from ._validation import (
    _check_audio,
    _check_control_points,
    _check_sample_rate,
    _check_semitones,
    _pitch_scale,
)
from .errors import EngineError, InvalidAudioError

__all__ = ["time_scrub"]


def time_scrub(
    audio: np.ndarray,
    sample_rate: int,
    *,
    control_points: object,
    semitones: float = 0.0,
) -> np.ndarray:
    """Render a continuous source-position curve, including holds and reverse.

    ``control_points`` contains ``(output_frame, source_frame)`` pairs. Output
    frames are strictly increasing integer boundaries starting at zero; the
    last one is the exact output length. Source frames may increase, stay
    still, or decrease, and may be fractional within ``[0, len(audio)]``.
    Positions between points are linearly interpolated. For example,
    ``[(0, 0), (44100, 44100), (88200, 44100)]`` plays one second forward
    and holds its final position for another second at 44.1 kHz.

    Input is finite float32/float64 NumPy audio, mono or stereo, in frame-major
    layout. The returned array keeps its dtype and layout and has exactly the
    requested frame count; the input is unchanged. Bungee Basic processes
    internally in float32, has no formant-preservation control, and uses a
    granular window, so sharp transients and abrupt turns may be smeared.
    ``semitones`` changes pitch globally and must be within two octaves.
    """
    frames, channels = _check_audio(audio)
    sample_rate = _check_sample_rate(sample_rate)
    if channels is not None and channels > 2:
        raise InvalidAudioError("time_scrub supports only mono or stereo audio")
    if not 8_000 <= sample_rate <= 192_000:
        raise InvalidAudioError("time_scrub sample_rate must be within 8000..192000 Hz")
    points = _check_control_points(control_points, frames)
    semitones = _check_semitones(semitones)
    if not -24.0 <= semitones <= 24.0:
        raise InvalidAudioError("time_scrub semitones must be within -24..24")
    pitch_scale = _pitch_scale(semitones)
    if np.any(np.abs(audio) > np.finfo(np.float32).max):
        raise InvalidAudioError("time_scrub audio values must fit in float32")

    buffer = np.array(
        audio.reshape(frames, -1).T, dtype=np.float32, copy=True, order="C"
    )
    try:
        from . import _bungee

        result = _bungee.render(buffer, sample_rate, points, pitch_scale)
    except Exception as exc:
        raise EngineError(f"bungee engine failed: {exc}") from exc

    target_frames = int(points[-1, 0])
    expected_shape = (buffer.shape[0], target_frames)
    if (
        not isinstance(result, np.ndarray)
        or result.dtype != np.float32
        or result.shape != expected_shape
        or not np.isfinite(result).all()
    ):
        raise EngineError("bungee engine returned invalid audio")

    output = np.ascontiguousarray(result.T, dtype=audio.dtype)
    if audio.ndim == 1:
        output = output.reshape(target_frames)
    return output
