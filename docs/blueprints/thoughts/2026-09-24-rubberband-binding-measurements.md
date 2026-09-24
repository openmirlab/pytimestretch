# Rubber Band direct binding — first measurements

> 2026-09-24 · Evidence for plan step 3. The binding works end to end: exact length, pitch held, no crosstalk, deterministic. Two findings need Paul's attention: the stereo channel option was changed from the plan's proposal, and R3 with the built-in FFT is slower than the CLI numbers from the first probe (a different engine and FFT, not a regression). Blind listening is still pending.

## Build under test

`pytimestretch._rubberband` at commit after `f4a8de7`: Rubber Band v4.0.0
(`1d95888b`) single-file build, built-in FFT, BQResampler, `NO_THREADING`,
`-O3`, GCC 13, Python 3.13, this Linux host. Engine options:
`OptionProcessOffline | OptionEngineFiner (R3) | OptionThreadingNever |
OptionChannelsApart`. Two passes (`study()` then `process()`/`retrieve()`)
in 4096-frame blocks; time ratio `target_frames / frames`; tail trimmed or
zero-padded to the facade's exact length. Sample rate 44.1 kHz unless noted.
The disposable script and raw JSON are in the session scratchpad.

## Results

**Output placement.** The header documents that offline mode compensates
start delay and pad internally; measured `getStartDelay() == 0` and
`getPreferredStartPad() == 0` in every case, and raw output length already
equalled the target in every impulse case. Peak offset of a single impulse
(measured − expected, ms):

| Impulse at | ×0.5 | ×0.8 | ×1.25 | ×1.5 | ×2.0 | ×3.0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.25 s | −1.45 | +0.48 | −1.20 | −3.58 | −6.05 | −10.02 |
| 1.0 s | −1.13 | −0.32 | −1.36 | −2.72 | −5.74 | −13.24 |
| 2.5 s | 0.00 | −0.25 | −1.66 | −2.95 | −5.10 | −12.97 |

A click train (0.5 s spacing) showed no drift across the file: mean/max
|offset| 2.96/3.74 ms at ×1.5 and 1.00/2.20 ms at ×0.5. Offsets are
consistently *early* and grow with the ratio, which matches a stretched
transient whose energy peak spreads ahead of the nominal position, not a
constant latency. Pinned in tests at ×1.5 (≤ 6 ms) and ×0.5 (≤ 5 ms). The
×3.0 case (~13 ms) is recorded but not pinned; judge it by listening before
treating it as a defect.

**Pitch.** 440 Hz sine → 439.99998 / 440.00000 / 440.00001 Hz at ×0.5, ×1.5, ×3.0.

**Silence and channels.** Silence in gives exact zeros out. With the plan's
proposed `OptionChannelsTogether`, a silent left channel beside full-scale
noise on the right picked up ~0.71 peak / ~−15 dBFS RMS, failing the
contract's channel-independence test; `OptionChannelsApart` (Rubber Band's
own default) gives exact zeros. The binding uses `OptionChannelsApart`.

**Precision at ×1.0** (float64 input; R3 is not an identity at ratio 1):
error RMS −29.75 dB for noise and −44.72 dB for a sine relative to input;
level change ≤ 0.01 dB.

**Determinism.** Same input twice → bitwise identical output.

**Speed** (warmed median of 7, this host): 4 s mono 232 ms; 4 s stereo
470 ms; the first call is no slower (no JIT). For context on the same 4 s
beat file, the system Rubber Band 3.3.0 CLI (with FFTW) took 0.03 s with R2
(its default, which the first probe measured) and 0.12 s with R3, including
file I/O. So the binding's R3 is ~2× slower than R3 with FFTW, and R3 itself
is ~4× slower than R2. It still runs ~17× faster than real time.

**Edge cases.** 1 frame at ×3.0, 10 frames at ×0.5, and 0.25 s at ×0.25 all
return finite audio of the exact length.

**Real material.** The first probe's beat and pad excerpts (mono, 4 s) at
×0.5/×1.5/×3.0: finite, exact length, peaks −2.1 to −7.8 dBFS. Renders are
kept for listening next to the earlier probe outputs.

## Open points for Paul

1. **Channel option.** `ChannelsApart` keeps channels strictly independent
   (safe for dual-mono stems, click-plus-music pairs, hard-panned parts);
   `ChannelsTogether` aims for a steadier centre image on stereo mixes but
   leaks between channels. Keep `Apart` as the default unless a blind
   comparison on real stereo mixes shows `Together` is clearly better; if
   so, it becomes an explicit option, not a silent default.
2. **Speed.** If R3 at ~17× real time is too slow for Tactus workflows, the
   candidates are a faster FFT (FFTW is GPL-compatible under the decided
   license but heavy to vendor; KissFFT is bundled with Rubber Band) or an
   explicit R2 option. Measure before choosing.
3. **Listening.** Blind listening of these renders against Signalsmith is
   still needed before any quality claim.
