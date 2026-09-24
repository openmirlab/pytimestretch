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

## ▶ Next — listening, then push and first CI run

- Paul's blind listening of Rubber Band, Signalsmith, and the Python
  prototype (local page); record per-cell judgments in the measurement notes.
- Push `feat/binding-first-engines` when Paul approves, and confirm the
  first GitHub Actions run.
- Open follow-ups from the measurements: `ChannelsApart` vs `ChannelsTogether`
  on real stereo mixes, R3 speed (faster FFT or an R2 option), Rubber Band's
  ~13 ms early peak at ×3.0.

## ⇄ Parallel — Python research lane (non-blocking)

- Record the pending blind-listening judgments, add voice and mixed music,
  and try one concrete creative-control task. Never gates the bindings.

## ⏸ Future — evidence-gated

- Before public release: amend the OpenMIRLab constitution with an
  audio-tool category that permits a compiled core (decided 2026-09-24;
  change lives in `openmirlab-dev`) and add macOS/Windows wheel CI. The
  package license becomes GPL-2.0-or-later in the binding plan's step 5.
- Integrate with Tactus only after real-audio, installed-wheel, and listening
  checks demonstrate a stable package boundary.
