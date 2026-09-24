# Changelog

## Unreleased

- Prepared public GitHub source with complete installation, API, migration,
  verification, upstream-credit and licensing documentation. PyPI publication
  and versioned releases remain unapproved.
- Made two host-dependent speed comparisons opt-in with `pytest -m performance`;
  the default suite retains all audio correctness tests. A macOS x86_64/Rosetta
  run measured Signalsmith balanced/high at 1.21x, below the previous 1.3x
  threshold despite both presets functioning correctly.
- Established a private, installable package scaffold and an explicit
  unimplemented audio entry point.
- Recorded the first backend-development contract and verification gates.
- Recorded a first Python/Numba feasibility probe (numerical and speed checks
  only; blind listening pending).
- Decided binding-first: direct C++ bindings to Rubber Band, then Signalsmith
  Stretch; the Python/Numba stretcher continues as a non-blocking research
  lane.
- Added `time_stretch` with an engine-independent contract suite and
  agent-oriented errors (`rate=`-style keywords, channels-first arrays).
- Built Rubber Band v4.0.0 from vendored sources into the package; offline R3
  stretching now works with exact output length, preserved dtype, and
  measured placement, pitch, crosstalk, and determinism.
- Added the Signalsmith Stretch backend (1.3.2 + main@57b93f4) through
  `.exact()`; the same contract suite passes on both engines.
- Added `pitch_shift`, `time_warp` (integer source→output markers), and
  `semitones`/`formants`/`quality` options on both engines, with teaching
  errors for pyrubberband's `n_steps=`, `time_map=`, and `rbargs=`.
- Fixed Signalsmith warp drift for markers whose output spans are not
  whole frames; constant-ratio warps now match `time_stretch`.
- Licensed the package under GPL-2.0-or-later with a NOTICE of vendored
  components; the repository remains private and unpublished.
- Added a Linux wheel CI workflow (manylinux x86_64, CPython 3.10–3.13) that
  tests every built wheel and never publishes.
- Added opt-in macOS arm64/x86_64 and Windows AMD64 wheel CI for CPython
  3.10–3.13, including per-wheel engine metadata. Fixed macOS deployment
  targets for nanobind's C++17 allocation requirements and added MSVC
  compilation options; artifacts remain private and unpublished.
