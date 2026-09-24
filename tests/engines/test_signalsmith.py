"""Signalsmith Stretch engine-specific measurements, pinned with margins.

Unlike tests/contract/test_contract.py (engine-independent, runs on every
backend), these assertions are Signalsmith-specific: numeric tolerances
derived from the step 4 measurement run recorded in
docs/blueprints/thoughts/2026-09-24-signalsmith-binding-measurements.md.
Margins here are deliberately generous relative to the measured worst case
so a small future build/config change doesn't flap the suite.

Reads: pytimestretch._signalsmith.
"""

from __future__ import annotations

import numpy as np
import pytest

from pytimestretch import _signalsmith as ss

SR = 44100


def target_frames(frames: int, ratio: float) -> int:
    import math

    return math.floor(frames * ratio + 0.5)


def impulse_at(t_sec: float, total_sec: float = 4.0, sr: int = SR) -> np.ndarray:
    frames = round(total_sec * sr)
    sig = np.zeros(frames, dtype=np.float32)
    sig[round(t_sec * sr)] = 1.0
    return sig


# Measured worst-case |offset| (docs/blueprints/thoughts, step 4 measurement
# table): well under 1 ms at both ratios (0.5's click train measured exactly
# 0.0 ms; 1.5's measured ~0.02 ms). The .exact() whole-buffer method has no
# streaming block-loop drift the way Rubber Band's two-pass offline loop
# does, so these margins are tight relative to Rubber Band's but still
# generous headroom (2 ms) over the measured worst case.
IMPULSE_TOLERANCE_MS = {1.5: 2.0, 0.5: 2.0}


@pytest.mark.parametrize("ratio", [1.5, 0.5])
@pytest.mark.parametrize("t_sec", [0.25, 1.0, 2.5])
def test_impulse_placement_within_tolerance(ratio: float, t_sec: float) -> None:
    audio = impulse_at(t_sec)
    frames = audio.shape[0]
    tgt = target_frames(frames, ratio)
    buf = audio.reshape(1, -1).copy()

    out = ss.stretch(buf, SR, ratio, tgt)

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

    out = ss.stretch(buf, SR, ratio, tgt)[0]

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

    out = ss.stretch(buf, SR, ratio, tgt)

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

    out = ss.stretch(buf, SR, ratio, tgt)

    left_peak = float(np.abs(out[0]).max())
    left_peak_dbfs = 20 * np.log10(left_peak) if left_peak > 0 else float("-inf")
    assert left_peak_dbfs < -80.0


def test_determinism_same_input_twice_bitwise_equal() -> None:
    ratio = 1.5
    rng = np.random.default_rng(11)
    audio = rng.standard_normal(SR).astype(np.float32)
    buf = audio.reshape(1, -1).copy()
    tgt = target_frames(SR, ratio)

    out1 = ss.stretch(buf.copy(), SR, ratio, tgt)
    out2 = ss.stretch(buf.copy(), SR, ratio, tgt)

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
# native/signalsmith_module.cpp's run_signalsmith() zero-pads input below
# that threshold and trims back down (see its comment); measured (step 4),
# all three cases below land back inside the padded .exact() call (i.e.
# still process real, non-silent output for the 0.25s case), stay finite,
# and are exactly target_frames long, matching the plan's edge-case gate.


def test_single_frame_edge_case() -> None:
    audio = np.ones(1, dtype=np.float32)
    buf = audio.reshape(1, -1).copy()
    tgt = target_frames(1, 3.0)

    out = ss.stretch(buf, SR, 3.0, tgt)

    assert out.shape == (1, tgt)
    assert np.isfinite(out).all()


def test_ten_frame_edge_case() -> None:
    audio = np.ones(10, dtype=np.float32)
    buf = audio.reshape(1, -1).copy()
    tgt = target_frames(10, 0.5)

    out = ss.stretch(buf, SR, 0.5, tgt)

    assert out.shape == (1, tgt)
    assert np.isfinite(out).all()


def test_short_clip_below_minimum_still_finite_and_exact_length() -> None:
    frames = round(0.25 * SR)
    audio = np.random.default_rng(0).standard_normal(frames).astype(np.float32)
    buf = audio.reshape(1, -1).copy()
    tgt = target_frames(frames, 0.25)

    out = ss.stretch(buf, SR, 0.25, tgt)

    assert out.shape == (1, tgt)
    assert np.isfinite(out).all()
