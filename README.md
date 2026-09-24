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

**Both engines work.** `time_stretch` calls Rubber Band v4.0.0 (R3 engine,
offline; the default) or Signalsmith Stretch 1.3.2 (`backend="signalsmith"`),
both compiled from vendored sources into the package — no system library
needed:

```python
import soundfile as sf
import pytimestretch

audio, sr = sf.read("loop.wav", dtype="float32")   # (frames, channels)
slower = pytimestretch.time_stretch(audio, sr, duration_ratio=1.5)
assert len(slower) == round(len(audio) * 1.5)
```

`duration_ratio` is output length / input length (> 1 = longer/slower) —
the opposite direction of pyrubberband/librosa `rate`. The output has the
exact computed length and the input's dtype (engines compute in float32).
`available_backends()` reports `("rubberband", "signalsmith")`. Measured
placement, pitch, precision, and speed are in `docs/blueprints/thoughts/`;
blind listening has not been done, so no audio-quality claim is made. Building from source needs CMake
≥ 3.24 and a C++17 compiler. There is no PyPI release.

```bash
git clone --recurse-submodules https://github.com/openmirlab/pytimestretch.git
cd pytimestretch
uv sync --group dev
uv run pytest -q
uv build
```

The repository is private; clone access requires OpenMIRLab permission.

## Intended boundary

- The caller owns musical intent: source, target duration or timing, engine
  choice, and any creative parameter choices.
- `pytimestretch` will own the NumPy-facing contract, input validation,
  exact output length/alignment policy, and clear errors.
- Audio is processed by direct C++ bindings to Rubber Band first, then
  Signalsmith Stretch, behind one shared contract. Neither binding exists
  yet. A Python engine may later ship only as a specialist option backed by
  its own listening evidence.
- The package will not take over Tactus arrangement semantics, a DAW session,
  or a real-time playback engine.

The proposed API and exact acceptance checks are in the
[development thought](docs/blueprints/thoughts/2026-09-24-time-stretch-package-contract.md).
The [bootstrap plan](docs/blueprints/plans/2026-09-24-package-bootstrap.md)
records what this first setup does and does not implement.

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

`uv run pytest -q` checks the current import/stub contract. `uv build`
checks that the package can be built. Real-audio golden fixtures and both
backend contract suites are future work; no audio-quality parity is claimed.
