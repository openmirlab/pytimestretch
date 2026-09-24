# Time-stretch package contract and first development path

> 2026-09-24 · Development note for the first working `pytimestretch` release. This is a proposed, testable contract—not a statement that the scaffold already processes audio. It draws on the Tactus [algorithm survey](https://github.com/rytho-ai/tactus/blob/main/docs/blueprints/thoughts/2026-09-23-time-stretch-competitors-research.md), [candidate survey](https://github.com/rytho-ai/tactus/blob/main/docs/blueprints/thoughts/2026-09-24-openmirlab-time-stretch-candidates.md), and [listening probe](https://github.com/rytho-ai/tactus/blob/main/docs/blueprints/thoughts/2026-09-24-time-stretch-algorithm-listening-probe.md). Some Tactus notes may still be local/unpublished; their links are provenance pointers, not required runtime inputs.

## Why this package exists

The package is a NumPy-facing time-stretch boundary, not a DAW. An agent
writing Python/NumPy audio should be able to ask for a duration change without
rediscovering ratio conventions, channel order, precision loss, binary
installation, and output-padding policy. The caller still decides *what* to
stretch and *why*; the package makes the result inspectable.

Its implementation is an open fork. **Binding hypothesis:** directly call the
Rubber Band and Signalsmith C++ libraries through native Python extensions,
using existing Python wrappers only as references. **Python hypothesis:**
NumPy/SciPy FFT plus Numba-compiled loops can provide enough quality, speed,
and control for Tactus without depending on either engine. A hybrid is also
possible. Do not equate a fast phase vocoder with a production-quality
replacement: transient behavior, phase coherence, exact output placement,
and corner cases are part of the algorithmic work. [Rubber Band technical
notes](https://www.breakfastquay.com/rubberband/technical.html),
[Signalsmith design](https://signalsmith-audio.co.uk/writing/2023/stretch-design/),
[Numba's supported NumPy features](https://numba.readthedocs.io/en/stable/reference/numpysupported.html)

The two established engine references have different roles:

- **Rubber Band** is the working baseline for Tactus. `pyrubberband` is one
  existing CLI/file wrapper, not the algorithm. Rubber Band supports R2/R3
  settings and offline key-frame maps; the first slice need not expose every
  advanced option. [Rubber Band API](https://www.breakfastquay.com/rubberband/code-doc/)
- **Signalsmith Stretch** is an independent MIT-licensed algorithm to test
  for moderate stretches. `python-stretch` is an existing compiled NumPy-facing binding;
  its internal audio shape is `(channels, samples)` and it accepts an explicit
  seed. It is a comparison target, not a promised quality improvement.
  [Signalsmith Stretch](https://github.com/Signalsmith-Audio/signalsmith-stretch),
  [Python binding](https://github.com/gregogiudici/python-stretch)

The prior listening probe compared a tiny set of beat/pad examples. A/B/C
labels were randomized per source/ratio cell, so Paul's preference for “A”
does not establish that Rubber Band wins every cell or that R2 wins R3. Keep
Rubber Band as the working default without overstating that evidence.

## Proposed first public Python contract

Start with one whole-buffer operation. The exact spelling can change before
the first audio release, but the semantics below must be settled by tests:

```python
output = stretch_audio(
    audio,                    # np.ndarray: (frames,) or (frames, channels)
    sample_rate=48_000,
    duration_ratio=1.5,       # output is 1.5x as long; pitch approximately held
    backend="rubberband",     # or "signalsmith"
)
```

- `duration_ratio > 1` means *longer/slower output*; `< 1` means
  *shorter/faster*. This is deliberately named to avoid confusing it with
  implementation-specific speed ratios. Test both directions against every candidate.
- Public arrays are frame-major because Tactus and SoundFile use
  `(frames, channels)`. Mono 1-D input returns 1-D; 2-D mono/stereo returns
  the same channel count and dimension. Each implementation owns its transposition.
- Input is finite, nonempty, float audio with a positive integer sample rate
  and finite positive ratio. Input must not be mutated. Decide whether to
  accept float64 by conversion or preserve it, and document the output dtype
  before releasing this call. Do not silently clamp peaks.
- Define `target_frames` once at the facade boundary. Proposed rounding is
  `floor(input_frames * duration_ratio + 0.5)` for positive ratios; reject a
  result below one frame. Every backend must return this many frames exactly,
  after a documented trim/pad policy. A frame-count match does not by itself
  prove alignment or quality.
- The API must distinguish invalid input, unavailable backend, engine failure,
  and unsupported option. Error messages should name the missing executable or
  Python extra and show the fix. No silent fallback to a different algorithm.
- The first slice is whole-buffer and offline. Marker maps, streaming,
  variable ratios, pitch-shift, and real-time latency controls are separate
  capabilities. Add them only with their own time-coordinate contracts and
  tests; do not overload `duration_ratio` with an ambiguous curve.

## Implementation seams and known traps

Rubber Band: `pyrubberband` calls an external `rubberband` executable and
uses temporary WAV files. Its current `sf.write(...)` call does not select a
subtype, and SoundFile's default WAV subtype is PCM-16. That means a naive
wrapper can quantize floating audio before stretching. A direct native
binding would avoid this file path, but must still prove its own buffer and
precision behavior. Compare low-level noise and round-trip error before
choosing. Do not copy engine code into this repo as a shortcut.
[pyrubberband source](https://github.com/bmcfee/pyrubberband/blob/main/pyrubberband/pyrb.py),
[SoundFile documentation](https://python-soundfile.readthedocs.io/)

Signalsmith: the existing binding is native/nanobind and expects
`(channels, samples)` float32. Verify its ratio interpretation, output-size
behavior, latency, flush/tail, and seeded repeatability with real installed
wheels. Do not assume a returned array can simply be transposed and treated
as perfectly aligned. [binding source](https://github.com/gregogiudici/python-stretch/blob/main/src/signalsmith-bindings.cpp)

Numba: JIT compilation can accelerate elementwise and frame-loop work, but
Numba's supported-feature listing does not include `numpy.fft` in nopython
mode. A realistic prototype can call NumPy/SciPy FFT outside JIT kernels and
JIT the surrounding numerical loops. Benchmark warmed execution separately
from first-call compilation. [Numba support listing](https://numba.readthedocs.io/en/stable/developer/autogen_numpy_listing.html)

Licensing is layered. Our code, the two Python wrappers, and the two
engines have different terms. Rubber Band itself is GPL-2.0-or-later or
commercial; the candidate Python wrapper is ISC. Signalsmith and its candidate
binding are MIT. `pytimestretch` currently vendors none of them and is private.
Re-expressing an upstream algorithm from its source is not automatically a
license-free alternative; obtain a legal review before any close port or
public distribution.
Decide this package's own license, linking/CLI distribution topology, and
OpenMIRLab audio-tool policy before public release; do not solve that by
changing only a classifier. [Rubber Band license](https://breakfastquay.com/rubberband/license.html)

## The deciding experiment before architecture selection

Build one bounded Python/NumPy/SciPy/Numba prototype rather than attempting
to reproduce every feature of Rubber Band. A sensible first candidate is a
phase-vocoder path with a named transient/phase treatment; record its actual
algorithm, not merely “Numba stretcher.” Compare it against installed Rubber
Band R2/R3 and Signalsmith on the *same* short, licensed materials: drums,
voice, sustained pad, and a mixed excerpt; use output-duration ratios 0.5,
1.5, and 3.0. All candidates must share sample rate, output length, playback
level, and a separately measured alignment policy.

Measure warmed render time, first-call compile time, peak memory, numerical
validity, transient position, pitch drift, and deployment/setup burden. Ask
Paul to listen blind per source/ratio cell; waveform equality is not a valid
quality oracle because different good stretch algorithms need not output the
same samples. If the Python prototype is good enough on the cells that matter
and is simpler to deploy, it can become the product engine. If it misses
material cases despite focused improvement, use a native engine there. A
split result supports a hybrid, not a universal winner. The quality threshold
and target cells must be declared *before* hearing the candidates.

## Implement in evidence-sized slices

1. **Contract tests first.** Add deterministic mono/stereo arrays: impulse,
   sine, transient clicks, silence, and a seeded random signal. Parameterize
   validation, immutability, shape, ratio direction, and frame-count tests
   independently of any installed engine. Add fixtures from real audio with
   explicit provenance and hashes for integration tests.
2. **Deciding probe.** Run the Python/Numba comparison above and record
   results before choosing which implementation belongs in the package.
3. **Chosen engine path.** If bindings win, implement direct C++ integration
   for the justified engines; use `pyrubberband`/`python-stretch` as references,
   not assumed runtime dependencies. If Python wins, ship the tested algorithm
   with exact versioned fixtures. If split, keep the engine boundary explicit.
4. **Alignment and listening.** For each shipped engine, measure impulse position,
   start/end padding, first transient shift, channel crosstalk, and silence
   behavior. Build a small, level-matched blind audition over named
   source/ratio cells. Store judgments per cell; do not convert an overall
   preference into a universal backend ranking.
5. **Installed-wheel handoff.** Test a clean wheel install with no engines;
   `import pytimestretch` must work. Then separately install each optional
   engine and exercise real processing. Run the Tactus consumer only after
   this surface is stable. Update README/CLAUDE.md/NOTICE/CHANGELOG together.

## First-release completion check

The first audio release is ready only when every advertised engine passes the
shared contract on actual installations; output length and ratio direction are exact;
precision and alignment limits are measured; missing-backend errors tell the
user what to install; the wheel install story matches the chosen architecture;
and README examples run as written. If only one engine is ready, state that
narrower scope rather than keeping a fake option.
