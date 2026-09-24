# pytimestretch

**A Python home for time stretching, with the algorithm boundary still under test.**

`pytimestretch` is a private OpenMIRLab package under development. The name
deliberately says what the package is for. The current product hypothesis is
a NumPy-facing Python binding to native time-stretch libraries, initially
Rubber Band and Signalsmith Stretch—not a wrapper around existing Python
wrappers. A competing hypothesis is that a focused Python/NumPy/SciPy/Numba
implementation could meet our actual needs without those engines. That fork
is not settled; the [development thought](docs/blueprints/thoughts/2026-09-24-time-stretch-package-contract.md)
defines the deciding experiment. Rubber Band remains Tactus's working
baseline, not a proven universal winner.

## Current status

This repository is an **installable scaffold, not an audio processor yet**.
`pytimestretch.__version__` imports. `stretch_audio(...)` deliberately raises
`NotImplementedError`. No native binding is built or bundled by this scaffold.
There is no PyPI release.

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
- A direct C++ binding is a candidate architecture. A measured
  Python/NumPy/SciPy/Numba engine is also a candidate; neither is shipped.
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
