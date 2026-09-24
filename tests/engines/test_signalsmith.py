"""Signalsmith Stretch engine-specific measurements, pinned with margins.

Unlike tests/contract/ (test_output_contract.py, test_markers.py, etc. --
engine-independent, runs on every backend), these assertions are
Signalsmith-specific: numeric tolerances
derived from this step's own disposable measurement script (run against
this build; see the step 4 report for the full side-by-side tables against
Rubber Band). Margins here are deliberately generous relative to the measured worst case
so a small future build/config change doesn't flap the suite. Calls target
native contract v2's ``render(buffer, sample_rate, markers, pitch_scale,
preserve_formants, quality)`` in full (step 4 implements pitch, formants,
quality presets via `presetDefault`/`presetCheaper`, and marker warp via a
scheduled process()/flush() stream).

Below the original step-1/2/4-plain checks (impulse placement via
``.exact()``, silence, crosstalk, determinism, engine_info/
SUPPORTED_QUALITY), the newer sections pin: pitch accuracy per quality, the
one formant (2600 Hz) whose envelope estimate proved stable (same method as
Rubber Band's own formant test), marker placement (steady ratio and the
humanized-to-grid case) at 100/250 ms spacing, speed ordering (balanced
faster than high), and determinism of ``time_warp``.

Reads: pytimestretch._signalsmith.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import pytimestretch
from pytimestretch import _signalsmith as ss

SR = 44100


def target_frames(frames: int, ratio: float) -> int:
    return math.floor(frames * ratio + 0.5)


def two_markers(frames: int, tgt: int) -> np.ndarray:
    return np.array([[0, 0], [frames, tgt]], dtype=np.int64)


def render(buf: np.ndarray, sr: int, markers: np.ndarray) -> np.ndarray:
    return ss.render(buf, sr, markers, 1.0, False, "high")


def impulse_at(t_sec: float, total_sec: float = 4.0, sr: int = SR) -> np.ndarray:
    frames = round(total_sec * sr)
    sig = np.zeros(frames, dtype=np.float32)
    sig[round(t_sec * sr)] = 1.0
    return sig


# Measured worst-case |offset| (step 4 measurement script, see the step 4
# report): well under 1 ms at both ratios (0.5's click train measured exactly
# 0.0 ms; 1.5's measured ~0.02 ms). The .exact() whole-buffer method has no
# streaming block-loop drift the way Rubber Band's two-pass offline loop
# does, so these margins are tight relative to Rubber Band's but still
# generous headroom (2 ms) over the measured worst case.
IMPULSE_TOLERANCE_MS = {1.5: 2.0, 0.5: 2.0}


@pytest.mark.parametrize("ratio", [1.5, 0.5])
@pytest.mark.parametrize("t_sec", [0.25, 1.0, 2.5])
def test_impulse_placement_within_tolerance(ratio: float, t_sec: float) -> None:
    # Regression (step 4 measurement item 5): the K == 2 .exact() path is
    # untouched by the new warp/pitch/formant/quality code, and reproduces
    # this same table.
    audio = impulse_at(t_sec)
    frames = audio.shape[0]
    tgt = target_frames(frames, ratio)
    buf = audio.reshape(1, -1).copy()

    out = render(buf, SR, two_markers(frames, tgt))

    measured_idx = int(np.argmax(np.abs(out[0])))
    expected_idx = round(t_sec * SR * ratio)
    offset_ms = abs(measured_idx - expected_idx) / SR * 1000
    assert offset_ms <= IMPULSE_TOLERANCE_MS[ratio]


def dominant_freq(x: np.ndarray, sr: int) -> float:
    n = len(x)
    window = np.hanning(n)
    spec = np.fft.rfft(x * window)
    mag = np.abs(spec)
    k = int(np.argmax(mag))
    if 0 < k < len(mag) - 1:
        alpha, beta, gamma = mag[k - 1], mag[k], mag[k + 1]
        denom = alpha - 2 * beta + gamma
        p = 0.5 * (alpha - gamma) / denom if denom != 0 else 0.0
    else:
        p = 0.0
    return float((k + p) * sr / n)


@pytest.mark.parametrize("ratio", [0.5, 1.5, 3.0])
def test_pitch_stays_within_one_percent(ratio: float) -> None:
    dur_sec = 3.0
    t = np.arange(round(dur_sec * SR), dtype=np.float64) / SR
    audio = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    frames = audio.shape[0]
    tgt = target_frames(frames, ratio)
    buf = audio.reshape(1, -1).copy()

    out = render(buf, SR, two_markers(frames, tgt))[0]

    out_dur = tgt / SR
    i0 = max(0, round((out_dur / 2 - 0.5) * SR))
    i1 = min(tgt, round((out_dur / 2 + 0.5) * SR))
    freq = dominant_freq(out[i0:i1], SR)

    assert abs(freq - 440.0) / 440.0 < 0.01


def test_silence_in_stays_silent() -> None:
    ratio = 1.5
    audio = np.zeros(SR, dtype=np.float32)
    tgt = target_frames(SR, ratio)
    buf = audio.reshape(1, -1).copy()

    out = render(buf, SR, two_markers(SR, tgt))

    # Measured (step 4): bit-exact zero, not just below a threshold.
    assert np.abs(out).max() < 1e-6


def test_stereo_crosstalk_stays_below_measured_bound() -> None:
    # Measured (step 4): a silent left channel against full-scale noise on
    # the right measured bitwise-exact 0.0 crosstalk, same as Rubber Band's
    # OptionChannelsApart. -80 dBFS is a generous bound around that, not a
    # tight pin.
    ratio = 1.5
    rng = np.random.default_rng(42)
    left = np.zeros(SR, dtype=np.float32)
    right = rng.standard_normal(SR).astype(np.float32)
    buf = np.stack([left, right], axis=0).copy()
    tgt = target_frames(SR, ratio)

    out = render(buf, SR, two_markers(SR, tgt))

    left_peak = float(np.abs(out[0]).max())
    left_peak_dbfs = 20 * np.log10(left_peak) if left_peak > 0 else float("-inf")
    assert left_peak_dbfs < -80.0


def test_determinism_same_input_twice_bitwise_equal() -> None:
    ratio = 1.5
    rng = np.random.default_rng(11)
    audio = rng.standard_normal(SR).astype(np.float32)
    buf = audio.reshape(1, -1).copy()
    tgt = target_frames(SR, ratio)

    markers = two_markers(SR, tgt)
    out1 = render(buf.copy(), SR, markers)
    out2 = render(buf.copy(), SR, markers)

    np.testing.assert_array_equal(out1, out2)


def test_engine_info_unchanged_keys() -> None:
    info = ss.engine_info()
    assert set(info) == {
        "engine",
        "version",
        "source_revision",
        "linear_revision",
        "fft",
        "preset",
        "seed",
    }
    assert info["engine"] == "signalsmith"


# --- Edge cases: below .exact()'s own seek/pre-roll minimum ---------------
#
# native/signalsmith_module.cpp's run_signalsmith_exact() zero-pads input
# below that threshold and trims back down (see its comment); measured
# (step 4), all three cases below land back inside the padded .exact() call
# (i.e. still process real, non-silent output for the 0.25s case), stay
# finite, and are exactly target_frames long, matching the plan's edge-case
# gate.


def test_single_frame_edge_case() -> None:
    audio = np.ones(1, dtype=np.float32)
    buf = audio.reshape(1, -1).copy()
    tgt = target_frames(1, 3.0)

    out = render(buf, SR, two_markers(1, tgt))

    assert out.shape == (1, tgt)
    assert np.isfinite(out).all()


def test_ten_frame_edge_case() -> None:
    audio = np.ones(10, dtype=np.float32)
    buf = audio.reshape(1, -1).copy()
    tgt = target_frames(10, 0.5)

    out = render(buf, SR, two_markers(10, tgt))

    assert out.shape == (1, tgt)
    assert np.isfinite(out).all()


def test_short_clip_below_minimum_still_finite_and_exact_length() -> None:
    frames = round(0.25 * SR)
    audio = np.random.default_rng(0).standard_normal(frames).astype(np.float32)
    buf = audio.reshape(1, -1).copy()
    tgt = target_frames(frames, 0.25)

    out = render(buf, SR, two_markers(frames, tgt))

    assert out.shape == (1, tgt)
    assert np.isfinite(out).all()


# --- Edge cases: warp (K > 2) on very short inputs -------------------------
#
# Both below and above .exact()'s pre-roll minimum, run_signalsmith() (the
# K > 2 dispatcher) pads the buffer *and* proportionally scales every
# marker before delegating to run_signalsmith_warp(), then trims back to
# target_frames -- measured (step 4): finite, exact length, no crash, for
# both a 100-frame (well below the pre-roll requirement) and a 3000-frame
# (comparable to it) 3-marker warp.


@pytest.mark.parametrize("frames", [100, 3000])
def test_warp_k3_on_short_input_is_finite_and_exact_length(frames: int) -> None:
    audio = np.random.default_rng(3).standard_normal(frames).astype(np.float32)
    buf = audio.reshape(1, -1).copy()
    mid_src = round(frames * 0.3)
    markers = np.array(
        [[0, 0], [mid_src, round(mid_src * 1.2)], [frames, round(frames * 1.4)]],
        dtype=np.int64,
    )

    out = ss.render(buf, SR, markers, 1.0, False, "high")

    assert out.shape == (1, int(markers[-1, 1]))
    assert np.isfinite(out).all()


def test_supported_quality_names_engine_capability() -> None:
    # The capability the engine can honor: render() accepts every quality
    # SUPPORTED_QUALITY names (see
    # test_pitch_shift_accuracy_within_measured_tolerance et al. below). No
    # "fast" equivalent for Signalsmith (never had one). "fast" itself was
    # removed from pytimestretch entirely 2026-09-25 (blind listening round
    # 2), so it is rejected for every backend at validation, before
    # SUPPORTED_QUALITY is even consulted -- see
    # test_unknown_quality_string_raises_value_error.
    assert ss.SUPPORTED_QUALITY == ("high", "balanced")


def test_unknown_quality_string_raises_value_error() -> None:
    # A genuine bad call: configure_engine() in
    # native/signalsmith_module.cpp raises std::invalid_argument for
    # anything outside "high"/"balanced" (defense in depth -- the facade
    # already rejects an unknown quality via SUPPORTED_QUALITY, and rejects
    # "fast" outright at validation, before this is reached).
    audio = np.zeros(44100, dtype=np.float32)
    buf = audio.reshape(1, -1).copy()
    markers = two_markers(44100, 44100)
    with pytest.raises(ValueError):
        ss.render(buf, SR, markers, 1.0, False, "ultra")


# --- Pitch accuracy (step 4 measurement) ----------------------------------
#
# Measured worst-case |cents| error, 440 Hz sine, 3 s, semitones +7 and -5
# at duration_ratio 1.0, plus +7 at x1.5 (this file's disposable
# measurement script, see the step 4 report): high 2.64/5.34/4.01,
# balanced 2.28/-3.92/8.12. Both qualities stay within about 8 cents
# (well under a tenth of a semitone); Rubber Band's high/balanced measured
# under 1 cent, so Signalsmith is the less pitch-accurate engine here --
# reported, not hidden. Tolerances below round the measured worst case up
# with headroom.
PITCH_CENTS_TOLERANCE = {"high": 15.0, "balanced": 15.0}


@pytest.mark.parametrize("quality", ["high", "balanced"])
@pytest.mark.parametrize("semitones", [7.0, -5.0])
def test_pitch_shift_accuracy_within_measured_tolerance(
    semitones: float, quality: str
) -> None:
    dur_sec = 3.0
    t = np.arange(round(dur_sec * SR), dtype=np.float64) / SR
    audio = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    frames = audio.shape[0]
    buf = audio.reshape(1, -1).copy()
    pitch_scale = 2.0 ** (semitones / 12.0)

    out = ss.render(buf, SR, two_markers(frames, frames), pitch_scale, False, quality)[0]

    i0 = round((dur_sec / 2 - 0.5) * SR)
    i1 = round((dur_sec / 2 + 0.5) * SR)
    freq = dominant_freq(out[i0:i1], SR)
    expected = 440.0 * 2.0 ** (semitones / 12.0)
    cents = 1200.0 * math.log2(freq / expected)

    assert abs(cents) <= PITCH_CENTS_TOLERANCE[quality]


# --- Formants (step 4 measurement) ----------------------------------------
#
# Same synthetic-vowel method as Rubber Band's own formant test (impulse
# train f0=150 Hz through three 2nd-order resonators at 700/1220/2600 Hz,
# bandwidths 80/90/120 Hz, cepstral-liftered envelope estimate); only the
# 2600 Hz formant is measurable here too, for the same reason (700/1220 Hz
# harmonic spacing too coarse at f0=150 Hz -- see test_rubberband.py's
# comment for the full explanation). Measured worst-case deviation:
# "shift" 0.31%, "preserve" 1.06% -- both noticeably tighter than Rubber
# Band's own 1.43%/3.39% here. Tolerances below round the measured worst
# case up with generous headroom.
FORMANT_F0 = 150.0
FORMANT_TARGETS = (700.0, 1220.0, 2600.0)
FORMANT_BWS = (80.0, 90.0, 120.0)
FORMANT_SHIFT_TOLERANCE_PCT = 8.0
FORMANT_PRESERVE_TOLERANCE_PCT = 10.0


def _make_vowel(f0: float, formants, bws, dur: float, sr: int) -> np.ndarray:
    frames = round(dur * sr)
    imp = np.zeros(frames, dtype=np.float64)
    period = sr / f0
    n = 0
    while True:
        idx = round(n * period)
        if idx >= frames:
            break
        imp[idx] = 1.0
        n += 1
    out = np.zeros(frames, dtype=np.float64)
    for f, bw in zip(formants, bws):
        r = math.exp(-math.pi * bw / sr)
        theta = 2 * math.pi * f / sr
        c = 2 * r * math.cos(theta)
        r2 = r * r
        y = np.zeros(frames, dtype=np.float64)
        y_1 = y_2 = 0.0
        for i in range(frames):
            yi = imp[i] + c * y_1 - r2 * y_2
            y[i] = yi
            y_2, y_1 = y_1, yi
        out += y
    peak = np.max(np.abs(out))
    if peak > 0:
        out /= peak
    return out.astype(np.float32)


def _cepstral_envelope(x: np.ndarray, sr: int, f0: float, nfft: int = 8192):
    n = min(len(x), nfft)
    seg = x[:n].astype(np.float64) * np.hanning(n)
    spec = np.fft.rfft(seg, n=nfft)
    log_mag = np.log(np.abs(spec) + 1e-12)
    cep = np.fft.irfft(log_mag, n=nfft)
    cutoff = max(4, int((sr / f0) * 0.9))
    lifter = np.zeros(nfft)
    lifter[:cutoff] = 1.0
    lifter[nfft - cutoff + 1 :] = 1.0
    smooth_log_mag = np.fft.rfft(cep * lifter, n=nfft).real
    mag = np.exp(smooth_log_mag)
    freqs = np.fft.rfftfreq(nfft, d=1.0 / sr)
    return freqs, mag


def _find_peak_near(freqs, mag, center: float, window: float = 400.0):
    mask = (freqs >= center - window) & (freqs <= center + window)
    idx = np.argmax(mag[mask])
    return float(freqs[mask][idx])


@pytest.mark.parametrize("mode", ["shift", "preserve"])
def test_formant_2600hz_stays_within_measured_tolerance(mode: str) -> None:
    semitones = 5.0
    pitch_scale = 2.0 ** (semitones / 12.0)
    preserve = mode == "preserve"
    target = FORMANT_TARGETS[2]

    vowel = _make_vowel(FORMANT_F0, FORMANT_TARGETS, FORMANT_BWS, 2.0, SR)
    frames = vowel.shape[0]
    mid_lo = round(0.75 * SR)
    mid_hi = round(1.25 * SR)

    orig_freqs, orig_mag = _cepstral_envelope(vowel[mid_lo:mid_hi], SR, FORMANT_F0)
    orig_peak = _find_peak_near(orig_freqs, orig_mag, target)

    buf = vowel.reshape(1, -1).copy()
    markers = two_markers(frames, frames)
    out = ss.render(buf, SR, markers, pitch_scale, preserve, "high")[0]

    out_f0 = FORMANT_F0 * pitch_scale
    freqs, mag = _cepstral_envelope(out[mid_lo:mid_hi], SR, out_f0)
    if mode == "shift":
        expected = orig_peak * pitch_scale
        tolerance = FORMANT_SHIFT_TOLERANCE_PCT
    else:
        expected = orig_peak
        tolerance = FORMANT_PRESERVE_TOLERANCE_PCT
    measured = _find_peak_near(freqs, mag, expected)

    pct_dev = 100.0 * (measured - expected) / expected
    assert abs(pct_dev) <= tolerance


# --- Marker placement: steady ratio (step 4 measurement) -------------------
#
# Click train, markers built as a source/target grid with a fixed *output*
# spacing and a steady local ratio (1.5) -- same construction as Rubber
# Band's own steady-ratio test. Measured (100/250 ms spacing, this file's
# disposable script, after fixing the warp scheduler's front/tail
# reservation -- see native/signalsmith_module.cpp's run_signalsmith_warp()
# comment): max |offset| 0.02-0.05 ms at both spacings and both qualities,
# no clicks lost -- essentially as accurate as the K == 2 .exact() path,
# since every segment's own local ratio is preserved exactly by
# construction. Tolerances below still carry real headroom (2 ms) in case a
# future engine/build change reintroduces drift.
STEADY_TOLERANCE_MS = {"high": 2.0, "balanced": 2.0}


def _build_markers(spacing_ms: float, sr: int, ratios, n_segments: int) -> np.ndarray:
    output_spacing = max(1, round(spacing_ms / 1000 * sr))
    src = tgt = 0
    markers = [(0, 0)]
    for i in range(n_segments):
        ratio = ratios[i % len(ratios)]
        src += max(1, round(output_spacing / ratio))
        tgt += output_spacing
        markers.append((src, tgt))
    return np.array(markers, dtype=np.int64)


def _click_offsets(markers: np.ndarray, out: np.ndarray, sr: int, window_s: float = 0.02):
    window = max(1, round(window_s * sr))
    offsets = []
    missing = 0
    for i in range(1, len(markers) - 1):
        _src_f, tgt_f = markers[i]
        lo = max(0, tgt_f - window)
        hi = min(len(out), tgt_f + window)
        seg = np.abs(out[lo:hi])
        if seg.size == 0 or seg.max() < 0.05:
            missing += 1
            continue
        peak_idx = lo + int(np.argmax(seg))
        offsets.append(abs(peak_idx - tgt_f) / sr * 1000)
    return offsets, missing


@pytest.mark.parametrize("spacing_ms", [100, 250])
@pytest.mark.parametrize("quality", ["high", "balanced"])
def test_marker_placement_steady_ratio_within_tolerance(
    quality: str, spacing_ms: int
) -> None:
    n_segments = max(6, round(3000 / spacing_ms))
    markers = _build_markers(spacing_ms, SR, [1.5], n_segments)
    frames = int(markers[-1, 0])
    audio = np.zeros(frames, dtype=np.float32)
    for src_f, _tgt_f in markers[1:]:
        if src_f < frames:
            audio[src_f] = 1.0
    buf = audio.reshape(1, -1).copy()

    out = ss.render(buf, SR, markers, 1.0, False, quality)[0]
    offsets, missing = _click_offsets(markers, out, SR)

    assert missing == 0
    assert max(offsets) <= STEADY_TOLERANCE_MS[quality]


# --- Marker placement: humanized clicks warped onto an exact grid ---------
#
# Same generator Rubber Band's step 3 measurement used (for direct
# comparability -- see the step 4 report for both engines side by side):
# 24 markers, local ratio jitter
# +/-jitter around a nominal grid, no clicks lost at any (jitter, spacing,
# quality) combination measured. Only +/-5% and +/-20% jitter are pinned
# here per the plan; +/-10% (measured, not pinned) sits between them.
# Measured max |offset| across the three spacings (100/250/500 ms), this
# file's disposable script:
#   +/-5%:  high 2.79-7.57 ms,  balanced 3.06-6.87 ms
#   +/-20%: high 16.58-31.97 ms, balanced 9.75-21.02 ms
# Tolerances below take the worst spacing per (jitter, quality) and round
# up with headroom.
HUMANIZED_TOLERANCE_MS = {
    (0.05, "high"): 12.0,
    (0.05, "balanced"): 12.0,
    (0.20, "high"): 40.0,
    (0.20, "balanced"): 30.0,
}


def _humanized_offsets(jitter: float, spacing_ms: int, quality: str):
    rng = np.random.default_rng(1)
    sp = int(spacing_ms * SR / 1000)
    n = 24
    src = np.cumsum(np.r_[0, sp * (1 + rng.uniform(-jitter, jitter, n))]).astype(int)
    frames = src[-1] + sp
    tgt = np.arange(n + 1) * sp
    x = np.zeros(frames, np.float32)
    x[src[1:]] = 1.0
    markers = np.c_[np.r_[0, src[1:], frames], np.r_[0, tgt[1:], tgt[-1] + sp]]
    y = pytimestretch.time_warp(
        x, SR, markers=markers, quality=quality, backend="signalsmith"
    )
    offsets = []
    missing = 0
    for t in tgt[1:]:
        lo = max(0, t - int(0.04 * SR))
        hi = min(len(y), t + int(0.04 * SR))
        seg = np.abs(y[lo:hi])
        if seg.size == 0 or seg.max() < 0.05:
            missing += 1
            continue
        peak_idx = lo + int(np.argmax(seg))
        offsets.append(abs(peak_idx - t) / SR * 1000)
    return offsets, missing


@pytest.mark.parametrize("spacing_ms", [100, 250, 500])
@pytest.mark.parametrize("quality", ["high", "balanced"])
@pytest.mark.parametrize("jitter", [0.05, 0.20])
def test_marker_placement_humanized_grid_within_measured_bound(
    jitter: float, quality: str, spacing_ms: int
) -> None:
    offsets, missing = _humanized_offsets(jitter, spacing_ms, quality)

    assert missing == 0
    assert max(offsets) <= HUMANIZED_TOLERANCE_MS[(jitter, quality)]


# --- Marker placement: abrupt ratio alternation (measured anomaly) --------
#
# Alternating x0.5/x2 every marker at 100 ms spacing (a 4x ratio jump
# between neighbours) loses clicks on both qualities here -- measured 15/29
# interior clicks missing for both "high" and "balanced". Rubber Band shows
# the same kind of failure on this same construction (its own
# test_marker_placement_alternating_ratio_within_measured_bound, 17/30 on
# "high"): a shared limitation of abrupt local-ratio alternation for both
# engines, not a Signalsmith-specific regression. Pinned loosely (headroom
# over the measured missing-count) so a further regression is still caught.
ALT_MAX_MISSING = {"high": 20, "balanced": 20}


@pytest.mark.parametrize("quality", ["high", "balanced"])
def test_marker_placement_alternating_ratio_loses_clicks_as_measured(
    quality: str,
) -> None:
    markers = _build_markers(100, SR, [0.5, 2.0], 30)
    frames = int(markers[-1, 0])
    audio = np.zeros(frames, dtype=np.float32)
    for src_f, _tgt_f in markers[1:]:
        if src_f < frames:
            audio[src_f] = 1.0
    buf = audio.reshape(1, -1).copy()

    out = ss.render(buf, SR, markers, 1.0, False, quality)[0]
    _offsets, missing = _click_offsets(markers, out, SR)

    assert missing <= ALT_MAX_MISSING[quality]


# --- Speed order (step 4 measurement) -------------------------------------
#
# Measured (warmed medians, this host, 4 s noise+clicks at x1.5):
#   mono:   high 295.2 ms, balanced 174.6 ms
#   stereo: high 479.1 ms, balanced 279.6 ms
# "balanced" is consistently faster (~1.7x) but by a smaller margin than
# Rubber Band's "balanced" vs "high" gap (~3x) -- reported, not hidden.
# Medians of 3 here (not 7) to keep the test fast.


def _median_render_ms(channels: int, quality: str, ratio: float = 1.5) -> float:
    import time

    frames = round(4.0 * SR)
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal((channels, frames)) * 0.1).astype(np.float32)
    step = round(0.5 * SR)
    audio[:, ::step] = 1.0
    tgt = round(frames * ratio)
    markers = two_markers(frames, tgt)

    times = []
    for _ in range(3):
        buf = audio.copy()
        t0 = time.perf_counter()
        ss.render(buf, SR, markers, 1.0, False, quality)
        times.append((time.perf_counter() - t0) * 1000)
    return float(np.median(times))


def test_balanced_quality_is_faster_than_high_on_stereo() -> None:
    high_ms = _median_render_ms(2, "high")
    balanced_ms = _median_render_ms(2, "balanced")

    assert high_ms >= balanced_ms * 1.3


# --- time_warp determinism -------------------------------------------------


def test_time_warp_determinism_bitwise_equal() -> None:
    rng = np.random.default_rng(7)
    frames = SR * 2
    audio = rng.standard_normal(frames).astype(np.float32)
    markers = np.array(
        [[0, 0], [round(frames * 0.4), round(frames * 0.5)], [frames, round(frames * 1.3)]],
        dtype=np.int64,
    )

    out1 = ss.render(audio.reshape(1, -1).copy(), SR, markers, 1.0, False, "high")
    out2 = ss.render(audio.reshape(1, -1).copy(), SR, markers, 1.0, False, "high")

    np.testing.assert_array_equal(out1, out2)
