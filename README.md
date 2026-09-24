# pytimestretch

**NumPy-facing Python bindings to native time-stretch engines.**

`pytimestretch` is a private OpenMIRLab package under development. The
product direction is decided: a NumPy-facing Python extension that calls the
Rubber Band and Signalsmith Stretch C++ libraries directly, in memory. It is
not a wrapper around `pyrubberband` or `python-stretch` (those serve as
behavior references and comparison baselines), and it does not re-implement
either engine's algorithm. A small Python/NumPy/SciPy/Numba prototype passed
basic correctness and speed checks in a [first probe](docs/blueprints/thoughts/2026-09-24-python-numba-vs-native-stretch-probe.md),
but its sound quality has not been judged; it continues as a research lane
for special creative control, not a replacement for either engine. See the
[development thought](docs/blueprints/thoughts/2026-09-24-time-stretch-package-contract.md).
Rubber Band remains Tactus's working baseline, not a proven universal winner.

## Current status

**Both engines work.** Three functions call Rubber Band v4.0.0 (the default)
or Signalsmith Stretch 1.3.2 (`backend="signalsmith"`), both compiled from
vendored sources into the package — no system library needed:

```python
import numpy as np
import soundfile as sf
import pytimestretch as pts

audio, sr = sf.read("loop.wav", dtype="float32")        # (frames, channels)

# Change duration, keep pitch. duration_ratio = output length / input length.
slower = pts.time_stretch(audio, sr, duration_ratio=1.5)
assert len(slower) == round(len(audio) * 1.5)

# Change pitch, keep duration. For voices, preserve formants.
vocal_up = pts.pitch_shift(audio, sr, semitones=3, formants="preserve")

# Warp: move source frames to output frames (e.g. a hit at 0.52 s onto beat 2
# at 120 BPM). Integer (source, output) pairs from (0, 0) to (len, output_len);
# with backend="signalsmith", keep markers >= 100 ms apart for tight timing.
hit, beat2 = int(round(0.52 * sr)), int(round(0.5 * sr))
warped = pts.time_warp(audio, sr, markers=[(0, 0), (hit, beat2), (len(audio), len(audio))])
```

- `duration_ratio` runs the opposite way to pyrubberband/librosa `rate`
  (`rate=2.0` there is `duration_ratio=0.5` here); passing `rate=`,
  `n_steps=`, `time_map=`, or `rbargs=` raises an error that shows the
  equivalent. `time_stretch` and `time_warp` also take `semitones=`.
- `formants="shift"` (default) lets the spectral envelope move with the
  pitch; use `"preserve"` for voices — it was clearly preferred on a vocal
  in blind listening.
- `quality="high"` (default) or `"balanced"`: about 3× faster on Rubber
  Band and 1.7× on Signalsmith; no audible difference was heard on a
  full-mix tempo change.
- Output length is exact, dtype matches the input (engines compute in
  float32), and the input is never modified.

In two rounds of blind listening (one listener, short loops) Rubber Band was
preferred wherever a difference was heard; Signalsmith was close on a bass
pitch shift. Measurements and listening notes are in
`docs/blueprints/thoughts/`. Building from source needs CMake ≥ 3.24 and a
C++17 compiler. There is no PyPI release.

```bash
git clone --recurse-submodules https://github.com/openmirlab/pytimestretch.git
cd pytimestretch
uv sync --group dev
uv run pytest -q
uv build
```

The repository is private; clone access requires OpenMIRLab permission.

CI builds and tests CPython 3.10–3.13 wheels for Linux x86_64
(`manylinux_2_28`), macOS arm64 and x86_64, and Windows AMD64. Wheels are
private GitHub Actions artifacts, not published packages. Linux CI runs on
every pull request and on pushes to `main`; macOS/Windows builds run only
with the `all-platforms` PR label or a manual workflow dispatch.

## Intended boundary

- The caller owns musical intent: source, target duration or timing, engine
  choice, and any creative parameter choices.
- `pytimestretch` owns the NumPy-facing contract, input validation,
  exact output length and marker placement, and clear errors.
- Audio is processed by direct C++ bindings to Rubber Band and Signalsmith
  Stretch behind one shared contract. A Python engine may later ship only as
  a specialist option backed by its own listening evidence.
- The package will not take over Tactus arrangement semantics, a DAW session,
  or a real-time playback engine.

Design and evidence live in `docs/blueprints/`: the
[development thought](docs/blueprints/thoughts/2026-09-24-time-stretch-package-contract.md),
the [binding plan](docs/blueprints/plans/2026-09-24-binding-first-engines.md),
and the [warp/pitch/quality plan](docs/blueprints/plans/2026-09-24-warp-pitch-quality.md).

## Licensing and distribution

pytimestretch is licensed under **GPL-2.0-or-later** (see [LICENSE](LICENSE)
and [NOTICE](NOTICE)). Its wheels compile in Rubber Band (GPL-2.0-or-later
or commercial), which makes the package as a whole GPL — the same choice
Spotify's pedalboard made for the same reason. Signalsmith Stretch and
Signalsmith Linear are MIT; nanobind's statically linked runtime is
BSD-3-Clause. Open-source consumers such as Tactus can use it under the GPL;
a closed-source product that distributes Rubber Band needs a commercial
licence from Breakfast Quay.

The repository stays private and unpublished until the OpenMIRLab
constitution gains an audio-tool category that permits a compiled core.

## Verification

`uv run pytest -q` runs the shared contract suite against both compiled
engines and a test-only fake, plus engine-specific signal measurements.
`uv run ruff check .` checks Python lint. `uv build` builds an sdist and a
wheel from it; CI installs and tests each platform wheel. Real-audio
listening evidence is recorded in `docs/blueprints/thoughts/`; committed
real-audio golden fixtures remain future work. No audio-quality parity
between engines is claimed.
