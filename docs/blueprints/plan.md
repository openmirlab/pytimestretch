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

## ✅ Shipped (local branch) — contract and Rubber Band binding

- `time_stretch` contract suite, native build from vendored engines, and a
  working Rubber Band v4.0.0 binding. See the
  [measurements](thoughts/2026-09-24-rubberband-binding-measurements.md).

## ▶ Next — Signalsmith binding, then licensing/docs and Linux CI

- Bind Signalsmith Stretch so the same contract suite passes on both.
  See the [binding-first engines plan](plans/2026-09-24-binding-first-engines.md).

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
