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

## ✅ Shipped (local branch) — contract and both engine bindings

- `time_stretch` contract suite, native build from vendored engines, and
  working Rubber Band v4.0.0 and Signalsmith Stretch 1.3.2 bindings. See the
  [Rubber Band](thoughts/2026-09-24-rubberband-binding-measurements.md) and
  [Signalsmith](thoughts/2026-09-24-signalsmith-binding-measurements.md)
  measurements.

## ✅ Shipped (local branch) — GPL licensing and Linux wheel CI

- GPL-2.0-or-later LICENSE and a NOTICE of vendored components (step 5).
  A cibuildwheel workflow for manylinux x86_64, CPython 3.10–3.13, verified
  locally in Docker (174 tests pass inside each wheel); not yet run on
  GitHub because the branch is unpushed (step 6).

## ✅ Shipped (local branch) — marker warp, pitch shift, quality presets

- `time_warp`, `pitch_shift`, and `semitones`/`formants`/`quality`
  (`"high"`/`"balanced"`) on both engines, with
  [round-2 listening](thoughts/2026-09-25-blind-listening-round-2.md). See the
  [plan](plans/2026-09-24-warp-pitch-quality.md).

## ✅ Shipped (draft PR #3) — first GitHub Actions run

- `feat/binding-first-engines` pushed; draft PR #3 triggered the wheel
  workflow: ruff and 319 tests green, manylinux_2_28 x86_64 wheels for
  CPython 3.10–3.13 each passing 319 tests in-container (run 35975469626).

## ▶ Next — review PR #3, then a Tactus trial

- Paul reviews and decides whether to merge PR #3; then try the API from a
  real Tactus workflow.

## ⇄ Parallel — Python research lane (non-blocking)

- Round 1 judged the first prototype worst in 4 of 6 cells, so it is not an
  everyday engine. The lane continues only for a concrete creative-control
  task (PaulStretch-style extreme stretching is the leading candidate).
  Never gates the bindings.

## ⏸ Future — evidence-gated

- Before public release: amend the OpenMIRLab constitution with an
  audio-tool category that permits a compiled core (decided 2026-09-24;
  change lives in `openmirlab-dev`) and add macOS/Windows wheel CI. The
  package license becomes GPL-2.0-or-later in the binding plan's step 5.
- Integrate with Tactus only after real-audio, installed-wheel, and listening
  checks demonstrate a stable package boundary.
