# Changelog

## Unreleased

- Add a separate `extreme_stretch` operation using direct libpaulstretch
  v0.3.0/KissFFT bindings. Preserve the requested factor and native
  approximate duration; accept mono/stereo clips of at least 81,920 frames.
  Spectral phase varies across repeated renders.
- Allow `extreme_stretch` ratios below 1 for native PaulStretch compression;
  `0.1` is accepted, with approximate output length. Guard extremely small
  ratios against the upstream input-skip integer limit.
- Convey the combined source distribution and wheels under GPL-2.0-only
  because libpaulstretch is GPLv2; retain original-code GPL-2.0-or-later
  notices and bundle upstream license files.
- Use uv throughout installation and execution examples, and distinguish
  C++ source-build requirements from precompiled wheel installation.
- Credit pedalboard and pylibrb alongside the original engines and other
  binding references in README and NOTICE.
- Keep local blueprints out of Git tracking and source distributions; remove
  public documentation's dependency on those notes.

## [0.1.0] - 2026-09-24

First versioned source snapshot. Available from GitHub; not published to PyPI.

- Added direct, in-memory NumPy bindings to Rubber Band v4.0.0 (offline R3)
  and Signalsmith Stretch 1.3.2 + main@57b93f4, compiled from pinned vendored
  sources without a system Rubber Band dependency.
- Added `time_stretch`, `pitch_shift`, and marker-based `time_warp`, with
  independent pitch, formant preservation, and high/balanced quality options.
- Defined a shared contract for frame-major mono/multichannel audio, exact
  output length, dtype preservation, input immutability, and actionable errors
  for pyrubberband/librosa conventions.
- Fixed Signalsmith warp drift on non-integer output spans; constant-ratio
  warps match `time_stretch`.
- Added engine-specific signal measurements, contract tests, and installed-wheel
  CI for CPython 3.10–3.13 on Linux x86_64, macOS arm64/x86_64, and Windows AMD64.
  macOS/Windows builds are opt-in. Host-dependent timing comparisons run
  separately with `pytest -m performance`.
- Documented source/wheel installation, runnable API examples, processing
  limitations, upstream credits, and GPL-2.0-or-later licensing.
- Verified both engines in an isolated Tactus production trial; the listener
  accepted all candidates. This does not claim universal audio-quality parity.
- Matched the imported version to installed distribution metadata in the
  package smoke test, replacing the bootstrap-only version assertion.

[0.1.0]: https://github.com/openmirlab/pytimestretch/tree/v0.1.0
