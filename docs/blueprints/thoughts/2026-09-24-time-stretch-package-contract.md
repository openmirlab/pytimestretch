# Time-stretch package contract and first development path

> 2026-09-24 · Development note for the first working `pytimestretch` release. This is a proposed, testable contract—not a statement that the scaffold already processes audio. It draws on the Tactus [algorithm survey](https://github.com/rytho-ai/tactus/blob/main/docs/blueprints/thoughts/2026-09-23-time-stretch-competitors-research.md), [candidate survey](https://github.com/rytho-ai/tactus/blob/main/docs/blueprints/thoughts/2026-09-24-openmirlab-time-stretch-candidates.md), and [listening probe](https://github.com/rytho-ai/tactus/blob/main/docs/blueprints/thoughts/2026-09-24-time-stretch-algorithm-listening-probe.md). Some Tactus notes may still be local/unpublished; their links are provenance pointers, not required runtime inputs.

## Why this package exists

The package is a NumPy-facing time-stretch boundary, not a DAW. An agent
writing Python/NumPy audio should be able to ask for a duration change without
rediscovering ratio conventions, channel order, precision loss, binary
installation, and output-padding policy. The caller still decides *what* to
stretch and *why*; the package makes the result inspectable.

**Decision (2026-09-24): binding-first.** The product is a NumPy-facing
Python extension that calls the Rubber Band and Signalsmith Stretch C++
libraries directly, in memory. It is not a layer over `pyrubberband` or
`python-stretch`; those two remain behavior references and comparison
baselines. It does not re-implement either engine's algorithm. A
Python/NumPy/SciPy/Numba stretcher continues only as a research lane (below)
and does not gate the first binding release. Do not equate a fast phase
vocoder with a production-quality replacement: transient behavior, phase
coherence, exact output placement, and corner cases are part of the
algorithmic work. [Rubber Band technical
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

## Python algorithm lane

Keep Python/NumPy/SciPy/Numba as a **research and creative-control path**, not
as a commitment to replace Rubber Band or Signalsmith. Its distinctive value
is that an Agent can change the stretch algorithm itself for a particular
musical task: for example, experiment with a local time map or a
material-specific transient rule, then inspect and revise that behavior in
ordinary Python. This benefit matters only when such control produces a
useful result that the existing engine paths cannot express as conveniently.

A NumPy-facing API and in-memory processing are not unique reasons to rewrite
DSP; direct C++ bindings can provide both. The first [Python-versus-native
probe](2026-09-24-python-numba-vs-native-stretch-probe.md) supports numerical
and speed feasibility for one small prototype, but leaves sound quality
unjudged. Its Rubber Band timing includes a CLI wrapper, so it does not
establish a speed win over a direct binding. NumPy/SciPy FFT and Numba also
retain native runtime dependencies; this path is not automatically a
no-binary installation story.

Test two claims separately:

1. **Everyday stretch:** Can the Python implementation meet the required
   audible quality, alignment, and reliability on named beat, pad, voice,
   and mixed-music cases? Use per-cell blind listening and the shared output
   contract; do not infer quality from waveform equality or render speed.
2. **New creative control:** Can an Agent use Python to make a valuable time
   treatment that the native paths cannot express as conveniently? Choose a
   concrete production task and compare the actual authored result and effort,
   not just the theoretical flexibility of a language.

This lane runs beside the binding work and never blocks the first usable
binding release; no document may describe the prototype as a replacement for
either native engine. Keep Rubber Band as the working baseline while these
claims are open. Make a Python engine the default only if it clears the
relevant quality gate and shows a meaningful creative or deployment advantage. If it wins only a
specific creative task, ship it as a specialist option; if neither claim
holds, keep Python for disposable experiments rather than maintaining a
second production engine.

## Proposed first public Python contract

Start with one whole-buffer operation. Its semantics are now pinned by
`tests/contract/`; the spelling below is the implemented facade (see the
[binding plan](../plans/2026-09-24-binding-first-engines.md) for the
agent-oriented revisions):

```python
output = time_stretch(
    audio,                    # np.ndarray: (frames,) or (frames, channels)
    48_000,                   # sample_rate
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
  and finite positive ratio. Input must not be mutated. float32 and float64
  are accepted; engines compute in float32 and the output dtype matches the
  input (decided 2026-09-24). Do not silently clamp peaks.
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
wrapper can quantize floating audio before stretching. The direct binding
avoids this file path, but must still prove its own buffer and precision
behavior; never report `pyrubberband`'s temporary-WAV results as the
binding's precision or speed. Build against unmodified upstream library
sources or installed libraries; do not port, re-express, or patch engine
algorithms in this repo.
[pyrubberband source](https://github.com/bmcfee/pyrubberband/blob/main/pyrubberband/pyrb.py),
[SoundFile documentation](https://python-soundfile.readthedocs.io/)

Signalsmith: `python-stretch` is a native/nanobind reference that expects
`(channels, samples)` float32. Our own binding calls the library directly and
must establish its ratio interpretation, output-size behavior, latency,
flush/tail, and seeded repeatability itself, using `python-stretch` only for
comparison. Do not assume an engine's output can simply be transposed and
treated as perfectly aligned. [binding source](https://github.com/gregogiudici/python-stretch/blob/main/src/signalsmith-bindings.cpp)

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

## Python-lane evidence still owed

The [first probe](2026-09-24-python-numba-vs-native-stretch-probe.md) built a
bounded Python/NumPy/SciPy/Numba phase vocoder and compared it with installed
Rubber Band and Signalsmith on beat and pad excerpts at 0.5, 1.5, and 3.0×.
It did not test voice, mixed music, blind-listening judgments, Rubber Band
R2/R3 as separate choices, or a Python algorithm with transient treatment.
Those missing cases—not more synthetic speed trials—are the lane's next
quality evidence. Its native baselines used wrapper paths; once the direct
bindings exist, later comparisons should use them instead. All candidates
must share sample rate, output length, playback level, and a separately
measured alignment policy.

Measure warmed render time, first-call compile time, peak memory, numerical
validity, transient position, pitch drift, and deployment/setup burden. Ask
Paul to listen blind per source/ratio cell; waveform equality is not a valid
quality oracle because different good stretch algorithms need not output the
same samples. A result here can add a specialist Python option or, only after
clearing the everyday-stretch gate, reopen the default-engine question; it
does not undo the binding-first decision. The quality threshold and target
cells must be declared *before* hearing the candidates.

## Implement in evidence-sized slices

1. **Contract tests first.** Add deterministic mono/stereo arrays: impulse,
   sine, transient clicks, silence, and a seeded random signal. Parameterize
   validation, immutability, shape, ratio direction, and frame-count tests
   independently of any installed engine. Add fixtures from real audio with
   explicit provenance and hashes for integration tests.
2. **Minimal Rubber Band binding.** One native extension path that calls the
   Rubber Band C++ library directly and proves in-memory buffer passing,
   parameter mapping (ratio direction, engine/options), output placement
   (start delay, tail flush, exact frame count), and a working
   build/install/licensing story. `pyrubberband` is a reference, not a
   runtime dependency.
3. **Signalsmith binding.** Call the Signalsmith Stretch C++ library through
   the same facade so the identical contract suite passes on both engines.
   `python-stretch` is a reference, not a runtime dependency.
4. **Alignment and listening.** For each shipped engine, measure impulse position,
   start/end padding, first transient shift, channel crosstalk, and silence
   behavior. Build a small, level-matched blind audition over named
   source/ratio cells. Store judgments per cell; do not convert an overall
   preference into a universal backend ranking.
The Python lane (blind listening, voice/mixed material, one concrete
creative-control task) proceeds in parallel and is not a step in this list.

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
