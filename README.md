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

This repository is **not an audio processor yet**. The public call,
`pytimestretch.time_stretch(audio, sample_rate, *, duration_ratio=...)`,
validates its input and then raises `BackendUnavailableError`, because no
native engine module is built yet. `available_backends()` returns an empty
tuple until one is. There is no PyPI release.

```bash
git clone https://github.com/openmirlab/pytimestretch.git
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

This repository stays private and unpublished while its own public license
and backend distribution topology are undecided. The present `LICENSE` grants
no redistribution rights. The package currently vendors no engine code or
binaries. A future compiled binding may need a different distribution model
for each engine; a close port of upstream code also needs licensing review.
Rubber Band itself has GPL-2.0-or-later/commercial licensing;
`pyrubberband` is ISC; Signalsmith Stretch and its candidate Python binding
are MIT. Those are separate layers; see [NOTICE](NOTICE). Do not infer that
an ISC Python wrapper makes a bundled Rubber Band engine ISC.

## Verification

`uv run pytest -q` checks the current import/stub contract. `uv build`
checks that the package can be built. Real-audio golden fixtures and both
backend contract suites are future work; no audio-quality parity is claimed.
