# Signalsmith Stretch direct binding — first measurements

> 2026-09-24 · Evidence for plan step 4, measured with the same script shape as the [Rubber Band note](2026-09-24-rubberband-binding-measurements.md). The identical contract suite passes on both engines. Signalsmith's whole-buffer `.exact()` places transients within 0.5 ms at every tested ratio; it is somewhat slower than Rubber Band R3 on mono. Blind listening is still pending.

## Build under test

`pytimestretch._signalsmith`: Signalsmith Stretch `57b93f4` (header version
1.3.2), Signalsmith Linear `5668673` (0.3.1), built-in FFT (Accelerate on
macOS, untested), `presetDefault`, seed `0x5eed`, no transpose. `-O3`,
GCC 13, Python 3.13, this Linux host, 44.1 kHz unless noted.

`.exact(inputs, inputFrames, outputs, outputFrames)` resets the engine,
pre-rolls with `outputSeek()`, processes, and flushes, producing exactly
`outputFrames` with latency already compensated. It needs at least
`outputSeekLength(rate)` input frames (about one block plus one interval,
~2.6–2.9k frames with `presetDefault`); below that it zero-fills the output
and returns `false`. That threshold is an ordinary short clip, not a corner
case: the contract suite's 4410-frame stereo fixture at 48 kHz hit it. The
binding therefore zero-pads short input past the threshold, stretches, and
keeps the first `target_frames`; if `.exact()` still fails, it raises
instead of returning silence. Measured: 1 to 3000 frames at ×0.25–×3.0 all
complete.

## Results

**Output placement** (impulse peak offset, measured − expected, ms):

| Impulse at | ×0.5 | ×0.8 | ×1.25 | ×1.5 | ×2.0 | ×3.0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.25 s | 0.02 | 0.09 | −0.50 | −0.02 | 0.00 | −0.07 |
| 1.0 s | 0.00 | 0.09 | −0.23 | −0.02 | 0.00 | −0.07 |
| 2.5 s | 0.00 | 0.09 | −0.27 | −0.02 | 0.00 | −0.29 |

Click train max |offset|: 0.023 ms at ×1.5, 0.0 ms at ×0.5. Pinned at ≤ 2 ms
for ×1.5 and ×0.5. Compared with Rubber Band R3 (up to −13 ms at ×3.0), the
impulse peak stays put; whether that sounds better on real transients is a
listening question.

**Pitch.** 440 Hz → 440.0000003 / 439.9999999 / 439.9991 Hz at ×0.5, ×1.5, ×3.0.

**Silence and channels.** Silence in gives exact zeros; a silent left
channel beside noise on the right stays exactly zero.

**Precision at ×1.0** (float64 input): error RMS −53.7 dB for both noise and
a sine; level change −0.002 dB (Rubber Band R3: −29.75 / −44.72 dB).

**Determinism.** Fixed seed → bitwise identical output across runs.

**Speed** (warmed median of 7, ×1.5, both engines in one process):

| Input | Signalsmith | Rubber Band R3 |
| --- | ---: | ---: |
| 4 s mono | 295 ms | 233 ms |
| 4 s stereo | 479 ms | 472 ms |

**Real material.** Beat and pad excerpts at ×0.5/×1.5/×3.0: finite, exact
length, peaks −0.6 to −5.3 dBFS; rendered next to the Rubber Band renders
for listening.

## Open points for Paul

1. **Listening.** Both engines now render the same material through direct
   bindings; a blind, level-matched comparison per source/ratio cell is the
   next quality evidence. Signalsmith's upstream README says stretching
   sounds best between roughly 0.75× and 1.5×, so extreme cells matter.
2. **Short-input padding** is binding glue around `.exact()`, not an
   algorithm change. It is tested by the contract suite's short fixtures.
