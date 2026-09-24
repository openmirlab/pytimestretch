# pytimestretch

**Time stretching, pitch shifting, and marker-based time warping for NumPy audio.**

[![Wheels](https://github.com/openmirlab/pytimestretch/actions/workflows/wheels.yml/badge.svg)](https://github.com/openmirlab/pytimestretch/actions/workflows/wheels.yml)
[![License: GPL-2.0-or-later](https://img.shields.io/badge/license-GPL--2.0--or--later-blue.svg)](LICENSE)

## Why this exists

Rubber Band and Signalsmith Stretch provide capable native audio-processing
engines. pytimestretch gives them one small Python interface: pass a NumPy
array, choose a duration, pitch, or timing map, and receive an array with a
predictable shape, dtype, and frame count.

This is a Python package with C++ native extensions, not a pure-Python
implementation. Both engines are compiled into the package and called
directly in memory.
Processing needs no system Rubber Band installation, command-line subprocess,
intermediate WAV file, or runtime dependency on another Python wrapper.

This is an early-stage package. **v0.1.0 is the first source tag; there is
no PyPI release yet**. The API may change during the 0.x series.

## Acknowledgments

The audio algorithms are the work of the upstream engine authors:

- **Chris Cannam / Breakfast Quay** — [Rubber Band Library](https://github.com/breakfastquay/rubberband),
  used here at v4.0.0 with its offline R3 engine.
- **Geraint Luff / Signalsmith Audio** — [Signalsmith Stretch](https://github.com/Signalsmith-Audio/signalsmith-stretch)
  and [Signalsmith Linear](https://github.com/Signalsmith-Audio/linear), the
  time/pitch processor and its FFT support.
- **Wenzel Jakob and contributors** — [nanobind](https://github.com/wjakob/nanobind),
  which connects the C++ engines to Python and NumPy.

The binding and build design also draws on these reference projects:

- **Spotify and contributors** — [pedalboard](https://github.com/spotify/pedalboard),
  a reference for Rubber Band's single-file build, offline processing, and
  platform-specific FFT configuration.
- **pawel-glomski and contributors** — [pylibrb](https://github.com/pawel-glomski/pylibrb),
  a reference for nanobind bindings to `RubberBandStretcher`, including its
  start-delay and preferred-padding APIs.
- **gregogiudici and contributors** — [python-stretch](https://github.com/gregogiudici/python-stretch),
  a reference for Signalsmith's nanobind integration and latency padding/trimming.
- **bmcfee and contributors** — [pyrubberband](https://github.com/bmcfee/pyrubberband),
  a reference for frame-major arrays, API comparisons, and early experiments.

These projects are design references, not runtime dependencies.
See [NOTICE](NOTICE) for pinned revisions, copyright notices, and licenses.

## Features

- `time_stretch`: change duration while keeping pitch, or shift both together.
- `pitch_shift`: transpose audio without changing its duration.
- `time_warp`: map source frame positions to output frame positions.
- Two interchangeable backends: `"rubberband"` (default) and `"signalsmith"`.
- Formant preservation and `"high"` / `"balanced"` quality presets.
- Mono or multichannel, frame-major NumPy arrays; exact output frame counts,
  preserved input dtype, and no input mutation.

## Scope

These are offline, whole-buffer operations. File I/O, resampling, loudness
normalization, beat detection, musical decisions, and real-time playback
belong to the caller.

## Install

### From source

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git,
and provide a C++17 toolchain (GCC, Clang, or MSVC). Python 3.10 or newer is
required; the example selects Python 3.12, which uv can provision. The native
build uses CMake 3.24 or newer and scikit-build-core; the isolated build
installs its Python build dependencies and obtains CMake when needed.

Clone the pinned source tag and let uv create `.venv` and install the package:

```bash
git clone --branch v0.1.0 --recurse-submodules https://github.com/openmirlab/pytimestretch.git
cd pytimestretch
uv sync --python 3.12 --no-dev
```

If you already cloned without submodules, run
`git submodule update --init --recursive` before installing. The engines are
compiled from these vendored sources; a system `librubberband` is not used.

### Built wheels

The [GitHub Actions runs](https://github.com/openmirlab/pytimestretch/actions)
provide wheel artifacts. Download and unzip the artifact for your platform,
then install the wheel matching your Python version and architecture.
A matching wheel already contains the compiled engines, so installing it
requires no C++ compiler. In a separate working directory (outside the source
checkout), create an environment matching the wheel's Python version:

```bash
uv venv --python 3.12
uv pip install "/path/to/the-matching-cp312-wheel.whl"
```

CI currently builds and tests **CPython 3.10–3.13** on:

| Platform | Architectures | Artifact |
| --- | --- | --- |
| Linux (`manylinux_2_28`) | x86_64 | `wheels-linux` |
| macOS | arm64, x86_64 | `wheels-macos` |
| Windows | AMD64 | `wheels-windows` |

macOS/Windows builds are opt-in, so those artifacts are available only on
runs of **Wheels (all platforms)**. Actions artifacts are development builds,
not versioned releases; downloading them through GitHub requires sign-in.

## Quick start

This example needs only pytimestretch and its NumPy dependency. Save it as
`quick_start.py` in the directory where you installed the package and run
`uv run --no-project python quick_start.py`. This uses the existing `.venv`
without changing its installed packages.

```python
import numpy as np
import pytimestretch as pts

sr = 44_100
t = np.arange(sr, dtype=np.float64) / sr
audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

# Duration ratio = output length / input length: 1.5 is longer/slower.
longer = pts.time_stretch(audio, sr, duration_ratio=1.5)
assert longer.shape == (66_150,)
assert longer.dtype == audio.dtype

# Raise pitch by three semitones without changing duration.
higher = pts.pitch_shift(audio, sr, semitones=3)
assert higher.shape == audio.shape

# Move the midpoint later while keeping the total duration.
warped = pts.time_warp(
    audio, sr, markers=[(0, 0), (sr // 2, sr * 3 // 5), (len(audio), len(audio))]
)
assert warped.shape == audio.shape

# Choose the other engine explicitly; there is no silent fallback.
alternative = pts.time_stretch(audio, sr, duration_ratio=1.5, backend="signalsmith")
print(pts.available_backends())  # ('rubberband', 'signalsmith') in a full build
```

For files, install `soundfile` separately with `uv pip install soundfile`,
then run the following script with `uv run --no-project python process_file.py`:

```python
import soundfile as sf
import pytimestretch as pts

audio, sr = sf.read("input.wav", dtype="float32")  # (frames, channels)
output = pts.time_stretch(audio, sr, duration_ratio=1.25)
sf.write("output.wav", output, sr, subtype="FLOAT")
```

## Processing contract

| Input or output | Rule |
| --- | --- |
| Audio | A nonempty, finite NumPy array with dtype `float32` or `float64`. |
| Layout | `(frames,)` for mono or `(frames, channels)` for multichannel; 1–64 channels. Non-contiguous arrays are accepted. |
| Sample rate | A positive integer in Hz; no implicit resampling. |
| Duration ratio | A finite positive number; `2.0` doubles duration, `0.5` halves it. |
| Stretch length | Exactly `floor(len(audio) * duration_ratio + 0.5)` frames; a result shorter than one frame is rejected. |
| Pitch-shift length | Exactly `len(audio)` frames. |
| Warp length | Exactly the last marker's output frame. |
| Output | A new C-contiguous array with the same dtype, channel count, and dimensionality as the input. The input is never modified. |
| Precision | Both engines calculate in `float32`, including when the input/output dtype is `float64`. |

To fit a known frame count, use
`duration_ratio=target_frames / len(audio)`. The rounding rule is half-up,
not Python's ties-to-even `round()`.

Processing does not normalize or clip the output. Check headroom before
encoding to an integer PCM format. A ratio of `1.0` still passes through the
engine; it is not a promise of sample-identical bypass.

### Pitch, formants, and quality

All three functions accept `backend`, `quality`, and `formants`.
`time_stretch` and `time_warp` also accept an optional `semitones=0.0`;
`pitch_shift` requires `semitones`.

```python
# Slow down and transpose together.
result = pts.time_stretch(audio, sr, duration_ratio=1.2, semitones=-2)

# Keep the spectral envelope in place when transposing a voice.
result = pts.pitch_shift(audio, sr, semitones=3, formants="preserve")

# Use the engine's lower-cost preset.
result = pts.time_stretch(audio, sr, duration_ratio=1.2, quality="balanced")
```

- `formants="shift"` (default) lets the spectral envelope move with pitch;
  `"preserve"` asks the engine to retain it. Results depend on the material.
- `quality="high"` is the default; `"balanced"` reduces processing work.
  The speed difference depends on the engine, platform, and audio. It is
  not a guaranteed speedup ratio or a promise of equal sound quality.

### Warp markers

Markers are integer `(source_frame, output_frame)` pairs. Supply at least
two pairs, starting at `(0, 0)` and ending at `(len(audio), output_frames)`.
Both columns must strictly increase; seconds and floating-point frame
values are rejected.

The final frame count is exact. **Transient placement is approximate**:
markers guide the engine rather than guarantee sample-exact alignment of
an audible attack. For Signalsmith, markers at least 100 ms apart are a
useful starting point from the measured cases. Dense markers and abrupt
changes in local stretch ratio can smear or lose transients with either
engine. Listen to the result for your material.

### Coming from librosa or pyrubberband

| Existing convention | pytimestretch equivalent |
| --- | --- |
| `rate=2.0` (twice as fast) | `duration_ratio=0.5` |
| `n_steps=3` | `semitones=3` |
| `time_map=[...]` | `markers=[...]`, with the endpoint rules above |
| librosa `(channels, samples)` | Pass `audio.T`, then transpose the result back if needed. |
| `rbargs={...}` | No arbitrary engine-option passthrough; use the named public options. |

Known foreign keywords raise an error showing the corresponding call.
Invalid audio/options raise `InvalidAudioError`; backend selection/import
failures raise `UnknownBackendError` or `BackendUnavailableError`. Unsupported
backend options raise `UnsupportedOptionError`, and engine failures raise
`EngineError`. These package errors derive from `PytimestretchError`;
unrecognized Python keywords raise `TypeError`.

## Development and verification

```bash
uv sync --group dev
uv run pytest -q
uv run ruff check .
uv build
```

The default suite checks the shared contract on both compiled engines and a
test-only fake, plus engine-specific pitch, placement, silence, channel
independence, and determinism. CI tests installed wheels across the matrix
above. `uv build` builds an sdist and then a wheel from that sdist.

Two host-dependent speed comparisons are excluded from the default suite.
Run them explicitly on a controlled machine with
`uv run pytest -q -m performance`; shared runners and CPU emulation do not
provide a stable timing threshold.

After changing native code, rebuild the installed package with
`uv sync --reinstall-package pytimestretch`. Linux CI runs for pull requests
and pushes to `main`; macOS/Windows CI runs for PRs labeled `all-platforms`
or via manual dispatch.

The signal tests provide bounded evidence for their inputs, ratios, and
builds; they do not establish a universal ranking of engines or audio-quality
parity. Real-audio fixtures are not bundled with the package.

## License

**GPL-2.0-or-later.** Wheels include Rubber Band, which is GPL-2.0-or-later;
Signalsmith Stretch and Signalsmith Linear are MIT, and nanobind's runtime
is BSD-3-Clause. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Rubber Band also offers [separate commercial licensing](https://breakfastquay.com/rubberband/license.html).
This repository and its distributed package remain under the license above.

## Support

Report reproducible problems in [GitHub Issues](https://github.com/openmirlab/pytimestretch/issues).
Include the Python/OS/architecture, backend and quality, input shape/dtype,
sample rate, and a small input that reproduces the problem. Prefer synthetic
audio when the original recording cannot be shared.
