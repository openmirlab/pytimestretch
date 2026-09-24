# Python/Numba versus native stretch — first probe

> 2026-09-24 · This evidence feeds the pending implementation-boundary decision back to Paul. Verdict: unsettled; the Python route is technically plausible, but audible acceptability has not been judged. The disposable harness and audio are in `/tmp/pytimestretch-numba-probe-hv8GEJ/`, not product code or committed fixtures.

## Question and preregistered rule

Could one small Python/NumPy/SciPy/Numba stretcher meet the needs that would otherwise make direct bindings to Rubber Band or Signalsmith necessary? This probe tests only a first phase-vocoder implementation, not the space of all possible Python algorithms.

The rule was stated before the first render: exact length, finite output, and plausible time/pitch placement are entry conditions. An obvious artifact on a beat or pad at 1.5× would show that *this prototype* is not a replacement, not that Python is incapable. If it sounds close on these cells, voice and more diverse music remain necessary before dropping native engines. Sound-quality judgment is pending Paul's blind listening; no numeric metric alone decides it.

## Controlled setup

- Two existing four-second mono excerpts: beat-grid demo (SHA-256 `b8506d0fdcb5bcf358cbf06dc755564300b9cdd9421aaf30753e30cc1e65b805`) and soft pad (SHA-256 `261eccabb42ddbebaf7f22cc891dad6f259aaf0cd06cc86cd8316037feb6a3d0`). The beat source was resampled from 22.05 to 44.1 kHz with `scipy.signal.resample_poly`; the pad was already 44.1 kHz. The exact source locations and generated files are recorded in the disposable harness.
- Output-duration ratios: 0.5, 1.5, and 3.0. Same input, sample rate, target frame count, and output WAV subtype (PCM-24) per cell. Output arrays were trimmed or zero-padded to the common target; `raw_frames` were recorded before this step.
- **Python prototype:** 2048-sample Hann-window STFT and inverse FFT in NumPy, phase advance and overlap-add in Numba. No transient detector, phase locking, marker map, or adaptive window. It is not a Rubber Band/Signalsmith port.
- **Rubber Band:** installed CLI 3.3.0 through `pyrubberband` 0.4.0, default CLI engine/settings; the wrapper uses temporary files and is not representative of a future direct binding's I/O cost or precision.
- **Signalsmith:** `python-stretch` 0.3.1, default preset, seed 0. Its speed-style `timeFactor` was set to the inverse of the output-duration ratio.
- Runtime: Python 3.13.5, NumPy 2.5.3, SciPy 1.18.1, Numba 0.67.0, SoundFile 0.14.0. Timings were on this one host. The listening page is a convenience blind with deterministic per-cell A/B/C labels and rough RMS matching, not a formal listening study.

## Observations

The first Python render exposed a real edge bug: at 3×, the requested output reached an almost-uncovered overlap-add tail, producing enormous peaks. Extending the final held analysis frame fixed that defect; the original failing result is not included in the listening page. This is a reminder that the engineering burden is not just writing the phase formula.

After the fix, all 18 real-material outputs (2 sources × 3 ratios × 3 methods) had finite samples, the exact target length, and peaks below 1.0. All three methods' raw output frame counts already matched targets in these cells, so the common trim/pad rule did not hide a length mismatch here. This establishes basic output validity, not perceptual equivalence.

For a synthetic 440 Hz sine at 1.5× and 3×, the dominant output frequency was 440.0–440.5 Hz across methods. A single synthetic impulse at 0.5 s placed its dominant peak within 13.22 ms of the scaled target in the six tested method/ratio combinations; the Python prototype offsets were −6.19 ms at 1.5× and 0.0 ms at 3×. One impulse and one sine do not characterize transient smearing, phasiness, or mixed-source quality.

Warmed processing time for the four-second beat excerpt at 1.5×, median of five runs:

| Method | Median wall time |
| --- | ---: |
| Python/NumPy/SciPy/Numba prototype | 40 ms |
| Rubber Band via CLI wrapper | 49.6 ms |
| Signalsmith via compiled Python binding | 33 ms |

The prototype's first call with a fresh Numba cache took about 0.51 s for a one-second input, versus much shorter warmed calls. These numbers measure different integration paths (in-memory Python versus CLI versus compiled binding) and one machine; they do **not** prove the Python algorithm is intrinsically faster or slower than either C++ library.

## Verdict and next evidence

**Unsettled.** The Python route passed a small numerical and speed feasibility check. It has not passed the deciding audible-quality check, and the prototype lacks the transient treatment, phase-coherence work, alignment/marker features, and broad edge-case coverage that native libraries offer. This neither proves that the project needs C++ bindings nor that it can drop them.

Paul can audition the temporary A/B/C page at `http://localhost:9134/index.html` while its local server is running. Record the source, ratio, selected letter, and any specific artifact before reveal. Next, add licensed voice and mixed-music material, listen blind at moderate and extreme ratios, then decide whether focused Python improvements, direct bindings, or a hybrid are justified. Preserve the same output contract across candidates; do not judge sound quality by waveform equality.
