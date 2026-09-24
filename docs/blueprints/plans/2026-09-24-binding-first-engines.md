# Binding-first engines — plan

> Generated: 2026-09-24 · Source: Paul's binding-first handoff and follow-up decisions (license A, all three desktop platforms, dtype preservation) · Grounding: fresh — repo scaffold, contract thought, first probe, and a survey of pedalboard, pylibrb, python-stretch, and pyrubberband sources

## Context

`stretch_audio()` in `src/pytimestretch/stretch.py` raises `NotImplementedError`;
the package is pure Python (Hatchling, `dependencies = []`) with two smoke tests
in `tests/test_package.py`. The [contract thought](../thoughts/2026-09-24-time-stretch-package-contract.md)
proposes the public call and now records the binding-first decision.

Target: one NumPy-facing facade that calls the Rubber Band and Signalsmith
Stretch C++ libraries directly, in memory, with an identical contract suite
passing on both, installable from a single wheel on Linux, macOS, and Windows
without any system Rubber Band install.

Reference implementations (read, never depend on):

- `spotify/pedalboard` `pedalboard/TimeStretch.h`, `setup.py` — pybind11,
  Rubber Band v3.3.0 (one release behind) single-file build vendored as a submodule; offline mode
  with a full `study()` pass, `isLastCall` flush; **no** start-delay
  compensation and output length **not** trimmed to a target. FFT: vendored
  FFTW on Linux (3–4× speed-up per its comment), vDSP on macOS, built-in FFT
  on Windows; BQResampler everywhere. Whole package GPL-3.0.
- `pawel-glomski/pylibrb` `src/bindings.cpp` — nanobind mapping of
  `RubberBandStretcher`, including `getStartDelay()`/`getPreferredStartPad()`.
- `gregogiudici/python-stretch` `src/signalsmith-bindings.cpp` — nanobind,
  Signalsmith header-only submodule, latency pre/post padding and trimming to
  an exact output length.
- `bmcfee/pyrubberband` `pyrubberband/pyrb.py` — CLI plus temporary WAV;
  frame-major arrays. Its results are never cited as binding precision/speed.

Ratio conventions differ everywhere (pedalboard `stretch_factor` 2.0 = faster;
python-stretch `timeFactor` 0.75 = longer; Rubber Band `timeRatio` 2.0 =
longer). Only `duration_ratio` is public; each engine module owns its
conversion, pinned by tests.

## Resolved questions

- **Architecture:** direct C++ bindings; no runtime dependency on
  `pyrubberband`/`python-stretch`; no port or modification of engine
  algorithms. Python/Numba lane is non-blocking and out of this plan.
- **License (option A):** whole package GPL-2.0-or-later, following the
  pedalboard precedent. Tactus is open source, so GPL is compatible with its
  intended use. Repo stays private and unpublished until release is approved.
- **Engine sourcing:** unmodified upstream sources as git submodules under
  `extern/`, compiled into the extension, each at its newest upstream state:
  - Rubber Band **`v4.0.0`** (tagged 2024-10-25; single-file build). v4 adds
    only `RubberBandLiveShifter`, keeps the stretcher API/audio unchanged,
    and fixes the R2 time-domain-smoothing stack overflow behind pedalboard
    issue #340 — so pedalboard's chunked-`study()` workaround is not needed.
    pedalboard, the first probe, and this host's system library are 3.3.0.
  - Signalsmith Stretch **`main@57b93f4`** (2026-01-24), recorded as
    "1.3.2 + main@57b93f4", not the `1.1.0` git tag. Upstream's header
    declares version 1.3.2 (also published to npm 2025-06; the git tags stop
    at 1.1.0). Post-1.3.2 commits fix `.exact()` (whole-buffer processing
    with exact output length), `flush()`, `signalsmith-linear` move
    assignment, and an MSVC build error needed for Windows. It depends on
    `signalsmith-linear` (FFT), a second pinned submodule. Record SHAs in
    NOTICE and `engine_info()`; bump only by an explicit submodule update
    plus contract suite and measurements.
  Measurements from the first probe used older engines and wrapper paths;
  do not compare them directly with binding measurements.
- **Platforms:** Linux, macOS, Windows wheels.
- **Toolchain (my call):** nanobind + scikit-build-core + CMake — nanobind's
  ndarray support suits NumPy I/O, and two of the references use it.
- **Module shape (my call):** one native module per engine
  (`pytimestretch._rubberband`, `pytimestretch._signalsmith`) behind a
  pure-Python facade, so the packaging can later split (option 3) without code
  changes.
- **Rubber Band defaults (my call):** offline mode, `OptionEngineFiner` (R3),
  `OptionThreadingNever`, `OptionChannelsApart`, full `study()` pass. No
  engine options are public in this plan. (Originally proposed
  `OptionChannelsTogether`; step 3 measured it leaking ~−15 dBFS RMS into a
  silent channel, breaking the contract's channel independence — see the
  [measurements](../thoughts/2026-09-24-rubberband-binding-measurements.md).)
- **FFT backend (my call):** Rubber Band uses its built-in FFT on
  Linux/Windows and vDSP on macOS first; vendoring FFTW is a later,
  timing-justified step. Signalsmith uses `signalsmith-linear`'s default
  FFT, with Accelerate on macOS; PFFFT is a later, timing-justified option.

## Proposed public contract (ratified by approving this plan)

```python
out = time_stretch(audio, sample_rate, *, duration_ratio, backend="rubberband")
```

Revised during step 1 (Paul, 2026-09-24) for agents fluent in NumPy/SciPy
and pyrubberband/librosa habits: renamed to `time_stretch`; `rate=`,
`speed=`, `stretch_factor=` and similar keywords raise a `TypeError` that
shows the equivalent `duration_ratio`; 2-D input with more than 64 channels
is rejected as likely channels-first with an `audio.T` hint;
`available_backends()` and `py.typed` added. `target_frames=` was not added
after a [probe](../thoughts/2026-09-24-target-frames-agent-probe.md) showed
no benefit; the docstring shows `duration_ratio=target / len(audio)`.

| Aspect | Rule |
|---|---|
| `audio` | `np.ndarray`, `float32` or `float64`; shape `(frames,)` or `(frames, channels)`; `frames ≥ 1`, `channels ≥ 1`; all finite. Non-contiguous input accepted (copied). Other dtypes rejected, not silently cast. |
| `sample_rate` | `int` (not `bool`) `> 0`. |
| `duration_ratio` | finite real `> 0`; `> 1` = longer/slower, `< 1` = shorter/faster. |
| Length | `target_frames = floor(frames * duration_ratio + 0.5)`, computed once in the facade; `< 1` rejected. Every backend returns exactly this many frames. |
| Shape / dtype | Same `ndim` and channel count as input; **dtype equals input dtype** (engines compute in float32; docs say so). New C-contiguous array; input never mutated. |
| Placement | Engine start latency is compensated so input time `t` lands near output time `t × duration_ratio`; the tolerance is set from step 3/4 measurements and then pinned in tests. |
| `backend` | `"rubberband"` or `"signalsmith"`. No silent fallback. |
| Errors | `pytimestretch.InvalidAudioError(ValueError)` for bad input/params; `UnknownBackendError(ValueError)`; `BackendUnavailableError(ImportError)` if a native module failed to load (message says how to rebuild); `EngineError(RuntimeError)` for engine-reported failure. |

No clamping, normalization, pitch shift, variable ratio, streaming, or engine
options in this plan.

## Decided at plan review (2026-09-24)

- Plan and proposed contract approved; commit and implement locally, no PR.
- **CI before public release: Linux only.** macOS/Windows wheels stay a
  build-configuration target (CMake defines kept per platform) and are
  added to CI before release; Paul may build on his Mac by hand meanwhile.
- **OpenMIRLab policy: amend the constitution with an audio-tool category**
  permitting a compiled core, in `openmirlab-dev`. That is a separate change
  in that repository; it blocks public release only, not this plan.

## Approach

Each step is independently verifiable; stop and report if a gate fails.

1. **Contract suite and facade (pure Python).** Add `errors.py`, a backend
   registry `_backends.py` (name → lazy module loader), and implement
   validation, `target_frames`, frame-major → channels-first float32
   conversion, dispatch, and result checks in `stretch.py`. Contract tests in
   `tests/contract/` run against every registered backend plus a test-only
   fake backend (simple resampler) so they pass before any native code exists:
   validation errors, immutability, shape/ndim, dtype preservation, exact
   length across ratios {0.25, 0.5, 0.999, 1.0, 1.5, 3.0} and odd frame counts,
   stereo channel order, no fallback.
2. **Native build skeleton.** Switch the build backend to scikit-build-core
   (version still single-sourced from `__about__.py` via the regex metadata
   provider), add `CMakeLists.txt`, nanobind, `numpy` runtime dependency, and
   the two submodules. Build `_rubberband` exposing only `engine_info()`
   (upstream version, FFT/resampler defines). Gate: `uv build` produces a
   platform wheel that installs in a clean venv on this Linux host with no
   system Rubber Band visible (verify with `ldd`), and `import pytimestretch`
   works.
3. **Rubber Band stretch.** Native `stretch(buffer[C,N] float32, sample_rate,
   time_ratio, target_frames) -> float32[C, target_frames]`: offline setup,
   `setExpectedInputDuration`, `study()`, `process(..., final)`, retrieve loop, then measure and
   compensate `getStartDelay()`, and pad/trim to `target_frames`. Release the
   GIL during processing. Gates: contract suite passes; impulse-placement,
   440 Hz pitch, silence-in/silence-out, stereo crosstalk measured and
   recorded; round-trip precision with float64 input documented; warmed timing
   vs the probe's CLI numbers recorded as a separate integration path.
4. **Signalsmith stretch.** Same native signature in `_signalsmith`, using the
   pinned version's `.exact()` whole-buffer method (python-stretch predates
   it and pads/trims by hand) with a fixed seed for determinism. Gate: the
   identical contract suite passes on both backends; same measurements
   recorded; determinism test (same input → identical output).
5. **Docs and licensing in one change.** Replace `LICENSE` with
   GPL-2.0-or-later text; `NOTICE` lists vendored Rubber Band (GPL-2.0-or-later)
   and Signalsmith Stretch (MIT) with pinned revisions; README gains a working
   example, dtype/precision note, and install story; update CLAUDE.md,
   AGENTS.md, CHANGELOG, the thought's contract section, and `plan.md`. Keep
   `Private :: Do Not Upload`. Measurements go in a dated thought under
   `docs/blueprints/thoughts/`.
6. **Linux wheel CI.** cibuildwheel workflow on Linux only (per plan
   review): build, install into a clean env, and run the contract suite.
   macOS and Windows jobs are added before public release.

## Critical files

| File | Role and planned change |
|---|---|
| `src/pytimestretch/stretch.py` | Facade: validation, `target_frames`, layout/dtype conversion, dispatch, result checks. Sole owner of the public contract. |
| `src/pytimestretch/errors.py` (new) | Public error hierarchy, re-exported from `__init__.py`. |
| `src/pytimestretch/_backends.py` (new) | Backend name → lazy native loader; `BackendUnavailableError` mapping. |
| `src/pytimestretch/__init__.py` | Export errors; header docstring updated. |
| `native/rubberband_module.cpp` (new) | Rubber Band binding: ratio conversion, offline loop, latency compensation, exact length. |
| `native/signalsmith_module.cpp` (new) | Signalsmith binding with the same native signature. |
| `CMakeLists.txt` (new) | nanobind modules, per-platform engine defines, single-file Rubber Band sources. |
| `extern/rubberband`, `extern/signalsmith-stretch`, `extern/signalsmith-linear` (new submodules) | Unmodified upstream sources at pinned revisions. |
| `pyproject.toml` | scikit-build-core backend, regex version provider, `numpy` dependency, GPL metadata, test markers. |
| `tests/contract/` (new), `tests/test_package.py` | Engine-independent contract suite; stub test replaced. |
| `.github/workflows/wheels.yml` (new, step 6) | cibuildwheel three-platform build and test. |
| `README.md`, `CLAUDE.md`, `AGENTS.md`, `NOTICE`, `LICENSE`, `CHANGELOG.md`, `docs/blueprints/plan.md` | Kept truthful with each capability. |

## Verification

- Every step: `uv run pytest -q`, `uv run ruff check .`, `uv build`.
- Step 2+: clean-venv wheel install on this host, `ldd` shows no system
  `librubberband`; `engine_info()` reports Rubber Band v4.0.0, the
  Signalsmith commit, and each FFT backend.
- Steps 3–4: contract suite on both engines; measured placement, pitch,
  crosstalk, silence, precision, determinism, and warmed timing written to a
  dated thought with exact submodule revisions and build flags.
- Listening: a short level-matched blind page (beat, pad, voice, mixed) at
  0.5/1.5/3.0 through the new bindings for Paul — evidence, not a gate for
  merging the bindings, and not a universal ranking.
- Step 6: clean install and the contract suite green on the Linux runner;
  macOS/Windows runner checks are a pre-release gate.

## Out of scope

Pitch shift, formants, variable ratio or key-frame maps, streaming/real-time,
exposing engine options, vendoring FFTW, PyPI publication or public
visibility, Tactus integration, and the Python/Numba research lane.
