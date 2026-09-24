# pytimestretch — plan

> 2026-09-24 · Status index. Design rationale lives in `thoughts/`; grounded
> implementation plans live in `plans/`; shipped behavior lives in Git.

## ✅ Shipped — package bootstrap

- Installable, truthful scaffold, version/stub tests, wheel build, and a
  developer-ready contract thought. See the
  [bootstrap plan](plans/2026-09-24-package-bootstrap.md).

## ✅ Shipped — first Python/Numba feasibility probe

- A small phase-vocoder prototype passed basic length, validity, pitch, and
  speed checks against wrapper-based Rubber Band and Signalsmith; blind
  listening is still pending. See the
  [probe](thoughts/2026-09-24-python-numba-vs-native-stretch-probe.md).

## ✅ Decided — binding-first

- Direct NumPy-facing C++ bindings to Rubber Band, then Signalsmith Stretch.
  No layer over `pyrubberband`/`python-stretch`; no engine re-implementation.
  See the [development thought](thoughts/2026-09-24-time-stretch-package-contract.md).

## ✅ Shipped — contract and both engine bindings

- `time_stretch` contract suite, native build from vendored engines, and
  working Rubber Band v4.0.0 and Signalsmith Stretch 1.3.2 bindings. See the
  [Rubber Band](thoughts/2026-09-24-rubberband-binding-measurements.md) and
  [Signalsmith](thoughts/2026-09-24-signalsmith-binding-measurements.md)
  measurements.

## ✅ Shipped — GPL licensing and Linux wheel CI

- GPL-2.0-or-later LICENSE and a NOTICE of vendored components (step 5).
  A cibuildwheel workflow for manylinux x86_64, CPython 3.10–3.13, verified
  locally in Docker and on GitHub Actions (319 tests pass inside each
  current wheel; step 6).

## ✅ Shipped — marker warp, pitch shift, quality presets

- `time_warp`, `pitch_shift`, and `semitones`/`formants`/`quality`
  (`"high"`/`"balanced"`) on both engines, with
  [round-2 listening](thoughts/2026-09-25-blind-listening-round-2.md). See the
  [plan](plans/2026-09-24-warp-pitch-quality.md).

## ✅ Shipped — first GitHub Actions run and PR #3

- `feat/binding-first-engines` pushed; draft PR #3 triggered the wheel
  workflow: ruff and 319 tests green, manylinux_2_28 x86_64 wheels for
  CPython 3.10–3.13 each passing 319 tests in-container (run 35975469626).
  [PR #3](https://github.com/openmirlab/pytimestretch/pull/3) merged into
  `main` as `3cb1bf7`.

## 🚧 In progress — cross-platform wheels (PR #4)

- [PR #4](https://github.com/openmirlab/pytimestretch/pull/4) adds opt-in
  macOS arm64/x86_64 and Windows AMD64 builds. At `b85f982`, all 12 wheels
  pass 319 tests each in [run 35982257399](https://github.com/openmirlab/pytimestretch/actions/runs/35982257399).
  Linux also passes in [run 35982257252](https://github.com/openmirlab/pytimestretch/actions/runs/35982257252).
  macOS logs confirm vDSP/Accelerate; Windows logs confirm built-in FFTs.
  Implementation and documentation are ready for review and merge.
- Refreshed README/CLAUDE/CHANGELOG to describe the actual tests and private
  wheel artifacts. Checked `openmirlab-skills/plugins/mir`: no public entry
  is appropriate while this package is private. NOTICE requires no update;
  no vendored revision or linked dependency changed.

## ✅ Verified — isolated Tactus trial

- Both backends complete the active Tactus real-source example through an
  installed wheel and `tactus run`. Unrelated drum/bass hashes are preserved;
  the bass override and a repeated native Rubber Band run behave as intended.
  All 20 outputs pass metadata/hash/audio checks; the original production
  stays unchanged. See the [trial evidence](thoughts/2026-09-24-tactus-installed-wheel-trial.md).

## ▶ Next — listen before Tactus adoption

- Compare the trial's sample/mix candidates with the existing production;
  no listening decision has been made. If accepted, handle the dependency,
  processor attribution and production-source change in Tactus.

## ⇄ Parallel — Python research lane (non-blocking)

- Round 1 judged the first prototype worst in 4 of 6 cells, so it is not an
  everyday engine. The lane continues only for a concrete creative-control
  task (PaulStretch-style extreme stretching is the leading candidate).
  Never gates the bindings.

## ⏸ Future — evidence-gated

- Before public release: amend the OpenMIRLab constitution with an
  audio-tool category that permits a compiled core (decided 2026-09-24;
  change lives in `openmirlab-dev`). macOS/Windows CI is implemented in
  PR #4; licensing is already GPL-2.0-or-later.
- Integrate with Tactus only after real-audio, installed-wheel, and listening
  checks demonstrate a stable package boundary.
