"""Private validation helpers and constants for the public contract.

Owns ``audio``/``sample_rate``/``duration_ratio``/``semitones``/``formants``/
``quality``/``markers`` validation, the frame-count and pitch-scale math, and
the teaching-error machinery for legacy pyrubberband/librosa keyword aliases
(``rate``, ``speed``, ``n_steps``, ``time_map``, ``rbargs``, ...). Every
raise here happens before ``stretch._render`` resolves a backend, so an
unavailable or capability-limited backend never masks a bad call. Each
public function in ``stretch.py`` passes its own accepted-keyword tuple to
``_reject_unexpected_kwargs`` so an unknown-keyword message lists only that
function's own vocabulary.

Reads: .errors.
"""

from __future__ import annotations

import math
import numbers

import numpy as np

from .errors import InvalidAudioError

# 2-D input past this many "channels" is almost certainly a channels-first
# array (e.g. librosa's ``(channels, samples)``) rather than genuine audio.
MAX_CHANNELS = 64

# No minimum marker spacing is enforced yet -- steps 3/4 pin this from
# measured engine placement tolerances and enforce it with an error naming
# the constant. Until then, any strictly-increasing spacing is accepted.
MIN_MARKER_SPACING_FRAMES = 1

# Keyword names from pyrubberband/librosa's ``time_stretch(y, sr, rate=...)``
# family whose *sign convention is inverted* relative to ours: their value
# is a speed factor (>1 = faster/shorter), ours is a duration ratio (>1 =
# longer/slower). ``time_ratio`` is Rubber Band's own C++ option name, which
# already means output/input, so it maps straight through instead of
# inverting.
_SPEED_ALIASES = ("rate", "speed", "stretch_factor", "time_ratio", "tempo", "factor")

_DURATION_RATIO_EXPLAINER = (
    "pytimestretch uses duration_ratio = output length / input length "
    "(>1 = longer/slower, <1 = shorter/faster), not a speed factor"
)

_MARKERS_EXAMPLE = (
    "markers must be a sequence of (source_frame, output_frame) integer "
    "pairs, e.g. [(0, 0), (22050, 20000), (44100, 40000)]: the first pair "
    "must be (0, 0), the last pair's source frame must equal len(audio), "
    "and both columns must strictly increase"
)

# Accepted keywords per public function, for the generic unexpected-keyword
# message (teaching aliases are checked first and never fall through here).
TIME_STRETCH_KEYWORDS = ("duration_ratio", "semitones", "formants", "quality", "backend")
PITCH_SHIFT_KEYWORDS = ("semitones", "formants", "quality", "backend")
TIME_WARP_KEYWORDS = ("markers", "semitones", "formants", "quality", "backend")

FORMANTS_CHOICES = ("shift", "preserve")
QUALITY_CHOICES = ("high", "balanced", "fast")


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


def _n_steps_note(value: object) -> str:
    """Best-effort teaching note for ``n_steps=``'s value: same meaning as
    ``semitones=`` (positive = up), so it passes through unconverted."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return ""
    value = float(value)
    if not math.isfinite(value):
        return ""
    return f"; semitones={value!r}"


def _reject_unexpected_kwargs(
    func_name: str,
    unexpected: dict[str, object],
    accepted_keywords: tuple[str, ...],
) -> None:
    """Raise ``TypeError`` for any leftover keyword argument.

    Must run before any other validation: an alias like ``rate=2.0`` or
    ``n_steps=7`` is a caller mistake about *which* keyword to use, and
    should be diagnosed as that, not masked by a later "required" error.
    """
    if not unexpected:
        return

    key, value = next(iter(unexpected.items()))

    if key in _SPEED_ALIASES:
        note = _alias_conversion_note(key, value)
        message = f"{func_name}() got an unexpected keyword argument {key!r}: "
        message += _DURATION_RATIO_EXPLAINER
        if note:
            message += f". {note}"
        raise TypeError(message)

    if key == "n_steps":
        raise TypeError(
            f"{func_name}() got an unexpected keyword argument 'n_steps': "
            "pytimestretch uses semitones= (same meaning: positive = up)"
            + _n_steps_note(value)
        )

    if key == "time_map":
        raise TypeError(
            f"{func_name}() got an unexpected keyword argument 'time_map': "
            "pytimestretch uses markers= with the same (source, target) "
            "frame pairs, which must start with (0, 0), end at "
            "(len(audio), output_length), and strictly increase"
        )

    if key == "rbargs":
        raise TypeError(
            f"{func_name}() got an unexpected keyword argument 'rbargs': "
            "pytimestretch has no raw Rubber Band flags; use quality= "
            '("high"/"balanced"/"fast"), formants= ("shift"/"preserve"), '
            "and semitones= instead"
        )

    accepted = ", ".join(repr(k) for k in accepted_keywords)
    raise TypeError(
        f"{func_name}() got an unexpected keyword argument {key!r}; "
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


def _check_semitones(semitones: object, *, required: bool = False) -> float:
    """Validate ``semitones`` and return it as a plain ``float``.

    ``None`` means "not given": for ``pitch_shift`` (``required=True``) that
    is an error, since it has no meaningful default; for ``time_stretch``/
    ``time_warp`` it resolves to ``0.0`` (no pitch change).
    """
    if semitones is None:
        if required:
            raise InvalidAudioError(
                "semitones is required for pitch_shift(): pitch shift "
                "amount in semitones, positive = up, negative = down, "
                "e.g. semitones=7.0"
            )
        return 0.0
    if isinstance(semitones, bool) or not isinstance(semitones, numbers.Real):
        raise InvalidAudioError(
            f"semitones must be a real number, got {type(semitones)!r}"
        )
    semitones = float(semitones)
    if not math.isfinite(semitones):
        raise InvalidAudioError(f"semitones must be finite, got {semitones}")
    return semitones


def _pitch_scale(semitones: float) -> float:
    """Convert a semitone offset to a linear frequency ratio."""
    return 2.0 ** (semitones / 12.0)


def _check_formants(formants: object) -> bool:
    """Validate ``formants`` and return the ``preserve_formants`` bool."""
    if formants not in FORMANTS_CHOICES:
        raise InvalidAudioError(
            f"formants must be one of {FORMANTS_CHOICES!r}, got {formants!r}"
        )
    return formants == "preserve"


def _check_quality(quality: object) -> str:
    """Validate ``quality`` and return it unchanged."""
    if quality not in QUALITY_CHOICES:
        raise InvalidAudioError(
            f"quality must be one of {QUALITY_CHOICES!r}, got {quality!r}"
        )
    return quality


def _check_markers(markers: object, frames: int) -> np.ndarray:
    """Validate ``markers`` against ``frames`` (``len(audio)``) and return a
    fresh C-contiguous ``int64`` ``(K, 2)`` array.

    Accepts a list/tuple of ``(source, output)`` pairs or an array-like of
    shape ``(K, 2)``. Values must be Python ``int`` or numpy integer dtype
    -- floats are rejected even when integral-valued (with a hint to
    ``np.round(...).astype(int)``), and bools are rejected. The first row
    must be exactly ``(0, 0)``, the last row's source must equal ``frames``
    with an output of at least 1, ``K >= 2``, and both columns must
    strictly increase.
    """
    if markers is None:
        raise InvalidAudioError(
            f"markers is required for time_warp(): {_MARKERS_EXAMPLE}"
        )

    try:
        markers_arr = np.asarray(markers)
    except Exception as exc:
        raise InvalidAudioError(
            f"markers must be array-like: {exc}. {_MARKERS_EXAMPLE}"
        ) from exc

    if markers_arr.ndim != 2 or markers_arr.shape[1] != 2:
        raise InvalidAudioError(
            f"markers must have shape (K, 2), got shape {markers_arr.shape}. "
            f"{_MARKERS_EXAMPLE}"
        )

    k = markers_arr.shape[0]
    if k < 2:
        raise InvalidAudioError(f"markers must have at least 2 rows, got {k}")

    if markers_arr.dtype == np.bool_:
        raise InvalidAudioError(
            "markers values must be integers, not bool. " + _MARKERS_EXAMPLE
        )
    if np.issubdtype(markers_arr.dtype, np.floating):
        raise InvalidAudioError(
            "markers values must be integers, not float (even when "
            "integral-valued); use np.round(markers).astype(int). "
            + _MARKERS_EXAMPLE
        )
    if not np.issubdtype(markers_arr.dtype, np.integer):
        raise InvalidAudioError(
            f"markers must contain only integers, got dtype "
            f"{markers_arr.dtype}. {_MARKERS_EXAMPLE}"
        )

    first_source = int(markers_arr[0, 0])
    first_target = int(markers_arr[0, 1])
    if first_source != 0 or first_target != 0:
        raise InvalidAudioError(
            f"markers must start at (0, 0), got ({first_source}, {first_target})"
        )

    last_source = int(markers_arr[-1, 0])
    last_target = int(markers_arr[-1, 1])
    if last_source != frames:
        raise InvalidAudioError(
            f"markers[-1][0] must equal len(audio) ({frames}), got {last_source}"
        )
    if last_target < 1:
        raise InvalidAudioError(
            f"markers[-1][1] (output length) must be >= 1, got {last_target}"
        )

    sources = markers_arr[:, 0].astype(np.int64)
    targets = markers_arr[:, 1].astype(np.int64)
    bad_source = np.flatnonzero(np.diff(sources) <= 0)
    bad_target = np.flatnonzero(np.diff(targets) <= 0)
    if bad_source.size or bad_target.size:
        first_bad = min(
            int(bad_source[0]) if bad_source.size else k,
            int(bad_target[0]) if bad_target.size else k,
        )
        row = first_bad + 1
        raise InvalidAudioError(
            "markers must strictly increase in both columns: row "
            f"{row} does not have a greater source or output frame than "
            f"row {row - 1} (equal source or output frames are not allowed)"
        )

    return np.ascontiguousarray(markers_arr, dtype=np.int64)
