"""Rubber Band engine-specific measurements, pinned with margins.

Unlike tests/contract/ (test_output_contract.py, test_markers.py, etc. --
engine-independent, runs on every backend), these assertions are Rubber
Band-specific: numeric tolerances
derived from this file's own step 3 measurement run (disposable script,
raw JSON kept in the session scratchpad; summarized in the step 3 report).
Margins here are deliberately generous relative to the measured worst case
so a small future engine-option or build change doesn't flap the suite.
Calls target native contract v2's ``render(buffer, sample_rate, markers,
pitch_scale, preserve_formants, quality)`` in full (step 3 implements
pitch, formants, quality presets, and marker warp; step 4 does the same
for Signalsmith).

Below the original step-1/2 checks (impulse placement, silence, crosstalk,
determinism, engine_info/SUPPORTED_QUALITY), the newer sections pin: pitch
accuracy per quality, the one formant (2600 Hz) whose envelope estimate
proved stable across quality/mode in measurement (700/1220 Hz were too
noisy to pin -- see the comment above ``test_formant_*``), marker
placement at 100/250 ms spacing for steady and alternating local ratios,
opt-in speed ordering, and ``engine_version`` via ``_stretch_diagnostics``.

Reads: pytimestretch._rubberband.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pytimestretch import _rubberband as rb

SR = 44100


def target_frames(frames: int, ratio: float) -> int:
    import math

    return math.floor(frames * ratio + 0.5)


def two_markers(frames: int, tgt: int) -> np.ndarray:
    return np.array([[0, 0], [frames, tgt]], dtype=np.int64)


def render(buf: np.ndarray, sr: int, markers: np.ndarray) -> np.ndarray:
    return rb.render(buf, sr, markers, 1.0, False, "high")


def impulse_at(t_sec: float, total_sec: float = 4.0, sr: int = SR) -> np.ndarray:
    frames = round(total_sec * sr)
    sig = np.zeros(frames, dtype=np.float32)
    sig[round(t_sec * sr)] = 1.0
    return sig


# Measured worst-case |offset|: ratio 1.5 -> 3.74 ms (click-train case),
# ratio 0.5 -> 2.20 ms
# (click-train case). Tolerances below round each up and add ~2 ms of
# headroom for jitter across machines; both stay well under the "flag if
# > 10 ms" measurement threshold (ratio 3.0 alone crossed that at ~13.2 ms and
# is reported separately, not pinned here).
IMPULSE_TOLERANCE_MS = {1.5: 6.0, 0.5: 5.0}


@pytest.mark.parametrize("ratio", [1.5, 0.5])
@pytest.mark.parametrize("t_sec", [0.25, 1.0, 2.5])
def test_impulse_placement_within_tolerance(ratio: float, t_sec: float) -> None:
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


def test_pitch_stays_within_one_percent_at_1_5() -> None:
    ratio = 1.5
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

    assert np.abs(out).max() < 1e-6


def test_stereo_crosstalk_stays_below_measured_bound() -> None:
    # Measured (step 3): with the decided engine setup (OptionChannelsApart
    # — see native/rubberband_module.cpp's kEngineOptions comment for why
    # ChannelsApart replaced the plan's originally proposed
    # ChannelsTogether), a silent left channel against full-scale noise on
    # the right measured bitwise-exact 0.0 crosstalk. -80 dBFS is a
    # generous bound around that, not a tight pin.
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
    info = rb.engine_info()
    assert set(info) == {
        "engine",
        "version",
        "engine_version",
        "fft",
        "resampler",
        "source_revision",
    }
    assert info["engine"] == "rubberband"


def test_supported_quality_names_engine_capability() -> None:
    # Step 3: render() now honors every quality SUPPORTED_QUALITY names.
    # "fast" was removed 2026-09-25 (blind listening round 2: no audible
    # benefit, no real speed edge over "balanced").
    assert rb.SUPPORTED_QUALITY == ("high", "balanced")


def test_unknown_quality_string_raises_value_error() -> None:
    # Now a genuine bad call (not "unimplemented"): quality_options() in
    # native/rubberband_module.cpp raises std::invalid_argument for
    # anything outside "high"/"balanced".
    audio = np.zeros(44100, dtype=np.float32)
    buf = audio.reshape(1, -1).copy()
    markers = two_markers(44100, 44100)
    with pytest.raises(ValueError):
        rb.render(buf, SR, markers, 1.0, False, "ultra")


# --- Pitch accuracy (step 3 measurement) --------------------------------
#
# Measured worst-case |cents| error, 440 Hz sine, 3 s, semitones +7 and -5
# at duration_ratio 1.0 (this file's disposable measurement script):
# high 0.25, balanced 0.25. Tolerances below round the measured worst case
# up with headroom. ("fast"/R2 was measured at 5.46 (+7) / 31.03 (-5) cents
# -- a real, reproducible outlier -- and was one input to removing "fast"
# 2026-09-25 after blind listening round 2 confirmed no audible benefit and
# no real speed edge over "balanced"; it is no longer a supported quality.)
PITCH_CENTS_TOLERANCE = {"high": 3.0, "balanced": 3.0}


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

    out = rb.render(buf, SR, two_markers(frames, frames), pitch_scale, False, quality)[0]

    i0 = round((dur_sec / 2 - 0.5) * SR)
    i1 = round((dur_sec / 2 + 0.5) * SR)
    freq = dominant_freq(out[i0:i1], SR)
    expected = 440.0 * 2.0 ** (semitones / 12.0)
    cents = 1200.0 * math.log2(freq / expected)

    assert abs(cents) <= PITCH_CENTS_TOLERANCE[quality]


# --- Formants (step 3 measurement) --------------------------------------
#
# Synthetic vowel (impulse train f0=150 Hz through three 2nd-order
# resonators at 700/1220/2600 Hz, bandwidths 80/90/120 Hz) measured with a
# cepstral-liftered envelope estimate. Only the 2600 Hz formant gave a
# stable reading across quality and formants= mode: measured worst-case
# deviation (self-referenced against the same estimator's own read of the
# unprocessed vowel, to cancel the estimator's own bias) was 1.43% for
# "shift" (expect the peak to move by pitch_scale) and 3.39% for
# "preserve" (expect the peak to stay put). The 700/1220 Hz formants are
# NOT pinned: with source f0=150 Hz, harmonics are 150 Hz apart -- close to
# or wider than those formants' 80/90 Hz bandwidths -- so only 1-2
# harmonics ever land near the resonance and the envelope estimate at
# those frequencies swung by 10-45% depending on which harmonic happened
# to dominate, unrelated to whether the engine is doing the right thing.
# Confirming formants= on those lower formants needs either a lower f0 (or
# noise-excited source) or real material, which is what plan step 5's
# listening round is for.
FORMANT_F0 = 150.0
FORMANT_TARGETS = (700.0, 1220.0, 2600.0)
FORMANT_BWS = (80.0, 90.0, 120.0)
FORMANT_SHIFT_TOLERANCE_PCT = 10.0
FORMANT_PRESERVE_TOLERANCE_PCT = 15.0


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


@pytest.mark.parametrize("quality", ["high", "balanced"])
@pytest.mark.parametrize("mode", ["shift", "preserve"])
def test_formant_2600hz_stays_within_measured_tolerance(mode: str, quality: str) -> None:
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
    out = rb.render(buf, SR, markers, pitch_scale, preserve, quality)[0]

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


# --- Marker placement (step 3 measurement) -------------------------------
#
# Click train, markers built as a source/target grid with a fixed *output*
# spacing and either a steady local ratio (1.5) or an alternating one
# (x0.5 / x2.0 between neighbours). Measured (100/250 ms spacing, this
# file's script):
#   steady, high:   max |offset| 3.85 ms (100 ms), 3.74 ms (250 ms), no loss
#   alt,    high:   17/30 and 8/12 interior clicks LOST (no detectable peak
#                   within a 20 ms search window); of those found, max
#                   |offset| ~18-18.5 ms
# The steady case pins tightly. The alternating case is a genuine anomaly
# for Paul, not a measurement artifact -- direct inspection (offset per
# marker, printed during step 3) showed real drift up to ~100 ms and near-
# zero peak energy at some markers, not just search-window misses. It is
# pinned loosely (headroom over the measured missing-count and offset) so
# a further regression is still caught. ("fast"/R2 was also measured here
# (steady: 13.22/12.22 ms, no loss; alt: no clicks lost, ~17.2/16.2 ms) but
# was removed 2026-09-25 after blind listening round 2 found no audible
# benefit and no real speed edge over "balanced".)
STEADY_TOLERANCE_MS = {"high": 6.0}
ALT_MAX_OFFSET_TOLERANCE_MS = {"high": 22.0}
ALT_MAX_MISSING = {"high": 20}


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


def _click_offsets(markers: np.ndarray, out: np.ndarray, sr: int):
    window = max(1, round(0.02 * sr))
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
@pytest.mark.parametrize("quality", ["high"])
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

    out = rb.render(buf, SR, markers, 1.0, False, quality)[0]
    offsets, missing = _click_offsets(markers, out, SR)

    assert missing == 0
    assert max(offsets) <= STEADY_TOLERANCE_MS[quality]


@pytest.mark.parametrize("spacing_ms", [100, 250])
@pytest.mark.parametrize("quality", ["high"])
def test_marker_placement_alternating_ratio_within_measured_bound(
    quality: str, spacing_ms: int
) -> None:
    n_segments = max(6, round(3000 / spacing_ms))
    markers = _build_markers(spacing_ms, SR, [0.5, 2.0], n_segments)
    frames = int(markers[-1, 0])
    audio = np.zeros(frames, dtype=np.float32)
    for src_f, _tgt_f in markers[1:]:
        if src_f < frames:
            audio[src_f] = 1.0
    buf = audio.reshape(1, -1).copy()

    out = rb.render(buf, SR, markers, 1.0, False, quality)[0]
    offsets, missing = _click_offsets(markers, out, SR)

    assert missing <= ALT_MAX_MISSING[quality]
    if offsets:
        assert max(offsets) <= ALT_MAX_OFFSET_TOLERANCE_MS[quality]


# --- Speed order (step 3 measurement) ------------------------------------
#
# Measured (warmed medians of 7, this host, 4 s noise+clicks at x1.5):
#   mono:   high 232 ms, balanced 71.4 ms
#   stereo: high 470 ms, balanced 145.0 ms
# "high" is unambiguously slowest in both cases (the only ordering claim
# this plan step actually needs pinned). Medians of 3 here (not 7) to keep
# the test fast. This host-specific threshold is opt-in, not a portable
# wheel correctness gate. ("fast" was also measured here (mono 73.5 ms, stereo 130.6 ms --
# no real speed edge over "balanced") but was removed 2026-09-25 after
# blind listening round 2 confirmed no audible benefit either.)


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
        rb.render(buf, SR, markers, 1.0, False, quality)
        times.append((time.perf_counter() - t0) * 1000)
    return float(np.median(times))


@pytest.mark.performance
def test_high_quality_is_slower_than_balanced_on_stereo() -> None:
    high_ms = _median_render_ms(2, "high")
    balanced_ms = _median_render_ms(2, "balanced")

    assert high_ms >= balanced_ms * 1.5


# --- engine_version via diagnostics --------------------------------------


@pytest.mark.parametrize(
    ("quality", "expected_version"),
    [("balanced", 3), ("high", 3)],
)
def test_engine_version_matches_quality(quality: str, expected_version: int) -> None:
    audio = np.zeros(44100, dtype=np.float32)
    buf = audio.reshape(1, -1).copy()
    markers = two_markers(44100, 44100)
    info = rb._stretch_diagnostics(buf, SR, markers, 1.0, False, quality)
    assert info["engine_version"] == expected_version
