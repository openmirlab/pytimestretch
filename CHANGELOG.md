# Changelog

## Unreleased

- Compensate Signalsmith's analysis-window lookback when `time_warp` changes
  ratio, while retaining constant-ratio parity and exact output length. In
  the issue #12 4× local-warp repro, the inside click moves from about 175 ms
  late to within 5 ms; tested across 22.05–96 kHz and both quality presets.
- Use 256-frame Rubber Band process blocks for key-frame warps (plain
  stretches keep 4096). In the same repro, the inside click moves from about
  154 ms early to about 32 ms early and later clicks from about 57 ms late
  to about 13 ms early. It remains an approximate-placement backend.
- Make Bungee Basic the default `time_warp` renderer and accept
  `backend="bungee"` explicitly. The existing marker format now reaches
  Bungee's measured click placement without manual column reversal.
  Rubber Band and Signalsmith remain explicit choices for their sound,
  broader channel/sample-rate support, formants, and quality presets.
  Default warp calls now follow Bungee's mono/stereo, 8–192 kHz and
  ±24-semitone limits; unsupported formant/quality options raise clearly.
- Correct the Signalsmith `time_warp` pre-roll rate for multi-marker curves.
  On the measured 4× local warp, clicks outside the changed region move from
  about 14 ms late to within 0.4 ms of the marker curve. Abrupt changes can
  still displace clicks inside the region.
- Pin the 4× click placement case and ratio-turn clicks for the Bungee path;
  document its measured placement and distinct sound/option limits.

## [0.2.0] - 2026-09-25

Source tag available from GitHub; not published to PyPI.

- Add `time_scrub` using direct Bungee Basic v2.4.30 bindings. Output-first
  control points drive continuous forward, held, and reverse source motion;
  global pitch is independent, and the result has an exact frame count.
  Preserve the existing stretch/warp backend contract and document Basic's
  dense-transient and stationary-grain limits.
- Vendor pinned Bungee Basic, Eigen, and PFFFT sources, build them into the
  native extension, and include MPL/UCAR attribution in source and wheels.
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

[0.2.0]: https://github.com/openmirlab/pytimestretch/tree/v0.2.0
[0.1.0]: https://github.com/openmirlab/pytimestretch/tree/v0.1.0
