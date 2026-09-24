# Changelog

## Unreleased

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
